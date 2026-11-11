# -*- coding: utf-8 -*-
"""Cat 100 the soi tay de chot ti le gan DUNG tam pin (nguong 95% muc 7 de bai).

Moi the gom hai khung cung mot cho tren thuc dia:
  - trai : ortho MAU  -> nhin ro mep tam pin, phan duoc "lo i co nam tren tam
           ma he thong tro toi khong"
  - phai : ortho NHIET -> nhin vet nong, phan duoc "loi nay co that khong"

Vi sao can ca hai: neu chi co anh mau thi gap bao dong gia van phai bam
"dung tam", so ra dep gia. Tach hai cau hoi moi do duoc ca hai thu.

Toa do: CHI dung lon/lat lam nguon. ocol/orow trong file la pixel ortho mau
(da kiem: khop chinh xac), nhung khong suy ra pixel anh nhiet duoc vi hai anh
khac transform.

Ma tam pin (D18-T080) la ma TU SINH trong gan_211.py - danh so theo hang/cot
tren anh, khong doi chieu so do nha may. Nen the phai VE duong bao tam duoc
gan, nguoi soi phan theo hinh hoc chu khong theo ma.
"""
import base64
import io
import json
import os
import random

import numpy as np
import rasterio
from PIL import Image, ImageDraw

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXP = "du_lieu/Thermal2_31M_full_export"
SO_MAU = 100
HAT = 20260812          # co dinh de rut lai ra dung 100 loi do
NUA_M = 6.0             # nua canh khung cat, tinh bang met
CO_ANH = 420            # kich thuoc canh moi khung xuat ra (px)

rgb = rasterio.open(os.path.join(EXP, "ortho.tif"))
nhiet = rasterio.open(os.path.join(EXP, "thermal_ortho.tif"))
loi = json.load(open("ket_qua/loi_tren_ortho_nhiet.json", encoding="utf-8"))
panels = json.load(open("ket_qua/tam_pin_polygon.json", encoding="utf-8"))

# KHONG tra nguoc qua panel_code duoc: gan_211.py ghi de ca hai file, nen ma
# trong file loi den tu mot lan chay khac voi tap polygon hien co (chi 98/195
# ma tra duoc). Thay vao do dung lai PHEP GAN hinh hoc y het dong 88-107 cua
# gan_211.py -> ra dung tam ma he thong da tro toi, khong phu thuoc ma.
cen = np.array([np.array(p).mean(0) for p in panels])
poly_np = [np.asarray(p, np.float32) for p in panels]


def quad_iou(a, b):
    import cv2
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    A, B = cv2.contourArea(a), cv2.contourArea(b)
    if A <= 0 or B <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(a, b)
    return inter / (A + B - inter)


def tam_duoc_gan(d, half_w):
    """Lap lai logic gan cua gan_211.py: uu tien tam CHUA diem loi, neu khong
    co thi lay tam co IoU cao nhat. Tra ve (chi_so_tam, iou, nam_trong)."""
    import cv2
    pt = (d["ocol"], d["orow"])
    dd = (cen[:, 0] - pt[0]) ** 2 + (cen[:, 1] - pt[1]) ** 2
    near = np.argsort(dd)[:6]
    q = np.array([[pt[0] - half_w[0], pt[1] - half_w[1]],
                  [pt[0] + half_w[0], pt[1] - half_w[1]],
                  [pt[0] + half_w[0], pt[1] + half_w[1]],
                  [pt[0] - half_w[0], pt[1] + half_w[1]]], np.float32)
    ins, best, bi = None, 0.0, None
    for i in near:
        if cv2.pointPolygonTest(poly_np[i], pt, False) >= 0:
            ins = i
        io = quad_iou(q, poly_np[i])
        if io > best:
            best, bi = io, i
    j = ins if ins is not None else bi
    return j, round(float(best), 3), ins is not None


GSD_CM = abs(rgb.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
half_w = np.array([[d["w_m"], d["h_m"]] for d in loi]).mean(0) / 2 / (GSD_CM / 100)
print("nua canh box loi dung de tinh IoU: %.1f x %.1f px" % (half_w[0], half_w[1]))

# do lon mot pixel ortho mau ra cm, de quy doi NUA_M sang pixel
GSD_M = abs(rgb.transform.a) * 111320 * np.cos(np.radians(11.424))


def cat(ds, lon, lat, nua_m, ve_poly=None, mau_vien=(255, 210, 0)):
    """Cat mot o vuong quanh (lon,lat). Tra ve anh PIL da phong ve CO_ANH."""
    col, row = ~ds.transform * (lon, lat)
    # so pixel tuong ung nua_m tren CHINH anh nay (hai anh khac do phan giai)
    gsd = abs(ds.transform.a) * 111320 * np.cos(np.radians(lat))
    nua_px = nua_m / gsd
    c0, r0 = int(col - nua_px), int(row - nua_px)
    n = int(nua_px * 2)
    c0 = max(0, min(c0, ds.width - n))
    r0 = max(0, min(r0, ds.height - n))
    w = rasterio.windows.Window(c0, r0, n, n)
    a = ds.read(window=w)[:3]
    a = np.moveaxis(a, 0, -1)
    im = Image.fromarray(np.ascontiguousarray(a)).convert("RGB")
    k = CO_ANH / float(n)
    im = im.resize((CO_ANH, CO_ANH), Image.LANCZOS)
    d = ImageDraw.Draw(im)

    # duong bao tam pin duoc gan (chi ve duoc tren anh mau - polygon o he do)
    if ve_poly is not None:
        pts = [((x - c0) * k, (y - r0) * k) for x, y in ve_poly]
        d.polygon(pts, outline=mau_vien, width=3)

    # dau chu thap tai vi tri loi - de nguoi soi biet dang xet cai nao
    cx = (col - c0) * k
    cy = (row - r0) * k
    for dx, dy in [(-14, 0), (14, 0)]:
        d.line([cx + dx * 0.35, cy, cx + dx, cy], fill=(255, 60, 60), width=3)
    for dx, dy in [(0, -14), (0, 14)]:
        d.line([cx, cy + dy * 0.35, cx, cy + dy], fill=(255, 60, 60), width=3)
    return im


def b64(im):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=82)
    return base64.b64encode(b.getvalue()).decode()


random.seed(HAT)
mau = random.sample(range(len(loi)), min(SO_MAU, len(loi)))
mau.sort()

the = []
co_poly = 0
for n, i in enumerate(mau, 1):
    d = loi[i]
    pj, iou_tinh, nam_trong = tam_duoc_gan(d, half_w)
    poly = panels[pj] if pj is not None else None
    if poly is not None:
        co_poly += 1
    im_rgb = cat(rgb, d["lon"], d["lat"], NUA_M, ve_poly=poly)
    im_nh = cat(nhiet, d["lon"], d["lat"], NUA_M)
    the.append({
        "idx": i,
        "cls": d["cls"],
        "conf": round(d["conf"], 3),
        "panel_code": d.get("panel_code"),
        "in_panel": bool(nam_trong),
        "iou": iou_tinh,
        "dist_cm": d.get("dist_cm"),
        "n_anh": d.get("n"),
        "lon": d["lon"], "lat": d["lat"],
        "rgb": b64(im_rgb),
        "nhiet": b64(im_nh),
    })
    if n % 10 == 0:
        print("   ...%d/%d the" % (n, len(mau)))

json.dump({"hat": HAT, "nua_m": NUA_M, "tong_loi": len(loi), "the": the},
          open("cong_cu/_the_soi_tay.json", "w", encoding="utf-8"))
print("\nDa cat %d the -> _the_soi_tay.json (%.1f MB)"
      % (len(the), os.path.getsize("cong_cu/_the_soi_tay.json") / 1e6))
print("Co duong bao tam de ve: %d/%d the" % (co_poly, len(the)))
print("Trong so do, loi roi HAN trong tam: %d" % sum(1 for t in the if t["in_panel"]))
