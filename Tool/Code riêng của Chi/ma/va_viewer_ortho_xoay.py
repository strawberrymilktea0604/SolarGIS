#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thêm bộ lỗi thứ tư vào so_sanh_model.html: detect TRÊN ORTHO, ô ảnh XOAY 270°.

Viewer đang có ba bộ trong ô chọn MÔ HÌNH:
    - "Model của bạn · OBB 4 lớp"   (284) detect trên ortho nhiệt, ô BẮC-LÊN
    - "Model của thầy · AABB 8 lớp" (211) detect trên ortho nhiệt, ô BẮC-LÊN
    - "Ảnh lẻ · OBB 4 lớp"          (603) detect trên ảnh gốc rồi chiếu
Script này thêm:
    - "Ortho xoay 270° · OBB 4 lớp" (463) detect trên ortho, ô xoay trước khi vào model

VÌ SAO CÓ BỘ NÀY. Drone bay yaw ~-89° nên ortho bắc-lên là cảnh xoay ~90° so với
mọi ảnh model từng train. Xoay ô lại thì recall nhảy 53,1% -> 82,7%
(`ma/thu_detect_tren_ortho.py`, mẫu 2x2: 0° 53,1 · 90° 81,4 · 180° 56,2 · 270° 82,7).
Đặt cạnh bộ "Model của bạn" trong cùng viewer là thấy ngay chênh lệch nằm ở đâu.

Chấm trên nhãn tay 511 tấm: bộ này P 0,962 · R 0,860 · F1 0,908, so với nhánh
ảnh lẻ P 0,865 · R 0,968 · F1 0,914. Nó đổi recall lấy precision.

Cần có trước:
    py -3.13 ma/thu_detect_tren_ortho.py --xoay 270 --bo-qua-C --bo-qua-B \
             --out ket_qua/detect_tren_ortho_xoay270.json
    py -3.13 ma/gan_tam_pin_4lop.py --nguon ket_qua/detect_tren_ortho_xoay270_ds_phat_hien.json \
             --out ket_qua/loi_ortho_xoay270_cuoi.json

Giống `va_viewer_anh_le.py`: bộ mới KHÔNG có ảnh cắt (trường o/t), ô chi tiết bên
phải sẽ trống, đổi lại HTML không phình thêm ~40 MB.

    py -3.13 ma/va_viewer_ortho_xoay.py
    py -3.13 ma/va_viewer_ortho_xoay.py --hoan-tac
"""
import argparse
import json
import os
import shutil

import numpy as np
import rasterio
from cv2 import pointPolygonTest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "cong_cu/so_sanh_model.html")
SAO = HTML + ".truoc_ortho_xoay.bak"
NGUON = os.path.join(BASE, "ket_qua/loi_ortho_xoay270_cuoi.json")
TAG = "orthoxoay"

ap = argparse.ArgumentParser()
ap.add_argument("--html", default=HTML)
ap.add_argument("--nguon", default=NGUON)
ap.add_argument("--nhan", default="Ortho xoay 270° · OBB 4 lớp")
ap.add_argument("--hoan-tac", action="store_true", dest="hoan_tac")
args = ap.parse_args()

if args.hoan_tac:
    if not os.path.exists(SAO):
        raise SystemExit(f"Không có bản sao {SAO} để hoàn tác.")
    shutil.copy2(SAO, args.html)
    print(f"[HOÀN TÁC] đã khôi phục từ {SAO}")
    raise SystemExit

if not os.path.exists(args.nguon):
    raise SystemExit(f"Chưa có {os.path.basename(args.nguon)} — xem docstring.")

src = open(args.html, encoding="utf-8").read()
i = src.find("const DATA = ")
j = src.find(";\nconst sets", i)
if i < 0 or j < 0:
    raise SystemExit("[DỪNG] không tìm thấy khối DATA trong HTML — không ghi gì cả.")
D = json.loads(src[i + len("const DATA = "):j])

if any(s.get("tag") == TAG for s in D["sets"]):
    raise SystemExit("Đã vá rồi. Muốn vá lại thì --hoan-tac trước.")

fr = D["frame"]
ortho = rasterio.open(os.path.join(BASE, "du_lieu/Thermal2_31M_full_export", "ortho.tif"))
panels = [np.array(p) for p in json.load(
    open(os.path.join(BASE, "ket_qua/tam_pin_polygon.json")))]
cen = np.array([p.mean(0) for p in panels])

# Mã tấm pin: đánh lại y hệt tao_viewer_data.py / va_viewer_anh_le.py để mã trùng
# với ba bộ kia. Sửa một bên là lệch mã giữa các bộ trong cùng viewer.
rid = np.zeros(len(panels), int)
cur, last = 0, None
for k in np.argsort(cen[:, 1]):
    if last is not None and cen[k, 1] - last > 55:
        cur += 1
    rid[k] = cur
    last = cen[k, 1]
code = {}
for r in range(cur + 1):
    idx = np.where(rid == r)[0]
    for k, t in enumerate(idx[np.argsort(cen[idx, 0])], 1):
        code[int(t)] = f"D{r+1:02d}-T{k:03d}"

det = json.load(open(args.nguon, encoding="utf-8"))
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100

items, ins_ok, ngoai_khung = [], 0, 0
for n, d in enumerate(sorted(det, key=lambda x: -x["conf"])):
    cc, rr = ~ortho.transform * (d["lon"], d["lat"])
    x = (cc - fr["c0"]) / fr["w"] * 100
    y = (rr - fr["r0"]) / fr["h"] * 100
    if not (-2 < x < 102 and -2 < y < 102):
        ngoai_khung += 1
        continue
    dd = (cen[:, 0] - cc) ** 2 + (cen[:, 1] - rr) ** 2
    near = np.argsort(dd)[:6]
    ins = None
    for t in near:
        if pointPolygonTest(panels[t].astype(np.float32), (float(cc), float(rr)), False) >= 0:
            ins = int(t)
            break
    j2 = ins if ins is not None else int(near[0])
    ins_ok += ins is not None
    items.append({
        "id": n, "cls": d["cls"], "conf": round(d["conf"], 2),
        "lon": round(d["lon"], 8), "lat": round(d["lat"], 8),
        "code": code.get(j2), "iou": d.get("iou", 0), "inp": ins is not None,
        "size": f"{d['w_m']:.2f} x {d['h_m']:.2f}",
        "x": round(x, 3), "y": round(y, 3),
        "w": round(d["w_m"] * 100 / GSD / fr["w"] * 100, 4),
        "h": round(d["h_m"] * 100 / GSD / fr["h"] * 100, 4),
        "n_anh": 1,          # quét trên ortho thì mỗi lỗi chỉ tồn tại một lần
    })

D["sets"].append({"tag": TAG, "label": args.nhan,
                  "items": items, "n": len(items), "in_panel": ins_ok})
print(f"[BỘ MỚI] {len(items)} lỗi trong khung (bỏ {ngoai_khung} ngoài khung), "
      f"rơi trong tấm {ins_ok} ({100*ins_ok/max(len(items),1):.1f}%)")

moi = src[:i + len("const DATA = ")] + json.dumps(D, ensure_ascii=False,
                                                  separators=(",", ":")) + src[j:]
if not os.path.exists(SAO):
    shutil.copy2(args.html, SAO)
    print(f"[SAO LƯU] {SAO}")
open(args.html, "w", encoding="utf-8").write(moi)
print(f"[VÁ]      {args.html}  ({len(moi)/1e6:.1f} MB)")
print(f"\nMở lại HTML — ô MÔ HÌNH có thêm '{args.nhan}'.")
print("Đặt cạnh 'Model của bạn · OBB 4 lớp' (cùng model, ô bắc-lên) để thấy chênh lệch.")
