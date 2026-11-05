"""Chay model loi tren ORTHO NHIET tu dung, quet cua so truot + khu trung lap."""
import json
import time

import cv2
import numpy as np
import rasterio
from ultralytics import YOLO

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
SRC = BASE + r"\ortho_nhiet_tu_lam.tif"
MODEL = r"mo_hinh\thermal_solar_anomaly.pt"

TILE = 640            # bang dung kich thuoc anh nhiet goc -> khong lech ti le
OVER = 0.30           # chong lan giua cac cua so
CONF = 0.25

t0 = time.time()
src = rasterio.open(SRC)
GSD = abs(src.transform.a) * 111320 * np.cos(np.radians(11.424))     # m/px
print(f"[ORTHO NHIET] {src.width} x {src.height}, GSD {GSD*100:.2f} cm/px")
print(f"[CUA SO] {TILE} px = {TILE*GSD:.1f} m, chong lan {OVER:.0%}")

model = YOLO(MODEL)
step = int(TILE * (1 - OVER))
raw = []
nwin = 0
for y in range(0, src.height - 1, step):
    for x in range(0, src.width - 1, step):
        w = min(TILE, src.width - x); h = min(TILE, src.height - y)
        if w < 200 or h < 200:
            continue
        a = src.read(1, window=rasterio.windows.Window(x, y, w, h))
        if (a > 0).mean() < 0.35:            # bo cua so gan nhu trong
            continue
        nwin += 1
        img = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)     # model doi 3 kenh xam
        r = model.predict(img, imgsz=640, conf=CONF, verbose=False)[0]
        for b in r.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            raw.append({"box": [x + x1, y + y1, x + x2, y + y2],
                        "cls": model.names[int(b.cls[0])], "conf": float(b.conf[0])})
print(f"[QUET] {nwin} cua so, {len(raw)} phat hien tho, {time.time()-t0:.0f}s")


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ar = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ar if ar > 0 else 0


order = sorted(range(len(raw)), key=lambda i: -raw[i]["conf"])
used = [False]*len(raw); uniq = []
for i in order:
    if used[i]:
        continue
    used[i] = True
    grp = [raw[i]]
    for j in order:
        if not used[j] and iou(raw[i]["box"], raw[j]["box"]) >= 0.30:
            used[j] = True; grp.append(raw[j])
    r = dict(raw[i]); r["n"] = len(grp)
    uniq.append(r)
print(f"[GOP]  {len(raw)} -> {len(uniq)} loi duy nhat\n")

out = []
for k, r in enumerate(uniq):
    x1, y1, x2, y2 = r["box"]
    lon, lat = src.transform * ((x1+x2)/2, (y1+y2)/2)
    w_m, h_m = (x2-x1)*GSD, (y2-y1)*GSD
    out.append({**r, "lon": lon, "lat": lat, "w_m": w_m, "h_m": h_m})
    if k < 25:
        print(f"  #{k:02d} {r['cls']:18s} conf={r['conf']:.2f}  "
              f"lon={lon:.8f} lat={lat:.8f}  {w_m:.2f} x {h_m:.2f} m  (gop {r['n']})")
if len(uniq) > 25:
    print(f"  ... con {len(uniq)-25} loi nua")

json.dump(out, open(BASE + r"\loi_tren_ortho_nhiet.json", "w"), indent=1)
sz = np.array([[o["w_m"], o["h_m"]] for o in out])
print(f"\nKich thuoc o loi: trung vi {np.median(sz[:,0]):.2f} x {np.median(sz[:,1]):.2f} m")
from collections import Counter
for c, n in Counter(o["cls"] for o in out).most_common():
    print(f"   {c:20s} {n}")

# ---- doi chieu voi 10 loi tim bang cach chieu tung anh ----
ref = json.load(open(BASE + r"\gan_tam_pin.json", encoding="utf-8"))
print(f"\n=== DOI CHIEU VOI {len(ref)} LOI TIM BANG CACH CHIEU TUNG ANH ===")
hit = 0
for r in ref:
    dmin, best = 1e9, None
    for o in out:
        d = np.hypot((o["lon"]-r["lon"])*111320*np.cos(np.radians(11.424)),
                     (o["lat"]-r["lat"])*110570)
        if d < dmin:
            dmin, best = d, o
    ok = dmin < 1.0
    hit += ok
    print(f"  {r['cls']:16s} conf={r['conf']:.2f}  ->  "
          f"{'TIM THAY' if ok else 'KHONG THAY':11s} cach {dmin:6.2f} m"
          + (f"  ({best['cls']} {best['conf']:.2f})" if ok else ""))
print(f"\n  Trung khop: {hit}/{len(ref)}")
