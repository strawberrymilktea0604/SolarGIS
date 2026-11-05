#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thêm lớp nền thứ năm vào so_sanh_model.html: ortho nhiệt BÙ THEO ORTHO MÀU.

Đây là bản ortho nhiệt dựng lại với phần bù đo từ ortho màu, cộng vào NGAY LÚC
GHÉP nên chỉ nội suy một lần:

    lệch với ortho màu  8,1 -> 4,7 cm   (giảm 42%)
    độ nét              772 -> 775      (không mất)

So với bản nắn sau khi ghép (ortho_nhiet_nan.tif): bản đó cũng giảm lệch nhưng
mất 22% độ nét vì ảnh bị nội suy hai lần.

Cần có trước:
    py -3.13 ma/bu_theo_rgb.py
    py -3.13 ma/ghep_ortho_nhiet.py --bu-rgb bu_theo_rgb.json --out ortho_nhiet_bu_rgb.tif
    py -3.13 ma/xuat_nen_net.py --lop burgb

    py -3.13 ma/va_viewer_bu_rgb.py
    py -3.13 ma/va_viewer_bu_rgb.py --hoan-tac
"""
import argparse
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "cong_cu/so_sanh_model.html")
SAO = HTML + ".truoc_burgb.bak"
DAU = "/* --- nen bu rgb --- */"

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
    '<button id="bXUOI" aria-pressed="false" ',
    '<button id="bBURGB" aria-pressed="false" '
    'title="Ortho nhiệt dựng lại với phần bù đo từ ortho màu — lệch 4,7 cm">'
    'Nhiệt · bù RGB</button>\n'
    '          <button id="bXUOI" aria-pressed="false" ',
))

# --------------------------------------------------------- 2. bảng nền + ảnh nét
VA.append((
    "           xuoi:'overview_thermal'};",
    "           xuoi:'overview_thermal', burgb:'overview_thermal'};\n"
    "/* --- nen bu rgb --- lop nay cung khong co ban 2400 px nhung san, muon tam\n"
    "   anh cua lop 'th' roi net/net_burgb.jpg tai xong se thay vao. */",
))
VA.append((
    "           xuoi:'net/net_xuoi.jpg'};",
    "           xuoi:'net/net_xuoi.jpg', burgb:'net/net_burgb.jpg'};",
))

# ------------------------------------------------------------ 3. bật/tắt nút
VA.append((
    "  bXUOI.setAttribute('aria-pressed',String(lop==='xuoi'));}",
    "  bXUOI.setAttribute('aria-pressed',String(lop==='xuoi'));\n"
    "  bBURGB.setAttribute('aria-pressed',String(lop==='burgb'));}",
))
VA.append((
    "bXUOI.onclick=()=>base('xuoi');",
    "bXUOI.onclick=()=>base('xuoi');\nbBURGB.onclick=()=>base('burgb');",
))

# --------------------------------------------------------------- 4. nhãn riêng
VA.append((
    "  if(lop==='xuoi'){",
    "  if(lop==='burgb'){\n"
    "    e.dataset.cho = xong ? '0' : '1';\n"
    "    e.textContent = xong ? 'bù theo ortho màu · lệch 4,7 cm (gốc 8,1)'\n"
    "                  : daNet.has(lop) ? 'đang tải nền bù RGB…'\n"
    "                  : 'CHƯA CÓ net_burgb.jpg — chạy bu_theo_rgb.py';\n"
    "    return;\n"
    "  }\n"
    "  if(lop==='xuoi'){",
))

for i, (cu, moi) in enumerate(VA, 1):
    n = src.count(cu)
    if n != 1:
        raise SystemExit(f"[DỪNG] chỗ vá {i} khớp {n} lần (cần đúng 1). "
                         f"HTML đã đổi so với lúc viết script — không ghi gì cả.\n"
                         f"        Chuỗi cần tìm: {cu[:70]}...")
    src = src.replace(cu, moi)

p = os.path.join(BASE, "cong_cu/net", "net_burgb.jpg")
print(f"  net/net_burgb.jpg  "
      f"{'có, %.1f MB' % (os.path.getsize(p)/1e6) if os.path.exists(p) else 'CHƯA CÓ'}")

if not os.path.exists(SAO):
    shutil.copy2(args.html, SAO)
    print(f"\n[SAO LƯU] {SAO}")
open(args.html, "w", encoding="utf-8").write(src)
print(f"[VÁ]      {args.html}  ({len(src)/1e6:.1f} MB)")
print("\nMở lại HTML — có thêm nút 'Nhiệt · bù RGB'.")
