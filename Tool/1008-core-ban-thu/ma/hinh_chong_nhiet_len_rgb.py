#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Chồng ảnh nhiệt lên ảnh RGB qua ma trận H — hình minh hoạ phép ghép.

Ảnh nhiệt 640x512 được warp bằng H sang khung ảnh RGB đã khử méo, rồi tô màu
nhiệt và trộn alpha lên nền RGB. Cắt đúng vùng nhiệt phủ để khỏi thừa mép đen.

  A  ba khung ngang    RGB gốc | nhiệt đã warp | chồng alpha
  B  một khung lớn     chỉ ảnh chồng, kèm viền vùng nhiệt phủ

H lấy từ ket_qua/thermal_to_rgb.json (khớp trên RGB ĐÃ KHỬ MÉO, nên ở đây cũng
phải khử méo trước, giống hinh_hieu_chuan_chi_tiet.py).

    py -3.13 ma/hinh_chong_nhiet_len_rgb.py
    py -3.13 ma/hinh_chong_nhiet_len_rgb.py --seq 0280 --alpha 0.45
"""
import argparse
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--seq", default="0280")
ap.add_argument("--alpha", type=float, default=0.45, help="do dam cua lop nhiet")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

TRANG = (255, 255, 255)
DEN = (28, 24, 20)
NEN = (250, 246, 244)
LUC = (80, 200, 90)

D = json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))
H = np.array(D["H_thermal_to_rgb"], float)
TW, TH = D["thermal_size"]
RW, RH = D["rgb_size"]

rows = {}
with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows[r["seq"]] = r
if args.seq not in rows:
    raise SystemExit("[DUNG] khong co seq %s trong manifest_anh.csv" % args.seq)
th = cv2.imread(rows[args.seq]["path_thermal"])
rgb = cv2.imread(rows[args.seq]["path_rgb"])
if th is None or rgb is None:
    raise SystemExit("[DUNG] khong doc duoc cap anh %s" % args.seq)


def khu_meo(im):
    """Khử méo ảnh RGB đúng bộ tham số Metashape đã dùng lúc khớp H."""
    s = ET.parse(os.path.join(EXP, "cameras.xml")).getroot().find(".//chunk").find(".//sensor[@id='0']")
    cal = s.find("calibration[@class='adjusted']")
    g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
    f = g("f")
    K = np.array([[f, 0, im.shape[1] / 2 + g("cx")],
                  [0, f, im.shape[0] / 2 + g("cy")], [0, 0, 1]])
    dist = np.array([g("k1"), g("k2"), g("p1"), g("p2"), g("k3")])
    return cv2.undistort(im, K, dist)


rgb_u = khu_meo(rgb)

# vùng ảnh nhiệt phủ lên khung RGB
goc4 = cv2.perspectiveTransform(
    np.array([[[0, 0], [TW, 0], [TW, TH], [0, TH]]], float), H)[0]
X0, Y0 = max(int(goc4[:, 0].min()), 0), max(int(goc4[:, 1].min()), 0)
X1, Y1 = min(int(goc4[:, 0].max()), rgb_u.shape[1]), min(int(goc4[:, 1].max()), rgb_u.shape[0])

# nhiệt -> khung RGB. Warp cả mặt nạ để biết pixel nào thật sự có nhiệt.
th_g = cv2.cvtColor(th, cv2.COLOR_BGR2GRAY)
th_g = cv2.normalize(th_g, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
th_mau = cv2.applyColorMap(th_g, cv2.COLORMAP_INFERNO)
warp = cv2.warpPerspective(th_mau, H, (rgb_u.shape[1], rgb_u.shape[0]))
mat_na = cv2.warpPerspective(np.full(th.shape[:2], 255, np.uint8), H,
                             (rgb_u.shape[1], rgb_u.shape[0]))

# trộn alpha CHỈ trong vùng có nhiệt
m = (mat_na > 0)[:, :, None].astype(np.float32)
chong = (rgb_u * (1 - args.alpha * m) + warp * (args.alpha * m)).astype(np.uint8)


def cat(a):
    return a[Y0:Y1, X0:X1]


def bang_ten(anh, chu, cao=34, mau=DEN):
    h, w = anh.shape[:2]
    ra = np.full((h + cao, w, 3), mau, np.uint8)
    ra[cao:] = anh
    cv2.putText(ra, chu, (10, cao - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TRANG, 1, cv2.LINE_AA)
    return ra


def vien(a, mau=(222, 213, 205), d=3):
    return cv2.copyMakeBorder(a, d, d, d, d, cv2.BORDER_CONSTANT, value=mau)


def cao_bang(a, cao=560):
    return cv2.resize(a, (int(a.shape[1] * cao / a.shape[0]), cao), interpolation=cv2.INTER_AREA)


# ================================================== A · ba khung: RGB | nhiet | chong
a1 = bang_ten(cao_bang(cat(rgb_u)), "1. RGB da khu meo  (cat vung nhiet phu)")
a2 = bang_ten(cao_bang(cat(warp)), "2. ANH NHIET warp bang H  ->  khung RGB")
a3 = bang_ten(cao_bang(cat(chong)), "3. CHONG  alpha %.2f" % args.alpha)
ra = np.hstack([vien(a1), vien(a2), vien(a3)])
nhan = np.full((38, ra.shape[1], 3), NEN, np.uint8)
cv2.putText(nhan, "Ghep nhiet vao RGB qua H  -  cap %s  -  nhiet %dx%d  ->  RGB %dx%d"
            % (args.seq, TW, TH, RW, RH),
            (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (32, 22, 27), 1, cv2.LINE_AA)
p1 = os.path.join(args.ra, "chong_nhiet_a_ba_khung.jpg")
cv2.imwrite(p1, np.vstack([nhan, ra]), [cv2.IMWRITE_JPEG_QUALITY, 92])

# ================================================== B · mot khung lon, ke vien vung phu
lon = rgb_u.copy()
lon = (lon * (1 - args.alpha * m) + warp * (args.alpha * m)).astype(np.uint8)
cv2.polylines(lon, [goc4.astype(np.int32)], True, LUC, 5, cv2.LINE_AA)
lon = lon[max(Y0 - 200, 0):Y1 + 200, max(X0 - 200, 0):X1 + 200]
lon = bang_ten(cao_bang(lon, 820),
               "CHONG NHIET LEN RGB  -  vien xanh = bon goc anh nhiet sau khi qua H", 40)
p2 = os.path.join(args.ra, "chong_nhiet_b_toan_khung.jpg")
cv2.imwrite(p2, vien(lon), [cv2.IMWRITE_JPEG_QUALITY, 92])

print("[XONG] %s" % p1)
print("[XONG] %s" % p2)
print("       vung nhiet phu tren RGB: x %d..%d  y %d..%d  (%d x %d px)"
      % (X0, X1, Y0, Y1, X1 - X0, Y1 - Y0))
