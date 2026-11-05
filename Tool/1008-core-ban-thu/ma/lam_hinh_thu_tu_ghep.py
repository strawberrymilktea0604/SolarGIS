#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Vẽ bộ hình minh hoạ THỨ TỰ GHÉP ảnh nhiệt thành ortho — cho THU_TU_GHEP_ORTHO.pdf.

Mọi hình đều tính từ dữ liệu THẬT trong thư mục này (cameras.xml, dsm.tif, ảnh
nhiệt gốc, các file lọc), không có hình vẽ tay ước lượng. Số in trên hình là số
chạy ra lúc vẽ, nên hình và văn bản không thể lệch nhau.

Dùng matplotlib chứ không dùng cv2.putText vì cv2 không viết được dấu tiếng Việt.

    py -3.13 ma/lam_hinh_thu_tu_ghep.py            # vẽ tất cả
    py -3.13 ma/lam_hinh_thu_tu_ghep.py --chi 3 6  # chỉ vẽ hình 3 và 6
"""
import argparse
import csv
import json
import os
import re
import textwrap
import time
import xml.etree.ElementTree as ET

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon
from pyproj import Transformer

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
RA = os.path.join(BASE, "tai_lieu/hinh_thu_tu")

ap = argparse.ArgumentParser()
ap.add_argument("--chi", type=int, nargs="*", default=None, help="chỉ vẽ các hình này")
# Cửa sổ mặc định nằm giữa vùng bay (tâm chụp trải cột 2406..22975, hàng 3639..10896).
# Đừng lấy cửa sổ sát mép: ở đó ảnh nhiệt không phủ kín, hình ra loang lổ và người
# đọc tưởng đó là lỗi của phương pháp.
ap.add_argument("--window", type=int, nargs=4, default=[11200, 6300, 2600, 2000])
args = ap.parse_args()
CAN = (lambda n: args.chi is None or n in args.chi)

os.makedirs(RA, exist_ok=True)
t0 = time.time()

# màu chung, khớp với CSS của bản PDF
XANH, CAM, XAM, DO, LUC = "#1a3f6f", "#d9730d", "#5a6572", "#c0392b", "#2e7d4f"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": "#b9c2cf", "figure.facecolor": "white"})


def ct(fig, y, chu, rong=118, **kw):
    """Lời chú dưới hình.

    PHẢI tự xuống dòng: bbox_inches="tight" nới khung theo artist rộng nhất, nên
    một dòng chú dài kéo cả hình bè ra và ảnh trong hình teo lại.
    """
    kw.setdefault("ha", "center")
    kw.setdefault("va", "top")
    kw.setdefault("fontsize", 8.2)
    kw.setdefault("color", XAM)
    kw.setdefault("linespacing", 1.55)
    return fig.text(0.5, y, textwrap.fill(" ".join(chu.split()), rong), **kw)


def luu(fig, ten):
    p = os.path.join(RA, ten)
    fig.savefig(p, dpi=155, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"   -> {ten}  ({os.path.getsize(p)/1024:.0f} KB)  {time.time()-t0:.0f}s")


# ═══════════════════════════════════════════════════════ dữ liệu dùng chung
print("[ĐỌC] cameras.xml, dsm, manifest ...")
H = np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                            encoding="utf-8"))["H_thermal_to_rgb"])
Hinv = np.linalg.inv(H)

root = ET.parse(os.path.join(EXP, "cameras.xml")).getroot()
chunk = root.find(".//chunk")
s_ = chunk.find(".//sensor[@id='0']")
res = s_.find("resolution")
cal = s_.find("calibration[@class='adjusted']")
g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
IW, IH, F, CX, CY = int(res.get("width")), int(res.get("height")), g("f"), g("cx"), g("cy")

tr = chunk.find(".//component").find("transform")
R_ch = np.array(list(map(float, tr.find("rotation").text.split()))).reshape(3, 3)
T_ch = np.array(list(map(float, tr.find("translation").text.split())))
S_ch = float(tr.find("scale").text)

cams = {}
for cam in chunk.findall(".//camera"):
    t_ = cam.find("transform")
    if t_ is None:
        continue
    m = re.search(r"_(\d{4})_", cam.get("label") or "")
    if m:
        cams[m.group(1)] = np.array(list(map(float, t_.text.split()))).reshape(4, 4)

rows_csv = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))
mdeg = 111320 * np.cos(np.radians(11.424))

to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)

# ---- ba lớp lọc, đúng thứ tự ghep_ortho_nhiet.py áp dụng
ks = sorted(cams, key=int)
Cch = {k: cams[k][:3, 3] for k in ks}
spd = {}
for i in range(1, len(ks) - 1):
    spd[ks[i]] = np.linalg.norm(Cch[ks[i + 1]] - Cch[ks[i - 1]]) * S_ch / 2
med_spd = np.median(list(spd.values()))
bo_quay = {k for k in ks if spd.get(k, med_spd) <= 0.6 * med_spd}
d_lech = json.load(open(os.path.join(BASE, "du_lieu/anh_tre_chup_full.json"), encoding="utf-8"))
d_rung = json.load(open(os.path.join(BASE, "du_lieu/anh_rung.json"), encoding="utf-8"))
bo_lech = {str(x) for x in d_lech.get("anh_nen_loai", [])} - bo_quay
bo_rung = {str(x) for x in d_rung.get("anh_nen_loai", [])} - bo_quay - bo_lech
good = [k for k in ks if k not in bo_quay | bo_lech | bo_rung]
print(f"[LỌC] {len(cams)} ảnh -> bỏ {len(bo_quay)} quay đầu, {len(bo_lech)} lệch, "
      f"{len(bo_rung)} rung -> giữ {len(good)}")


def tam_duoi_dat(k):
    """Tâm chụp chiếu xuống mặt đất (lon, lat) + tâm máy ảnh trong ECEF."""
    M = cams[k]
    C = S_ch * (R_ch @ M[:3, 3]) + T_ch
    lon, lat, alt = to_wgs.transform(*C)
    up = np.array([np.cos(np.radians(lat)) * np.cos(np.radians(lon)),
                   np.cos(np.radians(lat)) * np.sin(np.radians(lon)),
                   np.sin(np.radians(lat))])
    d = R_ch @ (M[:3, :3] @ np.array([-CX / F, -CY / F, 1.0]))
    d /= np.linalg.norm(d)
    t = (alt - zmed) / max(1e-6, -(d @ up))
    glon, glat, _ = to_wgs.transform(*(C + t * d))
    return glon, glat, C, alt


def vet_nhiet_duoi_dat(k, th=512, tw=640):
    """4 góc ảnh NHIỆT -> qua H -> pixel RGB -> tia -> mặt phẳng z=zmed -> lon/lat."""
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
        return None
    P = C + dw * tt[:, None]
    lo, la, _ = to_wgs.transform(P[:, 0], P[:, 1], P[:, 2])
    return np.c_[lo, la]


def doc_nhiet(k, mau=False):
    p = rows_csv[k]["path_thermal"]
    im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    return im


def sd(x, n=2):
    """Số thập phân kiểu Việt: dấu phẩy."""
    return f"{x:.{n}f}".replace(".", ",")


def do_phu():
    """Hai con số phủ của ortho nhiệt, đo thật.

    Đo trên KHUNG CHỮ NHẬT thì thấp một cách vô nghĩa: khung ortho là hộp bao của
    ảnh màu, còn tuyến bay là một hình bình hành nghiêng nằm lọt trong đó. Con số
    đáng nói là phủ trong VÙNG BAY — phần mặt đất mà ảnh nhiệt thực sự với tới.
    """
    onh = rasterio.open(os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
    B = 4
    W_, H_ = onh.width // B, onh.height // B
    co = onh.read(1, out_shape=(H_, W_)) > 0
    TF = onh.transform * rasterio.Affine.scale(B, B)
    inv = ~TF
    trong = np.zeros((H_, W_), np.uint8)
    for k in good:
        q = vet_nhiet_duoi_dat(k)
        if q is None:
            continue
        px = np.array([inv * (lo, la) for lo, la in q], np.float64)
        if not np.isfinite(px).all():
            continue
        cv2.fillPoly(trong, [px.astype(np.int32)], 1)
    trong = trong.astype(bool)
    return 100 * co.mean(), 100 * (co & trong).sum() / max(trong.sum(), 1), onh


def to_inferno(a, nen=(1, 1, 1)):
    """Ảnh xám -> inferno, ô trống tô nền."""
    v = a.astype(np.float32)
    co = v[v > 0]
    if co.size:
        lo, hi = np.percentile(co, [1, 99])
        v = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)
    rgb = plt.get_cmap("inferno")(v)[:, :, :3]
    rgb[a == 0] = nen
    return rgb


# ═══════════════════════════════════════════════════════════════ HÌNH 1
# Sơ đồ toàn tuyến: cái gì chạy trước, cái gì chạy sau, và vì sao.
if CAN(1):
    print("[H1] sơ đồ toàn tuyến")
    fig, ax = plt.subplots(figsize=(10.4, 6.5))
    ax.set_xlim(0, 100); ax.set_ylim(-1.5, 66); ax.axis("off")

    def hop(x, y, w, h, tieu, phu, mau, day=1.6, nen="white"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5,rounding_size=1.2",
                                    fc=nen, ec=mau, lw=day, zorder=2))
        ax.text(x + w / 2, y + h - 2.6, tieu, ha="center", va="top", fontsize=9.6,
                weight="bold", color=mau, zorder=3)
        ax.text(x + w / 2, y + h - 6.6, phu, ha="center", va="top", fontsize=8.1,
                color=XAM, zorder=3, linespacing=1.45)

    def ten(x1, y1, x2, y2, mau=XAM, nhan=None, lw=1.5, style="-"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=13, color=mau, lw=lw,
                                     linestyle=style, zorder=1,
                                     shrinkA=2, shrinkB=2))
        if nhan:
            ax.text((x1 + x2) / 2 + 1.2, (y1 + y2) / 2, nhan, fontsize=7.8,
                    color=mau, ha="left", va="center", style="italic")

    def so(bx, by, bh, n):
        """Số thứ tự, đặt ở góc trên-trái NGOÀI hộp để không đè lên chữ."""
        x, y = bx - 0.8, by + bh + 1.0
        ax.add_patch(plt.Circle((x, y), 2.05, fc=CAM, ec="white", lw=1.4, zorder=4))
        ax.text(x, y - 0.05, str(n), ha="center", va="center", fontsize=9,
                color="white", weight="bold", zorder=5)

    ax.text(50, 65, "THỨ TỰ CHẠY — từ ảnh thô đến ortho nhiệt",
            ha="center", fontsize=12.5, weight="bold", color=XANH)

    # đầu vào — mọi con số lấy từ chính dữ liệu, không gõ tay
    kmau = good[len(good) // 2]
    _th = doc_nhiet(kmau)
    gsd_rgb = ortho.transform.a * mdeg * 100
    hop(2, 50, 26, 11, f"{len(cams)} ảnh RGB (…_W.JPG)",
        f"{IW} × {IH} px\nkèm GPS/GNSS trong EXIF", XANH)
    hop(2, 35, 26, 11, f"{len(cams)} ảnh NHIỆT (…_T.JPG)",
        f"{_th.shape[1]} × {_th.shape[0]} px\nchụp cùng lần bấm", DO)

    # metashape
    hop(36, 50, 28, 11, "Metashape — CHỈ ảnh RGB",
        f"ortho.tif · dsm.tif · cameras.xml\n{ortho.width} × {ortho.height} px, "
        f"{sd(gsd_rgb)} cm/px", XANH, 2.0)
    so(36, 50, 11, 1)
    ten(28, 55.5, 36, 55.5, XANH)

    hop(36, 35, 28, 11, "Hiệu chuẩn H nhiệt→RGB",
        "chấm tay 31 cặp điểm, MỘT LẦN\ncho mỗi model drone", DO, 2.0)
    so(36, 35, 11, 2)
    ten(28, 40.5, 36, 40.5, DO)

    hop(70, 42, 28, 11, "Lọc ảnh xấu",
        f"{len(cams)} → {len(good)} ảnh\nquay đầu {len(bo_quay)} · lệch {len(bo_lech)} · rung {len(bo_rung)}",
        CAM, 2.0)
    so(70, 42, 11, 3)
    ten(64, 55.5, 70.5, 50.5, XANH)
    ten(64, 40.5, 70.5, 45.5, DO)

    # vòng lặp dựng
    ax.add_patch(FancyBboxPatch((14, 14), 72, 19, boxstyle="round,pad=0.6,rounding_size=1.4",
                                fc="#fbfaf6", ec=CAM, lw=2.2, zorder=1))
    ax.text(50, 31.4, "DỰNG ORTHO NHIỆT — duyệt theo Ô LƯỚI, không duyệt theo ảnh",
            ha="center", fontsize=9.8, weight="bold", color=CAM)
    so(14, 14, 19, 4)
    ten(84, 42, 68, 33.8, CAM)

    phu_khung, phu_bay, onh = do_phu()
    gsd_nh = onh.transform.a * mdeg * 100
    bwl = 16.5
    for i, (tt_, pp_) in enumerate([
            ("mỗi ô lưới ortho", f"{onh.width} × {onh.height} ô\n{sd(gsd_nh)} cm/ô"),
            ("hỏi: ô này lấy\ntừ ảnh nào?", "cây KD → ảnh có tâm\nchụp gần nhất"),
            ("đi ngược về\npixel ảnh nhiệt", "DSM → 3D → camera\n→ H⁻¹ → (u,v)"),
            ("nội suy song tuyến", "4 pixel lân cận\n→ một giá trị")]):
        x = 16 + i * 17.6
        ax.add_patch(FancyBboxPatch((x, 16.3), bwl, 12, boxstyle="round,pad=0.4,rounding_size=1",
                                    fc="white", ec="#d8c9ae", lw=1.3, zorder=2))
        ax.text(x + bwl / 2, 26.7, tt_, ha="center", va="top", fontsize=8.4,
                weight="bold", color="#8a5a10", zorder=3, linespacing=1.3)
        ax.text(x + bwl / 2, 21.2, pp_, ha="center", va="top", fontsize=7.5,
                color=XAM, zorder=3, linespacing=1.35)
        if i < 3:
            ten(x + bwl, 22.3, x + 17.6, 22.3, "#b09050", lw=1.3)

    hop(28, 0.2, 44, 10.6, "ket_qua/ortho/ortho_nhiet_tu_lam.tif",
        f"{onh.width} × {onh.height} px · GSD {sd(gsd_nh)} cm\n"
        f"kín {sd(phu_bay, 1)}% vùng bay ({sd(phu_khung, 1)}% khung chữ nhật)", LUC, 2.0)
    so(28, 0.2, 10.6, 5)
    ten(50, 13.4, 50, 11.4, LUC)

    ax.text(2, 9.5, "Đọc theo số 1→5.\nBước 1 và 2 độc lập nhau,\nchạy song song được.",
            fontsize=8.1, color=XAM, linespacing=1.55, va="top")
    luu(fig, "h1_thu_tu_chay.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 2
# Vì sao phải qua RGB: ảnh nhiệt nhìn thấy ít hơn nhiều so với ảnh RGB cùng lần bấm.
if CAN(2):
    print("[H2] một cặp ảnh thật + vết nhiệt trên RGB")
    k = "0300" if "0300" in rows_csv else good[len(good) // 2]
    rgb = cv2.imread(rows_csv[k]["path_rgb"], cv2.IMREAD_REDUCED_COLOR_4)[:, :, ::-1]
    th = doc_nhiet(k)
    hT, wT = th.shape

    goc = np.array([[0, 0], [wT, 0], [wT, hT], [0, hT]], np.float64)
    p = np.c_[goc, np.ones(4)] @ H.T
    uv = p[:, :2] / p[:, 2:3]

    fig, axs = plt.subplots(1, 2, figsize=(10.6, 4.3))
    axs[0].imshow(rgb)
    axs[0].add_patch(Polygon(uv / 4, closed=True, fill=False, ec=DO, lw=2.4))
    axs[0].add_patch(Polygon(uv / 4, closed=True, fc=DO, alpha=0.13, ec="none"))
    d1, d2_ = uv[2] - uv[0], uv[3] - uv[1]
    dt = 100 * abs(d1[0] * d2_[1] - d1[1] * d2_[0]) / 2 / (IW * IH)
    axs[0].set_title(f"Ảnh RGB {k}  ({IW} × {IH} px)\n"
                     f"khung đỏ = phần ảnh NHIỆT nhìn thấy, chỉ {dt:.0f}% khung RGB",
                     fontsize=9, color=XANH)
    axs[1].imshow(to_inferno(th))
    axs[1].set_title(f"Ảnh nhiệt {k}  ({wT} × {hT} px)\n"
                     f"cùng một lần bấm, ống kính khác — lệch cả vị trí lẫn tỉ lệ",
                     fontsize=9, color=DO)
    for a in axs:
        a.set_xticks([]); a.set_yticks([])
    fig.subplots_adjust(bottom=0.02, wspace=0.06)
    ct(fig, -0.02,
             "Ma trận H (3×3) là thứ nối hai khung này lại. Có H thì mọi phép định vị "
             "làm trên ảnh RGB — nơi Metashape đã dựng xong hình học — rồi mới đổi sang ảnh nhiệt.",
             ha="center", fontsize=8.3, color=XAM)
    luu(fig, "h2_cap_anh.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 3
# Thứ tự CHỤP (theo thời gian) và ảnh nào bị loại.
if CAN(3):
    print("[H3] đường bay, thứ tự chụp, ảnh bị loại")
    lo, la = [], []
    for k in ks:
        a, b, _, _ = tam_duoi_dat(k)
        lo.append(a); la.append(b)
    lo = np.array(lo); la = np.array(la)
    X = (lo - lo.min()) * mdeg
    Y = (la - la.min()) * 110570
    idx = {k: i for i, k in enumerate(ks)}

    # Số thật cho lời chú, đừng nói ước lượng: bao nhiêu phần trăm ảnh quay đầu
    # thực sự nằm ở hai mép đông–tây của vùng bay.
    mep = 0.12 * (X.max() - X.min())
    o_mep = sum(1 for k in bo_quay
                if X[idx[k]] < X.min() + mep or X[idx[k]] > X.max() - mep)
    pt_mep = 100 * o_mep / max(len(bo_quay), 1)

    # Dữ liệu rộng 205 m, cao 72 m — tỉ lệ 2,85:1. Để giữ aspect="equal" mà không
    # thừa khoảng trắng hai bên, chiều cao mỗi ô phải khớp với chiều rộng chia 2,85.
    fig, axs = plt.subplots(1, 2, figsize=(10.6, 2.9))
    ax = axs[0]
    ax.plot(X, Y, "-", color="#c9d2de", lw=0.8, zorder=1)
    sc = ax.scatter(X, Y, c=np.arange(len(ks)), cmap="viridis", s=8, zorder=2)
    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", fraction=0.07,
                      pad=0.30, aspect=42)
    cb.set_label("thứ tự bấm máy (seq 0001 → %s)" % ks[-1], fontsize=7.4)
    cb.ax.tick_params(labelsize=6.5)
    ax.set_title(f"Thứ tự CHỤP — {len(ks)} lần bấm, bay rắn bò từ nam lên bắc",
                 fontsize=9, color=XANH)
    ax.set_ylabel("m (bắc)", fontsize=8)
    ax.set_aspect("equal"); ax.tick_params(labelsize=7)

    ax = axs[1]
    ax.plot(X, Y, "-", color="#e9edf2", lw=0.7, zorder=1)
    ax.scatter([X[idx[k]] for k in good], [Y[idx[k]] for k in good],
               s=8, c="#a8b8c9", label=f"giữ — {len(good)} ảnh", zorder=2)
    for nh, tap, mau, mk in [("quay đầu (bay chậm)", bo_quay, "#7b4fb5", "s"),
                             ("lệch nhiệt–RGB", bo_lech, DO, "o"),
                             ("drone không bay đều", bo_rung, CAM, "^")]:
        if tap:
            ax.scatter([X[idx[k]] for k in tap], [Y[idx[k]] for k in tap],
                       s=19, c=mau, marker=mk, lw=0, zorder=3,
                       label=f"{nh} — bỏ {len(tap)}")
    ax.axvspan(X.min(), X.min() + mep, color="#7b4fb5", alpha=0.08, zorder=0)
    ax.axvspan(X.max() - mep, X.max(), color="#7b4fb5", alpha=0.08, zorder=0)
    ax.set_title(f"Ảnh nào bị loại trước khi ghép — {len(cams)} → {len(good)}",
                 fontsize=9, color=XANH)
    ax.set_xlabel("m (đông)", fontsize=8)
    ax.set_aspect("equal"); ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.20),
              ncol=2, frameon=False, columnspacing=1.0, handletextpad=0.35)
    fig.subplots_adjust(bottom=0.24, wspace=0.14)
    ct(fig, -0.06,
             f"Hai dải tím nhạt là 12% bề ngang ở hai mép — chỗ drone giảm tốc để đổi tuyến. "
             f"Chỉ {pt_mep:.0f}% ảnh quay đầu rơi vào đó, phần còn lại rải khắp nhà máy; "
             f"hai loại kia cũng vậy. Nên không thể lọc bằng cách cắt theo vị trí, phải đo từng ảnh.",
             ha="center", va="top", fontsize=8.2, color=XAM)
    luu(fig, "h3_thu_tu_chup.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 4
# Mỗi điểm trên mặt đất được bao nhiêu ảnh nhìn thấy.
if CAN(4):
    print("[H4] đếm số ảnh phủ mỗi chỗ")
    quads = [q for q in (vet_nhiet_duoi_dat(k) for k in good) if q is not None]
    Q = np.concatenate(quads)
    lo0, lo1 = Q[:, 0].min(), Q[:, 0].max()
    la0, la1 = Q[:, 1].min(), Q[:, 1].max()
    W = 900
    Hh = int(W * (la1 - la0) * 110570 / max((lo1 - lo0) * mdeg, 1e-9))
    dem = np.zeros((Hh, W), np.int32)
    for q in quads:
        px = np.c_[(q[:, 0] - lo0) / (lo1 - lo0) * (W - 1),
                   (1 - (q[:, 1] - la0) / (la1 - la0)) * (Hh - 1)]
        m = np.zeros((Hh, W), np.uint8)
        cv2.fillPoly(m, [px.astype(np.int32)], 1)
        dem += m

    trong = dem[dem > 0]
    fig, axs = plt.subplots(1, 2, figsize=(10.6, 3.6),
                            gridspec_kw={"width_ratios": [1.75, 1], "wspace": 0.22})
    im = axs[0].imshow(dem, cmap="magma", vmin=0, vmax=np.percentile(trong, 99.5))
    cb = fig.colorbar(im, ax=axs[0], orientation="horizontal",
                      fraction=0.045, pad=0.04, aspect=45)
    cb.set_label("số ảnh nhiệt cùng nhìn thấy một chỗ", fontsize=7.8)
    cb.ax.tick_params(labelsize=7)
    axs[0].set_xticks([]); axs[0].set_yticks([])
    axs[0].set_title(f"Độ chồng phủ của {len(quads)} ảnh nhiệt còn lại",
                     fontsize=9.5, color=XANH)

    axs[1].hist(trong, bins=np.arange(0.5, trong.max() + 1.5), color=CAM,
                edgecolor="white", lw=0.4)
    axs[1].axvline(np.median(trong), color=XANH, lw=1.8,
                   label=f"trung vị {np.median(trong):.0f} ảnh/chỗ")
    axs[1].set_xlabel("số ảnh phủ một chỗ", fontsize=8)
    axs[1].set_ylabel("số ô lưới", fontsize=8)
    axs[1].tick_params(labelsize=7)
    axs[1].legend(fontsize=7.6, frameon=False, loc="upper right")
    axs[1].set_title("Phân bố", fontsize=9.5, color=XANH)
    fig.subplots_adjust(bottom=0.12)
    ct(fig, -0.02,
             f"Trung vị {np.median(trong):.0f} ảnh cùng nhìn thấy một chỗ. Chính vì dư nhiều "
             f"như vậy nên bỏ {len(cams)-len(good)} ảnh xấu vẫn không thủng ortho — "
             f"và nên câu hỏi \"lấy ảnh nào\" mới cần trả lời có chủ đích.",
             ha="center", fontsize=8.3, color=XAM)
    luu(fig, "h4_chong_phu.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 5
# Chuỗi 6 bước cho MỘT ô lưới, kèm số thật chạy ra.
if CAN(5):
    print("[H5] chuỗi tính cho một ô lưới, số thật")
    c0, r0, ww, hh = args.window
    OT = rasterio.windows.transform(rasterio.windows.Window(c0, r0, ww, hh),
                                    ortho.transform) * rasterio.Affine.scale(3, 3)
    cc, rr = 430, 300
    LON, LAT = OT * (cc + 0.5, rr + 0.5)
    dc = int(np.clip((LON - dsm.transform.c) / dsm.transform.a, 0, dsm.width - 1))
    dr = int(np.clip((LAT - dsm.transform.f) / dsm.transform.e, 0, dsm.height - 1))
    Z = float(DSM[dr, dc])
    if Z == dsm.nodata or not np.isfinite(Z):
        Z = zmed
    Xe, Ye, Ze = to_ecef.transform(LON, LAT, Z)

    # ảnh có tâm chụp gần nhất
    nd = np.array([tam_duoi_dat(k)[:2] for k in good])
    d2 = ((nd[:, 0] - LON) * mdeg) ** 2 + ((nd[:, 1] - LAT) * 110570) ** 2
    j = int(np.argmin(d2)); kbest = good[j]
    P4 = np.array([*(R_ch.T @ (np.array([Xe, Ye, Ze]) - T_ch) / S_ch), 1.0])
    Pc = np.linalg.inv(cams[kbest]) @ P4
    u = F * Pc[0] / Pc[2] + IW / 2 + CX
    v = F * Pc[1] / Pc[2] + IH / 2 + CY
    q = Hinv @ np.array([u, v, 1.0])
    tu, tv = q[0] / q[2], q[1] / q[2]
    T = doc_nhiet(kbest).astype(np.float32)
    x0, y0 = int(tu), int(tv)
    fx, fy = tu - x0, tv - y0
    val = (T[y0, x0] * (1 - fx) * (1 - fy) + T[y0, x0 + 1] * fx * (1 - fy)
           + T[y0 + 1, x0] * (1 - fx) * fy + T[y0 + 1, x0 + 1] * fx * fy)

    fig = plt.figure(figsize=(10.6, 5.0))
    ax = fig.add_axes([0, 0.38, 1, 0.62]); ax.set_xlim(0, 100); ax.set_ylim(8, 43); ax.axis("off")
    ax.text(50, 42, f"Một ô lưới đi tìm giá trị của nó — số thật của ô (cột {cc}, hàng {rr})",
            ha="center", fontsize=11, weight="bold", color=XANH)

    buoc = [("Ô lưới ortho", f"cột {cc}\nhàng {rr}", XANH),
            ("Toạ độ địa lý", f"{LON:.6f}°E\n{LAT:.6f}°N", XANH),
            ("Cao độ từ DSM", f"z = {Z:.2f} m\ntra riêng từng ô", CAM),
            ("Điểm 3D (ECEF)", f"X  {Xe:,.0f}\nY  {Ye:,.0f}\nZ  {Ze:,.0f}", CAM),
            ("Chiếu vào ảnh RGB", f"ảnh {kbest}\nu {u:.1f}   v {v:.1f}", DO),
            ("Qua H⁻¹ sang nhiệt", f"u′ {tu:.2f}\nv′ {tv:.2f}", DO),
            ("Nội suy 4 pixel", f"giá trị = {val:.1f}", LUC)]
    w = 12.2
    for i, (tt_, pp_, mau) in enumerate(buoc):
        x = 1 + i * 14.1
        ax.add_patch(FancyBboxPatch((x, 15), w, 14, boxstyle="round,pad=0.4,rounding_size=1",
                                    fc="white", ec=mau, lw=1.7))
        ax.text(x + w / 2, 27.6, tt_, ha="center", va="top", fontsize=8.2,
                weight="bold", color=mau)
        ax.text(x + w / 2, 23.4, pp_, ha="center", va="top", fontsize=7.5,
                color=XAM, linespacing=1.5)
        ax.add_patch(plt.Circle((x + w / 2, 32.4), 1.8, fc=mau, ec="none"))
        ax.text(x + w / 2, 32.35, str(i + 1), ha="center", va="center",
                fontsize=8.4, color="white", weight="bold")
        if i < len(buoc) - 1:
            ax.add_patch(FancyArrowPatch((x + w + 0.5, 22), (x + 14.0, 22), arrowstyle="-|>",
                                         mutation_scale=12, color="#9aa5b4", lw=1.5))
    ax.text(50, 11.5, "Chiều chạy là NGƯỢC: xuất phát từ ô CẦN ĐIỀN rồi đi tìm nguồn, "
            "chứ không lấy ảnh rồi rải lên lưới.",
            ha="center", fontsize=8.8, color=XAM, style="italic")

    # ô nhiệt 4 pixel thật
    ax2 = fig.add_axes([0.375, 0.015, 0.25, 0.33])
    lay = T[y0 - 3:y0 + 5, x0 - 3:x0 + 5]
    ax2.imshow(to_inferno(lay), interpolation="nearest",
               extent=[x0 - 3.5, x0 + 4.5, y0 + 4.5, y0 - 3.5])
    ax2.add_patch(plt.Rectangle((x0 - 0.5, y0 - 0.5), 2, 2, fill=False,
                                ec="#00e5ff", lw=1.6))
    ax2.plot([tu], [tv], "o", ms=6, mfc="none", mec="#00e5ff", mew=2)
    ax2.set_title(f"bước 7 phóng to — 4 pixel của ảnh nhiệt {kbest} quanh (u′,v′)",
                  fontsize=7.6, color=XAM)
    ax2.tick_params(labelsize=6)
    luu(fig, "h5_chuoi_mot_o.png")

# ══════════════════════════════════════ máy dựng ortho cho MỘT vùng nhỏ
# Rút gọn đúng chuỗi của ghep_ortho_nhiet.py, đủ để hình vẽ ra là hình thật chứ
# không phải mô phỏng. Dùng chung cho hình 6 và hình 7.
_sang_ke, _mocs = {}, None


def can_sang_ke():
    """Trung vị + khoảng tứ phân vị của TỪNG ảnh, và mốc chung của cả tập."""
    global _mocs
    if _mocs is None:
        for k in good:
            im = cv2.imread(rows_csv[k]["path_thermal"], cv2.IMREAD_GRAYSCALE)
            if im is None:
                continue
            co = im[im > 0]
            if co.size < 100:
                continue
            a_, b_, c_ = np.percentile(co, [25, 50, 75])
            _sang_ke[k] = (float(b_), max(float(c_ - a_), 1.0))
        _mocs = (float(np.median([v[0] for v in _sang_ke.values()])),
                 float(np.median([v[1] for v in _sang_ke.values()])))
    return _sang_ke, _mocs


def dung_vung(window, can_sang=True, K=12):
    """Dựng ortho nhiệt cho một cửa sổ của ortho màu. Trả (ảnh, bản đồ nguồn)."""
    c0, r0, ww, hh = window
    OT = rasterio.windows.transform(rasterio.windows.Window(c0, r0, ww, hh),
                                    ortho.transform) * rasterio.Affine.scale(3, 3)
    OW, OH = int(ww / 3), int(hh / 3)
    gg, rr_ = np.meshgrid(np.arange(OW) + 0.5, np.arange(OH) + 0.5)
    LON = OT.c + OT.a * gg
    LAT = OT.f + OT.e * rr_

    dc = np.clip(((LON - dsm.transform.c) / dsm.transform.a).astype(np.int32), 0, dsm.width - 1)
    dr = np.clip(((LAT - dsm.transform.f) / dsm.transform.e).astype(np.int32), 0, dsm.height - 1)
    Z = DSM[dr, dc].astype(np.float64)
    Z[(Z == dsm.nodata) | ~np.isfinite(Z)] = zmed
    Xe, Ye, Ze = to_ecef.transform(LON.ravel(), LAT.ravel(), Z.ravel())
    P4 = np.vstack([R_ch.T @ (np.stack([Xe, Ye, Ze]) - T_ch[:, None]) / S_ch, np.ones(Xe.size)])

    nd = np.array([tam_duoi_dat(k)[:2] for k in good])
    P = np.c_[LON.ravel() * mdeg, LAT.ravel() * 110570]
    NDm = np.c_[nd[:, 0] * mdeg, nd[:, 1] * 110570]
    d2 = ((P[:, None, 0] - NDm[None, :, 0]) ** 2 + (P[:, None, 1] - NDm[None, :, 1]) ** 2)
    xep = np.argsort(d2, axis=1)[:, :K]

    ke, moc = can_sang_ke() if can_sang else ({}, (0, 0))
    out = np.zeros(OW * OH, np.float32)
    nguon = np.full(OW * OH, -1, np.int32)
    done = np.zeros(OW * OH, bool)
    cache = {}
    for kk in range(xep.shape[1]):
        todo = np.where(~done)[0]
        if todo.size == 0:
            break
        for i in np.unique(xep[todo, kk]):
            sl = todo[xep[todo, kk] == i]
            k = good[i]
            Pc = np.linalg.inv(cams[k]) @ P4[:, sl]
            z = Pc[2]; m = z > 0
            if not m.any():
                continue
            u = F * Pc[0] / z + IW / 2 + CX
            v = F * Pc[1] / z + IH / 2 + CY
            m &= (u >= 0) & (u < IW) & (v >= 0) & (v < IH)
            if not m.any():
                continue
            qq = Hinv @ np.vstack([u[m], v[m], np.ones(m.sum())])
            tu, tv = qq[0] / qq[2], qq[1] / qq[2]
            if k not in cache:
                T = doc_nhiet(k).astype(np.float32)
                if can_sang and k in ke:
                    m0, s0 = ke[k]
                    T = np.clip((T - m0) * (moc[1] / s0) + moc[0], 1, 255)
                cache[k] = T
            T = cache[k]
            ok = (tu >= 1) & (tu < T.shape[1] - 2) & (tv >= 1) & (tv < T.shape[0] - 2)
            if not ok.any():
                continue
            ii = sl[m][ok]
            gu = tu[ok].astype(np.float32); gv = tv[ok].astype(np.float32)
            for a_ in range(0, ii.size, 30000):   # cv2.remap giới hạn cạnh < 32767
                b_ = min(a_ + 30000, ii.size)
                out[ii[a_:b_]] = cv2.remap(T, gu[a_:b_].reshape(1, -1),
                                           gv[a_:b_].reshape(1, -1),
                                           cv2.INTER_LINEAR)[0]
            nguon[ii] = i
            done[ii] = True
    print(f"      phủ {100*done.mean():.1f}%, "
          f"{len(np.unique(nguon[nguon>=0]))} ảnh góp mặt"
          f"{'' if can_sang else ' (KHÔNG cân bằng sáng)'}")
    return out.reshape(OH, OW), nguon.reshape(OH, OW)


# ═══════════════════════════════════════════════════════════════ HÌNH 6
# Ô nào lấy từ ảnh nào — bản đồ nguồn, và ortho dựng ra từ chính nó.
if CAN(6):
    print("[H6] bản đồ nguồn: ô nào lấy từ ảnh nào (chạy thật trên một vùng)")
    out, nguon = dung_vung(args.window, can_sang=True)
    OH, OW = out.shape

    # tô màu bản đồ nguồn: mỗi ảnh một màu, giữ nguyên vị trí trong bảng màu
    uq = np.unique(nguon[nguon >= 0])
    ma = {v: i for i, v in enumerate(uq)}
    lut = np.array([ma.get(v, 0) for v in range(len(good))])
    mau = plt.get_cmap("tab20")(np.arange(len(uq)) % 20)[:, :3]
    anh_mau = np.ones((OH, OW, 3))
    m_ = nguon >= 0
    anh_mau[m_] = mau[lut[nguon[m_]]]

    fig, axs = plt.subplots(1, 2, figsize=(10.6, 4.4))
    axs[0].imshow(anh_mau, interpolation="nearest")
    for i in uq:
        yy, xx = np.where(nguon == i)
        if yy.size > 900:
            axs[0].text(xx.mean(), yy.mean(), good[i], fontsize=6.4, ha="center",
                        va="center", color="#101418",
                        bbox=dict(fc="white", alpha=0.62, pad=0.7, lw=0))
    axs[0].set_title(f"Ô nào lấy từ ảnh nào — {len(uq)} ảnh chia nhau vùng này",
                     fontsize=9.5, color=XANH)
    axs[1].imshow(to_inferno(out))
    axs[1].set_title("Ortho nhiệt dựng ra từ chính phép chia đó", fontsize=9.5, color=LUC)
    for a in axs:
        a.set_xticks([]); a.set_yticks([])
    fig.subplots_adjust(bottom=0.02, wspace=0.06)
    ct(fig, -0.02,
             "Ranh giới là đường trung trực giữa hai tâm chụp — mỗi ô về tay ảnh có tâm gần nó nhất. "
             "Không có ảnh nào \"dán sau đè lên ảnh trước\": mỗi ô được điền đúng MỘT lần, "
             "và kết quả không phụ thuộc thứ tự duyệt ảnh.",
             ha="center", fontsize=8.3, color=XAM)
    luu(fig, "h6_ban_do_nguon.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 7
# Cân bằng sáng: dựng CÙNG một vùng hai lần, chỉ khác bật/tắt cân bằng, rồi ĐO.
#
# Biểu đồ trung vị trước/sau thì vô nghĩa — sau khi kéo về mốc chung thì trung vị
# nào cũng bằng nhau, hiển nhiên đúng, chẳng nói lên điều gì. Thứ đáng đo là BƯỚC
# NHẢY tại mép ghép: chênh lệch giữa hai ô cạnh nhau nhưng lấy từ hai ảnh khác nhau.
#
# Đo trên ba cửa sổ khắp nhà máy thì bước nhảy gần như không đổi (18,1 -> 17,7 ·
# 19,2 -> 20,1 · 24,3 -> 22,7). Nên hình này nói đúng cái đo được, không nói
# "cân bằng làm mối ghép biến mất" — điều đó dữ liệu không chống lưng.
if CAN(7):
    print("[H7] cân bằng sáng — dựng cùng vùng hai lần rồi đo bước nhảy tại mép")
    tat, ng7 = dung_vung(args.window, can_sang=False)
    bat, _ = dung_vung(args.window, can_sang=True)
    ke, (M_REF, S_REF) = can_sang_ke()
    p50 = np.array([v[0] for v in ke.values()])

    def buoc_nhay(a):
        """Trung vị |chênh| giữa hai ô kề nhau: tại mép ghép, và trong lòng ảnh."""
        hs = ng7[:, :-1] != ng7[:, 1:]
        vs = ng7[:-1] != ng7[1:]
        dh = np.abs(a[:, :-1] - a[:, 1:])
        dv = np.abs(a[:-1] - a[1:])
        return (float(np.median(np.r_[dh[hs], dv[vs]])),
                float(np.median(np.r_[dh[~hs], dv[~vs]])))

    m_tat, i_tat = buoc_nhay(tat)
    m_bat, i_bat = buoc_nhay(bat)
    uq7 = np.unique(ng7[ng7 >= 0])
    med7 = np.array([ke[good[i]][0] for i in uq7])
    print(f"      mép ghép {m_tat:.1f} -> {m_bat:.1f} · trong lòng {i_tat:.1f} -> {i_bat:.1f}")

    # Thang màu CHUNG cho hai bản, nếu không thì mỗi bản tự co giãn và so sánh mất nghĩa.
    co = np.r_[tat[tat > 0], bat[bat > 0]]
    lo, hi = np.percentile(co, [1, 99])

    def chung(a):
        v = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
        rgb = plt.get_cmap("inferno")(v)[:, :, :3]
        rgb[a == 0] = 1
        return rgb

    fig = plt.figure(figsize=(10.6, 5.7))
    a1 = fig.add_axes([0.015, 0.31, 0.475, 0.60])
    a1.imshow(chung(tat)); a1.set_xticks([]); a1.set_yticks([])
    a1.set_title(f"TẮT cân bằng — bước nhảy tại mép ghép {sd(m_tat, 1)}",
                 fontsize=9, color=DO)
    a2 = fig.add_axes([0.510, 0.31, 0.475, 0.60])
    a2.imshow(chung(bat)); a2.set_xticks([]); a2.set_yticks([])
    a2.set_title(f"BẬT cân bằng — bước nhảy {sd(m_bat, 1)}, gần như không đổi",
                 fontsize=9, color=LUC)

    a3 = fig.add_axes([0.075, 0.10, 0.36, 0.16])
    a3.hist(p50, bins=45, color="#c9d2de", edgecolor="white", lw=0.4)
    a3.hist(med7, bins=45, color=DO, edgecolor="white", lw=0.4)
    a3.axvline(M_REF, color=LUC, lw=1.8)
    a3.set_title(f"trung vị sáng: cả {len(p50)} ảnh (xám) trải {p50.min():.0f}–{p50.max():.0f}, "
                 f"nhưng {len(uq7)} ảnh của vùng này (đỏ) chỉ {med7.min():.0f}–{med7.max():.0f}",
                 fontsize=7.3, color=XAM)
    a3.tick_params(labelsize=6.5); a3.set_yticks([])

    a4 = fig.add_axes([0.56, 0.10, 0.30, 0.16])
    a4.barh([1.4, 0.4], [m_tat, i_tat], height=0.34, color=DO, label="tắt")
    a4.barh([1.0, 0.0], [m_bat, i_bat], height=0.34, color=LUC, label="bật")
    a4.set_yticks([1.2, 0.2]); a4.set_yticklabels(["tại mép ghép", "trong lòng ảnh"],
                                                  fontsize=7)
    a4.tick_params(labelsize=6.5)
    a4.legend(fontsize=6.8, frameon=False, ncol=2, loc="lower right")
    a4.set_title("trung vị |chênh| giữa hai ô kề nhau (mức xám)",
                 fontsize=7.3, color=XAM)

    ct(fig, 0.005,
             f"Mép ghép vẫn nhảy gấp ~{m_bat/i_bat:.0f} lần trong lòng ảnh, bật hay tắt cân bằng cũng vậy: "
             f"chênh đó là do hình học chứ không do gain. Ảnh KỀ NHAU vốn nhìn gần cùng một cảnh nên "
             f"gain của chúng đã sát nhau sẵn; cân bằng chỉ có nghĩa khi ghép ảnh ở hai đầu chuyến bay.",
             ha="center", fontsize=8.3, color=XAM)
    luu(fig, "h7_can_sang.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 8
# Kết quả cuối + phóng to.
if CAN(8):
    print("[H8] ortho nhiệt toàn nhà máy + phóng to")
    src = rasterio.open(os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
    sc = 1700 / src.width
    toan = src.read(1, out_shape=(int(src.height * sc), int(src.width * sc)))
    # Cắt ĐÚNG cửa sổ của hình 6, để người đọc nối được hai hình với nhau.
    # Hình 6 làm ở lưới ortho màu bước 3, ortho nhiệt cũng bước 3 -> chia 3.
    c0, r0, ww, hh = args.window
    cx0, cy0, cw, ch_ = int(c0 / 3), int(r0 / 3), int(ww / 3), int(hh / 3)
    zoom = src.read(1, window=rasterio.windows.Window(cx0, cy0, cw, ch_))

    fig = plt.figure(figsize=(10.6, 6.6))
    a1 = fig.add_axes([0.02, 0.44, 0.96, 0.52])
    a1.imshow(to_inferno(toan, nen=(0.11, 0.11, 0.12)))
    a1.add_patch(plt.Rectangle((cx0 * sc, cy0 * sc), cw * sc, ch_ * sc,
                               fill=False, ec="#00e5ff", lw=1.8))
    a1.set_xticks([]); a1.set_yticks([])
    a1.set_title(f"ortho_nhiet_tu_lam.tif — {src.width} × {src.height} px, "
                 f"GSD {sd(src.transform.a * mdeg * 100)} cm, ghép từ {len(good)} ảnh nhiệt",
                 fontsize=9.5, color=XANH)
    a2 = fig.add_axes([0.20, 0.07, 0.60, 0.34])
    a2.imshow(to_inferno(zoom, nen=(0.11, 0.11, 0.12)))
    a2.set_xticks([]); a2.set_yticks([])
    a2.set_title("phóng to khung xanh — đúng vùng đã chia ở hình 6, "
                 "27 ảnh ghép lại mà không còn thấy mối nối",
                 fontsize=8.6, color=XAM)
    ct(fig, 0.005,
             "Phần đen quanh nhà máy là khung chữ nhật của ortho màu, tuyến bay không "
             "phủ tới — đó là chỗ chênh giữa hai con số phủ ở hình 1.",
             ha="center", fontsize=8.3, color=XAM)
    luu(fig, "h8_ket_qua.png")

# ═══════════════════════════════════════════════════════════════ HÌNH 9
# Nếu làm THEO THỨ TỰ ẢNH: dán xuôi. Dựng cùng một vùng bằng hai chiều rồi so.
#
# Không dùng lại kiem_tra_warp/so_dan_xuoi.jpg của minh_hoa_dan_xuoi.py: nhánh
# "đi ngược" trong script đó tra DSM sai (gán rowd rồi mới lấy cold từ rowd đã
# bị ghi đè, nên chỉ số cột lấy nhầm giá trị hàng). Ở đây dựng lại bằng chính
# dung_vung() đã dùng cho hình 6–7, nên hai vế so được với nhau.
if CAN(9):
    print("[H9] dán xuôi (theo thứ tự ảnh) so với đi ngược (theo ô lưới)")
    c0, r0, ww, hh = args.window
    OT = rasterio.windows.transform(rasterio.windows.Window(c0, r0, ww, hh),
                                    ortho.transform) * rasterio.Affine.scale(3, 3)
    OW, OH = int(ww / 3), int(hh / 3)
    inv = ~OT
    ke, moc = can_sang_ke()

    xuoi = np.zeros((OH, OW), np.float32)
    dem = np.zeros((OH, OW), np.uint16)
    n_dan = 0
    for k in good:
        q = vet_nhiet_duoi_dat(k)
        if q is None:
            continue
        dst = np.array([inv * (lo_, la_) for lo_, la_ in q], np.float32)
        if not np.isfinite(dst).all():
            continue
        if dst[:, 0].max() < 0 or dst[:, 0].min() > OW or \
           dst[:, 1].max() < 0 or dst[:, 1].min() > OH:
            continue
        im = doc_nhiet(k).astype(np.float32)
        if k in ke:
            m0, s0 = ke[k]
            im = np.clip((im - m0) * (moc[1] / s0) + moc[0], 1, 255)
        th_, tw_ = im.shape
        goc = np.array([[0, 0], [tw_, 0], [tw_, th_], [0, th_]], np.float32)
        Hw = cv2.getPerspectiveTransform(goc, dst)
        w1 = cv2.warpPerspective(im, Hw, (OW, OH), flags=cv2.INTER_LINEAR, borderValue=0)
        mk = w1 > 0
        xuoi[mk] = w1[mk]        # ảnh sau ĐÈ ảnh trước — đúng tinh thần "dán"
        dem[mk] += 1
        n_dan += 1

    nguoc, _ = dung_vung(args.window, can_sang=True)
    ho_x = float((xuoi == 0).mean()) * 100
    ho_n = float((nguoc == 0).mean()) * 100
    chong = float((dem > 1).mean()) * 100
    print(f"      dán xuôi: {n_dan} ảnh, trống {ho_x:.2f}%, {chong:.0f}% ô bị đè nhiều lần, "
          f"đè nhiều nhất {int(dem.max())} lần | đi ngược: trống {ho_n:.2f}%")

    def to_trang(a):
        v = a.copy()
        co = v[v > 0]
        if co.size:
            lo, hi = np.percentile(co, [1, 99])
            v = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)
        rgb = plt.get_cmap("inferno")(v)[:, :, :3]
        rgb[a == 0] = 1          # ô trống tô TRẮNG cho nổi
        return rgb

    # Chênh giữa hai cách — chỉ tính ở ô cả hai đều điền được.
    cả = (xuoi > 0) & (nguoc > 0)
    hieu = np.zeros_like(xuoi)
    hieu[cả] = np.abs(xuoi[cả] - nguoc[cả])
    tv_hieu = float(np.median(hieu[cả]))
    pt_lech = 100 * float((hieu[cả] > 20).mean())
    print(f"      chênh giữa hai cách: trung vị {tv_hieu:.1f} mức xám, "
          f"{pt_lech:.1f}% số ô chênh trên 20")

    fig, axs = plt.subplots(1, 3, figsize=(10.6, 3.1))
    axs[0].imshow(to_trang(xuoi))
    axs[0].set_title("DÁN XUÔI — duyệt theo THỨ TỰ ẢNH\n"
                     "warp cả ảnh lên lưới rồi dán chồng", fontsize=8.6, color=DO)
    axs[1].imshow(to_trang(nguoc))
    axs[1].set_title("ĐI NGƯỢC — duyệt theo Ô LƯỚI\n"
                     "mỗi ô tự đi tìm giá trị của nó", fontsize=8.6, color=LUC)
    im_ = axs[2].imshow(hieu, cmap="magma", vmin=0, vmax=np.percentile(hieu[cả], 99))
    cb = fig.colorbar(im_, ax=axs[2], orientation="horizontal",
                      fraction=0.055, pad=0.035, aspect=28)
    cb.set_label("|chênh| giữa hai cách (mức xám)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    axs[2].set_title(f"CHÊNH — trung vị {sd(tv_hieu, 1)}\n"
                     f"{sd(pt_lech, 1)}% số ô chênh quá 20", fontsize=8.6, color=XANH)
    for a in axs:
        a.set_xticks([]); a.set_yticks([])
    fig.subplots_adjust(bottom=0.10, wspace=0.06)
    ct(fig, -0.02,
             f"Cùng dữ liệu, cùng lưới, cùng {len(good)} ảnh, cùng cân bằng sáng — khác duy nhất CHIỀU CHẠY. "
             f"Dán xuôi ghi đè chồng lên nhau: ở vùng này mọi ô đều bị ghi lại nhiều lần, chỗ nhiều nhất "
             f"{int(dem.max())} lần, và chỉ lần CUỐI được giữ — nên kết quả phụ thuộc thứ tự duyệt ảnh. "
             f"Nó cũng phải giả định cả vùng ảnh phủ nằm trên một mặt phẳng (một phép biến đổi phối cảnh chỉ "
             f"nối được hai mặt phẳng), trong khi đi ngược tra DSM cho từng ô nên bám được độ cao tấm pin — "
             f"chênh nổi lên đúng ở mép các dãy pin.",
             ha="center", va="top", fontsize=8.2, color=XAM, linespacing=1.5)
    luu(fig, "h9_xuoi_va_nguoc.png")

print(f"\n[XONG] {time.time()-t0:.0f}s  ->  {RA}")
