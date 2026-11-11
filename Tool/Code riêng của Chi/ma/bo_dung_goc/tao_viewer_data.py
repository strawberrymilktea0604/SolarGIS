"""Du lieu cho trang xem so sanh 4 model. Gan tam pin cho tung bo ket qua."""
import base64
import json
import os
import time

import cv2
import numpy as np
import rasterio
from ultralytics import YOLO

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
EXP = BASE + r"\Thermal2_31M_full_export"
t0 = time.time()

SETS = [("obb4", "Của bạn · 4 lớp", "loi_obb4.json"),
        ("obb5", "Của bạn · 5 lớp", "loi_obb5.json"),
        ("obb6", "Của bạn · 6 lớp", "loi_obb6.json"),
        ("thay8", "Của thầy · 8 lớp", "loi_tren_ortho_nhiet.json")]

ortho = rasterio.open(EXP + r"\ortho.tif")
mine = rasterio.open(BASE + r"\ortho_nhiet_tu_lam.tif")
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
panels = [np.array(p) for p in json.load(open(BASE + r"\tam_pin_polygon.json"))]
cen = np.array([p.mean(0) for p in panels])

# ma day/tam (giong luc truoc)
rid = np.zeros(len(panels), int); cur = 0; last = None
for i in np.argsort(cen[:, 1]):
    if last is not None and cen[i, 1] - last > 55:
        cur += 1
    rid[i] = cur; last = cen[i, 1]
code = {}
for r in range(cur + 1):
    idx = np.where(rid == r)[0]
    for k, i in enumerate(idx[np.argsort(cen[idx, 0])], 1):
        code[int(i)] = f"D{r+1:02d}-T{k:03d}"


def b64(img, q=78):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def qiou(a, b):
    a = np.asarray(a, np.float32); b = np.asarray(b, np.float32)
    A, B = cv2.contourArea(a), cv2.contourArea(b)
    if A <= 0 or B <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(a, b)
    return inter / (A + B - inter)


# ---------- khung tong quan ----------
allp = []
for tag, _, f in SETS:
    for d in json.load(open(BASE + "\\" + f, encoding="utf-8")):
        c, r = ~ortho.transform * (d["lon"], d["lat"])
        allp.append((c, r))
allp = np.array(allp)
M = 700
c0 = max(0, int(allp[:, 0].min()) - M); r0 = max(0, int(allp[:, 1].min()) - M)
c1 = min(ortho.width, int(allp[:, 0].max()) + M); r1 = min(ortho.height, int(allp[:, 1].max()) + M)
OWpx = 2400; sc = OWpx / (c1 - c0); OHpx = int((r1 - r0) * sc)

rgb = ortho.read(window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0))[:3]
rgb = cv2.resize(np.ascontiguousarray(np.moveaxis(rgb, 0, -1)[:, :, ::-1]), (OWpx, OHpx),
                 interpolation=cv2.INTER_AREA)
lo0, la0 = ortho.transform * (c0, r0); lo1, la1 = ortho.transform * (c1, r1)
a0, b0 = ~mine.transform * (lo0, la0); a1, b1 = ~mine.transform * (lo1, la1)
tm = mine.read(1, window=rasterio.windows.Window(int(a0), int(b0), int(a1-a0), int(b1-b0)),
               boundless=True, fill_value=0)
th = cv2.applyColorMap(cv2.normalize(tm, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                       cv2.COLORMAP_INFERNO)
th[tm == 0] = (30, 30, 30)
therm = cv2.resize(th, (OWpx, OHpx), interpolation=cv2.INTER_AREA)
print(f"tong quan {OWpx}x{OHpx}, {time.time()-t0:.0f}s")

HALF = 190
out_sets = []
for tag, label, fn in SETS:
    det = json.load(open(BASE + "\\" + fn, encoding="utf-8"))
    items = []
    for i, d in enumerate(sorted(det, key=lambda x: -x["conf"])):
        cc, rr = ~ortho.transform * (d["lon"], d["lat"])
        hw = d["w_m"] / 2 / (GSD / 100); hh = d["h_m"] / 2 / (GSD / 100)
        q = np.array([[cc-hw, rr-hh], [cc+hw, rr-hh], [cc+hw, rr+hh], [cc-hw, rr+hh]], np.float32)

        dd = (cen[:, 0]-cc)**2 + (cen[:, 1]-rr)**2
        near = np.argsort(dd)[:6]
        ins, best, bi = None, 0.0, None
        for j in near:
            if cv2.pointPolygonTest(panels[j].astype(np.float32), (float(cc), float(rr)), False) >= 0:
                ins = int(j)
            io = qiou(q, panels[j])
            if io > best:
                best, bi = io, int(j)
        j = ins if ins is not None else bi

        aa, bb = int(cc-HALF), int(rr-HALF)
        oi = ortho.read(window=rasterio.windows.Window(aa, bb, HALF*2, HALF*2),
                        boundless=True, fill_value=0)[:3]
        oi = np.ascontiguousarray(np.moveaxis(oi, 0, -1)[:, :, ::-1])
        if j is not None:
            cv2.polylines(oi, [(panels[j]-[aa, bb]).astype(np.int32)], True, (0, 255, 0), 2)
        if "quad" in d:      # OBB -> ve tu giac that
            qq = np.array(d["quad"]) * abs(mine.transform.a) / abs(ortho.transform.a)
            off = np.array([~ortho.transform * (d["lon"], d["lat"])]) - qq.mean(0)
            cv2.polylines(oi, [(qq + off - [aa, bb]).astype(np.int32)], True, (0, 0, 255), 3)
        else:
            cv2.rectangle(oi, (int(HALF-hw), int(HALF-hh)), (int(HALF+hw), int(HALF+hh)),
                          (0, 0, 255), 3)
        oi = cv2.resize(oi, (320, 320), interpolation=cv2.INTER_NEAREST)

        ta, tb = ~mine.transform * (d["lon"], d["lat"])
        hp = int(HALF * abs(ortho.transform.a) / abs(mine.transform.a))
        tw = mine.read(1, window=rasterio.windows.Window(int(ta-hp), int(tb-hp), hp*2, hp*2),
                       boundless=True, fill_value=0)
        tc = cv2.applyColorMap(cv2.normalize(tw, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                               cv2.COLORMAP_INFERNO)
        tc[tw == 0] = (30, 30, 30)
        s2 = abs(mine.transform.a) * 111320 * np.cos(np.radians(11.424))
        cv2.rectangle(tc, (int(hp - d["w_m"]/2/s2), int(hp - d["h_m"]/2/s2)),
                      (int(hp + d["w_m"]/2/s2), int(hp + d["h_m"]/2/s2)), (255, 255, 255), 2)
        tc = cv2.resize(tc, (320, 320), interpolation=cv2.INTER_NEAREST)

        items.append({"id": i, "cls": d["cls"], "conf": round(d["conf"], 2),
                      "lon": round(d["lon"], 8), "lat": round(d["lat"], 8),
                      "code": code.get(j), "iou": round(float(best), 2), "inp": ins is not None,
                      "size": f"{d['w_m']:.2f} x {d['h_m']:.2f}",
                      "x": round((cc-c0)*sc/OWpx*100, 3), "y": round((rr-r0)*sc/OHpx*100, 3),
                      "o": b64(oi), "t": b64(tc)})
    inp = sum(1 for x in items if x["inp"])
    out_sets.append({"tag": tag, "label": label, "items": items,
                     "n": len(items), "in_panel": inp})
    print(f"  {tag}: {len(items)} loi, gan dung {inp} ({100*inp/len(items):.0f}%), {time.time()-t0:.0f}s")

data = {"overview": b64(rgb, 74), "overview_thermal": b64(therm, 74), "sets": out_sets,
        "meta": {"panels": len(panels), "rows": cur + 1}}
p = BASE + r"\viewer_data_4model.json"
json.dump(data, open(p, "w"), separators=(",", ":"))
print(f"\n-> {p}  ({os.path.getsize(p)/1024/1024:.1f} MB), {time.time()-t0:.0f}s")
