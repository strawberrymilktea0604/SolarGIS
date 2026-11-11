#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dung slide_thuat_ngu.html — giai thich cac thong so cua bai toan nay.

Khong chep CSS sang file moi: doc thang khoi <style> cua _slide_mau.html roi
ghep, de hai deck luon cung mot bo thiet ke. Sua mau o mau thi chay lai la
deck nay doi theo.

    python ma/lam_slide_thuat_ngu.py
"""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAU = os.path.join(BASE, "tai_lieu/_slide_mau.html")
RA = os.path.join(BASE, "tai_lieu/slide_thuat_ngu.html")

goc = open(MAU, encoding="utf-8").read()
dau = goc[:goc.index("</style>") + len("</style>")]
dau = re.sub(r"<title>.*?</title>",
             "<title>Thuật ngữ &amp; thông số — định vị lỗi tấm pin từ ảnh nhiệt</title>",
             dau, flags=re.S)
cuoi = goc[goc.rindex("<script>"):]

S = []


def slide(html):
    S.append(html)


# 1 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">1008-stage1-rgb-thermal · Bản tra cứu</div>
  <h1>Những thông số<br>cần hiểu trước</h1>
  <p class="sub">Mọi con số trong báo cáo đều rơi vào một trong hai nhóm dưới đây. Trộn hai
  nhóm vào nhau là nguồn gốc của gần như mọi hiểu nhầm — kể cả một kết luận sai đã lọt vào
  bản 1.0 của báo cáo.</p>
  <div class="cover-rule"></div>
  <div class="grid g2">
    <div class="card">
      <h3>Chỉ số của MODEL</h3>
      <p style="color:var(--text-2);font-size:15.5px">Đo bằng đơn vị <strong>không thứ nguyên</strong>
      (0 → 1): precision, recall, mAP, IoU. Trả lời câu hỏi <em>“model nhìn có chuẩn không?”</em></p>
    </div>
    <div class="card">
      <h3>Chỉ số của ĐỊNH VỊ</h3>
      <p style="color:var(--text-2);font-size:15.5px">Đo bằng <strong>centimet</strong> ngoài thực địa:
      RMSE, trung vị, P90. Trả lời câu hỏi <em>“chỉ đúng chỗ không?”</em></p>
    </div>
  </div>
""")

# 2 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Nền tảng</div>
  <h2>Ba chữ viết tắt <em>mọi thứ khác dựng lên từ đó</em></h2>
  <p class="sub">Với mỗi lỗi thật trên ảnh, model hoặc bắt trúng, hoặc bỏ qua, hoặc vẽ thừa
  một cái không có gì.</p>
  <div class="grid g3">
    <div class="card">
      <h3>TP — bắt trúng</h3>
      <p style="color:var(--text-2);font-size:15px">Có lỗi thật, model vẽ box trùm lên đúng chỗ đó.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Dự án này, ở conf 0,25</span>
        <span class="n good">273</span><span class="d">trên 280 lỗi thật</span></div>
    </div>
    <div class="card">
      <h3>FN — bỏ sót</h3>
      <p style="color:var(--text-2);font-size:15px">Có lỗi thật mà model không vẽ gì. Tấm hỏng
      không ai đi sửa — loại sai lầm <strong>đắt nhất</strong> ở bài toán này.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Bỏ sót</span>
        <span class="n">7</span><span class="d">2,5 % số lỗi</span></div>
    </div>
    <div class="card">
      <h3>FP — báo nhầm</h3>
      <p style="color:var(--text-2);font-size:15px">Model vẽ box ở chỗ không có lỗi. Tốn kỹ thuật
      viên đi soi một chuyến — khó chịu nhưng <strong>rẻ</strong>.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Box thừa</span>
        <span class="n bad">70</span><span class="d">trên 91 ảnh test</span></div>
    </div>
  </div>
  <div class="note" style="margin-top:20px"><strong>Vì sao phải phân biệt rõ FN và FP:</strong>
  ở đây bỏ sót một tấm đang nóng thì nó tiếp tục hỏng, tụt sản lượng, nặng thì cháy; còn báo
  nhầm chỉ tốn vài phút đi soi. Hai loại sai <em>không</em> đắt như nhau — và đó là lý do
  không chọn ngưỡng theo F1.</div>
""")

# 3 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Hai chỉ số cốt lõi</div>
  <h2>Precision và Recall — <em>đọc ngược nhau</em></h2>
  <div class="grid g2">
    <div class="card hot">
      <h3>Recall — bắt được bao nhiêu phần lỗi thật</h3>
      <pre style="margin:10px 0">Recall = <b>TP</b> / (TP + <b>FN</b>)
       = số lỗi bắt được / <i>tổng lỗi thật</i></pre>
      <p style="color:var(--text-2);font-size:15px">Recall 0,96 nghĩa là: cứ 100 tấm hỏng
      ngoài thực địa thì danh sách nêu tên được 96.</p>
    </div>
    <div class="card">
      <h3>Precision — báo ra thì đúng bao nhiêu phần</h3>
      <pre style="margin:10px 0">Precision = <b>TP</b> / (TP + <b>FP</b>)
          = số báo đúng / <i>tổng số báo ra</i></pre>
      <p style="color:var(--text-2);font-size:15px">Precision 0,875 nghĩa là: cứ 100 box model
      báo ra thì 87–88 cái là lỗi thật, 12–13 cái là báo nhầm.</p>
    </div>
  </div>
  <div class="note" style="margin-top:20px"><strong>Mẹo nhớ:</strong> mẫu số của recall là
  <em>lỗi thật ngoài đời</em> (model không đổi được), mẫu số của precision là <em>số box model
  vẽ ra</em> (model tự quyết). Nên hạ ngưỡng thì recall lên và precision xuống — luôn luôn.</div>
""")

# 4 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Cái điều khiển tất cả</div>
  <h2>Ngưỡng <em>conf</em> — và cái bẫy đi kèm</h2>
  <p class="sub">Model chấm cho mỗi box một điểm tin cậy 0→1. Ngưỡng là mức tối thiểu để nhận.
  Đổi ngưỡng là đổi cả precision lẫn recall — nên <strong>nói P/R mà không nói ngưỡng thì
  con số vô nghĩa.</strong></p>
  <div class="tbl-wrap">
    <table>
      <tr><th>conf</th><th class="num">0,05</th><th class="num">0,15</th><th class="num">0,25</th>
        <th class="num">0,40</th><th class="num">0,50</th><th class="num">0,64</th><th class="num">0,70</th></tr>
      <tr><td>Precision</td><td class="num">0,698</td><td class="num">0,822</td>
        <td class="num"><strong>0,875</strong></td><td class="num">0,902</td><td class="num">0,914</td>
        <td class="num">0,940</td><td class="num">0,954</td></tr>
      <tr><td>Recall</td><td class="num">0,996</td><td class="num">0,965</td>
        <td class="num"><strong>0,959</strong></td><td class="num">0,938</td><td class="num">0,922</td>
        <td class="num">0,906</td><td class="num">0,881</td></tr>
      <tr><td>F1</td><td class="num">0,812</td><td class="num">0,881</td><td class="num">0,911</td>
        <td class="num">0,918</td><td class="num">0,917</td><td class="num"><strong>0,922</strong> ← đỉnh</td>
        <td class="num">0,916</td></tr>
    </table>
  </div>
  <div class="note warn" style="margin-top:20px"><strong>Cái bẫy đã sập một lần:</strong>
  ultralytics mặc định báo P/R <em>tại điểm F1 lớn nhất</em> — ở model này là conf 0,637.
  Con số quen thuộc <code>P 0,946 · R 0,897</code> là lấy ở đó, <strong>không phải</strong> ở
  ngưỡng đang chạy thật. Bản 1.0 báo cáo đọc 0,897 thành “model sót 10 % số lỗi” — sai.
  Ở ngưỡng vận hành 0,25 thì recall là 0,959.</div>
""")

# 5 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Cách gộp hai chỉ số</div>
  <h2>F1 và F-beta — <em>chọn ngưỡng theo giá phải trả</em></h2>
  <p class="sub">F1 là trung bình điều hoà của P và R, tức <strong>coi bỏ sót và báo nhầm đắt
  ngang nhau</strong>. Giả định đó không đúng ở đây. F-beta cho phép khai báo độ lệch.</p>
  <div class="grid g-58">
    <div>
      <pre>F<sub>β</sub> = (1+β²)·P·R / (β²·P + R)

β = 1  <i>sót đắt bằng báo nhầm</i>
β = 2  <i>sót đắt gấp 4 lần</i>
β = 3  <i>sót đắt gấp 9 lần</i></pre>
      <div class="note" style="margin-top:14px">Bài toán này sót đắt hơn rõ ràng → tiêu chí
      đúng là <strong>F2</strong>, không phải F1.</div>
    </div>
    <div class="tbl-wrap">
      <table>
        <tr><th>Tiêu chí</th><th class="num">conf tốt nhất</th><th class="num">Còn lại /211 lỗi</th></tr>
        <tr><td>F1</td><td class="num">0,64</td><td class="num">115 <span class="pill no">mất 46 %</span></td></tr>
        <tr><td>F2</td><td class="num">0,11</td><td class="num">211</td></tr>
        <tr><td>F3</td><td class="num">0,08</td><td class="num">211</td></tr>
        <tr><td><strong>Đang dùng</strong></td><td class="num"><strong>0,25</strong></td>
          <td class="num">211 <span class="pill ok">giữ đủ</span></td></tr>
      </table>
    </div>
  </div>
  <div class="note" style="margin-top:18px"><strong>Vì sao 0,25 chứ không phải 0,11:</strong>
  F2 phẳng trong cả khoảng 0,11–0,30. Trong vùng phẳng đó, 0,25 mua được nhiều precision nhất
  mà gần như không mất recall — <strong>bớt 37 % box rác</strong> (0,802 → 0,875) đổi lấy
  2,8 điểm recall.</div>
""")

# 6 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Đo độ trùng khớp</div>
  <h2>IoU — <em>và hai loại IoU rất dễ lẫn</em></h2>
  <p class="sub">IoU = diện tích giao / diện tích hợp của hai hình. Bằng 1 là trùng khít,
  bằng 0 là rời nhau. Trong dự án này chữ “IoU” xuất hiện ở <strong>hai chỗ khác hẳn nhau</strong>.</p>
  <div class="grid g2">
    <div class="card">
      <h3>IoU dự đoán ↔ nhãn</h3>
      <p style="color:var(--text-2);font-size:15px">Dùng để phán “box này có tính là bắt trúng
      không”. Ngưỡng quy ước 0,5. Trần lý thuyết là <strong>1,0</strong>.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Dự án này</span>
        <span class="n good">rất chặt</span>
        <span class="d">mAP giữ nguyên 0,965 từ IoU 0,50 tới 0,80</span></div>
    </div>
    <div class="card">
      <h3>IoU box lỗi ↔ polygon tấm pin</h3>
      <p style="color:var(--text-2);font-size:15px">Dùng để gán lỗi vào mã tấm. Box lỗi
      (~1,0 × 0,9 m) <strong>nhỏ hơn cả tấm</strong> (~1,9 × 0,9 m), nên trần lý thuyết chỉ
      khoảng <strong>0,5–0,8</strong>.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Trung vị đo được</span>
        <span class="n">0,687</span><span class="d">gần trần — box lỗi nằm gọn trong tấm</span></div>
    </div>
  </div>
  <div class="note warn" style="margin-top:20px"><strong>Đừng so hai con số này với nhau.</strong>
  Thấy 0,687 rồi kêu “IoU thấp” là nhầm — nó đã gần kịch trần của phép đo thứ hai rồi.</div>
""")

# 7 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Chỉ số tổng hợp</div>
  <h2>mAP@50 và mAP@50-95</h2>
  <div class="grid g2">
    <div class="card">
      <h3>mAP@50</h3>
      <p style="color:var(--text-2);font-size:15px">Tính precision trung bình trên toàn dải
      ngưỡng conf, với quy ước “trúng” = IoU ≥ 0,50; rồi lấy trung bình các lớp.
      <strong>Không phụ thuộc ngưỡng conf</strong> — nên đây là con số dùng để so model với model.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Tập test độc lập</span>
        <span class="n">0,965</span></div>
    </div>
    <div class="card">
      <h3>mAP@50-95</h3>
      <p style="color:var(--text-2);font-size:15px">Trung bình của mAP tại 10 ngưỡng IoU
      từ 0,50 tới 0,95. Khắt khe hơn nhiều: nó chấm cả <strong>độ khít của box</strong>,
      không chỉ “có tìm ra hay không”.</p>
      <div class="stat" style="margin-top:12px"><span class="k">Tập test độc lập</span>
        <span class="n">0,955</span><span class="d">sát mAP@50 → box vẽ rất khít nhãn</span></div>
    </div>
  </div>
  <div class="note" style="margin-top:20px"><strong>Vì sao độ khít của box quan trọng ở đây
  hơn ở bài toán khác:</strong> box lệch bao nhiêu pixel thì toạ độ GPS lệch bấy nhiêu. Với
  ảnh nhiệt ~2,9 cm/px, box lệch 10 px là toạ độ sai gần 30 cm — chạm ngưỡng nghiệm thu.</div>
""")

# 8 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Cách đọc kết quả chi tiết</div>
  <h2>Ma trận nhầm lẫn — <em>hàng cuối là chỗ quan trọng nhất</em></h2>
  <p class="sub">Cột = nhãn thật, hàng = model đoán. Đường chéo là đoán đúng. Hàng
  <code>background</code> là <strong>lỗi thật mà không box nào chạm tới</strong> — tức bỏ sót.</p>
  <div class="tbl-wrap">
    <table>
      <tr><th>đoán \\ thật</th><th class="num">SingleHotSpot</th><th class="num">MultiHotSpot</th>
        <th class="num">Bypass</th><th class="num">background</th></tr>
      <tr><td>SingleHotSpot</td><td class="num"><strong>163</strong></td><td class="num">9</td>
        <td class="num">0</td><td class="num">—</td></tr>
      <tr><td>MultiHotSpot</td><td class="num">4</td><td class="num"><strong>60</strong></td>
        <td class="num">0</td><td class="num">—</td></tr>
      <tr><td>Bypass</td><td class="num">0</td><td class="num">0</td>
        <td class="num"><strong>37</strong></td><td class="num">—</td></tr>
      <tr><td><strong>background</strong> <span class="pill mid">bỏ sót</span></td>
        <td class="num">6</td><td class="num">1</td><td class="num">0</td><td class="num">—</td></tr>
    </table>
  </div>
  <div class="grid g3" style="margin-top:20px">
    <div class="stat"><span class="k">Bắt được</span><span class="n good">273/280</span>
      <span class="d">97,5 %</span></div>
    <div class="stat"><span class="k">Đúng cả tên lớp</span><span class="n">260/280</span>
      <span class="d">92,9 %</span></div>
    <div class="stat"><span class="k">Nhầm lớp</span><span class="n steel">13</span>
      <span class="d">tất cả đều Single ↔ Multi</span></div>
  </div>
  <div class="note warn" style="margin-top:18px"><strong>Bẫy ngưỡng lần nữa:</strong> chạy
  <code>model.val()</code> để mặc định là <code>conf=0.001</code>, ma trận sẽ ra bức tranh
  hoàn toàn khác — 1900 box, 0 bỏ sót, nhưng <strong>1620 báo động giả</strong>. Đọc ma trận
  mà không kiểm ngưỡng thì kết luận sai.</div>
""")

# 9 ---------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Kiểu box</div>
  <h2>OBB và AABB</h2>
  <div class="grid g2">
    <div class="card hot">
      <h3>OBB — hộp xoay được</h3>
      <p style="color:var(--text-2);font-size:15px">Lưu 4 đỉnh. Dãy tấm pin nằm chéo so với
      khung ảnh, nên hộp xoay <strong>bám sát tấm</strong>, ít nuốt nền.
      Model của dự án dùng loại này (<code>YOLO26s-OBB</code>).</p>
    </div>
    <div class="card">
      <h3>AABB — hộp thẳng trục</h3>
      <p style="color:var(--text-2);font-size:15px">Lưu 2 góc. Với vật nằm chéo thì hộp
      <strong>phình ra</strong>, ôm cả nền xung quanh. Model mượn 8 lớp chỉ có loại này.</p>
    </div>
  </div>
  <div class="note" style="margin-top:20px"><strong>Hệ quả khi so hai model:</strong> AABB nới
  IoU lên một chút nên dễ được tính là “trúng” hơn. Muốn so công bằng thì phải quy cả hai về
  cùng một kiểu — đó là lý do phép so ở mục 2.7 báo cáo hạ OBB xuống thành hộp bao ngoài
  trước khi ghép.</div>
""")

# 10 --------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Chia dữ liệu</div>
  <h2>Chia theo <em>nhóm chuyến bay</em>, không chia ngẫu nhiên</h2>
  <p class="sub">Khung ảnh drone liên tiếp chồng lấn nhau rất nhiều. Chia ngẫu nhiên từng ảnh
  thì <strong>cùng một tấm pin vật lý nằm ở cả tập train lẫn tập val</strong> — model đã nhìn
  thấy đáp án.</p>
  <div class="tbl-wrap">
    <table>
      <tr><th>Cách chia</th><th class="num">mAP@50</th><th>Dùng được để báo cáo?</th></tr>
      <tr><td>Chia ngẫu nhiên từng ảnh</td><td class="num">0,9704</td>
        <td><span class="pill no">không</span> điểm cao giả</td></tr>
      <tr><td>Chia theo nhóm chuyến bay — val</td><td class="num">0,9658</td>
        <td><span class="pill ok">được</span></td></tr>
      <tr><td>Chia theo nhóm chuyến bay — <strong>test</strong></td><td class="num"><strong>0,9654</strong></td>
        <td><span class="pill ok">được</span> chưa dùng khi train lẫn chọn epoch</td></tr>
    </table>
  </div>
  <div class="note" style="margin-top:20px">Ba con số sát nhau nên ở đây chênh lệch không lớn —
  nhưng đó là <strong>may</strong>, không phải luật. Vẫn phải báo bằng số của tập test chia
  theo nhóm. Ba khái niệm: <strong>train</strong> để học, <strong>val</strong> để chọn epoch,
  <strong>test</strong> chưa từng đụng tới — dùng đúng một lần lúc báo cáo.</div>
""")

# 11 --------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Chỉ số của phần định vị</div>
  <h2>RMSE, trung vị, P90 — <em>vì sao phải báo cả ba</em></h2>
  <div class="grid g3">
    <div class="card">
      <h3>Trung vị</h3>
      <p style="color:var(--text-2);font-size:15px">Nửa số ca tốt hơn, nửa tệ hơn. Không bị
      vài ca cá biệt kéo lệch. Cho biết <em>ngày thường trông thế nào</em>.</p>
    </div>
    <div class="card">
      <h3>RMSE</h3>
      <p style="color:var(--text-2);font-size:15px">Căn của trung bình bình phương sai lệch.
      Bình phương nên <strong>phạt nặng ca lệch lớn</strong>. Luôn ≥ trung bình.</p>
    </div>
    <div class="card hot">
      <h3>P90</h3>
      <p style="color:var(--text-2);font-size:15px">90 % số ca tốt hơn mức này. Cho biết
      <em>ca xấu thì xấu tới đâu</em> — thứ mà trung vị giấu đi.</p>
    </div>
  </div>
  <div class="tbl-wrap" style="margin-top:20px">
    <table>
      <tr><th>Phép đo</th><th class="num">Trung vị</th><th class="num">RMSE</th>
        <th class="num">P90</th><th>Đo cái gì</th></tr>
      <tr><td>Trên orthophoto đã ghép</td><td class="num">2,69 cm</td>
        <td class="num"><strong>2,56 cm</strong></td><td class="num">—</td>
        <td>sản phẩm cuối, sai số đã được trung bình hoá</td></tr>
      <tr><td>Trên từng ảnh lẻ (598 ảnh)</td><td class="num">14,1 cm</td><td class="num">—</td>
        <td class="num">24,6 cm</td><td>lệch giữa hai cảm biến một lần bấm máy</td></tr>
    </table>
  </div>
  <div class="note" style="margin-top:18px"><strong>Hai con số chênh nhau 5 lần nhưng đều
  đúng</strong> — chúng đo hai thứ khác nhau. Mỗi pixel ortho lấy từ nhiều ảnh chồng phủ nên
  sai số từng ảnh bị trung bình hoá đi. Ngưỡng nghiệm thu 30 cm xét sản phẩm ortho.</div>
""")

# 12 --------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Thuật ngữ trắc địa</div>
  <h2>Sáu chữ hay gặp trong chuỗi định vị</h2>
  <div class="grid g2">
    <div class="card">
      <h3>Ma trận H (homography)</h3>
      <p style="color:var(--text-2);font-size:15px">Phép biến đổi 3×3 đưa toạ độ <strong>ảnh
      nhiệt → ảnh RGB</strong>. Gắn với <strong>thiết bị</strong>, không gắn với trang trại —
      chấm tay một lần cho mỗi model drone. Đo được RMSE 4,38 px, so với 22,34 px của H nhà
      sản xuất.</p>
    </div>
    <div class="card">
      <h3>GSD — kích thước một pixel ngoài thực địa</h3>
      <p style="color:var(--text-2);font-size:15px">Ảnh nhiệt ở độ cao 31 m: <strong>~2,9
      cm/px</strong>. Ortho màu: <strong>0,96 cm/px</strong>. Ortho nhiệt dựng theo GSD của
      ảnh nhiệt, không phóng to vô ích.</p>
    </div>
    <div class="card">
      <h3>Orthophoto</h3>
      <p style="color:var(--text-2);font-size:15px">Ảnh đã nắn cho mọi điểm nhìn thẳng từ trên
      xuống, ghép từ hàng trăm ảnh. Đo khoảng cách trên đó ra mét thật.</p>
    </div>
    <div class="card">
      <h3>DSM — mô hình độ cao bề mặt</h3>
      <p style="color:var(--text-2);font-size:15px">Lưới cao độ của mặt đất <em>kể cả vật thể
      trên đó</em>. Cần để biết tia từ camera chạm đất ở đâu — tấm pin cao hơn mặt đất nên
      không có DSM là lệch.</p>
    </div>
    <div class="card">
      <h3>Off-nadir</h3>
      <p style="color:var(--text-2);font-size:15px">Góc lệch khỏi phương thẳng đứng. Một điểm
      nằm trong nhiều ảnh; ảnh <strong>đúng</strong> để chiếu là ảnh có off-nadir nhỏ nhất —
      xê dịch do độ cao tấm pin là ít nhất.</p>
    </div>
    <div class="card">
      <h3>Ironbow</h3>
      <p style="color:var(--text-2);font-size:15px">Bảng màu tím→cam→vàng quen thuộc của ảnh
      nhiệt. Quan trọng khi dùng model ngoài: model mượn 8 lớp học trên <strong>ảnh xám</strong>,
      đưa Ironbow vào thì bắt được 4/280 thay vì 128/280.</p>
    </div>
  </div>
""")

# 13 --------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Bảng lớp</div>
  <h2>Bốn loại lỗi — <em>và cặp luôn lẫn nhau</em></h2>
  <div class="tbl-wrap">
    <table>
      <tr><th>Lớp</th><th>Là gì</th><th class="num">Số mẫu test</th><th class="num">Bắt được</th>
        <th class="num">Đúng lớp</th></tr>
      <tr><td><strong>SingleHotSpot</strong></td><td>một điểm nóng trên tấm</td>
        <td class="num">173</td><td class="num">167</td><td class="num">163</td></tr>
      <tr><td><strong>MultiHotSpot</strong></td><td>từ hai điểm nóng trở lên</td>
        <td class="num">70</td><td class="num">69</td><td class="num">60</td></tr>
      <tr><td><strong>Bypass</strong></td><td>diode bypass ăn — cả dải tấm nóng thành vệt dài</td>
        <td class="num">37</td><td class="num">37</td><td class="num">37</td></tr>
      <tr><td><strong>ModuleOpenCircuit</strong></td><td>tấm đứt mạch — nguội hơn xung quanh</td>
        <td class="num">0</td><td class="num">—</td><td class="num">—</td></tr>
    </table>
  </div>
  <div class="grid g2" style="margin-top:20px">
    <div class="note warn"><strong>Single ↔ Multi lẫn nhau là chuyện định nghĩa nhãn,
    không phải model kém.</strong> Ranh giới “một hay từ hai điểm nóng” thì chính người gán
    nhãn cũng không nhất quán, và IEC xếp chúng làm một loại. Toàn bộ 13 ca nhầm lớp nằm ở
    cặp này. Gộp thành một lớp <code>HotSpot</code> thì tỉ lệ đúng lớp lên 97,5 % mà không
    phải train lại.</div>
    <div class="note"><strong>ModuleOpenCircuit chưa đánh giá được:</strong> tập test lẫn val
    chia theo nhóm đều không có mẫu nào. Model có học lớp này nhưng độ tin cậy chưa biết —
    nó đoán ra loại này thì phải tự kiểm lại.</div>
  </div>
""")

# 14 --------------------------------------------------------------------------
slide("""
  <div class="eyebrow">Tra nhanh</div>
  <h2>Một bảng để cạnh khi đọc báo cáo</h2>
  <div class="tbl-wrap">
    <table>
      <tr><th>Thông số</th><th>Đọc là</th><th class="num">Dự án này</th></tr>
      <tr><td>Recall</td><td>bắt được bao nhiêu phần lỗi thật</td><td class="num">0,959 <span class="mono">@conf 0,25</span></td></tr>
      <tr><td>Precision</td><td>báo ra thì đúng bao nhiêu phần</td><td class="num">0,875 <span class="mono">@conf 0,25</span></td></tr>
      <tr><td>F1 / F2</td><td>cách gộp P và R theo giá phải trả</td><td class="num">F1 0,911 · đỉnh ở conf 0,64</td></tr>
      <tr><td>mAP@50</td><td>điểm tổng hợp, không phụ thuộc ngưỡng</td><td class="num">0,965</td></tr>
      <tr><td>mAP@50-95</td><td>như trên, cộng chấm độ khít box</td><td class="num">0,955</td></tr>
      <tr><td>IoU (dự đoán ↔ nhãn)</td><td>box có trùng nhãn không, trần 1,0</td><td class="num">chặt tới IoU 0,80</td></tr>
      <tr><td>IoU (lỗi ↔ tấm pin)</td><td>gán lỗi vào tấm, trần ~0,5–0,8</td><td class="num">0,687 trung vị</td></tr>
      <tr><td>RMSE định vị</td><td>sai lệch thực địa, phạt nặng ca xấu</td><td class="num">2,56 cm</td></tr>
      <tr><td>P90</td><td>ca xấu thì xấu tới đâu</td><td class="num">24,6 cm <span class="mono">ảnh lẻ</span></td></tr>
      <tr><td>conf</td><td>ngưỡng nhận box — <strong>luôn phải nói kèm</strong></td><td class="num"><strong>0,25</strong> cố định</td></tr>
    </table>
  </div>
  <div class="note" style="margin-top:20px"><strong>Một câu nếu chỉ nhớ được một câu:</strong>
  precision và recall <em>không có giá trị cố định</em> — chúng là một đường cong theo ngưỡng
  conf. Nói con số mà không nói ngưỡng là chưa nói gì cả.</div>
""")

than = "\n".join(
    '<section class="slide"><div class="wrap">%s</div></section>' % s for s in S)

html = """%s

<div class="rail"></div>
<div class="hud">
  <button id="prev" aria-label="Slide trước">◀</button>
  <span><b id="cur">1</b> / %d</span>
  <button id="next" aria-label="Slide sau">▶</button>
</div>

<div class="deck" id="deck">
%s
</div>

%s""" % (dau, len(S), than, cuoi)

open(RA, "w", encoding="utf-8").write(html)
print("Da tao %s — %d slide, %.0f KB" % (os.path.basename(RA), len(S),
                                         os.path.getsize(RA) / 1024))
