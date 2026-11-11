#!/usr/bin/env python3
"""
LOẠI ẢNH TRỄ CHỤP — tìm những ảnh nhiệt bấm máy lệch thời điểm so với ảnh RGB.

Bối cảnh: tư thế camera trong cameras.xml là tư thế của ảnh RGB (Metashape dựng từ
RGB). Nếu cảm biến nhiệt bấm trễ, cảnh trong ảnh nhiệt đã dịch đi so với tư thế đó,
nên khi dựng ortho nhiệt vùng ấy bị đặt sai chỗ. Đã đo được: ảnh 0080 trễ ~159 ms
(lệch 80 px RGB) trong khi 0320/0440 chỉ 4-12 ms.

Cách phát hiện, KHÔNG cần chấm tay từng ảnh:
  1. Chạy detector tấm pin trên ảnh RGB — nó làm rất tốt việc này (conf ~0,93).
     (Trên ảnh nhiệt thì detector hỏng, conf ~0,33, nên không chạy bên nhiệt.)
  2. Chiếu viền tấm vừa tìm được sang toạ độ ảnh nhiệt qua H chuẩn của thiết bị.
  3. Trượt viền đó quanh vị trí gốc, tìm chỗ khớp nhất với viền thật trong ảnh nhiệt.
     Lệch tìm được chính là lệch do trễ chụp.

Vì sao bước 3 không vướng vấn đề tuần hoàn của lưới tấm pin (thứ đã làm hỏng
hieu_chuan_tu_dong.py): ở đó ta dò lệch TỪ ĐẦU nên vùng tìm rộng hơn bước tấm và
thuật toán nhảy nhầm ô. Ở đây H đã đúng sẵn, ta chỉ dò lệch NHỎ quanh 0 trong bán
kính hẹp hơn nửa bước tấm, nên không thể nhảy sang ô kế bên.

    python ma/loc_anh_tre.py                    # quét toàn bộ ảnh
    python ma/loc_anh_tre.py --so-anh 40        # thử nhanh trên 40 ảnh
    python ma/loc_anh_tre.py --soi 0080         # soi kỹ một ảnh

####################################################################
# CẢNH BÁO VỀ H_da_bu: ĐỪNG DÙNG ĐỂ DỰNG LẠI ORTHO.
#
# Hằng số bù (+1,84 ; -3,70) px mà script này tính ra KHÔNG cải thiện ortho.
# Đã thử dựng lại ortho với H đã bù rồi đo trực tiếp:
#     trước bù 15,5 cm  ->  sau bù 14,4 cm
# Gần như không đổi, và hướng lệch ĐẢO DẤU (dy từ +5 sang -3 px) — tức bù
# quá đà theo chiều dọc.
#
# Đo tiếp trên 31 vùng rải khắp nhà máy thì rõ nguyên nhân:
#     15 vùng lệch lên, 16 vùng lệch xuống — chia đôi 50/50
#     trung vị chỉ -2,0 px trong khi lệch trung bình 7,2 px
# Lệch KHÁC NHAU TUỲ CHỖ, không cùng một hướng. Đây là nhiễu cục bộ (địa
# hình, độ cao tấm pin, sai số tư thế từng ảnh), KHÔNG phải sai lệch hệ
# thống — nên không bù được bằng một hằng số.
#
# Vì sao đo trên ẢNH LẺ lại thấy "44/60 ảnh cùng hướng" mà trên ORTHO lại
# 50/50: hai phép đo khác đối tượng. Trên ảnh lẻ đo lệch giữa hai CẢM BIẾN
# của cùng một lần bấm máy; trên ortho đo lệch của SẢN PHẨM GHÉP, nơi mỗi
# pixel lấy từ một ảnh khác nhau nên sai số tư thế từng ảnh trộn vào.
#
# PHẦN VẪN DÙNG ĐƯỢC: danh sách `anh_nen_loai` — ảnh lệch bất thường (như
# 0487 lệch 54 cm) vẫn nên loại khi dựng ortho. Chỉ H_da_bu là không dùng.
####################################################################
"""
import argparse
import csv
import json
import os
import time

import cv2
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = r"mo_hinh\best.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--so-anh", type=int, default=0, dest="so_anh",
                help="chỉ xử lý N ảnh rải đều (0 = tất cả)")
ap.add_argument("--soi", default=None, metavar="SEQ", help="soi kỹ một ảnh")
ap.add_argument("--model", default=MODEL)
ap.add_argument("--H", default=os.path.join(BASE, "ket_qua/thermal_to_rgb.json"))
ap.add_argument("--nguong-px", type=float, default=8.0, dest="nguong_px",
                help="lệch quá ngần này (px ảnh nhiệt) thì đánh dấu loại")
ap.add_argument("--ban-kinh", type=int, default=16, dest="ban_kinh",
                help="bán kính trượt (px nhiệt); phải NHỎ HƠN nửa bước tấm ~18")
ap.add_argument("--out", default=os.path.join(BASE, "du_lieu/anh_tre_chup.json"))
args = ap.parse_args()

GSD_RGB_CM = 0.993
d_H = json.load(open(args.H, encoding="utf-8"))
H = np.array(d_H["H_thermal_to_rgb"])
Hinv = np.linalg.inv(H)
TW, TH = d_H.get("thermal_size", [640, 512])
TI_LE = float(np.hypot(H[0, 0], H[1, 0]))          # px RGB trên 1 px nhiệt

rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}

from ultralytics import YOLO
model = YOLO(args.model)


def vien_nhiet(img):
    """Bản đồ viền của ảnh nhiệt, cùng cách xử lý đã kiểm chứng ở hieu_chuan_tu_dong."""
    f = cv2.medianBlur(cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX,
                                     dtype=cv2.CV_8U), 5).astype(np.float32)
    f = f - cv2.GaussianBlur(f, (0, 0), 15)
    f = cv2.GaussianBlur(f, (0, 0), 1.2)
    g = np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3),
                 cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3))
    t = np.percentile(g, 80)
    return np.clip((g - t) / max(1e-6, g.max() - t), 0, 1).astype(np.float32)


def vien_tu_tam_pin(rgb):
    """Viền tấm pin lấy từ detector chạy trên ảnh RGB, đã chiếu về toạ độ ảnh nhiệt.

    Detector chỉ đáng tin trên RGB (conf ~0,93); trên ảnh nhiệt nó hỏng (conf ~0,33)
    nên tuyệt đối không chạy bên nhiệt.
    """
    r = model.predict(rgb, conf=0.5, verbose=False, imgsz=1024, max_det=2000)[0]
    if r.obb is None or len(r.obb) == 0:
        return None, 0
    poly = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    ve = np.zeros((TH, TW), np.uint8)
    for p in poly:
        q = np.vstack([p.T, np.ones(4)])
        q = Hinv @ q
        q = (q[:2] / q[2]).T
        cv2.polylines(ve, [np.round(q).astype(np.int32)], True, 255, 1)
    return cv2.GaussianBlur(ve.astype(np.float32) / 255.0, (0, 0), 1.5), len(poly)


def do_lech(seq):
    """Trả về (dx, dy, do_net, so_tam) — lệch của ảnh nhiệt so với vị trí đáng lẽ."""
    r = rows.get(seq)
    if r is None:
        return None
    nhiet = cv2.imread(r["path_thermal"], cv2.IMREAD_GRAYSCALE)
    rgb = cv2.imread(r["path_rgb"])
    if nhiet is None or rgb is None:
        return None

    mau, so_tam = vien_tu_tam_pin(rgb)
    if mau is None or so_tam < 10:
        return None
    that = vien_nhiet(nhiet)

    # Trượt viền dự đoán quanh vị trí gốc, tìm chỗ khớp nhất. Bán kính hẹp hơn nửa
    # bước tấm (~18 px) nên không thể nhảy nhầm sang ô tấm kế bên.
    R = args.ban_kinh
    diem = np.full((2 * R + 1, 2 * R + 1), -1.0, np.float64)
    for iy, dy in enumerate(range(-R, R + 1)):
        for ix, dx in enumerate(range(-R, R + 1)):
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            mv = cv2.warpAffine(mau, M, (TW, TH))
            diem[iy, ix] = float((mv * that).sum())
    iy, ix = np.unravel_index(np.argmax(diem), diem.shape)
    dy, dx = float(iy - R), float(ix - R)

    # đỉnh có nổi rõ so với nền không — nền phẳng nghĩa là ảnh không đủ cấu trúc
    nen = np.median(diem)
    do_net = float((diem.max() - nen) / (nen + 1e-9))

    # tinh dưới mức pixel bằng parabol theo từng trục
    if 0 < ix < 2 * R:
        y0, y1, y2 = diem[iy, ix - 1], diem[iy, ix], diem[iy, ix + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            dx += 0.5 * (y0 - y2) / den
    if 0 < iy < 2 * R:
        y0, y1, y2 = diem[iy - 1, ix], diem[iy, ix], diem[iy + 1, ix]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            dy += 0.5 * (y0 - y2) / den
    return dx, dy, do_net, so_tam


# --------------------------------------------------------------- soi một ảnh
if args.soi:
    kq = do_lech(args.soi)
    if kq is None:
        raise SystemExit(f"[SOI {args.soi}] không xử lý được")
    dx, dy, net, n = kq
    cm = np.hypot(dx, dy) * TI_LE * GSD_RGB_CM
    print(f"[SOI {args.soi}] {n} tấm pin trên ảnh RGB")
    print(f"[SOI {args.soi}] lệch ({dx:+.2f}, {dy:+.2f}) px nhiệt = {cm:.1f} cm mặt đất")
    print(f"[SOI {args.soi}] độ nổi của đỉnh {net:.3f}")

    r = rows[args.soi]
    nhiet = cv2.imread(r["path_thermal"], cv2.IMREAD_GRAYSCALE)
    mau, _ = vien_tu_tam_pin(cv2.imread(r["path_rgb"]))
    nen = cv2.cvtColor(cv2.normalize(nhiet, None, 0, 255, cv2.NORM_MINMAX,
                                     dtype=cv2.CV_8U), cv2.COLOR_GRAY2BGR)
    truoc = nen.copy()
    truoc[mau > 0.15] = (0, 255, 255)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    mv = cv2.warpAffine(mau, M, (TW, TH))
    sau = nen.copy()
    sau[mv > 0.15] = (0, 255, 0)
    so = np.hstack([truoc, np.full((TH, 6, 3), 40, np.uint8), sau])
    so = cv2.copyMakeBorder(so, 30, 0, 0, 0, cv2.BORDER_CONSTANT, value=(40, 40, 40))
    cv2.putText(so, "vang = vi tri du doan", (8, 21), cv2.FONT_HERSHEY_SIMPLEX,
                .55, (0, 255, 255), 1)
    cv2.putText(so, f"xanh = da bu ({dx:+.1f},{dy:+.1f})px = {cm:.0f}cm",
                (TW + 14, 21), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 0), 1)
    p = os.path.join(BASE, "ket_qua/kiem_tra_warp", f"anh_tre_{args.soi}.jpg")
    cv2.imwrite(p, so, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"-> {p}")
    raise SystemExit(0)


# --------------------------------------------------------------- quét nhiều ảnh
seqs = sorted(rows)
if args.so_anh:
    buoc = max(1, len(seqs) // args.so_anh)
    seqs = seqs[::buoc][:args.so_anh]
print(f"[QUÉT] {len(seqs)} ảnh, bán kính trượt {args.ban_kinh} px "
      f"(nửa bước tấm ~18 px)\n")

t0 = time.time()
ket = []
for i, seq in enumerate(seqs):
    kq = do_lech(seq)
    if kq is None:
        continue
    dx, dy, net, n = kq
    lech = float(np.hypot(dx, dy))
    ket.append({"seq": seq, "dx": dx, "dy": dy, "lech_px": lech,
                "lech_cm": lech * TI_LE * GSD_RGB_CM, "do_net": net,
                "so_tam": n})
    if (i + 1) % 20 == 0 or i == len(seqs) - 1:
        print(f"   {i+1}/{len(seqs)} ảnh   {time.time()-t0:5.0f}s")

if not ket:
    raise SystemExit("Không ảnh nào xử lý được")

lech = np.array([k["lech_px"] for k in ket])
net = np.array([k["do_net"] for k in ket])
DX = np.array([k["dx"] for k in ket])
DY = np.array([k["dy"] for k in ket])

# --------------------------------------------- phần lệch HỆ THỐNG, bù được
# Ảnh chạm mép bán kính là giá trị bị kẹp, lệch thật có thể lớn hơn -> loại khỏi
# phép tính hằng số bù, nếu không trung vị bị kéo lệch.
kep = (np.abs(DX) >= args.ban_kinh - 0.51) | (np.abs(DY) >= args.ban_kinh - 0.51)
bu_x, bu_y = float(np.median(DX[~kep])), float(np.median(DY[~kep]))
lech_sau = np.hypot(DX - bu_x, DY - bu_y)
for k, l in zip(ket, lech_sau):
    k["lech_sau_bu_px"] = float(l)
    k["lech_sau_bu_cm"] = float(l * TI_LE * GSD_RGB_CM)

# H đã bù: dịch thêm (bu_x, bu_y) trong toạ độ ảnh nhiệt trước khi áp H
H_bu = H @ np.array([[1.0, 0, bu_x], [0, 1.0, bu_y], [0, 0, 1.0]])
# ảnh có đỉnh không nổi thì phép đo không tin được, tách riêng chứ không coi là xấu
nguong_net = float(np.percentile(net, 10))
tin = net >= nguong_net

xau = sorted([k for k in ket if k["lech_sau_bu_px"] > args.nguong_px
              and k["do_net"] >= nguong_net],
             key=lambda k: -k["lech_sau_bu_px"])

cm = TI_LE * GSD_RGB_CM
print(f"\n{'='*70}")
print(f"[KẾT QUẢ] đo được {len(ket)}/{len(seqs)} ảnh"
      f"   ({kep.sum()} ảnh chạm mép bán kính, lệch thật có thể lớn hơn)")
print(f"\n  Lệch dọc dy: {(DY<0).sum()} ảnh âm / {(DY>0).sum()} ảnh dương,"
      f" trung vị {np.median(DY):+.2f} px")
print(f"  Lệch ngang dx: trung vị {np.median(DX):+.2f} px")
if abs(np.median(DY)) > 2 * abs(np.median(DX)) or max((DY < 0).sum(), (DY > 0).sum()) > 0.7 * len(DY):
    print(f"  -> lệch thiên hẳn một phía: có thành phần HỆ THỐNG, bù được bằng hằng số")
else:
    print(f"  -> lệch phân bố đều quanh 0: chủ yếu là nhiễu ngẫu nhiên từng ảnh")

print(f"\n  Sai số trước khi bù : trung vị {np.median(lech[tin]):5.2f} px = "
      f"{np.median(lech[tin])*cm:5.1f} cm   p90 {np.percentile(lech[tin],90)*cm:5.1f} cm")
print(f"  Hằng số bù          : ({bu_x:+.2f}, {bu_y:+.2f}) px ảnh nhiệt = "
      f"{np.hypot(bu_x,bu_y)*cm:.1f} cm mặt đất")
print(f"  Sai số sau khi bù   : trung vị {np.median(lech_sau[tin]):5.2f} px = "
      f"{np.median(lech_sau[tin])*cm:5.1f} cm   p90 "
      f"{np.percentile(lech_sau[tin],90)*cm:5.1f} cm")
giam = 100 * (1 - np.median(lech_sau[tin]) / max(1e-9, np.median(lech[tin])))
print(f"  -> giảm {giam:.0f}% sai số trung vị")

print(f"\n  {len(xau)} ảnh vẫn lệch quá {args.nguong_px:g} px ({args.nguong_px*cm:.0f} cm) "
      f"SAU KHI BÙ -> nên loại khi dựng ortho")
if xau:
    print(f"\n      Mười ảnh lệch nhất (sau bù):")
    for k in xau[:10]:
        print(f"        {k['seq']}  ({k['dx']-bu_x:+6.2f},{k['dy']-bu_y:+6.2f}) px"
              f"  = {k['lech_sau_bu_cm']:6.1f} cm   {k['so_tam']:3d} tấm")
print(f"{'='*70}")

json.dump({
    "nguong_px": args.nguong_px,
    "nguong_cm": args.nguong_px * cm,
    "ban_kinh_px": args.ban_kinh,
    "so_anh_do_duoc": len(ket),
    "so_anh_cham_mep": int(kep.sum()),
    "bu_x_px": bu_x,
    "bu_y_px": bu_y,
    "H_da_bu": H_bu.tolist(),
    "lech_truoc_bu_trung_vi_cm": float(np.median(lech[tin]) * cm),
    "lech_truoc_bu_p90_cm": float(np.percentile(lech[tin], 90) * cm),
    "lech_sau_bu_trung_vi_cm": float(np.median(lech_sau[tin]) * cm),
    "lech_sau_bu_p90_cm": float(np.percentile(lech_sau[tin], 90) * cm),
    "anh_nen_loai": [k["seq"] for k in xau],
    "chi_tiet": ket,
    "ghi_chu": ("Lệch đo bằng cách chiếu viền tấm pin (detector chạy trên ảnh RGB) "
                "sang toạ độ ảnh nhiệt qua H, rồi trượt tìm chỗ khớp nhất. Bán kính "
                "trượt hẹp hơn nửa bước tấm nên không nhảy nhầm ô. "
                "H_da_bu = H đã cộng hằng số lệch hệ thống, dùng thay cho H cũ. "
                "anh_nen_loai đưa vào ghep_ortho_nhiet.py để bỏ khi dựng ortho."),
}, open(args.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"-> {args.out}")
print(f"   H_da_bu đã lưu trong file — dùng thay thermal_to_rgb.json để bớt "
      f"{giam:.0f}% sai số")
