#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cắt ảnh minh hoạ cho trang chủ -> thư mục `trang/`.

Ảnh nào cũng lấy từ chính thứ nó minh hoạ, không lấy hình mượn:

  * ortho .tif   -> đọc thu nhỏ thẳng từ file, lớp nhiệt tô INFERNO đúng như
                    nền của công cụ gán nhãn (phân vị 1-99%)
  * hai giao diện-> cắt cùng một khoảnh nhà máy trên nền `nhan/nen_rgb.jpg`,
                    một tấm vẽ TẤT CẢ box model gợi ý, một tấm chỉ vẽ viền tấm
                    đã chốt là có lỗi. Nhìn cạnh nhau là thấy ngay khác gì nhau.
  * trang khác   -> moi ảnh base64 đầu tiên nhúng trong chính file HTML đó

Thiếu ảnh thì trang chủ tự bỏ trống ô hình, không vỡ.

    py -3.13 ma/lam_anh_trang_chu.py           # dựng lại tất cả
    py -3.13 ma/lam_anh_trang_chu.py --nhanh   # bỏ qua ortho.tif 1,2 GB (chậm nhất)
"""
import base64
import json
import os
import re
import sys

import cv2
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
RA = "trang"
LON = os.path.join(RA, "lon")
os.makedirs(LON, exist_ok=True)
NHANH = "--nhanh" in sys.argv
EXP = "du_lieu/Thermal2_31M_full_export"
W = 720                      # bề rộng ảnh minh hoạ trên thẻ
WLON = 2400                  # bề rộng bản to, bấm vào thẻ mới mở ra
CL = [cv2.IMWRITE_JPEG_QUALITY, 84]
MAU = {"SingleHotSpot": (58, 138, 224), "MultiHotSpot": (91, 87, 224),
       "Bypass": (224, 122, 154), "ModuleOpenCircuit": (168, 95, 201)}  # BGR


def ghi(ten, im, lon=None):
    """Ghi ảnh thẻ; truyền `lon` thì ghi thêm bản to vào trang/lon/ để bấm xem."""
    p = os.path.join(RA, ten)
    cv2.imwrite(p, im, CL)
    n = os.path.getsize(p)
    if lon is not None:
        pl = os.path.join(LON, ten)
        cv2.imwrite(pl, lon, [cv2.IMWRITE_JPEG_QUALITY, 86])
        print("   %-26s %5.0f KB  + bản to %d px %5.0f KB"
              % (ten, n / 1e3, lon.shape[1], os.path.getsize(pl) / 1e3))
    else:
        print("   %-26s %5.0f KB" % (ten, n / 1e3))


def thu_nho(im, rong=W):
    k = rong / im.shape[1]
    return cv2.resize(im, (rong, max(1, int(round(im.shape[0] * k)))),
                      interpolation=cv2.INTER_AREA)


# ------------------------------------------------------------ 1. các ortho .tif
def cat_tif(duong, ten, nhiet):
    if not os.path.exists(duong):
        return
    import rasterio
    with rasterio.open(duong) as s:
        # đọc thẳng ở cỡ BẢN TO rồi thu nhỏ ra ảnh thẻ — chỉ quét file .tif một lần
        W = min(WLON, s.width)
        h = max(1, int(round(s.height * W / s.width)))
        if nhiet:
            g = s.read(1, out_shape=(h, W),
                       resampling=rasterio.enums.Resampling.average)
            trong = g == 0
            v = g[~trong]
            lo, hi = np.percentile(v, (1, 99)) if v.size else (0.0, 1.0)
            if hi <= lo:
                lo, hi = float(g.min()), float(g.max()) + 1
            im = cv2.applyColorMap(np.clip((g.astype(np.float32) - lo)
                                           * (255.0 / (hi - lo)), 0, 255).astype(np.uint8),
                                   cv2.COLORMAP_INFERNO)
            im[trong] = (26, 22, 20)
        elif s.count >= 3:
            a = s.read((1, 2, 3), out_shape=(3, h, W),
                       resampling=rasterio.enums.Resampling.average)
            im = np.ascontiguousarray(a.transpose(1, 2, 0)[:, :, ::-1])
        else:                                    # DSM: 1 băng float, tô xám
            g = s.read(1, out_shape=(h, W),
                       resampling=rasterio.enums.Resampling.average)
            v = g[np.isfinite(g) & (g > -1000)]
            lo, hi = np.percentile(v, (2, 98)) if v.size else (0.0, 1.0)
            im = cv2.applyColorMap(np.clip((g - lo) * (255.0 / max(hi - lo, 1e-6)),
                                           0, 255).astype(np.uint8), cv2.COLORMAP_BONE)
    ghi(ten, thu_nho(im), im)


print("[ORTHO] đọc thu nhỏ thẳng từ .tif")
for d, t, n in [("ket_qua/ortho/ortho_nhiet_bu_rgb.tif", "o_bu_rgb.jpg", True),
                ("ket_qua/ortho/ortho_nhiet_tu_lam.tif", "o_tu_lam.jpg", True),
                ("ket_qua/ortho/ortho_nhiet_nan.tif", "o_nan.jpg", True),
                ("ket_qua/ortho/ortho_nhiet_dan_xuoi.tif", "o_dan_xuoi.jpg", True),
                (EXP + "/thermal_ortho.tif", "o_metashape.jpg", False),
                (EXP + "/dsm.tif", "o_dsm.jpg", False)]:
    cat_tif(d, t, n)
if NHANH:
    print("   (bỏ qua ortho.tif — chạy không --nhanh để dựng)")
else:
    print("   ortho.tif 1,2 GB — đọc lâu, chờ...")
    cat_tif(EXP + "/ortho.tif", "o_mau.jpg", False)

# ------------------------------------------------ 2. hai giao diện, cùng khoảnh
print("[GIAO DIỆN] cắt cùng một khoảnh nhà máy cho hai bản")
html = open("cong_cu/gan_nhan_tam.html", encoding="utf-8").read()
i = html.index('DATA = {"nen"')
D = json.loads(html[i + len("DATA = "):html.index("\n", i)].rstrip(";"))
LOI = json.load(open("ket_qua/nhan_tam_loi.json", encoding="utf-8"))["loi"]
IDX = {m: k for k, m in enumerate(D["ma"])}

# khoảnh cắt: quanh chỗ dày lỗi nhất, đo bằng chính tâm các tấm đã chốt
tam = np.array([[(v[0] + v[2] + v[4] + v[6]) / 4, (v[1] + v[3] + v[5] + v[7]) / 4]
                for a in LOI for v in [a.get("vien_sua") or D["poly"][IDX[a["ma_tam"]]]]])
CW, CH = 1500, 844                      # khung cắt trên nền, tỉ lệ 16:9
cx, cy = np.median(tam[:, 0]), np.median(tam[:, 1])
x0 = int(np.clip(cx - CW / 2, 0, D["nen"]["w"] - CW))
y0 = int(np.clip(cy - CH / 2, 0, D["nen"]["h"] - CH))
nen = cv2.imread("nhan/nen_rgb.jpg")
if nen is None:
    print("   thiếu nhan/nen_rgb.jpg — bỏ qua hai ảnh giao diện")
else:
    o = nen[y0:y0 + CH, x0:x0 + CW].copy()

    def da_giac(v):
        return np.array([[v[k] - x0, v[k + 1] - y0] for k in range(0, 8, 2)],
                        np.int32).reshape(-1, 1, 2)

    # (a) bản CHƯA CHỐT: mọi box model gợi ý, kể cả cái sau này chấm là tấm tốt
    a = o.copy()
    for x, y, cls, conf, ma, n, tr, hop in D["loi"]:
        if hop and x0 <= x <= x0 + CW and y0 <= y <= y0 + CH:
            cv2.polylines(a, [da_giac(hop)], True, MAU.get(cls, (71, 196, 216)), 2,
                          cv2.LINE_AA)
    ghi("gd_chua_chot.jpg", thu_nho(a), a)

    # (b) bản ĐÃ CHỐT: chỉ tấm đã chốt có lỗi, tô nền nhạt cho nổi
    b = o.copy()
    phu = b.copy()
    for r in LOI:
        v = r.get("vien_sua") or D["poly"][IDX[r["ma_tam"]]]
        if not (x0 <= v[0] <= x0 + CW and y0 <= v[1] <= y0 + CH):
            continue
        m = MAU.get(r["tinh_trang"], (71, 196, 216))
        cv2.fillPoly(phu, [da_giac(v)], m)
        cv2.polylines(b, [da_giac(v)], True, m, 2, cv2.LINE_AA)
    b = cv2.addWeighted(phu, 0.28, b, 0.72, 0)
    for r in LOI:                       # vẽ lại viền cho nét sau khi trộn
        v = r.get("vien_sua") or D["poly"][IDX[r["ma_tam"]]]
        if x0 <= v[0] <= x0 + CW and y0 <= v[1] <= y0 + CH:
            cv2.polylines(b, [da_giac(v)], True,
                          MAU.get(r["tinh_trang"], (71, 196, 216)), 2, cv2.LINE_AA)
    ghi("gd_da_chot.jpg", thu_nho(b), b)

# ------------------------------------------- 3. moi ảnh nhúng trong trang khác
print("[TRANG] moi ảnh base64 đầu tiên trong từng file HTML")
KHAC = [("cong_cu/so_sanh_model.html", "t_so_sanh_model.jpg"),
        ("cong_cu/soi_tay_100_loi.html", "t_soi_tay.jpg"),
        ("tai_lieu/giai_thich_lech_khung.html", "t_lech_khung.jpg"),
        ("tai_lieu/TAI_LIEU_PIPELINE.html", "t_tai_lieu.jpg"),
        ("tai_lieu/slide_pipeline.html", "t_slide_pipeline.jpg"),
        ("tai_lieu/slide_quy_trinh.html", "t_slide_quy_trinh.jpg")]
# ngưỡng 1500 ký tự ~ ảnh 1 KB: bỏ mấy icon nhỏ, giữ ảnh nội dung thật
RE = re.compile(r"data:image/(?:jpeg|png);base64,([A-Za-z0-9+/=]{1500,})")
# Trang nào ghép chuỗi trong JS ("data:image/jpeg;base64," + t.rgb) thì tiền tố
# không dính liền base64 — bắt thẳng theo chữ ký JPEG /9j/ hoặc PNG iVBOR.
RE2 = re.compile(r"(?:/9j/|iVBORw0KGgo)[A-Za-z0-9+/=]{1500,}")
for f, ra in KHAC:
    if not os.path.exists(f):
        continue
    noi_dung = open(f, encoding="utf-8", errors="ignore").read()
    m = RE.search(noi_dung) or RE2.search(noi_dung)
    if not m:
        print("   %-26s không có ảnh nhúng đủ lớn" % f)
        continue
    chuoi = m.group(1) if m.re is RE else m.group(0)
    im = cv2.imdecode(np.frombuffer(base64.b64decode(chuoi + "=" * (-len(chuoi) % 4)),
                                    np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        continue
    ghi(ra, thu_nho(im), im if im.shape[1] > W else None)

# can_tay.html vẽ bằng canvas, ảnh nằm rời trong nhan/cantay/
ct = sorted(f for f in os.listdir("nhan/cantay") if f.endswith(".jpg")) \
    if os.path.isdir("nhan/cantay") else []
if ct:
    im = cv2.imread(os.path.join("nhan/cantay", ct[0]))
    if im is not None:
        ghi("t_can_tay.jpg", thu_nho(im, 360), im)

print("\n-> %s/  (%d ảnh)" % (RA, len([f for f in os.listdir(RA) if f.endswith(".jpg")])))
print("   chạy tiếp: py -3.13 ma/lam_trang_chu.py")
