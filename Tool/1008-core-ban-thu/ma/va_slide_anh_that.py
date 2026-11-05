#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Chèn ba slide ẢNH THẬT vào `slide_thuat_toan.html`, cạnh slide sơ đồ tương ứng.

Deck gốc có 17 slide, ba hình đều là SVG vẽ tay giải thích cơ chế. Script này
thêm ba slide ảnh thật của chính chuyến bay, đặt ngay sau slide sơ đồ mà nó minh hoạ:

    sau ⑧ chuỗi chiếu   -> R1 chuỗi chiếu trên dữ liệu thật
    sau ⑨ gộp trùng     -> R3 gán vào polygon tấm pin
    sau ⑫ hướng cảnh    -> R2 cùng ô ortho, bắc-lên và xoay 270°

Ảnh nhúng thẳng dạng data URI, KHÔNG trỏ đường dẫn: bản publish lên artifact chặn
mọi tham chiếu ra ngoài file, trỏ `hinh/...` là ra ô ảnh vỡ. Đổi lại phải thu nhỏ
trước, nếu không deck phình từ 52 KB lên vài MB.

Cần có trước:
    py -3.13 ma/hinh_minh_hoa_thuc_te.py

    py -3.13 ma/va_slide_anh_that.py
    py -3.13 ma/va_slide_anh_that.py --hoan-tac
"""
import argparse
import base64
import os
import shutil

import cv2

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "tai_lieu/slide_thuat_toan.html")
SAO = HTML + ".truoc_anh_that.bak"
DAU = "<!-- slide ảnh thật, chèn bằng ma/va_slide_anh_that.py -->"

ap = argparse.ArgumentParser()
ap.add_argument("--html", default=HTML)
ap.add_argument("--rong", type=int, default=1500, help="bề ngang tối đa khi nhúng")
ap.add_argument("--chat-luong", type=int, default=82, dest="chat_luong")
ap.add_argument("--hoan-tac", action="store_true", dest="hoan_tac")
args = ap.parse_args()

if args.hoan_tac:
    if not os.path.exists(SAO):
        raise SystemExit("Không có bản sao %s để hoàn tác." % SAO)
    shutil.copy2(SAO, args.html)
    print("[HOÀN TÁC] đã khôi phục từ %s" % SAO)
    raise SystemExit


def nhung(ten, thu_muc="hinh"):
    p = os.path.join(BASE, "tai_lieu", thu_muc, ten)
    if not os.path.exists(p):
        raise SystemExit("[DỪNG] chưa có %s — chạy ma/hinh_minh_hoa_thuc_te.py trước." % ten)
    im = cv2.imread(p)
    if im.shape[1] > args.rong:
        k = args.rong / im.shape[1]
        im = cv2.resize(im, (args.rong, int(im.shape[0] * k)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, args.chat_luong])
    if not ok:
        raise SystemExit("[DỪNG] không mã hoá được %s" % ten)
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    print("   %-26s %5d px -> %.0f KB base64" % (ten, im.shape[1], len(b64) / 1024))
    return "data:image/jpeg;base64," + b64


def slide(eyebrow, tieu_de, nhan_manh, mo_ta, anh, chu_thich, lop=""):
    return """%s
<section class="slide">
  <div class="wrap">
    <div class="eyebrow%s">%s</div>
    <h2>%s <em%s>%s</em></h2>
    <p class="sub">%s</p>
    <figure class="figbox">
      <img src="%s" alt="%s" style="display:block;width:100%%;height:auto;max-height:56dvh;
           object-fit:contain;border-radius:8px"/>
      <figcaption>%s</figcaption>
    </figure>
  </div>
</section>
""" % (DAU, lop, eyebrow, tieu_de, (' class="b"' if lop else ""), nhan_manh, mo_ta,
       anh, chu_thich.replace('"', "'")[:180], chu_thich)


src = open(args.html, encoding="utf-8").read()
if DAU in src:
    raise SystemExit("Đã vá rồi. Muốn vá lại thì --hoan-tac trước.")

print("[NHÚNG]")
s_r1 = slide(
    "Nhánh A · bước ② trên dữ liệu thật",
    "Box trên ảnh gốc, vết trên", "mặt đất",
    "Bốn ca thật. Trái là ảnh nhiệt 640×512 với mọi box YOLO tìm được; phải là ortho màu "
    "cắt cửa sổ 6 m, khung đỏ là vết của lỗi sau khi chiếu qua DSM.",
    nhung("thuc_te_r1_chieu.jpg"),
    "<b>Hình không tuyên bố cặp box nào ứng với vết nào</b> — cái cần thấy là box trên ảnh gốc "
    "và vết trên mặt đất cùng rơi vào một tấm pin. Chú ý ca cuối: vết đỏ méo thành hình bình "
    "hành, đó là hiệu ứng chụp xiên.")

s_r3 = slide(
    "Bước chung của cả hai nhánh",
    "Gán vào", "polygon tấm pin",
    "6 473 polygon dò sẵn trên ortho màu. Mỗi lỗi gán bằng hai phép cùng lúc: "
    "điểm-trong-đa-giác cho tâm, và IoU giữa vết tứ giác xoay với polygon tấm.",
    nhung("thuc_te_r3_gan_tam.jpg"),
    "<b>Xanh:</b> polygon tấm pin. <b>Đỏ:</b> vết lỗi đã chiếu, IoU 0,974 với tấm <code>D12-T041</code>. "
    "Chú ý khung xanh nằm giữa bãi cỏ — detector tấm pin bắt nhầm một mảng cỏ. Đó là lý do bước gán "
    "luôn báo kèm <code>in_panel</code> và <code>dist_cm</code>.")

s_r2 = slide(
    "Thủ phạm, trên dữ liệu thật",
    "Cùng những pixel đó,", "hai kết quả",
    "Cùng một ô ortho nhiệt, đưa vào model hai lần. Ảnh bên phải đã quay về bắc-lên "
    "sau khi vẽ box, để hai bên so được trực tiếp.",
    nhung("thuc_te_r2_huong.jpg"),
    "<b>Trái, bắc-lên:</b> model bỏ sót — chữ thập trắng là lỗi thật, khung lơ là những box model "
    "vẫn nổ ra nhưng ở chỗ khác. <b>Phải, xoay 270°:</b> bắt trúng với conf 0,94–0,98. Model "
    "<b>không hề im lặng</b> ở cột trái — nó vẫn nổ 3–6 box mỗi ô. Đó là hành vi của model đang "
    "nhìn cảnh lạ, không phải của model đang nhìn ảnh mất tín hiệu.",
    lop=" b")

s_c1 = slide(
    "Hiệu chuẩn H · bước 1",
    "Toàn bộ đầu vào:", "31 cặp điểm",
    "Chấm tay trên một cặp ảnh nhiệt–RGB. Chọn góc tấm pin và giao lối đi vì đó là chỗ nhìn "
    "rõ trên cả hai kênh — mặt tấm thì nhiệt gần như phẳng màu, không bám vào đâu được.",
    nhung("hieu_chuan_c1_cap_diem.jpg"),
    "Mỗi số là một cặp: điểm bên trái trên ảnh nhiệt, điểm cùng số bên phải trên ảnh RGB. "
    "Khớp bằng bình phương tối thiểu trên cả 31 điểm — RMSE <b>4,38 px</b>, trung vị 2,95 px, "
    "lớn nhất 9,25 px, quy ra mặt đất 4,35 cm.")

s_c3 = slide(
    "Hiệu chuẩn H · bước 3",
    "Ma trận của hãng lệch", "22 px",
    "Cùng cặp ảnh, cùng cách kiểm tra bằng bàn cờ, chỉ khác ma trận. Ô sáng là ảnh RGB, "
    "ô tối là ảnh nhiệt đã warp.",
    nhung("hieu_chuan_c3_hang_vs_tay.jpg"),
    "<b>Trái:</b> ma trận trong <code>RTK350.txt</code> của DJI, RMSE 22,34 px — nhìn dải lối đi "
    "trắng ở ô RGB rồi bắt sang ô nhiệt kế bên, chúng lệch nhau thấy rõ. <b>Phải:</b> chấm tay, "
    "RMSE 4,38 px. Ma trận hãng là số của <b>dòng máy</b> tại nhà xưởng, không phải của con máy này.")

s_g5 = slide(
    "Ghép ortho · cơ chế",
    "Mỗi ô lưới tự đi", "tìm giá trị của nó",
    "Chiều chạy là NGƯỢC: xuất phát từ ô cần điền rồi đi tìm nguồn, chứ không lấy ảnh rồi "
    "rải lên lưới. Nhờ vậy không bao giờ có lỗ.",
    nhung("h5_chuoi_mot_o.png", thu_muc="hinh_thu_tu"),
    "Bảy bước với số thật cho ô (cột 430, hàng 300). Bước 6 dùng <b>H nghịch</b> — chiều ngược "
    "với lúc chiếu box ở nhánh A. Bước 7 nội suy song tuyến từ 4 pixel lân cận.",
    lop=" b")

s_g4 = slide(
    "Ghép ortho · độ chồng phủ",
    "Mỗi điểm được", "6–8 ảnh nhìn thấy",
    "Phần lõi nhà máy chồng phủ dày, rìa thì thưa hẳn. Đây là gốc của trường n — "
    "thứ mà nhánh quét trên ortho không thể có.",
    nhung("h4_chong_phu.png", thu_muc="hinh_thu_tu"),
    "Cũng là lý do ngưỡng lọc <code>n ≥ 3</code> <b>không mang sang chuyến bay cao hơn được</b>: "
    "bay 85 m thì chồng phủ tụt còn ước ~3 ảnh/điểm, ngưỡng phải hiệu chỉnh lại.",
    lop=" b")

for moc, khoi in [("<!-- ══════════════ 5 · LỌC ẢNH ══════════════ -->", s_c1 + "\n" + s_c3),
                  ("<!-- ══════════════ 7 · MODEL ══════════════ -->", s_g5 + "\n" + s_g4),
                  ("<!-- ══════════════ 9 · GỘP TRÙNG + n ══════════════ -->", s_r1),
                  ("<!-- ══════════════ 10 · NHÁNH B ══════════════ -->", s_r3),
                  ("<!-- ══════════════ 13 · NÉT ≠ TƯƠNG PHẢN ══════════════ -->", s_r2)]:
    if moc not in src:
        raise SystemExit("[DỪNG] không thấy mốc %s — không ghi gì cả." % moc[:40])
    src = src.replace(moc, khoi + "\n" + moc, 1)

n = src.count('<section class="slide">')
src = src.replace("<span><b id=\"cur\">1</b> / 17</span>",
                  "<span><b id=\"cur\">1</b> / %d</span>" % n)

if not os.path.exists(SAO):
    shutil.copy2(args.html, SAO)
    print("[SAO LƯU] %s" % os.path.basename(SAO))
open(args.html, "w", encoding="utf-8").write(src)
print("[VÁ]      %d slide, %.1f MB" % (n, len(src) / 1e6))
