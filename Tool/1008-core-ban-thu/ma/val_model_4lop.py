#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Val model fault_obb_4class.pt tren nhan that.

Chay tren HAI bo du lieu de thay chenh lech:
  - solar_cls4_nhom            : chia theo NHOM chuyen bay  -> con so THAT
  - solar_cls4_final_ngaunhien : chia NGAU NHIEN tung anh   -> con so CAO GIA
    (chinh data.yaml cua bo nay canh bao: cung mot tam pin vat ly nam o
     ca train lan val vi khung anh drone chong lan nhau)

Model duoc train tren bo ngau nhien, nen diem tren bo do la diem tu cham
tren du lieu no da thay -> khong dung de bao cao.
"""
import json
import os
import shutil
import sys

from ultralytics import YOLO

MODEL = r"mo_hinh\fault_obb_4class.pt"
GOC = r"du_lieu\colab"
RA = r"ket_qua\ket_qua_val"

BO = [
    ("solar_cls4_nhom", "Chia theo NHOM chuyen bay (con so THAT)"),
    ("solar_cls4_final_ngaunhien", "Chia NGAU NHIEN (cao gia - model da thay du lieu nay)"),
]

os.makedirs(RA, exist_ok=True)
tong = {}

for ten, mo_ta in BO:
    thu_muc = os.path.join(GOC, ten)
    if not os.path.isdir(thu_muc):
        print("BO QUA (khong thay): %s" % thu_muc)
        continue

    # data.yaml goc tro toi duong dan tren Colab -> viet lai cho may nay
    yaml_moi = os.path.join(RA, "data_%s.yaml" % ten)
    with open(os.path.join(thu_muc, "data.yaml"), encoding="utf-8") as fh:
        noi_dung = fh.read()
    dong_moi = []
    for dong in noi_dung.splitlines():
        if dong.strip().startswith("path:"):
            dong_moi.append("path: %s" % thu_muc.replace("\\", "/"))
        else:
            dong_moi.append(dong)
    with open(yaml_moi, "w", encoding="utf-8") as fh:
        fh.write("\n".join(dong_moi))

    print()
    print("=" * 78)
    print("VAL tren %s" % ten)
    print("  %s" % mo_ta)
    print("=" * 78)

    model = YOLO(MODEL)
    kq = model.val(
        data=yaml_moi,
        split="val",
        imgsz=640,
        batch=8,
        device="cpu",
        project=RA,
        name="val_%s" % ten,
        exist_ok=True,
        plots=True,
        verbose=True,
    )

    b = kq.box
    ten_lop = model.names
    lop = {}
    for i, ci in enumerate(b.ap_class_index):
        p, r, ap50, ap = b.class_result(i)
        lop[ten_lop[int(ci)]] = {
            "precision": float(p),
            "recall": float(r),
            "mAP50": float(ap50),
            "mAP50_95": float(ap),
        }

    tong[ten] = {
        "mo_ta": mo_ta,
        "precision": float(b.mp),
        "recall": float(b.mr),
        "mAP50": float(b.map50),
        "mAP50_95": float(b.map),
        "theo_lop": lop,
    }

    print()
    print("KET QUA TONG: P=%.4f  R=%.4f  mAP50=%.4f  mAP50-95=%.4f"
          % (b.mp, b.mr, b.map50, b.map))

with open(os.path.join(RA, "ket_qua_val_4lop.json"), "w", encoding="utf-8") as fh:
    json.dump(tong, fh, ensure_ascii=False, indent=1)

print()
print("=" * 78)
print("SO SANH HAI BO")
print("=" * 78)
hdr = ["Bo du lieu", "P", "R", "mAP50", "mAP50-95"]
print("%-30s %8s %8s %8s %10s" % tuple(hdr))
print("-" * 68)
for ten, d in tong.items():
    print("%-30s %8.4f %8.4f %8.4f %10.4f"
          % (ten, d["precision"], d["recall"], d["mAP50"], d["mAP50_95"]))

print()
print("Da luu: %s" % os.path.join(RA, "ket_qua_val_4lop.json"))
