# -*- coding: utf-8 -*-
"""51 'bao dong gia' co dau hieu nhiet giong loi that khong?

Cach do: voi moi box, lay do sang lon nhat ben trong tru di do sang nen cua
vung xung quanh. Anh nhiet da to mau (inferno) nen cang sang = cang nong.

  - Neu bao dong gia co do troi nhiet TUONG DUONG nhan that
    -> nhieu kha nang nhan bi bo sot, khong phai model bia.
  - Neu troi nhiet ~0 -> model bat nham that.

So sanh voi mot nhom doi chung: cac o lay NGAU NHIEN tren tam pin (khong loi).
"""
import glob
import json
import os
import random

import cv2
import numpy as np

BO = r"du_lieu\colab\solar_cls4_nhom\test"


def hop(p):
    return np.array([p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()])


def troi_nhiet(xam, b):
    """Do sang lon nhat trong box tru trung vi cua vanh xung quanh."""
    x1, y1, x2, y2 = [int(v) for v in b]
    H, W = xam.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, x2), min(H, y2)
    if x2 - x1 < 3 or y2 - y1 < 3:
        return None
    trong = xam[y1:y2, x1:x2]
    m = 26
    ox1, oy1 = max(0, x1-m), max(0, y1-m)
    ox2, oy2 = min(W, x2+m), min(H, y2+m)
    ngoai = xam[oy1:oy2, ox1:ox2].copy().astype(float)
    ngoai[y1-oy1:y2-oy1, x1-ox1:x2-ox1] = np.nan
    nen = np.nanmedian(ngoai)
    if np.isnan(nen):
        return None
    return float(np.percentile(trong, 99) - nen)


d = json.load(open("ket_qua/ket_qua_val/mo_xe_precision.json", encoding="utf-8"))
gia = d["bao_dong_gia"]

# gom box bao dong gia theo anh de doc anh mot lan
theo_anh = {}
for g in gia:
    theo_anh.setdefault(g["anh"], []).append(g)

# can toa do box -> chay lai model (chi tren cac anh co bao dong gia)
from ultralytics import YOLO

import goc  # dua tien trinh ve goc du an  # noqa: F401
model = YOLO(r"mo_hinh\fault_obb_4class.pt")

v_gia, v_that, v_ngau = [], [], []
random.seed(7)

for ten, ds in theo_anh.items():
    a = os.path.join(BO, "images", ten)
    img = cv2.imread(a)
    xam = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = xam.shape

    # nhan that
    nhan = os.path.join(BO, "labels", os.path.splitext(ten)[0] + ".txt")
    GT = []
    if os.path.exists(nhan):
        for l in open(nhan, encoding="utf-8"):
            v = l.split()
            if len(v) >= 9:
                GT.append(hop(np.array(list(map(float, v[1:9]))).reshape(4, 2)*[W, H]))
    for g in GT:
        r = troi_nhiet(xam, g)
        if r is not None:
            v_that.append(r)

    # box bao dong gia (khop lai theo conf)
    res = model.predict(a, conf=0.25, imgsz=640, verbose=False, max_det=300)[0]
    if res.obb is None or not len(res.obb):
        continue
    q = res.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    cfs = res.obb.conf.cpu().numpy()
    for g in ds:
        for p, cf in zip(q, cfs):
            if abs(float(cf) - g["conf"]) < 1e-3:
                r = troi_nhiet(xam, hop(p))
                if r is not None:
                    v_gia.append(r)
                break

    # doi chung: o ngau nhien cung kich thuoc, tren anh, khong trung nhan
    for _ in range(4):
        w, h = 40, 75
        x = random.randint(0, W-w-1)
        y = random.randint(0, H-h-1)
        b = np.array([x, y, x+w, y+h])
        if GT and max((min(b[2], g[2])-max(b[0], g[0])) > 0 and
                      (min(b[3], g[3])-max(b[1], g[1])) > 0 for g in GT):
            continue
        r = troi_nhiet(xam, b)
        if r is not None:
            v_ngau.append(r)

v_gia = np.array(v_gia); v_that = np.array(v_that); v_ngau = np.array(v_ngau)
print("=" * 66)
print("DO TROI NHIET (do sang dinh trong box - nen xung quanh)")
print("=" * 66)
print("%-28s %6s %8s %8s %8s" % ("Nhom", "so o", "trung vi", "TB", "P25"))
print("-" * 66)
for ten, v in [("Nhan that (nguoi cham)", v_that),
               ("'Bao dong gia' cua model", v_gia),
               ("O ngau nhien (doi chung)", v_ngau)]:
    if len(v):
        print("%-28s %6d %8.1f %8.1f %8.1f"
              % (ten, len(v), np.median(v), v.mean(), np.percentile(v, 25)))
print()
if len(v_gia) and len(v_that) and len(v_ngau):
    print("Doc ket qua:")
    print("  - Nhan that troi %.1f, o ngau nhien troi %.1f"
          % (np.median(v_that), np.median(v_ngau)))
    print("  - 'Bao dong gia' troi %.1f" % np.median(v_gia))
    if np.median(v_gia) > (np.median(v_that) + np.median(v_ngau)) / 2:
        print("  => Gan nhom NHAN THAT hon nhom ngau nhien.")
        print("     -> phan lon la loi CO THAT ma nguoi cham bo sot,")
        print("        khong phai model bia ra.")
    else:
        print("  => Gan nhom NGAU NHIEN hon.")
        print("     -> model that su bat nham.")
    cao = (v_gia >= np.percentile(v_that, 25)).sum()
    print()
    print("  So 'bao dong gia' co troi nhiet >= P25 cua nhan that: %d/%d = %.0f %%"
          % (cao, len(v_gia), 100.0*cao/len(v_gia)))

json.dump({"troi_nhiet_nhan_that": v_that.tolist(),
           "troi_nhiet_bao_dong_gia": v_gia.tolist(),
           "troi_nhiet_ngau_nhien": v_ngau.tolist()},
          open("ket_qua/ket_qua_val/troi_nhiet.json", "w"), indent=1)
