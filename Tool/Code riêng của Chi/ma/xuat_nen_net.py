#!/usr/bin/env python3
"""
Xuất ba lớp nền của viewer ở ĐỘ PHÂN GIẢI GỐC, thay cho bản 2400 px đang nhúng
base64 trong so_sanh_model.html.

Vì sao cần: ortho nhiệt tự ghép là 8451 x 4997 px, còn viewer chỉ hiển thị bản
thu nhỏ 2400 px. Phóng 300% trên màn hình là đang phóng to bản thu nhỏ đó, chứ
không phải nhìn dữ liệu gốc — mờ là do khâu hiển thị, không phải do ortho.

Ảnh xuất ra là FILE RỜI cạnh HTML, không nhúng base64: nhúng 8000 px vào file
đã 38 MB thì thành ~100 MB và trình duyệt phải giải nén hết mới vẽ được ô đầu
tiên. Để rời thì viewer vẽ ngay bản 2400 px nhúng sẵn, rồi âm thầm tải bản nét
và thay vào — xem tiếp phần vá trong `va_viewer_net.py`.

Cửa sổ cắt lấy đúng của viewer cũ, khôi phục từ lon/lat và toạ độ % của 284 lỗi
trong viewer_data (khớp tới 0,25 cm), nên khung lỗi không xê dịch một pixel nào.

    python ma/xuat_nen_net.py                # cả ba lớp, tối đa 8192 px
    python ma/xuat_nen_net.py --rong 12000   # nét hơn nữa, tốn RAM trình duyệt hơn
    python ma/xuat_nen_net.py --lop th       # chỉ làm lại lớp nhiệt tự ghép
"""
import argparse
import os

import cv2
import numpy as np
import rasterio
from rasterio.windows import from_bounds

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

# Cửa sổ viewer, tính bằng PIXEL của ortho.tif. Đây là số gốc, đọc từ DATA.frame
# nhúng trong so_sanh_model.html — chính cửa sổ mà bộ dựng viewer đã cắt.
#
# Đừng suy cửa sổ này ra từ lon/lat của các lỗi: đã thử, khớp tới 0,25 cm nhưng
# chiều cao vẫn lệch 6,8 px ortho (0,7 px ở thang 2400), đủ làm nền mới trôi ~4 cm
# so với nền cũ. frame là con số nguyên, không phải số khớp — dùng thẳng.
# ĐỪNG sửa nếu không dựng lại toàn bộ viewer: khung lỗi neo vào đây.
FRAME = dict(c0=1163, r0=2274, w=22613, h=10079)

LOP = {
    "rgb":  dict(src=os.path.join(EXP, "ortho.tif"),        mau=False,
                 ten="net_rgb.jpg",  nhan="ortho màu Metashape"),
    "th":   dict(src=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"), mau=True,
                 ten="net_th.jpg",   nhan="ortho nhiệt tự ghép (H chấm tay)"),
    "thms": dict(src=os.path.join(EXP, "thermal_ortho.tif"), mau=True,
                 ten="net_thms.jpg", nhan="ortho nhiệt Metashape"),
    "xuoi": dict(src=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_dan_xuoi.tif"), mau=True,
                 ten="net_xuoi.jpg", nhan="ortho nhiệt DÁN XUÔI (để đối chứng)"),
    "burgb": dict(src=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_bu_rgb.tif"), mau=True,
                  ten="net_burgb.jpg", nhan="ortho nhiệt BÙ THEO ORTHO MÀU (lệch 4,7 cm)"),
}

ap = argparse.ArgumentParser()
ap.add_argument("--rong", type=int, default=8192,
                help="bề rộng tối đa; không bao giờ phóng quá độ phân giải gốc")
ap.add_argument("--lop", choices=list(LOP) + ["all"], default="all")
ap.add_argument("--chatluong", type=int, default=90, help="chất lượng JPEG")
ap.add_argument("--thumuc", default=os.path.join(BASE, "cong_cu/net"))
ap.add_argument("--pct", type=float, nargs=2, default=(1.0, 99.0),
                help="phân vị kéo giãn tương phản lớp nhiệt; 0 100 = min-max như cũ")
args = ap.parse_args()

os.makedirs(args.thumuc, exist_ok=True)

# frame -> lon/lat, để chuyển sang lưới của hai ortho nhiệt (GSD khác ortho màu).
with rasterio.open(LOP["rgb"]["src"]) as _o:
    _t = _o.transform
    LON0 = _t.c + _t.a * FRAME["c0"]
    LON1 = _t.c + _t.a * (FRAME["c0"] + FRAME["w"])
    LAT0 = _t.f + _t.e * FRAME["r0"]                      # mép TRÊN
    LAT1 = _t.f + _t.e * (FRAME["r0"] + FRAME["h"])


def lam(key):
    cf = LOP[key]
    if not os.path.exists(cf["src"]):
        print(f"[BỎ QUA] {key}: không thấy {cf['src']}")
        return
    with rasterio.open(cf["src"]) as s:
        # Lớp màu cắt thẳng bằng frame; hai lớp nhiệt quy qua lon/lat vì lưới khác.
        w = (rasterio.windows.Window(FRAME["c0"], FRAME["r0"], FRAME["w"], FRAME["h"])
             if key == "rgb" else from_bounds(LON0, LAT1, LON1, LAT0, s.transform))
        # Kích thước gốc của cửa sổ. Ảnh nguồn có pixel vuông theo MÉT chứ không
        # theo độ, nên tỉ lệ w/h ở đây (2,246) khác tỉ lệ độ (2,276) — cứ giữ
        # nguyên, viewer tự đọc aspect từ ảnh.
        gw, gh = int(round(w.width)), int(round(w.height))
        r = min(1.0, args.rong / gw)
        ow, oh = max(1, int(gw * r)), max(1, int(gh * r))

        # boundless: ortho nhiệt Metashape hẹp hơn cửa sổ, phần thiếu để trống.
        n = 1 if cf["mau"] and s.count == 1 else min(3, s.count)
        im = s.read(list(range(1, n + 1)), window=w, out_shape=(n, oh, ow),
                    boundless=True, fill_value=0,
                    resampling=rasterio.enums.Resampling.average)

    if n == 1:
        g = im[0]
        trong = g == 0
        v = g[~trong]
        if v.size == 0:
            print(f"[BỎ QUA] {key}: cửa sổ rỗng")
            return
        lo, hi = np.percentile(v, args.pct)
        if hi <= lo:
            lo, hi = float(v.min()), float(v.max() + 1)
        # Kéo giãn theo phân vị của RIÊNG cửa sổ này, không phải min-max toàn nhà
        # máy: cả trang trại ép vào 256 mức thì vùng đang soi chỉ dùng vài chục
        # mức, nhìn bệt. Cắt 1% hai đầu bỏ luôn vài pixel cực trị gây lệch thang.
        out = cv2.applyColorMap(
            np.clip((g.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255)
            .astype(np.uint8), cv2.COLORMAP_INFERNO)
        out[trong] = (28, 28, 28)
        ghi_them = f"  (phân vị {args.pct[0]:g}-{args.pct[1]:g}% -> {lo:.0f}..{hi:.0f})"
    else:
        out = cv2.merge([im[2], im[1], im[0]]) if n == 3 else cv2.merge([im[0]] * 3)
        ghi_them = ""

    p = os.path.join(args.thumuc, cf["ten"])
    cv2.imwrite(p, out, [cv2.IMWRITE_JPEG_QUALITY, args.chatluong])
    gsd = (LON1 - LON0) / ow * 111320 * np.cos(np.radians(11.424)) * 100
    print(f"[{key:4s}] {cf['nhan']}")
    print(f"       {ow} x {oh} px   GSD {gsd:.2f} cm/px   "
          f"nét gấp {ow/2400:.1f} lần bản 2400 px   "
          f"{os.path.getsize(p)/1e6:.1f} MB{ghi_them}")
    if r == 1.0 and gw > args.rong * 0.99:
        pass
    elif r < 1.0:
        print(f"       (gốc {gw} px, đã hạ theo --rong {args.rong})")
    else:
        print(f"       (đã là độ phân giải gốc, --rong lớn hơn cũng không nét thêm)")
    print(f"       -> {p}")


for k in ([args.lop] if args.lop != "all" else list(LOP)):
    lam(k)

print("\nChạy tiếp:  python ma/va_viewer_net.py")
