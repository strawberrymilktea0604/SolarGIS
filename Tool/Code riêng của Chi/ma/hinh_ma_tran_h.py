#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ba hình chuyên giải thích MA TRẬN H — cho trang `H hoạt động thế nào`.

Khác với `hinh_hieu_chuan_chi_tiet.py` (dựng hình cho quy trình hiệu chuẩn), ba
hình ở đây mổ xẻ chính bản thân phép biến đổi:

  V1  bốn góc đi đâu   khung ảnh nhiệt 640×512 sau khi qua H nằm ở đâu trên khung
                       RGB 4056×3040, kèm lưới ô vuông bị biến dạng theo.
  V2  phần phối cảnh   hai số ở hàng cuối của H làm gì. Tắt chúng đi rồi đo xem
                       mỗi điểm dịch bao nhiêu — trường vector, phóng đại ×5.
  V3  31 vector sai số Vẽ sai số của từng cặp điểm, phóng đại ×20. Hai vế:
                       chỉ H, và H cộng `hieu_chinh_bo_sung`.

V3 là hình đáng giá nhất: ở vế trái mọi mũi tên chỉ CÙNG MỘT HƯỚNG — dấu hiệu
kinh điển của một độ lệch hằng số chưa được trừ. Vế phải mũi tên tán loạn, tức chỉ
còn nhiễu chấm tay. Đo được: chỉ H thì RMSE 11,65 px và sai số trung bình
(−9,65; −4,84) px; cộng offset thì RMSE về đúng 4,38 px như file ghi.

    py -3.13 ma/hinh_ma_tran_h.py
    py -3.13 ma/hinh_ma_tran_h.py --chi V3
"""
import argparse
import csv
import json
import os
import sys

import cv2
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

TRANG = (255, 255, 255)
DEN = (28, 24, 20)
CAM = (0, 77, 194)
XANH = (158, 95, 47)
LUC = (80, 160, 60)
DO = (60, 45, 200)
NEN = (250, 246, 244)

D = json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))
H = np.array(D["H_thermal_to_rgb"], float)
PT = np.array(D["points_thermal"], float)
PR = np.array(D["points_rgb"], float)
BU = D["hieu_chinh_bo_sung"]
TW, TH = D["thermal_size"]
RW, RH = D["rgb_size"]

rows = {}
with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows[r["seq"]] = r
th = cv2.imread(rows["0280"]["path_thermal"])
rgb = cv2.imread(rows["0280"]["path_rgb"])


def qua_H(P, M=None):
    M = H if M is None else M
    P = np.asarray(P, float).reshape(-1, 2)
    q = (M @ np.c_[P, np.ones(len(P))].T).T
    return q[:, :2] / q[:, 2:]


def bang_ten(a, chu, cao=34, co=0.56):
    h, w = a.shape[:2]
    ra = np.full((h + cao, w, 3), DEN, np.uint8)
    ra[cao:] = a
    cv2.putText(ra, chu, (10, cao - 11), cv2.FONT_HERSHEY_SIMPLEX, co, TRANG, 1, cv2.LINE_AA)
    return ra


def vien(a, mau=(222, 213, 205), d=3):
    return cv2.copyMakeBorder(a, d, d, d, d, cv2.BORDER_CONSTANT, value=mau)


# ======================================================== V1 · bốn góc đi đâu
def lam_V1():
    nen = rgb.copy()
    nen = (nen * 0.55).astype(np.uint8)          # làm mờ để lưới nổi lên

    # lưới ô vuông trên ảnh nhiệt, chiếu qua H -> thấy nó biến dạng thế nào
    B = 8
    for i in range(B + 1):
        doc = np.array([[i * TW / B, t * TH / 40] for t in range(41)])
        ngang = np.array([[t * TW / 40, i * TH / B] for t in range(41)])
        for P in (doc, ngang):
            q = qua_H(P).astype(np.int32)
            cv2.polylines(nen, [q], False, XANH, 2, cv2.LINE_AA)

    goc = qua_H([[0, 0], [TW, 0], [TW, TH], [0, TH]])
    cv2.polylines(nen, [goc.astype(np.int32)], True, CAM, 6, cv2.LINE_AA)
    ten = ["(0,0)", "(640,0)", "(640,512)", "(0,512)"]
    for (x, y), t in zip(goc, ten):
        cv2.circle(nen, (int(x), int(y)), 14, CAM, -1, cv2.LINE_AA)
        cv2.putText(nen, "%s -> (%d,%d)" % (t, x, y), (int(x) + 22, int(y) - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.15, CAM, 3, cv2.LINE_AA)

    k = 1240 / RW
    nen = cv2.resize(nen, (1240, int(RH * k)), interpolation=cv2.INTER_AREA)
    nen = bang_ten(nen, "KHUNG RGB 4056x3040  -  cam: khung anh nhiet sau khi qua H  |  "
                        "xanh: luoi o vuong cua anh nhiet, cung qua H")
    p = os.path.join(args.ra, "h_v1_bon_goc.jpg")
    cv2.imwrite(p, vien(nen), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("[V1] %s (%.0f KB)" % (os.path.basename(p), os.path.getsize(p) / 1024))


# ====================================================== V2 · phần phối cảnh
def lam_V2():
    A = H.copy()
    A[2] = [0, 0, 1]                              # H không có phối cảnh
    nen = cv2.resize(th, (TW * 2, TH * 2), interpolation=cv2.INTER_CUBIC)
    nen = (nen * 0.5 + 90).astype(np.uint8)
    K = 5                                         # phóng đại mũi tên

    # đo ở BỐN GÓC THẬT, không lấy theo lưới mẫu (lưới dừng cách mép 30 px nên hụt)
    lon = max(float(np.hypot(*(qua_H([[u, v]])[0] - qua_H([[u, v]], A)[0])))
              for u, v in [(0, 0), (TW, 0), (0, TH), (TW, TH)])
    for u in np.linspace(30, TW - 30, 9):
        for v in np.linspace(30, TH - 30, 7):
            p = qua_H([[u, v]])[0]
            a = qua_H([[u, v]], A)[0]
            d = p - a                             # phần phối cảnh gây ra
            pass  # lon da do o bon goc that
            x0, y0 = int(u * 2), int(v * 2)
            x1, y1 = int(x0 + d[0] * K), int(y0 + d[1] * K)
            cv2.arrowedLine(nen, (x0, y0), (x1, y1), DO, 2, cv2.LINE_AA, tipLength=0.3)
            cv2.circle(nen, (x0, y0), 3, DEN, -1, cv2.LINE_AA)

    for u, v, t in [(0, 0, "0 px"), (TW, 0, "21,6 px"), (0, TH, "2,4 px"),
                    (TW, TH, "29,6 px"), (TW / 2, TH / 2, "10,5 px")]:
        x, y = int(np.clip(u * 2, 60, TW * 2 - 130)), int(np.clip(v * 2, 40, TH * 2 - 20))
        cv2.putText(nen, t, (x - 50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, DO, 2, cv2.LINE_AA)

    nen = bang_ten(nen, "Hai so o HANG CUOI cua H lam gi  -  mui ten = do dich, phong dai x%d  "
                        "(lon nhat that: %.1f px o goc duoi-phai)" % (K, lon), co=0.55)
    p = os.path.join(args.ra, "h_v2_phoi_canh.jpg")
    cv2.imwrite(p, vien(nen), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[V2] %s (%.0f KB, lech lon nhat %.1f px)" % (os.path.basename(p),
                                                        os.path.getsize(p) / 1024, lon))


# ==================================================== V3 · 31 vector sai số
def lam_V3():
    q = qua_H(PT)
    off = np.array([BU["dx_px"], BU["dy_px"]])
    K = 20                                        # phóng đại sai số

    # TRỪ chứ không cộng — đúng quy ước của lam_notebook.py:90 `q - [dx, dy]`.
    # Sai số r = PR − q có trung bình (−9,65; −4,84), nên dự đoán đúng là q − off.
    ra = []
    for du, ten in [(q, "CHI DUNG H"), (q - off, "H - hieu_chinh_bo_sung")]:
        e = PR - du
        rmse = float(np.sqrt((e ** 2).sum(1).mean()))
        tb = e.mean(0)

        nen = (rgb * 0.45 + 110).astype(np.uint8)
        for (x, y), (dx, dy) in zip(du, e):
            cv2.arrowedLine(nen, (int(x), int(y)), (int(x + dx * K), int(y + dy * K)),
                            DO, 5, cv2.LINE_AA, tipLength=0.25)
            cv2.circle(nen, (int(x), int(y)), 9, XANH, -1, cv2.LINE_AA)

        # cắt quanh vùng có điểm
        x0, y0 = int(du[:, 0].min() - 260), int(du[:, 1].min() - 260)
        x1, y1 = int(du[:, 0].max() + 260), int(du[:, 1].max() + 260)
        v = nen[max(y0, 0):y1, max(x0, 0):x1]
        v = cv2.resize(v, (700, int(v.shape[0] * 700 / v.shape[1])), interpolation=cv2.INTER_AREA)
        v = bang_ten(v, "%s  -  RMSE %.2f px" % (ten, rmse))
        nh = np.full((32, v.shape[1], 3), NEN, np.uint8)
        cv2.putText(nh, "sai so trung binh: (%+.2f, %+.2f) px" % (tb[0], tb[1]),
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (32, 22, 27), 1, cv2.LINE_AA)
        ra.append(vien(np.vstack([nh, v])))

    cao = max(x.shape[0] for x in ra)
    ra = [cv2.copyMakeBorder(x, 0, cao - x.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=NEN)
          for x in ra]
    cap = np.hstack(ra)
    nhan = np.full((34, cap.shape[1], 3), NEN, np.uint8)
    cv2.putText(nhan, "31 vector sai so, phong dai x%d. Trai: moi mui ten chi CUNG MOT HUONG "
                      "= con mot do lech hang so chua tru." % K,
                (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (32, 22, 27), 1, cv2.LINE_AA)
    p = os.path.join(args.ra, "h_v3_sai_so.jpg")
    cv2.imwrite(p, np.vstack([nhan, cap]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[V3] %s (%.0f KB)" % (os.path.basename(p), os.path.getsize(p) / 1024))


for ten, fn in [("V1", lam_V1), ("V2", lam_V2), ("V3", lam_V3)]:
    if not args.chi or args.chi.upper() == ten:
        fn()
