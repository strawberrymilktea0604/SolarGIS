#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minh hoạ VÌ SAO không dán xuôi — chạy thật trên dữ liệu thật, xuất ảnh so sánh.

Dựng CÙNG một vùng ortho bằng HAI cách, rồi đặt cạnh nhau:

  TRÁI  — DÁN XUÔI: lấy từng ảnh nhiệt, warp lên lưới ortho rồi dán chồng lên.
          Đây là cách trực giác ai cũng nghĩ tới đầu tiên.
  PHẢI  — ĐI NGƯỢC: duyệt từng ô lưới ortho, đi tìm giá trị của nó.
          Đây là cách ghep_ortho_nhiet.py đang làm.

Cả hai dùng CHUNG: cameras.xml, dsm.tif, thermal_to_rgb.json, cùng tập ảnh, cùng
lưới đầu ra. Khác biệt duy nhất là CHIỀU CHẠY. Nên mọi khác biệt nhìn thấy trên
ảnh đều do chiều chạy sinh ra, không phải do tham số.

    py -3.13 ma/minh_hoa_dan_xuoi.py                    # vùng mặc định
    py -3.13 ma/minh_hoa_dan_xuoi.py --window 21000 6800 2600 2000
"""
import argparse
import csv
import json
import os
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--window", type=int, nargs=4, default=[21000, 6800, 2600, 2000],
                metavar=("COL", "ROW", "W", "H"))
ap.add_argument("--step", type=float, default=3.0)
ap.add_argument("--ra", default=os.path.join(BASE, "ket_qua/kiem_tra_warp", "so_dan_xuoi.jpg"))
args = ap.parse_args()

t0 = time.time()
os.makedirs(os.path.dirname(args.ra), exist_ok=True)

# ---------------------------------------------------------------- dữ liệu chung
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
    import re
    m = re.search(r"_(\d{4})_", cam.get("label") or "")
    if m:
        cams[m.group(1)] = np.array(list(map(float, t.text.split()))).reshape(4, 4)

ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))

c0, r0, ww, hh = args.window
base_tf = rasterio.windows.transform(rasterio.windows.Window(c0, r0, ww, hh), ortho.transform)
OT = base_tf * rasterio.Affine.scale(args.step, args.step)
OW, OH = int(ww / args.step), int(hh / args.step)
mdeg = 111320 * np.cos(np.radians(11.424))
print(f"[LƯỚI] {OW} x {OH} px, GSD {abs(OT.a)*mdeg*100:.2f} cm/px")

to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)

rows_csv = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

# tâm chụp dưới đất -> chọn ảnh phủ vùng này
lab, nad, Cecef, Minv = [], [], [], []
for k, M in cams.items():
    if k not in rows_csv:
        continue
    C = S_ch * (R_ch @ M[:3, 3]) + T_ch
    lon, lat, alt = to_wgs.transform(*C)
    up = np.array([np.cos(np.radians(lat)) * np.cos(np.radians(lon)),
                   np.cos(np.radians(lat)) * np.sin(np.radians(lon)),
                   np.sin(np.radians(lat))])
    d = R_ch @ (M[:3, :3] @ np.array([-CX / F, -CY / F, 1.0]))
    d /= np.linalg.norm(d)
    t = (alt - zmed) / max(1e-6, -(d @ up))
    glon, glat, _ = to_wgs.transform(*(C + t * d))
    lab.append(k); nad.append((glon, glat)); Cecef.append(C); Minv.append(np.linalg.inv(M))
nad = np.array(nad); Cecef = np.array(Cecef); Minv = np.array(Minv)

lo0, la0 = OT * (0, 0)
lo1, la1 = OT * (OW, OH)
lo_lo, lo_hi = min(lo0, lo1), max(lo0, lo1)
la_lo, la_hi = min(la0, la1), max(la0, la1)
M_ = 0.0012
sel = [i for i in range(len(lab))
       if lo_lo - M_ < nad[i, 0] < lo_hi + M_ and la_lo - M_ < nad[i, 1] < la_hi + M_]
print(f"[ẢNH]  {len(sel)} ảnh nhiệt phủ vùng này")


def doc_nhiet(k):
    im = cv2.imread(rows_csv[k]["path_thermal"], cv2.IMREAD_GRAYSCALE)
    return None if im is None else im.astype(np.float32)


# ══════════════════════════════════════════════ CÁCH 1 — DÁN XUÔI
# Với mỗi ảnh: 4 góc ảnh nhiệt -> qua H -> pixel RGB -> tia -> cắt mặt phẳng z=zmed
# -> lon/lat -> ô lưới ortho. Có 4 cặp điểm thì tìm được phép biến đổi phối cảnh,
# warp cả ảnh lên lưới rồi dán. Ảnh sau đè ảnh trước.
xuoi = np.zeros((OH, OW), np.float32)
dem_xuoi = np.zeros((OH, OW), np.uint8)

for i in sel:
    k = lab[i]
    im = doc_nhiet(k)
    if im is None:
        continue
    th, tw = im.shape
    goc_th = np.array([[0, 0], [tw, 0], [tw, th], [0, th]], np.float64)

    # nhiệt -> RGB
    p = np.c_[goc_th, np.ones(4)] @ H.T
    rgb_uv = p[:, :2] / p[:, 2:3]

    # RGB -> tia -> mặt đất
    x = (rgb_uv[:, 0] - (IW / 2 + CX)) / F
    y = (rgb_uv[:, 1] - (IH / 2 + CY)) / F
    dcam = np.c_[x, y, np.ones(4)]
    Mk = np.linalg.inv(Minv[i])
    dw = (R_ch @ (Mk[:3, :3] @ dcam.T)).T
    dw /= np.linalg.norm(dw, axis=1, keepdims=True)
    C = Cecef[i]
    lonC, latC, altC = to_wgs.transform(*C)
    up = np.array([np.cos(np.radians(latC)) * np.cos(np.radians(lonC)),
                   np.cos(np.radians(latC)) * np.sin(np.radians(lonC)),
                   np.sin(np.radians(latC))])
    tt = (altC - zmed) / np.maximum(1e-6, -(dw @ up))
    P = C + dw * tt[:, None]
    lons, lats, _ = to_wgs.transform(P[:, 0], P[:, 1], P[:, 2])

    inv = ~OT
    cols, rows_ = [], []
    for lo, la in zip(lons, lats):
        cc, rr = inv * (lo, la)
        cols.append(cc); rows_.append(rr)
    dst = np.array(list(zip(cols, rows_)), np.float32)

    if not np.isfinite(dst).all():
        continue
    Hw = cv2.getPerspectiveTransform(goc_th.astype(np.float32), dst)
    w1 = cv2.warpPerspective(im, Hw, (OW, OH), flags=cv2.INTER_LINEAR,
                             borderValue=0)
    mk = (w1 > 0)
    xuoi[mk] = w1[mk]          # ảnh sau ĐÈ ảnh trước — đúng tinh thần "dán"
    dem_xuoi[mk] += 1

print(f"[XUÔI] xong, {time.time()-t0:.0f}s")

# ══════════════════════════════════════════════ CÁCH 2 — ĐI NGƯỢC
# Đúng chuỗi của ghep_ortho_nhiet.py, rút gọn: mỗi ô lưới lấy từ ảnh có tâm gần nhất.
gg, rr_ = np.meshgrid(np.arange(OW), np.arange(OH))
lonG, latG = OT * (gg.ravel() + 0.5, rr_.ravel() + 0.5)
lonG = np.asarray(lonG).reshape(-1); latG = np.asarray(latG).reshape(-1)

rowd, cold = ~dsm.transform * (lonG, latG)
rowd = np.clip(np.asarray(cold).astype(int), 0, DSM.shape[0] - 1)
cold = np.clip(np.asarray(rowd).astype(int), 0, DSM.shape[1] - 1)
zz = DSM[rowd, cold].astype(np.float64)
zz[zz == dsm.nodata] = zmed

X, Y, Z = to_ecef.transform(lonG, latG, zz)
Pw = np.c_[X, Y, Z]

d2 = ((nad[sel, 0][None, :] - lonG[:, None]) * mdeg) ** 2 + \
     ((nad[sel, 1][None, :] - latG[:, None]) * 110570) ** 2
gan = np.array(sel)[np.argmin(d2, axis=1)]

nguoc = np.zeros(OW * OH, np.float32)
for i in np.unique(gan):
    k = lab[i]
    im = doc_nhiet(k)
    if im is None:
        continue
    th, tw = im.shape
    m = (gan == i)
    Pl = (Pw[m] - T_ch) / S_ch
    Pl = (np.linalg.inv(R_ch) @ Pl.T).T
    Pc = (Minv[i][:3, :3] @ Pl.T).T + Minv[i][:3, 3]
    ok = Pc[:, 2] > 1e-6
    u = np.full(len(Pc), -1.0); v = np.full(len(Pc), -1.0)
    u[ok] = F * Pc[ok, 0] / Pc[ok, 2] + IW / 2 + CX
    v[ok] = F * Pc[ok, 1] / Pc[ok, 2] + IH / 2 + CY
    q = np.c_[u, v, np.ones(len(u))] @ Hinv.T
    tu = q[:, 0] / q[:, 2]; tv = q[:, 1] / q[:, 2]
    good = ok & (tu >= 0) & (tu < tw - 1) & (tv >= 0) & (tv < th - 1)
    idx = np.where(m)[0][good]
    if idx.size:
        # cv2.remap giới hạn cạnh < 32767 -> chia lô
        gu = tu[good].astype(np.float32); gv = tv[good].astype(np.float32)
        LO = 30000
        for a in range(0, idx.size, LO):
            b = min(a + LO, idx.size)
            nguoc[idx[a:b]] = cv2.remap(im, gu[a:b].reshape(1, -1),
                                        gv[a:b].reshape(1, -1),
                                        cv2.INTER_LINEAR)[0]
nguoc = nguoc.reshape(OH, OW)
print(f"[NGƯỢC] xong, {time.time()-t0:.0f}s")

# ══════════════════════════════════════════════ đo và vẽ
ho_xuoi = int((xuoi == 0).sum()); ho_nguoc = int((nguoc == 0).sum())
tong = OW * OH
chong = int((dem_xuoi > 1).sum())
print(f"\n[ĐO]  dán xuôi : {ho_xuoi:>7} ô trống ({100*ho_xuoi/tong:5.2f}%), "
      f"{chong} ô bị nhiều ảnh đè lên nhau ({100*chong/tong:.1f}%)")
print(f"      đi ngược : {ho_nguoc:>7} ô trống ({100*ho_nguoc/tong:5.2f}%)")


def to_mau(a):
    v = a.copy()
    co = v[v > 0]
    if co.size:
        lo, hi = np.percentile(co, [1, 99])
        v = np.clip((v - lo) / max(hi - lo, 1) * 255, 0, 255)
    c = cv2.applyColorMap(v.astype(np.uint8), cv2.COLORMAP_INFERNO)
    c[a == 0] = (255, 255, 255)      # ô trống tô TRẮNG cho nổi
    return c


A, B = to_mau(xuoi), to_mau(nguoc)
GAP, TOP = 26, 78
cv = np.full((TOP + OH + 96, OW * 2 + GAP, 3), 255, np.uint8)
cv[TOP:TOP + OH, :OW] = A
cv[TOP:TOP + OH, OW + GAP:] = B

f1, f2 = cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX
cv2.putText(cv, "DAN XUOI - warp tung anh roi dan chong len", (8, 30), f2, 0.72, (30, 30, 190), 2)
cv2.putText(cv, f"{100*ho_xuoi/tong:.1f}% o TRANG = lo hong  |  {100*chong/tong:.0f}% o bi nhieu anh de nhau",
            (8, 58), f1, 0.56, (30, 30, 190), 1)
cv2.putText(cv, "DI NGUOC - moi o tu di tim gia tri (code dang dung)", (OW + GAP + 8, 30), f2, 0.72, (30, 130, 30), 2)
cv2.putText(cv, f"{100*ho_nguoc/tong:.1f}% o trang  |  moi o dien dung MOT lan",
            (OW + GAP + 8, 58), f1, 0.56, (30, 130, 30), 1)
cv2.rectangle(cv, (0, TOP), (OW - 1, TOP + OH - 1), (30, 30, 190), 2)
cv2.rectangle(cv, (OW + GAP, TOP), (OW * 2 + GAP - 1, TOP + OH - 1), (30, 130, 30), 2)

y = TOP + OH + 30
cv2.putText(cv, "Cung du lieu, cung luoi, cung tap anh - khac duy nhat CHIEU CHAY.",
            (8, y), f1, 0.6, (40, 40, 40), 1)
cv2.putText(cv, "Dan xuoi: anh nhiet KHONG phu kin luoi (bien anh, khe giua cac tuyen bay) va cho chong nhau anh sau de anh truoc.",
            (8, y + 26), f1, 0.54, (90, 90, 90), 1)
cv2.putText(cv, "Di nguoc: xuat phat tu O CAN DIEN nen khong the bo sot o nao.",
            (8, y + 50), f1, 0.54, (90, 90, 90), 1)

cv2.imwrite(args.ra, cv, [cv2.IMWRITE_JPEG_QUALITY, 93])
print(f"\n-> {args.ra}  ({os.path.getsize(args.ra)/1024:.0f} KB), {time.time()-t0:.0f}s")
