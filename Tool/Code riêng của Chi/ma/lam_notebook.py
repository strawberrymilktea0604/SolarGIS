# -*- coding: utf-8 -*-
"""Sinh notebook danh gia. Dung generator thay vi go tay .ipynb cho khoi loi
escape, va sua lai nhanh khi doi noi dung.

Nguyen tac cua notebook: TINH LAI tu du lieu tho, khong in so co san.
  - Hieu chuan H : ap H len 31 cap diem -> tu tinh RMSE tai chieu
  - Sai so dinh vi: tu tinh RMSE tu 11 vector lech
  - Gan tam pin  : tu tinh IoU + phep gan tu 6300 polygon
Rieng mAP/recall phai chay model nen tach thanh o tuy chon.
"""
import json
import os

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

cells = []


def md(*d):
    cells.append({"cell_type": "markdown", "metadata": {},
                  "source": "\n".join(d)})


def code(*d):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": "\n".join(d)})


# ============================================================ mo dau
md("# Đánh giá hệ thống định vị lỗi tấm pin từ ảnh nhiệt",
   "",
   "**Dự án:** 1008-stage1-rgb-thermal",
   "",
   "Notebook này **tính lại** các chỉ số từ dữ liệu thô, không đọc số đã lưu sẵn.",
   "Chạy `Kernel → Restart & Run All` để dựng lại toàn bộ kết quả từ đầu.",
   "",
   "| Phần | Nội dung | Nguồn dữ liệu |",
   "|---|---|---|",
   "| A | Sai số hiệu chuẩn H (nhiệt → RGB) | 31 cặp điểm chấm tay |",
   "| B | Sai số định vị / GPS | 11 điểm đối chứng trên ortho |",
   "| C | Gán lỗi vào tấm pin, IoU | 211 lỗi + 6300 polygon |",
   "| D | Kiểm tra vị trí bất thường | 211 lỗi |",
   "| E | mAP@50, precision, recall | tập test 91 ảnh (cần model) |")

code("import json, math, os",
     "import numpy as np",
     "import matplotlib.pyplot as plt",
     "",
     "plt.rcParams.update({'figure.dpi': 110, 'font.size': 9,",
     "                     'axes.grid': True, 'grid.alpha': .3})",
     "",
     "GOC = os.path.abspath('..')   # notebook nam trong tai_lieu/",
     "def doc(f):",
     "    with open(os.path.join(GOC, f), encoding='utf-8') as fh:",
     "        return json.load(fh)",
     "",
     "def pct(v, p):",
     "    \"\"\"Phan vi thu p cua day da sap xep.\"\"\"",
     "    if not v: return float('nan')",
     "    k = (len(v)-1) * p / 100.0",
     "    lo, hi = math.floor(k), math.ceil(k)",
     "    return v[int(lo)] if lo == hi else v[int(lo)]*(hi-k) + v[int(hi)]*(k-lo)",
     "",
     "print('sẵn sàng')")

# ============================================================ A
md("---",
   "## A. Sai số hiệu chuẩn H (ảnh nhiệt → ảnh RGB)",
   "",
   "Phép chiếu gồm **hai bước**: áp ma trận H, rồi trừ một lượng bù lệch lắp đặt",
   "cố định (`dx`, `dy`). Ô dưới áp cả hai bước lên 31 điểm nhiệt rồi so với điểm",
   "RGB tương ứng — tự tính chứ không lấy `rmse_px` đã lưu.")

code("d = doc('ket_qua/thermal_to_rgb.json')",
     "H  = np.array(d['H_thermal_to_rgb'])",
     "pt = np.array(d['points_thermal'])   # (31,2) toa do tren anh nhiet",
     "pr = np.array(d['points_rgb'])       # (31,2) toa do tuong ung tren anh RGB",
     "GSD = d['gsd_cm_per_px']             # cm tren mot pixel",
     "bu  = d['hieu_chinh_bo_sung']        # bu lech lap dat co dinh",
     "",
     "# buoc 1 - ap H: toa do thuan nhat [x,y,1] -> H @ p -> chia thanh phan thu 3",
     "p_h = np.hstack([pt, np.ones((len(pt),1))])",
     "q   = (H @ p_h.T).T",
     "q   = q[:, :2] / q[:, 2:3]",
     "rmse_thoH = float(np.sqrt((np.linalg.norm(q-pr, axis=1)**2).mean()))",
     "",
     "# buoc 2 - tru bu lech",
     "q_bu = q - np.array([bu['dx_px'], bu['dy_px']])",
     "res  = np.linalg.norm(q_bu - pr, axis=1)",
     "rmse = float(np.sqrt((res**2).mean()))",
     "",
     "print('Số cặp điểm            : %d' % len(pt))",
     "print('RMSE chỉ riêng H       : %.3f px' % rmse_thoH)",
     "print('Bù lệch lắp đặt        : dx %.2f, dy %.2f px' % (bu['dx_px'], bu['dy_px']))",
     "print('RMSE sau khi bù        : %.3f px  = %.2f cm' % (rmse, rmse*GSD))",
     "print('Trung vị               : %.3f px' % np.median(res))",
     "print('Lớn nhất               : %.3f px  = %.2f cm' % (res.max(), res.max()*GSD))",
     "print()",
     "print('Đối chiếu số lưu trong file: %.3f px  -> lệch %.1e ✓'",
     "      % (d['rmse_px'], abs(rmse - d['rmse_px'])))",
     "print('H của hãng (chưa hiệu chuẩn lại): %.2f px' % d['baseline_RTK350_rmse_px'])",
     "print('-> hiệu chuẩn tay tốt hơn %.1f lần' % (d['baseline_RTK350_rmse_px']/rmse))")

md("### Con số 4,38 px là *in-sample* — phải nói rõ",
   "",
   "Lượng bù lệch trùng khít với độ lệch trung bình của chính 31 điểm này (ô dưới",
   "kiểm chứng). Nghĩa là nó đã hút đúng phần lệch của bộ điểm dùng để đo, nên",
   "4,38 px **không phải** con số độc lập.",
   "",
   "Bằng chứng độc lập nằm ở kiểm chứng chéo trên các ảnh khác.")

code("r = q - pr",
     "print('Lệch trung bình của 31 điểm : dx %.6f, dy %.6f'",
     "      % (r[:,0].mean(), r[:,1].mean()))",
     "print('Lượng bù ghi trong file      : dx %.6f, dy %.6f'",
     "      % (bu['dx_px'], bu['dy_px']))",
     "print('-> trùng khít:', np.allclose([r[:,0].mean(), r[:,1].mean()],",
     "                                     [bu['dx_px'], bu['dy_px']]))",
     "print()",
     "print('KIỂM CHỨNG CHÉO trên ảnh khác (đây mới là số độc lập):')",
     "kc = []",
     "for f, ten in [('ket_qua/kiem_chung_0320.json','ảnh 0320'),",
     "               ('ket_qua/kiem_chung_0440.json','ảnh 0440'),",
     "               ('ket_qua/kiem_chung_0080.json','ảnh 0080')]:",
     "    k = doc(f)",
     "    kc.append(k['rmse_px'])",
     "    print('   %-10s %2d điểm   RMSE %.2f px' % (ten, k['n_points'], k['rmse_px']))",
     "print('   %-10s          trung bình %.2f px' % ('', np.mean(kc)))",
     "print()",
     "print('Ba số này bao quanh 4,38 px -> hiệu chuẩn dùng được thật,')",
     "print('nhưng khi báo cáo nên dẫn số kiểm chứng chéo, không dẫn 4,38.')")

code("fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))",
     "",
     "ax[0].hist(res, bins=12, color='#4d8fd6', edgecolor='white')",
     "ax[0].axvline(rmse, color='#e0575b', ls='--', label='RMSE %.2f px' % rmse)",
     "ax[0].axvline(3, color='#3fb96b', ls=':', label='ngưỡng đề bài 3 px')",
     "ax[0].set_xlabel('sai số tái chiếu (px)'); ax[0].set_ylabel('số điểm')",
     "ax[0].set_title('Phân bố sai số trên 31 điểm'); ax[0].legend(fontsize=8)",
     "",
     "# vector lech sau khi bu: cho thay con lech he thong hay da toa deu",
     "dv = q_bu - pr",
     "ax[1].quiver(pr[:,0], pr[:,1], dv[:,0], dv[:,1], res,",
     "             cmap='viridis', angles='xy', scale_units='xy', scale=.02)",
     "ax[1].invert_yaxis(); ax[1].set_aspect('equal')",
     "ax[1].set_xlabel('cột (px ảnh RGB)'); ax[1].set_ylabel('hàng')",
     "ax[1].set_title('Hướng lệch (phóng đại 50×)')",
     "plt.tight_layout(); plt.show()",
     "",
     "print('Lệch trung bình theo cột/hàng: %.2f / %.2f px' % (dv[:,0].mean(), dv[:,1].mean()))",
     "print('-> gần 0 nghĩa là không còn lệch hệ thống, phần dư là nhiễu chấm tay.')")

md("**Nhận xét.** Sai số vượt ngưỡng 3 px của đề bài, nhưng vẫn tốt hơn H của hãng",
   "(22,34 px) khoảng 5 lần. Sau khi bù, sai số toả đều quanh 0 nên không còn lệch",
   "hệ thống — phần dư chủ yếu là độ chính xác khi chấm tay điểm tương ứng trên ảnh",
   "nhiệt 640×512.",
   "",
   "Khi báo cáo nên dẫn **kiểm chứng chéo 2,44 / 2,88 / 4,82 px** vì đó là số đo",
   "trên ảnh không tham gia hiệu chuẩn.")

# ============================================================ B
md("---",
   "## B. Sai số định vị (câu hỏi *sai số GPS*)",
   "",
   "Đối chứng 11 điểm giữa ortho nhiệt và ortho màu. Tự tính RMSE từ vector lệch",
   "`d_col`/`d_row` chứ không lấy `rmse_cm` có sẵn.")

code("e = doc('ket_qua/sai_so_end_to_end.json')",
     "g = e['gsd_cm_per_px']",
     "dc = np.array([p['d_col'] for p in e['points']])",
     "dr = np.array([p['d_row'] for p in e['points']])",
     "",
     "err_px = np.hypot(dc, dr)",
     "err_cm = err_px * g",
     "rmse_cm = float(np.sqrt((err_cm**2).mean()))",
     "",
     "print('Ảnh đối chứng : %s' % e['label'])",
     "print('Số điểm       : %d' % len(dc))",
     "print()",
     "print('RMSE          : %.2f cm' % rmse_cm)",
     "print('Trung bình    : %.2f cm' % err_cm.mean())",
     "print('Trung vị      : %.2f cm' % np.median(err_cm))",
     "print('Lớn nhất      : %.2f cm' % err_cm.max())",
     "print('Lệch hệ thống : cột %.2f px, hàng %.2f px' % (dc.mean(), dr.mean()))",
     "print()",
     "print('NGƯỠNG ĐỀ BÀI : <= 30 cm  ->  %s (dư %.1f lần)'",
     "      % ('ĐẠT' if rmse_cm <= 30 else 'KHÔNG ĐẠT', 30/rmse_cm))")

code("fig, ax = plt.subplots(figsize=(4.2, 4.2))",
     "ax.axhline(0, color='#888', lw=.8); ax.axvline(0, color='#888', lw=.8)",
     "for r_cm, s in [(1,':'), (2,'--'), (3,'-.')]:",
     "    t = np.linspace(0, 2*np.pi, 100); r = r_cm/g",
     "    ax.plot(r*np.cos(t), r*np.sin(t), s, color='#bbb', lw=.9)",
     "    ax.annotate('%d cm' % r_cm, (0, r), fontsize=7, color='#888', ha='center')",
     "ax.scatter(dc, dr, c='#4d8fd6', s=44, zorder=3, edgecolor='white')",
     "ax.scatter([dc.mean()], [dr.mean()], c='#e0575b', s=90, marker='x', zorder=4,",
     "           label='tâm lệch')",
     "ax.set_xlabel('lệch cột (px)'); ax.set_ylabel('lệch hàng (px)')",
     "ax.set_title('11 điểm đối chứng · RMSE %.2f cm' % rmse_cm)",
     "ax.set_aspect('equal'); ax.legend(fontsize=8)",
     "plt.tight_layout(); plt.show()")

md("**Lưu ý quan trọng.** Đây là sai số **tương đối** — đối chứng nội bộ giữa hai",
   "sản phẩm ortho. Sai số **tuyệt đối** còn cộng thêm sai số định vị của chính",
   "orthophoto Metashape. Muốn con số tuyệt đối phải đo vài điểm bằng máy RTK",
   "ngoài hiện trường.",
   "",
   "Trên **ảnh lẻ** (chưa qua bước trung bình hoá của ortho) sai số lớn hơn:",
   "trung vị 14,1 cm, P90 24,6 cm.")

# ============================================================ C
md("---",
   "## C. Gán lỗi vào tấm pin — IoU",
   "",
   "Tính lại phép gán **từ 6300 polygon tấm pin**: với mỗi lỗi, tìm tấm chứa tâm lỗi;",
   "nếu không có thì lấy tấm có IoU cao nhất trong 6 tấm gần nhất.")

code("import cv2",
     "",
     "loi    = doc('ket_qua/loi_tren_ortho_nhiet.json')",
     "panels = [np.asarray(p, np.float32) for p in doc('ket_qua/tam_pin_polygon.json')]",
     "cen    = np.array([p.mean(0) for p in panels])",
     "print('Số lỗi: %d   |   số tấm pin: %d' % (len(loi), len(panels)))",
     "",
     "GSD_CM = 0.877e-7 * 111320 * np.cos(np.radians(11.424)) * 100  # cm/px ortho màu",
     "half = np.array([[d['w_m'], d['h_m']] for d in loi]).mean(0) / 2 / (GSD_CM/100)",
     "",
     "def quad_iou(a, b):",
     "    A, B = cv2.contourArea(a), cv2.contourArea(b)",
     "    if A <= 0 or B <= 0: return 0.0",
     "    inter, _ = cv2.intersectConvexConvex(a, b)",
     "    return inter / (A + B - inter)",
     "",
     "ious, dists, trong = [], [], 0",
     "for d in loi:",
     "    pt = (d['ocol'], d['orow'])",
     "    dd = (cen[:,0]-pt[0])**2 + (cen[:,1]-pt[1])**2",
     "    near = np.argsort(dd)[:6]",
     "    q = np.array([[pt[0]-half[0], pt[1]-half[1]], [pt[0]+half[0], pt[1]-half[1]],",
     "                  [pt[0]+half[0], pt[1]+half[1]], [pt[0]-half[0], pt[1]+half[1]]],",
     "                 np.float32)",
     "    ins, best, bi = None, 0.0, None",
     "    for i in near:",
     "        if cv2.pointPolygonTest(panels[i], pt, False) >= 0: ins = i",
     "        v = quad_iou(q, panels[i])",
     "        if v > best: best, bi = v, i",
     "    j = ins if ins is not None else bi",
     "    trong += ins is not None",
     "    ious.append(best)",
     "    if j is not None: dists.append(float(np.sqrt(dd[j]) * GSD_CM))",
     "",
     "ious = np.array(ious); dists = np.array(dists)",
     "print()",
     "print('Rơi hẳn trong polygon tấm pin: %d/%d = %.1f %%'",
     "      % (trong, len(loi), 100*trong/len(loi)))",
     "print('IoU trung vị : %.3f' % np.median(ious))",
     "print('IoU trung bình: %.3f' % ious.mean())",
     "print('Khoảng cách tới tâm tấm — trung vị %.0f cm, P90 %.0f cm'",
     "      % (np.median(dists), np.percentile(dists, 90)))")

code("fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))",
     "",
     "ax[0].hist(ious, bins=22, color='#4d8fd6', edgecolor='white')",
     "ax[0].axvline(np.median(ious), color='#e0575b', ls='--',",
     "              label='trung vị %.3f' % np.median(ious))",
     "ax[0].axvspan(.5, .8, color='#3fb96b', alpha=.12, label='trần lý thuyết 0,5–0,8')",
     "ax[0].set_xlabel('IoU box lỗi ↔ polygon tấm pin'); ax[0].set_ylabel('số lỗi')",
     "ax[0].set_title('Phân bố IoU'); ax[0].legend(fontsize=8)",
     "",
     "ax[1].hist(dists, bins=22, color='#8e6fd0', edgecolor='white')",
     "ax[1].axvline(50, color='#3fb96b', ls=':', label='nửa chiều rộng tấm (50 cm)')",
     "ax[1].set_xlabel('khoảng cách tâm lỗi → tâm tấm (cm)')",
     "ax[1].set_title('Độ lệch tâm'); ax[1].legend(fontsize=8)",
     "plt.tight_layout(); plt.show()",
     "",
     "for t in [0.0, .1, .3, .5, .7]:",
     "    c = (ious >= t).sum()",
     "    print('IoU >= %.1f : %3d/%d = %5.1f %%' % (t, c, len(loi), 100*c/len(loi)))")

md("**Đọc con số này cho đúng.** IoU ở đây **không phải** IoU detection giữa dự đoán",
   "và nhãn. Nó là phần giao giữa box lỗi (~1,0 × 0,9 m) và cả tấm pin (~1,9 × 0,9 m),",
   "nên trần lý thuyết chỉ khoảng 0,5–0,8. Trung vị 0,687 là gần sát trần.",
   "",
   "Và đây là tỉ lệ **gán được**, chưa phải **gán đúng** — đề bài yêu cầu soi tay",
   "100 lỗi mẫu mới kết luận được.")

# ============================================================ D
md("---",
   "## D. Kiểm tra có vị trí nào sai không")

code("lons = np.array([x['lon'] for x in loi]); lats = np.array([x['lat'] for x in loi])",
     "ws = np.array([x['w_m'] for x in loi]); hs = np.array([x['h_m'] for x in loi])",
     "",
     "rong = (lons.max()-lons.min()) * 111320 * np.cos(np.radians(lats.mean()))",
     "cao  = (lats.max()-lats.min()) * 110540",
     "print('Phạm vi toạ độ : %.0f m × %.0f m  -> nằm trong nhà máy' % (rong, cao))",
     "print('Không có điểm nào văng ra ngoài.')",
     "print()",
     "print('Kích thước box lỗi quy ra thực địa:')",
     "print('   rộng  trung vị %.2f m   (dải %.2f – %.2f m)' % (np.median(ws), ws.min(), ws.max()))",
     "print('   cao   trung vị %.2f m   (dải %.2f – %.2f m)' % (np.median(hs), hs.min(), hs.max()))",
     "print('   tấm pin thật ~1,0 × 2,0 m  -> tỉ lệ hợp lý')",
     "",
     "ngoai = [x for x in loi if not x.get('in_panel')]",
     "xa = [x for x in loi if x.get('dist_cm') and x['dist_cm'] > 100]",
     "print()",
     "print('Lỗi không rơi trong tấm nào     : %d' % len(ngoai))",
     "print('Lỗi gán được nhưng lệch > 100 cm: %d' % len(xa))")

code("fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))",
     "",
     "sc = ax[0].scatter(lons, lats, c=[x['conf'] for x in loi], cmap='viridis',",
     "                   s=17, edgecolor='none')",
     "ax[0].set_xlabel('kinh độ'); ax[0].set_ylabel('vĩ độ')",
     "ax[0].set_title('Vị trí %d lỗi trên mặt bằng' % len(loi))",
     "ax[0].ticklabel_format(useOffset=False, style='plain')",
     "ax[0].tick_params(axis='x', rotation=30)",
     "plt.colorbar(sc, ax=ax[0], label='độ tin cậy')",
     "",
     "from collections import Counter",
     "cc = Counter(x['cls'] for x in loi)",
     "k = list(cc.keys()); v = [cc[i] for i in k]",
     "ax[1].barh(range(len(k)), v, color='#4d8fd6')",
     "ax[1].set_yticks(range(len(k))); ax[1].set_yticklabels(k, fontsize=8)",
     "ax[1].set_xlabel('số lỗi'); ax[1].set_title('Phân bố theo loại lỗi')",
     "for i, n in enumerate(v):",
     "    ax[1].text(n+1, i, str(n), va='center', fontsize=8)",
     "plt.tight_layout(); plt.show()")

# ============================================================ E
md("---",
   "## E. mAP@50, precision, recall của model phát hiện lỗi",
   "",
   "Tập test **91 ảnh / 280 đối tượng**, chia theo nhóm chuyến bay — chưa từng",
   "dùng khi train hay chọn epoch nên là con số độc lập.",
   "",
   "Ô dưới đọc kết quả đã chạy. Muốn chạy lại từ đầu thì mở ô *(tuỳ chọn)* ở cuối",
   "phần này — cần model và tập dữ liệu trên ổ D.")

code("t = doc('ket_qua/ket_qua_val/ket_qua_test_4lop.json')",
     "print('Tập: %s' % t['tap'])",
     "print('Số ảnh: %d' % t['so_anh'])",
     "print()",
     "print('%-20s %8s %8s %9s %10s' % ('Lớp','P','R','mAP@50','mAP@50-95'))",
     "print('-'*58)",
     "for k, v in t['theo_lop'].items():",
     "    print('%-20s %8.4f %8.4f %9.4f %10.4f'",
     "          % (k, v['precision'], v['recall'], v['mAP50'], v['mAP50_95']))",
     "print('-'*58)",
     "print('%-20s %8.4f %8.4f %9.4f %10.4f'",
     "      % ('TẤT CẢ', t['precision'], t['recall'], t['mAP50'], t['mAP50_95']))",
     "print()",
     "print('LƯU Ý 1: P/R trên là giá trị tại điểm F1 lớn nhất (conf ~0,64),')",
     "print('         không phải tại ngưỡng chạy thật 0,25 — xem ô kế tiếp.')",
     "print('LƯU Ý 2: chỉ 3 lớp có mặt. Lớp ModuleOpenCircuit không có đối tượng nào')",
     "print('         trong tập test nên chưa đánh giá được.')")

code("m = t['mAP_theo_nguong_IoU']",
     "x = [float(k.split('@')[1]) for k in m]; y = list(m.values())",
     "",
     "fig, ax = plt.subplots(figsize=(5.2, 3.2))",
     "ax.plot(x, y, 'o-', color='#4d8fd6')",
     "ax.axhline(t['mAP50'], color='#3fb96b', ls=':', label='mAP@50 = %.3f' % t['mAP50'])",
     "ax.set_xlabel('ngưỡng IoU'); ax.set_ylabel('mAP')",
     "ax.set_title('mAP theo ngưỡng IoU — độ chặt của box')",
     "ax.set_ylim(.85, 1); ax.legend(fontsize=8)",
     "plt.tight_layout(); plt.show()",
     "",
     "print('mAP giữ nguyên tới ngưỡng IoU 0,80 rồi mới giảm')",
     "print('-> box dự đoán bám khá sát nhãn.')")

md("### Recall thật theo từng ngưỡng conf",
   "",
   "Đo bằng cách **ghép cặp trực tiếp** dự đoán ↔ nhãn (IoU ≥ 0,5, mỗi nhãn chỉ khớp",
   "một lần), không qua đường cong mAP. Đây mới là con số phản ánh lúc chạy thật.")

code("r = doc('ket_qua/ket_qua_val/recall_theo_nguong.json')",
     "tong = r['tong_gt']",
     "cf  = sorted(r['theo_nguong'].keys(), key=float)",
     "bat = [r['theo_nguong'][c]['bat'] for c in cf]",
     "pre = [r['theo_nguong'][c]['precision'] for c in cf]",
     "thua= [r['theo_nguong'][c]['thua'] for c in cf]",
     "rec = [b/tong for b in bat]",
     "",
     "print('Tổng đối tượng thật: %d   |   ngưỡng IoU ghép cặp: %.1f' % (tong, r['iou']))",
     "print()",
     "print('%6s %14s %8s %11s %10s' % ('conf','bắt được','bỏ sót','box thừa','precision'))",
     "print('-'*54)",
     "for c in cf:",
     "    v = r['theo_nguong'][c]",
     "    sao = '  <- ngưỡng chạy thật' if c == '0.25' else ''",
     "    print('%6s %6d (%5.1f%%) %8d %11d %10.3f%s'",
     "          % (c, v['bat'], 100*v['bat']/tong, v['sot'], v['thua'], v['precision'], sao))")

code("fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))",
     "xc = [float(c) for c in cf]",
     "",
     "ax[0].plot(xc, rec, 'o-', color='#3fb96b', label='recall')",
     "ax[0].plot(xc, pre, 's-', color='#e0575b', label='precision')",
     "ax[0].axvline(.25, color='#888', ls='--', lw=1)",
     "ax[0].annotate('ngưỡng chạy thật', (.25, .55), fontsize=7.5, rotation=90,",
     "               color='#666', ha='right')",
     "ax[0].set_xlabel('ngưỡng conf'); ax[0].set_ylabel('tỉ lệ')",
     "ax[0].set_title('Đánh đổi recall ↔ precision'); ax[0].legend(fontsize=8)",
     "",
     "ax[1].plot(rec, pre, 'o-', color='#4d8fd6')",
     "for i, c in enumerate(cf):",
     "    if c in ('0.05','0.25','0.50','0.64'):",
     "        ax[1].annotate(c, (rec[i], pre[i]), fontsize=7.5,",
     "                       textcoords='offset points', xytext=(5,-3))",
     "ax[1].set_xlabel('recall'); ax[1].set_ylabel('precision')",
     "ax[1].set_title('Đường cong P–R')",
     "plt.tight_layout(); plt.show()",
     "",
     "i25 = cf.index('0.25')",
     "print('Ở ngưỡng 0,25: bắt %d/%d = %.1f %%, nhưng %d box thừa'",
     "      % (bat[i25], tong, 100*rec[i25], thua[i25]))",
     "print('-> cứ khoảng %.0f cảnh báo thì 1 cái là rác.' % (1/(1-pre[i25])))")

md("*(tuỳ chọn)* Ô dưới **chạy lại** val từ đầu. Cần model và tập dữ liệu trên ổ D,",
   "mất vài phút trên CPU. Bỏ dấu `#` để chạy.")

code("# from ultralytics import YOLO",
     "# MODEL = r'mo_hinh\\fault_obb_4class.pt'",
     "# kq = YOLO(MODEL).val(data='ket_qua/ket_qua_val/data_test_nhom.yaml', split='test',",
     "#                      imgsz=640, batch=8, device='cpu', verbose=False)",
     "# print('mAP@50 = %.4f   mAP@50-95 = %.4f' % (kq.box.map50, kq.box.map))",
     "# print('P = %.4f   R = %.4f' % (kq.box.mp, kq.box.mr))")

# ============================================================ tong ket
md("---",
   "## Tổng kết")

code("i50 = cf.index('0.50')",
     "print('='*64)",
     "print('%-40s %s' % ('CHỈ SỐ', 'KẾT QUẢ'))",
     "print('='*64)",
     "print('MODEL PHÁT HIỆN LỖI — test độc lập 91 ảnh lẻ / 280 lỗi')",
     "print('%-40s %.3f' % ('   mAP@50', t['mAP50']))",
     "print('%-40s %.3f' % ('   mAP@50-95', t['mAP50_95']))",
     "print('%-40s %.1f %%   /  %.3f' % ('   Recall / Precision @ conf 0,25',",
     "                                    100*rec[i25], pre[i25]))",
     "print('%-40s %.1f %%   /  %.3f' % ('   Recall / Precision @ conf 0,50',",
     "                                    100*rec[i50], pre[i50]))",
     "print()",
     "print('ĐỊNH VỊ')",
     "print('%-40s %.2f cm   (ngưỡng 30 cm)  ĐẠT' % ('   Sai số trên ortho, RMSE', rmse_cm))",
     "print('%-40s %.2f px   (ngưỡng 3 px)' % ('   Hiệu chuẩn H, kiểm chứng chéo', np.mean(kc)))",
     "print('%-40s %.3f' % ('   IoU box lỗi ↔ tấm pin (trung vị)', np.median(ious)))",
     "print('='*64)",
     "print('Ghép cặp dự đoán ↔ nhãn ở IoU ≥ 0,50. Ngưỡng vận hành: conf 0,25.')")

md("### Ba chỉ số chưa đo được",
   "",
   "1. **Tỉ lệ gán *đúng* tấm pin** — hiện chỉ có tỉ lệ gán *được*. Cần soi tay",
   "   100 lỗi mẫu (đang làm, xem `soi_tay_100_loi.html`).",
   "2. **Tỉ lệ trùng lặp còn sót** — biết khử trùng lặp nén 1,93 lần",
   "   (407 quan sát → 211 lỗi), nhưng sót bao nhiêu thì phải đếm tay một khu mẫu.",
   "3. **Lớp ModuleOpenCircuit** — có 416 nhãn nhưng rơi trọn vào tập train,",
   "   tập test không có ca nào nên chưa đánh giá được.",
   "",
   "Ngoài ra sai số 2,56 cm là **tương đối**; muốn số tuyệt đối phải đo RTK",
   "ngoài hiện trường.")

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

with open("tai_lieu/DANH_GIA.ipynb", "w", encoding="utf-8") as fh:
    json.dump(nb, fh, ensure_ascii=False, indent=1)

print("Da tao DANH_GIA.ipynb — %d o (%d code, %d markdown)"
      % (len(cells), sum(c["cell_type"] == "code" for c in cells),
         sum(c["cell_type"] == "markdown" for c in cells)))
