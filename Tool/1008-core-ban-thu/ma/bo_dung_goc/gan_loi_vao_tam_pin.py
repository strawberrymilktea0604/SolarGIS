"""Gan 211 loi vao tam pin tren ortho mau + danh ma day/tam."""
import json
import time

import cv2
import numpy as np
import rasterio
from ultralytics import YOLO

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
EXP = BASE + r"\Thermal2_31M_full_export"
SCALE = 2                      # ti le dung de best.pt khoanh TAM PIN (khong phai cell)
TILE = 1024

t0 = time.time()
det = json.load(open(BASE + r"\loi_tren_ortho_nhiet.json", encoding="utf-8"))
ortho = rasterio.open(EXP + r"\ortho.tif")
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
model = YOLO(r"mo_hinh\best.pt")

# toa do loi -> pixel ortho mau
for d in det:
    c, r = ~ortho.transform * (d["lon"], d["lat"])
    d["ocol"], d["orow"] = float(c), float(r)

# ---------- quet tam pin tren cac o co loi ----------
side = TILE * SCALE
tiles = sorted({(int(d["ocol"] // side), int(d["orow"] // side)) for d in det})
print(f"[F7] {len(det)} loi nam trong {len(tiles)} o {side}px, quet tam pin...")

panels = []
for n, (tx, ty) in enumerate(tiles, 1):
    c0 = max(0, min(tx * side - side // 2, ortho.width - side))
    r0 = max(0, min(ty * side - side // 2, ortho.height - side))
    img = ortho.read(window=rasterio.windows.Window(c0, r0, side, side))[:3]
    img = np.ascontiguousarray(np.moveaxis(img, 0, -1)[:, :, ::-1])
    small = cv2.resize(img, (TILE, TILE), interpolation=cv2.INTER_AREA)
    res = model.predict(small, imgsz=TILE, conf=0.35, max_det=1000, verbose=False)[0]
    if res.obb is not None and len(res.obb):
        panels += list(res.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2) * SCALE + [c0, r0])
    if n % 5 == 0:
        print(f"   ...{n}/{len(tiles)} o, {len(panels)} tam pin, {time.time()-t0:.0f}s")

# khu trung lap tam pin giua cac o
cen = np.array([p.mean(0) for p in panels])
keep, taken = [], np.zeros(len(panels), bool)
order = np.argsort(-np.array([cv2.contourArea(p.astype(np.float32)) for p in panels]))
for i in order:
    if taken[i]:
        continue
    d2 = ((cen - cen[i]) ** 2).sum(1)
    taken |= d2 < (40 ** 2)
    keep.append(panels[i])
panels = keep
cen = np.array([p.mean(0) for p in panels])
print(f"[F7] {len(panels)} tam pin duy nhat, {time.time()-t0:.0f}s")

# ---------- danh ma day / tam ----------
# day = nhom theo hang (toa do row), tam = thu tu theo cot trong day
rows_sorted = np.argsort(cen[:, 1])
row_id = np.zeros(len(panels), int)
cur, last = 0, None
for i in rows_sorted:
    if last is not None and cen[i, 1] - last > 55:      # ~0,5 m -> sang day moi
        cur += 1
    row_id[i] = cur
    last = cen[i, 1]
code = {}
for rid in range(cur + 1):
    idx = np.where(row_id == rid)[0]
    for k, i in enumerate(idx[np.argsort(cen[idx, 0])], 1):
        code[i] = f"D{rid+1:02d}-T{k:03d}"
print(f"[F7] {cur+1} day pin")


def quad_iou(a, b):
    a = np.asarray(a, np.float32); b = np.asarray(b, np.float32)
    A, B = cv2.contourArea(a), cv2.contourArea(b)
    if A <= 0 or B <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(a, b)
    return inter / (A + B - inter)


# ---------- gan ----------
half_w = np.array([[d["w_m"], d["h_m"]] for d in det]).mean(0) / 2 / (GSD / 100)
ok = 0
for d in det:
    pt = (d["ocol"], d["orow"])
    dd = ((cen[:, 0] - pt[0]) ** 2 + (cen[:, 1] - pt[1]) ** 2)
    near = np.argsort(dd)[:6]
    ins, best, bi = None, 0.0, None
    q = np.array([[d["ocol"] - half_w[0], d["orow"] - half_w[1]],
                  [d["ocol"] + half_w[0], d["orow"] - half_w[1]],
                  [d["ocol"] + half_w[0], d["orow"] + half_w[1]],
                  [d["ocol"] - half_w[0], d["orow"] + half_w[1]]], np.float32)
    for i in near:
        if cv2.pointPolygonTest(panels[i].astype(np.float32), pt, False) >= 0:
            ins = i
        io = quad_iou(q, panels[i])
        if io > best:
            best, bi = io, i
    j = ins if ins is not None else bi
    d["in_panel"] = ins is not None
    d["iou"] = round(float(best), 3)
    d["panel_code"] = code.get(int(j)) if j is not None else None
    d["dist_cm"] = round(float(np.sqrt(dd[j]) * GSD)) if j is not None else None
    ok += d["in_panel"]

print(f"\n{'='*58}")
print(f"  Loi roi DUNG trong polygon tam pin: {ok}/{len(det)} = {100*ok/len(det):.0f}%")
print(f"  IoU trung vi: {np.median([d['iou'] for d in det]):.2f}")
print(f"  Co ma tam pin: {sum(d['panel_code'] is not None for d in det)}/{len(det)}")
print("=" * 58)

json.dump(det, open(BASE + r"\loi_tren_ortho_nhiet.json", "w"), indent=1)
json.dump([p.tolist() for p in panels], open(BASE + r"\tam_pin_polygon.json", "w"))

from collections import Counter
print("\nTop day pin nhieu loi nhat:")
for c, n in Counter(d["panel_code"].split("-")[0] for d in det if d["panel_code"]).most_common(8):
    print(f"   day {c}: {n} loi")
print("\n10 loi tin cay cao nhat:")
for d in sorted(det, key=lambda x: -x["conf"])[:10]:
    print(f"   {d['panel_code'] or '?':10s} {d['cls']:16s} conf={d['conf']:.2f}  "
          f"IoU={d['iou']:.2f}  lon={d['lon']:.7f} lat={d['lat']:.7f}")
