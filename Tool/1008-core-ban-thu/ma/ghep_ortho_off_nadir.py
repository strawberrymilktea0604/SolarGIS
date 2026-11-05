#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ghép ortho nhiệt, chọn ảnh theo GÓC OFF-NADIR thay vì khoảng cách tâm chụp.

VÌ SAO THỬ: ghep_ortho_nhiet.py chọn ảnh có tâm chụp GẦN NHẤT (cây KD trên toạ độ
tâm). Cách đó nhanh nhưng không đúng tiêu chí: cái quyết định sai số đặt chỗ là
GÓC NHÌN, không phải khoảng cách. Tấm pin cao hơn mặt đất 1–2 m, nên xê dịch do
độ cao (relief displacement) tỉ lệ với tan(theta) — theta là góc off-nadir.

Hai ảnh kề nhau cùng nhìn thẳng góc thì đặt tấm pin vào gần cùng một chỗ, biên
Voronoi giữa chúng đỡ gãy. Đây cũng là tiêu chí Metashape dùng khi ghép mosaic
(xem chú thích trong camera_select.py:10-12).

KHÁC BIỆT DUY NHẤT so với ghep_ortho_nhiet.py là cách xếp hạng ảnh cho mỗi ô.
Mọi thứ khác giữ nguyên: cùng H, cùng bộ lọc ảnh, cùng cân bằng sáng, cùng bù
lệch từng ảnh, cùng lưới. Nên mọi khác biệt trên ảnh đều do tiêu chí chọn ảnh.

    py -3.13 ma/ghep_ortho_off_nadir.py --window 3300 1950 760 430   # thử một vùng
    py -3.13 ma/ghep_ortho_off_nadir.py                              # toàn nhà máy
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
ap.add_argument("--tile", type=int, default=1024)
ap.add_argument("--k", type=int, default=8,
                help="xét K ảnh gần nhất rồi chọn ảnh off-nadir nhỏ nhất trong đó")
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_off_nadir.tif"))
ap.add_argument("--window", type=int, nargs=4, default=None,
                metavar=("COL", "ROW", "W", "H"))
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
print(f"[LƯỚI] {OW} x {OH} px, GSD {abs(OT.a)*mdeg*100:.2f} cm/px")
print(f"[CHỌN] off-nadir nhỏ nhất trong {args.k} ảnh gần nhất")

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


if args.window:
    C0, R0, WW, HH = args.window
else:
    C0, R0, WW, HH = 0, 0, OW, OH
WT = OT * rasterio.Affine.translation(C0, R0)
prof = dict(driver="GTiff", height=HH, width=WW, count=1, dtype="uint8",
            crs=ortho.crs, transform=WT, compress="deflate", nodata=0)

filled = total = 0
theta_ke = []

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

            N = X.size
            KK = min(args.k, len(lab))
            _, nn = tree.query(np.c_[LON.ravel() * mdeg, LAT.ravel() * 110570], k=KK)
            if nn.ndim == 1:
                nn = nn[:, None]

            # ---- BƯỚC KHÁC BẢN GỐC: tính off-nadir cho TỪNG ứng viên, chọn nhỏ nhất
            # theta = arctan(hypot(x,y)) với x,y là toạ độ chuẩn hoá trong hệ camera
            # (đúng công thức camera_select.py:165). Ảnh nào không nhìn thấy ô đó
            # thì gán theta = vô cực để loại.
            best_t = np.full(N, np.inf, np.float32)
            best_i = np.full(N, -1, np.int32)
            for kk in range(KK):
                ci = nn[:, kk]
                for i in np.unique(ci):
                    sl = np.where(ci == i)[0]
                    Pc = Minv[i] @ P4[:, sl]
                    z = Pc[2]
                    m = z > 0
                    if not m.any():
                        continue
                    x = Pc[0] / z; y = Pc[1] / z
                    u = F * x + IW / 2 + CX
                    v = F * y + IH / 2 + CY
                    m &= (u >= 0) & (u < IW) & (v >= 0) & (v < IH)
                    if not m.any():
                        continue
                    th = np.degrees(np.arctan(np.hypot(x, y)))
                    idx = sl[m]
                    tot = th[m].astype(np.float32)
                    ok = tot < best_t[idx]
                    best_t[idx[ok]] = tot[ok]
                    best_i[idx[ok]] = i

            co = best_i >= 0
            if co.any():
                theta_ke.append(best_t[co])

            out = np.zeros(N, np.float32)
            done = np.zeros(N, bool)
            for i in np.unique(best_i[co]):
                sl = np.where(best_i == i)[0]
                Pc = Minv[i] @ P4[:, sl]
                z = Pc[2]
                m = z > 0
                u = F * Pc[0] / z + IW / 2 + CX
                v = F * Pc[1] / z + IH / 2 + CY
                m &= (u >= 0) & (u < IW) & (v >= 0) & (v < IH)
                if not m.any():
                    continue
                q = Hinv @ np.vstack([u[m], v[m], np.ones(m.sum())])
                tu, tv = q[0] / q[2], q[1] / q[2]
                b = bu_anh.get(lab[i])
                if b is not None:
                    tu, tv = tu + b[0], tv + b[1]
                T = thermal(i)
                ok = (tu >= 0) & (tu < T.shape[1] - 1) & (tv >= 0) & (tv < T.shape[0] - 1)
                if not ok.any():
                    continue
                idx = sl[m][ok]
                xu, yv = tu[ok], tv[ok]
                x0 = xu.astype(np.int32); y0 = yv.astype(np.int32)
                fx = (xu - x0).astype(np.float32); fy = (yv - y0).astype(np.float32)
                out[idx] = (T[y0, x0] * (1 - fx) * (1 - fy) + T[y0, x0 + 1] * fx * (1 - fy)
                            + T[y0 + 1, x0] * (1 - fx) * fy + T[y0 + 1, x0 + 1] * fx * fy)
                done[idx] = True

            dst.write((np.maximum(out.reshape(th_, tw_), 1).astype(np.uint8)
                       * done.reshape(th_, tw_)), 1,
                      window=rasterio.windows.Window(tx, ty, tw_, th_))
            filled += done.sum(); total += done.size
            print(f"   ô ({tx:5d},{ty:5d})  phủ {100*done.mean():5.1f}%   "
                  f"tổng {100*filled/total:5.1f}%   {time.time()-t0:6.0f}s")

tk = np.concatenate(theta_ke) if theta_ke else np.array([0.0])
print(f"\n[XONG] phủ {100*filled/total:.1f}%, {time.time()-t0:.0f}s")
print(f"[GÓC]  off-nadir đã dùng: trung vị {np.median(tk):.2f}° | "
      f"P90 {np.percentile(tk,90):.2f}° | max {tk.max():.2f}°")
print(f"-> {args.out}  ({os.path.getsize(args.out)/1e6:.1f} MB)")
