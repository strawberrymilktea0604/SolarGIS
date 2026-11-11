#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Đo HÀM TRUYỀN từ mảng 16-bit (APP3) sang ẢNH XEM 8-bit trong R-JPEG của DJI.

Câu hỏi: ảnh xem 8-bit mà `cv2.imread` đọc ra có phải một hàm của RIÊNG giá trị
DN thô không? Nếu có — dù là hàm phi tuyến, dù đổi theo từng khung — thì nó
NGHỊCH ĐẢO ĐƯỢC theo từng khung, và cách làm chuẩn của lĩnh vực (kéo giãn để
SfM bắt điểm khớp rồi đảo ngược phép giãn, Swath Mosaic 2021) vẫn dùng được.

Cách đo, chạy riêng cho TỪNG khung:
  1. Giải APP3 lấy mảng DN uint16 640×512 (dùng lại ma/doc_nhiet_raw.py).
  2. Lọc VÙNG PHẲNG: biên độ DN cục bộ 5×5 nhỏ hơn `--nguong-phang`. Bỏ mép
     vật thể đi thì nhiễu nén JPEG và lệch căn chỉnh một điểm ảnh hết cửa
     giải thích phần dư.
  3. Dựng LUT TỐT NHẤT CÓ THỂ cho khung đó: trung bình mức xám theo từng giá
     trị DN, nội suy ô trống, ép đơn điệu bằng cummax. Không khớp tuyến tính —
     tuyến tính thua sẵn, thua cũng không chứng minh được gì.
  4. Phần dư = xám thật − LUT(DN). Nếu ảnh xem là hàm của riêng DN thì phần dư
     chỉ còn nhiễu nén: vô hướng, không cấu trúc không gian, và bị trung vị
     theo ô 16×16 dập gần hết.
  5. Báo phần dư theo ô 16×16 (đã dập nhiễu nén) và tương quan của phần dư với
     cột / hàng. Ô lệch nhau vài bậc xám ở CÙNG một DN nghĩa là bộ dựng ảnh có
     thành phần THÍCH NGHI THEO VÙNG, và ảnh xem không nghịch đảo được kể cả
     trong một khung.

    py -3.13 ma/do_ham_truyen_8bit.py                  # 100 khung, ~2 phút
    py -3.13 ma/do_ham_truyen_8bit.py --so-anh 0       # cả 598 khung
    py -3.13 ma/do_ham_truyen_8bit.py --nguong-phang 60
"""
import argparse
import csv
import json
import os

import cv2
import numpy as np

import goc  # đưa tiến trình về gốc dự án  # noqa: F401
from doc_nhiet_raw import doc_raw, W, H

ap = argparse.ArgumentParser()
ap.add_argument("--so-anh", type=int, default=100, dest="so_anh",
                help="0 = cả 598 khung; mặc định lấy mẫu đều 100 khung")
ap.add_argument("--nguong-phang", type=float, default=150.0, dest="nguong_phang",
                help="biên độ DN cục bộ 5x5 tối đa để coi là vùng phẳng")
ap.add_argument("--o", type=int, default=16, help="cạnh ô để lấy trung vị phần dư")
ap.add_argument("--thu-muc", default=None, dest="thu_muc",
                help="đo trên một THƯ MỤC ảnh _T thay vì manifest 598 ảnh — "
                     "dùng để lặp lại phép đo trên kho huấn luyện đa site đã có sẵn")
ap.add_argument("--out", default="ket_qua/ham_truyen_8bit.json")
args = ap.parse_args()

if args.thu_muc:
    import glob
    rows = [{"seq": os.path.basename(f), "path_thermal": f}
            for f in sorted(glob.glob(os.path.join(args.thu_muc, "*_T.*")))]
else:
    rows = list(csv.DictReader(open("du_lieu/manifest_anh.csv", encoding="utf-8-sig")))
if args.so_anh and args.so_anh < len(rows):
    idx = np.linspace(0, len(rows) - 1, args.so_anh).astype(int)
    rows = [rows[i] for i in sorted(set(idx.tolist()))]
print(f"[ẢNH] {len(rows)} khung, ngưỡng phẳng {args.nguong_phang:.0f} DN, ô {args.o}px")

K5 = np.ones((5, 5), np.uint8)
ket, ban_do = [], []
for i, r in enumerate(rows, 1):
    p = r["path_thermal"]
    dn = doc_raw(p)
    xam = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if dn is None or xam is None:
        continue
    dn = dn.astype(np.int32)
    f = dn.astype(np.float32)
    phang = (cv2.dilate(f, K5) - cv2.erode(f, K5)) < args.nguong_phang
    if phang.sum() < 5000:
        continue

    D = dn[phang].astype(np.int64)
    G = xam[phang].astype(np.float64)
    lo, hi = int(D.min()), int(D.max())
    n = hi - lo + 1
    j = D - lo
    tong = np.bincount(j, weights=G, minlength=n)
    dem = np.bincount(j, minlength=n)
    tb = np.where(dem > 0, tong / np.maximum(dem, 1), np.nan)
    co = ~np.isnan(tb)
    lut = np.maximum.accumulate(np.interp(np.arange(n), np.arange(n)[co], tb[co]))

    du = G - lut[j]                       # phần dư sau LUT tốt nhất của khung
    duM = np.full((H, W), np.nan)
    duM[phang] = du
    yy, xx = np.mgrid[0:H, 0:W]

    B = args.o
    bando = np.full((H // B, W // B), np.nan)
    for y in range(H // B):
        for x in range(W // B):
            v = duM[y * B:(y + 1) * B, x * B:(x + 1) * B]
            v = v[~np.isnan(v)]
            if v.size >= B * B // 2.56:   # ô phải đủ điểm phẳng mới tính
                bando[y, x] = float(np.median(v))
    ban_do.append(bando)
    o = bando[~np.isnan(bando)]
    if o.size == 0:
        o = np.array([0.0])

    # nửa trái so nửa phải ở CÙNG dải DN quanh trung vị cảnh
    md = int(np.median(dn))
    dai = (np.abs(dn - md) <= 5) & phang
    nua = np.zeros_like(dai)
    nua[:, :W // 2] = True
    tr, ph = xam[dai & nua], xam[dai & ~nua]

    ket.append({
        "seq": r["seq"],
        "so_muc_dn": int(len(np.unique(dn))),
        "dn_p1": float(np.percentile(dn, 1)), "dn_p99": float(np.percentile(dn, 99)),
        "xam_min": int(xam.min()), "xam_max": int(xam.max()),
        "ti_le_phang": float(phang.mean()),
        "du_rms": float(np.sqrt((du ** 2).mean())),
        "o_rms": float(np.sqrt((o ** 2).mean())),
        "o_p95": float(np.percentile(np.abs(o), 95)),
        "o_max": float(np.abs(o).max()),
        "r_cot": float(np.corrcoef(du, xx[phang])[0, 1]),
        "r_hang": float(np.corrcoef(du, yy[phang])[0, 1]),
        "lech_trai_phai": (float(np.median(tr)) - float(np.median(ph)))
                          if (tr.size and ph.size) else None,
    })
    if i % 25 == 0:
        print(f"   {i}/{len(rows)}")


# ---- phần dư CỐ ĐỊNH trên mặt phẳng tiêu hay ĐỔI THEO CẢNH?
# Nếu chênh giữa hai sản phẩm đến từ vignetting hay từ hai bảng flat-field khác
# nhau thì bản đồ phần dư phải GIỐNG NHAU ở mọi khung (tương quan cặp cao, độ
# lệch giữa các khung nhỏ). Nếu đến từ một bộ dựng ảnh thích nghi theo NỘI DUNG
# CẢNH thì ngược lại. Đây là phép thử phân biệt hai cơ chế, làm hết bằng dữ liệu
# đã có trên đĩa.
M = np.array(ban_do)
with np.errstate(invalid="ignore"):
    tb_map = np.nanmean(M, axis=0)
    sd_map = np.nanstd(M, axis=0)
cap = []
for a in range(0, len(M), max(1, len(M) // 12)):
    for b in range(a + 1, len(M), max(1, len(M) // 12)):
        u, v = M[a].ravel(), M[b].ravel()
        k = ~(np.isnan(u) | np.isnan(v))
        if k.sum() > 200:
            cap.append(float(np.corrcoef(u[k], v[k])[0, 1]))
co_dinh = {
    "rms_ban_do_trung_binh": float(np.sqrt(np.nanmean(tb_map ** 2))),
    "max_ban_do_trung_binh": float(np.nanmax(np.abs(tb_map))),
    "do_lech_giua_cac_khung_trung_vi": float(np.nanmedian(sd_map)),
    "tuong_quan_cap_trung_vi": float(np.median(cap)) if cap else None,
    "tuong_quan_cap_p90": float(np.percentile(cap, 90)) if cap else None,
    "so_cap": len(cap),
}


def dai_so(k):
    v = [x[k] for x in ket if x[k] is not None]
    return {"min": min(v), "trung_vi": float(np.median(v)), "max": max(v)}


tom = {
    "so_khung": len(ket),
    "nguong_phang_dn": args.nguong_phang,
    "canh_o_px": args.o,
    "so_muc_dn": dai_so("so_muc_dn"),
    "xam_min_luon_0": all(x["xam_min"] == 0 for x in ket),
    "xam_max_luon_255": all(x["xam_max"] == 255 for x in ket),
    "du_rms_bac_xam": dai_so("du_rms"),
    "o_rms_bac_xam": dai_so("o_rms"),
    "o_max_bac_xam": dai_so("o_max"),
    "abs_r_cot": {"trung_vi": float(np.median([abs(x["r_cot"]) for x in ket])),
                  "max": float(max(abs(x["r_cot"]) for x in ket))},
    "abs_lech_trai_phai": {"trung_vi": float(np.median([abs(x["lech_trai_phai"])
                                                       for x in ket if x["lech_trai_phai"] is not None])),
                           "max": float(max(abs(x["lech_trai_phai"])
                                            for x in ket if x["lech_trai_phai"] is not None))},
    "phan_du_co_dinh_khong": co_dinh,
}
os.makedirs(os.path.dirname(args.out), exist_ok=True)
json.dump({"tom_tat": tom, "tung_khung": ket}, open(args.out, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n[TÓM TẮT]")
print(json.dumps(tom, ensure_ascii=False, indent=1))
print(f"\n-> {args.out}")
