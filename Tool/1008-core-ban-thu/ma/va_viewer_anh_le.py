#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thêm bộ lỗi thứ ba vào so_sanh_model.html: lỗi detect trên ẢNH LẺ.

Viewer đang có hai bộ trong ô chọn MÔ HÌNH:
    - "Model của bạn · OBB 4 lớp"   (284 lỗi, detect trên ortho nhiệt)
    - "Model của thầy · AABB 8 lớp" (211 lỗi, detect trên ortho nhiệt)
Script này thêm:
    - "Ảnh lẻ · OBB 4 lớp"          (detect trên TỪNG ẢNH GỐC rồi chiếu lên ortho)

Để so trực tiếp hai ĐƯỜNG ĐI khác nhau, không phải hai model khác nhau:
  ghép ortho trước → detect sau   vs   detect trước → chiếu sau

Cần có trước:
    py -3.13 ma/quet_loi_anh_le.py     -> loi_tu_anh_le.json

Bộ mới KHÔNG có ảnh cắt (trường o/t) vì dựng ảnh base64 cho 600 lỗi sẽ làm HTML
phình thêm ~40 MB. Ô chi tiết bên phải sẽ trống cho bộ này — đổi lại file không
to thêm. Muốn có ảnh thì dựng lại viewer bằng bo_dung_goc/tao_viewer_data.py.

    py -3.13 ma/va_viewer_anh_le.py
    py -3.13 ma/va_viewer_anh_le.py --hoan-tac
"""
import argparse
import json
import os
import shutil

import numpy as np
import rasterio

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "cong_cu/so_sanh_model.html")
SAO = HTML + ".truoc_anh_le.bak"
NGUON = os.path.join(BASE, "ket_qua/loi_tu_anh_le.json")

ap = argparse.ArgumentParser()
ap.add_argument("--html", default=HTML)
ap.add_argument("--nguon", default=NGUON)
ap.add_argument("--hoan-tac", action="store_true", dest="hoan_tac")
args = ap.parse_args()

if args.hoan_tac:
    if not os.path.exists(SAO):
        raise SystemExit(f"Không có bản sao {SAO} để hoàn tác.")
    shutil.copy2(SAO, args.html)
    print(f"[HOÀN TÁC] đã khôi phục từ {SAO}")
    raise SystemExit

if not os.path.exists(args.nguon):
    raise SystemExit(f"Chưa có {os.path.basename(args.nguon)} — chạy quet_loi_anh_le.py trước.")

src = open(args.html, encoding="utf-8").read()
i = src.find("const DATA = ")
j = src.find(";\nconst sets", i)
if i < 0 or j < 0:
    raise SystemExit("[DỪNG] không tìm thấy khối DATA trong HTML — không ghi gì cả.")
D = json.loads(src[i + len("const DATA = "):j])

if any(s.get("tag") == "anhle" for s in D["sets"]):
    raise SystemExit("Đã vá rồi. Muốn vá lại thì --hoan-tac trước.")

fr = D["frame"]
ortho = rasterio.open(os.path.join(BASE, "du_lieu/Thermal2_31M_full_export", "ortho.tif"))
panels = [np.array(p) for p in json.load(
    open(os.path.join(BASE, "ket_qua/tam_pin_polygon.json")))]
cen = np.array([p.mean(0) for p in panels])

# Mã tấm pin: đánh lại y hệt tao_viewer_data.py để mã trùng với hai bộ kia.
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

items, ins_ok = [], 0
for n, d in enumerate(sorted(det, key=lambda x: -x["conf"])):
    cc, rr = ~ortho.transform * (d["lon"], d["lat"])
    # toạ độ % trong khung viewer — đúng công thức của tinh_lai_khung_viewer.py
    x = (cc - fr["c0"]) / fr["w"] * 100
    y = (rr - fr["r0"]) / fr["h"] * 100
    if not (-2 < x < 102 and -2 < y < 102):
        continue
    dd = (cen[:, 0] - cc) ** 2 + (cen[:, 1] - rr) ** 2
    near = np.argsort(dd)[:6]
    ins = None
    for t in near:
        from cv2 import pointPolygonTest
        if pointPolygonTest(panels[t].astype(np.float32), (float(cc), float(rr)), False) >= 0:
            ins = int(t)
            break
    j2 = ins if ins is not None else int(near[0])
    ins_ok += ins is not None
    items.append({
        "id": n, "cls": d["cls"], "conf": round(d["conf"], 2),
        "lon": round(d["lon"], 8), "lat": round(d["lat"], 8),
        "code": code.get(j2), "iou": 0, "inp": ins is not None,
        "size": f"{d['w_m']:.2f} x {d['h_m']:.2f}",
        "x": round(x, 3), "y": round(y, 3),
        "w": round(d["w_m"] * 100 / GSD / fr["w"] * 100, 4),
        "h": round(d["h_m"] * 100 / GSD / fr["h"] * 100, 4),
        "n_anh": d.get("n", 1),
    })

D["sets"].append({"tag": "anhle", "label": "Ảnh lẻ · OBB 4 lớp",
                  "items": items, "n": len(items), "in_panel": ins_ok})
print(f"[BỘ MỚI] {len(items)} lỗi trong khung, gán đúng tấm {ins_ok} "
      f"({100*ins_ok/max(len(items),1):.1f}%)")

moi = src[:i + len("const DATA = ")] + json.dumps(D, ensure_ascii=False,
                                                  separators=(",", ":")) + src[j:]
if not os.path.exists(SAO):
    shutil.copy2(args.html, SAO)
    print(f"[SAO LƯU] {SAO}")
open(args.html, "w", encoding="utf-8").write(moi)
print(f"[VÁ]      {args.html}  ({len(moi)/1e6:.1f} MB)")
print("\nMở lại HTML — ô MÔ HÌNH có thêm 'Ảnh lẻ · OBB 4 lớp'.")
print("Bộ này không có ảnh cắt ở ô chi tiết (xem docstring).")
