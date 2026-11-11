#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tính RECALL từ mẫu đã soi — model bỏ sót bao nhiêu lỗi trên cả nhà máy.

Ăn ba thứ:
  ket_qua/mau_recall.json        định nghĩa mẫu (bốc bằng boc_mau_recall.py)
  ket_qua/nhan_mau_recall.json   nhãn của mẫu — bấm "Tải JSON" trong trang soi mẫu
  ket_qua/nhan_tam_loi.json      tấm lỗi đã chốt ở công cụ chính (loc_tam_loi.py)

Cách tính, nói thẳng ra để ai cũng kiểm lại được:

  Mẫu n tấm bốc ngẫu nhiên từ Q tấm mà model KHÔNG đánh dấu. Soi tay thấy k tấm
  thật ra CÓ lỗi. Tỉ lệ lỗi bị bỏ trong nhóm không đánh dấu là p = k/n, khoảng
  tin cậy 95% lấy theo Clopper-Pearson (chính xác, không xấp xỉ chuẩn — với k
  nhỏ thì xấp xỉ chuẩn cho ra cận dưới âm, vô nghĩa).

  Số lỗi bỏ sót trên cả nhà máy  S = p x Q
  Recall = (lỗi model tìm được, đã xác nhận) / (lỗi đó + S)

Hai chỗ phải nói rõ kèm con số, không được giấu:
  * mẫu số là phần SOI ĐƯỢC — đã bỏ 1065 tấm rìa/thiếu nhiệt. Không có ảnh nhiệt
    thì không ai phán được, tính vào chỉ là bịa.
  * tấm tự thêm bằng tay ở công cụ chính (model dò sót cả TẤM) là bằng chứng có
    bỏ sót thật, nhưng KHÔNG bốc ngẫu nhiên nên không nhân lên được. Đếm riêng.

    py -3.13 ma/do_recall_mau.py
"""
import argparse
import json
import os
import sys
from math import comb

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

ap = argparse.ArgumentParser()
ap.add_argument("--mau", default="ket_qua/mau_recall.json")
ap.add_argument("--nhan-mau", dest="nhan_mau", default="ket_qua/nhan_mau_recall.json")
ap.add_argument("--nhan-chinh", dest="nhan_chinh", default="ket_qua/nhan_tam_loi.json")
ap.add_argument("--out", default="ket_qua/recall_mau.json")
args = ap.parse_args()

KHONG_LOI = {"tot", "?", "khong_ro", None, ""}


def cp_khoang(k, n, muc=0.05):
    """Khoảng tin cậy Clopper-Pearson cho tỉ lệ k/n, mò nhị phân trên phân phối
    nhị thức — khỏi cần scipy."""
    def duoi():
        if k == 0:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(80):
            p = (lo + hi) / 2
            s = sum(comb(n, j) * p**j * (1-p)**(n-j) for j in range(k, n + 1))
            if s > muc / 2:
                hi = p
            else:
                lo = p
        return (lo + hi) / 2

    def tren():
        if k == n:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(80):
            p = (lo + hi) / 2
            s = sum(comb(n, j) * p**j * (1-p)**(n-j) for j in range(0, k + 1))
            if s > muc / 2:
                lo = p
            else:
                hi = p
        return (lo + hi) / 2
    return duoi(), tren()


# ------------------------------------------------------------------ 1. đọc vào
M = json.load(open(args.mau, encoding="utf-8"))
Q, ds_mau = M["quan_the"], set(M["ma_tam"])

if not os.path.exists(args.nhan_mau):
    print("[CHƯA CÓ] %s" % args.nhan_mau)
    print("   Mở cong_cu/soi_mau_recall.html, soi hết %d tấm trong mẫu, bấm"
          % len(ds_mau))
    print("   \"Tải JSON\" rồi để file vào đúng đường dẫn trên. Chạy lại script này.")
    raise SystemExit(0)

NM = json.load(open(args.nhan_mau, encoding="utf-8"))
nhan = {x["ma_tam"]: x.get("tinh_trang") for x in NM["nhan"]}

ngoai = [m for m in nhan if m not in ds_mau and not m.startswith("TAY-")]
tay = [m for m in nhan if m.startswith("TAY-")]

da_soi = [m for m in ds_mau if nhan.get(m) not in (None, "")]
co_loi = [m for m in da_soi if nhan[m] not in KHONG_LOI]
n, k = len(da_soi), len(co_loi)

# ------------------------------------------------- 2. lỗi model tìm được, đã chốt
L = json.load(open(args.nhan_chinh, encoding="utf-8"))["loi"]
tim_duoc = [a for a in L if a.get("model_goi_y")]
tay_chinh = [a for a in L if not a.get("model_goi_y")]

print("[MẪU]  %d/%d tấm đã soi" % (n, len(ds_mau)))
if n < len(ds_mau):
    print("       còn %d tấm chưa phán — số dưới đây tính trên phần đã soi"
          % (len(ds_mau) - n))
if ngoai:
    print("       %d nhãn nằm NGOÀI mẫu, đã bỏ qua: %s"
          % (len(ngoai), ", ".join(sorted(ngoai)[:6])))
if tay:
    print("       %d tấm tự thêm trong trang mẫu — đếm là lỗi bỏ sót, xem mục dưới"
          % len(tay))
if not n:
    raise SystemExit("[LỖI] chưa tấm nào trong mẫu được gán nhãn.")

# Tấm tự thêm trong TRANG MẪU là lỗi model bỏ sót và vẫn nằm trong vùng bốc mẫu,
# nên tính vào k. Tấm tự thêm ở công cụ chính thì không — chỗ đó không bốc ngẫu nhiên.
k_tay = len([m for m in tay if nhan[m] not in KHONG_LOI])
k += k_tay

p = k / n
lo, hi = cp_khoang(k, n)
S, S_lo, S_hi = p * Q, lo * Q, hi * Q
T = len(tim_duoc)
recall = T / (T + S) if T + S else float("nan")
r_lo, r_hi = T / (T + S_hi), T / (T + S_lo) if S_lo else 1.0

print("\n[BỎ SÓT]")
print("   %d/%d tấm trong mẫu thật ra CÓ lỗi mà model không đánh dấu (%.2f%%)"
      % (k, n, 100 * p))
print("   khoảng tin cậy 95%%: %.2f%% .. %.2f%%" % (100 * lo, 100 * hi))
print("   suy ra cả %d tấm không đánh dấu: %.0f lỗi bị bỏ  (%.0f .. %.0f)"
      % (Q, S, S_lo, S_hi))

print("\n[RECALL]")
print("   model tìm được và đã chốt : %d lỗi" % T)
print("   ước lượng bỏ sót          : %.0f lỗi" % S)
print("   RECALL = %d/(%d+%.0f) = %.3f   (95%%: %.3f .. %.3f)"
      % (T, T, S, recall, r_lo, r_hi))
if tay_chinh:
    print("\n   [!] %d tấm ở công cụ chính là do người soi tự thêm — model dò sót cả TẤM"
          % len(tay_chinh))
    print("       chứ không riêng lỗi. Không bốc ngẫu nhiên nên không nhân lên được,")
    print("       nhưng là bằng chứng bỏ sót có thật: %s"
          % ", ".join(a["ma_tam"] for a in tay_chinh[:8]))

ra = {
    "quan_the_khong_danh_dau": Q,
    "co_mau": len(ds_mau), "da_soi": n,
    "tam_co_loi_trong_mau": k,
    "trong_do_tu_them": k_tay,
    "ty_le_bo_sot": round(p, 5),
    "ty_le_bo_sot_kt95": [round(lo, 5), round(hi, 5)],
    "loi_bo_sot_uoc_luong": round(S, 1),
    "loi_bo_sot_kt95": [round(S_lo, 1), round(S_hi, 1)],
    "loi_model_tim_duoc_da_chot": T,
    "recall": round(recall, 4),
    "recall_kt95": [round(r_lo, 4), round(r_hi, 4)],
    "_mau_so": "chỉ tính trên phần SOI ĐƯỢC — đã bỏ tấm rìa và tấm phủ nhiệt < 50%",
    "_tam_tu_them_o_cong_cu_chinh": [a["ma_tam"] for a in tay_chinh],
}
json.dump(ra, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n-> %s" % args.out)
