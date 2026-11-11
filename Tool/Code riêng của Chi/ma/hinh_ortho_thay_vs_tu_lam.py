#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hai hinh cho phep thu `thu_detect_ortho_thay.py`.

HINH 1 `ortho_thay_a_doi_chieu.jpg` - ba cot canh nhau tren CUNG mot loi:
    anh le ironbow goc | ortho THAY | ortho TU GHEP
  Moi o ortho la cua so 640x512 dat loi moc vao chinh giua; chu thap = vi tri
  loi moc. Model chay tren anh DA XOAY (thay 90 do, tu ghep 270 do) roi box duoc
  anh nguoc ve khung bac-len de ba cot nhin cung mot huong.

HINH 2 `ortho_thay_b_lech_he_toa_do.jpg` - phong to mot day tam:
  cham do = loi moc (he toa do RGB), cham xanh = phat hien tren ortho thay.
  Muc dich cho thay do lech ~2 m la MOT TRUONG lech co huong, khong phai nhieu
  ngau nhien - tuc model NHIN THAY loi, chi la ortho dat sai cho.

    py -3.13 ma/hinh_ortho_thay_vs_tu_lam.py
"""
import csv
import json
import os
import sys

import cv2
import numpy as np
import rasterio
from rasterio.windows import Window

import goc  # noqa: F401

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = r"mo_hinh\fault_obb_4class.pt"
THAY = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export/thermal_ortho.tif")
TULAM = os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif")
HINH = os.path.join(BASE, "tai_lieu/hinh")
TW, TH = 640, 512
CONF = 0.25
XOAY_THAY, XOAY_TULAM = 90, 270

CAM = (40, 130, 245)      # BGR - phat hien
LUC = (90, 220, 90)       # moc
TRANG = (255, 255, 255)


def met(lat):
    return 111320.0 * np.cos(np.radians(lat)), 110574.0


def to_inferno(x):
    g = cv2.normalize(x, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)


def xoay_anh(c, d):
    if not d:
        return c
    return cv2.rotate(c, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                          270: cv2.ROTATE_90_COUNTERCLOCKWISE}[d])


def go_xoay(x, y, W, H, d):
    if d == 90:
        return y, H - 1 - x
    if d == 270:
        return W - 1 - y, x
    if d == 180:
        return W - 1 - x, H - 1 - y
    return x, y


def chay(col, deg, W, H):
    """Chay model tren anh DA XOAY, tra box ve he toa do anh CHUA XOAY."""
    r = model.predict(xoay_anh(col, deg), imgsz=640, conf=CONF, verbose=False)[0]
    if getattr(r, "obb", None) is None or len(r.obb) == 0:
        return []
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    cf = r.obb.conf.cpu().numpy()
    cl = [model.names[int(c)] for c in r.obb.cls.cpu().numpy()]
    return [(np.array([go_xoay(x, y, W, H, deg) for x, y in q[k]], np.float32),
             float(cf[k]), cl[k]) for k in range(len(q))]


def ve_box(im, ds, mau=CAM, day=2):
    for poly, cf, cl in ds:
        cv2.polylines(im, [poly.astype(np.int32)], True, mau, day, cv2.LINE_AA)
        x, y = poly[:, 0].min(), poly[:, 1].min()
        cv2.putText(im, "%s %.2f" % (cl[:12], cf), (int(x), max(12, int(y) - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, mau, 1, cv2.LINE_AA)
    return im


def chu_thap(im, cx, cy, mau=LUC, r=16):
    cv2.line(im, (int(cx - r), int(cy)), (int(cx + r), int(cy)), mau, 2, cv2.LINE_AA)
    cv2.line(im, (int(cx), int(cy - r)), (int(cx), int(cy + r)), mau, 2, cv2.LINE_AA)
    cv2.circle(im, (int(cx), int(cy)), r + 6, mau, 1, cv2.LINE_AA)
    return im


def nhan(im, chu, phu=""):
    """Dai chu tren dinh o."""
    h = 44 if phu else 26
    b = np.zeros((h, im.shape[1], 3), np.uint8)
    b[:] = (28, 28, 30)
    cv2.putText(b, chu, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TRANG, 1, cv2.LINE_AA)
    if phu:
        cv2.putText(b, phu, (8, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (170, 170, 175),
                    1, cv2.LINE_AA)
    return np.vstack([b, im])


loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
ML, MT = met(float(np.mean([x["lat"] for x in loi])))
rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

from ultralytics import YOLO           # noqa: E402
model = YOLO(MODEL)

s_thay, s_tulam = rasterio.open(THAY), rasterio.open(TULAM)
GSD_T = abs(s_thay.transform[0]) * ML * 100.0
GSD_L = abs(s_tulam.transform[0]) * ML * 100.0


def cat(src, d, mau_kenh):
    r_, c_ = src.index(d["lon"], d["lat"])
    c0, r0 = int(c_ - TW / 2), int(r_ - TH / 2)
    if c0 < 0 or r0 < 0 or c0 + TW > src.width or r0 + TH > src.height:
        return None
    if mau_kenh:
        a = src.read([1, 2, 3], window=Window(c0, r0, TW, TH))
        if (a.sum(0) > 0).mean() < 0.98:
            return None
        return a.transpose(1, 2, 0)[:, :, ::-1].copy()
    im = src.read(1, window=Window(c0, r0, TW, TH))
    if (im != 0).mean() < 0.98:
        return None
    return to_inferno(im)


# ------------------------------------------------------- HINH 1: ba cot doi chieu
print("hinh 1 - chon loi co du ba nguon ...")
chon = []
for k in np.linspace(0, len(loi) - 1, 90).astype(int):
    d = loi[k]
    if d.get("seq") not in rows:
        continue
    a, b = cat(s_thay, d, True), cat(s_tulam, d, False)
    if a is None or b is None:
        continue
    fr = cv2.imread(rows[d["seq"]]["path_thermal"])
    if fr is None:
        continue
    chon.append((d, fr, a, b))
    if len(chon) == 3:
        break

hang = []
for d, fr, a, b in chon:
    dsA = chay(fr, 0, fr.shape[1], fr.shape[0])
    dsT = chay(a, XOAY_THAY, TW, TH)
    dsL = chay(b, XOAY_TULAM, TW, TH)

    def lech(ds, gsd):
        if not ds:
            return None
        t = np.array([[p[:, 0].mean(), p[:, 1].mean()] for p, _, _ in ds])
        return float(np.hypot(t[:, 0] - TW / 2, t[:, 1] - TH / 2).min() * gsd / 100)

    lT, lL = lech(dsT, GSD_T), lech(dsL, GSD_L)
    oA = nhan(ve_box(fr.copy(), dsA), "A. anh nhiet le - ironbow goc",
              "%s  |  %d phat hien  |  NHANH DANG DUNG" % (d["seq"], len(dsA)))
    oT = nhan(chu_thap(ve_box(a.copy(), dsT), TW / 2, TH / 2),
              "B. ortho THAY ghep (Metashape)",
              "%d phat hien  |  gan tam nhat: %s" % (
                  len(dsT), "%.2f m" % lT if lT is not None else "khong co"))
    oL = nhan(chu_thap(ve_box(b.copy(), dsL), TW / 2, TH / 2),
              "C. ortho TU GHEP (chieu qua DSM)",
              "%d phat hien  |  gan tam nhat: %s" % (
                  len(dsL), "%.2f m" % lL if lL is not None else "khong co"))
    hang.append(np.hstack([oA, np.zeros((oA.shape[0], 8, 3), np.uint8), oT,
                           np.zeros((oA.shape[0], 8, 3), np.uint8), oL]))
    print("   %s  thay %s  tu ghep %s" % (d["seq"], lT, lL))

h1 = np.vstack([x for p in hang for x in
                (p, np.zeros((10, hang[0].shape[1], 3), np.uint8))])[:-10]
chan = np.zeros((34, h1.shape[1], 3), np.uint8)
chan[:] = (28, 28, 30)
cv2.putText(chan, "chu thap xanh = vi tri loi moc (he toa do RGB) dat vao chinh giua o | "
                  "khung cam = model bat duoc | conf 0.25", (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (170, 170, 175), 1, cv2.LINE_AA)
h1 = np.vstack([h1, chan])
p1 = os.path.join(HINH, "ortho_thay_a_doi_chieu.jpg")
cv2.imwrite(p1, h1, [cv2.IMWRITE_JPEG_QUALITY, 92])
print("-> %s  (%dx%d)" % (os.path.relpath(p1, BASE), h1.shape[1], h1.shape[0]))

