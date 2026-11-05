#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng ortho nhiệt bằng cách DÁN XUÔI — để so với bản đi ngược.

Đây là cách trực giác: lấy từng ảnh nhiệt, warp lên lưới ortho rồi dán chồng lên.
Ngược với ghep_ortho_nhiet.py (duyệt từng ô lưới rồi đi tìm giá trị).

Dùng CHUNG mọi thứ với ghep_ortho_nhiet.py: cameras.xml, thermal_to_rgb.json,
manifest_anh.csv, cùng bộ lọc ảnh xấu, cùng cân bằng sáng, cùng lưới đầu ra.
Khác biệt DUY NHẤT là chiều chạy — nên mọi khác biệt trên ảnh đều do chiều chạy.

Ba điểm khác về bản chất, không phải lựa chọn cài đặt:
  1. Warp cả ảnh bằng MỘT phép biến đổi phối cảnh -> phải giả định mặt phẳng.
     Bản đi ngược tra DSM cho TỪNG Ô, nên bám được địa hình.
  2. Chỗ chồng nhau: ảnh sau đè ảnh trước, theo thứ tự duyệt. Bản đi ngược
     chọn có chủ đích ảnh có tâm chụp gần nhất.
  3. Phải warp toàn ảnh lên lưới rồi vứt phần thừa.

    py -3.13 ma/ghep_ortho_dan_xuoi.py
    py -3.13 ma/ghep_ortho_dan_xuoi.py --step 6        # nhanh hơn, thô hơn
"""
import argparse
import csv
import json
import os
import re
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--step", type=float, default=3.0)
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_dan_xuoi.tif"))
ap.add_argument("--lech", default=os.path.join(BASE, "du_lieu/anh_tre_chup_full.json"))
ap.add_argument("--rung", default=os.path.join(BASE, "du_lieu/anh_rung.json"))
ap.add_argument("--khong-can-sang", action="store_false", dest="can_sang")
args = ap.parse_args()

t0 = time.time()

# ------------------------------------------------------------ 1. dữ liệu chung
H = np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                            encoding="utf-8"))["H_thermal_to_rgb"])

root = ET.parse(os.path.join(EXP, "cameras.xml")).getroot()
chunk = root.find(".//chunk")
s = chunk.find(".//sensor[@id='0']")
res = s.find("resolution")
cal = s.find("calibration[@class='adjusted']")
g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
IW, IH, F, CX, CY = int(res.get("width")), int(res.get("height")), g("f"), g("cx"), g("cy")

tr = chunk.find(".//component").find("transform")
R_ch = np.array(list(map(float, tr.find("rotation").text.split()))).reshape(3, 3)
T_ch = np.array(list(map(float, tr.find("translation").text.split())))
S_ch = float(tr.find("scale").text)

cams = {}
for cam in chunk.findall(".//camera"):
    t = cam.find("transform")
    if t is None:
        continue
    m = re.search(r"_(\d{4})_", cam.get("label") or "")
    if m:
        cams[m.group(1)] = np.array(list(map(float, t.text.split()))).reshape(4, 4)

# ------------------------------------------------- 2. lọc ảnh xấu (giống bản kia)
def doc_loc(duong, ten):
    if not os.path.exists(duong):
        print(f"[!] không thấy {os.path.basename(duong)} — bỏ qua lọc theo {ten}")
        return None
    return json.load(open(duong, encoding="utf-8"))

d_lech = doc_loc(args.lech, "trễ chụp")
d_rung = doc_loc(args.rung, "rung")
bo = set()
for d in (d_lech, d_rung):
    if d and "anh_nen_loai" in d:
        bo |= {str(x) for x in d["anh_nen_loai"]}
good = [k for k in cams if k not in bo]
print(f"[LỌC] giữ {len(good)}/{len(cams)} ảnh (bỏ {len(bo)})")

ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))

OT = ortho.transform * rasterio.Affine.scale(args.step, args.step)
OW, OH = int(ortho.width / args.step), int(ortho.height / args.step)
mdeg = 111320 * np.cos(np.radians(11.424))
print(f"[LƯỚI] {OW} x {OH} px, GSD {abs(OT.a)*mdeg*100:.2f} cm/px")

to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
rows_csv = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

# --------------------------------------------------- 3. cân bằng sáng (giống bản kia)
sang_ke = {}
if args.can_sang:
    for k in good:
        if k not in rows_csv:
            continue
        im = cv2.imread(rows_csv[k]["path_thermal"], cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        co = im[im > 0]
        if co.size < 100:
            continue
        p25, p50, p75 = np.percentile(co, [25, 50, 75])
        sang_ke[k] = (float(p50), max(float(p75 - p25), 1.0))
    if sang_ke:
        M_REF = float(np.median([v[0] for v in sang_ke.values()]))
        S_REF = float(np.median([v[1] for v in sang_ke.values()]))
        print(f"[SÁNG] cân bằng {len(sang_ke)} ảnh về mốc chung {M_REF:.0f}")
    else:
        args.can_sang = False

# ------------------------------------------------------------------ 4. DÁN XUÔI
# Mỗi ảnh: 4 góc ảnh nhiệt -> qua H -> pixel RGB -> tia -> cắt mặt phẳng z=zmed
# -> lon/lat -> ô lưới. Bốn cặp điểm cho một phép biến đổi phối cảnh, warp cả ảnh.
#
# ĐÂY LÀ CHỖ YẾU CỦA CÁCH NÀY: một phép biến đổi phối cảnh chỉ mô tả được ánh xạ
# giữa hai MẶT PHẲNG. Phải giả định cả vùng ảnh phủ nằm trên một mặt phẳng z=zmed.
# Tấm pin cao hơn mặt đất ~1-2 m nên chỗ đó bị đặt sai. Bản đi ngược tra DSM cho
# từng ô nên không mắc lỗi này.
nen = np.zeros((OH, OW), np.float32)
dem = np.zeros((OH, OW), np.uint16)
inv = ~OT
n_ok = 0

for i, k in enumerate(good):
    if k not in rows_csv:
        continue
    im = cv2.imread(rows_csv[k]["path_thermal"], cv2.IMREAD_GRAYSCALE)
    if im is None:
        continue
    im = im.astype(np.float32)
    if args.can_sang and k in sang_ke:
        m_, s_ = sang_ke[k]
        im = np.clip((im - m_) * (S_REF / s_) + M_REF, 1, 255)

    th, tw = im.shape
    goc = np.array([[0, 0], [tw, 0], [tw, th], [0, th]], np.float64)

    p = np.c_[goc, np.ones(4)] @ H.T
    uv = p[:, :2] / p[:, 2:3]

    x = (uv[:, 0] - (IW / 2 + CX)) / F
    y = (uv[:, 1] - (IH / 2 + CY)) / F
    dcam = np.c_[x, y, np.ones(4)]

    M = cams[k]
    C = S_ch * (R_ch @ M[:3, 3]) + T_ch
    dw = (R_ch @ (M[:3, :3] @ dcam.T)).T
    dw /= np.linalg.norm(dw, axis=1, keepdims=True)
    lonC, latC, altC = to_wgs.transform(*C)
    up = np.array([np.cos(np.radians(latC)) * np.cos(np.radians(lonC)),
                   np.cos(np.radians(latC)) * np.sin(np.radians(lonC)),
                   np.sin(np.radians(latC))])
    tt = (altC - zmed) / np.maximum(1e-6, -(dw @ up))
    if not np.isfinite(tt).all() or (tt <= 0).any():
        continue
    P = C + dw * tt[:, None]
    lons, lats, _ = to_wgs.transform(P[:, 0], P[:, 1], P[:, 2])

    dst = np.array([inv * (lo, la) for lo, la in zip(lons, lats)], np.float32)
    if not np.isfinite(dst).all():
        continue

    # chỉ warp trong hộp bao của ảnh này, không quét cả lưới
    x0 = max(0, int(dst[:, 0].min()) - 2); x1 = min(OW, int(dst[:, 0].max()) + 2)
    y0 = max(0, int(dst[:, 1].min()) - 2); y1 = min(OH, int(dst[:, 1].max()) + 2)
    if x1 <= x0 or y1 <= y0:
        continue

    Hw = cv2.getPerspectiveTransform(goc.astype(np.float32),
                                     (dst - [x0, y0]).astype(np.float32))
    w1 = cv2.warpPerspective(im, Hw, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                             borderValue=0)
    mk = w1 > 0
    o = nen[y0:y1, x0:x1]
    o[mk] = w1[mk]                       # ảnh sau ĐÈ ảnh trước
    nen[y0:y1, x0:x1] = o
    dem[y0:y1, x0:x1][mk] += 1
    n_ok += 1
    if n_ok % 100 == 0:
        print(f"   đã dán {n_ok} ảnh, {time.time()-t0:.0f}s")

phu = (nen > 0)
print(f"\n[DÁN]  {n_ok} ảnh, phủ {100*phu.mean():.1f}% lưới, "
      f"{100*(dem>1).mean():.1f}% ô bị nhiều ảnh đè, {time.time()-t0:.0f}s")
print(f"       chồng nhiều nhất tại một ô: {int(dem.max())} ảnh")

# ------------------------------------------------------------------- 5. ghi ra
out = np.clip(nen, 0, 255).astype(np.uint8)
with rasterio.open(args.out, "w", driver="GTiff", height=OH, width=OW, count=1,
                   dtype="uint8", crs=ortho.crs, transform=OT,
                   compress="deflate", nodata=0) as d:
    d.write(out, 1)
print(f"\n-> {args.out}  ({os.path.getsize(args.out)/1e6:.1f} MB), {time.time()-t0:.0f}s")
print("\nChạy tiếp:  py -3.13 ma/xuat_nen_net.py --lop xuoi")
