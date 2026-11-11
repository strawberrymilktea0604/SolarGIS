#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng TAI_LIEU_PIPELINE.html — tài liệu đọc để hiểu pipeline.

Ba nguồn ghép lại:
  _ban_do_pipeline.md   bản đồ giai đoạn ↔ file, do 13 agent đọc code rồi kiểm chéo
  _hinh_ve.py           9 hình vẽ SVG cho các định nghĩa
  _anh_pipeline.json    18 ảnh thật của dự án, base64

CSS đọc thẳng từ _slide_mau.html nên tài liệu này và hai deck kia cùng một bộ thiết kế.

    python ma/lam_tai_lieu_pipeline.py
"""
import json
import os
import re

import _hinh_ve

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
RA = "tai_lieu/TAI_LIEU_PIPELINE.html"

# Lấy CSS từ deck nào còn trên đĩa — _slide_mau.html có thể đã bị dọn.
# Ba deck dùng chung một bộ nên lấy cái nào cũng như nhau.
for _m in ("tai_lieu/_slide_mau.html", "tai_lieu/slide_thuat_ngu.html", "tai_lieu/slide_pipeline.html"):
    if os.path.exists(_m):
        MAU = _m
        break
else:
    raise SystemExit("Không tìm thấy deck nào để lấy CSS")
goc = open(MAU, encoding="utf-8").read()
CSS = goc[goc.index("<style>"):goc.index("</style>") + 8]
print("CSS lấy từ", MAU)
ANH = json.load(open("tai_lieu/_anh_pipeline.json", encoding="utf-8"))
H = _hinh_ve.HINH

THEM = """
<style>
  body{font-size:16.5px}
  .deck{scroll-snap-type:none}
  .doc{max-width:1080px;margin:0 auto;padding:clamp(24px,4vw,60px) clamp(18px,4vw,40px) 120px}
  .doc h2{margin-top:56px;padding-top:20px;border-top:1px solid var(--line)}
  .doc h2:first-of-type{border-top:0;margin-top:24px}
  .doc h3{margin-top:30px}
  .doc p,.doc li{color:var(--text-2)}
  .doc strong{color:var(--text)}
  figure svg{width:100%;height:auto;display:block;background:var(--surface);
    border:1px solid var(--img-ring);border-radius:10px;padding:6px}
  figure{margin:22px 0}
  .toc{position:sticky;top:0;z-index:30;background:var(--ground);
    border-bottom:1px solid var(--line);padding:10px clamp(18px,4vw,40px);
    display:flex;flex-wrap:wrap;gap:6px 16px;font-family:var(--font-mono);font-size:11.5px}
  .toc a{color:var(--text-3);text-decoration:none;white-space:nowrap}
  .toc a:hover{color:var(--ember)}
  .gd{display:flex;align-items:baseline;gap:12px;margin:34px 0 10px}
  .gd .n{font-family:var(--font-display);font-size:30px;font-weight:600;color:var(--ember);
    line-height:1;min-width:44px}
  .gd .t{font-family:var(--font-display);font-size:22px;font-weight:600;color:var(--text)}
  .io{display:grid;grid-template-columns:78px 1fr;gap:6px 14px;margin:12px 0;
    font-size:14.5px;align-items:start}
  .io .k{font-family:var(--font-mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--text-3);padding-top:3px}
  .io .v{color:var(--text-2)}
  .cmd{font-family:var(--font-mono);font-size:13px;background:var(--surface-2);
    border:1px solid var(--line);border-radius:8px;padding:10px 13px;overflow-x:auto;
    color:var(--text-2);margin:8px 0}
  .cmd b{color:var(--ember);font-weight:600}
  @media print{ .toc{display:none} .doc h2{page-break-after:avoid} figure{page-break-inside:avoid} }
</style>
"""


def hinh(key, cap=""):
    return f'<figure>{H[key]}{f"<figcaption>{cap}</figcaption>" if cap else ""}</figure>'


def anh(key, cap=None):
    if key not in ANH:
        return ""
    a = ANH[key]
    c = cap or a["cap"]
    return (f'<figure><img src="{a["src"]}" alt="{c}">'
            f'<figcaption>{c} · <span class="mono">{a["goc"]}</span></figcaption></figure>')


def gd(n, t):
    return f'<div class="gd"><span class="n">{n}</span><span class="t">{t}</span></div>'


def io(an, de, lenh=None):
    r = '<div class="io">'
    r += f'<span class="k">ăn</span><span class="v">{an}</span>'
    r += f'<span class="k">đẻ</span><span class="v">{de}</span></div>'
    if lenh:
        r += f'<div class="cmd">{lenh}</div>'
    return r


S = []

# ══════════════════════════════════════════════════════════════════ mở đầu
S.append(f"""
<h1>Pipeline định vị lỗi tấm pin<br>— đọc để hiểu toàn bộ</h1>
<p class="sub">Tài liệu này trả lời đúng hai câu: <strong>chuỗi xử lý gồm những bước nào</strong>,
và <strong>file nào ứng với bước nào</strong>. Mọi quan hệ vào/ra dưới đây được dựng bằng cách
đọc code 18 script rồi grep lại để kiểm chứng từng khai báo — không suy từ tài liệu cũ.</p>

<div class="grid g3" style="margin:28px 0">
  <div class="stat"><span class="k">Script đã lập bản đồ</span><span class="n">18</span>
    <span class="d">mỗi khai báo vào/ra đều có số dòng chứng minh</span></div>
  <div class="stat"><span class="k">Đường tới hạn</span><span class="n good">4 lệnh</span>
    <span class="d">từ ảnh thô tới ortho nhiệt</span></div>
  <div class="stat"><span class="k">Mắt xích đứt</span><span class="n good">0</span>
    <span class="d">bước ⑦ đã tìm lại được code (12/08)</span></div>
</div>

<div class="note"><strong>Ba khối tách biệt, chỉ gặp nhau ở cuối.</strong>
<strong>Khối A — định vị</strong>: ảnh nhiệt + RGB → H → ortho nhiệt → toạ độ GPS → mã tấm pin.
<strong>Khối B — đánh giá model</strong>: độc lập hoàn toàn, chỉ đụng ổ <code>D:</code>.
<strong>Khối C — viewer &amp; báo cáo</strong>: tiêu thụ sản phẩm của A và B.
Trộn A với B vào nhau là nguồn gốc gần như mọi hiểu nhầm về kết quả.</div>

{hinh("luong_pipeline", "Luồng dữ liệu. Hộp xanh thép = thứ phải có sẵn; hộp cam = script chạy được; viên thuốc = file dữ liệu.")}
""")

# ══════════════════════════════════════════════════════════════════ GĐ 0
S.append(f"""
<h2 id="gd0">GĐ 0 · Thứ phải có sẵn trước khi chạy bất cứ script nào</h2>
<p>Những thứ pipeline cần nhưng không script nào trong khối A–D sinh ra. Mất một cái là pipeline đứng.
Riêng <code>manifest_anh.csv</code> nay đã dựng lại được bằng <code>tao_manifest.py</code> — xem cột cuối.</p>

<div class="tbl-wrap"><table>
<tr><th>Thứ cần có</th><th>Từ đâu</th><th>Đóng vai trò gì</th><th>Rủi ro nếu mất</th></tr>
<tr><td><code>Thermal2_31M_full_export/</code><br>cameras.xml · ortho.tif · dsm.tif · thermal_ortho.tif</td>
    <td>Export tay từ Metashape</td>
    <td><strong>Bộ khung toạ độ.</strong> <code>cameras.xml</code> cho nội tham số + tư thế từng ảnh
    để chiếu pixel ra tia; <code>dsm.tif</code> là bề mặt để cắt tia đó lấy điểm đáp
    (ray–DSM intersection); <code>ortho.tif</code> là nền đối chiếu, GSD 0,957 cm/px;
    <code>thermal_ortho.tif</code> là ortho nhiệt để so với bản tự ghép</td>
    <td>Dựng lại project Metashape, export lại đủ 4 file</td></tr>
<tr><td><code>manifest_anh.csv</code> — 598 cặp ảnh</td>
    <td><code>tao_manifest.py</code><br><em>(dựng lại được)</em></td>
    <td><strong>Khoá nối RGB↔nhiệt.</strong> Ghép cặp theo <code>seq</code> — 4 chữ số trong tên DJI —
    vì <strong>596/598</strong> cặp có timestamp trong tên <code>_W</code> và <code>_T</code> lệch nhau 1–2 giây,
    và <strong>79/598</strong> cặp có hai ảnh nằm ở hai thư mục giải nén khác nhau. Đồng thời lọc theo
    <code>&lt;transform&gt;</code> trong <code>cameras.xml</code>: chỉ giữ ảnh Metashape align được.
    8 script đọc nó làm điểm vào</td>
    <td><strong>Chứa đường dẫn TUYỆT ĐỐI</strong> — đổi máy hoặc ổ đĩa là 5 script vỡ.
    Cách chữa: chạy lại <code>tao_manifest.py</code>, đừng sửa tay CSV</td></tr>
<tr><td><code>tam_pin_polygon.json</code> — 6300 polygon tấm pin</td>
    <td><code>bo_dung_goc/tao_tam_pin_polygon.py</code><br><em>(chạy <code>best.pt</code> quét chính ortho màu)</em></td>
    <td><strong>Bảng tra mã tấm.</strong> Lỗi sau khi chiếu lên ortho chỉ là một toạ độ;
    phải đối polygon mới biết lỗi nằm ở tấm nào để báo cho người đi sửa</td>
    <td>Mất là không gán được mã tấm. Dựng lại được — <code>best.pt</code> chạy CPU
    <strong>tất định</strong> (đã thử hai lần, lệch 0,00 px). Nhưng script đọc
    <code>loi_obb4.json</code> để khoanh vùng quét, mà file đó <strong>không còn trên đĩa</strong>
    — phải sửa phần khoanh vùng trước khi chạy</td></tr>
<tr><td><code>best.pt</code> · <code>RTK350.txt</code></td><td>Repo <code>solarfarm_inspection</code> của thầy</td>
    <td><code>best.pt</code> — YOLO-OBB detect <em>tấm pin</em> trên ảnh RGB, dùng làm thước
    đo độ lệch để lọc ảnh rung/trễ (không phải model detect lỗi).
    <code>RTK350.txt</code> — ma trận H khởi tạo, làm mốc dẫn đường khi chấm tay hiệu chuẩn</td>
    <td>Mất <code>best.pt</code> thì bộ lọc ảnh lệch không chạy được</td></tr>
<tr><td>Ảnh gốc <code>_T.JPG</code> / <code>_W.JPG</code></td><td>Dữ liệu bay</td>
    <td><strong>Nguyên liệu thô.</strong> <code>_T</code> để detect lỗi và đọc nhiệt 16-bit
    trong APP3; <code>_W</code> để detect tấm pin và làm bên đích của phép ánh xạ H</td>
    <td>—</td></tr>
</table></div>
""")

# ══════════════════════════════════════════════════════════════════ GĐ 1
S.append(f"""
<h2 id="gd1">Khối A · Chuỗi định vị</h2>

{gd("①", "calib_thermal_rgb.py — hiệu chuẩn H nhiệt→RGB")}
<p><strong>Chấm tay, có người ngồi click.</strong> Chạy <em>một lần cho mỗi model drone</em>, không phải
mỗi trang trại. Click lên ảnh nhiệt, khung RGB tự nhảy tới vùng tương ứng kèm dấu + vàng là vị trí
ma trận khởi tạo dự đoán; bạn click vào điểm thật. Khoảng lệch giữa dấu + và chỗ bạn click chính
là sai số của ma trận cũ.</p>

{io("ảnh <code>_T.JPG</code> + <code>_W.JPG</code> · <code>cameras.xml</code> (để khử méo RGB) · <code>RTK350.txt</code> (H khởi tạo của hãng)",
    "<strong><code>thermal_to_rgb.json</code></strong> — H đang dùng cho toàn bộ pipeline phía sau",
    "python ma/calib_thermal_rgb.py --thermal <b>..._0280_T.JPG</b> --rgb <b>..._0280_W.JPG</b> \\<br>"
    "&nbsp;&nbsp;&nbsp;&nbsp;--xml Thermal2_31M_full_export/cameras.xml --alt 31<br>"
    "<span style='color:var(--text-3)'># chấm ~12 cặp rải 4 góc · bấm H để tính · bấm S để lưu · Q/ESC = mất hết</span>")}

{anh("hieu_chuan")}

<div class="note warn"><strong>Bẫy ghi đè — đã kiểm trên đĩa.</strong>
<code>thermal_to_rgb.json</code> hiện có <strong>20 khoá</strong>, nhưng script này chỉ ghi 13.
Bảy khoá còn lại (<code>rmse_cm</code>, <code>baseline_RTK350_rmse_px</code>,
<code>baseline_RTK350_rmse_cm</code>, <code>H_percent</code>, <code>fit_method</code>,
<code>median_err_px</code>, <code>hieu_chinh_bo_sung</code>) do ai đó thêm tay hoặc bằng script đã xoá.
Mà <code>danh_gia_chi_so.py</code> <strong>đang đọc 3 khoá trong số đó</strong>.
Chạy lại bước ① với <code>--out thermal_to_rgb.json</code> sẽ xoá sạch chúng và làm hỏng bảng chỉ số.
<strong>Muốn chấm lại thì ghi ra tên file khác rồi trộn tay.</strong></div>

<h3>Vì sao một ma trận 3×3 lại đủ cho cả ảnh</h3>
<p>Với hai camera nhìn cùng một <strong>mặt phẳng</strong>, ánh xạ giữa hai ảnh là một homography —
đúng tuyệt đối, không phải xấp xỉ. Sai số chỉ đến từ phần cảnh nhô khỏi mặt phẳng đó.</p>
{hinh("thi_sai", "Hai ống kính cách nhau ~3 cm ở độ cao 31 m: thị sai còn lại ~1 mm, nhỏ hơn một pixel ảnh nhiệt 30 lần.")}
<p>Cùng phép tính đó giải thích vì sao <strong>H gắn với thiết bị chứ không gắn với trang trại</strong>:
đổi độ cao bay từ 31 m lên 60 m chỉ làm H đổi ~0,5 px.</p>

<div class="note">Kết quả đang dùng: <strong>31 cặp điểm · RMSE 4,38 px · max 9,25 px</strong>.
H của hãng (<code>RTK350.txt</code>) cho RMSE 22,34 px — chấm tay tốt hơn <strong>5,1 lần</strong>.</div>
""")

# ══════════════════════════════════════════════════════════════════ GĐ 2-3
S.append(f"""
{gd("②③", "loc_anh_tre.py và loc_anh_rung.py — hai bộ lọc ảnh")}
<p>Ảnh RGB và ảnh nhiệt của <em>cùng một lần bấm máy</em> không nổ cùng lúc. Drone bay đều thì
khoảng trễ ấy chỉ dịch cảnh một đoạn nhỏ mà H bù được; drone đang phanh gấp hoặc bị gió giật thì
cảnh trong hai ảnh lệch một lượng không tả nổi bằng H.</p>

{hinh("tre_chup", "5 m/s × 30 ms = 15 cm — khớp gần khít trung vị đo được 14,1 cm. Lớn gấp 150 lần thị sai.")}

{gd("②", "loc_anh_tre.py — đo lệch trực tiếp trên từng ảnh")}
<p>Chạy detector tấm pin trên <strong>ảnh RGB</strong> (conf ~0,93 — trên ảnh nhiệt nó hỏng, chỉ
~0,33 nên tuyệt đối không chạy bên nhiệt), chiếu viền tấm sang toạ độ ảnh nhiệt qua H, rồi trượt
quanh vị trí gốc tìm chỗ khớp nhất. Lệch tìm được chính là lệch cần đo.</p>
{io("<code>thermal_to_rgb.json</code> · <code>manifest_anh.csv</code> · <code>best.pt</code> · ảnh <code>_W</code>+<code>_T</code>",
    "<strong><code>anh_tre_chup_full.json</code></strong> — <code>anh_nen_loai</code> (ảnh cần bỏ) và <code>chi_tiet[]</code> (dx, dy, do_net từng ảnh)",
    "python ma/loc_anh_tre.py <b>--out anh_tre_chup_full.json</b>"
    "&nbsp;&nbsp;<span style='color:var(--text-3)'># ~44 phút cho 598 ảnh</span>")}

<div class="note warn"><strong>Bẫy tên file.</strong> Mặc định <code>--out</code> là
<code>anh_tre_chup.json</code> (bản mẫu 60 ảnh), nhưng bước ④ và bước ⑫ đều mặc định đọc
<code>anh_tre_chup_full.json</code>. Chạy toàn bộ mà quên truyền <code>--out</code> thì hai bước sau
đọc hụt và <strong>không báo lỗi</strong>.</div>

{anh("anh_tre")}

{gd("③", "loc_anh_rung.py — đọc XMP, không mở ảnh ra tính")}
<p>Ảnh DJI ZH20T ghi sẵn tốc độ bay và tư thế thân máy tại đúng lúc bấm, <em>riêng cho từng cảm biến</em>.
Nên mỗi lần bấm có hai bản ghi ở hai thời điểm hơi khác nhau — so ra là biết lúc đó máy có bay đều không.
Chỉ đọc 600 KB đầu mỗi JPEG.</p>
{io("<code>manifest_anh.csv</code> · ảnh gốc · <code>exif_bay.json</code> (cache)",
    "<strong><code>anh_rung.json</code></strong> · <code>exif_bay.json</code>",
    "python ma/loc_anh_rung.py&nbsp;&nbsp;<span style='color:var(--text-3)'># ~1 phút</span>")}
<p>Chỉ <strong>2 trong 4 dấu hiệu đang bật</strong>. Hai cái còn lại (gia tốc, thân máy lắc) đã tắt vì
đo trên đủ 598 ảnh thì chúng loại nhầm nhiều ảnh tốt mà không cải thiện gì ở biên.</p>

<div class="note"><strong>Bài học đắt:</strong> trên mẫu 60 ảnh, dấu hiệu lệch tốc độ trông rất tốt —
nhóm vượt ngưỡng lệch gấp 1,7 lần. Quét đủ 598 ảnh thì tỉ số <strong>đảo về 0,89</strong>.
Nhóm vượt ngưỡng trong mẫu chỉ có 7 ảnh. Đừng chốt ngưỡng trên mẫu.</div>
""")

# ══════════════════════════════════════════════════════════════════ GĐ 4
S.append(f"""
{gd("④", "ghep_ortho_nhiet.py — dựng ortho nhiệt toàn nhà máy")}
<p>Đây là điểm hợp lưu: ①②③ đều đổ vào đây. Nguyên lý là <strong>chiếu ngược</strong> — duyệt từng
pixel của lưới ortho rồi hỏi ngược xem lấy giá trị ở đâu:</p>

{hinh("ghep_chieu_nguoc", "Không dán ảnh nhiệt lên ortho. Ngược lại: mỗi ô của lưới ortho tự đi tìm giá trị của mình.")}

<div class="note"><strong>Đầu ra là MỘT ảnh toàn cảnh, không phải 598 ảnh ghép lẻ.</strong>
Ghép từng cặp nhiệt–RGB lẻ thì được 598 ảnh rời, vẫn không biết lỗi nằm ở đâu trên thực địa.
Còn ortho là một tấm bản đồ liền có toạ độ địa lý thật, nên mới gán được mã tấm pin và
chỉ đường cho người đi sửa.</div>
<div class="chain">
  <div class="step"><span class="i">01</span><span class="h">pixel ortho</span><span class="b">lon/lat</span></div>
  <div class="step"><span class="i">02</span><span class="h">cao độ</span><span class="b">tra DSM</span></div>
  <div class="step"><span class="i">03</span><span class="h">điểm 3D</span><span class="b">ECEF</span></div>
  <div class="step"><span class="i">04</span><span class="h">chiếu vào ảnh RGB</span><span class="b">tư thế camera</span></div>
  <div class="step"><span class="i">05</span><span class="h">qua H⁻¹</span><span class="b">pixel ảnh nhiệt</span></div>
  <div class="step"><span class="i">06</span><span class="h">lấy giá trị</span><span class="b">nội suy song tuyến</span></div>
</div>

{io("<code>cameras.xml</code> · <code>ortho.tif</code> (lấy lưới) · <code>dsm.tif</code> · <code>thermal_to_rgb.json</code> · <code>manifest_anh.csv</code> · ảnh <code>_T</code> · <strong><code>anh_tre_chup_full.json</code></strong> · <strong><code>anh_rung.json</code></strong>",
    "<strong><code>ortho_nhiet_tu_lam.tif</code></strong> — 8451 × 4997 px, GSD 2,87 cm/px, 1 băng uint8",
    "python ma/ghep_ortho_nhiet.py&nbsp;&nbsp;<span style='color:var(--text-3)'># ~3 phút · nhanh gấp 4: --step 6</span>")}

{hinh("chon_anh", "Mỗi pixel chỉ tính với MỘT ảnh — ảnh có tâm chụp gần nhất, tìm bằng cây KD.")}

<p>Ba thứ khiến nó chạy vài phút thay vì vài giờ: đặt độ phân giải theo <em>ảnh nhiệt</em> chứ không
phóng to vô ích lên 0,96 cm/px của ortho màu; mỗi pixel chỉ tính với một ảnh; và loại sẵn ảnh xấu.</p>

<h3>Hai cải thiện mặc định bật</h3>
<div class="grid g2">
  <div class="card"><h3>Cân bằng độ sáng</h3>
    <p style="font-size:14.5px">Ảnh nhiệt đọc vào bằng <code>IMREAD_GRAYSCALE</code> là <strong>ảnh
    hiển thị</strong> DJI đã tự chỉnh gain riêng từng ảnh — trung vị của 396 ảnh trải 68..155.
    Kéo về cùng thang không mất thông tin vật lý nào. Độ tản mát giảm <strong>30 %</strong>.</p></div>
  <div class="card hot"><h3>Bù lệch riêng từng ảnh</h3>
    <p style="font-size:14.5px">Dùng <code>dx</code>,<code>dy</code> mà bước ② đã đo sẵn. Sai số đặt chỗ
    giảm <strong>14,1 → 4,3 cm</strong>, 238 cửa sổ tốt lên / 37 xấu đi.</p></div>
</div>
<div class="note warn">Bù bằng <strong>một hằng số</strong> thì hỏng — đã thử, hướng lệch đảo dấu.
Vì lệch đổi hướng tuỳ ảnh (15 vùng lệch lên / 16 lệch xuống) nên phải bù <em>riêng từng ảnh</em>.</div>

{anh("so_3_ban", "Metashape (trái) · tự ghép chưa bù (giữa) · tự ghép đã bù lệch từng ảnh (phải)")}

<div class="note warn"><strong>Còn một đường tốt hơn hẳn mà ortho hiện chưa dùng.</strong>
Ảnh <code>_T.JPG</code> của ZH20T <em>không chỉ</em> là ảnh xem 8-bit: mảng nhiệt độ
<strong>640×512 × 16-bit</strong> nằm trong các đoạn APP3 của file JPEG — đúng 655.360 byte.
<code>doc_nhiet_raw.py</code> rút được mảng đó ra. So sánh:
<strong>16-bit raw có 4283 mức</strong> khác nhau, ảnh 8-bit chỉ <strong>256 mức</strong> —
mất ~16 lần độ phân giải nhiệt, và mất luôn giá trị tuyệt đối vì mỗi ảnh tự kéo tương phản theo
dải nhiệt của riêng nó. Dựng ortho từ mảng raw thì <em>không cần cân bằng độ sáng nữa</em>
(giá trị vốn đã cùng một thang) và mỗi pixel ortho thành một <strong>số đo nhiệt độ thật</strong>.
Việc cân bằng độ sáng ở trên là cách chữa cho việc đang đọc ảnh xem — đúng nhưng là đường vòng.</div>
""")

# ══════════════════════════════════════════════════════════════════ GĐ 7
S.append(f"""
{gd("⑦", "quet_loi_tren_ortho.py — phát hiện lỗi trên ortho nhiệt")}
<div class="note"><strong>Đã tìm lại được code (12/08/2026).</strong> Tài liệu trước ghi bước này là
&ldquo;mắt xích đứt, không script nào sinh ra <code>loi_tren_ortho_nhiet.json</code>&rdquo; — <strong>không còn đúng</strong>.
Script vẫn còn, chỉ nằm ngoài dự án: nó chạy từ thư mục tạm nên grep <code>*.py</code> không thấy.
Nay khôi phục về <code>bo_dung_goc/quet_loi_tren_ortho.py</code>.</div>

<p>Chạy <code>thermal_solar_anomaly.pt</code> (model <strong>8 lớp của thầy</strong>) trên
<code>ortho_nhiet_tu_lam.tif</code>, cửa sổ trượt <strong>640 px, chồng lấn 30%</strong>, <code>conf 0,25</code>:</p>
<ul class="tick">
<li>Cửa sổ đúng <strong>640 px vì đó là kích thước ảnh nhiệt gốc</strong> — quét cửa sổ to hơn rồi thu nhỏ
thì tấm pin nhỏ hơn lúc train, model detect kém đi.</li>
<li>Bỏ cửa sổ có dưới 35% pixel khác 0 (gần như trống).</li>
<li>Gộp trùng giữa các cửa sổ bằng IoU ≥ 0,30 → còn <strong>211 lỗi</strong>.</li>
<li><code>gan_loi_vao_tam_pin.py</code> chạy tiếp, gán <code>panel_code</code>, <code>in_panel</code>,
<code>iou</code>, <code>dist_cm</code>.</li>
</ul>

<div class="note warn"><strong>Model 8 lớp CHỈ chạy được trên ortho — đã kiểm.</strong>
Thử chính model đó trên ảnh nhiệt <em>gốc</em>: ra <strong>0 box</strong>, kể cả khi hạ <code>conf</code> xuống
<strong>0,02</strong> và phóng ảnh 0,5–3×. Cùng model quét cửa sổ ortho thì ra 111 box/20 cửa sổ.
Ngược lại <code>fault_obb_4class.pt</code> (4 lớp, model của bạn) chạy tốt trên ảnh gốc — 115 box/12 ảnh.
Hai model train trên hai loại dữ liệu khác nhau. <strong>Nên quét trên ortho là ràng buộc của model,
không phải lựa chọn thiết kế.</strong></div>

{io("<code>ortho_nhiet_tu_lam.tif</code> · <code>thermal_solar_anomaly.pt</code> (ổ D:)",
    "<strong><code>loi_tren_ortho_nhiet.json</code></strong> — 211 lỗi, 8 lớp",
    "py -3.13 bo_dung_goc/quet_loi_tren_ortho.py")}

<h3>Bản đối chứng — detect trên ảnh lẻ</h3>
<p><code>quet_loi_anh_le.py</code> làm <strong>ngược thứ tự</strong>: detect trên từng ảnh nhiệt gốc trước,
rồi mới chiếu lên ortho bằng chuỗi <code>pixel → tia ECEF → cắt DSM</code> của
<code>project_box_to_ortho.py</code>. Dùng model 4 lớp vì model 8 lớp không chạy được trên ảnh gốc.</p>

<div class="tbl-wrap"><table>
<tr><th></th><th>Quét ortho (⑦)</th><th>Quét ảnh lẻ (đối chứng)</th></tr>
<tr><td>Thứ tự</td><td>ghép ortho <em>trước</em> → detect sau</td><td>detect <em>trước</em> → chiếu sau</td></tr>
<tr><td>Model</td><td>8 lớp (thầy)</td><td>4 lớp OBB (của bạn)</td></tr>
<tr><td>Số lỗi</td><td>211</td><td><strong>603</strong></td></tr>
<tr><td>Phát hiện thô</td><td>—</td><td>2 756 → mỗi lỗi thấy TB <strong>4,6 lần</strong></td></tr>
<tr><td>Sai số ghép ortho</td><td><strong>có</strong> — box kế thừa ~10,8 cm</td><td>không — detect trên ảnh gốc</td></tr>
<tr><td>Phải gộp trùng</td><td>chỉ giữa các cửa sổ</td><td><strong>giữa 5–10 ảnh chồng lấn</strong></td></tr>
</table></div>

<p><strong>Hai cách kiểm chứng chéo nhau:</strong> <strong>205/211</strong> lỗi của bước ⑦ được cách ảnh lẻ
tìm lại trong bán kính 1 m, khoảng cách trung vị <strong>17 cm</strong> (P90 44 cm). Hai đường đi độc lập
chỉ vào cùng một chỗ.</p>

<div class="note"><strong>Đừng vội kết luận &ldquo;ảnh lẻ tốt hơn&rdquo;</strong> dù nó ra 603 so với 211.
Ba nguyên nhân chưa tách bạch được: hai <em>model khác nhau</em>; ảnh gốc <em>nét hơn</em> ortho nên bắt
được lỗi nhỏ; và ngưỡng gộp 0,60 m có thể <em>chưa gộp hết trùng</em>. Muốn so công bằng phải chạy cùng
một model trên cả hai đường — mà điều đó bất khả, vì mỗi model chỉ chạy được một bên.</div>
{anh("loi_tren_ortho")}
{anh("gan_tam_pin")}
""")

# ══════════════════════════════════════════════════════════════════ đo đạc
S.append(f"""
<h2 id="do">Đo đạc &amp; kiểm chất lượng — bỏ được khỏi đường tới hạn</h2>
<p>Năm script dưới đây <strong>không sinh ra dữ liệu mà bước sau cần</strong>. Chúng trả lời câu hỏi
"làm đúng tới đâu", không phải "làm cái gì".</p>

<div class="tbl-wrap"><table>
<tr><th>Script</th><th>Đo gì</th><th>Đẻ ra</th></tr>
<tr><td><code>do_khop_ortho.py</code></td><td>Ortho nhiệt khớp ortho màu tới đâu — 300 cửa sổ ngẫu nhiên</td><td><code>do_khop_ortho.json</code></td></tr>
<tr><td><code>do_sai_so_ortho.py</code></td><td>Sai số end-to-end, <strong>chấm tay</strong> trên ortho</td><td><code>sai_so_end_to_end.json</code></td></tr>
<tr><td><code>do_tre_chup.py</code></td><td>Dò độ trễ bấm máy — kết luận <code>dang_tin=false</code>, giá trị chỉ là nhiễu</td><td><code>do_tre_chup.json</code></td></tr>
<tr><td><code>soi_25_ca_lech.py</code></td><td>Soi các ca lỗi không gán được tấm pin</td><td><code>soi_25_ca_lech.json</code></td></tr>
<tr><td><code>danh_gia_chi_so.py</code></td><td>Bảng chỉ số nghiệm thu — điểm hợp lưu cuối</td><td><strong>không ghi file</strong>, chỉ in ra màn hình</td></tr>
</table></div>

{hinh("rmse_p90", "Vì sao phải báo cả ba: trung vị cho biết ngày thường, P90 cho biết ca xấu tới đâu, RMSE phạt nặng ca cá biệt.")}

<div class="note"><strong>Hai con số chênh nhau 5 lần nhưng đều đúng.</strong>
RMSE <strong>2,56 cm</strong> đo trên <em>sản phẩm ortho đã ghép</em> — mỗi pixel lấy từ nhiều ảnh chồng phủ
nên sai số từng ảnh được trung bình hoá. Trung vị <strong>14,1 cm</strong> đo lệch giữa <em>hai cảm biến
trên một lần bấm máy</em>, chưa qua bước trung bình hoá đó. Ngưỡng nghiệm thu 30 cm xét sản phẩm ortho.</div>

<div class="note warn"><strong>Bẫy cache.</strong> <code>do_sai_so_ortho.py</code> có
<code>chieu_diem_cache.json</code> thì nạp thẳng cache và không mở lại DSM. Đổi <code>--label</code> mà quên
xoá cache thì toạ độ chiếu vẫn của lần cũ trong khi ảnh hiển thị đã đổi.</div>
""")

# ══════════════════════════════════════════════════════════════════ khối B
S.append(f"""
<h2 id="khoib">Khối B · Đánh giá model phát hiện lỗi</h2>
<p>Độc lập hoàn toàn với khối A — không đọc một file nào của pipeline định vị, chỉ đụng ổ <code>D:</code>
(model và bộ nhãn nằm ở dự án <code>solar-thermal-fault-annotator</code>).</p>

<div class="tbl-wrap"><table>
<tr><th>#</th><th>Script</th><th>Làm gì</th><th>Đẻ ra</th></tr>
<tr><td>⑪a</td><td><code>val_tap_test.py</code></td><td>Val trên tập test 91 ảnh / 280 lỗi, chia theo nhóm chuyến bay</td><td><code>ket_qua_test_4lop.json</code> + 12 biểu đồ</td></tr>
<tr><td>⑪b</td><td><code>phan_tich_recall.py</code></td><td>Tách "bỏ sót" khỏi "gán nhầm lớp"</td><td><code>phan_tich_recall.json</code></td></tr>
<tr><td>⑪c</td><td><code>val_model_4lop.py</code></td><td>Đối chứng hai cách chia tập</td><td><code>ket_qua_val_4lop.json</code></td></tr>
<tr><td>⑪d</td><td><code>so_model_8lop.py</code></td><td>So với model mượn 8 lớp</td><td><code>so_model_8lop.json</code></td></tr>
</table></div>

<div class="note warn"><strong>Ràng buộc cứng: ⑪a phải chạy trước ⑪b.</strong>
<code>phan_tich_recall.py</code> chỉ <em>đọc</em> <code>data_test_nhom.yaml</code> chứ không tự tạo.
Ngoài ra ⑪d không gọi <code>os.makedirs</code> — thư mục <code>ket_qua_val/</code> chưa có thì ba lượt
predict chạy xong mới văng lỗi và mất trắng công.</div>

<h3>Các thông số — hiểu đúng trước khi đọc số</h3>
{hinh("precision_recall", "Mẫu số khác nhau: recall chia cho lỗi thật ngoài đời, precision chia cho số box model vẽ ra. Nên hạ ngưỡng thì recall lên và precision xuống — luôn luôn.")}
{hinh("nguong_conf", "Precision và recall không có giá trị cố định — chúng là một đường cong theo ngưỡng conf. Nói con số mà không nói ngưỡng là chưa nói gì.")}
{hinh("iou", "Hai loại IoU trong dự án này có trần lý thuyết khác hẳn nhau. Thấy 0,687 rồi kêu thấp là nhầm.")}
{hinh("obb_aabb", "Dãy pin nằm chéo so với khung ảnh nên khác biệt này rất đáng kể khi so hai model.")}

{anh("ma_tran_nham", "Ma trận nhầm lẫn trên tập test. Hàng background = số bỏ sót hoàn toàn.")}

<div class="note"><strong>Đọc ma trận phải kiểm ngưỡng.</strong> Chạy <code>model.val()</code> để mặc định
là <code>conf=0.001</code> — ma trận khi đó cho bức tranh hoàn toàn khác: 1900 box, 0 bỏ sót, nhưng
<strong>1620 báo động giả</strong>. Ở ngưỡng vận hành 0,25 thì con số thật là 273/280 bắt được,
260/280 đúng cả tên lớp.</div>

<div class="note warn"><strong>Chỉ bộ <code>solar_cls4_nhom</code> được phép báo cáo.</strong>
Bộ <code>_ngaunhien</code> chia ngẫu nhiên từng ảnh, mà khung ảnh drone chồng lấn nên cùng một tấm pin
vật lý nằm ở cả train lẫn val — điểm trên bộ đó là tự chấm trên dữ liệu đã thấy.</div>

<p><strong>Tác dụng phụ không khai trong code:</strong> ultralytics ghi <code>labels.cache</code> ngược vào
bộ dữ liệu trên ổ <code>D:</code>. Bộ dữ liệu không thật sự chỉ-đọc — sửa nhãn mà cache chưa hết hạn thì
val dùng nhãn cũ.</p>
""")

# ══════════════════════════════════════════════════════════════════ tra ngược
S.append("""
<h2 id="tranguoc">Bảng tra ngược · file nào do đâu mà có</h2>
<p>Sắp theo thứ tự file xuất hiện trong pipeline. <strong>Đậm</strong> = file quan trọng, mất là đau.</p>
<div class="tbl-wrap"><table>
<tr><th>File</th><th>Sinh bởi</th><th>Tiêu thụ bởi</th></tr>
<tr><td><code>manifest_anh.csv</code></td><td><em>mồ côi</em></td><td>5 script</td></tr>
<tr><td><code>cameras.xml</code> · <code>ortho.tif</code> · <code>dsm.tif</code></td><td><em>mồ côi — Metashape</em></td><td>5 script</td></tr>
<tr><td><code>RTK350.txt</code> · <code>best.pt</code></td><td><em>mồ côi — repo của thầy</em></td><td><code>calib_thermal_rgb</code> · <code>loc_anh_tre</code></td></tr>
<tr><td><strong><code>thermal_to_rgb.json</code></strong></td><td><code>calib_thermal_rgb.py</code> <em>(+7 khoá thêm tay)</em></td><td><strong>6 script</strong></td></tr>
<tr><td><strong><code>anh_tre_chup_full.json</code></strong></td><td><code>loc_anh_tre.py --out ...</code></td><td><code>ghep_ortho_nhiet</code> · <code>danh_gia_chi_so</code></td></tr>
<tr><td><code>exif_bay.json</code></td><td><code>loc_anh_rung.py</code></td><td>chính nó (cache)</td></tr>
<tr><td><strong><code>anh_rung.json</code></strong></td><td><code>loc_anh_rung.py</code></td><td><code>ghep_ortho_nhiet</code> · <code>danh_gia_chi_so</code></td></tr>
<tr><td><strong><code>ortho_nhiet_tu_lam.tif</code></strong></td><td><code>ghep_ortho_nhiet.py</code></td><td><code>xuat_nen_net</code> · <code>do_khop_ortho</code></td></tr>
<tr><td><code>sai_so_end_to_end.json</code></td><td><code>do_sai_so_ortho.py</code> (chỉ khi bấm S)</td><td><code>danh_gia_chi_so</code></td></tr>
<tr><td><strong><code>loi_tren_ortho_nhiet.json</code></strong></td>
    <td><code>bo_dung_goc/quet_loi_tren_ortho.py</code><br><em>(khôi phục 12/08 — hết mồ côi)</em></td>
    <td>3 script</td></tr>
<tr><td><code>loi_tu_anh_le.json</code> — 603 lỗi</td>
    <td><code>quet_loi_anh_le.py</code> <em>(bản đối chứng, detect trên ảnh gốc)</em></td>
    <td>đối chiếu với bước ⑦</td></tr>
<tr><td><code>tam_pin_polygon.json</code></td>
    <td><code>bo_dung_goc/tao_tam_pin_polygon.py</code><br><em>(khôi phục 12/08 — cần <code>loi_obb4.json</code> đã mất)</em></td>
    <td><code>do_tre_chup</code> · <code>soi_25_ca_lech</code></td></tr>
<tr><td><code>kiem_chung_0320/0440/0080.json</code></td><td><em>mồ côi — script đã xoá?</em></td><td><code>danh_gia_chi_so</code> (đọc cứng, thiếu là crash)</td></tr>
<tr><td><code>net/net_*.jpg</code></td><td><code>xuat_nen_net.py</code></td><td><code>va_viewer_net.py</code> · trình duyệt</td></tr>
<tr><td><code>so_sanh_model.html</code></td>
    <td><code>bo_dung_goc/tao_viewer_data.py</code> + <code>viewer_khuon.html</code><br>
    <em>(khôi phục 12/08 — đủ để ĐỌC HIỂU, không đủ để dựng lại: file thật đã bị vá nhiều lần và rút từ 4 model xuống 2)</em></td>
    <td>hai script vá</td></tr>
<tr><td><code>kiem_tra_warp/*.jpg</code></td><td>4 script ghi ảnh kiểm chứng</td><td>người xem</td></tr>
</table></div>

<div class="note warn"><strong>Thư mục <code>kiem_tra_warp/</code> phải tồn tại sẵn.</strong>
Không script nào gọi <code>os.makedirs</code> cho nó, và <code>cv2.imwrite</code> <strong>thất bại lặng lẽ</strong>
— không báo lỗi, chỉ là không có ảnh.</div>
""")

# ══════════════════════════════════════════════════════════════════ nhánh cụt
S.append("""
<h2 id="nhanhcut">Nhánh cụt · đã thử và không dùng</h2>
<p>Giữ lại trong repo để người sau không thử lại. Mỗi cái đều có lý do hỏng cụ thể, không phải bỏ dở.</p>

<div class="grid g2">
<div class="card"><h3><code>hieu_chuan_tu_dong.py</code></h3>
<p style="font-size:14.5px">Hiệu chuẩn H tự động bằng tương quan pha. <strong>Hỏng vì lý do bản chất:</strong>
lưới tấm pin tuần hoàn quá đều nên bản đồ viền gần như hàm tuần hoàn hai chiều. Đo trên cặp 0280 (biết
trước đáp án): dịch đúng là (4,7 ; 45,3) px nhưng tương quan tại chính chỗ đó là <strong>ÂM</strong>,
còn các đỉnh mạnh nhất cách nhau đúng bước tấm pin 37–38 px. Không ngưỡng nào sửa được.</p></div>

<div class="card"><h3>Ghép góc tấm + RANSAC</h3>
<p style="font-size:14.5px">Dùng detector YOLO-OBB. Trên RGB nhận 300 tấm conf 0,91–0,94; trên
<strong>ảnh nhiệt chỉ 4–10 tấm conf 0,30–0,38</strong> — mức nhiễu. Muốn đi tiếp phải train lại detector
trên ảnh nhiệt, tức một dự án riêng cần gán nhãn mới.</p></div>

<div class="card"><h3><code>H_da_bu</code> — bù bằng hằng số</h3>
<p style="font-size:14.5px">Ortho từ 15,5 xuống 14,4 cm nhưng <strong>hướng lệch đảo dấu</strong>.
Đo lại 31 vùng: 15 lệch lên / 16 lệch xuống. Là nhiễu cục bộ, không phải sai lệch hệ thống.
<em>Chú ý:</em> chính file JSON vẫn có dòng khuyên dùng <code>H_da_bu</code> — đừng tin, tin khối cảnh báo
ở đầu <code>loc_anh_tre.py</code>.</p></div>

<div class="card"><h3>Hai dấu hiệu EXIF đã tắt</h3>
<p style="font-size:14.5px">Gia tốc và thân máy lắc. Trên đủ 598 ảnh, cả hai <strong>loại nhầm nhiều ảnh
tốt</strong>: bật lên bỏ thêm 9–14 % số ảnh mà P90 và ảnh xấu nhất không đổi.</p></div>
</div>
""")

# ══════════════════════════════════════════════════════════════════ script phụ
S.append("""
<h2 id="phu">Script điều tra &amp; công cụ — không nằm trong luồng chính</h2>
<p>Chín script dưới đây không sinh ra dữ liệu mà bước sau cần, nên không có trong sơ đồ luồng.
Nhưng năm cái đầu là <strong>điều tra thật</strong>, mỗi cái trả lời một câu hỏi cụ thể — liệt kê ở đây
để không ai tưởng chúng là file rác.</p>

<div class="tbl-wrap"><table>
<tr><th>Script</th><th>Trả lời câu hỏi gì</th><th>Kết luận rút ra</th></tr>
<tr><td><code>doc_nhiet_raw.py</code></td>
    <td>Ảnh <code>_T.JPG</code> có chứa nhiệt độ thật không?</td>
    <td><strong>Có</strong> — mảng 16-bit 640×512 nằm trong đoạn APP3, 4283 mức so với 256 mức của ảnh xem.
    Đây là đường nâng cấp lớn nhất còn bỏ ngỏ cho ortho nhiệt.</td></tr>
<tr><td><code>do_recall_theo_nguong.py</code></td>
    <td>Bỏ sót thật là bao nhiêu ở từng ngưỡng conf?</td>
    <td>Ghép cặp trực tiếp thay vì đi qua mAP. Chạy predict một lượt ở conf 0,03 rồi lọc lại nhiều ngưỡng
    nên rẻ. Đối chứng độc lập cho con số recall trong báo cáo.</td></tr>
<tr><td><code>thu_detect_tren_ortho.py</code></td>
    <td>Chạy model thẳng trên ortho nhiệt thì bắt lại được bao nhiêu %?</td>
    <td>Thước đo recall tương đối — 284 lỗi trong viewer đều do chính model này bắt trên <em>ảnh gốc</em>.</td></tr>
<tr><td><code>do_lech_ortho_nhiet.py</code></td>
    <td>Ortho nhiệt Metashape lệch bao nhiêu so với bản tự ghép?</td>
    <td>Bản tự ghép bám lời giải của ảnh RGB nên khớp ortho màu <em>theo định nghĩa</em>; hiệu hai bản
    chính là lệch của bản Metashape. Tránh bẫy tuần hoàn bằng cách đo thô trên ảnh thu nhỏ 6 lần rồi
    tinh lại ở độ phân giải gốc.</td></tr>
<tr><td><code>do_lech_metashape.py</code></td>
    <td>Hai lớp nhiệt trong viewer lệch đều một hướng hay mỗi chỗ một kiểu?</td>
    <td>Lệch đều = chỉ khác gốc toạ độ, bù được. Mỗi chỗ một kiểu = hai lời giải khác nhau.</td></tr>
</table></div>

<p style="margin-top:20px">Bốn cái còn lại là công cụ dựng tài liệu, không liên quan pipeline:
<code>_anh_pipeline.py</code> (đóng gói ảnh base64), <code>_hinh_ve.py</code> (9 hình vẽ SVG),
<code>lam_slide_thuat_ngu.py</code> (deck giải thích thông số), <code>so_ortho_nhiet.py</code>
(dựng ảnh so ba bản ortho), <code>va_viewer_ngoai_nen.py</code> (đánh dấu lỗi ngoài vùng nền —
<strong>đã hoàn tác, hiện không có tác dụng</strong>).</p>

<div class="note"><strong>Ba script <code>do_lech_*</code> và <code>do_recall_*</code> đều tự né được
bẫy lưới tuần hoàn</strong> — thứ đã làm hỏng <code>hieu_chuan_tu_dong.py</code>. Cách né: hoặc thu nhỏ
ảnh cho từng tấm nhoè đi chỉ còn cấu trúc hàng, hoặc giới hạn bán kính dò hẹp hơn nửa bước tấm.
Đây là bài học đã được áp dụng lại đúng chỗ.</div>
""")

# ══════════════════════════════════════════════════════════════════ nguồn gốc
S.append("""
<h2 id="nguongoc">Nguồn gốc code · cái gì của thầy, cái gì tự làm</h2>
<p>Đối chiếu trực tiếp với <code>D:\\Remote_Project\\solarfarm_inspection</code>. Chia làm ba mức,
mỗi mức có bằng chứng kiểm được.</p>

<h3>① Chép nguyên, không sửa một dòng</h3>
<div class="tbl-wrap"><table>
<tr><th>File</th><th>Bằng chứng</th></tr>
<tr><td><code>project_box_to_ortho.py</code></td>
    <td>Giống <strong>hệt</strong> <code>backend/project_box_to_ortho.py</code> — 849 dòng, 17 hàm/lớp
    trùng tên trùng số dòng, <code>diff</code> bỏ qua khoảng trắng ra <strong>0 khác biệt</strong>
    (chỉ khác ký tự xuống dòng CRLF)</td></tr>
<tr><td><code>best.pt</code> — detector tấm pin</td>
    <td>md5 <code>abbbb27f31127a93b2e8ae13ac69a317</code> trùng khít
    <code>backend/yolo_models/best.pt</code></td></tr>
<tr><td><code>RTK350.txt</code> — H khởi tạo của hãng</td>
    <td>Đọc thẳng từ repo thầy, hard-code ở <code>calib_thermal_rgb.py:34</code></td></tr>
</table></div>
<p>Đây là <strong>toàn bộ</strong> phần lấy sẵn. Không file nào khác trong dự án tồn tại trong repo thầy.</p>

<h3>② Dùng lại công thức và quy ước của thầy, code viết mới</h3>
<p>Năm script dưới đây tự viết nhưng <strong>đi theo đúng chuỗi toán và quy ước</strong> lấy từ code
thầy — bốn cái đầu từ <code>project_box_to_ortho.py</code>, cái cuối từ
<code>services/process_log_service.py</code>. Phải nói rõ chỗ này khi báo cáo.</p>
<div class="tbl-wrap"><table>
<tr><th>Script</th><th>Dùng lại gì</th><th>Khác gì so với bản gốc</th></tr>
<tr><td><code>ghep_ortho_nhiet.py</code></td>
    <td>Chuỗi pixel → tia → DSM → ECEF → lon/lat; quy ước <code>cx</code>,<code>cy</code> của Metashape
    là <em>độ lệch so với tâm ảnh</em> (<code>IW/2 + CX</code>); cách ghép chunk transform
    <code>S·(R·X) + T</code></td>
    <td>Chạy <strong>ngược chiều</strong> — thầy chiếu 1 box từ ảnh lên ortho, cái này chiếu từng pixel
    ortho về ảnh nhiệt; vector hoá cả lưới bằng numpy theo tile 2048×2048 thay vì lặp từng điểm</td></tr>
<tr><td><code>do_sai_so_ortho.py</code></td><td>Cùng chuỗi chiếu, cùng cách đọc XML</td>
    <td>Thêm giao diện chấm tay để đo sai số end-to-end</td></tr>
<tr><td><code>do_tre_chup.py</code></td><td>Cùng chuỗi chiếu</td>
    <td>Nội suy tư thế dọc quỹ đạo theo dt để dò độ trễ bấm máy</td></tr>
<tr><td><code>camera_select.py</code></td><td>Phép chiếu ngược ECEF → pixel ảnh</td>
    <td>Đọc XML <strong>đầy đủ</strong> (mọi sensor/component, không hard-code id như bản gốc);
    thêm chọn ảnh theo off-nadir và gộp trùng theo IoU tứ giác</td></tr>
<tr><td><code>calib_thermal_rgb.py</code><br>— hiệu chuẩn H nhiệt→RGB</td>
    <td><strong>Công thức quy đổi H theo phần trăm</strong> của thầy, ở
    <code>services/process_log_service.py:810</code> (thầy chú thích <em>"1:1 EXACT COPY FROM
    preview_alignment"</em>):<br>
    <code>H = S_rgb @ H_pct @ S_th_inv</code><br>
    Đây là cách đọc <code>RTK350.txt</code> — ma trận hãng ghi theo <strong>% khung ảnh</strong>,
    phải nhân hai ma trận tỉ lệ mới ra pixel. Tự mò rất dễ sai</td>
    <td>Thầy chỉ <strong>dùng</strong> H có sẵn để warp. Cái này <strong>tạo ra</strong> H mới:
    giao diện chấm tay có dẫn đường (click ảnh nhiệt → khung RGB tự nhảy tới kèm dấu + dự đoán),
    undistort bằng nội tham số từ <code>cameras.xml</code>, tính lại bằng
    <code>findHomography</code> + RANSAC rồi in sai số từng điểm</td></tr>
</table></div>

<p>Bằng chứng cho dòng cuối — cùng một công thức, viết bằng <code>np.diag</code> thay vì dựng
ma trận đầy đủ, tại <code>calib_thermal_rgb.py:83-85</code>:</p>
<pre><code>H_pct = np.array(nums[:9]).reshape(3, 3)
H = (np.diag([w_rgb / 100.0, h_rgb / 100.0, 1.0]) @ H_pct
     @ np.diag([100.0 / w_th, 100.0 / h_th, 1.0]))</code></pre>

<div class="note"><strong>Nói cho công bằng khi báo cáo:</strong> bản thân chuỗi
pixel → tia → cắt DSM → lon/lat là <em>toán trắc địa chuẩn</em>, không phải phát minh của ai.
Cái thật sự lấy từ code thầy là <strong>bản cài đặt cụ thể</strong>, <strong>quy ước đọc XML
Metashape</strong> (dễ sai nếu tự mò: <code>cx</code>,<code>cy</code> là độ lệch chứ không phải toạ độ
tuyệt đối), và <strong>bước bù xê dịch do độ cao</strong>. Nói "dùng lại chuỗi toán của thầy" là đúng;
nói "chép code" cho bốn file này là sai.</div>

<h3>③ Tự làm hoàn toàn — không có đối ứng trong repo thầy</h3>
<div class="grid g2">
<div class="card"><h3>Khối định vị</h3>
<ul class="tick" style="margin-top:8px">
<li><code>calib_thermal_rgb.py</code> — công cụ chấm H có dẫn đường</li>
<li><code>loc_anh_tre.py</code> — đo lệch từng ảnh bằng viền tấm pin</li>
<li><code>loc_anh_rung.py</code> — lọc theo XMP dữ liệu bay</li>
<li><code>hieu_chuan_tu_dong.py</code> — hướng tự động (đã hỏng, giữ làm ghi chép)</li>
<li><code>do_khop_ortho.py</code> · <code>soi_25_ca_lech.py</code> — QC</li>
</ul></div>
<div class="card"><h3>Khối đánh giá &amp; trình bày</h3>
<ul class="tick" style="margin-top:8px">
<li><code>val_tap_test.py</code> · <code>val_model_4lop.py</code></li>
<li><code>phan_tich_recall.py</code> · <code>so_model_8lop.py</code></li>
<li><code>danh_gia_chi_so.py</code> — bảng chỉ số nghiệm thu</li>
<li><code>xuat_nen_net.py</code> · <code>va_viewer_net.py</code> · <code>xuat_pdf.py</code></li>
<li><code>dong_goi.py</code> · các script dựng tài liệu</li>
</ul></div>
</div>

<div class="note warn"><strong>Model phát hiện lỗi không phải của thầy, cũng không phải của repo này.</strong>
<code>fault_obb_4class.pt</code> đến từ dự án <code>D:\\Remote_Project\\solar-thermal-fault-annotator</code>.
Đừng gộp nó vào phần "code của thầy" khi báo cáo.</div>

<div class="note"><strong>Một câu tóm nếu thầy hỏi:</strong> khâu <em>chiếu ảnh drone lên ortho</em> là
toán và code của thầy — giữ nguyên <code>project_box_to_ortho.py</code>, và bốn script khác đi theo đúng
chuỗi đó. Khâu <em>hiệu chuẩn H nhiệt–RGB, lọc ảnh, ghép ortho nhiệt, đo sai số, đánh giá model</em>
là viết mới trong dự án này.</div>
""")

# ══════════════════════════════════════════════════════════════════ runbook
S.append("""
<h2 id="runbook">Chạy cho một trang trại mới</h2>
<div class="cmd" style="font-size:13.5px;line-height:1.9">
<span style="color:var(--text-3)"># 0. Metashape (ngoài Python): import ảnh RGB → Align → Build DSM → Build Ortho</span><br>
<span style="color:var(--text-3)">#    Export cameras.xml + dsm.tif + ortho.tif vào Thermal2_31M_full_export/</span><br><br>
<span style="color:var(--text-3)"># 1. Hiệu chuẩn H — BỎ QUA nếu đã có H của model drone này</span><br>
python ma/calib_thermal_rgb.py --thermal <b>..._T.JPG</b> --rgb <b>..._W.JPG</b> \\<br>
&nbsp;&nbsp;&nbsp;&nbsp;--xml Thermal2_31M_full_export/cameras.xml --alt 31<br><br>
<span style="color:var(--text-3)"># 2 và 3 — chạy song song được</span><br>
python ma/loc_anh_tre.py <b>--out anh_tre_chup_full.json</b>&nbsp;&nbsp;<span style="color:var(--text-3)"># ~44 phút</span><br>
python ma/loc_anh_rung.py&nbsp;&nbsp;<span style="color:var(--text-3)"># ~1 phút</span><br><br>
<span style="color:var(--text-3)"># 4. Dựng ortho nhiệt — đã tự nối cả hai bộ lọc</span><br>
python ma/ghep_ortho_nhiet.py<br><br>
<span style="color:var(--text-3)"># 7. Phát hiện lỗi trên ortho nhiệt (model 8 lớp) rồi gán mã tấm</span><br>
py -3.13 bo_dung_goc/quet_loi_tren_ortho.py&nbsp;&nbsp;&amp;&amp;&nbsp;&nbsp;py -3.13 bo_dung_goc/gan_loi_vao_tam_pin.py<br><br>
<span style="color:var(--text-3)"># 7b. Bản đối chứng — detect trên ảnh lẻ rồi chiếu (model 4 lớp)</span><br>
py -3.13 ma/quet_loi_anh_le.py&nbsp;&nbsp;<span style="color:var(--text-3)"># ~72 phút · 603 lỗi</span><br><br>
<span style="color:var(--text-3)"># đo đạc &amp; báo cáo (không bắt buộc)</span><br>
python ma/do_khop_ortho.py&nbsp;&nbsp;&amp;&amp;&nbsp;&nbsp;python ma/danh_gia_chi_so.py&nbsp;&nbsp;&amp;&amp;&nbsp;&nbsp;python ma/xuat_pdf.py
</div>

<h3>Ràng buộc thứ tự không thể đảo</h3>
<ul class="tick">
<li><strong>① trước tất cả</strong> — 5 script sau đều cần <code>thermal_to_rgb.json</code></li>
<li>② và ③ song song được, nhưng <strong>cả hai phải xong trước ④</strong></li>
<li>② phải truyền đúng <code>--out anh_tre_chup_full.json</code>, không thì ④ và ⑫ đọc hụt trong im lặng</li>
<li><code>kiem_tra_warp/</code> phải tồn tại sẵn trước khi chạy ②, ④</li>
<li>⑨ trước ⑩ ở khối viewer · ⑪a trước ⑪b ở khối model</li>
</ul>

<div class="note"><strong>Ba con số phải nhớ:</strong> sai số định vị <strong>2,56 cm</strong> (ngưỡng 30 cm) ·
model bắt được <strong>97,5 %</strong> số lỗi ở conf 0,25 · hiệu chuẩn H <strong>4,38 px</strong>,
tốt hơn H của hãng 5,1 lần.</div>

<p style="margin-top:36px;color:var(--text-3);font-size:13.5px">
Tài liệu này dựng bằng <code>lam_tai_lieu_pipeline.py</code> từ ba nguồn:
<code>_ban_do_pipeline.md</code> (bản đồ do 13 agent đọc code rồi kiểm chéo),
<code>_hinh_ve.py</code> (9 hình vẽ SVG) và <code>_anh_pipeline.json</code> (18 ảnh thật của dự án).
Tài liệu sâu hơn về toán và từng dòng code: <code>HUONG_DAN_PIPELINE.md</code>.
Giải thích riêng các thông số: <code>slide_thuat_ngu.html</code>.</p>
""")

MUC = [("gd0", "GĐ 0 · có sẵn"), ("gd1", "Khối A · định vị"), ("do", "Đo đạc"),
       ("khoib", "Khối B · model"), ("tranguoc", "Tra ngược file"),
       ("nhanhcut", "Nhánh cụt"), ("phu", "Script điều tra"),
       ("nguongoc", "Nguồn gốc code"), ("runbook", "Chạy trang trại mới")]
toc = '<div class="toc">' + "".join(
    f'<a href="#{i}">{t}</a>' for i, t in MUC) + '</div>'

html = (re.sub(r"<title>.*?</title>",
               "<title>Tài liệu pipeline — định vị lỗi tấm pin từ ảnh nhiệt</title>",
               goc[:goc.index("<style>")], flags=re.S)
        + CSS + THEM + '<div class="rail"></div>' + toc
        + '<div class="doc">' + "\n".join(S) + "</div>")

open(RA, "w", encoding="utf-8").write(html)
print("-> %s  (%.1f MB · %d mục · %d hình vẽ · %d ảnh)"
      % (RA, os.path.getsize(RA) / 1e6, len(MUC), len(H), len(ANH)))
