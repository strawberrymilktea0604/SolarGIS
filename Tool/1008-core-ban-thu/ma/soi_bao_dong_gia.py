# -*- coding: utf-8 -*-
"""Cat anh cac 'bao dong gia' tin cay cao ra xem: model bia, hay nguoi cham
nhan bo sot?

Ve box do = du doan bi tinh la bao dong gia. Box xanh = nhan that co san.
Neu trong box do co vet nong ro rang -> nhan thieu, khong phai model sai.
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
CONF = 0.25
IOU_GHEP = 0.5
IOU_CHAM = 0.10
SO_CA = 6


def hop(p):
    return np.array([p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()])


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    it = max(0, x2-x1) * max(0, y2-y1)
    u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - it
    return it/u if u > 0 else 0.0


d = json.load(open("ket_qua/ket_qua_val/mo_xe_precision.json", encoding="utf-8"))
top = sorted(d["bao_dong_gia"], key=lambda z: -z["conf"])[:SO_CA]
model = YOLO(MODEL)

o = []
for t in top:
    a = os.path.join(BO, "images", t["anh"])
    img = cv2.imread(a)
    Hh, Ww = img.shape[:2]

    nhan = os.path.join(BO, "labels", os.path.splitext(t["anh"])[0] + ".txt")
    GT = []
    if os.path.exists(nhan):
        for l in open(nhan, encoding="utf-8"):
            v = l.split()
            if len(v) >= 9:
                GT.append(hop(np.array(list(map(float, v[1:9]))).reshape(4, 2)*[Ww, Hh]))

    r = model.predict(a, conf=CONF, imgsz=640, verbose=False, max_det=300)[0]
    DU = []
    if r.obb is not None and len(r.obb):
        q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
        DU = [(float(cf), hop(p)) for p, cf
              in zip(q, r.obb.conf.cpu().numpy())]
    DU.sort(key=lambda x: -x[0])

    # tim lai dung box bao dong gia nay (khop theo conf)
    bb = None
    for cf, b in DU:
        if abs(cf - t["conf"]) < 1e-3:
            bb = b
            break
    if bb is None:
        continue

    # dem vien quanh anh -> cat quanh box KHONG bi kep ve mep
    n = 90
    P = n + 10
    pad = cv2.copyMakeBorder(img, P, P, P, P, cv2.BORDER_CONSTANT, value=(25, 25, 25))
    for g in GT:
        cv2.rectangle(pad, (int(g[0])+P, int(g[1])+P), (int(g[2])+P, int(g[3])+P),
                      (0, 230, 0), 2)
    cv2.rectangle(pad, (int(bb[0])+P, int(bb[1])+P), (int(bb[2])+P, int(bb[3])+P),
                  (0, 40, 255), 2)

    cx, cy = (bb[0]+bb[2])/2 + P, (bb[1]+bb[3])/2 + P
    cut = pad[int(cy-n):int(cy+n), int(cx-n):int(cx+n)]
    cut = cv2.resize(cut, (330, 330), interpolation=cv2.INTER_LANCZOS4)
    cv2.rectangle(cut, (0, 0), (329, 26), (20, 20, 20), -1)
    cv2.putText(cut, "conf %.2f  %s" % (t["conf"], t["anh"][-11:-6]), (7, 19),
                cv2.FONT_HERSHEY_SIMPLEX, .52, (255, 255, 255), 1)
    o.append(cut)

if o:
    while len(o) % 3:
        o.append(np.zeros_like(o[0]))
    hang = [np.hstack(o[i:i+3]) for i in range(0, len(o), 3)]
    bang = np.vstack(hang)
    cv2.imwrite("tai_lieu/_bao_dong_gia.png", bang)
    print("Da luu _bao_dong_gia.png  (%d ca)" % len(top))
    print("do = du doan bi tinh bao dong gia | xanh = nhan that co san")
