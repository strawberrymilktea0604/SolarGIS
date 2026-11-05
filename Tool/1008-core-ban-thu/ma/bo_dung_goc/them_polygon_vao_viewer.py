"""Them polygon TAM PIN (toa do % khung tong quan) vao du lieu, de ve vien dung tam."""
import json

import cv2
import numpy as np
import rasterio

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
ortho = rasterio.open(BASE + r"\Thermal2_31M_full_export\ortho.tif")
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
panels = [np.array(p) for p in json.load(open(BASE + r"\tam_pin_polygon.json"))]
cen = np.array([p.mean(0) for p in panels])

p = BASE + r"\viewer_data_2model.json"
d = json.load(open(p))

# dung lai khung tong quan y het luc tao anh
allc, allr = [], []
for s in d["sets"]:
    for it in s["items"]:
        c, r = ~ortho.transform * (it["lon"], it["lat"])
        allc.append(c); allr.append(r)
allc = np.array(allc); allr = np.array(allr)
M = 700
c0 = max(0, int(allc.min()) - M); r0 = max(0, int(allr.min()) - M)
c1 = min(ortho.width, int(allc.max()) + M); r1 = min(ortho.height, int(allr.max()) + M)
W, H = c1 - c0, r1 - r0
print(f"khung {W} x {H} px")

no_panel = 0
for s in d["sets"]:
    for it in s["items"]:
        cc, rr = ~ortho.transform * (it["lon"], it["lat"])
        dd = (cen[:, 0] - cc) ** 2 + (cen[:, 1] - rr) ** 2
        j = int(np.argmin(dd))
        # chi nhan tam pin neu tam loi nam trong hoac rat gan
        inside = cv2.pointPolygonTest(panels[j].astype(np.float32),
                                      (float(cc), float(rr)), True)
        if inside < -60:                       # xa hon ~0,6 m thi bo
            it["poly"] = None
            no_panel += 1
            continue
        q = panels[j]
        it["poly"] = [[round((x - c0) / W * 100, 4), round((y - r0) / H * 100, 4)]
                      for x, y in q]

json.dump(d, open(p, "w"), separators=(",", ":"))
tot = sum(len(s["items"]) for s in d["sets"])
print(f"{tot - no_panel}/{tot} loi co polygon tam pin, {no_panel} khong tim duoc")
ex = next(i for s in d["sets"] for i in s["items"] if i["poly"])
print("vi du polygon (%):", [[round(a, 2), round(b, 2)] for a, b in ex["poly"]])
