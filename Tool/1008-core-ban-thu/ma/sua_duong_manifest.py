#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nắn lại đường dẫn trong `du_lieu/manifest_anh.csv` về chỗ ảnh ĐANG nằm.

Manifest ghi đường dẫn TUYỆT ĐỐI. Dự án đã dời hai lần — từ
`C:\\Users\\Chi\\Desktop\\1008-stage1-rgb-thermel\\` sang ổ D, rồi lại gom ảnh vào
`du_lieu/` khi tái cấu trúc thư mục — nên mọi đường trong file đều trỏ vào hư
không. Hậu quả im lặng và rất dễ tin nhầm: `cv2.imread` trả None, script detect
chạy hết 598 ảnh trong 5 giây và báo **0 phát hiện**, không một dòng lỗi nào.

Script này dò lại từng ảnh THEO TÊN FILE trong `du_lieu/`, chỉ ghi đè khi tìm đủ
cả cặp RGB + nhiệt. Bản cũ giữ lại thành `manifest_anh.csv.bak`.

    py -3.13 ma/sua_duong_manifest.py            # xem sẽ đổi gì, chưa ghi
    py -3.13 ma/sua_duong_manifest.py --ghi      # ghi đè thật
"""
import argparse
import csv
import os
import shutil
import sys

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

ap = argparse.ArgumentParser()
ap.add_argument("--manifest", default="du_lieu/manifest_anh.csv")
ap.add_argument("--goc-anh", default="du_lieu", dest="goc_anh",
                help="thư mục quét tìm ảnh")
ap.add_argument("--ghi", action="store_true", help="ghi đè thật, mặc định chỉ xem")
args = ap.parse_args()

# ------------------------------------------------------- 1. lập bảng tên -> đường
print("[QUÉT] %s ..." % args.goc_anh)
o_dau = {}
trung = 0
for goc_, _, files in os.walk(args.goc_anh):
    for f in files:
        if not f.upper().endswith((".JPG", ".JPEG")):
            continue
        p = os.path.abspath(os.path.join(goc_, f))
        if f in o_dau:
            trung += 1
            # ưu tiên bản trong data_Thermel gốc, không phải bản data_aligned
            if "data_aligned" in o_dau[f] and "data_aligned" not in p:
                o_dau[f] = p
        else:
            o_dau[f] = p
print("       %d tên ảnh (%d tên xuất hiện ở nhiều chỗ)" % (len(o_dau), trung))

# ------------------------------------------------------------------- 2. nắn lại
rows = list(csv.DictReader(open(args.manifest, encoding="utf-8-sig")))
cot = list(rows[0].keys())
sua, con_hong, van_dung = 0, [], 0
for r in rows:
    hong = False
    for cot_duong, cot_ten in (("path_rgb", "file_rgb"), ("path_thermal", "file_thermal")):
        cu = r[cot_duong]
        if os.path.exists(cu):
            van_dung += 1
            continue
        moi = o_dau.get(r[cot_ten])
        if moi:
            r[cot_duong] = moi
            sua += 1
        else:
            hong = True
    if hong:
        con_hong.append(r["seq"])

print("\n[KẾT QUẢ]")
print("   %4d đường vốn đã đúng" % van_dung)
print("   %4d đường nắn lại được" % sua)
print("   %4d dòng vẫn thiếu ảnh%s"
      % (len(con_hong), (": " + ", ".join(con_hong[:8])) if con_hong else ""))

if not sua:
    print("\nKhông có gì để đổi.")
    raise SystemExit(0)
if not args.ghi:
    print("\nĐây mới là bản xem. Chạy lại kèm --ghi để ghi đè thật.")
    raise SystemExit(0)

shutil.copy2(args.manifest, args.manifest + ".bak")
with open(args.manifest, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, cot)
    w.writeheader()
    w.writerows(rows)
print("\n-> %s đã ghi đè (bản cũ: %s.bak)" % (args.manifest, args.manifest))
