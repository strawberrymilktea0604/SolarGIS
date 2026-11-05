#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Xuat ORTHO NHIET THAY GHEP ra JPG xem duoc bang trinh xem anh thuong.

`du_lieu/Thermal2_31M_full_export/thermal_ortho.tif` la GeoTIFF 122 MB, 4 kenh
RGBA, 8600x3448 - Photos/Paint mo khong noi. Script xuat hai ban:

  ortho_thay_toan_canh.jpg            nguyen ban, dung do phan giai goc
  ortho_thay_toan_canh_phat_hien.jpg  chong them ket qua cua thu_detect_ortho_thay:
                                      khung xanh = 466 phat hien tren ortho thay,
                                      cham xanh la = 603 loi moc cua nhanh anh le.
                                      Zoom vao se thay hai lop lech nhau ~2,4 m.

    py -3.13 ma/xuat_ortho_thay_toan_canh.py
"""
import json
import os
import sys

import cv2
import numpy as np
import rasterio

import goc  # noqa: F401

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THAY = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export/thermal_ortho.tif")
HINH = os.path.join(BASE, "tai_lieu/hinh")

src = rasterio.open(THAY)
print("doc %s  %dx%d, %d kenh" % (os.path.basename(THAY), src.width, src.height, src.count))
rgb = src.read([1, 2, 3]).transpose(1, 2, 0)          # RGB
bgr = np.ascontiguousarray(rgb[:, :, ::-1])           # -> BGR cho cv2

p1 = os.path.join(HINH, "ortho_thay_toan_canh.jpg")
cv2.imwrite(p1, bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
print("-> %s  (%.1f MB)" % (os.path.relpath(p1, BASE), os.path.getsize(p1) / 1e6))

# ------------------------------------------------------- ban chong ket qua len
ds = os.path.join(BASE, "ket_qua/detect_ortho_thay_ds_phat_hien.json")
if not os.path.exists(ds):
    print("chua co %s - bo qua ban chong ket qua" % os.path.basename(ds))
    raise SystemExit

cum = json.load(open(ds, encoding="utf-8"))
loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
im = bgr.copy()

for p in cum:                                          # khung phat hien - xanh lam
    q = np.array([src.index(x, y)[::-1] for x, y in p["poly"]], np.int32)
    cv2.polylines(im, [q], True, (255, 224, 51), 3, cv2.LINE_AA)
for d in loi:                                          # loi moc - xanh la
    r_, c_ = src.index(d["lon"], d["lat"])
    cv2.circle(im, (int(c_), int(r_)), 9, (107, 255, 139), 3, cv2.LINE_AA)

dai = np.zeros((78, im.shape[1], 3), np.uint8)
dai[:] = (28, 28, 30)
cv2.putText(dai, "ORTHO NHIET THAY GHEP (Metashape) - %dx%d, 2,62 cm/px, 225,7 x 90,5 m"
            % (src.width, src.height), (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
            (255, 255, 255), 2, cv2.LINE_AA)
cv2.putText(dai, "khung xanh lam = %d phat hien cua fault_obb_4class.pt quet tren chinh "
                 "ortho nay   |   vong xanh la = %d loi moc tu nhanh anh le (he toa do RGB)"
            % (len(cum), len(loi)), (16, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.72,
            (170, 170, 175), 2, cv2.LINE_AA)
im = np.vstack([dai, im])

p2 = os.path.join(HINH, "ortho_thay_toan_canh_phat_hien.jpg")
cv2.imwrite(p2, im, [cv2.IMWRITE_JPEG_QUALITY, 90])
print("-> %s  (%.1f MB)" % (os.path.relpath(p2, BASE), os.path.getsize(p2) / 1e6))
