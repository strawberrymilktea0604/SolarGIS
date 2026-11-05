#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bốn hình cho `tai_lieu/BAY_HAI_TANG_AI_LAM_CHUA.md` — tình trạng nghiên cứu của
thiết kế "bay toàn cảnh một lần + bay khảo sát nhiều lần".

  B1  ai bay thật      hình chính: bốn thiết kế bay xếp cạnh nhau theo cùng một trục
                       độ cao. Nét liền = đã bay thật, nét đứt = chỉ có trên giấy.
                       Đây là câu trả lời trực tiếp cho "có ai làm chưa".
  B2  chỗ đứt 2022     Løfstad-Lie 2022 định làm gì và thực tế chạy gì. Vẽ đúng chỗ
                       thay thế: ảnh 20 m được "coi như" đầu ra tầng 80 m.
  B3  dòng thời gian   ý tưởng đã có tên chuẩn từ bao giờ và ai cắm cờ trước —
                       để không nhận là mới thứ đã được đặt tên.
  B4  ba trục còn hở   ma trận sáu tiêu chí × sáu công trình. Ô đặc = có làm và có
                       số, ô rỗng = không có. Ba dòng cuối là chỗ dự án chen vào.

MÀU: dùng lại bộ đã qua kiểm tra mù màu của `hinh_chia_tap.py` — lam #2F6FB5,
lục #3F8F5C, gỉ #C9552D. Ở đây gán nghĩa: lam = pha nền/RGB, gỉ = pha nhiệt,
lục = dự án. Nét đứt xám = công bố nhưng chưa bay.

Nguồn số: `ket_qua/bay_hai_tang_prior_art.json` (workflow 24/08/2026, 19 agent,
mọi phát hiện đã qua phản biện đối kháng) và toàn văn hai bài Løfstad-Lie trong
`tai_lieu/bai_bao_lien_quan/pdf/`.

    py -3.13 ma/hinh_bay_hai_tang.py
    py -3.13 ma/hinh_bay_hai_tang.py --chi B1
"""
import argparse
import os
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="chỉ dựng một hình: B1..B4")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

plt.rcParams["font.family"] = ["Segoe UI", "Arial", "sans-serif"]

C_NEN_B, C_NHIET, C_DUAN = "#2F6FB5", "#C9552D", "#3F8F5C"
C_CHU, C_MO, C_VIEN, C_NEN, C_MA = "#1F1F23", "#6B6B73", "#D8D4CE", "#FBFAF8", "#B9B4AC"
C_DAT, C_TAM = "#E8E2DA", "#4A4A52"


def khung(ax):
    ax.set_xticks([]), ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_facecolor(C_NEN)


def luu(fig, ten):
    p = os.path.join(args.ra, ten)
    fig.savefig(p, bbox_inches="tight", facecolor=C_NEN, pad_inches=0.14, dpi=170)
    plt.close(fig)
    try:
        p = os.path.relpath(p, BASE)
    except ValueError:
        pass
    print("->", p.replace("\\", "/"))


def drone(ax, x, y, mau, that=True, r=1.5):
    """Một chấm drone. that=False -> nét đứt, rỗng ruột: có trên giấy, chưa bay."""
    ax.add_patch(Circle((x, y), r, facecolor=mau if that else "none",
                        edgecolor=mau if that else C_MA, linewidth=1.6,
                        linestyle="-" if that else (0, (2.4, 1.8)), zorder=5))
    for d in (-1, 1):
        ax.plot([x + d * r * 0.72, x + d * r * 1.9], [y + r * 0.5, y + r * 1.15],
                color=mau if that else C_MA, linewidth=1.5,
                linestyle="-" if that else (0, (2.0, 1.6)), zorder=4)


def mat_dat(ax, x0, x1, n=7):
    """Dải đất kèm n hàng tấm pin nghiêng."""
    ax.add_patch(Rectangle((x0, -1.2), x1 - x0, 1.2, facecolor=C_DAT,
                           edgecolor="none", zorder=2))
    b = (x1 - x0) / (n + 1)
    for i in range(n):
        cx = x0 + b * (i + 1)
        ax.plot([cx - b * 0.30, cx + b * 0.30], [0.15, 1.5], color=C_TAM,
                linewidth=2.2, solid_capstyle="round", zorder=3)


lam = (lambda t: not args.chi or args.chi.upper() == t)

# ═════════════════════════════════════════════ B1  ai đã bay thật (hình chính)
if lam("B1"):
    # (tiêu đề, phụ đề, [(độ cao, nhãn, màu, đã-bay-thật)], ghi chú dưới)
    COT = [
        ("Løfstad-Lie 2022\nĐỀ XUẤT", "IEEE JPhotov 12(6)",
         [(80, "tầng thăm dò · 80 m", C_NHIET, False),
          (20, "tầng phân loại · 20 m", C_NHIET, False)],
         "Hai tầng — nhưng\nCHƯA TỪNG BAY"),
        ("Løfstad-Lie 2022\nTHỰC TẾ", "cùng bài, mục V",
         [(20, "một chuyến · 20 m", C_NHIET, True)],
         "Đúng 1 chuyến, 32 phút.\nBộ dò chạy trên ảnh 20 m"),
        ("Løfstad-Lie 2025\nBẦY 4 UAV", "IEEE JPhotov 15(5)",
         [(40, "chuyến chuẩn · 40 m", C_NEN_B, True),
          (30, "bầy 4 UAV · 30 m", C_NHIET, True)],
         "“3 lượt” nằm TRONG\nmột chuyến — 3 hàng\nlọt cùng khung"),
        ("Dự án", "Mapping1 + 13 sortie",
         [(60, "nền RGB toàn cảnh", C_NEN_B, True),
          (42, "sortie nhiệt · 42 m", C_DUAN, True),
          (35, "sortie nhiệt · 35 m", C_DUAN, True),
          (31, "sortie nhiệt · 31 m", C_DUAN, True)],
         "Nền RGB + N sortie nhiệt\nđa độ cao, cùng đăng ký"),
    ]
    fig, axs = plt.subplots(1, 4, figsize=(15.2, 6.4), facecolor=C_NEN)
    fig.subplots_adjust(wspace=0.16)
    for ax, (ten, phu, ds, ghi) in zip(axs, COT):
        khung(ax)
        ax.set_xlim(0, 30), ax.set_ylim(-14, 100)
        mat_dat(ax, 1, 29)
        for h, nhan, mau, that in ds:
            ax.plot([1, 29], [h, h], color=C_VIEN, linewidth=0.9, zorder=1)
            drone(ax, 8.5, h, mau, that)
            ax.text(13.5, h, nhan, fontsize=9.9, color=C_CHU if that else C_MO,
                    fontweight="700" if that else "400", va="center")
            # tia nhìn xuống đất
            for d in (-1, 1):
                ax.plot([8.5, 8.5 + d * (2.4 + h * 0.085)], [h - 1.7, 1.4],
                        color=mau, linewidth=0.8, alpha=0.30 if that else 0.16,
                        linestyle="-" if that else (0, (2, 2)), zorder=1)
        ax.text(15, 96, ten, fontsize=12.2, fontweight="700", color=C_CHU,
                ha="center", va="top", linespacing=1.35)
        ax.text(15, 86.5, phu, fontsize=9.2, color=C_MO, ha="center", va="top")
        ax.text(15, -3.4, ghi, fontsize=9.7, color=C_CHU, ha="center", va="top",
                linespacing=1.55)
    for mau, ten, x in [(C_NEN_B, "pha nền / RGB", 0.30), (C_NHIET, "pha nhiệt", 0.45),
                        (C_DUAN, "dự án", 0.56)]:
        fig.patches.append(Circle((x, 0.022), 0.007, transform=fig.transFigure,
                                  facecolor=mau, edgecolor="none", zorder=5))
        fig.text(x + 0.014, 0.022, ten, fontsize=9.4, color=C_CHU, va="center")
    fig.patches.append(Circle((0.645, 0.022), 0.007, transform=fig.transFigure,
                              facecolor="none", edgecolor=C_MA, linewidth=1.5,
                              linestyle=(0, (2, 2)), zorder=5))
    fig.text(0.659, 0.022, "có trên giấy, chưa bay", fontsize=9.4, color=C_CHU,
             va="center")
    luu(fig, "bay_b1_ai_bay_that.png")

# ═════════════════════════════════════════════ B2  chỗ đứt của Løfstad-Lie 2022
if lam("B2"):
    fig, ax = plt.subplots(figsize=(13.4, 6.0), facecolor=C_NEN)
    khung(ax)
    ax.set_xlim(0, 100), ax.set_ylim(0, 46)

    def hop(x, y, w, h, tren, duoi, mau, dut=False, chu_trang=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0,rounding_size=1.1",
                                    facecolor="none" if dut else mau,
                                    edgecolor=C_MA if dut else "none",
                                    linewidth=1.6,
                                    linestyle=(0, (3, 2)) if dut else "-", zorder=3))
        c = "#FFFFFF" if (chu_trang and not dut) else (C_MO if dut else C_CHU)
        ax.text(x + w / 2, y + h * 0.63, tren, fontsize=10.8, fontweight="700",
                color=c, ha="center", va="center")
        ax.text(x + w / 2, y + h * 0.26, duoi, fontsize=9.2, color=c,
                ha="center", va="center", linespacing=1.45)

    def mui(x0, x1, y, mau=C_CHU, dut=False, lw=1.7):
        ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle="-|>",
                                     mutation_scale=13, color=mau, linewidth=lw,
                                     linestyle=(0, (3, 2)) if dut else "-", zorder=4))

    ax.text(0, 43.5, "ĐỊNH LÀM", fontsize=11.0, fontweight="700", color=C_MO, va="top")
    hop(2, 30, 24, 9, "Tầng 1 · bay 80 m", "lawn mower quét nhanh\ntoàn nhà máy", C_NHIET, dut=True)
    mui(27.5, 35.5, 34.5, C_MA, dut=True)
    hop(37, 30, 22, 9, "Danh sách lỗi", "toạ độ điểm cần\nquay lại", C_NHIET, dut=True)
    mui(60.5, 68.5, 34.5, C_MA, dut=True)
    hop(70, 30, 24, 9, "Tầng 2 · bay 20 m", "ACO tính lộ trình,\nchụp lại từng điểm", C_NHIET, dut=True)

    ax.text(0, 21.5, "THỰC TẾ CHẠY", fontsize=11.0, fontweight="700", color=C_CHU, va="top")
    hop(2, 8, 24, 9, "Một chuyến · 20 m", "DJI M100 + Optris Pi 640\nMegasol, 32 phút", C_NHIET, chu_trang=True)
    mui(27.5, 35.5, 12.5, C_CHU)
    hop(37, 8, 22, 9, "93 phát hiện", "blob OpenCV · 69 đúng\n13 sai · recall 85 %", C_NHIET, chu_trang=True)
    mui(60.5, 68.5, 12.5, C_CHU)
    hop(70, 8, 24, 9, "Ước tính thời gian", "4 + 7 = 11 phút\n(tính ra, không bay)", C_NEN_B, chu_trang=True)

    # mũi tên thay thế: đầu ra 20 m được kéo lên đóng vai đầu ra tầng 80 m
    ax.add_patch(FancyArrowPatch((48, 17.6), (48, 29.4), arrowstyle="-|>",
                                 mutation_scale=14, color="#B34A20", linewidth=2.2,
                                 linestyle=(0, (4, 2)), zorder=6,
                                 connectionstyle="arc3,rad=0"))
    ax.add_patch(FancyBboxPatch((50.5, 20.2), 44, 6.4,
                                boxstyle="round,pad=0,rounding_size=1.0",
                                facecolor="#FBEDE6", edgecolor="#B34A20",
                                linewidth=1.3, zorder=5))
    ax.text(52.5, 24.1, "“are taken to represent the output of this first stage”",
            fontsize=9.9, fontweight="700", color="#8A3A17", va="center",
            style="italic", zorder=7)
    ax.text(52.5, 22.0, "tr. 1547 — đầu ra ảnh 20 m được COI NHƯ đầu ra tầng 80 m",
            fontsize=9.1, color="#8A3A17", va="center", zorder=7)

    ax.add_patch(FancyBboxPatch((2, 0.4), 92, 5.6,
                                boxstyle="round,pad=0,rounding_size=1.0",
                                facecolor="#F4F1ED", edgecolor=C_VIEN,
                                linewidth=1.0, zorder=3))
    ax.text(4, 3.2, "Họ CÓ ảnh 80 m trong tay — Hình 1 tr. 1546 so cùng một hotspot chụp ở 30 m và 80 m để chứng minh vết nhoè "
                    "gấp đôi (1,6 % → 3,3 %)\nnhưng không hề chạy bộ dò lên chính bộ ảnh đó. Độ bền phát hiện ở 80 m chỉ được lập luận "
                    "bằng vật lý cảm biến, không một con số recall nào.",
            fontsize=9.5, color=C_CHU, va="center", linespacing=1.7)
    luu(fig, "bay_b2_cho_dut_2022.png")

# ═════════════════════════════════════════════ B3  ý tưởng đã có tên từ bao giờ
if lam("B3"):
    # (năm, nhãn ngắn, mô tả, loại)  loại: ten | sangche | pv
    MOC = [
        (2015, "two-phase inspection", "Khan et al., ASCE Structures Congress\nngành NDE cầu — pha 1 phủ nhanh, pha 2 soi kỹ", "ten"),
        (2016, "US 11,156,573 B2", "Skydio — hai độ cao + so với\nbản đồ nhiệt lần trước", "sangche"),
        (2016, "RIBC / reference epoch", "Aicardi et al., ISPRS Archives XLI-B1\nđăng ký nhiều chuyến vào một chuyến mốc", "ten"),
        (2017, "explore-then-exploit", "Roberts et al., ICCV 2017\n← TÊN PHỔ BIẾN NHẤT của ý tưởng này", "ten"),
        (2017, "US 11,451,192 B2", "Acciona — CSDL định danh tấm\n+ CSDL lỗi lịch sử", "sangche"),
        (2019, "tiered view planning", "Okeson et al., Sensors 19(14)\nba mức khoảng cách 15/30/60 m", "ten"),
        (2022, "hai tầng cho PV", "Løfstad-Lie — 80 m + 20 m\nĐỀ XUẤT, chưa bay", "pv"),
        (2023, "chuẩn hoá thành một LỚP", "Maboudi et al., IEEE JSTARS\nexplore-then-exploit có Figure 2 riêng", "ten"),
        (2025, "chính nhóm đó BỎ hướng này", "Løfstad-Lie — chuyển sang\nmột độ cao + bầy 4 UAV", "pv"),
    ]
    MAU = {"ten": C_NEN_B, "sangche": "#7A5CA8", "pv": C_NHIET}
    # Ô xếp theo SLOT cách đều rồi nối về đúng mốc năm bằng một đường gấp khúc —
    # xếp thẳng theo năm thì cụm 2015-2017 đè lên nhau và nuốt mất chữ.
    TREN = [(2015, 2015.0), (2016, 2017.9), (2017, 2020.8),
            (2022, 2023.7), (2025, 2026.6)]
    DUOI = [(2016, 2016.4), (2017, 2019.4), (2019, 2022.4), (2023, 2025.4)]
    fig, ax = plt.subplots(figsize=(16.0, 7.4), facecolor=C_NEN)
    khung(ax)
    ax.set_xlim(2013.4, 2028.2), ax.set_ylim(-8.4, 8.4)
    ax.plot([2014, 2026.4], [0, 0], color=C_VIEN, linewidth=2.6, zorder=1,
            solid_capstyle="round")
    for n in range(2015, 2027, 2):
        ax.text(n, -0.55, str(n), fontsize=9.2, color=C_MO, ha="center", va="top")
        ax.plot([n, n], [-0.28, 0.28], color=C_MA, linewidth=1.0, zorder=2)

    W, H = 2.74, 3.05
    dung = {True: list(TREN), False: list(DUOI)}
    # 2016 và 2017 mỗi năm có hai mốc — không tách thì chấm vẽ sau đè mất chấm trước
    dem = {}
    for m in MOC:
        dem[m[0]] = dem.get(m[0], 0) + 1
    lech = {n: (-0.13 if dem[n] > 1 else 0.0) for n in dem}
    tren = True
    for nam, ten, mo, loai in MOC:
        for k, (n_moc, x_slot) in enumerate(dung[tren]):
            if n_moc == nam:
                dung[tren].pop(k)
                break
        else:                                   # năm không khớp slot nào -> lấy slot đầu
            n_moc, x_slot = dung[tren].pop(0)
        mau, d = MAU[loai], 1 if tren else -1
        xn = nam + lech[nam]
        lech[nam] += 0.26                       # mốc thứ hai cùng năm dịch sang phải
        y0 = d * 2.05                           # chân đường nối
        y_ho = d * 3.55                         # mép ô phía trục
        ax.plot([xn, xn], [0, y0], color=mau, linewidth=1.3, zorder=2)
        ax.plot([xn, x_slot], [y0, y_ho], color=mau, linewidth=1.3, zorder=2)
        ax.add_patch(Circle((xn, 0), 0.13, facecolor=mau, edgecolor="none", zorder=4))
        ax.add_patch(FancyBboxPatch((x_slot - W / 2, y_ho if tren else y_ho - H),
                                    W, H, boxstyle="round,pad=0,rounding_size=0.18",
                                    facecolor="#FFFFFF", edgecolor=mau,
                                    linewidth=1.3, zorder=3))
        yc = (y_ho + H / 2) if tren else (y_ho - H / 2)
        ax.text(x_slot, yc + 0.92, ten, fontsize=9.7, fontweight="700",
                color=mau, ha="center", va="center", zorder=5)
        ax.text(x_slot, yc - 0.42, mo, fontsize=8.2, color=C_CHU,
                ha="center", va="center", linespacing=1.55, zorder=5)
        tren = not tren
    for mau, ten, x in [(C_NEN_B, "tên chuẩn của phương pháp", 0.24),
                        ("#7A5CA8", "sáng chế đã cắm cờ", 0.475),
                        (C_NHIET, "riêng ngành PV", 0.635)]:
        fig.patches.append(Circle((x, 0.020), 0.007, transform=fig.transFigure,
                                  facecolor=mau, edgecolor="none", zorder=5))
        fig.text(x + 0.013, 0.020, ten, fontsize=9.4, color=C_CHU, va="center")
    luu(fig, "bay_b3_dong_thoi_gian.png")

# ═════════════════════════════════════════════ B4  ba trục còn hở
if lam("B4"):
    CONG = ["Roberts\n2017", "Okeson\n2019", "Løfstad-Lie\n2022", "Løfstad-Lie\n2025",
            "SunMap\n2023", "DỰ ÁN"]
    # 2 = có và có số, 1 = có nhưng không đo, 0 = không có
    HANG = [
        ("Bay nhiều pha / nhiều tầng", [2, 2, 1, 1, 0, 2], False),
        ("Bay THẬT cả hai pha trên hiện trường", [2, 2, 0, 1, 2, 2], False),
        ("Pha hai đo TỈ LỆ PHÁT HIỆN lỗi", [0, 0, 1, 2, 0, 2], False),
        ("Pha một làm KIỂM KÊ TÀI SẢN có mã", [0, 0, 0, 0, 1, 2], True),
        ("Nền RGB — đo bằng NHIỆT (chéo phổ)", [0, 0, 0, 0, 1, 2], True),
        ("N sortie ĐA ĐỘ CAO cùng đăng ký một nền", [0, 1, 0, 0, 0, 2], True),
    ]
    # tỉ lệ hình khớp tỉ lệ dữ liệu (86,2/47,4) thì Circle mới tròn, không bẹt thành elip
    fig, ax = plt.subplots(figsize=(13.0, 7.15), facecolor=C_NEN)
    khung(ax)
    W, H, X0, Y0 = 6.2, 5.4, 46, 4
    ax.set_xlim(0, X0 + W * len(CONG) + 3), ax.set_ylim(0, Y0 + H * len(HANG) + 11)
    for j, c in enumerate(CONG):
        cuoi = j == len(CONG) - 1
        ax.text(X0 + W * j + W / 2, Y0 + H * len(HANG) + 1.6, c,
                fontsize=9.9, fontweight="700" if cuoi else "400",
                color=C_DUAN if cuoi else C_CHU, ha="center", va="bottom",
                linespacing=1.4)
    for i, (ten, o, moi) in enumerate(HANG):
        y = Y0 + H * (len(HANG) - 1 - i)
        if moi:
            ax.add_patch(Rectangle((1, y - 0.3), X0 + W * len(CONG) - 1, H - 0.5,
                                   facecolor="#F0F5F1", edgecolor="none", zorder=1))
        ax.text(43, y + H / 2 - 0.3, ten, fontsize=10.1,
                fontweight="700" if moi else "400",
                color=C_DUAN if moi else C_CHU, ha="right", va="center")
        for j, v in enumerate(o):
            cx, cy = X0 + W * j + W / 2, y + H / 2 - 0.3
            cuoi = j == len(CONG) - 1
            mau = C_DUAN if cuoi else (C_NEN_B if v == 2 else C_MA)
            if v == 2:
                ax.add_patch(Circle((cx, cy), 1.30, facecolor=mau, edgecolor="none", zorder=3))
            elif v == 1:
                ax.add_patch(Circle((cx, cy), 1.30, facecolor="none", edgecolor=mau,
                                    linewidth=1.7, zorder=3))
                ax.plot([cx - 0.75, cx + 0.75], [cy, cy], color=mau, linewidth=1.7, zorder=4)
            else:
                ax.plot([cx - 0.8, cx + 0.8], [cy - 0.8, cy + 0.8], color=C_VIEN,
                        linewidth=1.6, zorder=3)
                ax.plot([cx - 0.8, cx + 0.8], [cy + 0.8, cy - 0.8], color=C_VIEN,
                        linewidth=1.6, zorder=3)
    ax.add_patch(Rectangle((X0 + W * 5 - 0.4, Y0 - 0.8), W + 0.8, H * len(HANG) + 1.4,
                           facecolor="none", edgecolor=C_DUAN, linewidth=1.9, zorder=5))
    ax.text(2, Y0 + H * len(HANG) + 1.6, "Ba dòng tô nền = ba trục còn trống,\nchỗ dự án chen vào",
            fontsize=9.7, fontweight="700", color=C_DUAN, ha="left", va="bottom",
            linespacing=1.6)
    for x, ten, kieu in [(0.335, "có làm VÀ có số", "dac"),
                         (0.475, "có nhưng không đo", "rong"),
                         (0.625, "không có", "x")]:
        if kieu == "dac":
            fig.patches.append(Circle((x, 0.021), 0.008, transform=fig.transFigure,
                                      facecolor=C_NEN_B, edgecolor="none", zorder=5))
        elif kieu == "rong":
            fig.patches.append(Circle((x, 0.021), 0.008, transform=fig.transFigure,
                                      facecolor="none", edgecolor=C_MA,
                                      linewidth=1.6, zorder=5))
        else:
            fig.text(x, 0.021, "✕", fontsize=10.3, color=C_VIEN, ha="center", va="center")
        fig.text(x + 0.015, 0.021, ten, fontsize=9.4, color=C_CHU, va="center")
    luu(fig, "bay_b4_ba_truc.png")
