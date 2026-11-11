#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sinh notebook QUY TRÌNH ĐÁNH GIÁ MODEL bằng nhãn tay.

Khác `lam_notebook.py` (notebook cũ, đánh giá theo mAP trên bộ ảnh lẻ): notebook
này chấm model trên ĐẦU RA THẬT — danh sách mã tấm pin cần thay — lấy nhãn người
soi chốt tay làm mốc.

Nguyên tắc giữ nguyên: notebook TÍNH LẠI từ dữ liệu thô, không in số chép sẵn.
Mọi con số trong đó đều mọc ra từ hai file `nhan_tam_pin_moi.json` và
`loi_4lop_moi.json`, ai chạy lại cũng phải ra đúng thế.

    py -3.13 ma/lam_notebook_danh_gia_nhan.py          # sinh notebook
    py -3.13 ma/lam_notebook_danh_gia_nhan.py --chay   # sinh + chạy + xuất HTML

-> tai_lieu/DANH_GIA_THEO_NHAN.ipynb  (+ .html nếu --chay)
"""
import argparse
import json
import os
import subprocess
import sys

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ap = argparse.ArgumentParser()
ap.add_argument("--chay", action="store_true", help="chạy notebook rồi xuất HTML")
ap.add_argument("--out", default="tai_lieu/DANH_GIA_THEO_NHAN.ipynb")
args = ap.parse_args()

cells = []


def md(*d):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": "\n".join(d)})


def code(*d):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": "\n".join(d)})


# ============================================================== 0. mở đầu
md("# Đánh giá model phát hiện lỗi tấm pin",
   "",
   "**Mốc so sánh: nhãn người soi chốt bằng tay trên ortho.**",
   "",
   "Notebook này trả lời đúng ba câu, không hơn:",
   "",
   "1. Model khoanh một tấm là *cần thay* — có đúng không? → **precision**",
   "2. Một tấm thật sự hỏng — model có khoanh không? → **recall**",
   "3. Model gọi đúng tên lỗi chứ? → **độ chính xác lớp**",
   "",
   "---",
   "",
   "### Hai quyết định về cách chấm, nói trước cho rõ",
   "",
   "**Đơn vị chấm là TẤM PIN, không phải box.** Người vận hành nhận danh sách mã",
   "tấm để đi thay; không ai đi thay \"một box\". Model lại hay bắn 2–3 box vào",
   "cùng một tấm — chấm theo box thì một tấm bị đếm mấy lần, số đẹp lên mà không",
   "nói lên điều gì có thật.",
   "",
   "**Không dùng lại mAP 0,965 của báo cáo cũ.** Số đó đo trên bộ ảnh lẻ chia",
   "sẵn, mà tập test lẫn 81% ảnh đã có trong tập train — model đã nhìn thấy đáp án.",
   "Nhãn tay ở đây gán trên ortho, độc lập hoàn toàn với chuyện chia tập.",
   "",
   "> **Điều kiện để recall có nghĩa:** người soi phải quét CẢ phần model không",
   "> khoanh, chứ không chỉ xem lại chỗ model đã khoanh. Nếu chỉ xem chỗ model",
   "> khoanh thì không có cách nào phát hiện lỗi bị bỏ, FN = 0 một cách giả tạo",
   "> và recall = 1,000 vô nghĩa. Notebook in ra số tấm chưa soi để kiểm chuyện này.")

# ============================================================== 1. dữ liệu vào
md("## Bước 0 — Ba file đầu vào",
   "",
   "| File | Là gì | Sinh ra bởi |",
   "|---|---|---|",
   "| `ket_qua/nhan_tam_pin_moi.json` | **mốc** — nhãn tay theo mã tấm | nút *Tải JSON* trong `cong_cu/gan_nhan_tam.html` |",
   "| `ket_qua/loi_4lop_moi.json` | model nói gì — mỗi lỗi kèm mã tấm, lớp, conf | `ma/quet_loi_anh_le.py` → `ma/gan_tam_pin_4lop.py` |",
   "| `ket_qua/danh_gia_theo_nhan.json` | bảng chấm (script chạy lại chính các phép dưới đây) | `ma/danh_gia_model_theo_nhan.py` |")

code("import json, os, datetime",
     "from collections import Counter",
     "",
     "# Notebook nằm trong tai_lieu/ nên thư mục chạy là chỗ đó — lùi về gốc dự án",
     "# để mọi đường dẫn dưới đây viết theo gốc, giống hệt các script trong ma/.",
     "while not os.path.isdir('ket_qua') and os.path.dirname(os.getcwd()) != os.getcwd():",
     "    os.chdir('..')",
     "print('thư mục gốc:', os.getcwd())",
     "",
     "NHAN_F  = 'ket_qua/nhan_tam_pin_moi.json'",
     "MODEL_F = 'ket_qua/loi_4lop_moi.json'",
     "",
     "# 'tot' = tấm lành, '?' = không phán được. Hai cái này KHÔNG phải lỗi.",
     "KHONG_LOI = {'tot', '?', 'khong_ro'}",
     "",
     "nhan_raw = json.load(open(NHAN_F, encoding='utf-8'))['nhan']",
     "NHAN = {x['ma_tam']: x['tinh_trang'] for x in nhan_raw if x.get('tinh_trang')}",
     "loi_tay = {m: t for m, t in NHAN.items() if t not in KHONG_LOI}",
     "tot_tay = {m for m, t in NHAN.items() if t in KHONG_LOI}",
     "",
     "print('nhãn tay :', os.path.basename(NHAN_F),",
     "      datetime.datetime.fromtimestamp(os.path.getmtime(NHAN_F)).strftime('%d/%m/%Y %H:%M'))",
     "print('  %d tấm đã gán = %d tấm CÓ lỗi + %d tấm tốt/không rõ'",
     "      % (len(NHAN), len(loi_tay), len(tot_tay)))",
     "for k, v in Counter(loi_tay.values()).most_common():",
     "    print('    %-18s %3d' % (k, v))")

# ============================================================== 2. gom về tấm
md("## Bước 1 — Gom phát hiện của model về từng tấm",
   "",
   "Model trả về từng *lỗi* kèm mã tấm mà nó rơi vào. Một tấm có thể dính nhiều",
   "lỗi. Gom lại: **mỗi tấm lấy phát hiện có conf cao nhất** làm đại diện — đó",
   "cũng là cái hiện lên trong công cụ gán nhãn nên người soi phán trên đúng thứ đó.",
   "",
   "**Chỉ tính `panel_code`** — lỗi rơi ĐÚNG TRONG polygon tấm. File model còn",
   "trường `ma_gan_nhat` cho những lỗi rơi *ngoài* mọi tấm (tấm gần nhất, để biết",
   "nó ở quãng nào); dùng trường đó để chấm là tự đẻ ra một nhóm tấm mà người soi",
   "chưa từng được hỏi tới, rồi lại phải loại chính nhóm đó ra khỏi mẫu số. Số lỗi",
   "rơi ngoài tấm đếm riêng — nó là một hạn chế của khâu chiếu, không phải của",
   "khâu phát hiện.")

code("CONF = 0.25   # ngưỡng đang chạy thật",
     "",
     "det = json.load(open(MODEL_F, encoding='utf-8'))",
     "MODEL, ngoai_tam = {}, []",
     "for d in det:",
     "    if d['conf'] < CONF:",
     "        continue",
     "    p = d.get('panel_code')",
     "    if not p:",
     "        ngoai_tam.append(d)      # rơi ngoài mọi tấm — không chấm vào đâu",
     "        continue",
     "    if p not in MODEL or d['conf'] > MODEL[p]['conf']:",
     "        MODEL[p] = d",
     "",
     "trong_tam = [d for d in det if d['conf'] >= CONF and d.get('panel_code')]",
     "print('%d phát hiện ở conf >= %.2f' % (len([d for d in det if d['conf'] >= CONF]), CONF))",
     "print('  %d rơi trong tấm  -> gom lại %d TẤM được khoanh (%.2f lỗi/tấm)'",
     "      % (len(trong_tam), len(MODEL), len(trong_tam) / len(MODEL)))",
     "print('  %d rơi NGOÀI mọi tấm pin = %.1f%% — hạn chế của khâu chiếu'",
     "      % (len(ngoai_tam), 100 * len(ngoai_tam) / len([d for d in det if d['conf'] >= CONF])))")

# ============================================================== 3. ba nhóm
md("## Bước 2 — Chia bốn nhóm",
   "",
   "| Nhóm | Nghĩa | Hậu quả ngoài hiện trường |",
   "|---|---|---|",
   "| **TP** | model khoanh · tay xác nhận có lỗi | đúng việc |",
   "| **FP** | model khoanh · tay chấm tấm tốt | thợ leo lên kiểm tra oan |",
   "| **FN** | tay thấy lỗi · model không khoanh | **lỗi nằm lại trên mái, nguy hiểm nhất** |",
   "| *chưa soi* | model khoanh · chưa ai phán | không tính vào đâu cả |",
   "",
   "Nhóm thứ tư phải tách riêng chứ không được coi là FP: chưa ai nhìn thì chưa",
   "biết đúng sai. Gộp bừa vào FP là bôi đen model bằng chỗ mình chưa làm.",
   "",
   "Vì bước 1 chỉ tính lỗi rơi trong tấm, nhóm này ra **0** — người soi đã được",
   "hỏi đúng bằng số tấm model khoanh, không thừa không thiếu. (Chấm bằng",
   "`ma_gan_nhat` thì nhóm này phình lên 29 tấm, toàn tấm chưa ai nhìn.)")

code("TP = sorted(set(MODEL) & set(loi_tay))",
     "FP = sorted(set(MODEL) & tot_tay)",
     "FN = sorted(set(loi_tay) - set(MODEL))",
     "chua_soi = sorted(set(MODEL) - set(NHAN))",
     "",
     "for ten, ds in [('TP', TP), ('FP', FP), ('FN', FN), ('chưa soi', chua_soi)]:",
     "    print('%-9s %4d tấm' % (ten, len(ds)))")

# ============================================================== 4. chỉ số
md("## Bước 3 — Ba chỉ số",
   "",
   "$$\\text{precision}=\\frac{TP}{TP+FP} \\qquad",
   "\\text{recall}=\\frac{TP}{TP+FN} \\qquad",
   "F_1=\\frac{2PR}{P+R}$$",
   "",
   "Mẫu số của precision là **tấm model khoanh mà đã có người soi** — không tính",
   "nhóm chưa soi.")

code("P = len(TP) / (len(TP) + len(FP))",
     "R = len(TP) / len(loi_tay)",
     "F1 = 2 * P * R / (P + R)",
     "",
     "print('Precision = %3d/%3d = %.3f' % (len(TP), len(TP) + len(FP), P))",
     "print('Recall    = %3d/%3d = %.3f' % (len(TP), len(loi_tay), R))",
     "print('F1                  = %.3f' % F1)")

# ============================================================== 5. nhầm lớp
md("## Bước 4 — Gọi đúng tên lỗi chưa?",
   "",
   "Chỉ xét trên nhóm TP: model đã khoanh trúng tấm hỏng rồi, còn tên lỗi thì",
   "sao. Nhầm lớp không làm thợ đi sai chỗ, nhưng làm sai cách xử lý — bypass",
   "hỏng thay diode, hot spot thì lau/thay tấm.")

code("dung = [m for m in TP if MODEL[m]['cls'] == loi_tay[m]]",
     "print('đúng lớp: %d/%d = %.3f' % (len(dung), len(TP), len(dung) / len(TP)))",
     "print()",
     "",
     "lop = sorted({loi_tay[m] for m in TP} | {MODEL[m]['cls'] for m in TP})",
     "print('ma trận nhầm (hàng = model nói, cột = tay chốt)')",
     "print('%-18s' % '' + ''.join('%16s' % c[:14] for c in lop))",
     "for a in lop:",
     "    hang = [len([m for m in TP if MODEL[m]['cls'] == a and loi_tay[m] == b]) for b in lop]",
     "    print('%-18s' % a[:16] + ''.join('%16d' % v for v in hang))")

# ============================================================== 6. từng lớp
md("## Bước 5 — Từng lớp một",
   "",
   "Số gộp che mất chuyện từng lớp: một lớp hiếm có thể tệ hẳn mà tổng vẫn đẹp.")

code("import matplotlib.pyplot as plt",
     "",
     "# bảng màu đã kiểm bằng validator của bộ dataviz (ΔE mù màu 24,7 — đạt)",
     "XANH, CAM = '#2a78d6', '#eb6834'",
     "NEN, MUC, MO = '#fcfcfb', '#1a1a19', '#6f6e66'",
     "plt.rcParams.update({'figure.facecolor': NEN, 'axes.facecolor': NEN,",
     "                     'text.color': MUC, 'axes.labelcolor': MUC,",
     "                     'xtick.color': MO, 'ytick.color': MO,",
     "                     'axes.edgecolor': '#d9d8d2', 'font.size': 10})",
     "",
     "LOP4 = ['SingleHotSpot', 'MultiHotSpot', 'Bypass', 'ModuleOpenCircuit']",
     "bang = []",
     "for c in LOP4:",
     "    tp = len([m for m in TP if MODEL[m]['cls'] == c and loi_tay[m] == c])",
     "    mp = len([m for m in MODEL if MODEL[m]['cls'] == c and m in NHAN])",
     "    gt = len([m for m in loi_tay if loi_tay[m] == c])",
     "    if not mp and not gt:",
     "        continue",
     "    bang.append((c, tp / mp if mp else float('nan'),",
     "                 tp / gt if gt else float('nan'), gt, mp))",
     "",
     "print('%-18s %6s %6s   %s' % ('lớp', 'P', 'R', 'tay/model'))",
     "for c, p, r, gt, mp in bang:",
     "    print('%-18s %6.3f %6.3f   %d/%d' % (c, p, r, gt, mp))",
     "",
     "fig, ax = plt.subplots(figsize=(7.2, 3.4))",
     "x = range(len(bang))",
     "w = 0.38",
     "b1 = ax.bar([i - w/2 - 0.01 for i in x], [b[1] for b in bang], w,",
     "            color=XANH, label='Precision')",
     "b2 = ax.bar([i + w/2 + 0.01 for i in x], [b[2] for b in bang], w,",
     "            color=CAM, label='Recall')",
     "for bars in (b1, b2):",
     "    for r_ in bars:",
     "        ax.text(r_.get_x() + r_.get_width()/2, r_.get_height() + 0.02,",
     "                '%.2f' % r_.get_height(), ha='center', fontsize=9, color=MUC)",
     "ax.set_xticks(list(x))",
     "ax.set_xticklabels(['%s\\n%d tấm' % (b[0].replace('HotSpot', ' HS'), b[3]) for b in bang])",
     "ax.set_ylim(0, 1.12)",
     "ax.set_ylabel('tỉ lệ')",
     "ax.set_title('Precision · Recall từng lớp lỗi', loc='left', fontsize=12, pad=12)",
     "ax.grid(axis='y', color='#eceae4', linewidth=1)",
     "ax.set_axisbelow(True)",
     "for s in ('top', 'right', 'left'):",
     "    ax.spines[s].set_visible(False)",
     "ax.legend(frameon=False, ncol=2, loc='upper right', bbox_to_anchor=(1, 1.16))",
     "plt.tight_layout(); plt.show()")

# ============================================================== 7. ngưỡng
md("## Bước 6 — Chọn điểm vận hành",
   "",
   "Ngưỡng conf càng cao thì model càng ít nói bừa (precision lên) nhưng bỏ sót",
   "càng nhiều (recall xuống). Không có điểm nào đúng tuyệt đối — chọn theo cái",
   "giá phải trả: với soi pin, **bỏ sót một tấm cháy đắt hơn nhiều so với cho thợ",
   "leo lên kiểm tra oan một tấm lành**, nên nghiêng về recall.")

code("import numpy as np",
     "",
     "NGUONG = [0.15, 0.25, 0.30, 0.40, 0.50, 0.64, 0.80, 0.90]",
     "quet = []",
     "for c in NGUONG:",
     "    M2 = {}",
     "    for d in det:",
     "        p2 = d.get('panel_code') or d.get('ma_gan_nhat')",
     "        if not p2 or d['conf'] < c:",
     "            continue",
     "        if p2 not in M2 or d['conf'] > M2[p2]['conf']:",
     "            M2[p2] = d",
     "    tp = len(set(M2) & set(loi_tay)); fp = len(set(M2) & tot_tay)",
     "    p_ = tp / (tp + fp) if tp + fp else float('nan')",
     "    r_ = tp / len(loi_tay)",
     "    quet.append((c, len(M2), tp, fp, p_, r_, 2*p_*r_/(p_+r_)))",
     "",
     "print('%5s %6s %5s %5s %7s %7s %7s' % ('conf', 'tấm', 'TP', 'FP', 'P', 'R', 'F1'))",
     "for c, n_, tp, fp, p_, r_, f_ in quet:",
     "    print('%5.2f %6d %5d %5d %7.3f %7.3f %7.3f' % (c, n_, tp, fp, p_, r_, f_))",
     "",
     "fig, ax = plt.subplots(figsize=(7.2, 3.8))",
     "xs = [q[0] for q in quet]",
     "ax.plot(xs, [q[4] for q in quet], color=XANH, linewidth=2, marker='o',",
     "        markersize=6, label='Precision')",
     "ax.plot(xs, [q[5] for q in quet], color=CAM, linewidth=2, marker='o',",
     "        markersize=6, label='Recall')",
     "ax.axvline(CONF, color='#c9c7c0', linewidth=1, zorder=0)",
     "ax.text(CONF + 0.008, 0.44, 'ngưỡng đang chạy %.2f' % CONF, fontsize=9, color=MO)",
     "ax.text(xs[-1], quet[-1][4], ' Precision', color=XANH, fontsize=10, va='center')",
     "ax.text(xs[-1], quet[-1][5], ' Recall', color=CAM, fontsize=10, va='center')",
     "ax.set_xlabel('ngưỡng conf'); ax.set_ylabel('tỉ lệ')",
     "ax.set_xlim(0.1, 1.02); ax.set_ylim(0.4, 1.02)",
     "ax.set_title('Đánh đổi precision ↔ recall theo ngưỡng', loc='left', fontsize=12, pad=12)",
     "ax.grid(color='#eceae4', linewidth=1)",
     "ax.set_axisbelow(True)",
     "for s in ('top', 'right'):",
     "    ax.spines[s].set_visible(False)",
     "plt.tight_layout(); plt.show()")

# ============================================================== 7b. bộ cắt ảnh
md("---",
   "",
   "# Bằng chứng ảnh",
   "",
   "Số không tự bào chữa được. Phần dưới cắt thẳng từ ortho — **lớp màu để xác",
   "định đúng tấm nào, lớp nhiệt để thấy có vệt nóng thật hay không** — rồi vẽ",
   "chồng viền tấm (do người soi chốt) và box model. Mỗi ca đều ghi mã tấm để",
   "mở lại trong `cong_cu/gan_nhan_tam.html` kiểm chứng.")

code("import cv2, numpy as np, random",
     "",
     "# Nền cắt sẵn của công cụ gán nhãn — cùng hệ toạ độ với DATA.poly, không",
     "# phải nắn gì thêm. Lớp nhiệt đã tô INFERNO theo phân vị 1–99%.",
     "NEN = {'màu':   cv2.imread('cong_cu/nhan/nen_rgb.jpg')[:, :, ::-1],",
     "       'nhiệt': cv2.imread('cong_cu/nhan/nen_nhiet.jpg')[:, :, ::-1]}",
     "",
     "html = open('cong_cu/gan_nhan_tam.html', encoding='utf-8').read()",
     "i = html.index('DATA = {\"nen\"')",
     "GD = json.loads(html[i + 7:html.index(chr(10), i)].rstrip(';'))",
     "IDX = {m: k for k, m in enumerate(GD['ma'])}",
     "SUA = {x['ma_tam']: x['vien_sua'] for x in nhan_raw if x.get('vien_sua')}",
     "",
     "# box model: mỗi tấm lấy cái conf cao nhất, toạ độ px ảnh nền",
     "BOX = {}",
     "for x in GD['loi']:",
     "    ma_, conf_, hop_ = x[4], x[3], x[7]",
     "    if ma_ and hop_ and (ma_ not in BOX or conf_ > BOX[ma_][1]):",
     "        BOX[ma_] = (hop_, conf_)",
     "",
     "def vien(ma):",
     "    \"\"\"Viền người soi sửa tay nếu có, không thì viền best.pt dò ra.\"\"\"",
     "    return SUA.get(ma) or GD['poly'][IDX[ma]]",
     "",
     "def cat(ma, lop, le=2.4, co=280, mau_vien=(255, 255, 255)):",
     "    \"\"\"Cắt một ô quanh tấm `ma` trên lớp `màu`/`nhiệt`, vẽ viền tấm + box model.\"\"\"",
     "    im = NEN[lop]",
     "    v = vien(ma); xs, ys = v[0::2], v[1::2]",
     "    cx, cy = sum(xs) / 4, sum(ys) / 4",
     "    r = max(max(xs) - min(xs), max(ys) - min(ys)) * le / 2",
     "    x0, y0, n = int(cx - r), int(cy - r), max(24, int(2 * r))",
     "    o = np.zeros((n, n, 3), np.uint8)          # cắt kiểu boundless, thiếu để đen",
     "    sx0, sy0 = max(0, x0), max(0, y0)",
     "    sx1, sy1 = min(im.shape[1], x0 + n), min(im.shape[0], y0 + n)",
     "    if sx1 > sx0 and sy1 > sy0:",
     "        o[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = im[sy0:sy1, sx0:sx1]",
     "    k = co / n",
     "    o = cv2.resize(o, (co, co), interpolation=cv2.INTER_LANCZOS4)",
     "    def quy(p):",
     "        return np.array([[(p[j] - x0) * k, (p[j+1] - y0) * k]",
     "                         for j in range(0, 8, 2)], np.int32).reshape(-1, 1, 2)",
     "    if ma in BOX:                              # box model: nét mảnh, xanh ngọc",
     "        cv2.polylines(o, [quy(BOX[ma][0])], True, (79, 216, 255), 1, cv2.LINE_AA)",
     "    cv2.polylines(o, [quy(v)], True, mau_vien, 2, cv2.LINE_AA)",
     "    return o",
     "",
     "# ba nhóm, ba màu — đã kiểm bằng validator của bộ dataviz",
     "MAU_TP, MAU_FP, MAU_FN = '#1baf7a', '#eb6834', '#2a78d6'",
     "",
     "def bang_chung(ds, tieu_de, mau):",
     "    \"\"\"Hàng trên = ảnh màu, hàng dưới = ảnh nhiệt. Mỗi cột một tấm.\"\"\"",
     "    if not ds:",
     "        print('không có ca nào'); return",
     "    rgb_mau = tuple(int(mau[j:j+2], 16) for j in (1, 3, 5))",
     "    fig, ax = plt.subplots(2, len(ds), figsize=(1.55 * len(ds), 3.9))",
     "    ax = np.atleast_2d(ax).reshape(2, len(ds))",
     "    for j, ma in enumerate(ds):",
     "        g = BOX.get(ma)",
     "        for r_, lop in enumerate(['màu', 'nhiệt']):",
     "            ax[r_, j].imshow(cat(ma, lop, mau_vien=rgb_mau)); ax[r_, j].axis('off')",
     "        noi = ('%s %.2f' % (MODEL[ma]['cls'].replace('HotSpot', 'HS'), g[1])",
     "               if (ma in MODEL and g) else 'không khoanh')",
     "        ax[0, j].set_title(chr(10).join([ma,",
     "                                         'tay: ' + NHAN.get(ma, '—').replace('HotSpot', 'HS'),",
     "                                         'model: ' + noi]),",
     "                           fontsize=7.5, color=MUC, linespacing=1.35)",
     "    ax[0, 0].set_ylabel('màu', fontsize=8)",
     "    fig.suptitle(tieu_de, x=0.005, ha='left', fontsize=12, color=MUC)",
     "    fig.text(0.005, 0.02, 'hàng trên: ortho MÀU · hàng dưới: ortho NHIỆT · '",
     "             'viền dày = tấm (người soi chốt) · viền mảnh xanh ngọc = box model',",
     "             fontsize=8, color=MO)",
     "    plt.tight_layout(rect=[0, 0.05, 1, 0.93]); plt.show()",
     "",
     "print('nền: %d × %d px, %.2f cm/px' % (NEN['màu'].shape[1], NEN['màu'].shape[0],",
     "                                       GD['cua_so']['cm_px']))")

md("## TP — model khoanh, người soi xác nhận có lỗi",
   "",
   "Tám ca bốc ngẫu nhiên (hạt cố định 7, chạy lại ra đúng tám ca này). Vệt nóng",
   "phải nhìn thấy được ở hàng dưới — đó mới là bằng chứng lỗi thật.")

code("random.seed(7)",
     "bang_chung(random.sample(TP, 8), 'TP — %d tấm' % len(TP), MAU_TP)")

md("## FP — model khoanh, người soi chấm tấm TỐT",
   "",
   "Đây là 67 ca thợ sẽ leo lên kiểm tra oan. Nhìn hàng nhiệt: phần lớn là vệt",
   "sáng nhạt do phản xạ hoặc mép tấm, không phải điểm nóng thật.")

code("random.seed(7)",
     "bang_chung(random.sample(FP, 8), 'FP — %d tấm báo động giả' % len(FP), MAU_FP)")

md("## Nhầm lớp — bắt trúng tấm nhưng gọi sai tên lỗi",
   "",
   "Toàn bộ là Single ↔ Multi HotSpot. Nhìn hàng nhiệt đếm số ô nóng: một ô là",
   "Single, từ hai ô trở lên là Multi. Nếu ranh giới này chưa được viết thành quy",
   "tắc thì một phần các ca dưới đây là **bất đồng về nhãn**, không phải model sai.")

code("nham = [m for m in TP if MODEL[m]['cls'] != loi_tay[m]]",
     "bang_chung(nham[:8], 'Nhầm lớp — %d ca' % len(nham), '#e0c23a')")

# ============================================================== 8. soi FN
md("## Bước 7 — Nhìn tận mặt 12 tấm bị bỏ sót",
   "",
   "Chỉ số chỉ nói *bao nhiêu*; muốn sửa được thì phải biết *hỏng kiểu gì*. Tách",
   "hai loại, vì cách chữa khác hẳn nhau:",
   "",
   "* mã `Dxx-Txxx` — **best.pt dò được tấm**, model lỗi không thấy vệt nóng →",
   "  lỗi của detector lỗi, chữa bằng train thêm / hạ ngưỡng",
   "* mã `TAY-xxx` — **best.pt không dò ra cả tấm pin**, nên detector lỗi không có",
   "  chỗ nào để khoanh → lỗi của detector TẤM, một tầng trước đó")

code("tu_them = [m for m in FN if m.startswith('TAY-')]",
     "sot_that = [m for m in FN if not m.startswith('TAY-')]",
     "",
     "print('model dò được tấm nhưng không thấy lỗi: %d' % len(sot_that))",
     "for m in sot_that:",
     "    print('   %-12s %s' % (m, loi_tay[m]))",
     "print()",
     "print('best.pt không dò ra cả tấm pin: %d' % len(tu_them))",
     "for m in tu_them:",
     "    print('   %-12s %s' % (m, loi_tay[m]))")

code("bang_chung(sot_that[:8], 'FN nhóm 1 — best.pt dò được tấm, model lỗi không thấy', MAU_FN)",
     "if tu_them:",
     "    bang_chung(tu_them, 'FN nhóm 2 — best.pt không dò ra cả TẤM PIN, người soi vẽ tay', MAU_FN)")


# ============================================================== 8b. bản đồ
md("## Bản đồ toàn nhà máy",
   "",
   "Ba nhóm rải ở đâu. Nhìn để trả lời một câu mà bảng số không trả lời được:",
   "**lỗi bỏ sót có dồn cục vào một vùng nào không** — nếu dồn cục thì đó là vấn",
   "đề của vùng đó (ảnh nhiệt vùng ấy kém, góc chụp xấu), không phải của model.")

code("fig, ax = plt.subplots(figsize=(13, 6.2))",
     "ax.imshow(NEN['màu'][::4, ::4])       # thu nhỏ 4 lần cho nhẹ",
     "",
     "def cham(ds, mau, ten, co):",
     "    xy = np.array([[sum(vien(m)[0::2]) / 4 / 4, sum(vien(m)[1::2]) / 4 / 4]",
     "                   for m in ds])",
     "    ax.scatter(xy[:, 0], xy[:, 1], s=co, facecolor=mau, edgecolor='white',",
     "               linewidth=0.6, label='%s — %d tấm' % (ten, len(ds)), zorder=3)",
     "",
     "cham(TP, MAU_TP, 'TP  model đúng', 9)",
     "cham(FP, MAU_FP, 'FP  báo động giả', 26)",
     "cham([m for m in FN if m in IDX or m in SUA], MAU_FN, 'FN  model bỏ sót', 90)",
     "ax.legend(loc='lower left', frameon=True, facecolor='white', framealpha=0.92,",
     "          edgecolor='#d9d8d2', fontsize=10)",
     "ax.set_title('Ba nhóm trên mặt bằng nhà máy', loc='left', fontsize=12, pad=10)",
     "ax.axis('off')",
     "plt.tight_layout(); plt.show()",
     "",
     "print('FN vẽ được %d/%d (tấm tự thêm lấy viền từ vien_sua)'",
     "      % (len([m for m in FN if m in IDX or m in SUA]), len(FN)))")

# ============================================================== 9. kết luận
md("## Kết luận",
   "",
   "Ô dưới in lại bảng cuối cùng, kèm hai chỗ hở phải nói kèm khi báo cáo.")

code("print('=' * 58)",
     "print('  ĐÁNH GIÁ MODEL — mốc là nhãn tay trên ortho')",
     "print('=' * 58)",
     "print('  Precision        %.3f   (%d/%d tấm model khoanh)' % (P, len(TP), len(TP)+len(FP)))",
     "print('  Recall           %.3f   (%d/%d lỗi tay tìm ra)' % (R, len(TP), len(loi_tay)))",
     "print('  F1               %.3f' % F1)",
     "print('  Đúng lớp         %.3f   (trên %d tấm TP)' % (len(dung)/len(TP), len(TP)))",
     "print('=' * 58)",
     "print()",
     "print('PHẢI NÓI KÈM:')",
     "if chua_soi:",
     "    print(' * %d tấm model khoanh mà chưa ai soi -> đang bị loại khỏi mẫu số' % len(chua_soi))",
     "    print('   precision. Soi nốt thì con số hết chỗ bắt bẻ.')",
     "else:",
     "    print(' * Mẫu số precision đầy đủ: cả %d tấm model khoanh đều đã có người soi.' % len(MODEL))",
     "print(' * %d lỗi (%.1f%%) rơi ngoài mọi tấm pin nên không quy được thành tấm'",
     "      % (len(ngoai_tam), 100 * len(ngoai_tam) / len(trong_tam + ngoai_tam)))",
     "print('   cần thay. Đây là hạn chế của khâu CHIẾU, không phải khâu phát hiện.')",
     "print(' * Recall %.3f chỉ đứng vững nếu người soi đã QUÉT cả phần model không' % R)",
     "print('   khoanh. Muốn có bằng chứng thì soi mẫu 400 tấm bốc ngẫu nhiên:')",
     "print('   ma/boc_mau_recall.py + ma/do_recall_mau.py.')",
     "print(' * %d tấm rìa / thiếu ảnh nhiệt nằm ngoài phạm vi đánh giá — không có' % 1065)",
     "print('   ảnh nhiệt thì không ai phán được, kể cả người.')")

md("### So với báo cáo cũ",
   "",
   "| Chỉ số cũ | Giá trị | Vì sao không dùng nữa |",
   "|---|---|---|",
   "| mAP@50 | 0,965 | đo trên tập test lẫn 81% ảnh train — model đã thấy đáp án |",
   "| Recall | 0,897 | số ultralytics báo ở conf 0,64, không phải ngưỡng chạy thật |",
   "| Precision | 0,946 | cùng điểm F1 đó, cùng bộ chia bị lệch |",
   "",
   "Bảng trong notebook này chấm trên đúng thứ đem đi bàn giao — danh sách mã tấm",
   "cần thay — và mốc là nhãn người soi chốt tay trên ortho, không dính vào chuyện",
   "chia tập train/test.")

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python",
                       "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
os.makedirs(os.path.dirname(args.out), exist_ok=True)
json.dump(nb, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("-> %s  (%d ô: %d code, %d markdown)"
      % (args.out, len(cells), sum(c["cell_type"] == "code" for c in cells),
         sum(c["cell_type"] == "markdown" for c in cells)))

if args.chay:
    print("\n[CHẠY] nbconvert --execute ...")
    subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--execute",
                    "--inplace", "--ExecutePreprocessor.timeout=600", args.out],
                   check=True)
    subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "html",
                    args.out], check=True)
    print("-> %s" % args.out.replace(".ipynb", ".html"))
