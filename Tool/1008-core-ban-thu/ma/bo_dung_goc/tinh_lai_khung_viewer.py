"""Tinh lai TOAN BO toa do % (cham + polygon) tu MOT khung duy nhat, ghi khung vao file."""
import json

import numpy as np
import rasterio

BASE = r"C:\Users\Chi\Desktop\1008-stage1-rgb-thermel"
ortho = rasterio.open(BASE + r"\Thermal2_31M_full_export\ortho.tif")
GSD = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
panels = [np.array(p) for p in json.load(open(BASE + r"\tam_pin_polygon.json"))]
cen = np.array([p.mean(0) for p in panels])

P = BASE + r"\viewer_data_2model.json"
d = json.load(open(P, encoding="utf-8"))

# KHUNG DUY NHAT: chinh la khung da dung khi tao anh tong quan (data_4model.py),
# tuc lay tu TAT CA loi cua ca 4 bo ket qua goc.
allc, allr = [], []
for f in ("loi_obb4.json", "loi_obb5.json", "loi_obb6.json", "loi_tren_ortho_nhiet.json"):
    for x in json.load(open(BASE + "\\" + f, encoding="utf-8")):
        c, r = ~ortho.transform * (x["lon"], x["lat"])
        allc.append(c); allr.append(r)
allc = np.array(allc); allr = np.array(allr)
M = 700
c0 = max(0, int(allc.min()) - M); r0 = max(0, int(allr.min()) - M)
c1 = min(ortho.width, int(allc.max()) + M); r1 = min(ortho.height, int(allr.max()) + M)
W, H = c1 - c0, r1 - r0
print(f"KHUNG: ({c0},{r0}) -> ({c1},{r1})   {W} x {H} px  = {W*GSD/100:.0f} x {H*GSD/100:.0f} m")
d["frame"] = {"c0": c0, "r0": r0, "w": W, "h": H}

tot = ins_ok = 0
for s in d["sets"]:
    for it in s["items"]:
        cc, rr = ~ortho.transform * (it["lon"], it["lat"])
        it["x"] = round((cc - c0) / W * 100, 4)          # cham, tinh lai
        it["y"] = round((rr - r0) / H * 100, 4)
        it["w"] = round(float(it["size"].split(" x ")[0]) * 100 / GSD / W * 100, 4)
        it["h"] = round(float(it["size"].split(" x ")[1]) * 100 / GSD / H * 100, 4)

        # tam pin BAO TRON cham; khong co thi lay tam gan nhat
        dd = (cen[:, 0] - cc) ** 2 + (cen[:, 1] - rr) ** 2
        near = np.argsort(dd)[:8]
        import cv2
        j = None
        for k in near:
            if cv2.pointPolygonTest(panels[k].astype(np.float32),
                                    (float(cc), float(rr)), False) >= 0:
                j = int(k); break
        it["inp"] = j is not None
        if j is None:
            j = int(near[0])
        q = panels[j]
        it["poly"] = [[round((x - c0) / W * 100, 4), round((y - r0) / H * 100, 4)]
                      for x, y in q]
        tot += 1; ins_ok += it["inp"]

json.dump(d, open(P, "w"), separators=(",", ":"))
print(f"cham NAM TRONG tam pin: {ins_ok}/{tot} = {100*ins_ok/tot:.0f}%")

# kiem chung lai bang chinh toa do % vua ghi
bad = 0; dist = []
for s in d["sets"]:
    for it in s["items"]:
        Pp = np.array(it["poly"]); px = Pp[:, 0]/100*W; py = Pp[:, 1]/100*H
        cx = it["x"]/100*W; cy = it["y"]/100*H
        dist.append(np.hypot(px.mean()-cx, py.mean()-cy)*GSD)
        if not (px.min() <= cx <= px.max() and py.min() <= cy <= py.max()):
            bad += 1
dist = np.array(dist)
print(f"kiem chung tren toa do %: cham ngoai khung {bad}/{tot}")
print(f"   lech tam-tam: trung vi {np.median(dist):.0f} cm, lon nhat {dist.max():.0f} cm")
