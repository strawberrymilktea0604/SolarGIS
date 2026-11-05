#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lọc nhãn tay: bỏ tấm chấm 'tốt', giữ lại danh sách TẤM CÓ LỖI.

Vào : nhan_tam_pin_CUU_v3.json  (kho localStorage đã cứu ra, khoá gan_nhan_tam_v3)
      gan_nhan_tam.html          (lấy mã tấm + lon/lat của cả 6473 tấm)
      loi_4lop_cuoi.json         (lớp + conf model đã gợi ý, để đối chiếu)
Ra  : nhan_tam_loi.json          (chỉ tấm có lỗi, kèm toạ độ và viền sửa tay)
      tam_loi_ban_giao.csv       (bảng phẳng, sắp theo dãy rồi mã tấm)

Tấm bị loại khỏi danh sách vẫn ghi lại trong nhan_tam_loi.json ở mục "da_loai"
— cần thì truy ngược được, không mất công soi lại.

    py -3.13 ma/loc_tam_loi.py
"""
import csv
import json
import os
import re
import sys

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

NGUON_NHAN = "cong_cu/nhan_cuu/nhan_tam_pin_CUU_v3.json"
# Tình trạng KHÔNG phải lỗi -> loại khỏi danh sách bàn giao.
KHONG_LOI = {"tot", "khong_ro", None, ""}

# ------------------------------------------------------- 1. mã tấm + toạ độ
html = open("cong_cu/gan_nhan_tam.html", encoding="utf-8").read()
i = html.index('DATA = {"nen"')
j = html.index("\n", i)
DATA = json.loads(html[i + len("DATA = "):j].rstrip(";"))
MA, LL = DATA["ma"], DATA["ll"]
TOA_DO = {m: LL[k] for k, m in enumerate(MA)}
print("[TẤM]   %d mã tấm trong công cụ" % len(MA))

# ------------------------------------------------------- 2. gợi ý của model
GOI = {}
for d in json.load(open("ket_qua/loi_4lop_cuoi.json", encoding="utf-8")):
    p = d.get("panel_code") or d.get("ma_gan_nhat")
    if p and (p not in GOI or d["conf"] > GOI[p]["conf"]):
        GOI[p] = d
print("[MODEL] %d tấm được model đánh dấu" % len(GOI))

# ------------------------------------------------------- 3. lọc nhãn tay
kho = json.load(open(NGUON_NHAN, encoding="utf-8"))
LOI, LOAI = [], []
for x in kho["nhan"]:
    ma = x["ma_tam"]
    tt = x.get("tinh_trang")
    if tt in KHONG_LOI:
        LOAI.append({"ma_tam": ma, "tinh_trang": tt,
                     "model_goi_y": GOI[ma]["cls"] if ma in GOI else None,
                     "conf": round(GOI[ma]["conf"], 3) if ma in GOI else None})
        continue
    lon, lat = TOA_DO.get(ma, (None, None))
    g = GOI.get(ma)
    LOI.append({
        "ma_tam": ma,
        "day": int(re.match(r"D(\d+)", ma).group(1)),
        "tinh_trang": tt,
        "lon": lon, "lat": lat,
        "model_goi_y": g["cls"] if g else None,
        "conf": round(float(g["conf"]), 3) if g else None,
        "khop_model": (g is not None and g["cls"] == tt),
        "so_anh_thay": int(g.get("n") or 1) if g else None,
        "vien_sua": x.get("vien_sua"),
        "ghi_chu": x.get("ghi_chu"),
    })

LOI.sort(key=lambda a: (a["day"], a["ma_tam"]))

# ------------------------------------------------------- 4. xuất
ra = {
    "_nguon": NGUON_NHAN,
    "_ghi_chu": "đã bỏ tấm chấm tốt / chưa rõ; chỉ còn tấm CÓ LỖI",
    "tam_co_loi": len(LOI),
    "tam_da_loai": len(LOAI),
    "loi": LOI,
    "da_loai": LOAI,
}
json.dump(ra, open("ket_qua/nhan_tam_loi.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

COT = ["ma_tam", "day", "tinh_trang", "lon", "lat",
       "model_goi_y", "conf", "khop_model", "so_anh_thay", "ghi_chu"]
with open("ket_qua/tam_loi_ban_giao.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, COT, extrasaction="ignore")
    w.writeheader()
    for r in LOI:
        w.writerow(r)

# ------------------------------------------------------- 5. bảng tổng kết
from collections import Counter
print("\n[GIỮ]   %d tấm có lỗi" % len(LOI))
for k, v in Counter(a["tinh_trang"] for a in LOI).most_common():
    print("          %-18s %3d" % (k, v))
print("[BỎ]    %d tấm" % len(LOAI))
for k, v in Counter(str(a["tinh_trang"]) for a in LOAI).most_common():
    print("          %-18s %3d" % (k, v))
ngoai = [a["ma_tam"] for a in LOI if a["model_goi_y"] is None]
print("[THÊM]  %d tấm tay tự gán mà model không đánh dấu: %s"
      % (len(ngoai), ", ".join(ngoai) or "—"))
print("[VIỀN]  %d/%d tấm đã sửa viền tay"
      % (sum(1 for a in LOI if a["vien_sua"]), len(LOI)))
print("\n-> nhan_tam_loi.json + tam_loi_ban_giao.csv")
