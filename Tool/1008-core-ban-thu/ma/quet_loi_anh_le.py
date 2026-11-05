#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Detect lỗi trên TỪNG ẢNH NHIỆT LẺ rồi chiếu lên ortho — để đối chứng với cách
quét thẳng trên ortho nhiệt (bước ⑦).

HAI CÁCH KHÁC NHAU Ở ĐÂU:

  Quét ortho (đang dùng)     : ghép ortho trước → detect sau.
      Lỗi thừa hưởng sai số ghép ortho (~10,8 cm), nhưng mỗi lỗi chỉ xuất hiện
      một lần nên không phải gộp trùng giữa các ảnh.

  Quét ảnh lẻ (script này)   : detect trước → chiếu sau.
      Detect trên ảnh gốc, KHÔNG dính sai số ghép. Đổi lại: một tấm pin nằm
      trong 5-10 ảnh chồng lấn nên cùng một lỗi bị phát hiện nhiều lần, phải
      gộp lại; và mỗi lần chiếu lại mang sai số riêng của tư thế ảnh đó.

Chuỗi chiếu dùng lại của project_box_to_ortho.py (code thầy):
    pixel ảnh nhiệt → qua H → pixel RGB → tia ECEF → cắt DSM → lon/lat

    py -3.13 ma/quet_loi_anh_le.py                 # cả 598 ảnh, ~15-25 phút
    py -3.13 ma/quet_loi_anh_le.py --so-anh 40     # thử nhanh trên 40 ảnh
    py -3.13 ma/quet_loi_anh_le.py --conf 0.4
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

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
# Model 4 lớp OBB (của bạn) — model DUY NHẤT chạy được trên ảnh nhiệt GỐC.
#
# Đã thử `thermal_solar_anomaly.pt` (8 lớp, model thầy, dùng ở bước ⑦): trên ảnh
# gốc nó ra ĐÚNG 0 box, thử conf xuống 0,02 và phóng ảnh 0,5-3× đều 0. Cùng model
# đó quét cửa sổ ortho thì ra 111 box/20 cửa sổ. Nên nó chỉ chạy được trên ortho.
# Model 4 lớp thì ngược lại: 115 box/12 ảnh gốc ở conf 0,25.
MODEL = r"mo_hinh\fault_obb_4class.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--conf", type=float, default=0.25, help="giống bước ⑦")
ap.add_argument("--so-anh", type=int, default=0, dest="so_anh", help="0 = tất cả")
ap.add_argument("--gop-m", type=float, default=0.60, dest="gop_m",
                help="hai phát hiện cách nhau dưới mức này (m) coi là một lỗi")
ap.add_argument("--model", default=MODEL)
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/loi_tu_anh_le.json"))
# --- thêm 12/08/2026, MẶC ĐỊNH TẮT: không truyền thì chạy y hệt như trước ---
ap.add_argument("--bu-tung-anh", action="store_true", dest="bu_tung_anh",
                help="cộng phần bù trễ chụp riêng từng ảnh (dx,dy đo sẵn trong "
                     "anh_tre_chup_full.json) trước khi qua H — chính phần bù mà "
                     "ghep_ortho_nhiet.py đã dùng để dựng ortho")
ap.add_argument("--do-net-toi-thieu", type=float, default=0.5, dest="do_net_toi_thieu",
                help="ảnh có do_net dưới mức này thì không bù (phép đo không đáng tin)")
args = ap.parse_args()

t0 = time.time()

# ---------------------------------------------------------------- 1. dữ liệu
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

rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
ND = dsm.nodata
zmed = float(np.median(DSM[DSM != ND]))
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)

# bỏ ảnh xấu, đúng bộ lọc của ghep_ortho_nhiet.py
bo = set()
for f in ("du_lieu/anh_tre_chup_full.json", "du_lieu/anh_rung.json"):
    p = os.path.join(BASE, f)
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        bo |= {str(x) for x in d.get("anh_nen_loai", [])}
seqs = [k for k in sorted(cams) if k in rows and k not in bo]
if args.so_anh:
    seqs = seqs[:args.so_anh]
print(f"[ẢNH] quét {len(seqs)} ảnh (bỏ {len(bo)} ảnh xấu), conf={args.conf}")


def cat_dsm(lon, lat):
    r, c = dsm.index(lon, lat)
    if 0 <= r < DSM.shape[0] and 0 <= c < DSM.shape[1]:
        z = float(DSM[r, c])
        if z != ND:
            return z
    return zmed


# Bù trễ chụp riêng từng ảnh — cùng bộ dx,dy mà ghep_ortho_nhiet.py dùng.
#
# CHIỀU DẤU, đọc kỹ vì rất dễ sai. Trong loc_anh_tre.py: viền DỰ ĐOÁN dịch đi
# (dx,dy) thì khớp viền THẬT. ghep_ortho_nhiet.py đi chiều ortho -> ảnh nhiệt nên
# nó CỘNG (lấy mẫu ở tu+dx). Ở đây đi chiều ngược — ta đang cầm một pixel THẬT
# trên ảnh nhiệt và muốn ra vị trí mặt đất — nên phải TRỪ để về lại hệ dự đoán mà
# H mô tả.
#
# Cách kiểm sau khi chạy: `gan_tam_pin_4lop.py` in "Lệch tâm, trung vị". Đang là
# 16 cm; bù đúng dấu thì phải TỤT xuống ~5 cm. Nếu nó tăng lên ~30 cm là sai dấu.
BU = {}
if args.bu_tung_anh:
    p_bu = os.path.join(BASE, "du_lieu/anh_tre_chup_full.json")
    if not os.path.exists(p_bu):
        print("[!] không thấy anh_tre_chup_full.json — chạy loc_anh_tre.py trước, "
              "lần này KHÔNG bù")
    else:
        yeu = 0
        for x in json.load(open(p_bu, encoding="utf-8")).get("chi_tiet", []):
            if x.get("dx") is None:
                continue
            if x.get("do_net", 0) < args.do_net_toi_thieu:
                yeu += 1
                continue
            BU[x["seq"]] = (float(x["dx"]), float(x["dy"]))
        v = np.array([np.hypot(*b) for b in BU.values()])
        print("[BÙ]   bù riêng %d ảnh (bỏ %d ảnh do_net thấp), dịch trung vị "
              "%.2f px = %.0f cm" % (len(BU), yeu, np.median(v), np.median(v) * 2.87))


def chieu(u_th, v_th, seq):
    """pixel ảnh nhiệt -> lon/lat. Qua H sang RGB, rồi tia ECEF cắt DSM."""
    b = BU.get(seq)
    if b:
        u_th, v_th = u_th - b[0], v_th - b[1]
    p = np.array([u_th, v_th, 1.0]) @ H.T
    u, v = p[0] / p[2], p[1] / p[2]

    # tia trong hệ camera (đúng quy ước Metashape: cx,cy là ĐỘ LỆCH so với tâm)
    x = (u - IW / 2.0 - CX) / F
    y = (v - IH / 2.0 - CY) / F
    d_cam = np.array([x, y, 1.0])

    M = cams[seq]
    C_ecef = S_ch * (R_ch @ M[:3, 3]) + T_ch
    d_ecef = R_ch @ (M[:3, :3] @ d_cam)
    d_ecef /= np.linalg.norm(d_ecef)

    # cắt DSM bằng dò nhị phân dọc tia
    lo, hi = 10.0, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        P = C_ecef + d_ecef * mid
        lon, lat, alt = to_wgs.transform(*P)
        if alt > cat_dsm(lon, lat):
            lo = mid
        else:
            hi = mid
    P = C_ecef + d_ecef * ((lo + hi) / 2)
    lon, lat, _ = to_wgs.transform(*P)
    return lon, lat


from ultralytics import YOLO
model = YOLO(args.model)
print(f"[MODEL] {os.path.basename(args.model)}  ({len(model.names)} lớp)")

raw = []
for i, seq in enumerate(seqs, 1):
    im = cv2.imread(rows[seq]["path_thermal"])
    if im is None:
        continue
    r = model.predict(im, imgsz=640, conf=args.conf, verbose=False)[0]
    # Model 4 lớp là OBB -> kết quả nằm ở r.obb, không phải r.boxes.
    # Lấy hộp bao ngoài của tứ giác để có (x1,y1,x2,y2) như nhau cho cả hai loại.
    # `goc` giữ nguyên TỨ GIÁC XOAY của OBB — cần để chiếu ra vết thật trên mặt
    # đất. Hộp bao `hop` chỉ dùng cho tâm và w_m/h_m (giữ nguyên để viewer không đổi).
    if getattr(r, "obb", None) is not None and len(r.obb):
        q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
        hop = [(p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()) for p in q]
        goc = [p.tolist() for p in q]
        cls_ = [model.names[int(c)] for c in r.obb.cls.cpu().numpy()]
        conf_ = r.obb.conf.cpu().numpy().tolist()
    elif getattr(r, "boxes", None) is not None and len(r.boxes):
        hop = [tuple(b.xyxy[0].tolist()) for b in r.boxes]
        goc = [[[a, b_], [c_, b_], [c_, d_], [a, d_]] for a, b_, c_, d_ in hop]
        cls_ = [model.names[int(b.cls[0])] for b in r.boxes]
        conf_ = [float(b.conf[0]) for b in r.boxes]
    else:
        # Ảnh không có lỗi nào: model OBB trả r.obb rỗng và r.boxes = None.
        hop, goc, cls_, conf_ = [], [], [], []

    for (x1, y1, x2, y2), gq, cl, cf in zip(hop, goc, cls_, conf_):
        lon, lat = chieu((x1 + x2) / 2, (y1 + y2) / 2, seq)
        # Kích thước: chiếu HAI MÉP ĐỐI DIỆN rồi lấy khoảng cách giữa chúng.
        # Không lấy (mép - tâm) rồi nhân 2: hộp lệch tâm sau khi chiếu thì sai.
        loT, laT = chieu(x1, (y1 + y2) / 2, seq)     # mép trái
        loP, laP = chieu(x2, (y1 + y2) / 2, seq)     # mép phải
        loR, laR = chieu((x1 + x2) / 2, y1, seq)     # mép trên
        loD, laD = chieu((x1 + x2) / 2, y2, seq)     # mép dưới
        mdeg = 111320 * np.cos(np.radians(lat))
        w_m = np.hypot((loP - loT) * mdeg, (laP - laT) * 110570)
        h_m = np.hypot((loD - loR) * mdeg, (laD - laR) * 110570)
        # Vết thật trên mặt đất: chiếu cả 4 góc của tứ giác xoay. w_m/h_m ở trên
        # là cạnh của HỘP BAO nên luôn theo trục ảnh; `poly` mới giữ đúng hướng
        # nằm của tấm pin, cần cho IoU với polygon tấm pin ở bước gán mã.
        poly = [list(chieu(gx, gy, seq)) for gx, gy in gq]
        raw.append({"seq": seq, "cls": cl, "conf": float(cf),
                    "lon": lon, "lat": lat, "w_m": w_m, "h_m": h_m, "poly": poly})
    if i % 50 == 0:
        print(f"   {i}/{len(seqs)} ảnh, {len(raw)} phát hiện thô, {time.time()-t0:.0f}s")

print(f"\n[THÔ] {len(raw)} phát hiện từ {len(seqs)} ảnh, {time.time()-t0:.0f}s")

# ------------------------------------------------- gộp: cùng một lỗi thấy nhiều lần
# Đây là việc mà quét ortho KHÔNG phải làm. Ảnh chồng lấn ~70-80% nên một tấm pin
# nằm trong 5-10 ảnh; cùng một điểm nóng sẽ được phát hiện lại ở mỗi ảnh.
mdeg = 111320 * np.cos(np.radians(11.424))
raw.sort(key=lambda x: -x["conf"])
uniq = []
for r in raw:
    trung = None
    for u in uniq:
        d = np.hypot((u["lon"] - r["lon"]) * mdeg, (u["lat"] - r["lat"]) * 110570)
        # Gộp theo VỊ TRÍ, không đòi trùng lớp: cùng một điểm nóng nhìn từ hai ảnh
        # khác góc có thể bị gán lớp khác nhau (SingleHotSpot vs MultiHotSpot).
        if d < args.gop_m:
            trung = u
            break
    if trung is None:
        uniq.append({**r, "n": 1, "seqs": [r["seq"]]})
    else:
        trung["n"] += 1
        trung["seqs"].append(r["seq"])

print(f"[GỘP] {len(raw)} -> {len(uniq)} lỗi duy nhất "
      f"(mỗi lỗi thấy trung bình {np.mean([u['n'] for u in uniq]):.1f} lần)")

json.dump(uniq, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n-> {args.out}  ({os.path.getsize(args.out)/1024:.0f} KB)")

from collections import Counter
for c, n in Counter(u["cls"] for u in uniq).most_common():
    print(f"   {c:22s} {n}")

# --------------------------------------------------------- đối chiếu với bước ⑦
p7 = os.path.join(BASE, "ket_qua/loi_tren_ortho_nhiet.json")
if os.path.exists(p7):
    ref = json.load(open(p7, encoding="utf-8"))
    print(f"\n=== ĐỐI CHIẾU với {len(ref)} lỗi quét trên ortho ===")
    d_gan = []
    hit = 0
    for r in ref:
        dmin = min((np.hypot((u["lon"] - r["lon"]) * mdeg,
                             (u["lat"] - r["lat"]) * 110570) for u in uniq),
                   default=1e9)
        d_gan.append(dmin)
        hit += dmin < 1.0
    d_gan = np.array(d_gan)
    print(f"  {hit}/{len(ref)} lỗi của bước ⑦ tìm lại được (trong bán kính 1 m)")
    if (d_gan < 1e8).any():
        v = d_gan[d_gan < 1e8]
        print(f"  khoảng cách: trung vị {np.median(v)*100:.0f} cm, "
              f"P90 {np.percentile(v,90)*100:.0f} cm")
    print(f"  ảnh lẻ tìm được {len(uniq)} lỗi, ortho tìm được {len(ref)} lỗi")
