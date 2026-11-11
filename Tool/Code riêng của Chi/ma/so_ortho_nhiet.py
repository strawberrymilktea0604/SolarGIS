#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""So ortho nhiet cua Metashape voi ban tu ghep, tren CUNG mot vung lon/lat.

Luu y khi doc hai file: thermal_ortho.tif cua Metashape la anh 4 bang DA TO MAU
(RGBA), con ortho_nhiet_tu_lam.tif la 1 bang gia tri nhiet tho. So thang gia tri
hai file la vo nghia — phai to mau ban tu ghep roi moi dat canh nhau.

Xuat ra _so_ortho_TOAN.png (toan canh) va _so_ortho_CAN.png (can canh ~40 m).
"""
import os

import cv2
import numpy as np
import rasterio
from rasterio.windows import from_bounds

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

MS = "du_lieu/Thermal2_31M_full_export/thermal_ortho.tif"
TU = "ket_qua/ortho/ortho_nhiet_tu_lam.tif"


def doc(f, bien, rong):
    """Cat mot vung lon/lat, tra ve anh BGR da chuan hoa."""
    r = rasterio.open(f)
    w = from_bounds(*bien, transform=r.transform)
    if r.count >= 3:                       # Metashape: da to mau san
        a = r.read((1, 2, 3), window=w, boundless=True, fill_value=0)
        img = np.transpose(a, (1, 2, 0))[:, :, ::-1].astype(np.uint8)
    else:                                  # tu ghep: gia tri tho -> to mau
        a = r.read(1, window=w, boundless=True, fill_value=0).astype(np.float32)
        co = a[a > 0]
        lo, hi = np.percentile(co, [2, 98]) if co.size > 50 else (0, 255)
        n = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
        img = cv2.applyColorMap((n * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        img[a == 0] = (30, 25, 20)         # cho trong: xam toi, de phan biet
    if img.shape[1] < 4:
        return None
    tl = rong / img.shape[1]
    return cv2.resize(img, (rong, max(1, int(img.shape[0] * tl))),
                      interpolation=cv2.INTER_AREA)


def ghep(bien, ten, nhan, rong=1500):
    a = doc(MS, bien, rong)
    b = doc(TU, bien, rong)
    if a is None or b is None:
        print("  bo qua", ten)
        return
    h = max(a.shape[0], b.shape[0])
    a = cv2.copyMakeBorder(a, 0, h - a.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    b = cv2.copyMakeBorder(b, 0, h - b.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    dai = np.full((h, 8, 3), 255, np.uint8)
    H = np.hstack([a, dai, b])
    H = cv2.copyMakeBorder(H, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(20, 18, 16))
    cv2.putText(H, "METASHAPE (da to mau san)", (10, 23),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(H, "TU GHEP (H + DSM, 1 anh / 1 pixel)", (rong + 18, 23),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (120, 200, 255), 1, cv2.LINE_AA)
    cv2.imwrite(ten, H)
    print("  %-22s %s  (%d x %d)" % (nhan, ten, H.shape[1], H.shape[0]))


# vung chung cua hai file
r1, r2 = rasterio.open(MS), rasterio.open(TU)
chung = (max(r1.bounds.left, r2.bounds.left), max(r1.bounds.bottom, r2.bounds.bottom),
         min(r1.bounds.right, r2.bounds.right), min(r1.bounds.top, r2.bounds.top))
print("Vung chung: %.6f %.6f %.6f %.6f" % chung)
print("  Metashape phu lat %.6f-%.6f | tu ghep %.6f-%.6f"
      % (r1.bounds.bottom, r1.bounds.top, r2.bounds.bottom, r2.bounds.top))

ghep(chung, "tai_lieu/_so_ortho_TOAN.png", "toan canh")

# can canh ~40 m giua nha may
cx = (chung[0] + chung[2]) / 2
cy = (chung[1] + chung[3]) / 2
d = 0.00020        # ~22 m moi chieu
ghep((cx - d, cy - d / 2, cx + d, cy + d / 2), "tai_lieu/_so_ortho_CAN.png", "can canh ~44 m")
