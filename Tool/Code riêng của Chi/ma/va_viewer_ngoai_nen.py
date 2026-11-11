#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Vá so_sanh_model.html: đánh dấu lỗi rơi RA NGOÀI vùng có dữ liệu của ảnh nền.

Vì sao cần: hai lớp nhiệt đều có chỗ trống — lớp tự ghép thủng ở rìa vì ảnh nguồn
bị bộ lọc loại, lớp Metashape thì extent hẹp hơn khung. Lỗi rơi vào đó hiện lên như
một khung lơ lửng giữa nền đen, người xem dễ tưởng máy bịa ra lỗi ở chỗ trống.

Thực ra lỗi đó vẫn thật: model chạy trên TỪNG ẢNH NHIỆT LẺ rồi mới chiếu lên ortho,
nên ảnh nguồn có nhìn thấy điểm nóng ấy — chỉ là ortho không có pixel ở đó.

Cách làm: nhúng MẶT NẠ VÙNG PHỦ của hai lớp nhiệt (bitmap 1 bit/ô, base64) rồi tra
trong JS theo toạ độ %, thay vì liệt kê id từng lỗi. Nhờ vậy dùng được cho cả bốn
model trong viewer, và không hỏng khi dữ liệu lỗi đổi.

Vá bằng thay chuỗi, mỗi chỗ bắt buộc khớp DUY NHẤT một lần; lệch một chỗ là dừng,
không ghi gì. Chạy lại nhiều lần vô hại (tự nhận ra đã vá).

    python ma/va_viewer_ngoai_nen.py
    python ma/va_viewer_ngoai_nen.py --hoan-tac
"""
import argparse
import base64
import os
import shutil
import sys

import numpy as np
import rasterio
from rasterio.windows import from_bounds

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
F = "cong_cu/so_sanh_model.html"
SAO = "luu_tru/ban_sao/so_sanh_model.html.truoc_ngoai_nen.bak"

# Cùng khung cắt mà xuat_nen_net.py dùng — phải khớp, không thì mặt nạ lệch với nền.
FRAME = dict(c0=1163, r0=2274, w=22613, h=10079)
RONG = 512                      # bề rộng mặt nạ, đủ mịn mà nhẹ

ap = argparse.ArgumentParser()
ap.add_argument("--hoan-tac", action="store_true")
a = ap.parse_args()

if a.hoan_tac:
    if not os.path.exists(SAO):
        sys.exit("Không có bản sao để hoàn tác")
    shutil.copy(SAO, F)
    sys.exit("Đã trả lại bản trước khi vá")

# ------------------------------------------------------------ 1. dựng mặt nạ
with rasterio.open(os.path.join(EXP, "ortho.tif")) as o:
    t = o.transform
    LON0 = t.c + t.a * FRAME["c0"]
    LON1 = t.c + t.a * (FRAME["c0"] + FRAME["w"])
    LAT0 = t.f + t.e * FRAME["r0"]                     # mép TRÊN
    LAT1 = t.f + t.e * (FRAME["r0"] + FRAME["h"])      # mép DƯỚI
CAO = int(round(RONG * FRAME["h"] / FRAME["w"]))


def mat_na(duong):
    """1 = ô có dữ liệu. Đọc thô rồi gộp ô, ô nào quá nửa là có thì tính là có."""
    with rasterio.open(duong) as s:
        w = from_bounds(LON0, LAT1, LON1, LAT0, s.transform)
        # đọc ở độ phân giải gấp 4 rồi gộp -> biên vùng phủ mượt hơn
        a4 = s.read(1, window=w, out_shape=(CAO * 4, RONG * 4),
                    boundless=True, fill_value=0)
    co = (a4 > 0).reshape(CAO, 4, RONG, 4).mean(axis=(1, 3))
    return co > 0.5


def goi(m):
    return base64.b64encode(np.packbits(m.ravel())).decode()


lop = {"th": "ket_qua/ortho/ortho_nhiet_tu_lam.tif",
       "thms": os.path.join(EXP, "thermal_ortho.tif")}
goi_lop = {}
for k, f in lop.items():
    if not os.path.exists(f):
        sys.exit("Thiếu " + f)
    m = mat_na(f)
    goi_lop[k] = goi(m)
    print("  %-5s phủ %5.1f%% khung  ->  mặt nạ %dx%d, %.1f KB base64"
          % (k, 100 * m.mean(), RONG, CAO, len(goi_lop[k]) / 1024))

# ------------------------------------------------------------ 2. các miếng vá
JS = """
/* ---- Đánh dấu lỗi nằm ngoài vùng có dữ liệu của ảnh nền -------------------
   Mặt nạ 1 bit/ô, hàng trước cột sau, dựng bởi va_viewer_ngoai_nen.py theo ĐÚNG
   khung cắt của ba lớp nền. Lớp ảnh màu phủ kín nên không cần mặt nạ. */
const PHU = {w:%d, h:%d, bit:{}};
(function(){
  const raw = {th:"%s", thms:"%s"};
  for (const k in raw){
    const s = atob(raw[k]), u = new Uint8Array(s.length);
    for (let i=0;i<s.length;i++) u[i] = s.charCodeAt(i);
    PHU.bit[k] = u;
  }
})();
function ngoaiNen(d){
  const u = PHU.bit[lop];
  if (!u) return false;                       /* lop 'rgb': phu kin */
  const cx = Math.min(PHU.w-1, Math.max(0, Math.round(d.x/100*PHU.w)));
  const cy = Math.min(PHU.h-1, Math.max(0, Math.round(d.y/100*PHU.h)));
  const i = cy*PHU.w + cx;
  return ((u[i>>3] >> (7-(i&7))) & 1) === 0;
}
"""

CSS_CU = "  .ov polygon.dim{opacity:.12}"
CSS_MOI = ("  .ov polygon.dim{opacity:.12}\n"
           "  /* Vòng tròn nét đứt quanh lỗi rơi ngoài vùng có dữ liệu của ảnh nền.\n"
           "     Lỗi vẫn thật — model chạy trên ảnh nhiệt lẻ, chỉ là ortho thủng ở đó. */\n"
           "  .ov circle.ngoai{fill:none;stroke:var(--muted);stroke-width:.045;\n"
           "    stroke-dasharray:.16 .13;pointer-events:none;opacity:.85}")

VE_CU = """  + S().map(d=>`<circle cx="${d.x}" cy="${d.y*k}" r=".03" fill="${ccol(d.cls)}"
      data-cls="${d.cls}"/>`).join('');"""
VE_MOI = """  + S().map(d=>`<circle cx="${d.x}" cy="${d.y*k}" r=".03" fill="${ccol(d.cls)}"
      data-cls="${d.cls}"/>`).join('')
  + S().filter(ngoaiNen).map(d=>`<circle class="ngoai" cx="${d.x}" cy="${d.y*k}" r=".55">
      <title>${d.code||'?'} · lỗi có thật, nhưng ảnh nền không có dữ liệu ở đây</title></circle>`).join('');"""

BASE_CU = "bRGB.onclick=()=>base('rgb'); bTH.onclick=()=>base('th'); bTHMS.onclick=()=>base('thms');"
BASE_MOI = ("bRGB.onclick=()=>base('rgb'); bTH.onclick=()=>base('th'); bTHMS.onclick=()=>base('thms');\n"
            "/* đổi lớp nền thì vùng phủ đổi theo -> vẽ lại để vòng nét đứt cập nhật */\n"
            "[bRGB,bTH,bTHMS].forEach(b=>b.addEventListener('click',()=>{\n"
            "  if (document.querySelector('.ov')) drawShapes();}));")

LG_CU = """    + `<span><i style="border-color:var(--muted);border-style:dashed"></i>không xác định được tấm</span>`;"""
LG_MOI = """    + `<span><i style="border-color:var(--muted);border-style:dashed"></i>không xác định được tấm</span>`
    + `<span><i style="border-color:var(--muted);border-radius:50%;border-style:dashed"></i>ảnh nền không có dữ liệu ở đây</span>`;"""

h = open(F, encoding="utf-8").read()
if "ngoaiNen" in h:
    sys.exit("Đã vá từ trước, không làm lại")

VA = [(CSS_CU, CSS_MOI), (VE_CU, VE_MOI), (BASE_CU, BASE_MOI), (LG_CU, LG_MOI)]
for cu, moi in VA:
    n = h.count(cu)
    if n != 1:
        sys.exit("KHÔNG VÁ: chuỗi xuất hiện %d lần\n  %s" % (n, cu[:80]))
    h = h.replace(cu, moi)

# chèn khối JS ngay trước drawShapes
neo = "function drawShapes(){"
if h.count(neo) != 1:
    sys.exit("KHÔNG VÁ: không tìm thấy drawShapes")
h = h.replace(neo, (JS % (RONG, CAO, goi_lop["th"], goi_lop["thms"])) + neo)

os.makedirs(os.path.dirname(SAO), exist_ok=True)
shutil.copy(F, SAO)
open(F, "w", encoding="utf-8").write(h)
print("\nĐã vá %s (bản cũ: %s)" % (F, SAO))
