# -*- coding: utf-8 -*-
"""Do BO SOT THAT theo tung nguong conf, bang ghep cap truc tiep (khong qua mAP).

Vi sao can: con so R=0,897 trong bao cao la recall tai DIEM F1 LON NHAT, ma diem
do nam o conf ~0,64 — khong phai nguong ta chay that (0,25). Script chay predict
MOT LUOT o conf 0,03 roi loc lai theo nhieu nguong, nen re.
"""
import glob, json, os
import cv2, numpy as np
from ultralytics import YOLO

import goc  # dua tien trinh ve goc du an  # noqa: F401

BO = r"du_lieu\colab\solar_cls4_nhom"
MODEL = r"mo_hinh\fault_obb_4class.pt"
LOP = ["SingleHotSpot", "MultiHotSpot", "Bypass", "ModuleOpenCircuit"]
IOU_THR = 0.5

def hop(poly):
    x = poly[:, 0]; y = poly[:, 1]
    return np.array([x.min(), y.min(), x.max(), y.max()])

def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    w = max(0, x2-x1); h = max(0, y2-y1)
    it = w*h
    u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - it
    return it/u if u > 0 else 0.0

def doc_gt(anh):
    nhan = anh.replace(os.sep+"images"+os.sep, os.sep+"labels"+os.sep)
    nhan = os.path.splitext(nhan)[0] + ".txt"
    H, W = cv2.imread(anh).shape[:2]
    ra = []
    if not os.path.exists(nhan): return ra
    for d in open(nhan, encoding="utf-8"):
        v = d.split()
        if len(v) < 9: continue
        p = np.array(list(map(float, v[1:9]))).reshape(4, 2) * [W, H]
        ra.append((int(v[0]), hop(p)))
    return ra

anhs = sorted(glob.glob(os.path.join(BO, "test", "images", "*.*")))
print("tap test: %d anh" % len(anhs))
model = YOLO(MODEL)

GT = []; DU = []
for a in anhs:
    GT.append(doc_gt(a))
    r = model.predict(a, conf=0.03, imgsz=640, verbose=False, max_det=300)[0]
    if r.obb is None or len(r.obb) == 0:
        DU.append([]); continue
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    DU.append([(int(c), float(cf), hop(p)) for p, c, cf
               in zip(q, r.obb.cls.cpu().numpy(), r.obb.conf.cpu().numpy())])

tong_gt = sum(len(g) for g in GT)
print("tong doi tuong that: %d\n" % tong_gt)
print("%6s %10s %10s %10s %10s %10s" % ("conf","bat duoc","bo sot","dung lop","box thua","precision"))
print("-"*62)
ket = {}
for C in [0.05,0.10,0.15,0.20,0.25,0.30,0.40,0.50,0.64]:
    bat = sot = dung = thua = 0
    for gts, dus in zip(GT, DU):
        d = sorted([x for x in dus if x[1] >= C], key=lambda x: -x[1])
        dung_roi = [False]*len(gts)
        khop = [None]*len(gts)
        for cls, cf, bb in d:
            tot, ti = -1, 0.0
            for i, (gc, gb) in enumerate(gts):
                if dung_roi[i]: continue
                v = iou(bb, gb)
                if v >= IOU_THR and v > ti: ti, tot = v, i
            if tot >= 0:
                dung_roi[tot] = True; khop[tot] = cls
            else:
                thua += 1
        bat  += sum(dung_roi)
        sot  += len(gts) - sum(dung_roi)
        dung += sum(1 for i,(gc,_) in enumerate(gts) if khop[i] == gc)
    p = bat/max(bat+thua,1)
    ket["%.2f"%C] = dict(bat=bat, sot=sot, dung_lop=dung, thua=thua, precision=p)
    print("%6.2f %9d%s %10d %10d %10d %10.3f"
          % (C, bat, " (%.1f%%)"%(100*bat/tong_gt), sot, dung, thua, p))
json.dump({"tong_gt": tong_gt, "iou": IOU_THR, "theo_nguong": ket},
          open("ket_qua/ket_qua_val/recall_theo_nguong.json","w",encoding="utf-8"), indent=1)
print("\n-> ket_qua_val/recall_theo_nguong.json")
