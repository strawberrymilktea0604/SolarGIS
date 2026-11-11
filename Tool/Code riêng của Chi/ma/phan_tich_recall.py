#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Truy nguon con so recall 0,897: model BO SOT hay GAN NHAM LOP?

Hai cau hoi tach bach:
  1. Ma tran nham lan: hang 'background' = so doi tuong that KHONG duoc phat
     hien. Neu hang do bang 0 thi model khong bo sot cai nao, phan thieu hut
     cua recall la do GAN SAI TEN LOP.
     (Bat buoc plots=True: ultralytics chi goi process_batch khi co plots.)
  2. Recall theo nguong conf, lay tu duong cong R-Confidence chu khong tu
     b.mr -- vi b.mr luon bao tai diem F1 lon nhat, doi conf khong doi so.
"""
import json
import os

import numpy as np
from ultralytics import YOLO

MODEL = r"mo_hinh\fault_obb_4class.pt"
RA = r"ket_qua\ket_qua_val"
YAML = os.path.join(RA, "data_test_nhom.yaml")

model = YOLO(MODEL)
ten = [model.names[i] for i in sorted(model.names)]
out = {}

kq = model.val(data=YAML, split="test", imgsz=640, batch=8, device="cpu",
               project=RA, name="_phan_tich", exist_ok=True, plots=True,
               verbose=False)

# --- 1. Ma tran nham lan tho -------------------------------------------------
M = np.array(kq.confusion_matrix.matrix)          # [du_doan+1, that+1]
nhan = ten + ["background"]

print("=" * 86)
print("MA TRAN NHAM LAN  (cot = NHAN THAT, hang = DU DOAN)")
print("=" * 86)
print("%-20s%s" % ("du doan \\ that", "".join("%14s" % n[:13] for n in nhan)))
for i, h in enumerate(nhan):
    print("%-20s%s" % (h[:19], "".join("%14.0f" % v for v in M[i])))

bo_sot = M[-1, :-1]                 # hang background = GT khong ai bat duoc
tong_gt = M[:, :-1].sum(axis=0)
dung = np.diag(M[:-1, :-1])
nham = tong_gt - dung - bo_sot      # bat duoc nhung gan sai ten lop

print()
print("%-20s%10s%10s%10s%10s" % ("Lop", "so GT", "dung", "sai lop", "bo sot"))
print("-" * 60)
for j, n in enumerate(ten):
    if tong_gt[j] == 0:
        continue
    print("%-20s%10.0f%10.0f%10.0f%10.0f"
          % (n, tong_gt[j], dung[j], nham[j], bo_sot[j]))
print("-" * 60)
print("%-20s%10.0f%10.0f%10.0f%10.0f"
      % ("TAT CA", tong_gt.sum(), dung.sum(), nham.sum(), bo_sot.sum()))
print()
print("=> PHAT HIEN DUOC (bat ky lop nao) : %.0f/%.0f = %.1f%%"
      % (tong_gt.sum() - bo_sot.sum(), tong_gt.sum(),
         100.0 * (tong_gt.sum() - bo_sot.sum()) / max(tong_gt.sum(), 1)))
print("=> GAN DUNG CA LOP                 : %.0f/%.0f = %.1f%%"
      % (dung.sum(), tong_gt.sum(), 100.0 * dung.sum() / max(tong_gt.sum(), 1)))
print("=> Bao dong gia (background->lop)  : %.0f" % M[:-1, -1].sum())

out["ma_tran_nham_lan"] = {"nhan": nhan, "matrix": M.tolist()}
out["theo_lop"] = {n: {"so_GT": float(tong_gt[j]), "gan_dung": float(dung[j]),
                       "gan_sai_lop": float(nham[j]), "bo_sot_han": float(bo_sot[j])}
                   for j, n in enumerate(ten) if tong_gt[j] > 0}
out["tong"] = {"so_GT": float(tong_gt.sum()), "phat_hien_duoc": float(tong_gt.sum() - bo_sot.sum()),
               "gan_dung_lop": float(dung.sum()), "gan_sai_lop": float(nham.sum()),
               "bo_sot_han": float(bo_sot.sum()), "bao_dong_gia": float(M[:-1, -1].sum())}

# --- 2. Recall thuc su tai tung nguong conf, lay tu duong cong ----------------
# curves_results: [P-conf, R-conf, ...] moi cai la [x, y, xlabel, ylabel]
rc = None
for c in kq.curves_results:
    if "Recall" in c[3] and "Confidence" in c[2]:
        rc = c
        break

if rc is not None:
    x = np.array(rc[0])                       # nguong conf
    y = np.array(rc[1])                       # [so_lop, n] recall tung lop
    y_all = y.mean(axis=0) if y.ndim > 1 else y
    print()
    print("=" * 86)
    print("RECALL THUC TE THEO NGUONG CONF (tu duong cong R-Confidence)")
    print("=" * 86)
    print("%10s%12s%s" % ("conf", "TAT CA", "".join("%16s" % n[:15] for n in ten[:y.shape[0]])))
    theo_conf = {}
    for c in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70]:
        i = int(np.argmin(np.abs(x - c)))
        hang = {"tat_ca": float(y_all[i])}
        for j in range(y.shape[0]):
            hang[ten[j]] = float(y[j, i])
        theo_conf["%.2f" % c] = hang
        print("%10.2f%12.4f%s" % (c, y_all[i],
              "".join("%16.4f" % y[j, i] for j in range(y.shape[0]))))
    out["recall_theo_conf_that"] = theo_conf

out["recall_bao_cao_tai_diem_F1"] = {"precision": float(kq.box.mp),
                                     "recall": float(kq.box.mr)}

with open(os.path.join(RA, "phan_tich_recall.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print()
print("Da luu ket_qua_val/phan_tich_recall.json")
