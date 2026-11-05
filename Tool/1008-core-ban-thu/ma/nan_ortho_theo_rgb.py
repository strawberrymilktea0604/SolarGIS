#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nắn ortho nhiệt BÁM THEO ortho màu — lấy ortho màu làm chuẩn hình học.

Ý TƯỞNG: hai hướng trước đều sửa ở khâu GHÉP và đều thất bại (pha trộn biên
Voronoi làm ghosting; chọn theo off-nadir thì trùng 96,7% với chọn theo khoảng
cách). Hướng này sửa SAU KHI GHÉP: coi ortho màu là bản đồ đúng, đo xem từng
mảnh ortho nhiệt lệch đi đâu, rồi kéo nó về.

CÁCH LÀM — co-registration bằng trường dịch chuyển:
  1. Dựng MẶT NẠ TẤM PIN cho cả hai ảnh. Không khớp trực tiếp giá trị pixel vì
     hai ảnh khác phương thức (nhiệt vs màu) — khớp mặt nạ nhị phân bền hơn hẳn.
       ortho màu  : tấm pin là vùng TỐI  -> đảo ngược rồi Otsu
       ortho nhiệt: tấm pin là vùng NÓNG -> Otsu thẳng
  2. Chia lưới ô vuông, mỗi ô khớp bằng phase correlation -> (dx, dy).
  3. Lọc: bỏ ô có độ tin thấp hoặc dịch quá xa; lọc trung vị để khử ô lạc.
  4. Nội suy thành trường dịch chuyển dày rồi remap ảnh nhiệt.

Trường dịch chuyển là hàm TRƠN, nên nó kéo được lệch cục bộ nhưng KHÔNG vá được
đứt gãy tại biên Voronoi (đứt gãy là gián đoạn). Đo bằng số ở cuối để biết ăn
thua tới đâu, đừng tin cảm nhận.

    py -3.13 ma/nan_ortho_theo_rgb.py --window 2600 1600 2400 1400   # thử một vùng
    py -3.13 ma/nan_ortho_theo_rgb.py                                # toàn nhà máy
"""
import argparse
import os
import time

import cv2
import numpy as np
import rasterio
from rasterio.windows import from_bounds

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--nguon", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_nan.tif"))
ap.add_argument("--o", type=int, default=256, help="cạnh ô khớp, px lưới nhiệt")
ap.add_argument("--buoc", type=int, default=128, help="bước trượt giữa các ô")
ap.add_argument("--toi-da", type=float, default=25.0, dest="toi_da",
                help="bỏ ô có dịch lớn hơn mức này (px) — chắc chắn là khớp nhầm")
ap.add_argument("--tin-toi-thieu", type=float, default=0.06, dest="tin",
                help="ngưỡng độ tin của phase correlation")
ap.add_argument("--phu-min", type=float, default=0.15, dest="phu_min",
                help="tỉ lệ tấm pin tối thiểu trong ô thì mới khớp")
ap.add_argument("--phu-max", type=float, default=0.90, dest="phu_max")
ap.add_argument("--im", action="store_true", help="bớt in ra màn hình")
ap.add_argument("--window", type=int, nargs=4, default=None,
                metavar=("COL", "ROW", "W", "H"))
args = ap.parse_args()

t0 = time.time()
nhiet = rasterio.open(args.nguon)
mau = rasterio.open(os.path.join(EXP, "ortho.tif"))

if args.window:
    C0, R0, WW, HH = args.window
else:
    C0, R0, WW, HH = 0, 0, nhiet.width, nhiet.height
TF = nhiet.transform * rasterio.Affine.translation(C0, R0)
GSD = abs(TF.a) * 111320 * np.cos(np.radians(11.424)) * 100
print(f"[VÙNG] {WW} x {HH} px, GSD {GSD:.2f} cm/px")

TH = nhiet.read(1, window=rasterio.windows.Window(C0, R0, WW, HH))

# ortho màu, đưa về ĐÚNG lưới của ảnh nhiệt
lo0, la0 = TF * (0, 0)
lo1, la1 = TF * (WW, HH)
w = from_bounds(min(lo0, lo1), min(la0, la1), max(lo0, lo1), max(la0, la1), mau.transform)
RGB = mau.read([1, 2, 3], window=w, out_shape=(3, HH, WW),
               resampling=rasterio.enums.Resampling.average)
G = cv2.cvtColor(np.ascontiguousarray(np.moveaxis(RGB, 0, -1)[:, :, ::-1]), cv2.COLOR_BGR2GRAY)


def mat_na(v, dao):
    """Mặt nạ tấm pin. dao=True: tấm pin là vùng tối (ảnh màu).

    Ngưỡng Otsu CHỈ tính trên phần có dữ liệu. Cả hai ortho đều có vùng đen lớn
    ngoài rìa trang trại; nếu đưa cả vùng đó vào thì Otsu tách "đen vs có dữ liệu"
    thay vì "tấm pin vs mặt đất" — chạy toàn nhà máy ra mặt nạ 0,3%, vô dụng.
    """
    b = cv2.GaussianBlur(v, (0, 0), 2.0)
    hop_le = v > 0
    co = b[hop_le]
    if co.size < 100:
        return np.zeros_like(v, np.float32)
    t, _ = cv2.threshold(co.astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = (b < t) if dao else (b > t)
    m = m.astype(np.uint8) * 255
    m[~hop_le] = 0
    # bỏ đốm nhỏ để mặt nạ chỉ còn cấu trúc hàng tấm pin
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    return m.astype(np.float32) / 255.0


MT = mat_na(TH, False)
MG = mat_na(G, True)
print(f"[MẶT NẠ] tấm pin chiếm {100*MT.mean():.1f}% (nhiệt) · {100*MG.mean():.1f}% (màu)")

# ------------------------------------------------- khớp từng ô
O, B = args.o, args.buoc
ny = max(1, (HH - O) // B + 1)
nx = max(1, (WW - O) // B + 1)
DX = np.full((ny, nx), np.nan, np.float32)
DY = np.full((ny, nx), np.nan, np.float32)
han = cv2.createHanningWindow((O, O), cv2.CV_32F)
n_ok = 0
for iy in range(ny):
    for ix in range(nx):
        y0, x0 = iy * B, ix * B
        a = MT[y0:y0 + O, x0:x0 + O]
        b = MG[y0:y0 + O, x0:x0 + O]
        if a.shape != (O, O) or b.shape != (O, O):
            continue
        # Ô phải có cả tấm pin lẫn nền, không thì không có gì để khớp.
        # Ô toàn tấm pin (mean ~1) hay toàn nền (mean ~0) đều vô dụng: phase
        # correlation trên mảng gần như hằng số chỉ trả về nhiễu.
        if not (args.phu_min < a.mean() < args.phu_max
                and args.phu_min < b.mean() < args.phu_max):
            continue
        (dx, dy), r = cv2.phaseCorrelate(a * han, b * han)
        if r < args.tin or np.hypot(dx, dy) > args.toi_da:
            continue
        DX[iy, ix], DY[iy, ix] = dx, dy
        n_ok += 1
print(f"[KHỚP] {n_ok}/{ny*nx} ô khớp được ({100*n_ok/max(ny*nx,1):.0f}%), {time.time()-t0:.0f}s")
if n_ok < 8:
    raise SystemExit("[DỪNG] quá ít ô khớp được — không dựng được trường dịch chuyển.")

co = ~np.isnan(DX)
print(f"[DỊCH] trước khi nắn: trung vị "
      f"{np.median(np.hypot(DX[co], DY[co])):.2f} px = "
      f"{np.median(np.hypot(DX[co], DY[co]))*GSD:.1f} cm")


def lam_day(A):
    """Điền ô trống bằng lân cận, rồi lọc trung vị khử ô lạc, rồi làm trơn.

    Quy đổi về 0..255 theo ĐÚNG biên độ --toi-da rồi mới inpaint. Lần đầu viết
    dùng (F*8+128) — với dịch 25 px thì thành 328, bị cắt ở 255 và mất sạch giá
    trị ở các ô lệch nhiều.
    """
    M = np.isnan(A).astype(np.uint8)
    F = A.copy()
    F[np.isnan(F)] = 0
    S = 127.0 / max(args.toi_da, 1e-6)
    if M.any():
        u = np.clip(F * S + 128, 0, 255).astype(np.uint8)
        u = cv2.inpaint(u, M, 3, cv2.INPAINT_TELEA).astype(np.float32)
        F = (u - 128) / S
    F = cv2.medianBlur(F, 3)
    return cv2.GaussianBlur(F, (0, 0), 1.2)


FX = lam_day(DX)
FY = lam_day(DY)

# ------------------------------------------------- nội suy thành trường dày & remap
fx = cv2.resize(FX, (WW, HH), interpolation=cv2.INTER_CUBIC)
fy = cv2.resize(FY, (WW, HH), interpolation=cv2.INTER_CUBIC)
gx, gy = np.meshgrid(np.arange(WW, dtype=np.float32), np.arange(HH, dtype=np.float32))
# DẤU TRỪ. phaseCorrelate(MT, MG) = d nghĩa là mặt nạ MÀU nằm lệch +d so với mặt
# nạ NHIỆT. Muốn kéo ảnh nhiệt tới chỗ của ảnh màu thì remap phải LẤY MẪU ở
# (x - d). Lần đầu viết dùng dấu cộng: dịch ngược hướng nên lệch tăng gấp đôi
# (12,1 -> 27,8 cm) — đúng dấu hiệu của sai dấu, không phải phương pháp sai.
# INTER_CUBIC chứ không LINEAR: dịch dưới một pixel bằng nội suy tuyến tính làm
# nhoè đáng kể (đo được: độ nét tụt một nửa). Cubic giữ lại phần lớn.
NAN = cv2.remap(TH, gx - fx, gy - fy, cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
print(f"[NẮN]  xong, {time.time()-t0:.0f}s")

prof = dict(driver="GTiff", height=HH, width=WW, count=1, dtype="uint8",
            crs=nhiet.crs, transform=TF, compress="deflate", nodata=0)
with rasterio.open(args.out, "w", **prof) as d:
    d.write(NAN, 1)


# ------------------------------------------------- đo kết quả
def do_gay(v):
    bien = []
    for x in range(v.shape[1]):
        idx = np.where(v[:, x] > 150)[0]
        bien.append(idx[0] if idx.size else -1)
    y = np.array(bien, float)
    y = y[y > 0]
    return np.abs(np.diff(y, 2)) if y.size > 20 else None


# THƯỚC ĐO CỐ ĐỊNH, không phụ thuộc tham số nắn. Lần đầu dùng chính O/B/ngưỡng
# của bước nắn để đo, nên mỗi cấu hình tự chấm bằng thước của mình: ô 128 px cho
# n=2203 mẫu còn ô 256 px cho n=309, và phép đo trên ô nhỏ vốn nhiễu hơn — hoá ra
# so nhầm độ nhiễu của thước chứ không phải chất lượng của kết quả.
E_O, E_B, E_TIN = 256, 128, 0.06
e_han = cv2.createHanningWindow((E_O, E_O), cv2.CV_32F)
e_ny = max(1, (HH - E_O) // E_B + 1)
e_nx = max(1, (WW - E_O) // E_B + 1)


def do_khop(v):
    """Còn lệch bao nhiêu so với ortho màu. Luôn đo bằng ô 256/128, ngưỡng 0,06."""
    M = mat_na(v, False)
    d = []
    for iy in range(e_ny):
        for ix in range(e_nx):
            y0, x0 = iy * E_B, ix * E_B
            a = M[y0:y0 + E_O, x0:x0 + E_O]
            b = MG[y0:y0 + E_O, x0:x0 + E_O]
            if a.shape != (E_O, E_O) or b.shape != (E_O, E_O):
                continue
            if not (0.15 < a.mean() < 0.9 and 0.15 < b.mean() < 0.9):
                continue
            (dx, dy), r = cv2.phaseCorrelate(a * e_han, b * e_han)
            if r >= E_TIN and np.hypot(dx, dy) <= args.toi_da:
                d.append(np.hypot(dx, dy))
    return np.array(d)


print("\n=== KẾT QUẢ ===")
for ten, v in (("trước khi nắn", TH), ("sau khi nắn ", NAN)):
    g = do_gay(v)
    k = do_khop(v)
    print(f"  {ten}: gãy P95 {np.percentile(g,95):6.2f} px | "
          f"lệch với ortho màu: trung vị {np.median(k)*GSD:5.1f} cm (n={len(k)}) | "
          f"nét {cv2.Laplacian(v, cv2.CV_64F).var():7.1f}")
print(f"\n-> {args.out}  ({os.path.getsize(args.out)/1e6:.1f} MB)")
