#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng hình chi tiết cho bước HIỆU CHUẨN H — ảnh thật, số thật.

Ba hình, đi từ "chấm cái gì" tới "chấm xong thì được gì":

  C1  31 cặp điểm    ảnh nhiệt và ảnh RGB cạnh nhau, mỗi cặp điểm cùng số cùng màu.
                     Đây là TOÀN BỘ đầu vào của phép hiệu chuẩn — chỉ có thế.
  C2  bàn cờ         ảnh nhiệt sau khi warp bằng H, cài răng lược với ảnh RGB.
                     Lưới tấm pin chạy liền qua mép ô = H đúng.
  C3  hãng vs tay    cùng ảnh nhiệt, warp bằng hai ma trận, chồng viền tấm pin
                     lấy từ RGB. Trái lệch thấy rõ, phải khít.

Ma trận của hãng (`RTK350.txt`) ghi theo hệ PHẦN TRĂM khung ảnh, không phải pixel.
Đổi bằng H_px = S_rgb · H_% · S_nhiệt⁻¹ với S là hai ma trận tỉ lệ. Đã kiểm chéo:
đổi `H_percent` trong thermal_to_rgb.json theo đúng công thức này thì ra lại khớp
`H_thermal_to_rgb` tới 1e-13, nên công thức đúng.

H được khớp trên ảnh RGB ĐÃ KHỬ MÉO (`rgb_undistorted: true`), nên ở đây cũng phải
khử méo trước khi so, nếu không mép ảnh lệch thêm vài px không phải lỗi của H.

    py -3.13 ma/hinh_hieu_chuan_chi_tiet.py
    py -3.13 ma/hinh_hieu_chuan_chi_tiet.py --chi C2
"""
import argparse
import csv
import os
import json
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
HANG = r"mo_hinh\RTK350.txt"

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

TRANG = (255, 255, 255)
DEN = (28, 24, 20)
LUC = (80, 200, 90)
DO = (60, 45, 200)
NEN = (250, 246, 244)

D = json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))
H = np.array(D["H_thermal_to_rgb"], float)
PT = np.array(D["points_thermal"], float)
PR = np.array(D["points_rgb"], float)
TW, TH = D["thermal_size"]
RW, RH = D["rgb_size"]

rows = {}
with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows[r["seq"]] = r
seq = "0280"
th = cv2.imread(rows[seq]["path_thermal"])
rgb = cv2.imread(rows[seq]["path_rgb"])
if th is None or rgb is None:
    raise SystemExit("[DỪNG] không đọc được cặp ảnh %s" % seq)


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


def bang_ten(anh, chu, cao=32, mau=DEN):
    h, w = anh.shape[:2]
    ra = np.full((h + cao, w, 3), mau, np.uint8)
    ra[cao:] = anh
    cv2.putText(ra, chu, (10, cao - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, TRANG, 1, cv2.LINE_AA)
    return ra


def vien(a, mau=(222, 213, 205), d=3):
    return cv2.copyMakeBorder(a, d, d, d, d, cv2.BORDER_CONSTANT, value=mau)


def h_tu_phan_tram(P):
    """Ma trận hệ % -> ma trận hệ pixel. Kiểm chéo trong docstring."""
    St = np.diag([100.0 / TW, 100.0 / TH, 1.0])
    Sr = np.diag([RW / 100.0, RH / 100.0, 1.0])
    M = Sr @ np.array(P, float) @ St
    return M / M[2, 2]


# vùng mà ảnh nhiệt phủ lên khung RGB — cắt để khỏi thừa mép đen
goc4 = cv2.perspectiveTransform(
    np.array([[[0, 0], [TW, 0], [TW, TH], [0, TH]]], float), H)[0]
X0, Y0 = int(goc4[:, 0].min()), int(goc4[:, 1].min())
X1, Y1 = int(goc4[:, 0].max()), int(goc4[:, 1].max())


# ============================================================= C1 · 31 cặp điểm
def lam_C1():
    a = th.copy()
    b = rgb_u.copy()
    for i, ((ux, uy), (vx, vy)) in enumerate(zip(PT, PR), 1):
        mau = tuple(int(c) for c in cv2.applyColorMap(
            np.array([[int(255 * i / len(PT))]], np.uint8), cv2.COLORMAP_HSV)[0, 0])
        cv2.circle(a, (int(ux), int(uy)), 6, mau, 2, cv2.LINE_AA)
        cv2.putText(a, str(i), (int(ux) + 8, int(uy) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, mau, 1, cv2.LINE_AA)
        cv2.circle(b, (int(vx), int(vy)), 16, mau, 4, cv2.LINE_AA)
        cv2.putText(b, str(i), (int(vx) + 20, int(vy) - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, mau, 3, cv2.LINE_AA)

    b = b[max(Y0 - 260, 0):Y1 + 260, max(X0 - 260, 0):X1 + 260]
    k = 620 / a.shape[0]
    a = cv2.resize(a, (int(a.shape[1] * k), 620), interpolation=cv2.INTER_CUBIC)
    b = cv2.resize(b, (int(b.shape[1] * 620 / b.shape[0]), 620), interpolation=cv2.INTER_AREA)
    a = bang_ten(a, "ANH NHIET  %s_T  640x512" % seq)
    b = bang_ten(b, "ANH RGB  %s_W  da khu meo  (cat quanh vung nhiet phu)" % seq)
    ra = np.hstack([vien(a), vien(b)])
    nhan = np.full((36, ra.shape[1], 3), NEN, np.uint8)
    cv2.putText(nhan, "31 cap diem cham tay  -  RMSE 4,38 px  -  trung vi 2,95 px  -  lon nhat 9,25 px",
                (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (32, 22, 27), 1, cv2.LINE_AA)
    p = os.path.join(args.ra, "hieu_chuan_c1_cap_diem.jpg")
    cv2.imwrite(p, np.vstack([nhan, ra]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[C1] %s (%.0f KB)" % (os.path.basename(p), os.path.getsize(p) / 1024))


# ================================================================= C2 · bàn cờ
def lam_C2():
    w = cv2.warpPerspective(th, H, (RW, RH))
    O = 150                                     # ô bàn cờ, px
    yy, xx = np.mgrid[0:RH, 0:RW]
    ca = ((xx // O + yy // O) % 2).astype(bool)
    tron = np.where(ca[:, :, None], w, rgb_u)
    # kẻ mép ô cho thấy ranh giới cài răng lược
    for x in range(0, RW, O):
        cv2.line(tron, (x, 0), (x, RH), (255, 255, 255), 1)
    for y in range(0, RH, O):
        cv2.line(tron, (0, y), (RW, y), (255, 255, 255), 1)

    cat = tron[Y0 + 40:Y1 - 40, X0 + 40:X1 - 40]
    k = 1180 / cat.shape[1]
    cat = cv2.resize(cat, (1180, int(cat.shape[0] * k)), interpolation=cv2.INTER_AREA)
    cat = bang_ten(cat, "O SANG: anh RGB   |   O TOI: anh nhiet da warp bang H   "
                        "-> luoi tam pin chay LIEN qua mep o", cao=34)
    p = os.path.join(args.ra, "hieu_chuan_c2_ban_co.jpg")
    cv2.imwrite(p, vien(cat), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[C2] %s (%.0f KB)" % (os.path.basename(p), os.path.getsize(p) / 1024))


# =========================================================== C3 · hãng vs tay
def lam_C3():
    txt = open(HANG, encoding="utf-8").read()
    so = [float(x) for x in txt.replace("[", " ").replace("]", " ").replace(",", " ").split()]
    Hh = h_tu_phan_tram(np.array(so[:9]).reshape(3, 3))

    # HAI CÁCH ĐÃ THỬ VÀ BỎ, ghi lại để không ai thử lại:
    #   Canny thẳng    -> kết cấu cỏ sinh hàng vạn cạnh vụn, xanh tràn kín hình.
    #   Hough đoạn dài -> tệ hơn: lưới CELL trên mặt tấm pin sinh 9 212 đoạn dài,
    #                     vì mỗi mép cell cũng là một đường thẳng dài và thẳng.
    # Phát hiện cạnh sai hướng ngay từ đầu. Dùng lại thủ pháp BÀN CỜ của C2:
    # không cần dò cạnh gì cả, lệch bao nhiêu thì lộ ra ngay ở mép ô cài răng lược.
    O = 72                                      # ô nhỏ hơn C2 để bắt lệch nhỏ
    cx, cy = (X0 + X1) // 2, (Y0 + Y1) // 2
    S = 500                                     # cắt hẹp rồi phóng to: 22 px lệch -> 27 px
    o = (slice(cy - S // 2, cy + S // 2), slice(cx - S // 2, cx + S // 2))
    nen = rgb_u[o]
    yy, xx = np.mgrid[0:S, 0:S]
    ca = (((xx + cx - S // 2) // O + (yy + cy - S // 2) // O) % 2).astype(bool)

    ra = []
    for M, ten, rmse in [(Hh, "MA TRAN CUA HANG (RTK350.txt)", 22.34),
                         (H, "HIEU CHUAN LAI, 31 cap diem cham tay", 4.38)]:
        w = cv2.warpPerspective(th, M, (RW, RH))[o]
        v = np.where(ca[:, :, None], w, nen)
        v = cv2.resize(v, (620, 620), interpolation=cv2.INTER_CUBIC)
        k = 620 / S
        for g in range(0, S + O, O):            # kẻ mép ô để mắt bám vào mà so
            t = int((g - (cx - S // 2) % O) * k)
            if 0 < t < 620:
                cv2.line(v, (t, 0), (t, 620), (255, 255, 255), 1)
            t = int((g - (cy - S // 2) % O) * k)
            if 0 < t < 620:
                cv2.line(v, (0, t), (620, t), (255, 255, 255), 1)
        v = bang_ten(v, "%s  -  RMSE %.2f px" % (ten, rmse), cao=34)
        ra.append(vien(v, (222, 213, 205)))

    cap = np.hstack(ra)
    nhan = np.full((36, cap.shape[1], 3), NEN, np.uint8)
    cv2.putText(nhan, "O sang: anh RGB. O toi: anh nhiet da warp. "
                      "Khop = mep tam pin chay LIEN qua duong ke trang.",
                (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (32, 22, 27), 1, cv2.LINE_AA)
    p = os.path.join(args.ra, "hieu_chuan_c3_hang_vs_tay.jpg")
    cv2.imwrite(p, np.vstack([nhan, cap]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[C3] %s (%.0f KB)" % (os.path.basename(p), os.path.getsize(p) / 1024))


for ten, fn in [("C1", lam_C1), ("C2", lam_C2), ("C3", lam_C3)]:
    if not args.chi or args.chi.upper() == ten:
        fn()
