#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hai hình cho tài liệu "Từ ảnh nhiệt ra vị trí lỗi".

  H1 — bốn cách ngành đang dùng để biến một phát hiện trên ảnh nhiệt thành toạ độ,
       xếp thành bốn làn ngang, mỗi làn kèm sai số chính tác giả báo.
  H2 — hai vai của ảnh RGB: cho HÌNH HỌC (tư thế + DSM) và cho BIÊN TẤM (polygon).

Vẽ bằng matplotlib chứ không dùng SVG như ma/_hinh_ve.py, vì tài liệu này đi qua
pandoc -> xelatex, mà SVG dùng biến CSS thì xelatex không dựng được.

    py -3.13 ma/hinh_bon_cach_dinh_vi.py
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RA = os.path.join(BASE, "tai_lieu", "hinh")
os.makedirs(RA, exist_ok=True)

plt.rcParams["font.family"] = ["Segoe UI", "Arial", "sans-serif"]

# bảng màu: nhiệt = cam, RGB = xanh thép, hình học = xám, đầu ra = xanh lá
C_NHIET = "#E07A3F"
C_RGB = "#3E6E9E"
C_HINH = "#7A7A82"
C_RA = "#3F8F5C"
C_NEN = "#FBFAF8"
C_CHU = "#1F1F23"
C_MO = "#6B6B73"


def hop(ax, x, y, w, h, ten, phu=None, mau=C_HINH, dam=False):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=2.2 if dam else 1.5, edgecolor=mau,
        facecolor="#FFFFFF", zorder=3))
    ax.text(x + w / 2, y + h * (0.60 if phu else 0.5), ten, ha="center", va="center",
            fontsize=8.6, color=C_CHU, fontweight="600" if dam else "500", zorder=4)
    if phu:
        ax.text(x + w / 2, y + h * 0.26, phu, ha="center", va="center",
                fontsize=7.2, color=C_MO, zorder=4)


def mui(ax, x1, y, x2, mau=C_HINH):
    ax.add_patch(FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>",
                                 mutation_scale=11, linewidth=1.4,
                                 color=mau, zorder=2))


# ══════════════════════════════════════════════ H1 — bốn cách
fig, ax = plt.subplots(figsize=(11.0, 5.8), dpi=210)
ax.set_xlim(0, 100)
ax.set_ylim(0, 58)
ax.axis("off")
fig.patch.set_facecolor(C_NEN)

ax.text(0.5, 55.6, "Từ một phát hiện trên ảnh nhiệt đến toạ độ ngoài đồng — bốn cách ngành đang dùng",
        fontsize=11.6, fontweight="700", color=C_CHU)
ax.text(0.5, 52.8, "Hộp cam = dữ liệu nhiệt · hộp xanh = dữ liệu RGB · hộp xám = hình học · "
                   "cột phải = sai số chính tác giả báo",
        fontsize=7.6, color=C_MO)

# ba cột: nhãn làn [0,20] · chuỗi hộp [21,79] · sai số [81,99.5]
X0, X1, GAP = 21.0, 79.0, 2.2
H = 6.6
W = (X1 - X0 - 3 * GAP) / 4.0

LAN = [
    dict(y=42.2, ten="① Ghép ortho nhiệt trước", phu="detect ngay trên ortho",
         hop=[("Ảnh nhiệt lẻ", None, C_NHIET), ("Ghép ortho nhiệt", "đã georeference", C_NHIET),
              ("Detect trên ortho", None, C_NHIET), ("Đọc geotransform", "pixel → lon/lat", C_HINH)],
         ss="0,72–1,50 m", ai="[21] PRISM · [47] Zeitview"),
    dict(y=32.6, ten="② Chiếu thẳng, sân phẳng", phu="không cần mô hình độ cao",
         hop=[("Ảnh nhiệt lẻ", None, C_NHIET), ("Detect trên khung", None, C_NHIET),
              ("Pinhole + GPS", "tư thế gimbal", C_HINH), ("Giả thiết sân phẳng", "z = const", C_HINH)],
         ss="2,51 m", ai="[08] Barraz · [09] Løfstad-Lie"),
    dict(y=23.0, ten="③ Bắn tia cắt DSM", phu="DỰ ÁN đi đường này",
         hop=[("Ảnh nhiệt lẻ", None, C_NHIET), ("Detect trên khung", None, C_NHIET),
              ("Ma trận H", "sang khung RGB", C_RGB), ("Tia ECEF, cắt DSM", "lon/lat", C_HINH)],
         ss="4,3 cm*", ai="[20] MatchPlant · [43] SunMap"),
    dict(y=13.4, ten="④ SfM trên ảnh nhiệt", phu="không dùng RGB",
         hop=[("Ảnh nhiệt lẻ", None, C_NHIET), ("SfM trên ảnh nhiệt", "hay hỏng", C_NHIET),
              ("Bám vết đa khung", None, C_NHIET), ("Bản đồ nhiệt", None, C_NHIET)],
         ss="5,87 m", ai="[01][02] PV-Hawk"),
]

for L in LAN:
    y = L["y"]
    noi_bat = L["ss"].endswith("*")
    ax.text(0.5, y + H * 0.62, L["ten"], fontsize=8.8, fontweight="700",
            color=C_RA if noi_bat else C_CHU, va="center")
    ax.text(0.5, y + H * 0.24, L["phu"], fontsize=7.0, color=C_MO, style="italic", va="center")
    x = X0
    for i, (ten, phu, mau) in enumerate(L["hop"]):
        hop(ax, x, y, W, H, ten, phu, mau, dam=(noi_bat and mau == C_RGB))
        if i < len(L["hop"]) - 1:
            mui(ax, x + W, y + H / 2, x + W + GAP)
        x += W + GAP
    ax.text(99.5, y + H * 0.62, L["ss"], fontsize=10.6, fontweight="700",
            color=C_RA if noi_bat else C_CHU, ha="right", va="center")
    ax.text(99.5, y + H * 0.22, L["ai"], fontsize=6.6, color=C_MO, ha="right", va="center")

ax.plot([0.5, 99.5], [10.2, 10.2], color="#D8D4CE", linewidth=1)
ax.text(0.5, 7.6,
        "Cách ① không thực hiện phép chiếu nào — nó đọc vị trí pixel trên một tấm ortho đã được georeference sẵn "
        "bằng GCP hoặc GPS. Review [34] chỉ trích\nrằng phần lớn ortho thu được “chỉ là một ảnh đơn thuần, "
        "không có thêm thông tin GPS”.",
        fontsize=7.6, color=C_CHU, va="top")
ax.text(0.5, 2.4,
        "* 4,3 cm là độ khớp giữa ortho nhiệt và ortho màu — sai số TƯƠNG ĐỐI, chưa phải sai số tuyệt đối "
        "kiểm chứng bằng đo ngoại nghiệp.",
        fontsize=7.0, color=C_MO, va="top", style="italic")

fig.savefig(os.path.join(RA, "dinh_vi_bon_cach.png"), bbox_inches="tight",
            facecolor=C_NEN, pad_inches=0.12)
plt.close(fig)

# ══════════════════════════════════════════════ H2 — hai vai của RGB
fig, ax = plt.subplots(figsize=(9.6, 4.2), dpi=210)
ax.set_xlim(0, 100)
ax.set_ylim(0, 44)
ax.axis("off")
fig.patch.set_facecolor(C_NEN)

ax.text(0.5, 41.4, "Vì sao phải có cả hai kênh — hai vai khác nhau của ảnh RGB",
        fontsize=11.4, fontweight="700", color=C_CHU)

hop(ax, 1.5, 27.5, 26, 8.4, "Ảnh NHIỆT", "nhìn thấy LỖI\nbiên tấm nhoè", C_NHIET, dam=True)
hop(ax, 1.5, 13.0, 26, 8.4, "Ảnh RGB", "nhìn thấy TẤM\nkhông thấy lỗi", C_RGB, dam=True)

mui(ax, 27.5, 31.7, 37.5, C_NHIET)
mui(ax, 27.5, 17.2, 37.5, C_RGB)

hop(ax, 37.5, 27.5, 27, 8.4, "Phát hiện dị thường", "hộp bao trên khung nhiệt", C_NHIET)
hop(ax, 37.5, 13.0, 27, 8.4, "Vai 2 — BIÊN TẤM", "polygon từng tấm pin", C_RGB)

ax.add_patch(FancyBboxPatch((37.5, 1.2), 27, 8.4,
                            boxstyle="round,pad=0.012,rounding_size=0.02",
                            linewidth=2.2, edgecolor=C_RGB, facecolor="#FFFFFF", zorder=3))
ax.text(51, 6.6, "Vai 1 — HÌNH HỌC", ha="center", va="center", fontsize=8.6,
        fontweight="600", color=C_CHU, zorder=4)
ax.text(51, 3.4, "tư thế camera + DSM\n(SfM trên nhiệt thì hỏng)", ha="center", va="center",
        fontsize=7.2, color=C_MO, zorder=4)

ax.add_patch(FancyArrowPatch((64.5, 31.7), (74.5, 26.0), arrowstyle="-|>",
                             mutation_scale=11, linewidth=1.4, color=C_NHIET, zorder=2))
ax.add_patch(FancyArrowPatch((64.5, 17.2), (74.5, 22.0), arrowstyle="-|>",
                             mutation_scale=11, linewidth=1.4, color=C_RGB, zorder=2))
ax.add_patch(FancyArrowPatch((64.5, 5.4), (74.5, 20.0), arrowstyle="-|>",
                             mutation_scale=11, linewidth=1.4, color=C_RGB, zorder=2))

hop(ax, 74.5, 19.0, 24, 10.0, "MÃ TẤM PIN", "đầu ra đội O&M dùng", C_RA, dam=True)

ax.text(69.0, 9.0,
        "Nối hai kênh bằng phép ĐĂNG KÝ.\n"
        "Tấm rộng 0,88 m → sai số quá ~44 cm\nlà bắt đầu gán nhầm sang tấm bên.",
        fontsize=7.4, color=C_CHU, va="top")

fig.savefig(os.path.join(RA, "dinh_vi_hai_vai_rgb.png"), bbox_inches="tight",
            facecolor=C_NEN, pad_inches=0.12)
plt.close(fig)

for f in ["dinh_vi_bon_cach.png", "dinh_vi_hai_vai_rgb.png"]:
    p = os.path.join(RA, f)
    print("->", p, "%.0f KB" % (os.path.getsize(p) / 1024))
