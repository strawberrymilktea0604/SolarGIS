#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hình vẽ SVG minh hoạ các định nghĩa — dùng cho tài liệu pipeline.

Vẽ tay bằng SVG chứ không lấy ảnh minh hoạ trên mạng, vì ba lý do: số liệu trên
hình là số THẬT của dự án này; màu lấy từ biến CSS nên nền sáng/tối đều đọc được;
và không vướng bản quyền.

Mọi hình dùng biến màu của _slide_mau.html: --ember (cam), --steel (xanh thép),
--good, --bad, --text, --text-2, --text-3, --line, --surface, --surface-2.
"""

# Bảng nhãn dùng lại nhiều lần
_F = 'font-family="var(--font-body),system-ui,sans-serif"'
_M = 'font-family="var(--font-mono),monospace"'


HINH = {}


def _hop_tam(x, y, w, ten, phu):
    """Hộp nhỏ có nhãn chính + nhãn phụ, dùng cho chuỗi bước ngang."""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="46" rx="6" fill="var(--surface)" '
            f'stroke="var(--ember)" stroke-width="1.6"/>'
            f'<text x="{x+w/2}" y="{y+20}" {_M} font-size="11.5" fill="var(--text)" '
            f'text-anchor="middle" font-weight="600">{ten}</text>'
            f'<text x="{x+w/2}" y="{y+36}" {_F} font-size="10" fill="var(--text-3)" '
            f'text-anchor="middle">{phu}</text>')


def _mui_ngang(x1, y, x2, mau="var(--ember)"):
    """Mũi tên nằm ngang."""
    return (f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{mau}" stroke-width="1.6"/>'
            f'<path d="M{x2-7},{y-4} L{x2},{y} L{x2-7},{y+4}" fill="{mau}"/>')

# --------------------------------------------------------------- precision/recall
HINH["precision_recall"] = f'''
<svg viewBox="0 0 760 300" role="img" aria-label="Sơ đồ TP, FP, FN và công thức precision, recall">
  <defs>
    <clipPath id="cThat"><circle cx="300" cy="150" r="112"/></clipPath>
  </defs>
  <circle cx="300" cy="150" r="112" fill="var(--steel)" opacity=".13"/>
  <circle cx="410" cy="150" r="112" fill="var(--ember)" opacity=".13"/>
  <circle cx="410" cy="150" r="112" fill="var(--ember)" opacity=".16" clip-path="url(#cThat)"/>
  <circle cx="300" cy="150" r="112" fill="none" stroke="var(--steel)" stroke-width="2"/>
  <circle cx="410" cy="150" r="112" fill="none" stroke="var(--ember)" stroke-width="2"/>

  <text x="228" y="46" {_F} font-size="14" fill="var(--steel)" text-anchor="middle">LỖI THẬT</text>
  <text x="228" y="64" {_F} font-size="11.5" fill="var(--text-3)" text-anchor="middle">có ngoài thực địa</text>
  <text x="486" y="46" {_F} font-size="14" fill="var(--ember)" text-anchor="middle">MODEL BÁO</text>
  <text x="486" y="64" {_F} font-size="11.5" fill="var(--text-3)" text-anchor="middle">box vẽ ra</text>

  <text x="243" y="150" {_F} font-size="19" font-weight="600" fill="var(--text)" text-anchor="middle">FN</text>
  <text x="243" y="172" {_F} font-size="11.5" fill="var(--text-2)" text-anchor="middle">bỏ sót</text>
  <text x="243" y="189" {_M} font-size="12" fill="var(--bad)" text-anchor="middle">7</text>

  <text x="355" y="150" {_F} font-size="19" font-weight="600" fill="var(--text)" text-anchor="middle">TP</text>
  <text x="355" y="172" {_F} font-size="11.5" fill="var(--text-2)" text-anchor="middle">bắt trúng</text>
  <text x="355" y="189" {_M} font-size="12" fill="var(--good)" text-anchor="middle">273</text>

  <text x="467" y="150" {_F} font-size="19" font-weight="600" fill="var(--text)" text-anchor="middle">FP</text>
  <text x="467" y="172" {_F} font-size="11.5" fill="var(--text-2)" text-anchor="middle">báo nhầm</text>
  <text x="467" y="189" {_M} font-size="12" fill="var(--bad)" text-anchor="middle">70</text>

  <line x1="300" y1="268" x2="300" y2="284" stroke="var(--steel)" stroke-width="1.5"/>
  <line x1="188" y1="284" x2="412" y2="284" stroke="var(--steel)" stroke-width="1.5"/>
  <text x="300" y="299" {_M} font-size="11.5" fill="var(--steel)" text-anchor="middle">mẫu số của RECALL = 280 lỗi thật</text>

  <line x1="410" y1="22" x2="410" y2="38" stroke="var(--ember)" stroke-width="1.5"/>
  <line x1="298" y1="22" x2="522" y2="22" stroke="var(--ember)" stroke-width="1.5"/>
  <text x="410" y="16" {_M} font-size="11.5" fill="var(--ember)" text-anchor="middle">mẫu số của PRECISION = 343 box vẽ ra</text>

  <text x="600" y="120" {_M} font-size="13.5" fill="var(--text-2)">Recall    = TP/(TP+FN)</text>
  <text x="600" y="141" {_M} font-size="13.5" fill="var(--steel)">          = 273/280 = 0,975</text>
  <text x="600" y="176" {_M} font-size="13.5" fill="var(--text-2)">Precision = TP/(TP+FP)</text>
  <text x="600" y="197" {_M} font-size="13.5" fill="var(--ember)">          = 273/343 = 0,796</text>
  <text x="600" y="232" {_F} font-size="11.5" fill="var(--text-3)">conf 0,25 · tập test 91 ảnh</text>
</svg>'''

# --------------------------------------------------------------------------- IoU
HINH["iou"] = f'''
<svg viewBox="0 0 760 300" role="img" aria-label="IoU: giao trên hợp, và hai loại IoU trong dự án">
  <text x="20" y="24" {_F} font-size="13" font-weight="600" fill="var(--text)">IoU = diện tích GIAO / diện tích HỢP</text>

  <rect x="30" y="52" width="150" height="96" fill="var(--steel)" opacity=".16"
        stroke="var(--steel)" stroke-width="2"/>
  <rect x="110" y="86" width="150" height="96" fill="var(--ember)" opacity=".16"
        stroke="var(--ember)" stroke-width="2"/>
  <rect x="110" y="86" width="70" height="62" fill="var(--good)" opacity=".38"/>
  <text x="60" y="46" {_M} font-size="11" fill="var(--steel)">nhãn</text>
  <text x="238" y="196" {_M} font-size="11" fill="var(--ember)">dự đoán</text>
  <text x="145" y="122" {_M} font-size="11" fill="var(--text)" text-anchor="middle">giao</text>

  <text x="30" y="216" {_M} font-size="12.5" fill="var(--text-2)">IoU = 0 (rời) … 1 (trùng khít)</text>
  <text x="30" y="238" {_M} font-size="12.5" fill="var(--text-3)">quy ước "bắt trúng": IoU ≥ 0,50</text>

  <line x1="320" y1="30" x2="320" y2="285" stroke="var(--line)" stroke-width="1"/>

  <text x="352" y="24" {_F} font-size="13" font-weight="600" fill="var(--bad)">Hai loại IoU khác hẳn nhau — đừng so với nhau</text>

  <text x="352" y="56" {_M} font-size="11.5" fill="var(--text-3)">① dự đoán ↔ nhãn</text>
  <rect x="352" y="66" width="120" height="58" fill="var(--steel)" opacity=".14"
        stroke="var(--steel)" stroke-width="1.8"/>
  <rect x="360" y="72" width="120" height="58" fill="var(--ember)" opacity=".14"
        stroke="var(--ember)" stroke-width="1.8" stroke-dasharray="5 3"/>
  <text x="500" y="88" {_F} font-size="12" fill="var(--text-2)">hai hình CÙNG CỠ</text>
  <text x="500" y="107" {_F} font-size="12" fill="var(--text-2)">→ trần lý thuyết</text>
  <text x="500" y="126" {_M} font-size="14" font-weight="600" fill="var(--good)">1,00</text>

  <text x="352" y="176" {_M} font-size="11.5" fill="var(--text-3)">② box lỗi ↔ polygon tấm pin</text>
  <rect x="352" y="186" width="150" height="60" fill="var(--steel)" opacity=".12"
        stroke="var(--steel)" stroke-width="1.8"/>
  <rect x="366" y="196" width="78" height="40" fill="var(--ember)" opacity=".22"
        stroke="var(--ember)" stroke-width="1.8"/>
  <text x="530" y="200" {_F} font-size="12" fill="var(--text-2)">box lỗi NHỎ HƠN cả tấm</text>
  <text x="530" y="219" {_F} font-size="12" fill="var(--text-2)">→ trần lý thuyết chỉ</text>
  <text x="530" y="238" {_M} font-size="14" font-weight="600" fill="var(--flare)">0,5 – 0,8</text>
  <text x="352" y="272" {_M} font-size="12" fill="var(--text-2)">Dự án đo được trung vị 0,687 — tức đã GẦN KỊCH TRẦN của loại ②.</text>
</svg>'''

# --------------------------------------------------------------- ngưỡng conf
HINH["nguong_conf"] = f'''
<svg viewBox="0 0 760 330" role="img" aria-label="Precision và recall đổi ngược nhau theo ngưỡng conf">
  <line x1="70" y1="270" x2="700" y2="270" stroke="var(--line)" stroke-width="1.5"/>
  <line x1="70" y1="40" x2="70" y2="270" stroke="var(--line)" stroke-width="1.5"/>
  <text x="385" y="300" {_F} font-size="12.5" fill="var(--text-3)" text-anchor="middle">ngưỡng conf →</text>
  <text x="24" y="155" {_F} font-size="12.5" fill="var(--text-3)" transform="rotate(-90 24 155)" text-anchor="middle">giá trị</text>

  <!-- recall: cao roi giam -->
  <path d="M70,48 C200,52 300,66 420,96 C520,122 610,158 700,206"
        fill="none" stroke="var(--steel)" stroke-width="2.6"/>
  <!-- precision: thap roi tang -->
  <path d="M70,222 C180,168 280,140 420,116 C520,100 610,88 700,74"
        fill="none" stroke="var(--ember)" stroke-width="2.6"/>

  <text x="710" y="210" {_M} font-size="12" fill="var(--steel)">Recall</text>
  <text x="710" y="78" {_M} font-size="12" fill="var(--ember)">Precision</text>

  <!-- diem 0,25 -->
  <line x1="228" y1="40" x2="228" y2="270" stroke="var(--good)" stroke-width="1.6" stroke-dasharray="5 4"/>
  <circle cx="228" cy="60" r="4.5" fill="var(--steel)"/>
  <circle cx="228" cy="152" r="4.5" fill="var(--ember)"/>
  <text x="228" y="288" {_M} font-size="12" fill="var(--good)" text-anchor="middle">0,25</text>
  <text x="238" y="56" {_M} font-size="11.5" fill="var(--steel)">0,959</text>
  <text x="238" y="168" {_M} font-size="11.5" fill="var(--ember)">0,875</text>
  <text x="150" y="32" {_F} font-size="11.5" font-weight="600" fill="var(--good)">ĐANG DÙNG</text>

  <!-- diem F1 -->
  <line x1="536" y1="40" x2="536" y2="270" stroke="var(--bad)" stroke-width="1.4" stroke-dasharray="4 4"/>
  <circle cx="536" cy="128" r="4.5" fill="var(--steel)"/>
  <circle cx="536" cy="96" r="4.5" fill="var(--ember)"/>
  <text x="536" y="288" {_M} font-size="12" fill="var(--bad)" text-anchor="middle">0,64</text>
  <text x="548" y="126" {_M} font-size="11.5" fill="var(--steel)">0,906</text>
  <text x="548" y="92" {_M} font-size="11.5" fill="var(--ember)">0,940</text>
  <text x="470" y="32" {_F} font-size="11.5" font-weight="600" fill="var(--bad)">đỉnh F1 — KHÔNG dùng</text>

  <text x="70" y="322" {_F} font-size="12" fill="var(--text-2)">Nâng ngưỡng lên 0,64 thì precision +6,5 điểm nhưng
  <tspan font-weight="600" fill="var(--bad)">mất 98/211 lỗi</tspan> — trong đó 84 cái rơi ĐÚNG trong tấm pin.</text>
</svg>'''

# --------------------------------------------------------------------- thị sai
HINH["thi_sai"] = f'''
<svg viewBox="0 0 760 340" role="img" aria-label="Vì sao một ma trận H dùng được cho cả ảnh">
  <rect x="318" y="26" width="120" height="30" rx="6" fill="var(--surface-2)"
        stroke="var(--line)" stroke-width="1.5"/>
  <circle cx="348" cy="41" r="6" fill="var(--steel)"/>
  <circle cx="408" cy="41" r="6" fill="var(--ember)"/>
  <text x="348" y="20" {_M} font-size="10.5" fill="var(--steel)" text-anchor="middle">RGB</text>
  <text x="408" y="20" {_M} font-size="10.5" fill="var(--ember)" text-anchor="middle">nhiệt</text>
  <text x="452" y="45" {_M} font-size="11.5" fill="var(--text-3)">hai ống kính cách nhau ~3 cm</text>

  <line x1="348" y1="47" x2="300" y2="252" stroke="var(--steel)" stroke-width="1.4" opacity=".75"/>
  <line x1="408" y1="47" x2="300" y2="252" stroke="var(--ember)" stroke-width="1.4" opacity=".75"/>
  <line x1="348" y1="47" x2="470" y2="252" stroke="var(--steel)" stroke-width="1.4" opacity=".45"/>
  <line x1="408" y1="47" x2="470" y2="252" stroke="var(--ember)" stroke-width="1.4" opacity=".45"/>

  <line x1="120" y1="46" x2="120" y2="254" stroke="var(--text-3)" stroke-width="1"/>
  <path d="M116,50 L120,42 L124,50" fill="var(--text-3)"/>
  <path d="M116,250 L120,258 L124,250" fill="var(--text-3)"/>
  <text x="112" y="160" {_M} font-size="12" fill="var(--text-2)" text-anchor="end">31 m</text>

  <rect x="200" y="252" width="380" height="14" fill="var(--surface-2)" stroke="var(--line)"/>
  <rect x="258" y="240" width="90" height="12" fill="var(--steel)" opacity=".3" stroke="var(--steel)"/>
  <rect x="392" y="243" width="90" height="9" fill="var(--steel)" opacity=".3" stroke="var(--steel)"/>
  <text x="590" y="262" {_M} font-size="11" fill="var(--text-3)">mặt đất + tấm pin</text>
  <text x="590" y="278" {_M} font-size="11" fill="var(--text-3)">chênh cao ~1 m</text>

  <rect x="60" y="292" width="640" height="40" rx="8" fill="var(--surface-2)" stroke="var(--line)"/>
  <text x="76" y="309" {_M} font-size="12.5" fill="var(--text-2)">lệch do thị sai = b·ΔZ / Z = 0,03 × 1 / 31 ≈ <tspan fill="var(--good)" font-weight="600">1 mm</tspan>
  = 0,03 px ảnh nhiệt</text>
  <text x="76" y="326" {_F} font-size="12" fill="var(--text-3)">Nhỏ hơn một pixel 30 lần → với hai cảm biến này, cả nhà máy coi như MỘT MẶT PHẲNG.
  Mà cảnh phẳng thì một ma trận 3×3 là đúng chính xác.</text>
</svg>'''

# ------------------------------------------------------------------- trễ chụp
HINH["tre_chup"] = f'''
<svg viewBox="0 0 760 250" role="img" aria-label="Trễ bấm máy giữa hai cảm biến gây lệch 15 cm">
  <line x1="60" y1="70" x2="700" y2="70" stroke="var(--line)" stroke-width="1.5"/>
  <text x="60" y="42" {_F} font-size="12.5" fill="var(--text-3)">drone bay 5 m/s →</text>

  <circle cx="250" cy="70" r="9" fill="var(--steel)"/>
  <text x="250" y="52" {_M} font-size="11.5" fill="var(--steel)" text-anchor="middle">RGB bấm</text>
  <circle cx="400" cy="70" r="9" fill="var(--ember)"/>
  <text x="400" y="52" {_M} font-size="11.5" fill="var(--ember)" text-anchor="middle">nhiệt bấm</text>

  <line x1="250" y1="92" x2="400" y2="92" stroke="var(--flare)" stroke-width="1.6"/>
  <line x1="250" y1="86" x2="250" y2="98" stroke="var(--flare)" stroke-width="1.6"/>
  <line x1="400" y1="86" x2="400" y2="98" stroke="var(--flare)" stroke-width="1.6"/>
  <text x="325" y="112" {_M} font-size="12" fill="var(--flare)" text-anchor="middle">~30 ms</text>

  <rect x="60" y="140" width="640" height="46" rx="8" fill="var(--surface-2)" stroke="var(--line)"/>
  <text x="76" y="163" {_M} font-size="13" fill="var(--text-2)">5 m/s × 30 ms = <tspan fill="var(--ember)" font-weight="600">15 cm</tspan>
  — khớp gần khít trung vị đo được <tspan fill="var(--ember)" font-weight="600">14,1 cm</tspan></text>
  <text x="76" y="180" {_F} font-size="12" fill="var(--text-3)">Lớn gấp 150 lần thị sai. Đây mới là nguồn sai số thật, không phải khoảng cách hai ống kính.</text>

  <text x="60" y="216" {_F} font-size="12.5" fill="var(--text-2)">Vì lệch đổi hướng tuỳ ảnh (15 vùng lệch lên / 16 lệch xuống) nên
  <tspan font-weight="600" fill="var(--bad)">bù bằng một hằng số thì hỏng</tspan>,</text>
  <text x="60" y="236" {_F} font-size="12.5" fill="var(--text-2)">còn <tspan font-weight="600" fill="var(--good)">bù riêng từng ảnh</tspan>
  thì sai số ortho giảm 14,1 → 4,3 cm.</text>
</svg>'''

# ------------------------------------------------------------------ OBB / AABB
HINH["obb_aabb"] = f'''
<svg viewBox="0 0 760 240" role="img" aria-label="Hộp xoay OBB so với hộp thẳng trục AABB">
  <g transform="translate(60,30)">
    <rect x="20" y="40" width="180" height="80" transform="rotate(-18 110 80)"
          fill="var(--steel)" opacity=".2" stroke="var(--steel)" stroke-width="1.5"/>
    <rect x="20" y="40" width="180" height="80" transform="rotate(-18 110 80)"
          fill="none" stroke="var(--good)" stroke-width="2.6"/>
    <text x="110" y="16" {_F} font-size="13.5" font-weight="600" fill="var(--good)" text-anchor="middle">OBB — hộp xoay</text>
    <text x="110" y="168" {_M} font-size="11.5" fill="var(--text-2)" text-anchor="middle">4 đỉnh · bám sát tấm</text>
    <text x="110" y="186" {_M} font-size="11.5" fill="var(--text-3)" text-anchor="middle">model của dự án</text>
  </g>
  <g transform="translate(430,30)">
    <rect x="20" y="40" width="180" height="80" transform="rotate(-18 110 80)"
          fill="var(--steel)" opacity=".2" stroke="var(--steel)" stroke-width="1.5"/>
    <rect x="4" y="17" width="212" height="126"
          fill="var(--ember)" opacity=".1" stroke="var(--ember)" stroke-width="2.6"/>
    <text x="110" y="16" {_F} font-size="13.5" font-weight="600" fill="var(--ember)" text-anchor="middle">AABB — hộp thẳng trục</text>
    <text x="110" y="168" {_M} font-size="11.5" fill="var(--text-2)" text-anchor="middle">2 góc · phình ra, ôm cả nền</text>
    <text x="110" y="186" {_M} font-size="11.5" fill="var(--text-3)" text-anchor="middle">model mượn 8 lớp</text>
  </g>
  <text x="380" y="228" {_F} font-size="12" fill="var(--text-3)" text-anchor="middle">Dãy pin nằm chéo so với khung ảnh, nên khác biệt này rất đáng kể.
  So hai model phải quy về cùng một kiểu hộp.</text>
</svg>'''

# -------------------------------------------------------- RMSE / trung vị / P90
HINH["rmse_p90"] = f'''
<svg viewBox="0 0 760 280" role="img" aria-label="Trung vị, RMSE và P90 trên phân bố sai số">
  <line x1="60" y1="210" x2="700" y2="210" stroke="var(--line)" stroke-width="1.5"/>
  <path d="M60,210 C130,208 160,120 210,96 C260,72 300,120 350,148 C410,180 470,196 540,203
           C600,208 650,209 700,210 Z" fill="var(--ember)" opacity=".16"/>
  <path d="M60,210 C130,208 160,120 210,96 C260,72 300,120 350,148 C410,180 470,196 540,203
           C600,208 650,209 700,210" fill="none" stroke="var(--ember)" stroke-width="2.2"/>

  <line x1="222" y1="70" x2="222" y2="210" stroke="var(--steel)" stroke-width="2"/>
  <text x="222" y="60" {_M} font-size="12" fill="var(--steel)" text-anchor="middle">trung vị</text>
  <text x="222" y="232" {_M} font-size="12" fill="var(--steel)" text-anchor="middle">14,1 cm</text>
  <text x="222" y="250" {_F} font-size="11" fill="var(--text-3)" text-anchor="middle">ngày thường thế nào</text>

  <line x1="290" y1="110" x2="290" y2="210" stroke="var(--flare)" stroke-width="2"/>
  <text x="298" y="104" {_M} font-size="12" fill="var(--flare)">RMSE</text>
  <text x="298" y="122" {_F} font-size="11" fill="var(--text-3)">phạt nặng ca xấu → luôn ≥ trung bình</text>

  <line x1="470" y1="150" x2="470" y2="210" stroke="var(--bad)" stroke-width="2"/>
  <text x="470" y="142" {_M} font-size="12" fill="var(--bad)" text-anchor="middle">P90</text>
  <text x="470" y="232" {_M} font-size="12" fill="var(--bad)" text-anchor="middle">24,6 cm</text>
  <text x="470" y="250" {_F} font-size="11" fill="var(--text-3)" text-anchor="middle">ca xấu thì xấu tới đâu</text>

  <path d="M540,203 L700,210" fill="none" stroke="var(--bad)" stroke-width="2.4"/>
  <text x="630" y="192" {_F} font-size="11.5" fill="var(--text-3)" text-anchor="middle">cái đuôi mà trung vị giấu đi</text>
  <text x="380" y="272" {_F} font-size="12" fill="var(--text-2)" text-anchor="middle">Phải báo cả ba. Chỉ báo trung vị là giấu đuôi; chỉ báo RMSE là để một ca cá biệt bôi đen cả bộ.</text>
</svg>'''

# ------------------------------------------------------------- chọn ảnh Voronoi
HINH["chon_anh"] = f'''
<svg viewBox="0 0 760 260" role="img" aria-label="Mỗi pixel ortho lấy từ ảnh có tâm chụp gần nhất">
  <rect x="60" y="30" width="280" height="180" fill="var(--surface-2)" stroke="var(--line)"/>
  <path d="M60,140 L200,30 M200,30 L340,150 M60,140 L150,210 M150,210 L340,150"
        stroke="var(--ember)" stroke-width="1.6" fill="none" stroke-dasharray="5 4"/>
  <circle cx="120" cy="90" r="5" fill="var(--ember)"/><text x="120" y="80" {_M} font-size="10" fill="var(--text-3)" text-anchor="middle">A</text>
  <circle cx="265" cy="80" r="5" fill="var(--ember)"/><text x="265" y="70" {_M} font-size="10" fill="var(--text-3)" text-anchor="middle">B</text>
  <circle cx="110" cy="180" r="5" fill="var(--ember)"/><text x="110" y="200" {_M} font-size="10" fill="var(--text-3)" text-anchor="middle">C</text>
  <circle cx="270" cy="185" r="5" fill="var(--ember)"/><text x="270" y="205" {_M} font-size="10" fill="var(--text-3)" text-anchor="middle">D</text>
  <text x="200" y="20" {_F} font-size="12.5" font-weight="600" fill="var(--text)" text-anchor="middle">Chấm = tâm chụp của từng ảnh</text>
  <text x="200" y="234" {_F} font-size="11.5" fill="var(--text-3)" text-anchor="middle">Nét đứt = biên Voronoi, mỗi ô lấy từ một ảnh</text>

  <text x="390" y="60" {_F} font-size="13" font-weight="600" fill="var(--text)">Vì sao chọn ảnh gần tâm nhất</text>
  <text x="390" y="86" {_F} font-size="12.5" fill="var(--text-2)">Một điểm dưới đất nằm trong nhiều ảnh. Ảnh có</text>
  <text x="390" y="105" {_F} font-size="12.5" fill="var(--text-2)">off-nadir nhỏ nhất thì xê dịch do độ cao tấm pin</text>
  <text x="390" y="124" {_F} font-size="12.5" fill="var(--text-2)">là nhỏ nhất — cũng là tiêu chí Metashape dùng.</text>
  <text x="390" y="156" {_F} font-size="12.5" fill="var(--text-2)">Mỗi pixel chỉ tính với MỘT ảnh → nhanh gấp ~16 lần,</text>
  <text x="390" y="175" {_F} font-size="12.5" fill="var(--text-2)">và giữ được giá trị của một lần đo thật.</text>
  <text x="390" y="207" {_F} font-size="12" fill="var(--text-3)">Giá phải trả: biên Voronoi lộ thành viền răng cưa,</text>
  <text x="390" y="225" {_F} font-size="12" fill="var(--text-3)">vì không pha trộn như Metashape.</text>
</svg>'''

# ------------------------------------------- ghép ortho nhiệt: chiều chạy ngược
HINH["ghep_chieu_nguoc"] = f'''
<svg viewBox="0 0 760 330" role="img" aria-label="Ghép ortho nhiệt chạy ngược: từ pixel ortho về ảnh nhiệt">
  <text x="20" y="22" {_F} font-size="13" font-weight="600" fill="var(--bad)">✗ Cách trực giác — DÁN XUÔI</text>
  <rect x="20" y="34" width="330" height="96" rx="6" fill="var(--surface-2)" stroke="var(--bad)" stroke-width="1.5" stroke-dasharray="5 4"/>
  <text x="34" y="56" {_F} font-size="12" fill="var(--text-2)">Lấy từng ảnh nhiệt, warp rồi dán lên ortho.</text>
  <rect x="40" y="68" width="52" height="40" fill="var(--ember)" opacity=".3" stroke="var(--ember)"/>
  <rect x="100" y="74" width="52" height="40" fill="var(--ember)" opacity=".3" stroke="var(--ember)"/>
  <rect x="166" y="66" width="52" height="40" fill="var(--ember)" opacity=".3" stroke="var(--ember)"/>
  <circle cx="160" cy="112" r="7" fill="var(--bad)" opacity=".5"/>
  <circle cx="96" cy="66" r="5" fill="var(--bad)" opacity=".5"/>
  <text x="238" y="86" {_F} font-size="11.5" fill="var(--bad)">Hở lỗ chỗ giữa</text>
  <text x="238" y="102" {_F} font-size="11.5" fill="var(--bad)">các ảnh · chồng mép</text>

  <text x="410" y="22" {_F} font-size="13" font-weight="600" fill="var(--good)">✓ Cách code làm — ĐI NGƯỢC</text>
  <rect x="410" y="34" width="330" height="96" rx="6" fill="var(--surface-2)" stroke="var(--good)" stroke-width="1.5"/>
  <text x="424" y="56" {_F} font-size="12" fill="var(--text-2)">Duyệt từng ô của lưới ortho, đi TÌM giá trị.</text>
  <g stroke="var(--good)" stroke-width="1" opacity=".55" fill="none">
    <path d="M430,68 h280 M430,84 h280 M430,100 h280 M430,116 h280"/>
    <path d="M430,68 v48 M478,68 v48 M526,68 v48 M574,68 v48 M622,68 v48 M670,68 v48 M710,68 v48"/>
  </g>
  <rect x="526" y="84" width="48" height="16" fill="var(--good)" opacity=".45"/>
  <text x="424" y="126" {_F} font-size="11" fill="var(--good)">Mỗi ô điền đúng một lần → không hở</text>

  <text x="20" y="160" {_F} font-size="13" font-weight="600" fill="var(--text)">Một ô ortho đi tìm giá trị của nó — 5 chặng</text>
  {_hop_tam(20, 174, 128, "① ô ortho", "hàng, cột")}
  {_mui_ngang(150, 197, 176)}
  {_hop_tam(178, 174, 128, "② lon / lat", "transform ortho")}
  {_mui_ngang(308, 197, 334)}
  {_hop_tam(336, 174, 128, "③ điểm 3D", "cao độ ← dsm.tif")}
  {_mui_ngang(466, 197, 492)}
  {_hop_tam(494, 174, 128, "④ pixel RGB", "tư thế ← cameras.xml")}
  {_mui_ngang(624, 197, 650)}
  {_hop_tam(652, 174, 88, "⑤ pixel nhiệt", "H⁻¹")}
  <text x="696" y="244" {_M} font-size="11" fill="var(--ember)" text-anchor="middle">lấy giá trị</text>
  <path d="M696,250 L696,262" stroke="var(--ember)" stroke-width="1.6"/>
  <path d="M692,255 L696,262 L700,255" fill="var(--ember)"/>

  <rect x="20" y="262" width="620" height="52" rx="6" fill="var(--ember)" fill-opacity=".08" stroke="var(--ember)" stroke-width="1.3"/>
  <text x="34" y="282" {_F} font-size="12" fill="var(--text-2)"><tspan font-weight="600">H dùng ở dạng NGHỊCH ĐẢO.</tspan> Ma trận hiệu chuẩn là nhiệt→RGB, nhưng ở đây đang đi</text>
  <text x="34" y="300" {_F} font-size="12" fill="var(--text-2)">từ RGB về nhiệt — nên phải lật ngược. H chỉ là mắt CUỐI, không phải cả phép ghép.</text>
</svg>'''


# ------------------------------------------------------------ luồng pipeline
def _hop(x, y, w, ten, phu, mau="var(--line)", nen="var(--surface)", dam=False):
    kieu = 'font-weight="600"' if dam else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="46" rx="7" fill="{nen}" '
            f'stroke="{mau}" stroke-width="1.8"/>'
            f'<text x="{x+11}" y="{y+20}" {_M} font-size="12" fill="var(--text)" {kieu}>{ten}</text>'
            f'<text x="{x+11}" y="{y+36}" {_F} font-size="10.5" fill="var(--text-3)">{phu}</text>')


def _file(x, y, w, ten, mau="var(--ember)"):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="26" rx="13" '
            f'fill="{mau}" fill-opacity=".12" stroke="{mau}" stroke-width="1.4"/>'
            f'<text x="{x+w/2}" y="{y+17}" {_M} font-size="11" fill="{mau}" '
            f'text-anchor="middle">{ten}</text>')


def _mui(x1, y1, x2, y2, mau="var(--text-3)", dut=False):
    d = ' stroke-dasharray="5 4"' if dut else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{mau}" '
            f'stroke-width="1.6"{d}/>'
            f'<path d="M{x2-4},{y2-7} L{x2},{y2} L{x2+4},{y2-7}" fill="{mau}"/>')


_L = [
    '<svg viewBox="0 0 980 700" role="img" aria-label="Luồng dữ liệu của pipeline">'
    # --- GĐ 0
    f'<text x="20" y="20" {_M} font-size="11" fill="var(--text-3)">GĐ 0 · PHẢI CÓ SẴN — không script nào sinh ra</text>'
    + _hop(20, 30, 200, "Metashape export", "cameras.xml · ortho.tif · dsm.tif", "var(--steel)")
    + _hop(232, 30, 178, "du_lieu/manifest_anh.csv", "598 cặp, đường dẫn tuyệt đối", "var(--steel)")
    + _hop(422, 30, 150, "ảnh _T.JPG / _W.JPG", "dữ liệu bay", "var(--steel)")
    + _hop(584, 30, 170, "best.pt · RTK350.txt", "ổ D: — dự án của thầy", "var(--steel)")
    + _hop(766, 30, 194, "ket_qua/tam_pin_polygon.json", "~6300 polygon tấm pin", "var(--steel)")
    # --- GĐ 1
    + _mui(120, 76, 120, 104)
    + _hop(20, 106, 250, "① calib_thermal_rgb.py", "CHẤM TAY · 1 lần cho mỗi model drone", "var(--ember)", "var(--surface)", True)
    + _mui(145, 152, 145, 174)
    + _file(38, 176, 214, "ket_qua/thermal_to_rgb.json")
    # --- GĐ 2, 3
    # loc_anh_tre cần H; loc_anh_rung KHÔNG — nó chỉ đọc manifest + XMP trong ảnh
    + _mui(90, 202, 90, 232) + _mui(330, 78, 330, 232)
    + _hop(20, 234, 218, "② loc_anh_tre.py", "đo lệch từng ảnh · ~44 phút", "var(--ember)")
    + _hop(250, 234, 210, "③ loc_anh_rung.py", "đọc XMP · ~1 phút", "var(--ember)")
    + _mui(129, 280, 129, 302) + _mui(355, 280, 355, 302)
    + _file(24, 304, 210, "du_lieu/anh_tre_chup_full.json")
    + _file(250, 304, 210, "du_lieu/anh_rung.json")
    # --- GĐ 4
    + _mui(129, 330, 200, 360) + _mui(355, 330, 260, 360)
    + _hop(120, 362, 250, "④ ghep_ortho_nhiet.py", "chiếu ngược từng pixel · ~3 phút", "var(--ember)", "var(--surface)", True)
    + _mui(245, 408, 245, 430)
    + _file(140, 432, 210, "ket_qua/ortho/ortho_nhiet_tu_lam.tif")
    # --- GĐ 7: đã tìm lại được code 12/08/2026, không còn là mắt xích đứt
    + _mui(245, 458, 245, 486)
    + _hop(90, 488, 310, "⑦ quet_loi_tren_ortho.py", "model 8 lớp · cửa sổ 640 px, chồng 30%", "var(--ember)")
    + _mui(245, 534, 245, 556)
    + _file(120, 558, 250, "ket_qua/loi_tren_ortho_nhiet.json")
    + f'<text x="245" y="600" {_M} font-size="10.5" fill="var(--text-3)" text-anchor="middle">211 lỗi · khôi phục từ scratchpad 12/08</text>'
    # --- khối B
    + f'<text x="560" y="120" {_M} font-size="11" fill="var(--text-3)">KHỐI B · độc lập hoàn toàn, chỉ đụng ổ D:</text>'
    + _hop(560, 130, 200, "⑪a val_tap_test.py", "tập test 91 ảnh / 280 lỗi", "var(--steel)")
    + _mui(660, 176, 660, 198)
    + _hop(560, 200, 200, "⑪b phan_tich_recall.py", "cần yaml của ⑪a", "var(--steel)")
    + _hop(776, 130, 184, "⑪c val_model_4lop.py", "hai cách chia tập", "var(--steel)")
    + _hop(776, 200, 184, "⑪d so_model_8lop.py", "so model mượn", "var(--steel)")
    + _mui(760, 246, 760, 270)
    + _file(600, 272, 320, "ket_qua/ket_qua_val/*.json  →  báo cáo", "var(--steel)"),
    # --- khối C
    _hop(560, 400, 250, "⑫ danh_gia_chi_so.py", "in bảng chỉ số · KHÔNG ghi file", "var(--flare)")
    + _hop(560, 470, 250, "⑨⑩ xuat_nen_net + va_viewer", "nền nét cho so_sanh_model.html", "var(--flare)")
    + _mui(375, 566, 552, 432, "var(--text-3)", True)
    + f'<text x="560" y="392" {_M} font-size="11" fill="var(--text-3)">KHỐI C · tiêu thụ sản phẩm của A và B</text>'
    + f'<text x="20" y="660" {_F} font-size="11.5" fill="var(--text-3)">Đường tới hạn = 4 lệnh: ① → ② ‖ ③ → ④. Mọi thứ khác là QC, đo đạc hoặc trình bày — bỏ được mà pipeline vẫn chạy.</text>'
    + f'<text x="20" y="682" {_F} font-size="11.5" fill="var(--text-3)">Bước ⑦ đã tìm lại được code (12/08/2026) — cả chuỗi nay dựng lại được từ đầu.</text>'
    + '</svg>',
]
HINH["luong_pipeline"] = "".join(_L)


if __name__ == "__main__":
    print("%d hình:" % len(HINH))
    for k, v in HINH.items():
        print("  %-18s %5d ký tự" % (k, len(v)))
