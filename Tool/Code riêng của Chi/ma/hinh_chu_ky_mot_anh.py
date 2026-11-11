#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hình cho mục 1.2 — chữ ký một-ảnh của báo động giả.

Trái : phân bố n tách theo TP/FP (nhãn tay), chuẩn hoá theo từng nhóm.
Phải : đường cong P–R khi lọc theo n so với lọc theo conf — cho thấy hai
       đường CẮT NHAU, tức không đường nào trội hẳn (đúng kết luận bootstrap).

    py -3.13 ma/hinh_chu_ky_mot_anh.py
"""
import json, os, sys
from collections import Counter
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
det = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
nhan = json.load(open(os.path.join(BASE, "ket_qua/nhan_tam_pin_moi.json"), encoding="utf-8"))

KHONG_LOI = {"tot", "?", "khong_ro"}
NHAN = {x["ma_tam"]: x["tinh_trang"] for x in nhan["nhan"] if x.get("tinh_trang")}
loi_tay = {m: t for m, t in NHAN.items() if t not in KHONG_LOI}
tot_tay = {m for m, t in NHAN.items() if t in KHONG_LOI}

MODEL = {}
for d in det:
    p = d.get("panel_code")
    if p and (p not in MODEL or d["conf"] > MODEL[p]["conf"]):
        MODEL[p] = d
TP = [MODEL[p] for p in MODEL if p in loi_tay]
FP = [MODEL[p] for p in MODEL if p in tot_tay]
# n = số ảnh RIÊNG BIỆT. Không dùng trường "n" trong file: nó đếm cả seq trùng.
nn = lambda d: len(set(d["seqs"]))

plt.rcParams.update({"font.family": "Segoe UI", "font.size": 10})
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.1))

# ---- trái: phân bố n
mx = max(max(nn(d) for d in TP), max(nn(d) for d in FP))
xs = list(range(1, mx + 1))
ct, cf = Counter(nn(d) for d in TP), Counter(nn(d) for d in FP)
a1.bar([x - .2 for x in xs], [ct.get(x, 0)/len(TP)*100 for x in xs], .4,
       label=f"Lỗi thật (TP, {len(TP)})", color="#2f7d4f")
a1.bar([x + .2 for x in xs], [cf.get(x, 0)/len(FP)*100 for x in xs], .4,
       label=f"Báo động giả (FP, {len(FP)})", color="#c0392b")
a1.set_xlabel("n — số ảnh riêng biệt cùng thấy một lỗi")
a1.set_ylabel("% trong nhóm")
a1.set_title("(a) Chữ ký một-ảnh của báo động giả", fontweight="bold")
a1.set_xticks(xs); a1.legend(frameon=False); a1.grid(axis="y", alpha=.25)
a1.annotate(f"{cf.get(1,0)/len(FP)*100:.1f}%", (1.2, cf.get(1,0)/len(FP)*100),
            xytext=(2.4, 62), fontsize=10, fontweight="bold", color="#c0392b",
            arrowprops=dict(arrowstyle="->", color="#c0392b"))
a1.annotate(f"{ct.get(1,0)/len(TP)*100:.1f}%", (.8, ct.get(1,0)/len(TP)*100),
            xytext=(.6, 34), fontsize=10, fontweight="bold", color="#2f7d4f",
            arrowprops=dict(arrowstyle="->", color="#2f7d4f"))

# ---- phải: hai đường P-R cắt nhau
def duong(key, moc):
    pr = []
    for k in moc:
        tp = len([d for d in TP if key(d) >= k]); fp = len([d for d in FP if key(d) >= k])
        if tp:
            pr.append((tp/len(TP), tp/(tp+fp)))
    return zip(*pr)

rn, pn = duong(nn, range(1, 11))
rc, pc = duong(lambda d: d["conf"], [i/100 for i in range(25, 99)])
a2.plot(rc, pc, "-", color="#4a6fa5", lw=2, label="lọc theo conf")
a2.plot(rn, pn, "o-", color="#c47f1a", lw=2, ms=5, label="lọc theo n")
a2.set_xlabel("Recall"); a2.set_ylabel("Precision")
a2.set_title("(b) Hai đường cắt nhau — không đường nào trội", fontweight="bold")
a2.legend(frameon=False); a2.grid(alpha=.25)
a2.text(.02, .03, "ΔP(n≥3 vs conf cùng recall) = +0,019\nKTC 95% [−0,005; +0,044] — chứa 0",
        transform=a2.transAxes, fontsize=8.5, va="bottom",
        bbox=dict(boxstyle="round,pad=.4", fc="#fff8e7", ec="#c47f1a", lw=.8))

fig.tight_layout()
ra = os.path.join(BASE, "tai_lieu/hinh/chu_ky_mot_anh.png")
fig.savefig(ra, dpi=170, bbox_inches="tight")
print(f"-> {ra}")
print(f"   FP n=1: {cf.get(1,0)/len(FP)*100:.1f}%   TP n=1: {ct.get(1,0)/len(TP)*100:.1f}%")
