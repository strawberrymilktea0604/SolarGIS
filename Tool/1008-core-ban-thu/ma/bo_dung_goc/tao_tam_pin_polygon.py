"""Khoanh lai TAM PIN tren ortho mau, cua so gia lien nhau, toa do quy doi dung."""
import json
import time

import cv2
import numpy as np
import rasterio
from ultralytics import YOLO

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
ortho = rasterio.open(BASE + r"\Thermal2_31M_full_export\ortho.tif")
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424))     # m/px
model = YOLO(r"mo_hinh\best.pt")

SCALE = 2                 # thu nho 2 lan -> 1,91 cm/px, ti le model khoanh dung tam pin
WIN = 1024 * SCALE        # cua so tren ortho goc
STEP = int(WIN * 0.80)    # chong lan 20%

# chi quet vung co loi (+ le rong)
det = json.load(open(BASE + r"\loi_obb4.json", encoding="utf-8")) + \
      json.load(open(BASE + r"\loi_tren_ortho_nhiet.json", encoding="utf-8"))
pc = np.array([(~ortho.transform * (d["lon"], d["lat"])) for d in det])
M = 900
C0 = max(0, int(pc[:, 0].min()) - M); R0 = max(0, int(pc[:, 1].min()) - M)
C1 = min(ortho.width, int(pc[:, 0].max()) + M); R1 = min(ortho.height, int(pc[:, 1].max()) + M)
print(f"vung quet: ({C0},{R0}) -> ({C1},{R1})  = {(C1-C0)*GSD:.0f} x {(R1-R0)*GSD:.0f} m")

t0 = time.time(); polys = []
xs = list(range(C0, C1, STEP)); ys = list(range(R0, R1, STEP))
for iy, y in enumerate(ys):
    for x in xs:
        w = min(WIN, C1 - x); h = min(WIN, R1 - y)
        if w < 400 or h < 400:
            continue
        img = ortho.read(window=rasterio.windows.Window(x, y, w, h))[:3]
        img = np.ascontiguousarray(np.moveaxis(img, 0, -1)[:, :, ::-1])
        small = cv2.resize(img, (w // SCALE, h // SCALE), interpolation=cv2.INTER_AREA)
        r = model.predict(small, imgsz=1024, conf=0.35, max_det=900, verbose=False)[0]
        if r.obb is None or not len(r.obb):
            continue
        # toa do trong 'small' -> nhan SCALE -> cong goc cua so (x,y). Khong co le nao khac.
        P = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2) * SCALE + [x, y]
        # bo hop cham bien cua so (bi cat), se lay tu cua so ke ben
        m = 12 * SCALE
        for p in P:
            if (p[:, 0].min() > x + m and p[:, 0].max() < x + w - m
                    and p[:, 1].min() > y + m and p[:, 1].max() < y + h - m):
                polys.append(p)
    print(f"   hang {iy+1}/{len(ys)}: {len(polys)} tam pin, {time.time()-t0:.0f}s")

print(f"\n{len(polys)} hop tho")

# loc theo kich thuoc that cua tam pin
w = np.array([np.linalg.norm(p[1]-p[0]) for p in polys]) * GSD
h = np.array([np.linalg.norm(p[3]-p[0]) for p in polys]) * GSD
lo, hi = np.sort(np.stack([w, h]), 0)
ok = (lo > 0.6) & (lo < 1.3) & (hi > 1.4) & (hi < 2.3)
polys = [p for p, k in zip(polys, ok) if k]
print(f"{len(polys)} hop dat kich thuoc tam pin (0,6-1,3 x 1,4-2,3 m)")

# khu trung lap giua cac cua so
cen = np.array([p.mean(0) for p in polys])
order = np.argsort(-np.array([cv2.contourArea(p.astype(np.float32)) for p in polys]))
taken = np.zeros(len(polys), bool); keep = []
for i in order:
    if taken[i]:
        continue
    taken |= ((cen - cen[i]) ** 2).sum(1) < 45 ** 2
    keep.append(polys[i])
polys = keep
print(f"{len(polys)} tam pin duy nhat")

w = np.array([np.linalg.norm(p[1]-p[0]) for p in polys]) * GSD
h = np.array([np.linalg.norm(p[3]-p[0]) for p in polys]) * GSD
lo, hi = np.sort(np.stack([w, h]), 0)
print(f"kich thuoc: trung vi {np.median(lo):.2f} x {np.median(hi):.2f} m")
json.dump([p.tolist() for p in polys], open(BASE + r"\tam_pin_polygon.json", "w"))

c0, r0, S = 21000, 6800, 900
img = ortho.read(window=rasterio.windows.Window(c0, r0, S, S))[:3]
img = np.ascontiguousarray(np.moveaxis(img, 0, -1)[:, :, ::-1])
n = 0
for p in polys:
    q = p - [c0, r0]
    if q[:, 0].min() > -50 and q[:, 0].max() < S+50 and q[:, 1].min() > -50 and q[:, 1].max() < S+50:
        cv2.polylines(img, [q.astype(np.int32)], True, (0, 255, 0), 2); n += 1
cv2.imwrite(BASE + r"\kiem_tra_warp\soi_polygon2.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
print(f"ve {n} polygon -> kiem_tra_warp\\soi_polygon2.jpg")
