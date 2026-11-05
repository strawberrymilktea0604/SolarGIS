#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Do ortho nhiet khop ortho mau den dau — so nhieu ban dung khac nhau.

Cach do: lay N cua so ngau nhien khap nha may. Moi cua so, rut ban do VIEN cua
ca hai anh roi truot ban nhiet quanh vi tri goc tim cho khop nhat. Lech tim duoc
la sai so dat cho cua ortho nhiet tai vung do.

Vi sao khong vuong van de luoi tam pin tuan hoan (thu pham lam hong
hieu_chuan_tu_dong.py): ban kinh truot +-12 px = +-34 cm, hep hon nhieu so voi
nua buoc hang tam pin (~2 m), nen khong the nhay nham sang hang ke ben.

DUNG CUNG MOT BO CUA SO cho moi ban -> so theo cap, nhay hon nhieu so voi so
hai phan bo doc lap.

    python ma/do_khop_ortho.py
"""
import json
import os

import cv2
import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

BAN = [("ban goc", "ket_qua/ortho/ortho_nhiet_tu_lam.tif"),
       ("can sang", "ortho_nhiet_can_sang.tif"),
       ("can sang + bu tung anh", "ortho_nhiet_bu_anh.tif")]
O = 192          # canh cua so, px ortho nhiet (~5,5 m)
R = 12           # ban kinh truot, px (~34 cm)
N = 300
GSD_CM = 2.87

rng = np.random.default_rng(20260811)


def vien(img):
    """Ban do vien — dung dung cong thuc da kiem chung trong loc_anh_tre.py."""
    f = cv2.medianBlur(cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX,
                                     dtype=cv2.CV_8U), 5).astype(np.float32)
    f = f - cv2.GaussianBlur(f, (0, 0), 15)
    f = cv2.GaussianBlur(f, (0, 0), 1.2)
    g = np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3),
                 cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3))
    t = np.percentile(g, 80)
    return np.clip((g - t) / max(1e-6, g.max() - t), 0, 1).astype(np.float32)


mau_r = rasterio.open(os.path.join(EXP, "ortho.tif"))

# --- chon cua so tren ban dau tien, dung lai cho moi ban ---------------------
r0 = rasterio.open(BAN[0][1])
a0 = r0.read(1)
cua = []
while len(cua) < N:
    c = int(rng.integers(0, r0.width - O))
    r = int(rng.integers(0, r0.height - O))
    if (a0[r:r + O, c:c + O] > 0).mean() > 0.92:
        cua.append((c, r))
print("Chon %d cua so %dx%d px (~%.1f m), truot +-%d px (+-%.0f cm)"
      % (len(cua), O, O, O * GSD_CM / 100, R, R * GSD_CM))

# --- vien anh mau cho tung cua so, tinh mot lan ------------------------------
vien_mau = {}
for c, r in cua:
    b = rasterio.windows.bounds(Window(c, r, O, O), r0.transform)
    w = from_bounds(*b, transform=mau_r.transform)
    g = mau_r.read(1, window=w, out_shape=(O, O), boundless=True, fill_value=0)
    vien_mau[(c, r)] = vien(g.astype(np.uint8))
print("Xong viền ảnh màu")

ket = {}
for ten, f in BAN:
    if not os.path.exists(f):
        print("  thieu", f)
        continue
    src = rasterio.open(f)
    lech = []
    for c, r in cua:
        th = src.read(1, window=Window(c, r, O, O))
        if (th > 0).mean() < 0.92:
            continue
        vt = vien(th)
        vm = vien_mau[(c, r)]
        diem = np.full((2 * R + 1, 2 * R + 1), -1.0)
        for iy, dy in enumerate(range(-R, R + 1)):
            for ix, dx in enumerate(range(-R, R + 1)):
                M = np.float32([[1, 0, dx], [0, 1, dy]])
                diem[iy, ix] = float((cv2.warpAffine(vt, M, (O, O)) * vm).sum())
        iy, ix = np.unravel_index(np.argmax(diem), diem.shape)
        if iy in (0, 2 * R) or ix in (0, 2 * R):
            continue                      # cham mep vung truot, khong tin
        dy, dx = float(iy - R), float(ix - R)
        for tr, i0, i1 in ((0, iy, ix), (1, iy, ix)):
            pass
        y0, y1, y2 = diem[iy, ix - 1], diem[iy, ix], diem[iy, ix + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            dx += 0.5 * (y0 - y2) / den
        y0, y1, y2 = diem[iy - 1, ix], diem[iy, ix], diem[iy + 1, ix]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            dy += 0.5 * (y0 - y2) / den
        lech.append(np.hypot(dx, dy))
    v = np.array(lech)
    ket[ten] = v
    print("%-26s n=%3d | trung vi %5.2f px = %5.1f cm | p90 %5.2f px = %5.1f cm | max %5.1f cm"
          % (ten, v.size, np.median(v), np.median(v) * GSD_CM,
             np.percentile(v, 90), np.percentile(v, 90) * GSD_CM, v.max() * GSD_CM))

if len(ket) >= 2:
    a = ket[BAN[1][0]]
    b = ket[BAN[2][0]]
    n = min(a.size, b.size)
    print()
    print("So theo cap (%d cua so chung):" % n)
    print("   tot len : %d cua so" % int((b[:n] < a[:n]).sum()))
    print("   xau di  : %d cua so" % int((b[:n] > a[:n]).sum()))
    print("   thay doi trung vi: %+.2f px = %+.1f cm"
          % (np.median(b[:n] - a[:n]), np.median(b[:n] - a[:n]) * GSD_CM))

json.dump({k: v.tolist() for k, v in ket.items()},
          open("ket_qua/do_khop_ortho.json", "w", encoding="utf-8"), indent=1)
print("\n-> do_khop_ortho.json")
