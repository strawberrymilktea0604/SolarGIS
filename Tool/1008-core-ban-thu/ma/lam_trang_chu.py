#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng TRANG CHỦ — cửa vào cho cả dự án.

Gom về một chỗ: hai giao diện gán nhãn (bản chưa chốt để sửa, bản đã chốt để
bàn giao), danh sách ortho .tif đã dựng kèm trạng thái, các trang xem/báo cáo
khác, và mục việc đang làm dở.

Kích cỡ file, số tấm, ngày sửa đều ĐỌC TỪ ĐĨA lúc dựng — không chép tay, chạy
lại là số tự cập nhật. Riêng phần TRẠNG THÁI và lời mô tả là đặt tay ngay dưới
đây, sửa thẳng trong bảng này khi việc tiến triển.

    py -3.13 ma/lam_trang_chu.py     ->  index.html
"""
import datetime
import json
import os
import sys

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
EXP = "du_lieu/Thermal2_31M_full_export"

# ============================================================ BẢNG ĐẶT TAY
# trạng thái: xong | dang | chua | bo

# MỘT file công cụ, hai chế độ. Thẻ thứ hai chỉ khác cái đuôi #chot trên đường
# dẫn — mở thẳng vào bản bàn giao. Trong trang bấm nút ✎/✓ hoặc phím X là qua lại,
# không phải quay ra đây.
GIAO_DIEN = [
    {"file": "cong_cu/gan_nhan_tam.html", "ten": "Gán nhãn tấm pin — chế độ SỬA",
     "anh": "gd_chua_chot.jpg", "tt": "dang", "nhan": "sửa được",
     "mo_ta": "Công cụ soi từng tấm trên ortho màu + ortho nhiệt, model chỉ gợi ý, "
              "người soi chốt lại bằng tay. Sửa nhãn, kéo viền, chốt/bỏ chốt đều ở đây. "
              "Nhãn nằm trong localStorage của trình duyệt — phải mở bằng "
              "<b>file://</b> đúng như lúc gán, mở qua http server là kho khác.",
     "so": "506/6473 tấm đã gán · 496 tấm model đánh dấu đã soi hết"},
    {"file": "cong_cu/gan_nhan_tam.html", "link": "cong_cu/gan_nhan_tam.html#chot",
     "ten": "Cũng trang đó — chế độ ĐÃ CHỐT", "anh": "gd_da_chot.jpg",
     "tt": "xong", "nhan": "chỉ xem",
     "mo_ta": "Cùng một file, cùng kho nhãn, chỉ khác cái nhìn thấy: giấu box gợi ý "
              "của model, giấu tấm tốt / chưa xét / thiếu nhiệt, giấu luôn cột sửa bên "
              "phải. Còn lại đúng tấm đã chốt là có lỗi, tô theo lớp. Mọi thao tác ghi "
              "đều bị chặn nên bấm nhầm không hỏng được gì. Số liệu cập nhật ngay theo "
              "nhãn đang có, không phải chạy lại script nào.",
     "so": "438 tấm lỗi · 306 Single · 101 Multi · 31 Bypass"},
    {"file": "cong_cu/soi_mau_recall.html", "ten": "Soi mẫu đo recall",
     "anh": None, "tt": "chua", "nhan": "để dành",
     "mo_ta": "Cùng công cụ, cùng cách soi, nhưng danh sách khoá cứng vào 400 tấm bốc "
              "ngẫu nhiên (hạt 1008) trong 4916 tấm model KHÔNG đánh dấu, và dùng kho "
              "localStorage riêng nên không lẫn với nhãn chính. Soi xong bấm Tải JSON, "
              "để vào <code>ket_qua/nhan_mau_recall.json</code> rồi chạy "
              "<code>ma/do_recall_mau.py</code> ra recall kèm khoảng tin cậy.",
     "so": "chưa dùng — recall đã đo bằng quét tay toàn bản đồ"},
]

ORTHO = [
    {"anh": "o_mau.jpg", "file": EXP + "/ortho.tif", "ten": "Ortho MÀU (Metashape)", "tt": "xong",
     "sinh": "export tay từ Metashape", "do": "nền chuẩn — mọi thứ khác khớp về đây",
     "mo_ta": "Nền màu của cả dự án. Mã tấm pin, polygon 6473 tấm, toạ độ lỗi đều "
              "tính trên lưới này."},
    {"anh": "o_dsm.jpg", "file": EXP + "/dsm.tif", "ten": "DSM (Metashape)", "tt": "xong",
     "sinh": "export tay từ Metashape", "do": "—",
     "mo_ta": "Mặt cao độ để bắn tia từ ảnh nhiệt xuống mặt đất. Không có nó thì "
              "không quy được pixel ảnh lẻ ra toạ độ."},
    {"anh": "o_metashape.jpg", "file": EXP + "/thermal_ortho.tif", "ten": "Ortho nhiệt (Metashape)", "tt": "bo",
     "sinh": "export tay từ Metashape", "do": "lưới khác hẳn",
     "mo_ta": "KHÔNG dùng: nằm trên lưới toạ độ khác ortho màu (8600×3448, bước "
              "2,405e-07 độ), chồng lên là phải nắn lại. Giữ để đối chứng."},
    {"anh": "o_tu_lam.jpg", "file": "ket_qua/ortho/ortho_nhiet_tu_lam.tif", "ten": "Ortho nhiệt tự ghép", "tt": "xong",
     "sinh": "ma/ghep_ortho_nhiet.py", "do": "lệch trung vị 7,92 cm · RMSE 8,30 cm",
     "mo_ta": "Bản gốc: đưa từng ảnh nhiệt qua H sang khung RGB rồi dán lên lưới "
              "gấp 3 lần ortho màu. Đầu vào cho hai bản nắn bên dưới."},
    {"anh": "o_nan.jpg", "file": "ket_qua/ortho/ortho_nhiet_nan.tif", "ten": "Ortho nhiệt nắn theo RGB", "tt": "xong",
     "sinh": "ma/nan_ortho_theo_rgb.py", "do": "bản trung gian",
     "mo_ta": "Nắn TOÀN CỤC một phép cho cả tấm ortho. Đỡ hơn bản gốc nhưng không "
              "chữa được lệch riêng của từng ảnh — nên mới có bản bù dưới đây."},
    {"anh": "o_dan_xuoi.jpg", "file": "ket_qua/ortho/ortho_nhiet_dan_xuoi.tif", "ten": "Ortho nhiệt dán xuôi", "tt": "bo",
     "sinh": "ma/ghep_ortho_dan_xuoi.py", "do": "đối chứng",
     "mo_ta": "Dán thẳng không nắn, làm ra để so cho thấy khác biệt. Đừng lấy ảnh "
              "minh hoạ <code>so_dan_xuoi.jpg</code> làm bằng chứng — script vẽ nó "
              "tra DSM sai chỉ số (cột nhận giá trị hàng)."},
    {"anh": "o_bu_rgb.jpg", "file": "ket_qua/ortho/ortho_nhiet_bu_rgb.tif", "ten": "Ortho nhiệt bù theo RGB", "tt": "xong",
     "sinh": "bu_theo_rgb.py → ghep_ortho_nhiet.py --bu-rgb", "do":
     "lệch trung vị <b>1,50 cm</b> · RMSE 2,79 cm",
     "dang_dung": True,
     "mo_ta": "BẢN ĐANG DÙNG. Cân sáng rồi bù lệch RIÊNG cho từng ảnh trước khi dán. "
              "Đây là lớp nhiệt trong cả hai giao diện gán nhãn."},
]

# Chỉ để hai trang này. Mấy mục cũ (soi tay 100 lỗi, căn tay, vì sao lệch khung,
# tài liệu pipeline, hai slide, bốn file .md) vẫn còn nguyên trên đĩa và ảnh minh
# hoạ vẫn nằm sẵn trong trang/ — muốn hiện lại chỉ việc chép dòng vào đây:
#   ("cong_cu/soi_tay_100_loi.html", "Soi tay 100 lỗi", "...", "t_soi_tay.jpg"),
#   ("cong_cu/can_tay.html", "Căn tay nhiệt ↔ màu", "...", "t_can_tay.jpg"),
#   ("tai_lieu/giai_thich_lech_khung.html", "Vì sao lệch khung", "...", "t_lech_khung.jpg"),
#   ("tai_lieu/TAI_LIEU_PIPELINE.html", "Tài liệu pipeline", "...", "t_tai_lieu.jpg"),
#   ("tai_lieu/slide_pipeline.html", "Slide pipeline", "...", "t_slide_pipeline.jpg"),
#   ("tai_lieu/slide_quy_trinh.html", "Slide quy trình", "...", "t_slide_quy_trinh.jpg"),
#   ("tai_lieu/BAO_CAO_DANH_GIA.md", "Báo cáo đánh giá", "...", None),
#   ("tai_lieu/TOM_TAT_KET_QUA.md", "Tóm tắt kết quả", "...", None),
#   ("tai_lieu/_ban_do_pipeline.md", "Bản đồ pipeline", "...", None),
#   ("tai_lieu/THUAT_NGU.md", "Thuật ngữ (bản .md)", "...", None),
TRANG = [
    ("tai_lieu/DANH_GIA_THEO_NHAN.html", "Quy trình đánh giá model",
     "Notebook đã chạy: từ nhãn tay ra precision/recall/F1, ma trận nhầm lớp, "
     "đánh đổi theo ngưỡng conf. Mọi số tính lại từ dữ liệu thô.", None),
    ("cong_cu/so_sanh_model.html", "So sánh model",
     "Đối chiếu đầu ra hai model trên cùng ảnh.", "t_so_sanh_model.jpg"),
    ("tai_lieu/slide_thuat_ngu.html", "Thuật ngữ",
     "Giải nghĩa từ chuyên môn dùng trong dự án.", None),
]

DANG_LAM = [
    ("xong", "Đánh giá model bằng nhãn tay",
     "Precision <b>0,865</b> · Recall <b>0,968</b> · F1 <b>0,914</b> · đúng lớp "
     "<b>0,972</b>. Mốc là 511 tấm người soi chốt tay, đơn vị chấm là tấm pin. "
     "Recall đo bằng quét tay toàn bản đồ nên là số đếm hết, không phải ước lượng. "
     "Bảng đầy đủ trong <code>tai_lieu/DANH_GIA_THEO_NHAN.ipynb</code>, chạy lại "
     "bằng <code>ma/danh_gia_model_theo_nhan.py</code>."),
    ("dang", "Ba nhà máy mới của Khánh",
     "BIM 2 · Thuận Nam 19 · Thuận Nam Đức Long — dữ liệu còn đang tải trong "
     "<code>Data_Khánh_làm/</code>, chưa chạy pipeline lần nào."),
    ("chua", "Nhiệt độ thật từ ảnh 16-bit",
     "Ảnh nhiệt có dữ liệu 16-bit nằm trong khối APP3 mà pipeline đang bỏ phí — "
     "chỉ đọc ảnh 8-bit đã tô màu. Mở ra thì tính được ΔT thật của từng vệt nóng, "
     "lọc lỗi theo chênh nhiệt chứ không chỉ theo hình dạng."),
    ("chua", "Hai bản ghép còn dang dở",
     "<code>ghep_ortho_pha_tron.py</code> và <code>ghep_ortho_off_nadir.py</code> "
     "có script nhưng chưa dựng ra file .tif nào."),
]

# ============================================================ ĐỌC ĐĨA
def kich(p):
    if not os.path.exists(p):
        return None, None
    n = os.path.getsize(p)
    t = datetime.datetime.fromtimestamp(os.path.getmtime(p))
    return (("%.1f GB" % (n / 1e9)) if n > 1e9 else
            ("%.1f MB" % (n / 1e6)) if n > 1e6 else
            ("%.0f KB" % (n / 1e3))), t.strftime("%d/%m/%Y")


CO = {}
try:
    import rasterio
    for o in ORTHO:
        if os.path.exists(o["file"]):
            with rasterio.open(o["file"]) as r:
                CO[o["file"]] = "%d × %d" % (r.width, r.height)
except ImportError:
    print("(không có rasterio — bỏ qua cột kích thước ảnh)")

for m in GIAO_DIEN + ORTHO:
    m["co"], m["ngay"] = kich(m["file"])
    m["px"] = CO.get(m["file"])
    m["co_tren_dia"] = m["co"] is not None

TRANG_CO = [(f, t, m, a, *kich(f)) for f, t, m, a in TRANG if os.path.exists(f)]
thieu = [f for f, _, _, _ in TRANG if not os.path.exists(f)]
if thieu:
    print("(bỏ qua %d trang không có trên đĩa: %s)" % (len(thieu), ", ".join(thieu)))

ANH = "trang"
thieu_anh = [m.get("anh") for m in GIAO_DIEN + ORTHO
             if m.get("anh") and not os.path.exists(os.path.join(ANH, m["anh"]))]
if thieu_anh:
    print("(thiếu %d ảnh minh hoạ, ô hình để trống: %s)"
          % (len(thieu_anh), ", ".join(thieu_anh)))
    print(" chạy `py -3.13 ma/lam_anh_trang_chu.py` để dựng")

# ============================================================ DỰNG HTML
NHAN_TT = {"xong": ("XONG", "#3f9e6a"), "dang": ("ĐANG LÀM", "#c98a2e"),
           "chua": ("CHƯA LÀM", "#6f7883"), "bo": ("KHÔNG DÙNG", "#8a5a5a")}


def the_tt(tt):
    ten, mau = NHAN_TT[tt]
    return '<span class="tt" style="background:%s22;color:%s;border-color:%s55">%s</span>' % (
        mau, mau, mau, ten)


def hinh(ten, chu=""):
    """Ô hình của một thẻ. Không có ảnh thì trả về ô chữ, đừng để thẻ hụt cao."""
    if ten and os.path.exists(os.path.join(ANH, ten)):
        return '<img class="hinh" src="%s/%s" alt="" loading="lazy">' % (ANH, ten)
    return '<div class="hinh trong">%s</div>' % chu


h = []
h.append("""<!doctype html><html lang="vi"><meta charset="utf-8">
<title>1008 · Định vị lỗi tấm pin từ ảnh nhiệt</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0e1013;color:#e6e8ea;font:14px/1.6 "Segoe UI",system-ui,sans-serif;
     padding:0 0 60px}
.bao{max-width:1080px;margin:0 auto;padding:0 24px}
header{border-bottom:1px solid #262a31;background:#131519;padding:26px 0 22px;margin-bottom:28px}
h1{font-size:22px;font-weight:600;letter-spacing:.2px}
h1 span{color:#6f7883;font-weight:400}
.duoi{color:#9aa3ad;margin-top:5px}
h2{font-size:13px;font-weight:600;letter-spacing:1.4px;color:#7e8791;
   margin:34px 0 12px;text-transform:uppercase}
a{color:inherit;text-decoration:none}
.the{display:block;background:#171a1f;border:1px solid #262a31;border-radius:10px;
     padding:15px 17px;margin-bottom:11px;transition:.12s}
a.the:hover{background:#1c2027;border-color:#3a4250}
.dong{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ten{font-size:16px;font-weight:600}
.tt{font-size:10.5px;font-weight:700;letter-spacing:.7px;padding:2px 7px;
    border-radius:4px;border:1px solid}
.nhan{font-size:11.5px;color:#8b939d;border:1px solid #2e343d;border-radius:4px;padding:1px 6px}
.mt{color:#a8b0b9;margin-top:7px}
.so{color:#7fb0e8;font-family:Consolas,monospace;font-size:12.5px;margin-top:6px}
.meo{color:#6f7883;font-size:12px;margin-top:6px;font-family:Consolas,monospace}
code{background:#22262d;padding:1px 5px;border-radius:4px;font-size:12.5px;color:#cfd5db}
.luoi{display:grid;gap:12px}
.luoi .the{margin:0}
.luoi .ten{font-size:14.5px}
.luoi .mt{font-size:12.5px;margin-top:4px}
.hai{grid-template-columns:repeat(auto-fit,minmax(400px,1fr))}
.ba{grid-template-columns:repeat(auto-fill,minmax(310px,1fr))}
.bon{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.hinh{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:7px;
      background:#0b0d10;margin:-3px 0 11px;border:1px solid #23272e}
.hinh.trong{display:flex;align-items:center;justify-content:center;color:#4a525c;
      font:600 12px/1 Consolas,monospace;letter-spacing:2px;
      background:repeating-linear-gradient(135deg,#15181d,#15181d 9px,#191d23 9px,#191d23 18px)}
.dungngay{border-color:#2f6fd0;box-shadow:0 0 0 1px #2f6fd044}
.tay{color:#6f7883;font-size:12px}
footer{color:#5f6874;font-size:12px;margin-top:38px;border-top:1px solid #1e2229;padding-top:14px}
</style>
<header><div class="bao">
  <h1>Định vị lỗi tấm pin từ ảnh nhiệt drone <span>· 1008-stage1-rgb-thermal</span></h1>
  <div class="duoi">Nhà máy Thermal2_31M · 598 ảnh nhiệt + RGB · 6473 tấm pin ·
      ortho nhiệt khớp ortho màu ở mức 1,50 cm</div>
</div></header>
<div class="bao">""")

# ---- giao diện: hai thẻ to nằm cạnh nhau, ảnh cắt cùng một khoảnh nhà máy nên
#      nhìn cạnh nhau là thấy ngay bản nào còn box model, bản nào đã sạch
h.append("<h2>Giao diện làm việc</h2><div class='luoi hai'>")
for m in GIAO_DIEN:
    if not m["co_tren_dia"]:
        continue
    h.append('<a class="the" href="%s">' % m.get("link", m["file"]))
    h.append(hinh(m.get("anh"), "CHƯA CÓ ẢNH"))
    h.append('<div class="dong"><span class="ten">%s</span>%s</div>'
             % (m["ten"], the_tt(m["tt"]) + '<span class="nhan">%s</span>' % m["nhan"]))
    h.append('<div class="mt">%s</div>' % m["mo_ta"])
    h.append('<div class="so">%s</div>' % m["so"])
    h.append('<div class="meo">%s · %s · sửa %s</div></a>' % (m["file"], m["co"], m["ngay"]))
h.append("</div>")

# ---- ortho
h.append("<h2>Ortho &amp; dữ liệu nền</h2><div class='luoi ba'>")
for m in ORTHO:
    if not m["co_tren_dia"]:
        continue
    h.append('<div class="the%s">' % (" dungngay" if m.get("dang_dung") else ""))
    h.append(hinh(m.get("anh"), ".TIF"))
    h.append('<div class="dong"><span class="ten">%s</span>%s%s</div>'
             % (m["ten"], the_tt(m["tt"]),
                '<span class="nhan">đang dùng</span>' if m.get("dang_dung") else ""))
    h.append('<div class="mt">%s</div>' % m["mo_ta"])
    h.append('<div class="so">%s</div>' % m["do"])
    h.append('<div class="meo">%s<br>%s · %s · sinh bởi %s</div></div>'
             % (m["file"], m["px"] or "—", m["co"], m["sinh"]))
h.append("</div>")

# ---- trang khác
h.append("<h2>Trang xem &amp; báo cáo</h2><div class='luoi hai'>")
for f, t, mt, a, co, ngay in TRANG_CO:
    h.append('<a class="the" href="%s">%s<div class="ten">%s</div>'
             '<div class="mt">%s</div><div class="meo">%s · %s</div></a>'
             % (f, hinh(a, f.rsplit(".", 1)[-1].upper()), t, mt, co, ngay))
h.append("</div>")

# ---- đang làm
h.append("<h2>Đang làm &amp; còn thiếu</h2>")
for tt, ten, mt in DANG_LAM:
    h.append('<div class="the"><div class="dong"><span class="ten">%s</span>%s</div>'
             '<div class="mt">%s</div></div>' % (ten, the_tt(tt), mt))

h.append('<footer>Trang này dựng bằng <code>lam_trang_chu.py</code> — số liệu đọc từ '
         'đĩa lúc dựng, phần trạng thái sửa tay ngay trong script. Dựng lúc %s.</footer>'
         "</div></html>" % datetime.datetime.now().strftime("%H:%M %d/%m/%Y"))

open("index.html", "w", encoding="utf-8").write("\n".join(h))
print("-> index.html  (%d giao diện, %d ortho, %d trang, %d việc đang làm)"
      % (sum(1 for m in GIAO_DIEN if m["co_tren_dia"]),
         sum(1 for m in ORTHO if m["co_tren_dia"]), len(TRANG_CO), len(DANG_LAM)))
