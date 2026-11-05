#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Năm hình minh hoạ cho `TOM_TAT_CACH_CHIA_TAP.md` — chuyện chia train/test.

  C5  họ chia theo gì  hình chính: 25 bài có huấn luyện model xếp thành bảy bậc,
                       từ "không nói gì" tới "tách theo nhà máy". Đây là câu trả
                       lời trực tiếp cho câu hỏi "cách chia của họ như nào".
  C1  cơ chế rò rỉ     vì sao chia ngẫu nhiên theo ảnh thì hỏng khi bay chồng lấn.
  C2  25 ô             mỗi ô một bài, tô theo mức rủi ro. Vẽ đủ 25 ô thay vì vẽ
                       phần trăm — n nhỏ thì phần trăm nói dối.
  C3  hệ số tụt        khi ai đó đo lại không rò rỉ thì tụt bao nhiêu. Mỗi dòng quy
                       về chính nó (bẩn = 100 %) vì AP/AUROC/mAP không cùng thang.
  C4  ba cách chia     random theo ảnh → theo tấm pin → khối không gian + vùng đệm.

MÀU: bảng của `hinh_bon_cach_dinh_vi.py` trượt kiểm tra mù màu (cam #E07A3F ↔ lục
#3F8F5C chỉ cách ΔE 4,0 dưới protan, và lam #3E6E9E dưới sàn chroma nên đọc ra
xám). Ở đây dùng bản đã nắn: lam #2F6FB5, lục #3F8F5C, gỉ #C9552D — bộ ba này qua
cả sáu kiểm tra. Giữ nguyên ý nghĩa cũ: lam = train, lục = test, gỉ = nhiệt/cảnh báo.
Mức rủi ro dùng thang TUẦN TỰ một sắc (nhạt → đậm), không phải ba màu rời.

Nguồn số: `tai_lieu/bai_bao_lien_quan/CACH_CHIA_TAP.md` §1, §2, §5.

    py -3.13 ma/hinh_chia_tap.py
    py -3.13 ma/hinh_chia_tap.py --chi C5
"""
import argparse
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="chỉ dựng một hình: C1..C5, C7, C8")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/bai_bao_lien_quan/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

plt.rcParams["font.family"] = ["Segoe UI", "Arial", "sans-serif"]

C_TRAIN, C_TEST, C_NHIET = "#2F6FB5", "#3F8F5C", "#C9552D"
C_CHU, C_MO, C_VIEN, C_NEN, C_DEM = "#1F1F23", "#6B6B73", "#D8D4CE", "#FBFAF8", "#B9B4AC"
R_THAP, R_TB, R_CAO = "#F6DFD2", "#E3A87F", "#B34A20"

# 25 bài có huấn luyện model, theo mức rủi ro rò rỉ (CACH_CHIA_TAP.md §2)
CAO = ["04", "52", "50", "56", "54", "77", "09", "08", "11", "17", "57", "39", "60"]
TB = ["45", "47", "58", "23", "40", "74"]
THAP = ["55", "02", "44", "18", "21", "20"]
RUI_RO = {b: R_CAO for b in CAO} | {b: R_TB for b in TB} | {b: R_THAP for b in THAP}
CHU_O = {R_CAO: "#FFFFFF", R_TB: C_CHU, R_THAP: C_CHU}
RAO = {"02", "18", "20", "21", "44", "45", "55"}   # có biện pháp tường minh


def khung(ax):
    ax.set_xticks([]), ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_facecolor(C_NEN)


def luu(fig, ten):
    p = os.path.join(args.ra, ten)
    fig.savefig(p, bbox_inches="tight", facecolor=C_NEN, pad_inches=0.14)
    plt.close(fig)
    try:
        p = os.path.relpath(p, BASE)
    except ValueError:      # --ra tro sang o dia khac BASE
        pass
    print("->", p.replace("\\", "/"))


def chip(ax, x, y, b, w=4.4, h=3.4, fs=8.4):
    """Một ô số hiệu bài. Nền = mức rủi ro; viền đậm = bài có nói thẳng biện pháp."""
    nen, rao = RUI_RO[b], b in RAO
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.5",
                                linewidth=1.8 if rao else 0.9,
                                edgecolor=C_CHU if rao else "#00000018",
                                facecolor=nen, zorder=3))
    ax.text(x + w / 2, y + h / 2, b, fontsize=fs, fontweight="700",
            color=CHU_O[nen], ha="center", va="center", zorder=4)
    return x + w + 1.0


lam = (lambda t: not args.chi or args.chi.upper() == t)

# ═══════════════════════════════════════════════ C5  họ chia theo cái gì (chính)
if lam("C5"):
    BAC = [
        ("Không xác định được", "bài không nói đủ để biết họ chia theo cái gì", ["09", "52", "77"]),
        ("Theo CROP / TILE / PATCH", "đơn vị nhỏ hơn một cảnh — cùng một vật dễ nằm hai bên nhất",
         ["04", "17", "20", "39", "50", "56", "57", "74"]),
        ("Theo ẢNH / KHUNG nguyên", "mọi mảnh của một ảnh nằm cùng phía, nhưng cùng một vật vẫn có ở ảnh khác",
         ["08", "11", "23", "40", "54", "58"]),
        ("Theo THỜI GIAN", "90 % khung đầu / 10 % khung cuối — vẫn một cảnh duy nhất", ["60"]),
        ("Theo ĐỐI TƯỢNG VẬT LÝ", "mọi ảnh của cùng một tấm pin nằm cùng một phía", ["02"]),
        ("Theo SITE / NHÀ MÁY / TUYẾN BAY", "giữ riêng cả một địa điểm; bài 55 làm cả hai cấp",
         ["18", "21", "44", "45", "47", "55"]),
    ]

    fig, ax = plt.subplots(figsize=(11.0, 6.6), dpi=210)
    khung(ax)
    fig.patch.set_facecolor(C_NEN)
    ax.set_xlim(0, 100), ax.set_ylim(0, 74)

    ax.text(0, 71.4, "25 bài có huấn luyện model chia dữ liệu theo ĐƠN VỊ gì",
            fontsize=13.0, fontweight="700", color=C_CHU)
    ax.text(0, 68.0,
            "Sáu bậc theo đơn vị chia thực tế, lỏng nhất ở trên. Màu ô là rủi ro rò rỉ của chính bài đó, không phải của bậc.",
            fontsize=8.2, color=C_MO)

    y = 58.0
    for ten, phu, ds in BAC:
        ax.plot([3.0, 99.0], [y + 5.4, y + 5.4], color=C_VIEN, linewidth=0.9, zorder=1)
        ax.text(3.0, y + 3.4, ten, fontsize=9.4, fontweight="700", color=C_CHU, va="center")
        ax.text(3.0, y + 0.55, phu, fontsize=7.4, color=C_MO, va="center", style="italic")
        x = 52.0
        for b in ds:
            x = chip(ax, x, y + 0.5, b)
        ax.text(99.5, y + 2.2, "%d bài" % len(ds), fontsize=8.0, fontweight="700",
                color=C_MO, ha="right", va="center")
        y -= 9.4

    ax.add_patch(FancyArrowPatch((1.2, 63.8), (1.2, 5.6), arrowstyle="-|>", mutation_scale=12,
                                 linewidth=1.6, color=C_NHIET, zorder=2))
    ax.text(0.0, 34.0, "chặt dần", fontsize=8.4, fontweight="700", color=C_NHIET,
            rotation=90, ha="center", va="center")

    xl = 3.0
    for mau, ten in [(R_CAO, "rủi ro cao"), (R_TB, "trung bình"), (R_THAP, "thấp")]:
        ax.add_patch(Rectangle((xl, 0.4), 2.6, 2.2, linewidth=0.9,
                               edgecolor="#00000018", facecolor=mau, zorder=3))
        ax.text(xl + 3.5, 1.5, ten, fontsize=7.8, color=C_CHU, va="center")
        xl += 16.0
    ax.add_patch(FancyBboxPatch((xl, 0.4), 2.6, 2.2, boxstyle="round,pad=0,rounding_size=0.4",
                                linewidth=1.8, edgecolor=C_CHU, facecolor="#FFFFFF", zorder=3))
    ax.text(xl + 3.5, 1.5, "viền đậm = có nói thẳng biện pháp chống rò rỉ — 7 bài, và chỉ 7",
            fontsize=7.8, color=C_CHU, va="center")
    ax.text(3.0, -3.6, "Bài 47 chỉ dùng cụm “geographically split test set” đúng một lần, gắn cho một trong ba model của bài — "
                       "chứng cứ mỏng hơn năm bài cùng bậc.", fontsize=7.0, color=C_MO, style="italic", va="top")
    luu(fig, "chia_c5_ho_chia_theo_gi.png")

# ═══════════════════════════════════════════════════════════ C1  cơ chế rò rỉ
if lam("C1"):
    fig, ax = plt.subplots(figsize=(10.6, 5.9), dpi=210)
    khung(ax)
    ax.set_xlim(0, 100), ax.set_ylim(0, 60)
    fig.patch.set_facecolor(C_NEN)

    ax.text(0, 57.6, "Vì sao chia ngẫu nhiên theo ảnh thì hỏng",
            fontsize=12.6, fontweight="700", color=C_CHU)
    ax.text(0, 54.6, "Bay lập bản đồ chồng lấn 80 % ⇒ một tấm pin nằm trong bốn khung ảnh liên tiếp",
            fontsize=8.2, color=C_MO)

    # — bốn vệt phủ khung nhiệt, xếp so le để thấy rõ từng khung
    W, B = 29.0, 5.8          # bề rộng vệt phủ và bước bay → chồng lấn 80 %
    for k in range(4):
        x, yb = 8 + k * B, 46.4 - k * 2.3
        ax.add_patch(Rectangle((x, yb), W, 1.8, linewidth=1.2, edgecolor=C_NHIET,
                               facecolor=C_NHIET, alpha=0.30, zorder=3))
        ax.text(x - 0.9, yb + 0.9, "f%d" % (k + 1), fontsize=7.6, color=C_NHIET,
                fontweight="700", ha="right", va="center")
    ax.annotate("", xy=(8, 50.4), xytext=(8 + W, 50.4),
                arrowprops=dict(arrowstyle="<->", color=C_MO, lw=1.0))
    ax.text(8 + W / 2, 51.2, "vệt phủ một khung ảnh nhiệt", fontsize=7.0, color=C_MO, ha="center")

    # — hàng tấm pin; tấm nổi bật nằm trong giao của cả bốn vệt phủ
    y0, hp, wp, pitch, nb = 33.0, 5.2, 6.4, 7.4, 3
    for i in range(9):
        x, la = 8 + i * pitch, i == nb
        ax.add_patch(Rectangle((x, y0), wp, hp, linewidth=2.0 if la else 1.1,
                               edgecolor=C_NHIET if la else "#9BA3AC",
                               facecolor="#FFF3EC" if la else "#EEF1F4", zorder=3))
    cx = 8 + nb * pitch + wp / 2
    ax.plot([cx, cx], [y0 + hp, 47.6], color=C_NHIET, linewidth=1.2,
            linestyle=(0, (3, 2.5)), zorder=4)
    ax.text(6.6, y0 + hp / 2, "dãy pin", fontsize=7.8, color=C_MO, ha="right", va="center")
    ax.text(cx + 5.0, y0 - 2.4, "một tấm pin vật lý — cả bốn khung đều nhìn thấy nó",
            fontsize=7.6, color=C_NHIET, fontweight="700", ha="left", va="center")

    # — bốn view của chính tấm đó, đã bị phép chia ngẫu nhiên rải ra hai bên
    ycard, hc, wc = 17.0, 7.2, 9.6
    chia = [C_TRAIN, C_TEST, C_TRAIN, C_TRAIN]
    for k in range(4):
        x = 10 + k * (wc + 3.4)
        ax.add_patch(FancyBboxPatch((x, ycard), wc, hc, boxstyle="round,pad=0,rounding_size=0.7",
                                    linewidth=1.8, edgecolor=chia[k], facecolor="#FFFFFF", zorder=3))
        ax.add_patch(Rectangle((x + 2.4, ycard + 1.8), wc - 4.8, hc - 3.6,
                               linewidth=1.3, edgecolor=C_NHIET, facecolor="#FFF3EC", zorder=4))
        ax.text(x + wc / 2, ycard + hc + 1.2, "f%d" % (k + 1), fontsize=7.6,
                color=C_CHU, fontweight="700", ha="center")
        ax.add_patch(FancyArrowPatch((cx, y0 - 3.6), (x + wc / 2, ycard + hc + 2.7),
                                     arrowstyle="-", linewidth=0.8, color=C_VIEN, zorder=1))
    ax.text(8.4, ycard + hc / 2, "cùng một tấm,\nbốn góc nhìn", fontsize=7.6,
            color=C_MO, ha="right", va="center", linespacing=1.5)

    # — hai rổ
    yb = 3.4
    for x0, w, mau, ten, dsc in [(10, 32.6, C_TRAIN, "TẬP TRAIN", "f1 · f3 · f4"),
                                 (56, 22.6, C_TEST, "TẬP TEST", "f2")]:
        ax.add_patch(FancyBboxPatch((x0, yb), w, 8.0, boxstyle="round,pad=0,rounding_size=0.9",
                                    linewidth=1.9, edgecolor=mau, facecolor="#FFFFFF", zorder=3))
        ax.text(x0 + w / 2, yb + 5.2, ten, fontsize=8.6, fontweight="700",
                color=mau, ha="center", va="center")
        ax.text(x0 + w / 2, yb + 2.4, dsc, fontsize=7.6, color=C_CHU, ha="center", va="center")
    for k in range(4):
        x = 10 + k * (wc + 3.4) + wc / 2
        ax.add_patch(FancyArrowPatch((x, ycard - 0.5), (26.3 if chia[k] == C_TRAIN else 67.3, yb + 8.6),
                                     arrowstyle="-|>", mutation_scale=10, linewidth=1.3,
                                     color=chia[k], connectionstyle="arc3,rad=0.12", zorder=2))

    ax.add_patch(FancyBboxPatch((82.0, yb), 17.5, 15.6, boxstyle="round,pad=0,rounding_size=0.9",
                                linewidth=1.7, edgecolor=C_NHIET, facecolor="#FFF3EC", zorder=3))
    ax.text(90.8, yb + 12.8, "Kết quả", fontsize=8.2, fontweight="700",
            color=C_NHIET, ha="center", va="center")
    ax.text(90.8, yb + 6.2, "Cùng một tấm pin\nnằm CẢ HAI BÊN.\nModel không dự đoán,\nnó nhớ lại.",
            fontsize=7.6, color=C_CHU, ha="center", va="center", linespacing=1.65)

    ax.text(0, 0.4,
            "Bài 02 đo được 38,95 ảnh cho mỗi tấm pin, bài 55 đo 39,4, bài 01 đo 64,1 — và cả ba đều gọi số đó là "
            "“những góc nhìn tăng cường khác nhau”.",
            fontsize=7.3, color=C_MO, style="italic")
    luu(fig, "chia_c1_co_che_ro_ri.png")

# ═══════════════════════════════════════════════════════════ C2  ô đơn vị 25 bài
if lam("C2"):
    o = CAO + TB + THAP
    fig, ax = plt.subplots(figsize=(10.0, 4.9), dpi=210)
    khung(ax)
    ax.set_xlim(0, 100), ax.set_ylim(0, 50)
    fig.patch.set_facecolor(C_NEN)

    ax.text(0, 47.6, "25 bài có huấn luyện model, xếp theo rủi ro rò rỉ",
            fontsize=12.6, fontweight="700", color=C_CHU)
    ax.text(0, 44.6,
            "Mỗi ô một bài, số trong ô là số hiệu bài trong kho. Vẽ đủ 25 ô chứ không vẽ phần trăm — n nhỏ thì phần trăm nói dối.",
            fontsize=8.2, color=C_MO)

    s, gap = 9.2, 1.5
    for i, b in enumerate(o):
        x = 1.0 + (i % 9) * (s + gap)
        y = 31.0 - (i // 9) * (s + gap)
        nen, rao = RUI_RO[b], b in RAO
        ax.add_patch(FancyBboxPatch((x, y), s, s, boxstyle="round,pad=0,rounding_size=0.8",
                                    linewidth=2.4 if rao else 1.0,
                                    edgecolor=C_CHU if rao else "#00000018",
                                    facecolor=nen, zorder=3))
        ax.text(x + s / 2, y + s / 2, b, fontsize=9.8, fontweight="700",
                color=CHU_O[nen], ha="center", va="center", zorder=4)

    for k, (mau, ten, dem) in enumerate([(R_CAO, "Rủi ro CAO", "13 bài"),
                                         (R_TB, "Trung bình", "6 bài"),
                                         (R_THAP, "Thấp", "6 bài")]):
        x = 1.0 + k * 23.0
        ax.add_patch(Rectangle((x, 2.6), 3.0, 3.0, linewidth=1.0,
                               edgecolor="#00000018", facecolor=mau, zorder=3))
        ax.text(x + 4.2, 4.8, ten, fontsize=8.2, fontweight="700", color=C_CHU, va="center")
        ax.text(x + 4.2, 2.1, dem, fontsize=7.6, color=C_MO, va="center")
    ax.add_patch(FancyBboxPatch((70.0, 2.6), 3.0, 3.0, boxstyle="round,pad=0,rounding_size=0.4",
                                linewidth=2.4, edgecolor=C_CHU, facecolor="#FFFFFF", zorder=3))
    ax.text(74.2, 4.8, "viền đậm = có nói thẳng biện pháp", fontsize=8.2, fontweight="700",
            color=C_CHU, va="center")
    ax.text(74.2, 2.1, "7 bài — và chỉ 7", fontsize=7.6, color=C_MO, va="center")
    luu(fig, "chia_c2_25_bai.png")

# ═════════════════════════════════════════════════════════════ C3  hệ số tụt
if lam("C3"):
    # (nhan, mo_ta, ctx, diem hoac dai, trung_vi, kieu)
    A = [("bài 48", "AP 79,7 → 65,4", "khử trùng lặp ảnh, giữ nguyên mọi thứ khác  ·  tr.11",
          (0.8206, 0.8206), None, "diem")]
    B = [("bài 55", "9 tác vụ chéo nhà máy", "quy về mốc cùng nguồn  ·  tr.8",
          (0.75, 1.03), 0.93, "dai"),
         ("bài 45", "6 phép đo, 3 phương pháp", "nhà máy chưa thấy  ·  Bảng 2, tr.25",
          (0.7175, 1.1589), 0.992, "dai")]
    C = [("CỦA ANH", "mAP 0,965 → ~0,62–0,70", "ước tính, CHƯA CÓ phép đo theo khối không gian",
          (0.6425, 0.7254), None, "uoc")]

    fig, ax = plt.subplots(figsize=(10.4, 5.4), dpi=210)
    khung(ax)
    fig.patch.set_facecolor(C_NEN)
    ax.set_xlim(0.58, 1.36), ax.set_ylim(-24, 100)

    ax.text(0.58, 96.5, "“Đo lại cho sạch” — gần như chưa ai làm",
            fontsize=12.6, fontweight="700", color=C_CHU)
    ax.text(0.58, 91.0,
            "Hai loại con số hay bị trộn. Chỉ nhóm A trả lời đúng câu hỏi “bỏ rò rỉ thì tụt bao nhiêu”. "
            "Mỗi dòng quy về chính nó (số gốc = 100 %).",
            fontsize=8.0, color=C_MO)

    for v in [0.7, 0.8, 0.9, 1.0, 1.1]:
        ax.plot([v, v], [2.0, 82.0], color=C_VIEN, linewidth=0.9, zorder=1)
        ax.text(v, -3.0, "%d %%" % round(v * 100), fontsize=7.4, color=C_MO, ha="center", va="bottom")
    ax.plot([1.0, 1.0], [2.0, 82.0], color="#B3AEA6", linewidth=1.4, zorder=1)
    ax.text(1.0, 84.0, "không đổi", fontsize=7.0, color=C_MO, ha="center")

    NHOM = [("A · Bỏ rò rỉ rồi đo lại — cùng model, cùng tác vụ", A, C_NHIET),
            ("B · Đổi sang nhà máy chưa thấy — tổng quát hoá, KHÔNG phải rò rỉ", B, "#8A8F96"),
            ("Của anh — chưa đo", C, C_NHIET)]
    y = 76.0
    for ten, hang, mau_de in NHOM:
        ax.text(0.58, y, ten, fontsize=8.6, fontweight="700", color=mau_de, va="center")
        y -= 9.0
        for nhan, mo, ctx, (lo, hi), tv, kieu in hang:
            anh = kieu == "uoc"
            mau = C_NHIET if (kieu in ("diem", "uoc")) else "#9AA1A8"
            if kieu == "diem":
                ax.plot([lo], [y], marker="o", markersize=10, color=mau, zorder=4)
                ax.text(lo, y + 5.2, ("x%.2f" % lo).replace(".", ","), fontsize=9.2,
                        fontweight="700", color=C_CHU, ha="center")
            else:
                ax.plot([lo, hi], [y, y], color=mau, linewidth=7.5,
                        alpha=0.30 if not anh else 0.22, solid_capstyle="round", zorder=2)
                if anh:
                    ax.plot([lo, hi], [y, y], color=mau, linewidth=2.0, zorder=3,
                            linestyle=(0, (4, 2.6)), solid_capstyle="butt")
                for v in (lo, hi):
                    ax.plot([v], [y], marker="|", markersize=11, markeredgewidth=2.2,
                            color=mau, zorder=4)
                if tv is not None:
                    ax.plot([tv], [y], marker="o", markersize=9, color=mau, zorder=5)
                    ax.text(tv, y + 5.2, ("trung vị x%.2f" % tv).replace(".", ","),
                            fontsize=8.0, fontweight="700", color=C_CHU, ha="center")
                ax.text((lo + hi) / 2, y - 5.4, ("x%.2f–%.2f" % (lo, hi)).replace(".", ","),
                        fontsize=7.6, color=C_MO if not anh else C_NHIET,
                        fontweight="600" if anh else "400", ha="center")
            ax.text(1.19, y + 2.0, nhan, fontsize=8.4, fontweight="700",
                    color=C_NHIET if anh else C_CHU, ha="left", va="center")
            ax.text(1.19, y - 1.4, mo, fontsize=7.0, color=C_MO, ha="left", va="center")
            ax.text(1.19, y - 4.4, ctx, fontsize=6.5, color=C_MO, ha="left", va="center", style="italic")
            y -= 13.5
        y -= 1.5

    ax.text(0.58, -10.5,
            "Bài 69 cũng thuộc nhóm A nhưng đo sai số nên đi chiều ngược: RMSE 0,021 → 0,039 dưới leave-cluster-out, tức sai số x1,86 (tr.7).\n"
            "Bài 45 chỉ nhánh YOLO tụt (module x0,86, khe bench x0,72); nhánh Edge và U-Net phần lớn ĐI LÊN — 4/6 phép đo trong Bảng 2 tăng.\n"
            "Kết luận đọc được: trong cả lô chỉ có MỘT phép đo thật sự sạch (bài 48). Chỗ trống đó là chỗ để bài của anh chen vào.",
            fontsize=7.2, color=C_MO, va="top", linespacing=1.75)
    luu(fig, "chia_c3_he_so_tut.png")

# ═══════════════════════════════════════════════════════════ C4  ba cách chia
if lam("C4"):
    rng = np.random.default_rng(7)
    NC, NR = 9, 7
    fig, axs = plt.subplots(1, 3, figsize=(11.4, 3.25), dpi=210)
    fig.patch.set_facecolor(C_NEN)
    fig.subplots_adjust(wspace=0.10, bottom=0.19, top=0.99)

    TIEU = [("(a) ngẫu nhiên theo ảnh", "cùng một tấm có view ở cả hai bên", C_NHIET),
            ("(b) theo tấm pin vật lý", "hết trùng view, tấm kề nhau vẫn tương quan", "#9A7420"),
            ("(c) khối không gian + vùng đệm", "tấm test cách train ít nhất một vệt phủ", C_TEST)]

    for k, ax in enumerate(axs):
        khung(ax)
        ax.set_xlim(-0.6, NC + 0.6), ax.set_ylim(-2.3, NR + 2.0)
        ax.set_aspect("equal")
        ten, phu, mau_t = TIEU[k]
        ax.text(-0.6, NR + 1.30, ten, fontsize=9.4, fontweight="700", color=C_CHU)
        ax.text(-0.6, NR + 0.45, phu, fontsize=7.3, color=mau_t)

        cot_test, cot_dem = set(range(6, NC)), {5}
        nn = rng.random((NR, NC))
        for r in range(NR):
            for c in range(NC):
                x, y = c, NR - 1 - r
                if k == 2:
                    mau = C_DEM if c in cot_dem else (C_TEST if c in cot_test else C_TRAIN)
                    ax.add_patch(Rectangle((x + .09, y + .09), .82, .82, linewidth=.8,
                                           edgecolor="#00000012", facecolor=mau, zorder=3))
                elif k == 1:
                    mau = C_TEST if nn[r, c] > 0.72 else C_TRAIN
                    ax.add_patch(Rectangle((x + .09, y + .09), .82, .82, linewidth=.8,
                                           edgecolor="#00000012", facecolor=mau, zorder=3))
                else:
                    ax.add_patch(Rectangle((x + .09, y + .09), .82, .82, linewidth=.8,
                                           edgecolor=C_VIEN, facecolor="#FFFFFF", zorder=3))
                    for j in range(4):
                        dx, dy = .27 + (j % 2) * .32, .27 + (j // 2) * .32
                        ax.plot([x + dx], [y + dy], marker="s", markersize=3.6,
                                color=C_TEST if rng.random() > 0.72 else C_TRAIN, zorder=4)

        if k == 0:
            ax.text(NC / 2 - 0.5, -0.6, "bốn chấm trong một ô = bốn khung ảnh nhìn thấy tấm đó",
                    fontsize=7.0, color=C_MO, ha="center", va="top")
        if k == 2:
            ax.add_patch(Rectangle((5.05, -0.62), .9, .30, linewidth=0,
                                   facecolor=C_DEM, zorder=3))
            ax.text(5.5, -1.15, "vùng đệm", fontsize=7.0, color=C_MO, ha="center", va="top")

    for mau, ten, x in [(C_TRAIN, "train", 0.352), (C_TEST, "test", 0.462), (C_DEM, "vùng đệm", 0.560)]:
        fig.patches.append(Rectangle((x, 0.030), 0.015, 0.040, transform=fig.transFigure,
                                     facecolor=mau, edgecolor="#00000018", linewidth=.8, zorder=5))
        fig.text(x + 0.021, 0.050, ten, fontsize=8.2, color=C_CHU, va="center")
    luu(fig, "chia_c4_ba_cach.png")

# ════════════════════════════════════════ C7  hướng dẫn chia tập cho bộ 598 ảnh
# Thay cho C6 cũ (đã bỏ). C6 sai hai chỗ: vẽ đệm ăn vào cả khối test — làm các tấm
# sát ranh giới KHÔNG BAO GIỜ được đánh giá ở bất kỳ vòng nào, mất ~42 % nhà máy —
# và ghi "trung bình ± độ lệch chuẩn của 6 vòng", trong khi lớp Bypass chỉ có 31 ca
# nên ba khối chỉ chứa đúng 1 ca, đo theo vòng thì ra 0 % hoặc 100 %.
#
# Số liệu vẽ trên hình đều đếm thật:
#   ranh giới khối   np.quantile(x_tam, i/6)  -> 55,7 / 84,4 / 113,6 / 141,4 / 170,4 m
#   tấm mỗi khối     1.079 (cắt theo SỐ TẤM bằng nhau nên bề rộng khác nhau)
#   lỗi mỗi khối     tam_loi_ban_giao.csv, 438 tấm lỗi
#   đệm              18,4 m = cạnh dài vệt phủ khung nhiệt 640x512 @ GSD 2,871 cm/px
if lam("C7"):
    import matplotlib.gridspec as gridspec

    L, W, NDAY, NKHOI, FOOT = 217.2, 93.0, 25, 6, 18.4
    CANH = [0.0, 55.7, 84.4, 113.6, 141.4, 170.4, L]
    NTAM = [1079, 1079, 1078, 1079, 1079, 1079]
    NLOI = [49, 93, 61, 92, 82, 61]
    NBYP = [7, 14, 7, 1, 1, 1]
    MAT = [652, 1243, 1393, 1409, 1312, 702]          # tấm train rơi vào đệm mỗi vòng
    C_VAL = "#C9552D"
    MAU = {"train": C_TRAIN, "val": C_VAL, "test": C_TEST}
    TEN = {"train": "TRAIN", "val": "VAL", "test": "TEST"}

    def vong(i):
        vt = i + 1 if i + 1 < NKHOI else i - 1
        return ["test" if k == i else ("val" if k == vt else "train") for k in range(NKHOI)]

    fig = plt.figure(figsize=(11.2, 12.4), dpi=200)
    fig.patch.set_facecolor(C_NEN)
    gs = gridspec.GridSpec(3, 1, height_ratios=[1.00, 0.80, 1.05], hspace=0.26,
                           left=0.05, right=0.975, top=0.955, bottom=0.035)
    fig.text(0.05, 0.982, "Chia train / val / test cho bộ 598 ảnh nhiệt — ba bước",
             fontsize=14.0, fontweight="700", color=C_CHU, va="center")

    # ─────────────────────────────── (a) bước 1–2: cắt khối theo SỐ TẤM bằng nhau
    ax = fig.add_subplot(gs[0]); khung(ax); ax.set_aspect("equal")
    ax.set_xlim(-6, L + 6), ax.set_ylim(-46, W + 26)
    ax.text(-6, W + 20, "Bước 1–2 · Gán panel_id, rồi cắt trục dài thành 6 khối BẰNG NHAU VỀ SỐ TẤM",
            fontsize=10.6, fontweight="700", color=C_CHU, va="bottom")
    ax.text(-6, W + 13.5, "Cắt theo số tấm chứ không theo bề rộng — nhà máy không phủ đều nên khối rộng hẹp khác nhau.",
            fontsize=7.8, color=C_MO, va="bottom")
    buoc, cao = W / NDAY, 1.76
    for r in range(NDAY):
        y = buoc * r + (buoc - cao) / 2
        for k in range(NKHOI):
            ax.add_patch(Rectangle((CANH[k], y), CANH[k + 1] - CANH[k], cao, linewidth=0,
                                   facecolor="#9BB6D4" if k % 2 == 0 else "#B8CBE0", zorder=3))
    for c in CANH[1:-1]:
        ax.plot([c, c], [-4, W + 4], color=C_CHU, linewidth=1.5, zorder=5)
    for k in range(NKHOI):
        xc = (CANH[k] + CANH[k + 1]) / 2
        ax.text(xc, W + 7.0, "K%d" % (k + 1), fontsize=9.6, fontweight="700",
                color=C_CHU, ha="center", va="center")
        ax.text(xc, -9.0, "%.1f m" % (CANH[k + 1] - CANH[k]), fontsize=7.2, color=C_MO, ha="center")
        ax.text(xc, -15.5, "%d tấm" % NTAM[k], fontsize=7.8, fontweight="700", color=C_CHU, ha="center")
        ax.text(xc, -21.5, "%d lỗi" % NLOI[k], fontsize=7.6, color=C_CHU, ha="center")
        ax.text(xc, -27.5, "%d Bypass" % NBYP[k], fontsize=7.6,
                fontweight="700" if NBYP[k] <= 1 else "400",
                color=C_NHIET if NBYP[k] <= 1 else C_MO, ha="center")
    ax.plot([0, 50], [-36, -36], color=C_CHU, linewidth=2.0)
    ax.text(25, -38.5, "50 m", fontsize=7.4, color=C_CHU, ha="center", va="top")
    ax.text(60, -37.5,
            "217 × 93 m · 1,99 ha · 25 dãy · 6.473 tấm · 438 tấm lỗi\n"
            "Ba khối chỉ có 1 ca Bypass — lý do KHÔNG báo chỉ số theo từng vòng (xem bước 5).",
            fontsize=7.6, color=C_MO, va="center", linespacing=1.7)

    # ─────────────────────────────── (b) bước 3–4: đệm chỉ cắt bên train
    ax = fig.add_subplot(gs[1]); khung(ax); ax.set_aspect("equal")
    ZL, ZR, ZH = -34.0, 26.0, 30.0                     # cửa sổ phóng to quanh một ranh giới
    ax.set_xlim(ZL - 3, ZR + 30), ax.set_ylim(-30, ZH + 22)
    ax.text(ZL - 3, ZH + 15, "Bước 3–4 · Vùng đệm 18,4 m chỉ cắt bên TRAIN — khối test giữ nguyên toàn bộ",
            fontsize=10.6, fontweight="700", color=C_CHU, va="bottom")
    ax.text(ZL - 3, ZH + 8.6, "Phóng to quanh một ranh giới. Đây là chỗ bản vẽ trước làm sai: cắt cả hai phía thì tấm sát ranh giới không bao giờ được đánh giá.",
            fontsize=7.8, color=C_MO, va="bottom")
    b2, c2, nd2 = 30.0 / 7, 1.76, 7
    for r in range(nd2):
        y = b2 * r + (b2 - c2) / 2
        x = ZL
        while x < ZR:
            if x >= 0:
                mau, alp = C_TEST, 1.0                    # test: giữ nguyên tất cả
            elif x >= -FOOT:
                mau, alp = C_DEM, 0.55                    # đệm: bỏ, cắt từ train
            else:
                mau, alp = C_TRAIN, 1.0
            ax.add_patch(Rectangle((x, y), 1.5, c2, linewidth=0, facecolor=mau, alpha=alp, zorder=3))
            x += 1.8
    ax.plot([0, 0], [-4, ZH + 3], color=C_CHU, linewidth=1.8, zorder=6)
    ax.text(1.5, -4.0, "KHỐI TEST — giữ nguyên toàn bộ", fontsize=8.4,
            fontweight="700", color=C_TEST, ha="left", va="top")
    ax.text(-FOOT / 2, -4.0, "ĐỆM", fontsize=8.0, fontweight="700", color=C_MO,
            ha="center", va="top")
    ax.text(ZL + 8, -4.0, "TRAIN", fontsize=8.4, fontweight="700", color=C_TRAIN,
            ha="center", va="top")
    ax.annotate("", xy=(-FOOT, -12.5), xytext=(0, -12.5),
                arrowprops=dict(arrowstyle="<->", color=C_CHU, lw=1.2))
    ax.text(-FOOT / 2, -17.0, "18,4 m", fontsize=8.0, fontweight="700", color=C_CHU,
            ha="center", va="top")
    ax.add_patch(Rectangle((-14.0, -1.2), FOOT, ZH + 2.4, linewidth=1.8, edgecolor=C_NHIET,
                           facecolor=C_NHIET, alpha=0.11, zorder=6))
    ax.text(-14.0 + FOOT / 2, ZH + 2.4, "một khung ảnh nhiệt, đúng tỉ lệ", fontsize=7.4,
            fontweight="700", color=C_NHIET, ha="center", va="bottom", zorder=7)
    ax.text(ZR + 2.0, ZH / 2 + 4,
            "Khung ảnh nhiệt rộng 18,4 m (vẽ đúng tỉ lệ, ô cam).\n"
            "Khung nào chứa tấm test thì vươn xa nhất 18,4 m\n"
            "sang trái — mà 18,4 m đó đã bị dọn sạch tấm train.\n"
            "Vậy không khung nào thấy đồng thời hai bên.",
            fontsize=7.8, color=C_CHU, va="center", linespacing=1.75)
    ax.text(ZR + 2.0, ZH / 2 - 14,
            "Giá phải trả nằm hết bên train: mất 652–1.409 tấm\nmỗi vòng trên ~5.400. Test không mất tấm nào.",
            fontsize=7.6, color=C_MO, va="center", linespacing=1.7, style="italic")

    # ─────────────────────────────── (c) bước 5: gộp out-of-fold
    ax = fig.add_subplot(gs[2]); khung(ax)
    ax.set_xlim(-15, 150), ax.set_ylim(-20, 86)
    ax.text(-15, 80, "Bước 5 · Chạy 6 vòng rồi GỘP dự đoán out-of-fold thành MỘT tập đánh giá",
            fontsize=10.6, fontweight="700", color=C_CHU, va="bottom")
    ax.text(-15, 73.5, "Không tính chỉ số cho từng vòng rồi lấy trung bình — làm thế thì lớp Bypass có vòng chỉ đo trên 1 ca.",
            fontsize=7.8, color=C_MO, va="bottom")
    ow, oh, gap = 13.0, 7.4, 1.5
    for k in range(NKHOI):
        ax.text(1 + k * (ow + gap) + ow / 2, 66.5, "K%d" % (k + 1), fontsize=8.0,
                fontweight="700", color=C_MO, ha="center")
    for i in range(NKHOI):
        v, y = vong(i), 56.5 - i * (oh + 1.7)
        ax.text(-1.5, y + oh / 2, "vòng %d" % (i + 1), fontsize=8.0, fontweight="700",
                color=C_CHU, ha="right", va="center")
        for k in range(NKHOI):
            x = 1 + k * (ow + gap)
            ax.add_patch(FancyBboxPatch((x, y), ow, oh, boxstyle="round,pad=0,rounding_size=0.6",
                                        linewidth=0, facecolor=MAU[v[k]], zorder=3))
            ax.text(x + ow / 2, y + oh / 2, TEN[v[k]], fontsize=7.0, fontweight="700",
                    color="#FFFFFF", ha="center", va="center", zorder=4)
        ax.text(88.5, y + oh / 2, "%d tấm · %d lỗi" % (NTAM[i], NLOI[i]), fontsize=7.0,
                color=C_MO, ha="left", va="center")
        ax.add_patch(FancyArrowPatch((107.0, y + oh / 2), (113.5, 30.0), arrowstyle="-|>",
                                     mutation_scale=9, linewidth=1.1, color=C_TEST,
                                     connectionstyle="arc3,rad=%.2f" % (0.20 - i * 0.07), zorder=2))
    ax.add_patch(FancyBboxPatch((115.0, 4.0), 34.0, 50.0, boxstyle="round,pad=0,rounding_size=1.2",
                                linewidth=2.0, edgecolor=C_TEST, facecolor="#FFFFFF", zorder=3))
    ax.text(132.0, 48.0, "TẬP ĐÁNH GIÁ GỘP", fontsize=8.8, fontweight="700",
            color=C_TEST, ha="center", va="center")
    ax.text(132.0, 26.0,
            "6.473 tấm\n438 lỗi\nđủ cả 31 Bypass\n\nmỗi tấm đúng MỘT dự đoán,\ntừ model chưa từng thấy\nkhối của tấm đó",
            fontsize=7.8, color=C_CHU, ha="center", va="center", linespacing=1.55)
    xl = 1.0
    for k_, t_ in [("train", "train — 4 khối"), ("val", "val — chọn epoch & ngưỡng"),
                   ("test", "test — gộp vào tập đánh giá")]:
        ax.add_patch(Rectangle((xl, 0.5), 3.2, 3.2, linewidth=0, facecolor=MAU[k_], zorder=3))
        ax.text(xl + 4.4, 2.1, t_, fontsize=7.8, color=C_CHU, va="center")
        xl += 31.0
    ax.text(-15, -6.0,
            "Tính mAP / recall / precision MỘT LẦN trên tập gộp. Độ lệch giữa các vòng chỉ dùng làm chú thích độ ổn định, và chỉ cho hai lớp đông.\n"
            "Bypass vẫn chỉ 31 ca (khoảng tin cậy recall ±9 điểm) — báo số đếm “bắt được k/31” kèm khoảng tin cậy, đừng chỉ báo phần trăm.",
            fontsize=7.4, color=C_MO, va="top", linespacing=1.8, style="italic")
    luu(fig, "chia_c7_huong_dan_chia.png")


# ═══════════════════════════════ C8  hướng dẫn chia tập, vẽ trên ORTHO RGB THẬT
# Cùng nội dung C7 nhưng nền là ảnh trực giao thật thay vì sơ đồ. Ảnh đọc ở mức
# giảm 1/4 (IMREAD_REDUCED_COLOR_4) rồi cắt theo `cua_so` của nhan_tam_pin_moi.json,
# nên toạ độ đa giác tấm pin chia 4 là khớp thẳng — đã kiểm bằng cách chấm thử.
#   1 px (sau khi giảm 1/4) = 0,0383 m
#   ranh giới khối 55,7 / 84,4 / 113,6 / 141,4 / 170,4 m
#   đệm 18,4 m = 481 px
if lam("C8"):
    import csv
    import io as _io
    import json as _json
    import matplotlib.gridspec as gridspec
    import cv2

    ORT = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export/ortho.tif")
    CS = _json.load(_io.open(os.path.join(BASE, "ket_qua/nhan_tam_pin_moi.json"),
                            encoding="utf-8"))["cua_so"]
    im = cv2.imread(ORT, cv2.IMREAD_REDUCED_COLOR_4)
    c0, r0, gw, gh = CS["c0"] // 4, CS["r0"] // 4, CS["gw"] // 4, CS["gh"] // 4
    base = cv2.cvtColor(im[r0:r0 + gh, c0:c0 + gw], cv2.COLOR_BGR2RGB)
    H, Wp = base.shape[:2]
    L_M = 217.2
    MPP = L_M / Wp                                  # mét trên mỗi pixel
    CANH_M = [0.0, 55.7, 84.4, 113.6, 141.4, 170.4, L_M]
    CANH = [c / MPP for c in CANH_M]
    FOOT_PX = 18.4 / MPP
    NTAM = [1079, 1079, 1078, 1079, 1079, 1079]
    NLOI = [49, 93, 61, 92, 82, 61]
    NBYP = [7, 14, 7, 1, 1, 1]
    C_VAL = "#C9552D"
    MAU = {"train": C_TRAIN, "val": C_VAL, "test": C_TEST}
    TEN = {"train": "TRAIN", "val": "VAL", "test": "TEST"}
    VAI = ["test", "val", "train", "train", "train", "train"]     # vòng 1

    def hex2rgb(h):
        return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)

    def to_phu(anh, x0, x1, mau, a=0.42):
        x0, x1 = max(0, int(x0)), min(anh.shape[1], int(x1))
        if x1 <= x0:
            return
        v = anh[:, x0:x1].astype(float)
        anh[:, x0:x1] = np.clip(v * (1 - a) + hex2rgb(mau) * a, 0, 255).astype(np.uint8)

    def to_dem(anh, x0, x1):
        x0, x1 = max(0, int(x0)), min(anh.shape[1], int(x1))
        if x1 <= x0:
            return
        v = anh[:, x0:x1].astype(float)
        xam = v.mean(axis=2, keepdims=True)
        anh[:, x0:x1] = np.clip(xam * 0.55 + 150 * 0.45, 0, 255).astype(np.uint8)

    # ── ảnh (a): tô cả sáu khối, rồi phủ đệm lên hai ranh giới của vòng 1
    A = base.copy()
    for k in range(6):
        to_phu(A, CANH[k], CANH[k + 1], MAU[VAI[k]])
    ranh1 = []
    for k in range(1, 6):
        if VAI[k - 1] == VAI[k]:
            continue
        # cắt về phía KHÔNG phải test; nếu không bên nào là test thì cắt bên train
        if VAI[k - 1] == "test":
            x0, x1, phia = CANH[k], CANH[k] + FOOT_PX, "phai"
        elif VAI[k] == "test":
            x0, x1, phia = CANH[k] - FOOT_PX, CANH[k], "trai"
        elif VAI[k] == "train":
            x0, x1, phia = CANH[k], CANH[k] + FOOT_PX, "phai"
        else:
            x0, x1, phia = CANH[k] - FOOT_PX, CANH[k], "trai"
        to_dem(A, x0, x1)
        ranh1.append((x0 + x1) / 2)

    # ── vị trí lỗi để chấm lên ảnh (a)
    Rw = list(csv.DictReader(_io.open(os.path.join(BASE, "ket_qua/tam_loi_ban_giao.csv"),
                                     encoding="utf-8-sig")))
    fx = np.array([(float(r["lon"]) - CS["lon0"]) / (CS["lon1"] - CS["lon0"]) * Wp for r in Rw])
    fy = np.array([(float(r["lat"]) - CS["lat0"]) / (CS["lat1"] - CS["lat0"]) * H for r in Rw])
    byp = np.array([r["tinh_trang"] == "Bypass" for r in Rw])

    fig = plt.figure(figsize=(11.4, 9.6), dpi=200)
    fig.patch.set_facecolor(C_NEN)
    gs = gridspec.GridSpec(2, 1, height_ratios=[1.0, 0.80], hspace=0.30,
                           left=0.035, right=0.985, top=0.925, bottom=0.03)
    fig.text(0.035, 0.972, "Chia khối trên ảnh trực giao thật — vòng 1 trong 6",
             fontsize=14.0, fontweight="700", color=C_CHU, va="center")
    fig.text(0.035, 0.949,
             "Nền là orthomosaic RGB của chính chuyến bay. Mọi ranh giới và vùng đệm vẽ đúng tỉ lệ mặt đất.",
             fontsize=8.4, color=C_MO, va="center")

    # ───────────────────────────────────────────────── (a)
    ax = fig.add_subplot(gs[0]); khung(ax)
    ax.imshow(A, interpolation="bilinear")
    ax.set_xlim(0, Wp), ax.set_ylim(H, 0)
    ax.plot(fx[~byp], fy[~byp], "o", markersize=1.9, color="#FFFFFF",
            markeredgewidth=0, alpha=0.80, zorder=4)
    ax.plot(fx[byp], fy[byp], "o", markersize=5.2, color="#FFE14D",
            markeredgecolor="#3A2E00", markeredgewidth=0.8, zorder=5)
    for k in range(1, 6):
        ax.plot([CANH[k], CANH[k]], [0, H], color="#FFFFFF", linewidth=1.7, zorder=6)
    for k in range(6):
        xc = (CANH[k] + CANH[k + 1]) / 2
        ax.text(xc, H * 0.062, "K%d · %s" % (k + 1, TEN[VAI[k]]), fontsize=8.6,
                fontweight="700", color="#FFFFFF", ha="center", va="center", zorder=7,
                bbox=dict(boxstyle="round,pad=0.34", facecolor=MAU[VAI[k]], edgecolor="none"))
        ax.text(xc, H * (1.050 if k % 2 == 0 else 1.115),
                "%d tấm · %d lỗi · %d Bypass" % (NTAM[k], NLOI[k], NBYP[k]),
                fontsize=7.4, fontweight="700" if NBYP[k] <= 1 else "400",
                color=C_NHIET if NBYP[k] <= 1 else C_CHU, ha="center", va="center")
    for r in ranh1:
        ax.text(r - FOOT_PX / 2, H * 0.90, "đệm\n18,4 m", fontsize=7.0, fontweight="700",
                color="#FFFFFF", ha="center", va="center", zorder=7,
                bbox=dict(boxstyle="round,pad=0.22", facecolor="#00000066", edgecolor="none"))
    sb = 50.0 / MPP
    ax.plot([Wp * 0.015, Wp * 0.015 + sb], [H * 0.95, H * 0.95], color="#FFFFFF", linewidth=3.0, zorder=7)
    ax.text(Wp * 0.015 + sb / 2, H * 0.912, "50 m", fontsize=7.6, fontweight="700",
            color="#FFFFFF", ha="center", va="center", zorder=7)
    ax.plot([], [], "o", markersize=5.2, color="#FFE14D", markeredgecolor="#3A2E00",
            markeredgewidth=0.8, label="lỗi Bypass (31 ca)")
    ax.plot([], [], "o", markersize=3.6, color="#FFFFFF", label="lỗi khác (407 ca)")
    ax.legend(loc="lower right", fontsize=7.6, framealpha=0.92, borderpad=0.5,
              handletextpad=0.5, edgecolor="#00000022")

    # ───────────────────────────────────────────────── (b) phóng to ranh giới K1|K2
    xb = CANH[1]
    zx0, zx1 = int(xb - 34 / MPP), int(xb + 34 / MPP)
    zy0, zy1 = int(H * 0.30), int(H * 0.74)
    B = base[zy0:zy1, zx0:zx1].copy()
    off = xb - zx0
    to_phu(B, 0, off - FOOT_PX, C_TRAIN)
    to_dem(B, off - FOOT_PX, off)
    to_phu(B, off, B.shape[1], C_TEST)
    Hb, Wb = B.shape[:2]

    ax = fig.add_subplot(gs[1]); khung(ax)
    ax.imshow(B, interpolation="bilinear")
    ax.set_xlim(0, Wb), ax.set_ylim(Hb, 0)
    ax.plot([off, off], [0, Hb], color="#FFFFFF", linewidth=2.2, zorder=5)
    ax.text(-Wb * 0.005, -Hb * 0.085,
            "Phóng to ranh giới K1 | K2 — đệm 18,4 m chỉ cắt bên TRAIN, khối test giữ nguyên toàn bộ",
            fontsize=10.4, fontweight="700", color=C_CHU, ha="left", va="center")
    for x_, t_, m_ in [(off - FOOT_PX - 190, "TRAIN", C_TRAIN),
                       (off - FOOT_PX / 2, "ĐỆM — bỏ", "#4A4A52"),
                       (off + 190, "TEST — giữ nguyên", C_TEST)]:
        ax.text(x_, Hb * 0.075, t_, fontsize=8.6, fontweight="700", color="#FFFFFF",
                ha="center", va="center", zorder=7,
                bbox=dict(boxstyle="round,pad=0.32", facecolor=m_, edgecolor="none"))
    fw, fh = 18.4 / MPP, 14.7 / MPP
    fx0, fy0 = off - fw * 0.94, Hb * 0.38
    ax.add_patch(Rectangle((fx0, fy0), fw, fh, linewidth=2.4, edgecolor="#FFE14D",
                           facecolor="#FFE14D", alpha=0.17, zorder=6))
    ax.add_patch(Rectangle((fx0, fy0), fw, fh, linewidth=2.4, edgecolor="#FFE14D",
                           facecolor="none", zorder=7))
    ax.text(fx0 + fw / 2, fy0 - Hb * 0.035, "khung ảnh nhiệt ở vị trí xấu nhất — 18,4 × 14,7 m",
            fontsize=7.8, fontweight="700", color="#3A2E00", ha="center", va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.26", facecolor="#FFE14D", edgecolor="none"))
    ax.annotate("", xy=(off - FOOT_PX, Hb * 0.93), xytext=(off, Hb * 0.93),
                arrowprops=dict(arrowstyle="<->", color="#FFFFFF", lw=1.8))
    ax.text(off - FOOT_PX / 2, Hb * 0.985, "18,4 m", fontsize=8.2, fontweight="700",
            color="#FFFFFF", ha="center", va="center", zorder=7,
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#00000077", edgecolor="none"))
    ax.text(Wb * 1.004, Hb * 0.5,
            "Khung nào chứa tấm test\nthì vươn xa nhất 18,4 m\nsang trái — mà 18,4 m đó\nđã dọn sạch tấm train.\n\n"
            "Nên không khung nào\nthấy đồng thời hai bên.",
            fontsize=8.0, color=C_CHU, ha="left", va="center", linespacing=1.75)
    luu(fig, "chia_c8_ortho_that.png")

# ══════════════════════════════════════ C9  đệm để làm gì — hình giải thích tối giản
# Vẽ đúng một ý: model học ẢNH chứ không học TẤM PIN, mà một ảnh nhiệt phủ tới
# ~106 tấm pin (đếm thật: 18,4 x 14,7 m, mật độ 0,32 tấm/m²). Nên ảnh nằm vắt qua
# ranh giới thì chứa tấm của cả hai bên, và không xếp được vào bên nào.
if lam("C9"):
    N, S, G = 34, 2.2, 0.45              # số tấm vẽ, cạnh ô, khe
    P = S + G
    RANH = 17                            # ranh giới nằm giữa ô 16 và 17
    DEM = 9                              # số ô đệm — đúng bằng bề rộng một khung ảnh
    AW = 9 * P                           # bề rộng một khung ảnh, tính theo số ô

    fig, axs = plt.subplots(2, 1, figsize=(11.0, 5.4), dpi=210)
    fig.patch.set_facecolor(C_NEN)
    fig.subplots_adjust(left=0.035, right=0.985, top=0.90, bottom=0.045, hspace=0.52)
    fig.text(0.035, 0.955, "Vùng đệm để làm gì", fontsize=13.6, fontweight="700",
             color=C_CHU, va="center")
    fig.text(0.035, 0.918,
             "Model không học từng tấm pin — model học ẢNH. Mà một khung ảnh nhiệt phủ tới 106 tấm pin cùng lúc.",
             fontsize=8.6, color=C_MO, va="center")

    for ax, co_dem in zip(axs, (False, True)):
        khung(ax)
        ax.set_xlim(-2, N * P + 30), ax.set_ylim(-9, 15)
        ax.set_aspect("equal")
        for i in range(N):
            if co_dem and RANH - DEM // 2 - 1 <= i <= RANH + DEM // 2 - 1:
                mau, a = C_DEM, 0.5
            else:
                mau, a = (C_TRAIN if i < RANH else C_TEST), 1.0
            ax.add_patch(Rectangle((i * P, 0), S, S * 1.9, linewidth=0,
                                   facecolor=mau, alpha=a, zorder=3))
        xr = RANH * P - G / 2
        ax.plot([xr, xr], [-2.6, 7.2], color=C_CHU, linewidth=2.0, zorder=5)
        ax.text(xr, 7.6, "ranh giới khối", fontsize=7.6, color=C_MO,
                ha="center", va="bottom")

        if not co_dem:
            ax.text(-2, 13.0, "① KHÔNG có đệm", fontsize=10.4, fontweight="700",
                    color=C_NHIET, va="center")
            ax0 = xr - AW * 0.55
            ax.add_patch(Rectangle((ax0, -1.4), AW, S * 1.9 + 2.8, linewidth=2.4,
                                   edgecolor="#C9A227", facecolor="#FFE14D", alpha=0.20, zorder=6))
            ax.add_patch(Rectangle((ax0, -1.4), AW, S * 1.9 + 2.8, linewidth=2.4,
                                   edgecolor="#C9A227", facecolor="none", zorder=7))
            ax.text(ax0 + AW / 2, -3.4, "một khung ảnh", fontsize=7.8, fontweight="700",
                    color="#7A5F00", ha="center", va="top")
            ax.text(N * P + 2, 4.0,
                    "Khung này chứa CẢ tấm train LẪN tấm test.\n"
                    "Phải đưa nó vào train (vì có tấm train)\n"
                    "⇒ model đã nhìn thấy tấm test rồi.",
                    fontsize=8.4, color=C_CHU, va="center", linespacing=1.8)
        else:
            ax.text(-2, 13.0, "② CÓ đệm — bỏ trống một dải rộng bằng đúng một khung ảnh",
                    fontsize=10.4, fontweight="700", color=C_TEST, va="center")
            for d, lab in ((-1, "chỉ chạm train"), (1, "chỉ chạm test")):
                a0 = xr + d * (AW * 0.52 + AW / 2) - AW / 2
                ax.add_patch(Rectangle((a0, -1.4), AW, S * 1.9 + 2.8, linewidth=2.0,
                                       edgecolor="#C9A227", facecolor="#FFE14D",
                                       alpha=0.18, zorder=6))
                ax.text(a0 + AW / 2, -3.4, lab, fontsize=7.6, fontweight="700",
                        color="#7A5F00", ha="center", va="top")
            ax.annotate("", xy=((RANH - DEM // 2 - 1) * P, 10.8),
                        xytext=((RANH + DEM // 2 - 1) * P + S, 10.8),
                        arrowprops=dict(arrowstyle="<->", color=C_CHU, lw=1.3))
            ax.text(xr, 11.2, "đệm", fontsize=8.0, fontweight="700",
                    color=C_CHU, ha="center", va="bottom")
            ax.text(N * P + 2, 4.0,
                    "Khe trống rộng bằng một khung ảnh\n"
                    "⇒ KHÔNG khung nào bắc qua được.\n"
                    "Mỗi khung chỉ chạm được một bên.",
                    fontsize=8.4, color=C_CHU, va="center", linespacing=1.8)

    for mau, ten, x in [(C_TRAIN, "tấm train", 0.30), (C_TEST, "tấm test", 0.44),
                        (C_DEM, "tấm bỏ ra (đệm)", 0.56)]:
        fig.patches.append(Rectangle((x, 0.008), 0.013, 0.026, transform=fig.transFigure,
                                     facecolor=mau, edgecolor="none", zorder=5))
        fig.text(x + 0.018, 0.021, ten, fontsize=8.0, color=C_CHU, va="center")
    luu(fig, "chia_c9_dem_de_lam_gi.png")
