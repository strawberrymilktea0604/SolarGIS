"""Polygon tam pin co dung kich thuoc tam pin that khong?"""
import json

import cv2
import numpy as np
import rasterio

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
ortho = rasterio.open(BASE + r"\Thermal2_31M_full_export\ortho.tif")
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424))    # m/px
panels = [np.array(p) for p in json.load(open(BASE + r"\tam_pin_polygon.json"))]
print(f"{len(panels)} polygon, GSD {GSD*100:.3f} cm/px")

w = np.array([np.linalg.norm(p[1]-p[0]) for p in panels]) * GSD
h = np.array([np.linalg.norm(p[3]-p[0]) for p in panels]) * GSD
lo, hi = np.sort(np.stack([w, h]), 0)
print(f"kich thuoc polygon: trung vi {np.median(lo):.2f} x {np.median(hi):.2f} m")
print(f"   canh ngan: {np.percentile(lo,[5,50,95]).round(2)}")
print(f"   canh dai : {np.percentile(hi,[5,50,95]).round(2)}")

# chong lan giua cac polygon
cen = np.array([p.mean(0) for p in panels])
from scipy.spatial import cKDTree
tree = cKDTree(cen)
pairs = tree.query_pairs(r=60)
ov = 0
for i, j in list(pairs)[:4000]:
    a = panels[i].astype(np.float32); b = panels[j].astype(np.float32)
    inter, _ = cv2.intersectConvexConvex(a, b)
    if inter / max(cv2.contourArea(a), 1) > 0.25:
        ov += 1
print(f"cap polygon chong lan >25%: {ov} (trong {len(pairs)} cap gan nhau)")

# ve thu mot vung de nhin
c0, r0, S = 21000, 6800, 900
img = ortho.read(window=rasterio.windows.Window(c0, r0, S, S))[:3]
img = np.ascontiguousarray(np.moveaxis(img, 0, -1)[:, :, ::-1])
n = 0
for p in panels:
    q = p - [c0, r0]
    if q[:, 0].min() > -50 and q[:, 0].max() < S+50 and q[:, 1].min() > -50 and q[:, 1].max() < S+50:
        cv2.polylines(img, [q.astype(np.int32)], True, (0, 255, 0), 2)
        n += 1
print(f"ve {n} polygon trong vung thu")
cv2.imwrite(BASE + r"\kiem_tra_warp\soi_polygon.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
print("-> kiem_tra_warp\\soi_polygon.jpg")
