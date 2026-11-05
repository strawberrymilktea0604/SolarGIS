#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hinh ket qua cua `thu_detect_ortho_thay.py` - hai bang so, khong suy dien.

TRAI  duong cong recall theo DUNG SAI ghep cap. Phai ve theo duong cong chu khong
      mot con so, vi ortho thay lech dinh vi co met: chot mot nguong la tron lan
      "model co nhin thay loi khong" voi "ortho co dat dung cho khong".
      Duong MOC NGAU NHIEN (rai lai dung 466 phat hien do vao vung phu) la SAN
      NHA - cho biet phan nao cua duong cong chi la mat do phat hien.

PHAI  huong canh. Ortho bac-len la canh xoay ~90 do so voi moi anh model tung
      train (drone bay yaw ~-89 do), nen phai do ca bon huong.

    py -3.13 ma/hinh_ortho_thay_ketqua.py
"""
import json
import os
import sys

import numpy as np

import goc  # noqa: F401

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
kq = json.load(open(os.path.join(BASE, "ket_qua/detect_ortho_thay.json"), encoding="utf-8"))
C, D = kq["C"], kq["D_quet_truot"]
X = kq["dung_sai_m"]


def y(d):
    return [100 * d["%.1f" % t] for t in X]


NEN, O1, O2 = "#141416", "#1b1b1f", "#f0f0f2"
fig = plt.figure(figsize=(17.5, 7.0), facecolor=NEN)
gs = fig.add_gridspec(1, 2, width_ratios=[1.42, 1], wspace=0.17,
                      left=0.052, right=0.985, top=0.845, bottom=0.105)

# ------------------------------------------------------------- TRAI: duong cong
ax = fig.add_subplot(gs[0, 0], facecolor=O1)
duong = [
    ("ortho TU GHEP, xoay 270  (cua so quanh loi)", C["tulam_inferno_xoay270"]
     ["recall_theo_dung_sai_m"], "#8bff6b", "-", 2.6, "o"),
    ("ortho THAY, xoay 90  (cua so quanh loi)", C["thay_mau_goc_xoay90"]
     ["recall_theo_dung_sai_m"], "#33e0ff", "-", 2.6, "o"),
    ("ortho THAY, quet truot toan bo - ghep 1-1", D["recall_doi_mot_mot"],
     "#ffb03a", "-", 2.2, "s"),
    ("ortho THAY, 1-1 sau khi bu dich deu (-2,9 / +2,5) m",
     D["bu_dich_deu_tot_nhat"]["recall_doi_mot_mot_sau_bu"], "#c58cff", "--", 1.9, "^"),
    ("MOC NGAU NHIEN - rai lai 466 phat hien, ghep 1-1",
     D["moc_ngau_nhien"]["recall_doi_mot_mot"], "#ff5a4d", ":", 2.2, "x"),
]
for ten, d, mau, ls, lw, mk in duong:
    ax.plot(X, y(d), ls, color=mau, lw=lw, marker=mk, ms=5.5, label=ten, zorder=3)
ax.axvline(1.0, color="#6a6a74", lw=1.2, ls="-.", zorder=1)
ax.text(1.06, 3, "nguong pipeline\ndang dung: 1 m", color="#9a9aa4", fontsize=8.6, va="bottom")
ax.fill_between(X, 0, y(D["moc_ngau_nhien"]["recall_doi_mot_mot"]),
                color="#ff5a4d", alpha=0.10, zorder=0)
ax.set_xlim(0.5, 6); ax.set_ylim(0, 100)
ax.set_xlabel("dung sai ghep cap (m)", color="#a0a0a8", fontsize=10)
ax.set_ylabel("bat lai duoc / 603 loi moc  (%)", color="#a0a0a8", fontsize=10)
ax.set_title("Recall theo dung sai - vung do la SAN NHA cua phep do",
             color=O2, fontsize=12.5, pad=9, loc="left")
ax.grid(color="#33333a", lw=0.7)
ax.tick_params(colors="#8a8a92", labelsize=9)
lg = ax.legend(loc="lower right", fontsize=9, framealpha=0.94, facecolor="#26262c",
               edgecolor="#3a3a40")
for t in lg.get_texts():
    t.set_color("#dcdce2")
for sp in ax.spines.values():
    sp.set_color("#3a3a40")

# --------------------------------------------------------------- PHAI: huong canh
ax2 = fig.add_subplot(gs[0, 1], facecolor=O1)
deg = [0, 90, 180, 270]
g_goc = [100 * C["thay_mau_goc_xoay%d" % d]["recall_theo_dung_sai_m"]["3.0"] for d in deg]
g_inf = [100 * C["thay_inferno_xoay%d" % d]["recall_theo_dung_sai_m"]["3.0"] for d in deg]
w = 0.36
xs = np.arange(4)
ax2.bar(xs - w / 2, g_goc, w, color="#33e0ff", label="giu bang mau goc cua ortho thay")
ax2.bar(xs + w / 2, g_inf, w, color="#2b7f96", label="chuyen xam roi to lai INFERNO")
for i in range(4):
    ax2.text(xs[i] - w / 2, g_goc[i] + 1.4, "%.1f" % g_goc[i], color="#33e0ff",
             ha="center", fontsize=9.5)
    ax2.text(xs[i] + w / 2, g_inf[i] + 1.4, "%.1f" % g_inf[i], color="#7fc4d6",
             ha="center", fontsize=9.5)
ax2.set_xticks(xs)
ax2.set_xticklabels(["0\n(bac-len)", "90", "180", "270"], color="#a0a0a8", fontsize=10)
ax2.set_ylim(0, 88)
ax2.set_ylabel("recall o dung sai 3 m  (%)", color="#a0a0a8", fontsize=10)
ax2.set_xlabel("xoay o ortho truoc khi dua vao model (do)", color="#a0a0a8", fontsize=10)
ax2.set_title("Huong canh doi ~24 diem; bang mau gan nhu khong doi gi",
              color=O2, fontsize=12.5, pad=9, loc="left")
ax2.grid(axis="y", color="#33333a", lw=0.7)
ax2.set_axisbelow(True)
ax2.tick_params(colors="#8a8a92", labelsize=9)
lg2 = ax2.legend(loc="upper left", fontsize=9, framealpha=0.94, facecolor="#26262c",
                 edgecolor="#3a3a40")
for t in lg2.get_texts():
    t.set_color("#dcdce2")
for sp in ax2.spines.values():
    sp.set_color("#3a3a40")

fig.text(0.052, 0.965,
         "fault_obb_4class.pt quet tren ORTHO NHIET THAY GHEP (Metashape)  -  conf 0,25, "
         "603 loi moc", color="#ffffff", fontsize=15.5, fontweight="bold", va="top")
fig.text(0.052, 0.918,
         "O dung sai 1 m ma pipeline dang dung: ortho tu ghep 82,8 %  |  ortho thay 12,8 %  |  "
         "moc ngau nhien 8,3 %. Ortho thay chi vuot san nha khi noi dung sai len vai met.",
         color="#a8a8b0", fontsize=10.5, va="top")

out = os.path.join(BASE, "tai_lieu/hinh/ortho_thay_b_ket_qua.jpg")
fig.savefig(out, dpi=118, facecolor=NEN)
print("-> %s" % os.path.relpath(out, BASE))
