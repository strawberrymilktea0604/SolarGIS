#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng `tai_lieu/trang_ma_tran_h.html` — trang giải thích riêng ma trận H.

Trang một mạch cuộn (không phải deck): mở đầu bằng câu hỏi, rồi bóc dần từng phần
của H, mỗi phần kèm một hình ĐO ĐƯỢC chứ không phải hình vẽ ước lệ.

Ảnh nhúng data URI để trang tự đứng một mình — publish lên artifact thì mọi tham
chiếu ra ngoài file đều bị chặn.

Cần có trước:
    py -3.13 ma/hinh_hieu_chuan_chi_tiet.py     -> hieu_chuan_c1..c3
    py -3.13 ma/hinh_ma_tran_h.py               -> h_v1..v3

    py -3.13 ma/lam_trang_ma_tran_h.py
"""
import argparse
import base64
import json
import os
import sys

import cv2
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/trang_ma_tran_h.html"))
ap.add_argument("--rong", type=int, default=1400)
args = ap.parse_args()

D = json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))
H = np.array(D["H_thermal_to_rgb"], float)
PT = np.array(D["points_thermal"], float)
PR = np.array(D["points_rgb"], float)


def anh(ten):
    p = os.path.join(BASE, "tai_lieu/hinh", ten)
    if not os.path.exists(p):
        raise SystemExit("[DỪNG] thiếu %s — xem docstring." % ten)
    im = cv2.imread(p)
    if im.shape[1] > args.rong:
        k = args.rong / im.shape[1]
        im = cv2.resize(im, (args.rong, int(im.shape[0] * k)), interpolation=cv2.INTER_AREA)
    b = base64.b64encode(cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 84])[1].tobytes())
    print("   %-30s -> %.0f KB" % (ten, len(b) / 1024))
    return "data:image/jpeg;base64," + b.decode("ascii")


def hinh(ten, chu, alt):
    return ('<figure class="figbox"><img src="%s" alt="%s"/>'
            '<figcaption>%s</figcaption></figure>' % (anh(ten), alt.replace('"', "'"), chu))


# Một ví dụ chạy tay bằng số thật, lấy luôn cặp điểm số 1.
# Thay bằng .replace() chứ KHÔNG dùng `% vd`: chuỗi trang có đầy dấu % của CSS
# (width:100%, 62%...) nên phép format sẽ vỡ ngay.
u, v = PT[0]
p = H @ [u, v, 1]
VD = {
    "__U__": "%.1f" % u, "__V__": "%.1f" % v,
    "__X__": "%.1f" % p[0], "__Y__": "%.1f" % p[1], "__W__": "%.5f" % p[2],
    "__RX__": "%.1f" % (p[0] / p[2]), "__RY__": "%.1f" % (p[1] / p[2]),
}

print("[NHÚNG]")
TRANG = """<title>Ma trận H</title>
<style>
:root{
  --ground:#f7f4f1; --surface:#ffffff; --surface-2:#efe9e4;
  --line:#ded5cd; --line-soft:#ebe4dd;
  --text:#1b1620; --text-2:#5f5769; --text-3:#8b8394;
  --ember:#c24d00; --ember-soft:#f7e3d4; --flare:#9a6b00;
  --steel:#2f5f9e; --steel-soft:#dde7f4; --good:#1e6b46; --bad:#b03040;
  --shadow:0 1px 2px rgba(27,22,32,.06), 0 8px 24px rgba(27,22,32,.06);
  --font-display:"Bahnschrift","DIN Alternate","Segoe UI",system-ui,sans-serif;
  --font-body:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
  --font-mono:"Cascadia Mono",Consolas,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0f0d16; --surface:#181524; --surface-2:#221d31;
    --line:#332b47; --line-soft:#262038;
    --text:#ece7f2; --text-2:#a49bb5; --text-3:#776e8a;
    --ember:#ff7a1a; --ember-soft:#3a2214; --flare:#ffc247;
    --steel:#6f9fdd; --steel-soft:#1a2740; --good:#4cc38a; --bad:#f0616f;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --ground:#0f0d16; --surface:#181524; --surface-2:#221d31;
  --line:#332b47; --line-soft:#262038;
  --text:#ece7f2; --text-2:#a49bb5; --text-3:#776e8a;
  --ember:#ff7a1a; --ember-soft:#3a2214; --flare:#ffc247;
  --steel:#6f9fdd; --steel-soft:#1a2740; --good:#4cc38a; --bad:#f0616f;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0; background:var(--ground); color:var(--text);
     font-family:var(--font-body); font-size:17px; line-height:1.62;
     -webkit-font-smoothing:antialiased}
.rail{position:fixed; left:0; top:0; width:5px; height:100dvh; z-index:40;
  background:linear-gradient(180deg,#0b0a12 0%,#3b1a56 22%,#8e2467 42%,#d9481f 62%,#ff8a1e 80%,#ffd84a 100%);
  opacity:.9}
.wrap{max-width:900px; margin:0 auto; padding:clamp(34px,5vw,72px) clamp(22px,4vw,40px) 100px}
.eyebrow{font-family:var(--font-mono); font-size:12px; letter-spacing:.16em;
  text-transform:uppercase; color:var(--text-3); display:flex; align-items:center;
  gap:10px; margin-bottom:14px}
.eyebrow::before{content:""; width:26px; height:2px; background:var(--ember); flex:none}
h1{font-family:var(--font-display); font-weight:600; letter-spacing:-.015em;
   font-size:clamp(34px,5.4vw,60px); line-height:1.04; margin:0 0 16px; text-wrap:balance}
h2{font-family:var(--font-display); font-weight:600; letter-spacing:-.01em;
   font-size:clamp(23px,2.7vw,33px); line-height:1.15; margin:56px 0 12px; text-wrap:balance;
   padding-top:20px; border-top:1px solid var(--line-soft)}
h2 em{font-style:normal; color:var(--ember)}
h3{font-family:var(--font-display); font-size:19px; font-weight:600; margin:28px 0 8px}
.dat{font-size:clamp(17px,1.4vw,20px); color:var(--text-2); margin:0 0 26px; max-width:64ch}
p{margin:0 0 14px; max-width:68ch}
strong{color:var(--text)}
code{font-family:var(--font-mono); font-size:.87em; background:var(--surface-2);
     padding:1px 6px; border-radius:5px; color:var(--ember)}
figure{margin:26px 0 8px}
.figbox{background:var(--surface); border:1px solid var(--line); border-radius:12px;
        padding:clamp(10px,1.2vw,16px); box-shadow:var(--shadow); overflow-x:auto}
.figbox img{display:block; width:100%; height:auto; border-radius:7px}
figcaption{margin-top:10px; font-size:13.5px; color:var(--text-3); line-height:1.5}
figcaption b{color:var(--text-2); font-weight:600}
.tbl{overflow-x:auto; border:1px solid var(--line); border-radius:11px;
     background:var(--surface); margin:20px 0}
table{border-collapse:collapse; width:100%; font-size:15px}
th,td{padding:9px 14px; text-align:left; border-bottom:1px solid var(--line-soft)}
th{font-family:var(--font-mono); font-size:11.5px; letter-spacing:.11em;
   text-transform:uppercase; color:var(--text-3); background:var(--surface-2); font-weight:500}
tr:last-child td{border-bottom:0}
td.num{font-family:var(--font-mono); font-variant-numeric:tabular-nums; text-align:right}
.note{border-left:3px solid var(--flare); background:var(--surface-2);
      padding:13px 17px; border-radius:0 10px 10px 0; font-size:15.5px;
      color:var(--text-2); margin:20px 0}
.note.warn{border-left-color:var(--bad)}
.note strong{color:var(--text)}
.chay{font-family:var(--font-mono); font-size:14px; background:var(--surface-2);
      border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin:20px 0;
      overflow-x:auto; line-height:1.9; color:var(--text-2)}
.chay b{color:var(--ember); font-weight:600}
ul{margin:0 0 14px; padding-left:20px; max-width:66ch}
li{margin:6px 0; color:var(--text-2)}
li strong{color:var(--text)}
</style>
<div class="rail"></div>
<div class="wrap">

<div class="eyebrow">Định vị lỗi tấm pin · khối hiệu chuẩn</div>
<h1>Ma trận H</h1>
<p class="dat">Drone mang hai ống kính. Ống nhiệt thấy điểm nóng nhưng không biết mình
đang nhìn đâu; ống màu biết mình nhìn đâu nhưng không thấy điểm nóng. <strong>H là thứ
duy nhất nối hai bên</strong> — và toàn bộ chuỗi định vị đứng hay đổ là ở đó.</p>

<h2>1 · Bài toán, một câu</h2>
<p>Hai ống kính nằm cạnh nhau trên cùng gimbal, chụp cùng lúc, nhìn cùng một cảnh. Nhưng
ảnh nhiệt là <strong>640 × 512</strong> còn ảnh màu là <strong>4056 × 3040</strong>, và hai
ống lệch nhau vài centimet. Điểm nóng nằm ở pixel (217, 334) của ảnh nhiệt —
<strong>nó là pixel nào của ảnh màu?</strong></p>
__C1__

<h2>2 · H là <em>cái máy trả lời</em> câu đó</h2>
<p>Chỉ là một bảng 9 số. Bỏ toạ độ nhiệt vào, ra toạ độ màu. Không có gì huyền bí:</p>
<div class="chay">
(u, v, 1) &nbsp;×&nbsp; H &nbsp;=&nbsp; (x, y, w) &nbsp;&nbsp;rồi&nbsp;&nbsp; chia cả hai cho w<br><br>
điểm số 1 trên ảnh nhiệt &nbsp;&nbsp;<b>(__U__, __V__)</b><br>
nhân với H &nbsp;→&nbsp; (__X__, __Y__, __W__)<br>
chia cho w &nbsp;→&nbsp; <b>(__RX__, __RY__)</b> trên ảnh màu
</div>
<p>Bước "chia cho w" là chỗ hay bị bỏ qua. Nếu <code>w</code> luôn bằng 1 thì H chỉ là phép
biến hình phẳng. Ở đây <code>w</code> thay đổi theo vị trí — mục 4 nói vì sao điều đó quan trọng.</p>

<h2>3 · Chín số ấy <em>làm gì</em></h2>
<p>Tách ra thì mỗi nhóm số phụ trách đúng một việc, và đều đo được:</p>
<div class="tbl"><table>
<thead><tr><th>Vị trí trong H</th><th>Việc</th><th>Trị đo được</th></tr></thead>
<tbody>
<tr><td>2 số trên đường chéo</td><td><strong>Phóng to</strong></td>
    <td class="num">2,640 và 2,634 lần</td></tr>
<tr><td>2 số chéo góc</td><td><strong>Xoay</strong></td><td class="num">−0,345°</td></tr>
<tr><td>2 số cột cuối</td><td><strong>Dịch</strong></td>
    <td class="num">1 195,0 và 961,6 px</td></tr>
<tr><td>2 số hàng cuối</td><td><strong>Phối cảnh</strong></td>
    <td class="num">1,12e−5 và 1,78e−6</td></tr>
</tbody></table></div>
<p>Phóng to 2,64 lần vì ảnh màu có nhiều pixel hơn cho cùng một mảnh đất. Xoay 0,345° vì
hai ống lắp không hoàn toàn song song. Dịch hơn nghìn pixel vì ống nhiệt nhìn hẹp hơn, khung
của nó nằm lọt vào giữa khung màu:</p>
__V1__

<h2>4 · Hai số cuối — phần <em>khó hiểu nhất</em>, và không bỏ được</h2>
<p>Nếu hai số ở hàng cuối bằng 0 thì <code>w</code> luôn bằng 1, và H chỉ là phóng + xoay +
dịch đều nhau trên cả ảnh. Khác 0 nghĩa là <strong>tỉ lệ thay đổi theo vị trí trong khung</strong> —
giống khi bạn nhìn nghiêng một tờ giấy, cạnh xa trông ngắn hơn cạnh gần.</p>
<p>Hai số đó nhỏ tới mức trông như số làm tròn thừa. Nhưng tắt chúng đi rồi đo xem mỗi điểm
xê dịch bao nhiêu:</p>
__V2__
<div class="tbl"><table>
<thead><tr><th>vị trí trên ảnh nhiệt</th><th>lệch nếu bỏ phần phối cảnh</th></tr></thead>
<tbody>
<tr><td>góc trên-trái</td><td class="num">0 px</td></tr>
<tr><td>góc dưới-trái</td><td class="num">2,4 px</td></tr>
<tr><td>tâm ảnh</td><td class="num">10,5 px</td></tr>
<tr><td>góc trên-phải</td><td class="num">21,6 px</td></tr>
<tr><td>góc dưới-phải</td><td class="num">29,6 px</td></tr>
</tbody></table></div>
<p>Gần <strong>30 pixel</strong> ở góc — quy ra mặt đất là 28 cm, gấp mười lần sai số cuối
cùng của cả chuỗi. Đó là lý do phải dùng ma trận 3×3 chứ không thể ghi gọn "phóng 2,64 lần
rồi dịch 1195 px".</p>

<h2>5 · Vì sao <em>31 cặp điểm</em> chứ không phải 4</h2>
<p>Về toán, H có <strong>8 ẩn số</strong>: 9 ô nhưng nhân cả bảng với một hằng số thì kết quả
không đổi, nên một bậc tự do là thừa. Mỗi cặp điểm cho 2 phương trình, vậy
<strong>4 cặp là đủ giải</strong>.</p>
<p>Chấm 31 cặp là để <strong>dư ra</strong>. Tay người chấm lệch vài pixel là chuyện thường;
có dư điểm thì bình phương tối thiểu san đều sai số đó, thay vì để một cú chấm lệch làm hỏng
cả ma trận. Đổi lại, không cặp nào khớp hoàn hảo — sai số còn lại chính là thứ mục 8 mổ xẻ.</p>

<h2>6 · Làm sao biết H <em>đúng</em></h2>
<p>Không nhìn 9 con số mà biết được. Phải warp ảnh nhiệt bằng H rồi cài răng lược với ảnh
màu: mép tấm pin chạy liền qua đường kẻ thì đúng, gãy khúc thì sai.</p>
__C2__

<h2>7 · Ma trận của hãng lệch <em>22 pixel</em></h2>
<p>DJI có sẵn một ma trận trong <code>RTK350.txt</code>, ghi theo hệ <strong>phần trăm khung
ảnh</strong> chứ không phải pixel — đổi sang pixel rồi mới so được. Kết quả:</p>
__C3__
<div class="note"><strong>Vì sao lệch tới 22 px.</strong> Đó là số hiệu chuẩn của
<strong>dòng máy</strong> tại nhà xưởng, không phải của con máy này. Sai lệch lắp ráp từng
chiếc, cộng thêm gimbal đã tháo lắp, làm nó trôi. Đây chính là lý do phải chấm tay —
nhưng chỉ <strong>một lần cho mỗi model drone</strong>, không phải mỗi trang trại.</div>

<h2>8 · H một mình <em>chưa đủ</em></h2>
<p>Chỗ này phát hiện khi tự tính lại sai số để lấy số minh hoạ. File ghi RMSE 4,38 px, nhưng
áp thẳng <code>H_thermal_to_rgb</code> lên 31 cặp điểm thì ra <strong>11,65 px</strong>.</p>
<p>Vẽ sai số của từng cặp ra thì lộ ngay nguyên nhân:</p>
__V3__
<p>Bên trái <strong>mọi mũi tên chỉ cùng một hướng</strong> — đó là dấu hiệu kinh điển của một
độ lệch hằng số chưa được trừ, không phải nhiễu. Sai số trung bình đúng bằng
<strong>(−9,65; −4,84) px</strong>, mà đó chính là trường <code>hieu_chinh_bo_sung</code> nằm
sẵn trong cùng file. Trừ nó đi thì mũi tên tán loạn, trung bình về (0,00; 0,00) và RMSE về
đúng 4,38 px như file ghi.</p>
<p>Nói cách khác: phép biến đổi đầy đủ là <strong>H rồi trừ offset</strong>. Bản thân
<code>H_thermal_to_rgb</code> chưa phải phép biến đổi hoàn chỉnh.</p>
<div class="note warn"><strong>Chưa kết luận đây là lỗi.</strong> Trong <code>ma/</code>, chỉ
<code>lam_notebook.py</code> có trừ offset; các script pipeline đọc H rồi dùng thẳng. Nhưng có
một khả năng hợp lý: phép đo trễ màn trập của <code>loc_anh_tre.py</code> đo <code>dx, dy</code>
từng ảnh bằng cách trượt tìm chỗ khớp — nếu H thiếu một hằng số thì phép đo đó <em>tự nuốt</em>
hằng số ấy vào, và trừ cả hai là bù gấp đôi. Đúng cùng lý do mà <code>--lech-tay</code> ghi đè
chứ không cộng dồn. Muốn biết chắc phải chạy <code>quet_loi_anh_le.py</code> hai lần rồi so
lệch tâm với nhãn tay.</div>

<h2>9 · H được dùng ở <em>ba chỗ</em>, hai chiều</h2>
<ul>
<li><strong>Chiếu box lỗi xuống đất</strong> — chiều xuôi. Pixel nhiệt → H → pixel màu → tia →
cắt DSM → lon/lat. Đây là nhánh đang chạy.</li>
<li><strong>Ghép ortho nhiệt</strong> — chiều <strong>ngược</strong>. Mỗi ô lưới ortho hỏi
ngược xem nó lấy giá trị từ pixel nào của ảnh nhiệt nào, nên dùng <code>H⁻¹</code>.</li>
<li><strong>Lọc ảnh trễ màn trập</strong> — chiếu viền tấm pin qua H xuống ảnh nhiệt rồi trượt
tìm chỗ khớp. Ảnh nào không khớp nổi là ảnh chụp lúc drone chưa ổn định.</li>
</ul>
<div class="note"><strong>H là phần lõi tái sử dụng được của cả dự án.</strong> Nó gắn với
<em>model drone</em>, không gắn với trang trại. Chấm một lần cho ZH20T là dùng được cho mọi
trang trại bay bằng ZH20T. Mọi thứ khác trong pipeline — ortho, DSM, tư thế camera, nhãn tay —
đều phải làm lại cho từng chuyến bay.</div>
<div class="note warn"><strong>Đừng thử tự động hoá việc chấm H.</strong> Hai hướng đã thử và
hỏng vì lý do bản chất. Tương quan pha: lưới tấm pin tuần hoàn quá đều nên đỉnh tương quan lặp
lại ở mọi bước lưới, không có đỉnh nào trội. Ghép theo góc tấm + RANSAC: detector tấm pin không
chạy được trên ảnh nhiệt, conf tụt còn 0,30–0,38 tức mức nhiễu.</div>

</div>
"""
for k, x in VD.items():
    TRANG = TRANG.replace(k, x)

for moc, ten, chu, alt in [
    ("__C1__", "hieu_chuan_c1_cap_diem.jpg",
     "<b>Cùng một cảnh, hai khung toạ độ.</b> 31 cặp điểm chấm tay trên cặp ảnh <code>0280</code>: "
     "mỗi số ứng với một cặp, điểm bên trái trên ảnh nhiệt, điểm cùng số bên phải trên ảnh màu. "
     "Chọn góc tấm pin và giao lối đi vì đó là chỗ nhìn rõ trên cả hai kênh — mặt tấm thì nhiệt "
     "gần như phẳng màu, không bám vào đâu được.",
     "Anh nhiet va anh RGB canh nhau voi 31 cap diem danh so"),
    ("__V1__", "h_v1_bon_goc.jpg",
     "<b>Khung ảnh nhiệt nằm ở đâu trên khung ảnh màu.</b> Cam là bốn góc của ảnh nhiệt sau khi "
     "qua H; xanh là lưới ô vuông của ảnh nhiệt, cũng qua H. Lưới không còn vuông — đó chính là "
     "phần phối cảnh đang làm việc.",
     "Khung anh nhiet sau khi qua H nam tren khung RGB, kem luoi bien dang"),
    ("__V2__", "h_v2_phoi_canh.jpg",
     "<b>Hai số ở hàng cuối làm gì.</b> Mỗi mũi tên là độ xê dịch nếu tắt phần phối cảnh đi, "
     "phóng đại ×5. Bằng 0 ở góc trên-trái và lớn dần về góc dưới-phải, tối đa 29,6 px.",
     "Truong vector cho thay do dich do phan phoi canh gay ra"),
    ("__C2__", "hieu_chuan_c2_ban_co.jpg",
     "<b>Kiểm tra bằng bàn cờ.</b> Ô sáng là ảnh màu, ô tối là ảnh nhiệt sau khi warp bằng H. "
     "Mép tấm pin và lối đi chạy liền qua đường kẻ trắng — dấu hiệu H đúng.",
     "Anh nhiet warp bang H cai rang luoc voi anh RGB kieu ban co"),
    ("__C3__", "hieu_chuan_c3_hang_vs_tay.jpg",
     "<b>Cùng cặp ảnh, cùng cách kiểm tra, chỉ khác ma trận.</b> Trái: ma trận của hãng, "
     "RMSE 22,34 px — nhìn dải lối đi trắng ở ô màu rồi bắt sang ô nhiệt kế bên, chúng lệch rõ. "
     "Phải: chấm tay, RMSE 4,38 px.",
     "Hai ban co canh nhau so ma tran hang va ma tran cham tay"),
    ("__V3__", "h_v3_sai_so.jpg",
     "<b>31 vector sai số, phóng đại ×20.</b> Trái: chỉ dùng H — mọi mũi tên chỉ cùng một hướng, "
     "sai số trung bình (−9,65; −4,84) px. Phải: trừ <code>hieu_chinh_bo_sung</code> — mũi tên "
     "tán loạn, trung bình về (0,00; 0,00), RMSE đúng 4,38 px như file ghi.",
     "Hai bang vector sai so, trai lech he thong mot huong, phai tan loan"),
]:
    TRANG = TRANG.replace(moc, hinh(ten, chu, alt))

open(args.ra, "w", encoding="utf-8").write(TRANG)
print("\n-> %s  (%.1f MB)" % (args.ra, os.path.getsize(args.ra) / 1e6))
