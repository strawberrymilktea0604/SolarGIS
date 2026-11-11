#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Val model 4 lop tren tap TEST cua bo chia theo nhom chuyen bay.

Tap test chua bao gio duoc dung trong train lan chon epoch -> con so doc lap
hoan toan. Dong thoi do IoU that giua box du doan va box nhan (khac voi IoU
gan tam pin o phan sau).
"""
import json
import os

import numpy as np
from ultralytics import YOLO

MODEL = r"mo_hinh\fault_obb_4class.pt"
BO = r"du_lieu\colab\solar_cls4_nhom"
RA = r"ket_qua\ket_qua_val"
os.makedirs(RA, exist_ok=True)

yaml_moi = os.path.join(RA, "data_test_nhom.yaml")
with open(os.path.join(BO, "data.yaml"), encoding="utf-8") as fh:
    goc = fh.read()
dong = []
for l in goc.splitlines():
    dong.append("path: %s" % BO.replace("\\", "/") if l.strip().startswith("path:") else l)
with open(yaml_moi, "w", encoding="utf-8") as fh:
    fh.write("\n".join(dong))

model = YOLO(MODEL)
kq = model.val(data=yaml_moi, split="test", imgsz=640, batch=8, device="cpu",
               project=RA, name="test_nhom", exist_ok=True, plots=True, verbose=True)

b = kq.box
ten_lop = model.names
lop = {}
for i, ci in enumerate(b.ap_class_index):
    p, r, ap50, ap = b.class_result(i)
    lop[ten_lop[int(ci)]] = {"precision": float(p), "recall": float(r),
                             "mAP50": float(ap50), "mAP50_95": float(ap)}

# mAP tai tung nguong IoU (0.50 .. 0.95) - cho thay model dinh vi box chat den dau
maps_theo_iou = {}
try:
    # b.all_ap co dang (so_lop, 10) tuong ung IoU 0.50:0.05:0.95
    aa = np.array(b.all_ap)
    nguong = np.linspace(0.5, 0.95, 10)
    for j, t in enumerate(nguong):
        maps_theo_iou["mAP@%.2f" % t] = float(aa[:, j].mean())
except Exception as e:
    maps_theo_iou["loi"] = repr(e)

out = {
    "tap": "test (chia theo nhom chuyen bay) - doc lap hoan toan",
    "so_anh": 91,
    "precision": float(b.mp), "recall": float(b.mr),
    "mAP50": float(b.map50), "mAP50_95": float(b.map),
    "theo_lop": lop,
    "mAP_theo_nguong_IoU": maps_theo_iou,
}
with open(os.path.join(RA, "ket_qua_test_4lop.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)

print()
print("=" * 70)
print("TAP TEST (91 anh, chia theo nhom chuyen bay)")
print("=" * 70)
print("%-20s %8s %8s %8s %10s" % ("Lop", "P", "R", "mAP50", "mAP50-95"))
print("-" * 58)
for k, v in lop.items():
    print("%-20s %8.4f %8.4f %8.4f %10.4f"
          % (k, v["precision"], v["recall"], v["mAP50"], v["mAP50_95"]))
print("%-20s %8.4f %8.4f %8.4f %10.4f" % ("TAT CA", b.mp, b.mr, b.map50, b.map))
print()
print("mAP tai tung nguong IoU (do do chat cua box):")
for k, v in maps_theo_iou.items():
    print("   %-10s %s" % (k, ("%.4f" % v) if isinstance(v, float) else v))
