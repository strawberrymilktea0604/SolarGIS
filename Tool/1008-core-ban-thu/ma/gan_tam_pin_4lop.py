#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Gán mã tấm pin cho đầu ra của model 4 lớp OBB (`loi_tu_anh_le.json`).

Thay cho `bo_dung_goc/gan_loi_vao_tam_pin.py` — bản cũ gán cho 211 lỗi do model
8 lớp quét trên ortho sinh ra. Khác hai chỗ:

  1. Nguồn là `loi_tu_anh_le.json`: detect bằng `fault_obb_4class.pt` trên ẢNH
     GỐC rồi mới chiếu. Cùng model với con số đánh giá.

  2. IoU tính trên VẾT THẬT của lỗi — 4 góc tứ giác xoay đã chiếu xuống mặt đất
     (trường `poly`), không phải hộp thẳng trục dựng từ kích thước trung bình.
     Bản cũ dùng w_m/h_m, mà hai số đó là cạnh của HỘP BAO theo trục ẢNH nên
     lệch ~90° so với hướng nằm của tấm pin -> IoU sai.

Model dò TẤM PIN (`best.pt`) vẫn giữ — nó là việc khác, không phải model lỗi.

    py -3.13 ma/gan_tam_pin_4lop.py
    py -3.13 ma/gan_tam_pin_4lop.py --conf 0.4      # lọc chặt hơn trước khi gán
"""
import argparse
import json
import os
import time
from collections import Counter

import cv2
import numpy as np
import rasterio
from ultralytics import YOLO

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
PANEL_MODEL = r"mo_hinh\best.pt"
SCALE = 2          # best.pt khoanh TẤM PIN ở tỉ lệ này (không phải cell)
TILE = 1024

ap = argparse.ArgumentParser()
ap.add_argument("--nguon", default=os.path.join(BASE, "ket_qua/loi_tu_anh_le.json"))
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"))
ap.add_argument("--out-tam", default=os.path.join(BASE, "ket_qua/tam_pin_polygon_4lop.json"),
                dest="out_tam")
ap.add_argument("--conf", type=float, default=0.0, help="bỏ lỗi dưới ngưỡng này")
ap.add_argument("--quet-lai", action="store_true", dest="quet_lai",
                help="quét lại tấm pin thay vì dùng lại file cũ")
args = ap.parse_args()

t0 = time.time()
det = json.load(open(args.nguon, encoding="utf-8"))
if args.conf > 0:
    truoc = len(det)
    det = [d for d in det if d["conf"] >= args.conf]
    print("[LỌC] conf >= %.2f: %d -> %d lỗi" % (args.conf, truoc, len(det)))

ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100   # cm/px
print("[ORTHO] %d x %d, GSD %.3f cm/px" % (ortho.width, ortho.height, GSD))

co_poly = sum(1 for d in det if d.get("poly"))
print("[NGUỒN] %s — %d lỗi, %d có vết chiếu (`poly`)"
      % (os.path.basename(args.nguon), len(det), co_poly))
if co_poly < len(det):
    print("        thiếu `poly` -> chạy lại `quet_loi_anh_le.py` để có 4 góc đã chiếu")

# ---------------------------------------------- toạ độ -> pixel ortho màu
for d in det:
    c, r = ~ortho.transform * (d["lon"], d["lat"])
    d["ocol"], d["orow"] = float(c), float(r)
    if d.get("poly"):
        d["_opoly"] = [list(~ortho.transform * (lo, la)) for lo, la in d["poly"]]

# ------------------------------------------------ quét tấm pin trên ô có lỗi
side = TILE * SCALE
tiles = sorted({(int(d["ocol"] // side), int(d["orow"] // side)) for d in det})
print("[TẤM PIN] %d lỗi nằm trong %d ô %d px, quét..." % (len(det), len(tiles), side))

if os.path.exists(args.out_tam) and not args.quet_lai:
    panels = [np.array(p, np.float32) for p in json.load(open(args.out_tam))]
    print("[TẤM PIN] dùng lại %d tấm từ %s (--quet-lai để quét mới)"
          % (len(panels), os.path.basename(args.out_tam)))
    tiles = []
else:
    panels = []
mo_hinh_tam = YOLO(PANEL_MODEL) if tiles else None
for n, (tx, ty) in enumerate(tiles, 1):
    c0 = max(0, min(tx * side - side // 2, ortho.width - side))
    r0 = max(0, min(ty * side - side // 2, ortho.height - side))
    img = ortho.read(window=rasterio.windows.Window(c0, r0, side, side))[:3]
    img = np.ascontiguousarray(np.moveaxis(img, 0, -1)[:, :, ::-1])
    small = cv2.resize(img, (TILE, TILE), interpolation=cv2.INTER_AREA)
    res = mo_hinh_tam.predict(small, imgsz=TILE, conf=0.35, max_det=1000, verbose=False)[0]
    if res.obb is not None and len(res.obb):
        panels += list(res.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2) * SCALE + [c0, r0])
    if n % 5 == 0:
        print("   ...%d/%d ô, %d tấm pin, %.0fs" % (n, len(tiles), len(panels), time.time() - t0))

# khử trùng lặp tấm pin giữa các ô (file dùng lại thì đã khử rồi)
if tiles:
    cen = np.array([p.mean(0) for p in panels])
    keep, taken = [], np.zeros(len(panels), bool)
    order = np.argsort(-np.array([cv2.contourArea(p.astype(np.float32)) for p in panels]))
    for i in order:
        if taken[i]:
            continue
        taken |= ((cen - cen[i]) ** 2).sum(1) < (40 ** 2)
        keep.append(panels[i])
    panels = keep
    print("[TẤM PIN] %d tấm duy nhất, %.0fs" % (len(panels), time.time() - t0))
cen = np.array([p.mean(0) for p in panels])

# ------------------------------------------------------- đánh mã dãy / tấm
rows_sorted = np.argsort(cen[:, 1])
row_id = np.zeros(len(panels), int)
cur, last = 0, None
for i in rows_sorted:
    if last is not None and cen[i, 1] - last > 55:      # ~0,5 m -> sang dãy mới
        cur += 1
    row_id[i] = cur
    last = cen[i, 1]
code = {}
for rid in range(cur + 1):
    idx = np.where(row_id == rid)[0]
    for k, i in enumerate(idx[np.argsort(cen[idx, 0])], 1):
        code[i] = "D%02d-T%03d" % (rid + 1, k)
print("[TẤM PIN] %d dãy" % (cur + 1))


def quad_iou(a, b):
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    A, B = cv2.contourArea(a), cv2.contourArea(b)
    if A <= 0 or B <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(a, b)
    return inter / (A + B - inter)


# ------------------------------------------------------------------- gán
# Dự phòng cho lỗi thiếu `poly`: hộp thẳng trục theo kích thước trung vị, lấy
# theo ĐÚNG hướng nằm của tấm pin (w_m/h_m theo trục ảnh nên phải đảo).
kt = np.array([[d["h_m"], d["w_m"]] for d in det])
half = np.median(kt, axis=0) / 2 / (GSD / 100)

for d in det:
    pt = (d["ocol"], d["orow"])
    dd = ((cen[:, 0] - pt[0]) ** 2 + (cen[:, 1] - pt[1]) ** 2)
    near = np.argsort(dd)[:6]
    q = np.array(d.get("_opoly") or
                 [[pt[0] - half[0], pt[1] - half[1]], [pt[0] + half[0], pt[1] - half[1]],
                  [pt[0] + half[0], pt[1] + half[1]], [pt[0] - half[0], pt[1] + half[1]]],
                 np.float32)
    ins, best, bi = None, 0.0, None
    for i in near:
        if cv2.pointPolygonTest(panels[i].astype(np.float32), pt, False) >= 0:
            ins = i
        io = quad_iou(q, panels[i])
        if io > best:
            best, bi = io, i
    j = ins if ins is not None else bi
    d["in_panel"] = ins is not None
    d["iou"] = round(float(best), 3)
    d["panel_code"] = code.get(int(j)) if j is not None else None
    # Khoang cach LUON tinh toi tam pin gan nhat, ke ca khi khong gan duoc ma.
    # Ban cu de None o day, nen 41 loi vua khong co ma vua khong co khoang cach —
    # doi bao tri khong biet no cach tam nao bao xa de di kiem.
    gan_nhat = int(j) if j is not None else int(near[0])
    d["dist_cm"] = round(float(np.sqrt(dd[gan_nhat]) * GSD))
    d["ma_gan_nhat"] = code.get(gan_nhat)
    d.pop("_opoly", None)

ok = sum(d["in_panel"] for d in det)
ma = sum(d["panel_code"] is not None for d in det)
print("\n" + "=" * 60)
print("  Lỗi rơi ĐÚNG trong polygon tấm pin : %d/%d = %.1f%%" % (ok, len(det), 100.0 * ok / len(det)))
print("  Gán được mã tấm pin                : %d/%d = %.1f%%" % (ma, len(det), 100.0 * ma / len(det)))
print("  IoU vết lỗi ↔ tấm pin, trung vị    : %.3f" % np.median([d["iou"] for d in det]))
print("  Lệch tâm, trung vị                 : %.0f cm"
      % np.median([d["dist_cm"] for d in det if d["dist_cm"] is not None]))
print("=" * 60)

json.dump(det, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump([p.tolist() for p in panels], open(args.out_tam, "w"))
print("\n-> %s  (%d lỗi)" % (args.out, len(det)))
print("-> %s  (%d tấm pin)" % (args.out_tam, len(panels)))

print("\nTop dãy nhiều lỗi nhất:")
for c, n in Counter(d["panel_code"].split("-")[0] for d in det if d["panel_code"]).most_common(8):
    print("   dãy %s: %d lỗi" % (c, n))
