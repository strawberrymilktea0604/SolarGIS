#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cat anh 84 loi se bi vut neu nang nguong conf len 0,64, de soi bang mat.

Cau hoi can tra loi: nhung loi bi bo do la LOI THAT hay NHIEU? Chi so khong
tra loi duoc, phai nhin. Nen xuat hai tam:
    _soi_BO_DI.png  - loi conf 0,25-0,64 ma roi DUNG trong tam pin (mat oan)
    _soi_GIU_LAI.png - loi conf >= 0,64 de doi chieu
Neu hai tam nhin giong nhau thi nang nguong la dang vut lo thật.

Anh cat tu ortho nhiet tu ghep, moi o ~3,5 m thuc dia, to mau theo phan vi
cua chinh o do (nhiet nen thay doi khap nha may nen khong dung thang do chung).
"""
import json
import os

import cv2
import numpy as np
import rasterio

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

NGUONG = 0.64
O = 132          # canh mot o anh, pixel ortho nhiet (~3,8 m)
COT = 12         # so o moi hang


def cat(r, arr, f):
    """Cat mot o quanh tam loi, to mau, ve khung box."""
    x1, y1, x2, y2 = f["box"]
    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
    n = O // 2
    c0, r0 = max(0, cx - n), max(0, cy - n)
    c1, r1 = min(arr.shape[1], cx + n), min(arr.shape[0], cy + n)
    if c1 - c0 < 20 or r1 - r0 < 20:
        return None
    o = arr[r0:r1, c0:c1].astype(np.float32)
    hop_le = o[np.isfinite(o) & (o != 0)]
    if hop_le.size < 50:
        return None
    lo, hi = np.percentile(hop_le, [2, 98])
    o = np.clip((o - lo) / max(hi - lo, 1e-6), 0, 1)
    img = cv2.applyColorMap((o * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    img = cv2.resize(img, (O, O), interpolation=cv2.INTER_NEAREST)
    # khung box loi, quy ve toa do o da resize
    sx, sy = O / (c1 - c0), O / (r1 - r0)
    cv2.rectangle(img, (int((x1 - c0) * sx), int((y1 - r0) * sy)),
                  (int((x2 - c0) * sx), int((y2 - r0) * sy)), (0, 255, 0), 1)
    cv2.putText(img, "%.2f" % f["conf"], (3, 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.36, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def tam(ds, ten, tieu_de):
    o = [c for c in ds if c is not None]
    if not o:
        print("  khong cat duoc o nao cho", ten)
        return
    hang = (len(o) + COT - 1) // COT
    H = np.zeros((hang * O + 26, COT * O, 3), np.uint8)
    cv2.putText(H, tieu_de, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA)
    for i, im in enumerate(o):
        r, c = divmod(i, COT)
        H[26 + r * O:26 + (r + 1) * O, c * O:(c + 1) * O] = im
    cv2.imwrite(ten, H)
    print("  %-20s %3d o  ->  %s" % (tieu_de.split("—")[0].strip(), len(o), ten))


d = json.load(open("ket_qua/loi_tren_ortho_nhiet.json", encoding="utf-8"))
r = rasterio.open("ket_qua/ortho/ortho_nhiet_tu_lam.tif")
arr = r.read(1)

bo = [f for f in d if f["conf"] < NGUONG and f.get("in_panel")]
giu = [f for f in d if f["conf"] >= NGUONG]
bo.sort(key=lambda f: -f["conf"])
giu.sort(key=lambda f: -f["conf"])

print("Bo di (conf %.2f-%.2f, roi trong tam pin): %d loi" % (0.25, NGUONG, len(bo)))
print("Giu lai (conf >= %.2f)                   : %d loi" % (NGUONG, len(giu)))
tam([cat(r, arr, f) for f in bo], "_soi_BO_DI.png",
    "SE BI VUT neu nang nguong len 0,64 — %d loi roi dung trong tam pin" % len(bo))
tam([cat(r, arr, f) for f in giu[:len(bo)]], "_soi_GIU_LAI.png",
    "GIU LAI o nguong 0,64 — de doi chieu")
