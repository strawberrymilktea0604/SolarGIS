#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sinh manifest_anh.csv + data_aligned/ — ghép cặp ảnh RGB↔nhiệt theo cameras.xml.

NGUỒN GỐC: đây là script đã tạo ra manifest_anh.csv lúc 10/08/2026 12:04. Bản gốc
chạy từ thư mục tạm nên không nằm trong dự án; đã khôi phục lại đây ngày 11/08/2026.
Chạy lại cho ra file GIỐNG HỆT TỪNG BYTE với bản hiện có (đã kiểm chứng).

VÌ SAO PHẢI CÓ FILE NÀY — ba lý do, đều đã đo:
  1. 596/598 cặp có timestamp trong tên _W và _T LỆCH nhau 1-2 giây
     -> không thể suy tên ảnh nhiệt từ tên ảnh RGB bằng cách đổi hậu tố.
  2. 79/598 cặp có ảnh _W và _T nằm ở HAI thư mục giải nén khác nhau
     (Google Drive cắt dataset thành 4 phần) -> không thể ghép theo thư mục.
  3. Chỉ ảnh Metashape align được mới dùng được -> lọc theo <transform> trong
     cameras.xml, không phải cứ có file trên đĩa là lấy.
Khoá nối duy nhất đứng vững: seq — 4 chữ số trong tên file DJI.

    py -3.13 ma/tao_manifest.py

CẢNH BÁO: manifest ghi ĐƯỜNG DẪN TUYỆT ĐỐI. Đổi máy, đổi ổ đĩa, hay dời thư mục
dự án thì chạy lại script này thay vì sửa tay CSV.
"""
import csv
import os
import re
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export", "cameras.xml")
DATA = os.path.join(BASE, "du_lieu/data_Thermel_2_31M")
OUT = os.path.join(BASE, "du_lieu/data_aligned")

# ---------- 1. Danh sách camera đã align ----------
root = ET.parse(XML).getroot()
aligned = {}          # seq -> label
not_aligned = []
for cam in root.findall(".//camera"):
    label = cam.get("label")
    m = re.search(r"_(\d{4})_", label or "")
    if not m:
        continue
    # Metashape chỉ ghi <transform> cho camera align THÀNH CÔNG.
    if cam.find("transform") is None:
        not_aligned.append(label)
    else:
        aligned[m.group(1)] = label

print(f"[XML] {len(aligned)} camera da align, {len(not_aligned)} chua align")

# ---------- 2. Quét file ảnh trên đĩa, gom theo số thứ tự ----------
# os.walk đệ quy: gom phẳng cả 4 thư mục giải nén vào một dict keyed by seq,
# nên ảnh _W và _T của cùng một cặp nằm khác thư mục vẫn ghép được.
# \d+ trong regex nuốt luôn phần timestamp -> timestamp bị bỏ qua hoàn toàn.
found = {}            # seq -> {"W": path, "T": path}
for dirpath, _, files in os.walk(DATA):
    for fn in files:
        m = re.match(r"DJI_\d+_(\d{4})_([WTZ])\.JPG$", fn, re.I)
        if not m:
            continue
        seq, kind = m.group(1), m.group(2).upper()
        found.setdefault(seq, {})[kind] = os.path.join(dirpath, fn)

print(f"[DIA ] {len(found)} so thu tu, "
      f"{sum('W' in v for v in found.values())} anh _W, "
      f"{sum('T' in v for v in found.values())} anh _T")

# ---------- 3. Đối chiếu ----------
ok, thieu_T, thieu_W, khong_align, thieu_file = [], [], [], [], []

for seq, label in sorted(aligned.items()):
    v = found.get(seq)
    if not v:
        thieu_file.append(label)
    elif "W" not in v:
        thieu_W.append(label)
    elif "T" not in v:
        thieu_T.append(label)
    else:
        ok.append((seq, label, v["W"], v["T"]))

for seq in sorted(found):
    if seq not in aligned:
        khong_align.append(seq)

print(f"\n[KET QUA]")
print(f"  Cap dung & da align : {len(ok)}")
print(f"  Thieu anh nhiet _T  : {len(thieu_T)}  {thieu_T[:5]}")
print(f"  Thieu anh RGB  _W   : {len(thieu_W)}  {thieu_W[:5]}")
print(f"  Khong co file tren dia: {len(thieu_file)}  {thieu_file[:5]}")
print(f"  Co file nhung KHONG align (phai loai): {len(khong_align)}  {khong_align[:5]}")

# Kiem tra ten _T co trung timestamp voi _W khong
lech = sum(1 for _, lb, w, t in ok
           if os.path.basename(w)[:-6] != os.path.basename(t)[:-6])
print(f"  Cap co timestamp _W va _T LECH nhau: {lech}/{len(ok)}"
      f"  -> {'phai ghep theo so thu tu' if lech else 'ghep kieu nao cung duoc'}")

cheo = sum(1 for _, _, w, t in ok if os.path.dirname(w) != os.path.dirname(t))
print(f"  Cap co _W va _T o KHAC thu muc giai nen: {cheo}/{len(ok)}")

# ---------- 4. Xuất manifest ----------
# utf-8-sig: ghi kèm BOM. Moi script doc lai PHAI dung encoding="utf-8-sig",
# khong thi cot dau bi dinh ﻿.
man = os.path.join(BASE, "du_lieu/manifest_anh.csv")
with open(man, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["seq", "label_xml", "file_rgb", "file_thermal", "path_rgb", "path_thermal"])
    for seq, label, pw, pt in ok:
        w.writerow([seq, label, os.path.basename(pw), os.path.basename(pt), pw, pt])
print(f"\n[OUT] manifest: {man}")

# ---------- 5. Tạo thư mục lọc bằng hardlink (không tốn thêm dung lượng) ----------
# hardlink chu khong phai copy: data_aligned/ hien 6,4 GB nhung KHONG chiem
# them dia. Xoa data_aligned/ khong lam mat anh goc, va nguoc lai.
os.makedirs(os.path.join(OUT, "rgb"), exist_ok=True)
os.makedirs(os.path.join(OUT, "thermal"), exist_ok=True)

n_link, n_copy = 0, 0
for seq, label, pw, pt in ok:
    for src, sub in ((pw, "rgb"), (pt, "thermal")):
        dst = os.path.join(OUT, sub, os.path.basename(src))
        if os.path.exists(dst):
            continue
        try:
            os.link(src, dst)
            n_link += 1
        except OSError:
            # os.link chi chay khi nguon va dich CUNG mot volume NTFS.
            import shutil
            shutil.copy2(src, dst)
            n_copy += 1

print(f"[OUT] {OUT}  ->  {n_link} hardlink, {n_copy} copy")
print(f"      rgb/     : {len(os.listdir(os.path.join(OUT, 'rgb')))} file")
print(f"      thermal/ : {len(os.listdir(os.path.join(OUT, 'thermal')))} file")
