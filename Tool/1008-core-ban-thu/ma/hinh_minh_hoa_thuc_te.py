#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng HÌNH MINH HOẠ BẰNG ẢNH THẬT cho TAI_LIEU_THUAT_TOAN.md.

Ba hình vẽ tay bằng SVG (`thuat_toan_h1..h3`) giải thích cơ chế. Ba hình ở đây
là ảnh THẬT của chính chuyến bay này, để người đọc thấy tận mắt thứ mà sơ đồ nói:

  R1  chuỗi chiếu     ảnh nhiệt gốc có box YOLO  ↔  đúng chỗ đó trên ortho MÀU
                      sau khi chiếu qua DSM. Bốn ca, chọn ảnh chỉ có 1 lỗi để
                      cặp box↔vết là 1-1, không phải đoán.
  R2  hướng cảnh      cùng một ô ortho, đưa vào model hai lần: bắc-lên và xoay
                      270°. Vẽ box model tìm được. Đây là hình chốt của mục 7.2.
  R3  gán tấm pin     ortho màu + polygon tấm pin + vết lỗi tứ giác + mã tấm.

Vì sao không dùng lại `tai_lieu/hinh/h3_loi_that.jpg`: ảnh đó ghi lớp
`SingleByPassed` — lớp của model 8 lớp ở nhánh CŨ đã bỏ. Để trong tài liệu nói về
model 4 lớp là mâu thuẫn ngay trên hình.

    py -3.13 ma/hinh_minh_hoa_thuc_te.py
    py -3.13 ma/hinh_minh_hoa_thuc_te.py --chi R2
"""
import argparse
import csv
import json
import os
import sys

import cv2
import numpy as np
import rasterio
from rasterio.windows import Window

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = r"mo_hinh\fault_obb_4class.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="chỉ dựng một hình: R1 / R2 / R3")
ap.add_argument("--conf", type=float, default=0.25)
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

# BGR — cùng bảng màu với tài liệu: ember cam, steel xanh, good xanh lá, bad đỏ
CAM = (0, 77, 194)
XANH = (158, 95, 47)
LUC = (80, 200, 90)      # lục sáng — box bắt ĐÚNG
DO = (64, 48, 176)
LO = (235, 220, 40)      # lơ — box model nổ nhưng KHÔNG trúng; nền inferno cam
                         # nên đỏ chìm mất, phải dùng màu đối lập mới đọc được
TRANG = (255, 255, 255)
DEN = (28, 24, 20)

loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
oc = rasterio.open(os.path.join(BASE, "du_lieu/Thermal2_31M_full_export/ortho.tif"))
ot = rasterio.open(os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
GSD_C = abs(oc.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100   # cm/px ortho màu
GSD_T = abs(ot.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100   # cm/px ortho nhiệt

from ultralytics import YOLO       # noqa: E402
model = YOLO(MODEL)
names = model.names


def bang_ten(anh, chu, mau=DEN, cao=30):
    """Thanh tiêu đề đen phía trên một ô ảnh."""
    h, w = anh.shape[:2]
    ra = np.full((h + cao, w, 3), mau, np.uint8)
    ra[cao:] = anh
    cv2.putText(ra, chu, (10, cao - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.52, TRANG, 1, cv2.LINE_AA)
    return ra


def vien(anh, mau, day=3):
    return cv2.copyMakeBorder(anh, day, day, day, day, cv2.BORDER_CONSTANT, value=mau)


def to_mau_nhiet(xam):
    g = cv2.normalize(xam, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)


def obb(anh):
    r = model.predict(anh, imgsz=640, conf=args.conf, verbose=False)[0]
    if getattr(r, "obb", None) is None or len(r.obb) == 0:
        return [], [], []
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    return q, r.obb.conf.cpu().numpy(), [names[int(c)] for c in r.obb.cls.cpu().numpy()]


# =============================================================== R1 · chuỗi chiếu
def lam_R1():
    rows = {}
    with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows[row["seq"]] = row

    # Đếm lỗi theo ảnh; chỉ lấy ảnh CHỈ CÓ MỘT lỗi để cặp box↔vết là 1-1.
    dem = {}
    for d in loi:
        for s in (d.get("seqs") or [d["seq"]]):
            dem[s] = dem.get(s, 0) + 1

    # HAI BẪY đã sập khi dựng hình này:
    #
    # ① Lọc "ảnh chỉ có 1 lỗi" (để cặp box↔vết là 1-1) vô tình toàn ra ẢNH RÌA
    #   trang trại — trung bình một ảnh thấy 6,8 lỗi, nên ảnh chỉ thấy 1 lỗi gần
    #   như chắc chắn là ảnh mép. Ở đó lỗi nằm sát biên khung, chụp rất xiên, vết
    #   chiếu rơi ra bãi cỏ. Đó là ca HỎNG, không minh hoạ được cơ chế.
    #
    # ② Siết thêm in_panel + IoU thì chỉ còn 1 ca lọt — điều kiện tự mâu thuẫn.
    #
    # Cách chữa: BỎ đòi hỏi 1-1. Vẽ MỌI box model tìm được trên ảnh đó (trắng),
    # còn bên phải là vết của ĐÚNG lỗi ghi ở tiêu đề (đỏ). Không tuyên bố cặp
    # nào ứng với cặp nào — cái cần thấy là box trên ảnh gốc và vết trên mặt đất
    # cùng rơi vào một tấm pin.
    o = []
    for d in sorted(loi, key=lambda x: -x["conf"]):
        s = d["seq"]
        if s not in rows or not d.get("poly"):
            continue
        if not d.get("in_panel") or not d.get("panel_code") or d.get("iou", 0) < 0.60:
            continue
        im = cv2.imread(rows[s]["path_thermal"])
        if im is None:
            continue
        q, cf, cl = obb(im)
        if not (1 <= len(q) <= 3):            # ít box thì hình còn đọc được
            continue

        # trái: ảnh nhiệt gốc + mọi box YOLO
        tr = im.copy()
        for k in range(len(q)):
            cv2.polylines(tr, [q[k].astype(np.int32)], True, TRANG, 2, cv2.LINE_AA)
        tr = bang_ten(tr, "ANH NHIET GOC  %s  -  %d box model tim duoc" % (s, len(q)))

        # phải: ortho MÀU cắt quanh lỗi + vết đã chiếu
        cc, rr = ~oc.transform * (d["lon"], d["lat"])
        W = int(6.0 * 100 / GSD_C)            # cửa sổ 6 m
        c0, r0 = int(cc - W / 2), int(rr - W / 2)
        if c0 < 0 or r0 < 0 or c0 + W > oc.width or r0 + W > oc.height:
            continue
        cua = oc.read([1, 2, 3], window=Window(c0, r0, W, W))
        ph = np.ascontiguousarray(np.transpose(cua, (1, 2, 0))[:, :, ::-1])
        vet = np.array([[(~oc.transform * (lo, la))[0] - c0,
                         (~oc.transform * (lo, la))[1] - r0] for lo, la in d["poly"]], np.int32)
        cv2.polylines(ph, [vet], True, DO, 2, cv2.LINE_AA)
        ph = cv2.resize(ph, (tr.shape[0] - 30, tr.shape[0] - 30), interpolation=cv2.INTER_CUBIC)
        ph = bang_ten(ph, "ORTHO MAU  %s  (%.5f, %.5f)" % (d["panel_code"] or "-", d["lon"], d["lat"]))

        cao = min(tr.shape[0], ph.shape[0])
        cap = np.hstack([vien(tr[:cao], CAM), vien(ph[:cao], DO)])
        nhan = np.full((34, cap.shape[1], 3), (250, 246, 244), np.uint8)
        cv2.putText(nhan, "%s   conf %.2f   %d anh cung thay   IoU voi tam pin %.2f"
                    % (d["cls"], d["conf"], d["n"], d["iou"]),
                    (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (32, 22, 27), 1, cv2.LINE_AA)
        o.append(np.vstack([nhan, cap]))
        if len(o) == 4:
            break

    if not o:
        print("[R1] không tìm được ca phù hợp"); return
    r = min(x.shape[1] for x in o)
    o = [cv2.resize(x, (r, int(x.shape[0] * r / x.shape[1]))) for x in o]
    ra = np.vstack([np.vstack([x, np.full((14, r, 3), (250, 246, 244), np.uint8)]) for x in o])
    p = os.path.join(args.ra, "thuc_te_r1_chieu.jpg")
    cv2.imwrite(p, ra, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("[R1] %d ca -> %s (%.0f KB)" % (len(o), os.path.basename(p), os.path.getsize(p) / 1024))


# ============================================================== R2 · hướng cảnh
def lam_R2():
    TW, TH = 640, 512
    o = []
    for d in sorted(loi, key=lambda x: -x["conf"]):
        r_, c_ = ot.index(d["lon"], d["lat"])
        c0, r0 = int(c_ - TW / 2), int(r_ - TH / 2)
        if c0 < 0 or r0 < 0 or c0 + TW > ot.width or r0 + TH > ot.height:
            continue
        im = ot.read(1, window=Window(c0, r0, TW, TH))
        if (im != 0).mean() < 0.98:
            continue
        col = to_mau_nhiet(im)

        q0, cf0, _ = obb(col)
        xoay = cv2.rotate(col, cv2.ROTATE_90_COUNTERCLOCKWISE)
        q7, cf7, cl7 = obb(xoay)

        def trung(q, w, h):
            if not len(q):
                return None
            dm = np.hypot(q[:, :, 0].mean(1) - w / 2, q[:, :, 1].mean(1) - h / 2) * GSD_T / 100
            j = int(np.argmin(dm))
            return j if dm[j] < 1.0 else None

        j0 = trung(q0, TW, TH)
        j7 = trung(q7, xoay.shape[1], xoay.shape[0])
        if j0 is not None or j7 is None:      # chỉ lấy ca BẮC-LÊN TRƯỢT mà XOAY BẮT ĐƯỢC
            continue

        # Trái: bắc-lên. Vẽ MỌI box model nổ ra bằng lơ — để thấy nó không hề im
        # lặng, nó nổ chỗ khác. Chữ thập trắng là vị trí lỗi thật.
        a = col.copy()
        for k in range(len(q0)):
            cv2.polylines(a, [q0[k].astype(np.int32)], True, LO, 2, cv2.LINE_AA)
        cv2.drawMarker(a, (TW // 2, TH // 2), TRANG, cv2.MARKER_CROSS, 28, 2)
        a = bang_ten(a, "ORTHO BAC-LEN  -  bo sot (%d box lo, khong cai nao trung cho)" % len(q0))

        # Phải: cùng ô, xoay. Vẽ box TRONG hệ đã xoay rồi mới quay ảnh về bắc-lên,
        # nên box theo ảnh về đúng chỗ. Ghi nhãn SAU khi quay, nếu không chữ bị dựng đứng.
        b = xoay.copy()
        cv2.polylines(b, [q7[j7].astype(np.int32)], True, LUC, 3, cv2.LINE_AA)
        b = cv2.rotate(b, cv2.ROTATE_90_CLOCKWISE)
        cv2.drawMarker(b, (b.shape[1] // 2, b.shape[0] // 2), TRANG, cv2.MARKER_CROSS, 28, 2)
        b = bang_ten(b, "CUNG O DO, XOAY 270  -  bat duoc  conf %.2f  %s" % (cf7[j7], cl7[j7]))

        cao = max(a.shape[0], b.shape[0])
        def dem(x):
            return cv2.copyMakeBorder(x, 0, cao - x.shape[0], 0, 0,
                                      cv2.BORDER_CONSTANT, value=(250, 246, 244))
        cap = np.hstack([vien(dem(a), DO), vien(dem(b), LUC)])
        nhan = np.full((34, cap.shape[1], 3), (250, 246, 244), np.uint8)
        cv2.putText(nhan, "loi %s tai tam o  -  %s" % (d["cls"], d["panel_code"] or "-"),
                    (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (32, 22, 27), 1, cv2.LINE_AA)
        o.append(np.vstack([nhan, cap]))
        if len(o) == 3:
            break

    if not o:
        print("[R2] không tìm được ca phù hợp"); return
    r = min(x.shape[1] for x in o)
    o = [cv2.resize(x, (r, int(x.shape[0] * r / x.shape[1]))) for x in o]
    ra = np.vstack([np.vstack([x, np.full((14, r, 3), (250, 246, 244), np.uint8)]) for x in o])
    p = os.path.join(args.ra, "thuc_te_r2_huong.jpg")
    cv2.imwrite(p, ra, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("[R2] %d ca -> %s (%.0f KB)" % (len(o), os.path.basename(p), os.path.getsize(p) / 1024))


# ============================================================== R3 · gán tấm pin
def lam_R3():
    panels = [np.array(p) for p in json.load(
        open(os.path.join(BASE, "ket_qua/tam_pin_polygon_4lop.json"), encoding="utf-8"))]
    cen = np.array([p.mean(0) for p in panels])

    d = max((x for x in loi if x.get("panel_code") and x.get("poly") and x["in_panel"]),
            key=lambda x: x["iou"])
    cc, rr = ~oc.transform * (d["lon"], d["lat"])
    W = int(12.0 * 100 / GSD_C)                     # cửa sổ 12 m
    c0, r0 = int(cc - W / 2), int(rr - W / 2)
    cua = oc.read([1, 2, 3], window=Window(c0, r0, W, W))
    ph = np.ascontiguousarray(np.transpose(cua, (1, 2, 0))[:, :, ::-1])

    gan = np.argsort((cen[:, 0] - cc) ** 2 + (cen[:, 1] - rr) ** 2)[:14]
    for i in gan:
        p = (panels[i] - [c0, r0]).astype(np.int32)
        cv2.polylines(ph, [p], True, XANH, 2, cv2.LINE_AA)
    vet = np.array([[(~oc.transform * (lo, la))[0] - c0,
                     (~oc.transform * (lo, la))[1] - r0] for lo, la in d["poly"]], np.int32)
    cv2.polylines(ph, [vet], True, DO, 3, cv2.LINE_AA)
    tx, ty = vet[:, 0].min(), vet[:, 1].min() - 10
    cv2.putText(ph, "%s  IoU %.3f" % (d["panel_code"], d["iou"]), (int(tx), int(ty)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, DO, 2, cv2.LINE_AA)

    ph = bang_ten(ph, "ORTHO MAU  -  xanh: polygon tam pin (6473 tam)   do: vet loi da chieu", cao=34)
    p = os.path.join(args.ra, "thuc_te_r3_gan_tam.jpg")
    cv2.imwrite(p, vien(ph, (222, 213, 205)), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[R3] %s -> %s (%.0f KB)" % (d["panel_code"], os.path.basename(p),
                                       os.path.getsize(p) / 1024))


for ten, fn in [("R1", lam_R1), ("R2", lam_R2), ("R3", lam_R3)]:
    if not args.chi or args.chi.upper() == ten:
        fn()
