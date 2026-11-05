#!/usr/bin/env python3
"""
HIỆU CHUẨN H TỰ ĐỘNG giữa ảnh nhiệt và ảnh RGB — không cần chấm tay điểm nào.

######################################################################
# CẢNH BÁO: HƯỚNG NÀY ĐÃ THỬ VÀ THẤT BẠI. ĐỪNG DÙNG KẾT QUẢ.
#
# Đã đo trực tiếp trên cặp ảnh 0280 (biết trước đáp án từ H chấm tay):
#   - dịch ĐÚNG là (4,7 ; 45,3) px ảnh nhiệt
#   - giá trị tương quan pha TẠI CHÍNH VỊ TRÍ ĐÚNG ĐÓ là ÂM (-0,0057),
#     tức còn tệ hơn nền nhiễu
#   - các đỉnh mạnh nhất nằm ở (-38,-38), (3,-37), (-39,-37)... cách nhau
#     đúng ~37-38 px = ĐÚNG BƯỚC TẤM PIN
#
# Nguyên nhân gốc: lưới tấm pin tuần hoàn quá đều. Bản đồ viền của một
# trang trại điện mặt trời gần như là hàm tuần hoàn hai chiều, nên tương
# quan pha không phân biệt được ô tấm này với ô tấm kế bên. Đây là hạn chế
# BẢN CHẤT của phương pháp trên loại cảnh này, không phải lỗi tham số —
# không có bán kính, ngưỡng hay bộ lọc nào sửa được.
#
# Bản đồ viền tự nó vẫn TỐT (xem kiem_tra_warp/hieu_chuan_0280.jpg: viền
# đỏ và xanh đều sắc nét, cấu trúc trùng nhau). Vấn đề nằm ở khâu GHÉP.
#
# Hướng còn lại đã kiểm tra:
#   1. Ghép theo góc tấm + RANSAC dùng detector tấm pin -> ĐÃ THỬ, KHÔNG DÙNG
#      ĐƯỢC. Detector solarfarm_inspection/backend/yolo_models/best.pt (YOLO OBB,
#      lớp 'solar_panel') chỉ nhận được tấm pin trên ảnh RGB:
#          ảnh RGB   : 300 tấm, độ tin cậy 0,91-0,94
#          ảnh NHIỆT :  4-10 tấm, độ tin cậy 0,30-0,38  (mức nhiễu)
#      Model huấn luyện trên ảnh màu nên không nhận ra tấm pin trong ảnh nhiệt.
#      Muốn đi hướng này phải huấn luyện lại detector trên ảnh nhiệt — một dự án
#      riêng, cần gán nhãn mới.
#   2. Neo bằng vật thể KHÔNG tuần hoàn trong cảnh: đường đi, mương, nhà trạm,
#      mép ruộng. Chưa thử. Rủi ro: nhiều trang trại không có đủ vật mốc như vậy
#      trong khung ảnh hẹp của cảm biến nhiệt (~15 x 12 m).
#   3. Chấm tay MỘT LẦN cho mỗi model drone (H gắn với thiết bị, không gắn với
#      trang trại) -> ĐÂY LÀ PHƯƠNG ÁN ĐANG DÙNG. Đủ cho bài toán hàng nghìn
#      trang trại, và đã xác nhận bằng số liệu: ba trong bốn lần hiệu chuẩn độc
#      lập khớp nhau trong 2-6 cm.
######################################################################

Bài toán: cần ma trận H đưa toạ độ ảnh nhiệt sang toạ độ ảnh RGB. Chấm tay 31 điểm
cho ra H tốt nhưng không nhân rộng được cho hàng nghìn trang trại.

Vì sao ghép được dù hai ảnh khác phổ: đã xác minh trong dữ liệu này (xem
kiem_tra_warp/soi_manh_tre.jpg) rằng mặt tấm pin trong ảnh nhiệt PHẲNG LÌ, không có
lưới cell như ảnh màu. Nên ghép theo độ sáng chắc chắn hỏng. Thứ hiện rõ ở CẢ HAI
phổ chỉ có VIỀN TẤM PIN. Vậy ta rút viền ra khỏi mỗi ảnh rồi ghép trên bản đồ viền.

Cách làm, mỗi cặp ảnh:
  1. Rút viền tấm pin ở cả hai ảnh (lọc nhiễu -> gradient -> nhị phân hoá).
  2. Quét thô bằng tương quan pha để tìm dịch chuyển + tỉ lệ gần đúng.
  3. Tinh bằng ECC trên bản đồ viền -> ra H đầy đủ cho cặp đó.
Rồi gộp nhiều cặp: lấy TRUNG VỊ từng phần tử. Trung vị tự loại ảnh hỏng và ảnh
trễ chụp bất thường (đã thấy ảnh 0080 trễ ~159 ms trong khi phần lớn dưới 12 ms).

Đồng thời xuất danh sách ảnh có H lệch xa trung vị -> dùng để LOẠI ẢNH khi dựng
ortho, giống cách ghep_ortho_nhiet.py đang loại ảnh ở đoạn quay đầu.

    python ma/hieu_chuan_tu_dong.py                    # 30 cặp rải đều
    python ma/hieu_chuan_tu_dong.py --so-cap 60
    python ma/hieu_chuan_tu_dong.py --soi 0280         # soi kỹ một cặp
"""
import argparse
import csv
import json
import os
import time

import cv2
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--so-cap", type=int, default=30, dest="so_cap",
                help="số cặp ảnh lấy mẫu, rải đều dọc chuyến bay")
ap.add_argument("--soi", default=None, metavar="SEQ",
                help="chỉ chạy một cặp và xuất ảnh chẩn đoán")
ap.add_argument("--doi-chieu", default=os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                dest="doi_chieu", help="H chấm tay để đối chiếu (chỉ để báo cáo)")
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/H_tu_dong.json"))
ap.add_argument("--nguong-lech-cm", type=float, default=15.0, dest="nguong_lech",
                help="lệch quá ngần này so với trung vị thì coi là ảnh xấu")
args = ap.parse_args()

GSD_RGB_CM = 0.993          # cm/px của ảnh RGB dưới đất, lấy từ hiệu chuẩn đã có

# Bán kính tìm đỉnh tương quan pha, tính bằng px ẢNH NHIỆT.
# Bối cảnh: bước tấm pin chỉ ~37 px nhiệt, trong khi lệch tâm quang giữa hai cảm
# biến ~40 px và trễ chụp thêm tới ~30 px. Vùng hợp lý rộng hơn bước lưới, nên
# KHÔNG thể tách đỉnh đúng chỉ bằng một lần quét. Giải pháp hai giai đoạn:
#   - giai đoạn 1 quét rộng trên nhiều ảnh, đỉnh ĐÚNG lặp lại nhất quán còn đỉnh
#     giả nhảy lung tung theo cảnh -> bỏ phiếu ra lệch tâm quang thật;
#   - giai đoạn 2 quét hẹp quanh giá trị đó, hẹp hơn nửa bước tấm nên không thể
#     nhảy nhầm sang đỉnh kế bên.
BAN_KINH_RONG = 90          # đủ bao lệch tâm quang (~40) + trễ chụp (~30)
BAN_KINH_HEP = 14           # < nửa bước tấm (37/2), chỉ bao dao động trễ chụp

rows = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}


# ----------------------------------------------------------------- rút viền
def ban_do_vien(img, sigma_nen=15, sigma_min=1.2):
    """Rút bản đồ viền tấm pin, chuẩn hoá về [0,1] float32.

    Ba bước, thứ tự quan trọng:
      - lọc trung vị: dập nhiễu muối tiêu của cảm biến nhiệt, giữ nguyên biên thẳng
      - trừ nền mờ: bỏ chênh sáng/chênh nhiệt biến thiên chậm (bóng mây, gradient
        nhiệt toàn cục) vốn khác hẳn nhau giữa hai phổ
      - biên độ gradient rồi ép ngưỡng theo phân vị: giữ lại đúng phần viền mạnh,
        bỏ vân cỏ/đất lốm đốm vốn chiếm quá nửa diện tích
    """
    f = img.astype(np.float32)
    f = cv2.medianBlur(cv2.normalize(f, None, 0, 255, cv2.NORM_MINMAX,
                                     dtype=cv2.CV_8U), 5).astype(np.float32)
    f = f - cv2.GaussianBlur(f, (0, 0), sigma_nen)
    f = cv2.GaussianBlur(f, (0, 0), sigma_min)
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    m = np.hypot(gx, gy)
    # phân vị 80 làm ngưỡng: viền tấm chiếm thiểu số pixel nên ngưỡng cao là đúng
    t = np.percentile(m, 80)
    m = np.clip((m - t) / max(1e-6, m.max() - t), 0, 1)
    return m.astype(np.float32)


def doc_cap(seq):
    r = rows[seq]
    t = cv2.imread(r["path_thermal"], cv2.IMREAD_GRAYSCALE)
    g = cv2.imread(r["path_rgb"], cv2.IMREAD_GRAYSCALE)
    return t, g


# ------------------------------------------------------- ước lượng H một cặp
def uoc_luong_H(nhiet, rgb, H_goi_y=None, tam_dich=None):
    """Ước lượng H đưa toạ độ ảnh nhiệt -> toạ độ ảnh RGB, dựa trên bản đồ viền.

    tam_dich: (dx, dy) đã biết từ vòng bỏ phiếu, dùng làm tâm vùng tìm kiếm. Nhờ
    nó bán kính thu về rất hẹp nên không còn nguy cơ bắt nhầm đỉnh của lưới tấm.

    Trả về (H, do_khop) hoặc (None, lý do). do_khop là hệ số tương quan ECC trên
    bản đồ viền, càng gần 1 càng khớp.
    """
    TH, TW = nhiet.shape
    RH, RW = rgb.shape

    vt = ban_do_vien(nhiet)
    vr = ban_do_vien(rgb)

    # Đưa RGB về đúng thang của ảnh nhiệt để ECC làm việc trên hai ảnh cùng cỡ.
    # Tỉ lệ lấy từ gợi ý nếu có, không thì suy từ khung ảnh.
    if H_goi_y is not None:
        s = float(np.hypot(H_goi_y[0, 0], H_goi_y[1, 0]))
    else:
        s = RW / TW
    vr_nho = cv2.resize(vr, (int(RW / s), int(RH / s)), interpolation=cv2.INTER_AREA)

    # ---- bước 1: dịch thô, CÓ RÀNG BUỘC
    # Lưới tấm pin tuần hoàn nên tương quan pha có vô số đỉnh cách nhau đúng một
    # bước tấm; thả tự do là nó chọn nhầm đỉnh, lệch nguyên một ô tấm (đã gặp:
    # kiem_tra_warp/hieu_chuan_0280.jpg bản đầu lệch 5,6 m). Hai cảm biến lại gắn
    # cùng thân drone nên lệch quang tâm chỉ cỡ vài cm — vài chục px ảnh nhiệt.
    # Vậy chỉ xét các đỉnh nằm trong bán kính hợp lý, chọn đỉnh mạnh nhất trong đó.
    # Ảnh nhiệt chỉ phủ PHẦN GIỮA ảnh RGB (khung hẹp hơn nhiều), nên phải cắt đúng
    # vùng giữa của RGB thu nhỏ. Cắt góc trên-trái như bản đầu thì hai mảnh gần như
    # không chồng nhau, tương quan pha không thể có đỉnh đúng.
    hh = min(vt.shape[0], vr_nho.shape[0])
    ww = min(vt.shape[1], vr_nho.shape[1])
    oy0 = (vr_nho.shape[0] - hh) // 2
    ox0 = (vr_nho.shape[1] - ww) // 2
    a = vt[:hh, :ww].copy()
    b = vr_nho[oy0:oy0 + hh, ox0:ox0 + ww].copy()

    win = cv2.createHanningWindow((ww, hh), cv2.CV_32F)
    A = cv2.dft(a * win, flags=cv2.DFT_COMPLEX_OUTPUT)
    B = cv2.dft(b * win, flags=cv2.DFT_COMPLEX_OUTPUT)
    C = cv2.mulSpectrums(A, B, 0, conjB=True)
    mag = cv2.magnitude(C[..., 0], C[..., 1]) + 1e-9
    C[..., 0] /= mag
    C[..., 1] /= mag
    r = cv2.idft(C, flags=cv2.DFT_REAL_OUTPUT | cv2.DFT_SCALE)
    r = np.fft.fftshift(r)
    cy0, cx0 = hh // 2, ww // 2
    if tam_dich is None:
        # chưa biết lệch tâm quang: xét cả vùng rộng, chấp nhận có thể bắt nhầm
        # đỉnh của lưới tấm — vòng bỏ phiếu bên ngoài sẽ lọc ra đỉnh đúng.
        tx, ty, R = 0.0, 0.0, BAN_KINH_RONG
    else:
        # đã biết lệch tâm quang: chỉ tìm quanh đó trong bán kính NHỎ HƠN NỬA BƯỚC
        # TẤM, nhờ vậy loại hẳn khả năng nhảy sang đỉnh giả kế bên.
        tx, ty, R = tam_dich[0], tam_dich[1], BAN_KINH_HEP
    R = int(R)
    ox = int(np.clip(cx0 + tx, R, ww - R - 1))
    oy = int(np.clip(cy0 + ty, R, hh - R - 1))
    vung_r = r[oy - R:oy + R + 1, ox - R:ox + R + 1]
    iy, ix = np.unravel_index(np.argmax(vung_r), vung_r.shape)
    dy = float(iy + oy - R - cy0)
    dx = float(ix + ox - R - cx0)
    # độ nổi của đỉnh so với nền: dưới ngưỡng nghĩa là không có căn chỉnh tin được
    noi = float(vung_r.max() / (np.abs(r).mean() + 1e-12))

    # ---- bước 2: tinh bằng ECC, mô hình affine (đủ cho hai cảm biến cùng trục)
    W = np.array([[1, 0, dx], [0, 1, dy]], np.float32)
    try:
        tieu_chi = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
        do_khop, W = cv2.findTransformECC(b, a, W, cv2.MOTION_AFFINE, tieu_chi,
                                          None, 5)
    except cv2.error as e:
        return None, f"ECC không hội tụ ({str(e).splitlines()[-1][:40]})"

    # W đưa toạ độ b(=RGB thu nhỏ) sang a(=nhiệt). Ta cần chiều ngược lại,
    # rồi nhân lại tỉ lệ s để về toạ độ RGB gốc.
    # W đưa toạ độ b (RGB thu nhỏ ĐÃ CẮT) sang a (ảnh nhiệt). Muốn về toạ độ RGB
    # gốc phải: nghịch đảo W -> cộng lại lượng đã cắt (ox0,oy0) -> nhân tỉ lệ s.
    W3 = np.vstack([W, [0, 0, 1]])
    cat = np.array([[1.0, 0, ox0], [0, 1.0, oy0], [0, 0, 1.0]])
    H = np.diag([s, s, 1.0]) @ cat @ np.linalg.inv(W3)
    return H.astype(np.float64), {"do_khop": float(do_khop), "noi": noi,
                                  "dx_tho": dx, "dy_tho": dy}


# --------------------------------------------------------------- chạy 1 cặp
if args.soi:
    seq = args.soi
    nhiet, rgb = doc_cap(seq)
    H, tt = uoc_luong_H(nhiet, rgb)
    if H is None:
        print(f"[SOI {seq}]  hỏng: {tt}")
    else:
        print(f"[SOI {seq}]  ECC {tt['do_khop']:.4f}  đỉnh nổi {tt['noi']:.1f}"
              f"  dịch thô ({tt['dx_tho']:.1f},{tt['dy_tho']:.1f}) px nhiệt")
        c = np.array([320.0, 256.0, 1.0])
        p = H @ c; p = p[:2] / p[2]
        print(f"[SOI {seq}]  tâm ảnh nhiệt -> RGB ({p[0]:.1f}, {p[1]:.1f})")
        H0 = np.array(json.load(open(args.doi_chieu, encoding="utf-8"))
                      ["H_thermal_to_rgb"])
        q = H0 @ c; q = q[:2] / q[2]
        d = np.linalg.norm(p - q)
        print(f"[SOI {seq}]  H chấm tay  -> RGB ({q[0]:.1f}, {q[1]:.1f})"
              f"   lệch {d:.1f} px = {d*GSD_RGB_CM:.1f} cm")

        warp = cv2.warpPerspective(nhiet, H, (rgb.shape[1], rgb.shape[0]))
        vr8 = cv2.normalize(ban_do_vien(rgb), None, 0, 255, cv2.NORM_MINMAX,
                            dtype=cv2.CV_8U)
        vt8 = cv2.warpPerspective(
            cv2.normalize(ban_do_vien(nhiet), None, 0, 255, cv2.NORM_MINMAX,
                          dtype=cv2.CV_8U), H, (rgb.shape[1], rgb.shape[0]))
        so = np.zeros(rgb.shape + (3,), np.uint8)
        so[..., 1] = vr8            # xanh = viền ảnh RGB
        so[..., 2] = vt8            # đỏ   = viền ảnh nhiệt (đã nắn)
        sc = 1400 / so.shape[1]
        so = cv2.resize(so, None, fx=sc, fy=sc)
        cv2.putText(so, "xanh = vien RGB   do = vien NHIET da nan", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2)
        p_ = os.path.join(BASE, "ket_qua/kiem_tra_warp", f"hieu_chuan_{seq}.jpg")
        cv2.imwrite(p_, so, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"-> {p_}")
    raise SystemExit(0)


# --------------------------------------------------------- chạy nhiều cặp
seqs = sorted(rows)
buoc = max(1, len(seqs) // args.so_cap)
chon = seqs[::buoc][:args.so_cap]
print(f"[CẶP] lấy {len(chon)} cặp rải đều trong {len(seqs)} ảnh\n")

t0 = time.time()

# ---- giai đoạn 1: bỏ phiếu tìm lệch tâm quang giữa hai cảm biến
# Quét rộng nên từng ảnh riêng lẻ có thể bắt nhầm đỉnh của lưới tấm. Nhưng đỉnh
# ĐÚNG do lệch tâm quang là cố định theo thiết bị nên lặp lại ở mọi ảnh, còn đỉnh
# giả phụ thuộc cảnh nên tản mát. Gom theo ô lưới rồi lấy ô đông phiếu nhất.
print("[GIAI ĐOẠN 1] bỏ phiếu tìm lệch tâm quang giữa hai cảm biến")
phieu = []
for seq in chon:
    nhiet, rgb = doc_cap(seq)
    if nhiet is None or rgb is None:
        continue
    H, tt = uoc_luong_H(nhiet, rgb)
    if H is None:
        continue
    phieu.append((tt["dx_tho"], tt["dy_tho"], tt["noi"], seq))

if len(phieu) < 5:
    raise SystemExit(f"Chỉ {len(phieu)} ảnh cho được đỉnh — quá ít để bỏ phiếu.")

P = np.array([[p[0], p[1]] for p in phieu])
O = int(BAN_KINH_HEP)                      # cạnh ô gom phiếu
khoa = np.round(P / O).astype(np.int64)
uniq, dem = np.unique(khoa, axis=0, return_counts=True)
thang = uniq[np.argmax(dem)]
trong_o = np.all(khoa == thang, axis=1)
tam_dich = P[trong_o].mean(axis=0)
print(f"   {len(phieu)} ảnh cho đỉnh, ô đông nhất được {dem.max()}/{len(phieu)} phiếu")
print(f"   -> lệch tâm quang ≈ ({tam_dich[0]:.1f}, {tam_dich[1]:.1f}) px ảnh nhiệt")
if dem.max() < max(3, 0.25 * len(phieu)):
    print("   [CẢNH BÁO] phiếu tản mát, lệch tâm quang chưa chắc chắn")

# ---- giai đoạn 2: quét hẹp quanh lệch tâm quang -> H từng cặp
print(f"\n[GIAI ĐOẠN 2] quét hẹp (bán kính {BAN_KINH_HEP} px) quanh giá trị đó")
ket = []
H_goi_y = None
for seq in chon:
    nhiet, rgb = doc_cap(seq)
    if nhiet is None or rgb is None:
        print(f"   {seq}  bỏ: không đọc được ảnh")
        continue
    H, tt = uoc_luong_H(nhiet, rgb, H_goi_y, tam_dich)
    if H is None:
        print(f"   {seq}  bỏ: {tt}")
        continue
    c = np.array([320.0, 256.0, 1.0])
    p = H @ c; p = p[:2] / p[2]
    ket.append({"seq": seq, "H": H.tolist(), "do_khop": tt["do_khop"],
                "noi": tt["noi"], "tam_x": float(p[0]), "tam_y": float(p[1])})
    if H_goi_y is None:
        H_goi_y = H
    print(f"   {seq}  khớp {tt['do_khop']:.4f}  nổi {tt['noi']:5.1f}"
          f"  tâm -> ({p[0]:7.1f},{p[1]:7.1f})   {time.time()-t0:5.0f}s")

if len(ket) < 5:
    raise SystemExit(f"\nChỉ {len(ket)} cặp ghép được — quá ít để lấy trung vị.")

# ------------------------------------------------- gộp: trung vị từng phần tử
Hs = np.array([k["H"] for k in ket])
H_tv = np.median(Hs, axis=0)
H_tv /= H_tv[2, 2]

# lệch của từng ảnh so với trung vị, quy ra cm mặt đất tại tâm ảnh
c = np.array([320.0, 256.0, 1.0])
q = H_tv @ c; q = q[:2] / q[2]
for k in ket:
    p = np.array([k["tam_x"], k["tam_y"]])
    k["lech_cm"] = float(np.linalg.norm(p - q) * GSD_RGB_CM)

lech = np.array([k["lech_cm"] for k in ket])
xau = [k["seq"] for k in ket if k["lech_cm"] > args.nguong_lech]

print(f"\n{'='*66}")
print(f"[GỘP] {len(ket)} cặp ghép thành công / {len(chon)} cặp thử")
print(f"      lệch so với trung vị:  trung vị {np.median(lech):.1f} cm"
      f"   p90 {np.percentile(lech,90):.1f} cm   max {lech.max():.1f} cm")
print(f"      {len(xau)} ảnh lệch quá {args.nguong_lech:g} cm -> nên loại khi dựng ortho")

H0 = np.array(json.load(open(args.doi_chieu, encoding="utf-8"))["H_thermal_to_rgb"])
b = H0 @ c; b = b[:2] / b[2]
d_tay = float(np.linalg.norm(q - b) * GSD_RGB_CM)
print(f"\n[ĐỐI CHIẾU với H chấm tay 31 điểm]")
print(f"      tâm ảnh nhiệt -> tự động ({q[0]:.1f},{q[1]:.1f})"
      f"   chấm tay ({b[0]:.1f},{b[1]:.1f})")
print(f"      lệch giữa hai cách: {d_tay:.1f} cm")
if d_tay < 10:
    print(f"      -> khớp tốt, H tự động dùng thay được cho H chấm tay")
else:
    print(f"      -> lệch còn lớn, CHƯA thay được — cần soi thêm")
print(f"{'='*66}")

json.dump({
    "H_thermal_to_rgb": H_tv.tolist(),
    "so_cap_thu": len(chon),
    "so_cap_ghep_duoc": len(ket),
    "lech_trung_vi_cm": float(np.median(lech)),
    "lech_p90_cm": float(np.percentile(lech, 90)),
    "lech_max_cm": float(lech.max()),
    "lech_so_voi_cham_tay_cm": d_tay,
    "nguong_lech_cm": args.nguong_lech,
    "anh_nen_loai": xau,
    "chi_tiet": ket,
    "ghi_chu": ("H lấy trung vị từng phần tử qua nhiều cặp. Trung vị tự loại ảnh "
                "trễ chụp bất thường. anh_nen_loai là các ảnh lệch xa trung vị, "
                "nên bỏ khi dựng ortho nhiệt."),
}, open(args.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"-> {args.out}")
