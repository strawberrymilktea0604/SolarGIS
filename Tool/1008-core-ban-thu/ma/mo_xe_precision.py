# -*- coding: utf-8 -*-
"""Precision 0,796 - 70 box thua do la gi?

Phan biet hai thu rat khac nhau ve van hanh:
  A. TRUNG LAP  - box thua nam chong len mot loi THAT (da co box khac ghep roi).
     Khong nguy hiem: khong dan tho di nham cho, va khoi F6 se gom cum lai.
  B. BAO DONG GIA THAT - box thua o cho khong co loi nao.
     Day moi la thu lam tho di kiem tra tam pin lanh.

Neu phan lon la (A) thi precision 0,796 dang bi hieu oan.
"""
import glob
import json
import os

import cv2
import numpy as np
from ultralytics import YOLO

import goc  # dua tien trinh ve goc du an  # noqa: F401

BO = r"du_lieu\colab\solar_cls4_nhom\test"
MODEL = r"mo_hinh\fault_obb_4class.pt"
LOP = ["SingleHotSpot", "MultiHotSpot", "Bypass", "ModuleOpenCircuit"]
CONF = 0.25
IOU_GHEP = 0.5      # nguong ghep cap chinh thuc
IOU_CHAM = 0.10     # cham vao loi that -> coi la trung lap, khong phai bao dong gia


def hop(p):
    return np.array([p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()])


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    it = max(0, x2 - x1) * max(0, y2 - y1)
    u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - it
    return it / u if u > 0 else 0.0


anhs = sorted(glob.glob(os.path.join(BO, "images", "*.*")))
model = YOLO(MODEL)
print("Quet %d anh o conf %.2f ..." % (len(anhs), CONF))

trung_lap, gia_that, bat, tong_gt = [], [], 0, 0
for k, a in enumerate(anhs, 1):
    nhan = os.path.join(BO, "labels",
                        os.path.splitext(os.path.basename(a))[0] + ".txt")
    Hh, Ww = cv2.imread(a).shape[:2]
    GT = []
    if os.path.exists(nhan):
        for d in open(nhan, encoding="utf-8"):
            v = d.split()
            if len(v) >= 9:
                p = np.array(list(map(float, v[1:9]))).reshape(4, 2) * [Ww, Hh]
                GT.append((int(v[0]), hop(p)))
    tong_gt += len(GT)

    r = model.predict(a, conf=CONF, imgsz=640, verbose=False, max_det=300)[0]
    DU = []
    if r.obb is not None and len(r.obb):
        q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
        DU = [(int(c), float(cf), hop(p)) for p, c, cf
              in zip(q, r.obb.cls.cpu().numpy(), r.obb.conf.cpu().numpy())]
    DU.sort(key=lambda x: -x[1])

    da = [False] * len(GT)
    for cls, cf, b in DU:
        ti, tv = -1, 0.0
        for j, (gc, gb) in enumerate(GT):
            if da[j]:
                continue
            v = iou(b, gb)
            if v >= IOU_GHEP and v > tv:
                tv, ti = v, j
        if ti >= 0:
            da[ti] = True
            bat += 1
            continue
        # box thua -> no co cham vao loi that nao khong (ke ca da bi ghep)?
        cham = max([iou(b, gb) for _, gb in GT], default=0.0)
        ghi = {"anh": os.path.basename(a), "lop": LOP[cls], "conf": round(cf, 3),
               "iou_voi_loi_that": round(cham, 3)}
        (trung_lap if cham >= IOU_CHAM else gia_that).append(ghi)
    if k % 20 == 0:
        print("   ...%d/%d anh" % (k, len(anhs)))

thua = len(trung_lap) + len(gia_that)
print()
print("=" * 68)
print("MO XE %d BOX THUA (o nguong conf %.2f)" % (thua, CONF))
print("=" * 68)
print("  A. Trùng lặp — chồng lên lỗi THẬT (IoU >= %.2f)  : %3d  (%.1f %%)"
      % (IOU_CHAM, len(trung_lap), 100.0*len(trung_lap)/max(thua, 1)))
print("  B. Báo động giả thật — chỗ KHÔNG có lỗi          : %3d  (%.1f %%)"
      % (len(gia_that), 100.0*len(gia_that)/max(thua, 1)))
print()
p_tho = bat / float(bat + thua)
p_that = bat / float(bat + len(gia_that))
print("  Precision tính thô (mọi box thừa đều là rác) : %.3f" % p_tho)
print("  Precision nếu bỏ phần trùng lặp              : %.3f" % p_that)
print()
print("  Trùng lặp không làm thợ đi nhầm chỗ, và khối F6 sẽ gom cụm lại.")
print("  Con số đáng lo là B: %d báo động giả trên %d lỗi thật = %.1f %%"
      % (len(gia_that), tong_gt, 100.0*len(gia_that)/tong_gt))

if gia_that:
    print()
    print("  10 báo động giả tin cậy cao nhất (đáng soi tay):")
    for x in sorted(gia_that, key=lambda z: -z["conf"])[:10]:
        print("     %-46s %-14s conf %.3f" % (x["anh"][:46], x["lop"], x["conf"]))

json.dump({"nguong_conf": CONF, "tong_gt": tong_gt, "bat_duoc": bat,
           "box_thua": thua, "trung_lap": trung_lap, "bao_dong_gia": gia_that,
           "precision_tho": p_tho, "precision_bo_trung_lap": p_that},
          open("ket_qua/ket_qua_val/mo_xe_precision.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("-> ket_qua_val/mo_xe_precision.json")
