#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thêm lớp nền thứ tư vào so_sanh_model.html: ortho nhiệt DÁN XUÔI (đối chứng).

Để bấm qua lại giữa "Nhiệt · H tay" (đi ngược, bản đang dùng) và "Nhiệt · dán xuôi"
ngay trên cùng một khung, cùng một bộ lỗi — nhìn thấy khác biệt tận mắt thay vì
đọc số. Dùng để giải thích vì sao pipeline chạy ngược chiều.

Cần có trước:
    py -3.13 ma/ghep_ortho_dan_xuoi.py      -> ortho_nhiet_dan_xuoi.tif
    py -3.13 ma/xuat_nen_net.py --lop xuoi  -> net/net_xuoi.jpg

Vá bằng thay chuỗi, mỗi chỗ bắt buộc khớp DUY NHẤT một lần; lệch một chỗ là dừng,
không ghi gì. Chạy lại nhiều lần vô hại (tự nhận ra đã vá).

    py -3.13 ma/va_viewer_dan_xuoi.py
    py -3.13 ma/va_viewer_dan_xuoi.py --hoan-tac
"""
import argparse
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "cong_cu/so_sanh_model.html")
SAO = HTML + ".truoc_xuoi.bak"
DAU = "/* --- nen dan xuoi --- */"

ap = argparse.ArgumentParser()
ap.add_argument("--html", default=HTML)
ap.add_argument("--hoan-tac", action="store_true", dest="hoan_tac")
args = ap.parse_args()

if args.hoan_tac:
    if not os.path.exists(SAO):
        raise SystemExit(f"Không có bản sao {SAO} để hoàn tác.")
    shutil.copy2(SAO, args.html)
    print(f"[HOÀN TÁC] đã khôi phục từ {SAO}")
    raise SystemExit

src = open(args.html, encoding="utf-8").read()
if DAU in src:
    raise SystemExit("File đã được vá rồi. Muốn vá lại thì --hoan-tac trước.")

VA = []

# ------------------------------------------------------------------ 1. nút bấm
VA.append((
    '<button id="bTHMS" aria-pressed="false">Nhiệt · Metashape</button>',
    '<button id="bTHMS" aria-pressed="false">Nhiệt · Metashape</button>\n'
    '          <button id="bXUOI" aria-pressed="false" '
    'title="Ortho dựng bằng cách dán xuôi — để đối chứng, không dùng cho kết quả">'
    'Nhiệt · dán xuôi</button>',
))

# ------------------------------------------------- 2. bảng nền + hàm đổi lớp
CU2 = """const NEN={rgb:'overview', th:'overview_thermal', thms:'overview_thermal_ms'};"""
MOI2 = """const NEN={rgb:'overview', th:'overview_thermal', thms:'overview_thermal_ms',
           xuoi:'overview_thermal'};
/* --- nen dan xuoi ---
   Lop 'xuoi' KHONG co ban 2400 px nhung san trong DATA (viewer dung tu truoc khi
   co lop nay). Nen tam muon anh cua lop 'th' de co cai ve ngay, roi net/net_xuoi.jpg
   tai xong se thay vao. Neu thieu file do thi lop nay trong y het lop 'th' — de
   khong ai nham, nhan ben canh se bao 'CHUA CO net_xuoi.jpg'. */"""
VA.append((CU2, MOI2))

CU3 = """  bTHMS.setAttribute('aria-pressed',String(lop==='thms'));}
bRGB.onclick=()=>base('rgb'); bTH.onclick=()=>base('th'); bTHMS.onclick=()=>base('thms');"""
MOI3 = """  bTHMS.setAttribute('aria-pressed',String(lop==='thms'));
  bXUOI.setAttribute('aria-pressed',String(lop==='xuoi'));}
bRGB.onclick=()=>base('rgb'); bTH.onclick=()=>base('th'); bTHMS.onclick=()=>base('thms');
bXUOI.onclick=()=>base('xuoi');"""
VA.append((CU3, MOI3))

# --------------------------------------------- 3. đăng ký ảnh nét cho lớp mới
CU4 = """const NET={rgb:'net/net_rgb.jpg', th:'net/net_th.jpg', thms:'net/net_thms.jpg'};"""
MOI4 = """const NET={rgb:'net/net_rgb.jpg', th:'net/net_th.jpg', thms:'net/net_thms.jpg',
           xuoi:'net/net_xuoi.jpg'};"""
VA.append((CU4, MOI4))

# ------------------------------------------- 4. nhãn: nói rõ đây là bản đối chứng
CU5 = """  e.dataset.cho = xong ? '0' : '1';
  e.textContent = xong ? 'nền gốc · nét gấp ~3,3×'
                : daNet.has(lop) ? 'đang tải nền nét…' : 'nền 2400 px';"""
MOI5 = """  e.dataset.cho = xong ? '0' : '1';
  /* --- nen dan xuoi --- lop doi chung phai tu noi ra minh la doi chung */
  if(lop==='xuoi'){
    e.dataset.cho = xong ? '0' : '1';
    e.textContent = xong ? 'DÁN XUÔI · bản đối chứng, không dùng cho kết quả'
                  : daNet.has(lop) ? 'đang tải nền dán xuôi…'
                  : 'CHƯA CÓ net_xuoi.jpg — chạy ghep_ortho_dan_xuoi.py';
    return;
  }
  e.textContent = xong ? 'nền gốc · nét gấp ~3,3×'
                : daNet.has(lop) ? 'đang tải nền nét…' : 'nền 2400 px';"""
VA.append((CU5, MOI5))

for i, (cu, moi) in enumerate(VA, 1):
    n = src.count(cu)
    if n != 1:
        raise SystemExit(f"[DỪNG] chỗ vá {i} khớp {n} lần (cần đúng 1). "
                         f"HTML đã đổi so với lúc viết script — không ghi gì cả.\n"
                         f"        Chuỗi cần tìm: {cu[:70]}...")
    src = src.replace(cu, moi)

p = os.path.join(BASE, "cong_cu/net", "net_xuoi.jpg")
print(f"  net/net_xuoi.jpg  "
      f"{'có, %.1f MB' % (os.path.getsize(p)/1e6) if os.path.exists(p) else 'CHƯA CÓ — chạy ghep_ortho_dan_xuoi.py rồi xuat_nen_net.py --lop xuoi'}")

if not os.path.exists(SAO):
    shutil.copy2(args.html, SAO)
    print(f"\n[SAO LƯU] {SAO}")
open(args.html, "w", encoding="utf-8").write(src)
print(f"[VÁ]      {args.html}  ({len(src)/1e6:.1f} MB)")
print("\nMở lại HTML — có thêm nút 'Nhiệt · dán xuôi' cạnh 'Nhiệt · Metashape'.")
print("Bấm qua lại giữa 'Nhiệt · H tay' và 'Nhiệt · dán xuôi' để so cùng một chỗ.")
