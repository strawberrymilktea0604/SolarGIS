#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bốc mẫu ngẫu nhiên để ĐO RECALL — model bỏ sót bao nhiêu lỗi.

Vì sao phải bốc mẫu: 496 tấm đã soi đều là tấm MODEL ĐÁNH DẤU, nên chỉ đo được
precision (model báo có lỗi thì đúng bao nhiêu). Muốn biết model BỎ SÓT bao
nhiêu thì phải soi cả tấm model KHÔNG đánh dấu — 4916 tấm, soi hết là không
tưởng. Bốc ngẫu nhiên vài trăm tấm rồi suy ra cho cả nhà máy thì đủ kết luận.

Quần thể bốc mẫu — bỏ hai nhóm, mỗi nhóm vì một lý do khác nhau:
  * tấm RÌA và tấm THIẾU NHIỆT (phủ nhiệt < 50%): không có ảnh nhiệt để nhìn,
    ép soi là ép đoán mò. Bỏ ra thì con số đo được là "recall trên phần soi
    được", nói rõ mẫu số chứ không giấu.
  * tấm MODEL ĐÃ ĐÁNH DẤU: đã soi hết rồi, nằm ở phía precision.

Hạt ngẫu nhiên cố định + ghi thẳng danh sách ra file: ai chạy lại cũng ra đúng
mẫu đó, không cãi được là chọn tấm dễ mà soi.

    py -3.13 ma/boc_mau_recall.py            # mặc định 400 tấm, hạt 1008
    py -3.13 ma/boc_mau_recall.py --so 600

-> ket_qua/mau_recall.json
"""
import argparse
import json
import os
import random
import sys

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

ap = argparse.ArgumentParser()
ap.add_argument("--so", type=int, default=400, help="số tấm bốc ra")
ap.add_argument("--hat", type=int, default=1008, help="hạt ngẫu nhiên")
ap.add_argument("--nguong-nhiet", type=float, default=50.0, dest="nguong",
                help="phủ nhiệt tối thiểu để coi là soi được, %%")
ap.add_argument("--cong-cu", default="cong_cu/gan_nhan_tam.html")
ap.add_argument("--out", default="ket_qua/mau_recall.json")
args = ap.parse_args()

# ---------------------------------------------------------- đọc DATA của công cụ
html = open(args.cong_cu, encoding="utf-8").read()
i = html.index('DATA = {"nen"')
D = json.loads(html[i + len("DATA = "):html.index("\n", i)].rstrip(";"))
MA, RIA, PHU, GOI = D["ma"], D["ria"], D["phu"], D["goi_y"]
N = len(MA)

soi_duoc = [k for k in range(N) if not RIA[k] and PHU[k] >= args.nguong]
danh_dau = [k for k in soi_duoc if str(k) in GOI]
quan_the = [k for k in soi_duoc if str(k) not in GOI]

print("[QUẦN THỂ]")
print("   %5d tấm tất cả" % N)
print("   %5d tấm soi được  (bỏ %d tấm rìa / phủ nhiệt < %g%%)"
      % (len(soi_duoc), N - len(soi_duoc), args.nguong))
print("   %5d tấm model đánh dấu — đã soi, nằm ở phía precision" % len(danh_dau))
print("   %5d tấm để bốc mẫu" % len(quan_the))

if args.so > len(quan_the):
    raise SystemExit("[LỖI] xin %d tấm mà quần thể chỉ có %d" % (args.so, len(quan_the)))

r = random.Random(args.hat)
mau = sorted(r.sample(quan_the, args.so))

# Trải đều hay dồn cục? Đếm theo dãy để nhìn được ngay — bốc ngẫu nhiên đơn giản
# thì về lý là trải đều, nhưng in ra vẫn hơn là tin suông.
day = {}
for k in mau:
    d = MA[k].split("-")[0]
    day[d] = day.get(d, 0) + 1

ra = {
    "_muc_dich": "mẫu ngẫu nhiên để đo recall — tấm model KHÔNG đánh dấu",
    "cong_cu": args.cong_cu,
    "hat": args.hat,
    "nguong_phu_nhiet": args.nguong,
    "tong_tam": N,
    "tam_soi_duoc": len(soi_duoc),
    "tam_model_danh_dau": len(danh_dau),
    "quan_the": len(quan_the),
    "so_mau": len(mau),
    "so_day_co_mau": len(day),
    "ma_tam": [MA[k] for k in mau],
}
os.makedirs(os.path.dirname(args.out), exist_ok=True)
json.dump(ra, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("\n[MẪU]  %d tấm, hạt %d, rải trên %d dãy (nhiều nhất %d tấm/dãy)"
      % (len(mau), args.hat, len(day), max(day.values())))
print("-> %s" % args.out)
print("   dựng trang soi:")
print("   py -3.13 ma/lam_gan_nhan_tam.py --bo-nen --chi-tam %s \\" % args.out)
print("       --khoa gan_nhan_mau_recall_v1 --tieu-de \"Soi mẫu đo recall\" \\")
print("       --out cong_cu/soi_mau_recall.html")
