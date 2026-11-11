# -*- coding: utf-8 -*-
"""Vi du cu the tren MOT anh: nhan that, du doan, va cach ghep cap.

Muc dich: cho thay vi sao khong the chi DEM so luong. Phai kiem tra tung du
doan co trung vi tri voi nhan khong (IoU >= 0.5) thi moi tinh la bat duoc.
"""
import glob
import os

import cv2
import numpy as np
from ultralytics import YOLO

BO = r"du_lieu\colab\solar_cls4_nhom\test"
MODEL = r"mo_hinh\fault_obb_4class.pt"
LOP = ["SingleHotSpot", "MultiHotSpot", "Bypass", "ModuleOpenCircuit"]
CONF = 0.25
IOU_THR = 0.5


def hop(poly):
    return np.array([poly[:, 0].min(), poly[:, 1].min(),
                     poly[:, 0].max(), poly[:, 1].max()])


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    it = max(0, x2 - x1) * max(0, y2 - y1)
    u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - it
    return it / u if u > 0 else 0.0


# chon anh co nhieu doi tuong de vi du de thay
anhs = sorted(glob.glob(os.path.join(BO, "images", "*.*")))
tot, so = None, 0
for a in anhs:
    n = os.path.join(BO, "labels", os.path.splitext(os.path.basename(a))[0] + ".txt")
    k = sum(1 for l in open(n, encoding="utf-8") if l.strip()) if os.path.exists(n) else 0
    if k > so:
        tot, so = a, k

print("Anh vi du: %s  (%d nhan that)" % (os.path.basename(tot), so))
H, W = cv2.imread(tot).shape[:2]
print("Kich thuoc anh: %d x %d px\n" % (W, H))

# --- nhan that ---
nhan = os.path.join(BO, "labels", os.path.splitext(os.path.basename(tot))[0] + ".txt")
GT = []
for d in open(nhan, encoding="utf-8"):
    v = d.split()
    if len(v) < 9:
        continue
    p = np.array(list(map(float, v[1:9]))).reshape(4, 2) * [W, H]
    GT.append((int(v[0]), hop(p)))

print("=" * 72)
print("BUOC 1 - NHAN THAT (nguoi cham tay, doc tu file .txt)")
print("=" * 72)
for i, (c, b) in enumerate(GT):
    print("  nhan #%d  %-16s tam (%4.0f,%4.0f)  kich thuoc %.0fx%.0f px"
          % (i, LOP[c], (b[0]+b[2])/2, (b[1]+b[3])/2, b[2]-b[0], b[3]-b[1]))

# --- du doan ---
r = YOLO(MODEL).predict(tot, conf=CONF, imgsz=640, verbose=False, max_det=300)[0]
DU = []
if r.obb is not None and len(r.obb):
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    DU = [(int(c), float(cf), hop(p)) for p, c, cf
          in zip(q, r.obb.cls.cpu().numpy(), r.obb.conf.cpu().numpy())]
DU.sort(key=lambda x: -x[1])

print()
print("=" * 72)
print("BUOC 2 - MODEL DU DOAN (o nguong conf %.2f)" % CONF)
print("=" * 72)
for i, (c, cf, b) in enumerate(DU):
    print("  du doan #%d  %-16s conf %.3f  tam (%4.0f,%4.0f)"
          % (i, LOP[c], cf, (b[0]+b[2])/2, (b[1]+b[3])/2))

print()
print("Chi DEM thoi: %d nhan that, %d du doan." % (len(GT), len(DU)))
print("-> Chua noi len dieu gi. Phai xem tung du doan co TRUNG VI TRI khong.")

# --- ghep cap ---
print()
print("=" * 72)
print("BUOC 3 - GHEP CAP: duyet du doan theo conf giam dan, IoU >= %.1f" % IOU_THR)
print("        moi nhan chi duoc ghep MOT lan")
print("=" * 72)

da_ghep = [False] * len(GT)
khop = [None] * len(GT)
thua = []
for i, (c, cf, b) in enumerate(DU):
    tot_i, tot_v = -1, 0.0
    for j, (gc, gb) in enumerate(GT):
        if da_ghep[j]:
            continue
        v = iou(b, gb)
        if v >= IOU_THR and v > tot_v:
            tot_v, tot_i = v, j
    if tot_i >= 0:
        da_ghep[tot_i] = True
        khop[tot_i] = c
        ok = "dung lop" if c == GT[tot_i][0] else "SAI LOP (that la %s)" % LOP[GT[tot_i][0]]
        print("  du doan #%d  ->  nhan #%d   IoU %.3f   %s" % (i, tot_i, tot_v, ok))
    else:
        thua.append(i)
        print("  du doan #%d  ->  KHONG khop nhan nao  = BOX THUA (bao dong gia)" % i)

sot = [j for j in range(len(GT)) if not da_ghep[j]]
for j in sot:
    print("  nhan #%d     ->  KHONG du doan nao bat duoc  = BO SOT" % j)

bat = sum(da_ghep)
dung = sum(1 for j in range(len(GT)) if khop[j] == GT[j][0])
print()
print("=" * 72)
print("BUOC 4 - CONG SO TREN ANH NAY")
print("=" * 72)
print("  bat duoc      %d/%d" % (bat, len(GT)))
print("  bo sot        %d" % len(sot))
print("  box thua      %d" % len(thua))
print("  dung ca lop   %d/%d" % (dung, len(GT)))
print()
print("  recall    = bat / tong nhan that = %d/%d = %.3f" % (bat, len(GT), bat/len(GT)))
print("  precision = bat / tong du doan   = %d/%d = %.3f"
      % (bat, bat+len(thua), bat/max(bat+len(thua), 1)))
print()
print("Lam y het cho ca 91 anh roi cong lai -> ra 273/280 = 97,5%")
