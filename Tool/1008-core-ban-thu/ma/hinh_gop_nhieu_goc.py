#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ví dụ trực quan cho mục 1.2: MỘT lỗi được nhiều ảnh nhìn thấy từ nhiều lượt bay.

Trái  : vị trí drone lúc bấm máy (GPS trong EXIF). Chấm xám = toàn bộ 598 ảnh,
        đường màu = các LƯỢT BAY riêng đã thấy lỗi này, sao đen = tấm pin lỗi.
Phải  : cắt ảnh nhiệt THẬT quanh lỗi, mỗi ô một ảnh nguồn, viền tô theo lượt bay.

Chiếu NGƯỢC (thế giới -> pixel nhiệt) là phép nghịch đảo giải tích của hàm
`chieu()` trong quet_loi_anh_le.py: lon/lat + DSM -> ECEF -> tia trong hệ camera
-> pixel RGB -> qua H^-1 về pixel nhiệt.

    py -3.13 ma/hinh_gop_nhieu_goc.py
    py -3.13 ma/hinh_gop_nhieu_goc.py --thu 2
"""
import argparse, csv, json, os, re, sys
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from pyproj import Transformer
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ExifTags

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--thu", type=int, default=0)
ap.add_argument("--khe", type=int, default=3, help="seq cách nhau > khe là lượt bay khác")
ap.add_argument("--o", type=int, default=190, help="nửa cạnh ô cắt, tính bằng pixel nhiệt")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh/gop_nhieu_goc.png"))
args = ap.parse_args()

det = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

# ---------------------------------------------------------------- tham số máy
H = np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                            encoding="utf-8"))["H_thermal_to_rgb"])
Hi = np.linalg.inv(H)
chunk = ET.parse(os.path.join(EXP, "cameras.xml")).getroot().find(".//chunk")
s = chunk.find(".//sensor[@id='0']"); res = s.find("resolution")
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
    m = re.search(r"_(\d{4})_", cam.get("label") or "")
    if t is not None and m:
        cams[m.group(1)] = np.array(list(map(float, t.text.split()))).reshape(4, 4)

dsm = rasterio.open(os.path.join(EXP, "dsm.tif")); DSM = dsm.read(1); ND = dsm.nodata
zmed = float(np.median(DSM[DSM != ND]))
to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)


def cat_dsm(lon, lat):
    r, c = dsm.index(lon, lat)
    if 0 <= r < DSM.shape[0] and 0 <= c < DSM.shape[1]:
        z = float(DSM[r, c])
        if z != ND:
            return z
    return zmed


def chieu_nguoc(lon, lat, seq):
    """lon/lat -> pixel ảnh nhiệt. Nghịch đảo của chieu() trong quet_loi_anh_le.py."""
    if seq not in cams:
        return None
    P = np.array(to_ecef.transform(lon, lat, cat_dsm(lon, lat)))
    M = cams[seq]
    C = S_ch * (R_ch @ M[:3, 3]) + T_ch
    d_cam = np.linalg.inv(M[:3, :3]) @ (R_ch.T @ (P - C))
    if d_cam[2] <= 0:                                   # sau lưng máy ảnh
        return None
    u = d_cam[0] / d_cam[2] * F + IW / 2.0 + CX
    v = d_cam[1] / d_cam[2] * F + IH / 2.0 + CY
    q = np.array([u, v, 1.0]) @ Hi.T                    # RGB -> nhiệt
    return q[0] / q[2], q[1] / q[2]


# ---------------------------------------------------------------- chọn lỗi
def cac_dot(seqs, khe):
    s = sorted(int(x) for x in set(seqs))
    out, cur = [], [s[0]]
    for a, b in zip(s, s[1:]):
        if b - a <= khe:
            cur.append(b)
        else:
            out.append(cur); cur = [b]
    out.append(cur)
    return out


ung = sorted(det, key=lambda x: (-len(cac_dot(x["seqs"], args.khe)), -len(set(x["seqs"]))))
d = ung[args.thu]
seqs = sorted(set(d["seqs"]), key=int)
dot = cac_dot(seqs, args.khe)
print("[LỖI] %s conf=%.2f tại (%.6f, %.6f)" % (d["cls"], d["conf"], d["lat"], d["lon"]))
print("       %d ảnh · %d lượt bay: %s"
      % (len(seqs), len(dot), [["%04d" % x for x in gg] for gg in dot]))


# ---------------------------------------------------------------- GPS bay
def gps(p):
    try:
        ex = Image.open(p)._getexif()
        gk = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")
        gg = {ExifTags.GPSTAGS.get(k, k): v for k, v in ex.get(gk, {}).items()}
        f = lambda t: float(t[0]) + float(t[1]) / 60 + float(t[2]) / 3600
        la, lo = f(gg["GPSLatitude"]), f(gg["GPSLongitude"])
        return (-la if gg.get("GPSLatitudeRef") == "S" else la,
                -lo if gg.get("GPSLongitudeRef") == "W" else lo)
    except Exception:
        return None


POS = {}
for k_, r in rows.items():
    p = gps(r["path_rgb"])
    if p:
        POS[k_] = p
print("[EXIF] %d/%d ảnh có GPS" % (len(POS), len(rows)))

# ---------------------------------------------------------------- vẽ
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9.5})
fig = plt.figure(figsize=(14, 5.8))
gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.3], wspace=.14)
mau = ["#c0392b", "#2f7d4f", "#8e44ad", "#c47f1a", "#16a085", "#2980b9"]
mdeg = 111320 * np.cos(np.radians(d["lat"]))

a1 = fig.add_subplot(gs[0])
a1.scatter([(POS[k_][1] - d["lon"]) * mdeg for k_ in POS],
           [(POS[k_][0] - d["lat"]) * 110570 for k_ in POS],
           s=3.5, c="#ccd6e2", zorder=1, label="toàn bộ %d ảnh" % len(POS))
lim = 0
for i, gg in enumerate(dot):
    pts = [POS["%04d" % x] for x in gg if "%04d" % x in POS]
    if not pts:
        continue
    px = [(p[1] - d["lon"]) * mdeg for p in pts]
    py = [(p[0] - d["lat"]) * 110570 for p in pts]
    lim = max(lim, max(map(abs, px + py)))
    c = mau[i % len(mau)]
    a1.plot(px, py, "-o", color=c, ms=8.5, lw=2.3, zorder=3,
            label="lượt %d: %d ảnh (%04d–%04d)" % (i + 1, len(gg), gg[0], gg[-1]))
    for x, y, sq in zip(px, py, gg):
        a1.annotate("%04d" % sq, (x, y), fontsize=6.8, color=c, fontweight="bold",
                    xytext=(0, 8.5), textcoords="offset points", ha="center")
a1.plot(0, 0, "*", ms=27, color="#111", zorder=5, label="tấm pin lỗi")
R = lim * 1.22 + 12
a1.set_xlim(-R, R); a1.set_ylim(-R, R); a1.set_aspect("equal")
a1.set_xlabel("Tây ← → Đông  (m)"); a1.set_ylabel("Nam ← → Bắc  (m)")
a1.set_title("(a) %d ảnh thấy lỗi này — từ %d LƯỢT BAY riêng biệt" % (len(seqs), len(dot)),
             fontweight="bold", fontsize=10.5)
a1.legend(fontsize=7.4, framealpha=.95); a1.grid(alpha=.25)

k = min(len(seqs), 10)
nc = (k + 1) // 2
gs2 = gs[1].subgridspec(2, nc, hspace=.3, wspace=.05)
for i, sq in enumerate(seqs[:k]):
    ax = fig.add_subplot(gs2[i // nc, i % nc]); ax.set_xticks([]); ax.set_yticks([])
    idot = next(j for j, gg in enumerate(dot) if int(sq) in gg)
    c = mau[idot % len(mau)]
    for sp in ax.spines.values():
        sp.set_color(c); sp.set_linewidth(2.6)
    ax.set_title("%s · lượt %d" % (sq, idot + 1), fontsize=8, color=c,
                 fontweight="bold", pad=2.5)
    r = rows.get(sq)
    uv = chieu_nguoc(d["lon"], d["lat"], sq)
    if not r or not os.path.exists(r["path_thermal"]) or uv is None:
        ax.text(.5, .5, "không cắt được", ha="center", va="center", fontsize=7)
        continue
    im = np.asarray(Image.open(r["path_thermal"]).convert("L"), float)
    u, v = uv
    o = args.o
    x0, y0 = int(round(u - o)), int(round(v - o))
    pad = np.full((2 * o, 2 * o), np.nan)
    xs, ys = max(0, x0), max(0, y0)
    xe, ye = min(im.shape[1], x0 + 2 * o), min(im.shape[0], y0 + 2 * o)
    if xe > xs and ye > ys:
        pad[ys - y0:ye - y0, xs - x0:xe - x0] = im[ys:ye, xs:xe]
    fin = pad[~np.isnan(pad)]
    if fin.size:
        lo_, hi_ = np.percentile(fin, [2, 99.5])
        ax.imshow(pad, cmap="inferno", vmin=lo_, vmax=max(hi_, lo_ + 1))
    ax.plot(o, o, "o", ms=15, mfc="none", mec="#00e5ff", mew=2.1)

fig.suptitle("Một lỗi %s nhìn từ %d lượt bay khác nhau — "
             "vòng xanh là cùng MỘT điểm trên mặt đất" % (d["cls"], len(dot)),
             fontsize=11.5, fontweight="bold", y=1.0)
fig.savefig(args.ra, dpi=160, bbox_inches="tight")
print("-> %s" % args.ra)
