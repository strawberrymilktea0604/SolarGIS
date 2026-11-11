#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ĐÁNH GIÁ MODEL bằng nhãn tay — chấm trên đúng thứ đem đi bàn giao.

Đây là bảng số thay cho mAP 0,965 và recall 0,897 trong báo cáo cũ. Hai số đó
đo trên bộ ảnh lẻ chia sẵn (mà tập test lại lẫn 81% ảnh train), còn bảng này chấm
trên ĐẦU RA THẬT của cả chuỗi: danh sách MÃ TẤM cần thay, đối chiếu với nhãn do
người soi chốt bằng tay trên ortho.

Đơn vị chấm là TẤM PIN, không phải box:
  * người vận hành nhận danh sách tấm để đi thay, không ai đi thay "một box"
  * model bắn nhiều box vào cùng một tấm là chuyện thường (trung bình 1,2 box/tấm)
    — chấm theo box thì cùng một tấm bị đếm mấy lần, số đẹp lên mà vô nghĩa

Ba nhóm tấm, phải tách bạch vì mỗi nhóm nói một chuyện:
  TP  model khoanh, tay xác nhận CÓ lỗi        -> model đúng
  FP  model khoanh, tay chấm là tấm TỐT        -> báo động giả, thợ đi kiểm tra oan
  FN  tay chấm CÓ lỗi mà model không khoanh    -> lỗi bị bỏ, nguy hiểm nhất

FN chỉ đếm được nếu người soi đã QUÉT phần model không khoanh. Script in rõ số
tấm model khoanh mà chưa ai soi, để không tự nhận vơ mẫu số.

    py -3.13 ma/danh_gia_model_theo_nhan.py
    py -3.13 ma/danh_gia_model_theo_nhan.py --nhan ket_qua/nhan_tam_pin.json

Nhãn lấy từ đâu: bấm "Tải JSON" trong công cụ gán nhãn. Không truyền --nhan thì
script tự lấy file nhãn mới nhất tìm được.
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

KHONG_LOI = {"tot", "?", "khong_ro"}
LOP = ["SingleHotSpot", "MultiHotSpot", "Bypass", "ModuleOpenCircuit", "khac"]

ap = argparse.ArgumentParser()
ap.add_argument("--nhan", help="JSON nhãn tay; bỏ trống thì tự tìm file mới nhất")
ap.add_argument("--model", default="ket_qua/loi_4lop_cuoi.json")
ap.add_argument("--conf", type=float, default=0.25,
                help="ngưỡng conf coi là model có khoanh")
ap.add_argument("--tinh-gan-nhat", action="store_true", dest="gan_nhat",
                help="tính cả lỗi rơi NGOÀI mọi tấm, gán theo tấm gần nhất")
ap.add_argument("--out", default="ket_qua/danh_gia_theo_nhan.json")
args = ap.parse_args()

# --------------------------------------------------------------- 1. nhãn tay
if args.nhan:
    duong = args.nhan
else:
    ung = [p for p in glob.glob("ket_qua/**/*.json", recursive=True)
           + glob.glob("cong_cu/**/*.json", recursive=True)
           + glob.glob("*.json")
           if os.path.basename(p).startswith(("nhan_tam_pin", "nhan_tam_loi"))]
    if not ung:
        raise SystemExit("[LỖI] không thấy file nhãn nào — bấm 'Tải JSON' trong công cụ.")
    duong = max(ung, key=os.path.getmtime)

D = json.load(open(duong, encoding="utf-8"))
ds = D["nhan"] if "nhan" in D else D["loi"]
NHAN = {}
for x in ds:
    tt = x.get("tinh_trang")
    if tt:
        NHAN[x["ma_tam"]] = tt
print("[NHÃN]  %s — %d tấm đã gán (%s)"
      % (duong, len(NHAN), __import__("datetime").datetime.fromtimestamp(
          os.path.getmtime(duong)).strftime("%d/%m/%Y %H:%M")))

loi_tay = {m: t for m, t in NHAN.items() if t not in KHONG_LOI}
tot_tay = {m for m, t in NHAN.items() if t in KHONG_LOI}
print("        %d tấm CÓ lỗi · %d tấm tốt/không rõ" % (len(loi_tay), len(tot_tay)))
for k, v in Counter(loi_tay.values()).most_common():
    print("          %-18s %3d" % (k, v))

# --------------------------------------------------------------- 2. model nói gì
# `panel_code` = lỗi rơi ĐÚNG TRONG polygon tấm. `ma_gan_nhat` = lỗi rơi NGOÀI
# mọi tấm, chỉ ghi lại tấm gần nhất cho biết nó ở quãng nào.
#
# Mặc định CHỈ tính panel_code. Lý do: công cụ gán nhãn cũng chỉ đánh dấu tấm
# theo panel_code, nên chấm bằng ma_gan_nhat là tự đẻ ra một nhóm tấm mà người
# soi chưa từng được hỏi tới — rồi lại phải loại chính nhóm đó khỏi mẫu số.
# Lỗi rơi ngoài mọi tấm là chuyện khác hẳn, đếm riêng ở dòng dưới.
det = json.load(open(args.model, encoding="utf-8"))
MODEL, ngoai_tam = {}, []
for d in det:
    if d["conf"] < args.conf:
        continue
    p = d.get("panel_code")
    if not p:
        ngoai_tam.append(d)
        p = d.get("ma_gan_nhat") if args.gan_nhat else None
        if not p:
            continue
    if p not in MODEL or d["conf"] > MODEL[p]["conf"]:
        MODEL[p] = d
print("\n[MODEL] %d phát hiện ở conf ≥ %.2f -> %d tấm được khoanh"
      % (len([d for d in det if d["conf"] >= args.conf]), args.conf, len(MODEL)))
print("        %d lỗi rơi NGOÀI mọi tấm pin — %s"
      % (len(ngoai_tam),
         "đã tính theo tấm gần nhất" if args.gan_nhat else "không tính vào đâu"))

# --------------------------------------------------------------- 3. ba nhóm
TP = sorted(set(MODEL) & set(loi_tay))
FP = sorted(set(MODEL) & tot_tay)
FN = sorted(set(loi_tay) - set(MODEL))
chua_soi = sorted(set(MODEL) - set(NHAN))

P = len(TP) / (len(TP) + len(FP)) if TP or FP else float("nan")
R = len(TP) / len(loi_tay) if loi_tay else float("nan")
F1 = 2 * P * R / (P + R) if P + R else float("nan")

print("\n[BA NHÓM] (đơn vị: TẤM PIN)")
print("   TP  model khoanh · tay xác nhận có lỗi : %4d" % len(TP))
print("   FP  model khoanh · tay chấm tấm tốt    : %4d" % len(FP))
print("   FN  tay thấy lỗi · model không khoanh  : %4d" % len(FN))
if chua_soi:
    print("   ??  model khoanh · CHƯA AI SOI          : %4d  (không tính vào đâu cả)"
          % len(chua_soi))

print("\n[CHỈ SỐ]")
print("   Precision = TP/(TP+FP) = %d/%d = %.3f" % (len(TP), len(TP)+len(FP), P))
print("   Recall    = TP/(TP+FN) = %d/%d = %.3f" % (len(TP), len(loi_tay), R))
print("   F1                              = %.3f" % F1)

# --------------------------------------------------------------- 4. đúng lớp chưa
dung = [m for m in TP if MODEL[m]["cls"] == loi_tay[m]]
print("\n[LỚP]   trên %d tấm TP: đúng lớp %d = %.3f"
      % (len(TP), len(dung), len(dung) / len(TP) if TP else float("nan")))
mt = Counter((MODEL[m]["cls"], loi_tay[m]) for m in TP if MODEL[m]["cls"] != loi_tay[m])
for (a, b), v in mt.most_common():
    print("          nhầm %-16s -> %-16s %3d" % (a, b, v))

print("\n[TỪNG LỚP]")
print("   %-18s %5s %5s %5s   %s" % ("lớp", "P", "R", "F1", "tay/model"))
theo_lop = {}
for c in LOP:
    tp = len([m for m in TP if MODEL[m]["cls"] == c and loi_tay[m] == c])
    mp = len([m for m in MODEL if MODEL[m]["cls"] == c and m in NHAN])
    gt = len([m for m in loi_tay if loi_tay[m] == c])
    if not mp and not gt:
        continue
    p = tp / mp if mp else float("nan")
    r = tp / gt if gt else float("nan")
    f = 2*p*r/(p+r) if p and r and p + r else float("nan")
    theo_lop[c] = {"tp": tp, "model": mp, "tay": gt, "P": round(p, 3) if mp else None,
                   "R": round(r, 3) if gt else None}
    print("   %-18s %5.3f %5.3f %5.3f   %d/%d" % (c, p, r, f, gt, mp))

# --------------------------------------------------------------- 5. đổi ngưỡng conf
print("\n[NGƯỠNG] chấm lại ở vài mức conf — chọn điểm vận hành")
print("   %5s %5s %5s %5s %6s %6s" % ("conf", "tấm", "TP", "FP", "P", "R"))
bang = []
for c in (0.15, 0.25, 0.40, 0.50, 0.64, 0.80):
    M2 = {}
    for d in det:
        p2 = d.get("panel_code") or (d.get("ma_gan_nhat") if args.gan_nhat else None)
        if not p2 or d["conf"] < c:
            continue
        if p2 not in M2 or d["conf"] > M2[p2]["conf"]:
            M2[p2] = d
    tp = len(set(M2) & set(loi_tay))
    fp = len(set(M2) & tot_tay)
    p_ = tp / (tp + fp) if tp + fp else float("nan")
    r_ = tp / len(loi_tay) if loi_tay else float("nan")
    bang.append({"conf": c, "tam": len(M2), "TP": tp, "FP": fp,
                 "P": round(p_, 3), "R": round(r_, 3)})
    print("   %5.2f %5d %5d %5d %6.3f %6.3f" % (c, len(M2), tp, fp, p_, r_))

# --------------------------------------------------------------- 6. ghi ra
ra = {
    "_nguon_nhan": duong,
    "_don_vi": "tấm pin, không phải box",
    "_canh_bao_recall": (
        "Recall chỉ đúng nếu người soi đã QUÉT cả phần model không khoanh. "
        "Nếu chỉ soi tấm model khoanh thì FN = 0 giả tạo, phải đo bằng mẫu ngẫu "
        "nhiên (ma/boc_mau_recall.py + ma/do_recall_mau.py)."),
    "conf": args.conf,
    "tam_da_gan": len(NHAN), "tam_co_loi": len(loi_tay), "tam_tot": len(tot_tay),
    "tam_model_khoanh": len(MODEL), "tam_model_khoanh_chua_soi": len(chua_soi),
    "loi_ngoai_moi_tam": len(ngoai_tam), "tinh_gan_nhat": args.gan_nhat,
    "TP": len(TP), "FP": len(FP), "FN": len(FN),
    "precision": round(P, 4), "recall": round(R, 4), "f1": round(F1, 4),
    "dung_lop_tren_TP": round(len(dung) / len(TP), 4) if TP else None,
    "nham_lop": {"%s->%s" % k: v for k, v in mt.items()},
    "theo_lop": theo_lop,
    "theo_nguong": bang,
    "ds_FN": FN,
    "ds_FP": FP,
    "ds_chua_soi": chua_soi,
}
json.dump(ra, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n-> %s" % args.out)
