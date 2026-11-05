#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Đo lệch của ortho nhiệt so với ortho MÀU, quy về hiệu chỉnh cho TỪNG ẢNH.

VÌ SAO CẦN: nan_ortho_theo_rgb.py nắn ortho ĐÃ GHÉP nên ảnh bị nội suy hai lần
(ghép một lần, nắn một lần) — đo được mất 22% độ nét, và mọi cấu hình tham số đều
mất đúng chừng đó, chứng tỏ nguyên nhân là ở số lần lấy mẫu chứ không phải tham số.

Script này lấy cùng phép đo đó nhưng KHÔNG nắn ảnh. Nó quy trường dịch chuyển về
một cặp (du, dv) cho mỗi ảnh, ghi ra JSON để ghep_ortho_nhiet.py cộng vào lúc lấy
mẫu. Kết quả: chỉ nội suy MỘT lần.

    py -3.13 ma/bu_theo_rgb.py
    py -3.13 ma/ghep_ortho_nhiet.py --bu-rgb bu_theo_rgb.json --out ortho_nhiet_bu_rgb.tif

BA CHỖ DỄ SAI, đã xử lý:

  1. ĐƠN VỊ. Trường dịch chuyển đo bằng pixel LƯỚI ORTHO; còn bu_anh trong
     ghep_ortho_nhiet.py tính bằng pixel ẢNH NHIỆT. Hai lưới xấp xỉ cùng GSD
     (~2,87 cm) nhưng KHÁC HƯỚNG — trục ảnh nhiệt xoay theo hướng bay. Phải nhân
     ma trận Jacobi của phép chiếu, không được cộng thẳng.

  2. DẤU. Cộng vào (tu, tv) là dời điểm LẤY MẪU trong ảnh nguồn, nên nội dung ở
     ortho dịch NGƯỢC lại. Suy ra: delta = -J @ d_ortho. Dấu này được kiểm bằng
     thực nghiệm ở cuối (chạy ghép rồi đo lại) — nếu sai dấu thì lệch tăng gấp
     đôi chứ không giảm.

  3. ẢNH ÍT DỮ LIỆU. Ảnh nào có dưới --toi-thieu ô khớp được thì để bù = 0, giữ
     nguyên như cũ. Thà không sửa còn hơn sửa theo một phép đo không đáng tin.
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
from rasterio.windows import from_bounds

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--nguon", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/bu_theo_rgb.json"))
ap.add_argument("--o", type=int, default=128)
ap.add_argument("--buoc", type=int, default=64)
ap.add_argument("--tin", type=float, default=0.03)
ap.add_argument("--toi-da", type=float, default=25.0, dest="toi_da")
ap.add_argument("--toi-thieu", type=int, default=3, dest="toi_thieu",
                help="số ô khớp tối thiểu thì mới tin, dưới mức này để bù = 0")
ap.add_argument("--tran", type=float, default=8.0,
                help="chặn biên độ bù (px ảnh nhiệt), tránh một ô lạc kéo cả ảnh đi")
args = ap.parse_args()

t0 = time.time()

# ------------------------------------------------------------------ 1. dữ liệu
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
rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}
good = [k for k in sorted(cams) if k not in bo and k in rows]

nhiet = rasterio.open(args.nguon)
mau = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))
to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
mdeg = 111320 * np.cos(np.radians(11.424))

OT = nhiet.transform
WW, HH = nhiet.width, nhiet.height
GSD = abs(OT.a) * mdeg * 100
print(f"[VÙNG] {WW} x {HH}, GSD {GSD:.2f} cm/px")

# --------------------------------------------------- 2. tâm chụp dưới đất
lab, nad, Minv = [], [], []
for k in good:
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
from scipy.spatial import cKDTree
tree = cKDTree(np.c_[nad[:, 0] * mdeg, nad[:, 1] * 110570])
print(f"[TÂM]  {len(lab)} ảnh")

# --------------------------------------------------- 3. trường dịch chuyển
TH = nhiet.read(1)
lo0, la0 = OT * (0, 0)
lo1, la1 = OT * (WW, HH)
w = from_bounds(min(lo0, lo1), min(la0, la1), max(lo0, lo1), max(la0, la1), mau.transform)
RGB = mau.read([1, 2, 3], window=w, out_shape=(3, HH, WW),
               resampling=rasterio.enums.Resampling.average)
G = cv2.cvtColor(np.ascontiguousarray(np.moveaxis(RGB, 0, -1)[:, :, ::-1]), cv2.COLOR_BGR2GRAY)


def mat_na(v, dao):
    b = cv2.GaussianBlur(v, (0, 0), 2.0)
    hop_le = v > 0
    co = b[hop_le]
    if co.size < 100:
        return np.zeros_like(v, np.float32)
    t, _ = cv2.threshold(co.astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = ((b < t) if dao else (b > t)).astype(np.uint8) * 255
    m[~hop_le] = 0
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    return m.astype(np.float32) / 255.0


MT, MG = mat_na(TH, False), mat_na(G, True)
print(f"[MẶT NẠ] {100*MT.mean():.1f}% (nhiệt) · {100*MG.mean():.1f}% (màu)")

O, B = args.o, args.buoc
han = cv2.createHanningWindow((O, O), cv2.CV_32F)
pts, dxy = [], []
for y0 in range(0, HH - O + 1, B):
    for x0 in range(0, WW - O + 1, B):
        a = MT[y0:y0 + O, x0:x0 + O]
        b = MG[y0:y0 + O, x0:x0 + O]
        if not (0.08 < a.mean() < 0.95 and 0.08 < b.mean() < 0.95):
            continue
        (dx, dy), r = cv2.phaseCorrelate(a * han, b * han)
        if r < args.tin or np.hypot(dx, dy) > args.toi_da:
            continue
        pts.append((x0 + O / 2, y0 + O / 2))
        dxy.append((dx, dy))
pts = np.array(pts); dxy = np.array(dxy)
print(f"[KHỚP] {len(pts)} ô, dịch trung vị "
      f"{np.median(np.hypot(dxy[:,0], dxy[:,1])):.2f} px = "
      f"{np.median(np.hypot(dxy[:,0], dxy[:,1]))*GSD:.1f} cm, {time.time()-t0:.0f}s")

# --------------------------------------------------- 4. gán ô cho ảnh (Voronoi)
LONc = OT.c + OT.a * pts[:, 0]
LATc = OT.f + OT.e * pts[:, 1]
_, chu = tree.query(np.c_[LONc * mdeg, LATc * 110570], k=1)


def ortho_to_thermal(lon, lat, i):
    """(lon,lat) -> pixel ảnh nhiệt của ảnh thứ i. None nếu không nhìn thấy."""
    r, c = dsm.index(lon, lat)
    z = zmed
    if 0 <= r < DSM.shape[0] and 0 <= c < DSM.shape[1]:
        zz = float(DSM[r, c])
        if zz != dsm.nodata and np.isfinite(zz):
            z = zz
    X, Y, Z = to_ecef.transform(lon, lat, z)
    Pl = R_ch.T @ (np.array([X, Y, Z]) - T_ch) / S_ch
    Pc = Minv[i][:3, :3] @ Pl + Minv[i][:3, 3]
    if Pc[2] <= 1e-6:
        return None
    u = F * Pc[0] / Pc[2] + IW / 2 + CX
    v = F * Pc[1] / Pc[2] + IH / 2 + CY
    q = Hinv @ np.array([u, v, 1.0])
    return np.array([q[0] / q[2], q[1] / q[2]])


# --------------------------------------------------- 5. quy về bù từng ảnh
bu = {}
n_du, n_thieu = 0, 0
for i in range(len(lab)):
    sel = np.where(chu == i)[0]
    if sel.size < args.toi_thieu:
        n_thieu += 1
        continue
    d_ortho = np.median(dxy[sel], axis=0)          # px lưới ortho (cột, hàng)

    # Jacobi của phép chiếu tại tâm chụp: đổi 1 px ortho -> bao nhiêu px ảnh nhiệt
    c0 = np.median(pts[sel, 0]); r0 = np.median(pts[sel, 1])
    P0 = ortho_to_thermal(OT.c + OT.a * c0, OT.f + OT.e * r0, i)
    Pc_ = ortho_to_thermal(OT.c + OT.a * (c0 + 1), OT.f + OT.e * r0, i)
    Pr_ = ortho_to_thermal(OT.c + OT.a * c0, OT.f + OT.e * (r0 + 1), i)
    if P0 is None or Pc_ is None or Pr_ is None:
        n_thieu += 1
        continue
    J = np.column_stack([Pc_ - P0, Pr_ - P0])      # 2x2

    # DẤU TRỪ: cộng vào (tu,tv) là dời điểm lấy mẫu, nội dung dịch ngược lại.
    delta = -J @ d_ortho
    n = np.hypot(*delta)
    if n > args.tran:
        delta = delta / n * args.tran
    bu[lab[i]] = [float(delta[0]), float(delta[1])]
    n_du += 1

v = np.array([np.hypot(*b) for b in bu.values()]) if bu else np.array([0.0])
print(f"[BÙ]   {n_du} ảnh có bù, {n_thieu} ảnh để 0 (thiếu dữ liệu)")
print(f"       biên độ: trung vị {np.median(v):.2f} px = {np.median(v)*GSD:.1f} cm, "
      f"lớn nhất {v.max():.2f} px")

json.dump({"ghi_chu": "bù thêm theo ortho màu, đơn vị PIXEL ẢNH NHIỆT, "
                      "cộng vào bu_anh của ghep_ortho_nhiet.py",
           "so_anh": n_du, "bu": bu},
          open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n-> {args.out}")
print("Chạy tiếp:  py -3.13 ma/ghep_ortho_nhiet.py --bu-rgb bu_theo_rgb.json "
      "--out ortho_nhiet_bu_rgb.tif")
