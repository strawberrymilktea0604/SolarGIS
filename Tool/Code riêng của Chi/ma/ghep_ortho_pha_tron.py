#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ghép ortho nhiệt CÓ PHA TRỘN ở biên Voronoi — thử làm mượt chỗ gãy khúc.

VẤN ĐỀ: ghep_ortho_nhiet.py cho mỗi ô lưới lấy từ ĐÚNG MỘT ảnh (ảnh có tâm chụp
gần nhất). Chỗ hai vùng ảnh giáp nhau, hai ảnh đặt lệch nhau vài chục cm nên biên
tấm pin gãy thành răng cưa. Đo được 426 chỗ gãy > 30 px, mạnh nhất 752 px (~21 m).

CÁCH LÀM: mỗi ô lấy từ HAI ảnh gần nhất, trộn theo trọng số phụ thuộc khoảng cách
tới biên Voronoi:

    d1 = khoảng cách tới tâm ảnh gần nhất
    d2 = khoảng cách tới tâm ảnh gần nhì
    t  = (d2 - d1) / DAI          # 0 ở đúng biên, 1 khi đã sâu trong vùng
    giá trị = ảnh1 * (0,5 + 0,5·t) + ảnh2 * (0,5 - 0,5·t)

Ở đúng biên (d1 = d2) thì trộn 50/50; đi sâu vào trong DAI mét thì về hẳn ảnh 1.
Ngoài dải đó không trộn, nên giữ được gần hết tốc độ của bản gốc.

ĐÁNH ĐỔI phải nói rõ: trong dải biên, giá trị pixel là TRUNG BÌNH của hai lần đo
chứ không còn là một phép đo thật. Với ảnh nhiệt 8-bit đã qua gain riêng từng ảnh
thì điều này chấp nhận được (xem chú thích cân bằng sáng trong bản gốc), nhưng
nếu sau này chuyển sang dùng dữ liệu 16-bit thật thì phải cân nhắc lại.

    py -3.13 ma/ghep_ortho_pha_tron.py --dai 3
    py -3.13 ma/ghep_ortho_pha_tron.py --dai 0        # tắt trộn, để đối chứng
    py -3.13 ma/ghep_ortho_pha_tron.py --window 3300 1950 760 430   # thử một vùng
"""
import argparse
import csv
import json
import os
import re
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--step", type=float, default=3.0)
ap.add_argument("--tile", type=int, default=2048)
ap.add_argument("--dai", type=float, default=3.0,
                help="bề rộng dải pha trộn quanh biên Voronoi, tính bằng MÉT (0 = tắt)")
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_pha_tron.tif"))
ap.add_argument("--window", type=int, nargs=4, default=None,
                metavar=("COL", "ROW", "W", "H"),
                help="chỉ làm một vùng, toạ độ theo lưới ORTHO NHIỆT")
args = ap.parse_args()

t0 = time.time()

H = np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                            encoding="utf-8"))["H_thermal_to_rgb"])
Hinv = np.linalg.inv(H)

root = ET.parse(os.path.join(EXP, "cameras.xml")).getroot()
chunk = root.find(".//chunk")
s = chunk.find(".//sensor[@id='0']")
res = s.find("resolution")
cal = s.find("calibration[@class='adjusted']")
g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
IW, IH, F, CX, CY = int(res.get("width")), int(res.get("height")), g("f"), g("cx"), g("cy")

tr = chunk.find(".//component").find("transform")
R_ch = np.array(list(map(float, tr.find("rotation").text.split()))).reshape(3, 3)
T_ch = np.array(list(map(float, tr.find("translation").text.split())))
S_ch = float(tr.find("scale").text)

cams = {}
for cam in chunk.findall(".//camera"):
    t = cam.find("transform")
    if t is None:
        continue
    m = re.search(r"_(\d{4})_", cam.get("label") or "")
    if m:
        cams[m.group(1)] = np.array(list(map(float, t.text.split()))).reshape(4, 4)

bo = set()
for f in ("du_lieu/anh_tre_chup_full.json", "du_lieu/anh_rung.json"):
    p = os.path.join(BASE, f)
    if os.path.exists(p):
        bo |= {str(x) for x in json.load(open(p, encoding="utf-8")).get("anh_nen_loai", [])}
good = [k for k in sorted(cams) if k not in bo]

# bù lệch riêng từng ảnh — giữ nguyên như bản gốc
bu_anh = {}
p = os.path.join(BASE, "du_lieu/anh_tre_chup_full.json")
if os.path.exists(p):
    for x in json.load(open(p, encoding="utf-8")).get("chi_tiet", []):
        if x.get("dx") is not None and x.get("do_net", 0) >= 0.5:
            bu_anh[x["seq"]] = (float(x["dx"]), float(x["dy"]))

ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))

OT = ortho.transform * rasterio.Affine.scale(args.step, args.step)
OW, OH = int(ortho.width / args.step), int(ortho.height / args.step)
mdeg = 111320 * np.cos(np.radians(11.424))
GSD = abs(OT.a) * mdeg
print(f"[LƯỚI] {OW} x {OH} px, GSD {GSD*100:.2f} cm/px")
print(f"[TRỘN] dải {args.dai:.1f} m quanh biên Voronoi"
      if args.dai > 0 else "[TRỘN] TẮT — giống bản gốc")

to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)

rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

lab, nad, Minv = [], [], []
for k in good:
    if k not in rows:
        continue
    M = cams[k]
    C = S_ch * (R_ch @ M[:3, 3]) + T_ch
    lon, lat, alt = to_wgs.transform(*C)
    up = np.array([np.cos(np.radians(lat)) * np.cos(np.radians(lon)),
                   np.cos(np.radians(lat)) * np.sin(np.radians(lon)),
                   np.sin(np.radians(lat))])
    d = R_ch @ (M[:3, :3] @ np.array([-CX / F, -CY / F, 1.0]))
    d /= np.linalg.norm(d)
    tt = (alt - zmed) / max(1e-6, -(d @ up))
    glon, glat, _ = to_wgs.transform(*(C + tt * d))
    lab.append(k); nad.append((glon, glat)); Minv.append(np.linalg.inv(M))
nad = np.array(nad); Minv = np.array(Minv)
print(f"[TÂM]  {len(lab)} ảnh")

from scipy.spatial import cKDTree
tree = cKDTree(np.c_[nad[:, 0] * mdeg, nad[:, 1] * 110570])

# cân bằng sáng — giữ nguyên như bản gốc
sang = {}
for k in lab:
    im = cv2.imread(rows[k]["path_thermal"], cv2.IMREAD_GRAYSCALE)
    if im is None:
        continue
    co = im[im > 0]
    if co.size < 100:
        continue
    p25, p50, p75 = np.percentile(co, [25, 50, 75])
    sang[k] = (float(p50), max(float(p75 - p25), 1.0))
M_REF = float(np.median([v[0] for v in sang.values()]))
S_REF = float(np.median([v[1] for v in sang.values()]))
print(f"[SÁNG] cân bằng {len(sang)} ảnh về mốc {M_REF:.0f}")

cache = {}


def thermal(i):
    k = lab[i]
    if k not in cache:
        if len(cache) > 24:
            cache.pop(next(iter(cache)))
        im = cv2.imread(rows[k]["path_thermal"], cv2.IMREAD_GRAYSCALE).astype(np.float32)
        if k in sang:
            m_, s_ = sang[k]
            im = np.clip((im - m_) * (S_REF / s_) + M_REF, 1, 255)
        cache[k] = im
    return cache[k]


def lay_mau(i, sl, P4):
    """Lấy giá trị nhiệt của ảnh thứ i tại các ô sl. Trả (idx, giá trị)."""
    Pc = Minv[i] @ P4[:, sl]
    z = Pc[2]
    m = z > 0
    if not m.any():
        return None, None
    u = F * Pc[0] / z + IW / 2 + CX
    v = F * Pc[1] / z + IH / 2 + CY
    m &= (u >= 0) & (u < IW) & (v >= 0) & (v < IH)
    if not m.any():
        return None, None
    q = Hinv @ np.vstack([u[m], v[m], np.ones(m.sum())])
    tu, tv = q[0] / q[2], q[1] / q[2]
    b = bu_anh.get(lab[i])
    if b is not None:
        tu, tv = tu + b[0], tv + b[1]
    T = thermal(i)
    ok = (tu >= 0) & (tu < T.shape[1] - 1) & (tv >= 0) & (tv < T.shape[0] - 1)
    if not ok.any():
        return None, None
    idx = sl[m][ok]
    xu, yv = tu[ok], tv[ok]
    x0 = xu.astype(np.int32); y0 = yv.astype(np.int32)
    fx = (xu - x0).astype(np.float32); fy = (yv - y0).astype(np.float32)
    val = (T[y0, x0] * (1 - fx) * (1 - fy) + T[y0, x0 + 1] * fx * (1 - fy)
           + T[y0 + 1, x0] * (1 - fx) * fy + T[y0 + 1, x0 + 1] * fx * fy)
    return idx, val


if args.window:
    C0, R0, WW, HH = args.window
else:
    C0, R0, WW, HH = 0, 0, OW, OH
WT = OT * rasterio.Affine.translation(C0, R0)

prof = dict(driver="GTiff", height=HH, width=WW, count=1, dtype="uint8",
            crs=ortho.crs, transform=WT, compress="deflate", nodata=0)
filled = total = 0
n_tron = 0

with rasterio.open(args.out, "w", **prof) as dst:
    for ty in range(0, HH, args.tile):
        for tx in range(0, WW, args.tile):
            th_ = min(args.tile, HH - ty)
            tw_ = min(args.tile, WW - tx)
            cc, rr = np.meshgrid(np.arange(C0 + tx, C0 + tx + tw_) + .5,
                                 np.arange(R0 + ty, R0 + ty + th_) + .5)
            LON = OT.c + OT.a * cc
            LAT = OT.f + OT.e * rr

            dc = np.clip(((LON - dsm.transform.c) / dsm.transform.a).astype(np.int32),
                         0, dsm.width - 1)
            dr = np.clip(((LAT - dsm.transform.f) / dsm.transform.e).astype(np.int32),
                         0, dsm.height - 1)
            Z = DSM[dr, dc].astype(np.float64)
            Z[(Z == dsm.nodata) | ~np.isfinite(Z)] = zmed

            X, Y, Zc = to_ecef.transform(LON.ravel(), LAT.ravel(), Z.ravel())
            P4 = np.vstack([R_ch.T @ (np.stack([X, Y, Zc]) - T_ch[:, None]) / S_ch,
                            np.ones(X.size)])

            # hai ảnh gần nhất + khoảng cách tới tâm chúng
            Q = np.c_[LON.ravel() * mdeg, LAT.ravel() * 110570]
            dist, nn = tree.query(Q, k=min(2, len(lab)))
            if nn.ndim == 1:
                nn = nn[:, None]; dist = dist[:, None]

            out = np.zeros(X.size, np.float32)
            wsum = np.zeros(X.size, np.float32)

            # trọng số ảnh gần nhì: chỉ khác 0 trong dải biên
            if args.dai > 0 and nn.shape[1] > 1:
                t = np.clip((dist[:, 1] - dist[:, 0]) / args.dai, 0, 1)
                w1 = 0.5 + 0.5 * t          # 0,5 ở đúng biên -> 1 khi sâu trong vùng
                w2 = 1.0 - w1
                n_tron += int((w2 > 0.02).sum())
            else:
                w1 = np.ones(X.size, np.float32)
                w2 = np.zeros(X.size, np.float32)

            for kk in range(nn.shape[1]):
                w = w1 if kk == 0 else w2
                co_w = np.where(w > 0.02)[0]
                if co_w.size == 0:
                    continue
                ci = nn[co_w, kk]
                order = np.argsort(ci, kind="stable")
                co_w = co_w[order]; ci = ci[order]
                bounds = np.searchsorted(ci, np.arange(len(lab) + 1))
                for i in range(len(lab)):
                    sl = co_w[bounds[i]:bounds[i + 1]]
                    if sl.size == 0:
                        continue
                    idx, val = lay_mau(i, sl, P4)
                    if idx is None:
                        continue
                    out[idx] += val * w[idx]
                    wsum[idx] += w[idx]

            done = wsum > 0.02
            out[done] /= wsum[done]
            dst.write((np.maximum(out.reshape(th_, tw_), 1).astype(np.uint8)
                       * done.reshape(th_, tw_)), 1,
                      window=rasterio.windows.Window(tx, ty, tw_, th_))
            filled += done.sum(); total += done.size
            print(f"   ô ({tx:5d},{ty:5d})  phủ {100*done.mean():5.1f}%   "
                  f"tổng {100*filled/total:5.1f}%   {time.time()-t0:6.0f}s")

print(f"\n[XONG] phủ {100*filled/total:.1f}%, "
      f"{100*n_tron/max(total,1):.1f}% ô nằm trong dải pha trộn, {time.time()-t0:.0f}s")
print(f"-> {args.out}  ({os.path.getsize(args.out)/1e6:.1f} MB)")
