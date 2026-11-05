#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng công cụ GÁN NHÃN TAY THEO TẤM PIN trên ortho màu.

Yêu cầu của thầy: model detect chỉ làm bước gợi ý sẵn, người gán nhãn chốt lại
bằng tay. Vị trí thì phán trên **ortho MÀU** (mới đọc được mép tấm, hàng, cột),
còn có lỗi thật hay không thì phán trên **ortho NHIỆT** (vệt nóng chỉ hiện ở đó).
Nhãn gắn vào **TẤM PIN**, không phải vào vùng lỗi — đầu ra là bảng mã tấm → tình
trạng, dùng để bàn giao danh sách tấm cần thay.

Vì sao chồng được hai lớp lên nhau mà không cần biến đổi gì thêm:

    ortho.tif              25354 x 14993   px = 8,770e-08 độ   góc (108,8501605 · 11,4250098)
    ortho_nhiet_bu_rgb.tif  8451 x  4997   px = 2,631e-07 độ   góc (108,8501605 · 11,4250098)

Cùng góc trên-trái, bước pixel gấp ĐÚNG 3 lần. Tức pixel (c,r) của ortho nhiệt là
pixel (3c, 3r) của ortho màu. Ma trận H đã được dùng từ trước — `quet_loi_anh_le.py`
đưa pixel ảnh nhiệt qua H sang pixel RGB rồi mới bắn tia cắt DSM, còn
`ghep_ortho_nhiet.py` dùng H chiều ngược để dựng ortho nhiệt. Đến bước này H đã
nằm sẵn trong toạ độ, không phải áp lại lần nữa.

Chọn `ortho_nhiet_bu_rgb.tif` chứ không phải bản Metashape: đo trong
`do_khop_ortho.json` cho lệch trung vị 1,50 cm / RMSE 2,79 cm, so với 7,92 cm của
bản chưa bù. Bản Metashape (`thermal_ortho.tif`) nằm trên lưới khác hẳn, chồng lên
là phải nắn — không dùng.

Mã tấm pin dựng lại y hệt dòng 111-125 của `gan_tam_pin_4lop.py` (đánh theo dãy
rồi theo thứ tự trái→phải trong dãy). Đã đối chiếu: 544/544 lỗi rơi trong tấm cho
ra đúng mã đang có trong `loi_4lop_cuoi.json`, không lệch cái nào.

    py -3.13 ma/lam_gan_nhan_tam.py                 # dựng cả nền lẫn HTML
    py -3.13 ma/lam_gan_nhan_tam.py --bo-nen        # chỉ dựng lại HTML, giữ nền cũ
    py -3.13 ma/lam_gan_nhan_tam.py --rong 6144     # nền nhẹ hơn cho máy yếu RAM

-> gan_nhan_tam.html + nhan/nen_rgb.jpg + nhan/nen_nhiet.jpg
"""
import argparse
import csv
import json
import os
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, from_bounds

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--rong", type=int, default=8192, help="bề rộng ảnh nền xuất ra")
ap.add_argument("--le", type=int, default=80, dest="le",
                help="lề quanh khối tấm pin, tính bằng pixel ortho màu")
ap.add_argument("--chatluong", type=int, default=88, dest="cl")
ap.add_argument("--nhiet", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_bu_rgb.tif"))
ap.add_argument("--bo-nen", action="store_true", dest="bo_nen",
                help="không cắt lại ảnh nền, chỉ dựng lại HTML")
ap.add_argument("--pct", type=float, nargs=2, default=(1.0, 99.0),
                help="phân vị kéo giãn tương phản lớp nhiệt")
ap.add_argument("--co-tam", type=float, nargs=2, default=(90.0, 180.0), dest="co_tam",
                metavar=("NGAN_CM", "DAI_CM"),
                help="cỡ CHUẨN của một tấm pin, cm. Đây là số ĐẶT TAY chứ không "
                     "đo từ ảnh — nút 'về đúng cỡ một tấm' nắn theo số này")
ap.add_argument("--khong-nan-co", action="store_false", dest="nan_co",
                help="GIỮ nguyên viền best.pt dò ra. Mặc định là nắn sẵn cả 6473 "
                     "tấm về cỡ chuẩn, tấm cụt thì mọc ra phía mép ô quét")
ap.add_argument("--cat-theo-nhiet", action="store_true", dest="cat_theo_nhiet",
                help="xén lớp màu ở vùng không có nhiệt. MẶC ĐỊNH TẮT — giữ ortho "
                     "màu đầy đủ; xén hay không đều không đụng gì tới hình học")
ap.add_argument("--khong-cat-theo-nhiet", action="store_false", dest="cat_theo_nhiet",
                help="(giữ cho tương thích, đây đã là mặc định)")
ap.add_argument("--out", default=os.path.join(BASE, "cong_cu/gan_nhan_tam.html"))
# Ba cờ dưới đây để dựng TRANG MẪU (soi recall) từ cùng một bộ mã: cùng công cụ,
# cùng cách soi, chỉ khác danh sách tấm và kho nhãn. Không truyền thì ra đúng
# công cụ cũ, không đổi gì.
ap.add_argument("--chi-tam", dest="chi_tam",
                help="JSON chứa danh sách mã tấm — danh sách chỉ còn bấy nhiêu tấm")
ap.add_argument("--khoa", help="khoá localStorage riêng cho trang này")
ap.add_argument("--tieu-de", dest="tieu_de", help="tiêu đề hiện trên thanh trên cùng")
args = ap.parse_args()

t0 = time.time()
THU_MUC = os.path.join(BASE, "cong_cu/nhan")
os.makedirs(THU_MUC, exist_ok=True)

# ----------------------------------------------------------------- 1. tấm pin
panels = [np.array(p, np.float32) for p in
          json.load(open(os.path.join(BASE, "ket_qua/tam_pin_polygon_4lop.json")))]
cen = np.array([p.mean(0) for p in panels])
print("[TẤM PIN] %d tấm" % len(panels))

# --- mã tấm: y hệt gan_tam_pin_4lop.py, đừng đổi nếu không muốn lệch mã cũ
rows_sorted = np.argsort(cen[:, 1])
row_id = np.zeros(len(panels), int)
cur, last = 0, None
for i in rows_sorted:
    if last is not None and cen[i, 1] - last > 55:      # ~0,5 m -> sang dãy mới
        cur += 1
    row_id[i] = cur
    last = cen[i, 1]
code = {}
for rid in range(cur + 1):
    idx = np.where(row_id == rid)[0]
    for k, i in enumerate(idx[np.argsort(cen[idx, 0])], 1):
        code[int(i)] = "D%02d-T%03d" % (rid + 1, k)
print("[TẤM PIN] %d dãy, %d mã duy nhất" % (cur + 1, len(set(code.values()))))
ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
GSD_CM = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100

# --------------------------------------- 1b. tấm nào KHÔNG có dữ liệu nhiệt
# Ortho nhiệt chỉ phủ phần chuyến bay nhiệt đi qua, ortho màu rộng hơn. Tấm nằm
# ngoài vùng phủ thì KHÔNG PHÁN ĐƯỢC — không phải "tấm tốt". Không đánh dấu ra
# thì người gán nhãn bấm "tốt" cho cả nghìn tấm chưa từng được soi, bộ nhãn tay
# thành khai khống. Đây là lý do trường `phu` phải đi kèm mọi nhãn xuất ra.
#
# Tính TRƯỚC cửa sổ cắt, vì cửa sổ chốt theo chính vùng phủ này.
with rasterio.open(args.nhiet) as _s:
    _K = abs(ortho.transform.a) / abs(_s.transform.a)
    _oc = (ortho.transform.c - _s.transform.c) / abs(_s.transform.a)
    _or = (ortho.transform.f - _s.transform.f) / -abs(_s.transform.e)
    TH = _s.read(1)


def do_phu(p):
    tp = np.stack([p[:, 0] * _K + _oc, p[:, 1] * _K + _or], 1)
    a0, b0 = max(0, int(tp[:, 0].min())), max(0, int(tp[:, 1].min()))
    a1 = min(TH.shape[1], int(np.ceil(tp[:, 0].max())))
    b1 = min(TH.shape[0], int(np.ceil(tp[:, 1].max())))
    if a1 <= a0 or b1 <= b0:
        return 0
    m = np.zeros((b1 - b0, a1 - a0), np.uint8)
    cv2.fillConvexPoly(m, (tp - [a0, b0]).astype(np.int32), 1)
    return int(round(100 * float((TH[b0:b1, a0:a1][m > 0] > 0).mean()))) if m.sum() else 0


PHU = [do_phu(p) for p in panels]
del TH
thieu = sum(1 for v in PHU if v < 50)
print("[NHIỆT]  %d/%d tấm không đủ dữ liệu nhiệt để phán (<50%% phủ) — %.1f%%"
      % (thieu, len(PHU), 100.0 * thieu / len(PHU)))

# --------------------------------------------- 1c. vùng lõi có ảnh nhiệt
# Rìa nhà máy có ảnh MÀU mà không có ảnh NHIỆT — thấy tấm pin nhưng không phán
# được lỗi nào ở đó. KHÔNG cắt cứng lúc dựng: chỉ đo lấy hộp bao của khối tấm CÓ
# nhiệt rồi giao cho công cụ, để người soi tự bật tắt. Cắt cứng thì mỗi lần đổi ý
# phải dựng lại 10 giây và mất luôn khả năng ngó ra ngoài xem có gì.
_co = [i for i in range(len(panels)) if PHU[i] >= 50]
_pv = np.concatenate([panels[i] for i in _co])
VC0, VC1 = float(_pv[:, 0].min() - args.le), float(_pv[:, 0].max() + args.le)
VR0, VR1 = float(_pv[:, 1].min() - args.le), float(_pv[:, 1].max() + args.le)
RIA = [not (VC0 <= cen[i, 0] <= VC1 and VR0 <= cen[i, 1] <= VR1)
       for i in range(len(panels))]
MA_TAM = [code[i] for i in range(len(panels))]
print("[VÙNG]   khối tấm có nhiệt bao %d/%d tấm; %d tấm nằm ở rìa ngoài"
      % (len(panels) - sum(RIA), len(panels), sum(RIA)))
print("         trong vùng lõi vẫn còn %d tấm thiếu nhiệt — lỗ nằm TRONG khối, "
      "soi bằng ảnh gốc"
      % sum(1 for i in range(len(panels)) if not RIA[i] and PHU[i] < 50))

# ------------------------------------------------------------- 2. cửa sổ cắt
# Lấy theo bao của CHÍNH khối tấm pin, không mượn FRAME của so_sanh_model.html:
# frame đó (c0=1163, r0=2274) cắt mất mép trái và mép trên của khối tấm — tấm
# ngoài cùng bắt đầu ở cột 1013, hàng 1363. Công cụ này phải thấy đủ 6473 tấm.
#
# Phải bao CẢ VỊ TRÍ LỖI, không chỉ tấm pin: 41 lỗi không gán được mã rơi cách
# tấm gần nhất 3-8 m. Chỉ chừa lề 80 px (~2 m) quanh khối tấm thì chúng nằm ngoài
# ảnh, bị vẽ lên nền trang đen — nhìn ra như thủng dữ liệu, mà thật ra là chiếu
# trượt ra ngoài khung.
det = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))

# ------------------------------------- 1d. nắn mọi tấm về đúng cỡ chuẩn
# Nắn sẵn để người soi khỏi phải bấm N từng tấm. Nhưng nắn KHÔNG phải chỉ đổi
# kích thước quanh tâm: 1348 tấm bị mép ô quét cắt cụt, và TÂM CỦA MẢNH CỤT
# KHÔNG PHẢI TÂM TẤM THẬT — phóng quanh tâm đó thì đúng cỡ mà sai chỗ, tức là
# vẫn hỏng, chỉ hỏng kín đáo hơn.
#
# Phần bị mất nằm về phía MÉP Ô QUÉT. Nên tấm cụt thì mọc RA PHÍA MÉP, giữ nguyên
# mặt phía trong. Tấm không cụt thì phóng quanh tâm, tâm không đổi.
#
# Mã tấm đánh từ TRƯỚC bước này nên không đổi — đừng đảo thứ tự.
if args.nan_co:
    _side = 1024 * 2
    _cua = []
    for _tx, _ty in sorted({(int(d["ocol"] // _side), int(d["orow"] // _side))
                            for d in det}):
        _c = max(0, min(_tx * _side - _side // 2, ortho.width - _side))
        _r = max(0, min(_ty * _side - _side // 2, ortho.height - _side))
        _cua.append((_c, _r, _c + _side, _r + _side))
    W0, H0 = args.co_tam[1] / GSD_CM, args.co_tam[0] / GSD_CM   # dài, ngắn (px)

    # HƯỚNG lấy từ các tấm LÀNH, không lấy từ chính mảnh cụt. Mảnh cụt cao hơn
    # rộng thì "trục dài" của nó là trục ĐỨNG, nắn ra box xoay 90 độ nằm chỏng
    # chơ — đã thử và hỏng đúng như vậy ở D20-T136, D11-T146.
    # Trung bình góc lấy theo vòng tròn 2*theta vì hướng chỉ có nghĩa mod 180 độ.
    _lanh, _goc = [], []
    for p in panels:
        e1, e2 = p[1] - p[0], p[2] - p[1]
        l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
        ok = (abs(max(l1, l2) - W0) < 0.15 * W0) and (abs(min(l1, l2) - H0) < 0.15 * H0)
        _lanh.append(ok)
        if ok:
            d = e1 if l1 >= l2 else e2
            _goc.append(np.arctan2(d[1], d[0]))
    _g2 = np.array(_goc) * 2
    GOC_CHUAN = float(np.arctan2(np.sin(_g2).mean(), np.cos(_g2).mean()) / 2)
    U_CHUAN = np.array([np.cos(GOC_CHUAN), np.sin(GOC_CHUAN)])
    print("[NẮN]    hướng chuẩn %.2f độ, suy từ %d/%d tấm lành"
          % (np.degrees(GOC_CHUAN), sum(_lanh), len(panels)))

    def huong_mep(x, y):
        """Vector đơn vị chỉ RA mép ô quét gần nhất; None nếu không nằm ô nào."""
        tot = None
        for a, b, c, d_ in _cua:
            if not (a <= x < c and b <= y < d_):
                continue
            for kc, v in ((x - a, (-1., 0.)), (c - x, (1., 0.)),
                          (y - b, (0., -1.)), (d_ - y, (0., 1.))):
                if tot is None or kc < tot[0]:
                    tot = (kc, np.array(v))
        return None if tot is None else tot[1]

    def nan_mot(p, lanh):
        cx, cy = p.mean(0)
        e1, e2 = p[1] - p[0], p[2] - p[1]
        l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
        # tấm lành thì tin hướng của chính nó; tấm cụt thì dùng hướng chuẩn
        u = ((e1 / l1) if l1 >= l2 else (e2 / l2)) if lanh else U_CHUAN
        v = np.array([-u[1], u[0]])                       # trục NGẮN
        # phần thiếu đo THEO TRỤC u/v, không theo cạnh nào dài hơn — mảnh cụt
        # có thể thiếu ở đúng trục dài mà cạnh đo được lại là trục ngắn
        pu = np.array([abs(float((q - [cx, cy]) @ u)) for q in p]).max() * 2
        pv = np.array([abs(float((q - [cx, cy]) @ v)) for q in p]).max() * 2
        tw, th = W0 - pu, H0 - pv                         # phần còn thiếu
        if max(tw / W0, th / H0) > 0.15:
            ra = huong_mep(cx, cy)
            if ra is not None:
                # dồn hết phần thiếu về phía mép: tâm dịch nửa phần thiếu
                d_ = (abs(float(u @ ra)) * tw + abs(float(v @ ra)) * th) / 2
                cx += float(ra[0]) * d_
                cy += float(ra[1]) * d_
        return np.array([[cx + u[0]*W0/2*a - v[0]*H0/2*b,
                          cy + u[1]*W0/2*a - v[1]*H0/2*b]
                         for a, b in ((-1,-1), (1,-1), (1,1), (-1,1))], np.float32)

    # CHỈ nắn tấm CÓ LỖI — đó là tấm người soi phải phán. Nắn cả 6473 tấm thì
    # lộ ra chuyện khác: ở mép ô quét, cùng một tấm thật bị detect hai lần thành
    # hai mảnh cụt, khử trùng lặp cũ (cách tâm 40 px) không bắt được. Nắn cả hai
    # về đủ cỡ là chúng trùm lên nhau — đo được 787 cặp IoU>0,3, trước khi nắn là 0.
    # Tấm có lỗi nằm giữa ô quét chứ không ở mép, nên nắn nhóm này thì không dính.
    ma_co_loi = {d.get("panel_code") for d in det if d.get("panel_code")}
    _can = [i for i in range(len(panels)) if MA_TAM[i] in ma_co_loi]
    _tam_cu = cen.copy()
    _cut = 0
    for i in _can:
        if not _lanh[i]:
            _cut += 1
        panels[i] = nan_mot(panels[i], _lanh[i])
    cen = np.array([p.mean(0) for p in panels])
    _doi = np.linalg.norm(cen - _tam_cu, axis=1) * GSD_CM
    print("[NẮN]    nắn %d/%d tấm — chỉ tấm CÓ LỖI — về %.0f x %.0f cm "
          "(--khong-nan-co để tắt)"
          % (len(_can), len(panels), args.co_tam[0], args.co_tam[1]))
    print("         trong đó %d tấm cụt quá 15%% -> mọc ra phía mép ô quét; "
          "tâm dịch trung vị %.0f cm, xa nhất %.0f cm"
          % (_cut, np.median(_doi[_doi > 1]) if (_doi > 1).any() else 0, _doi.max()))

_dc, _dr = [], []
for d in det:
    _dc.append(d["ocol"])
    _dr.append(d["orow"])
    for lo, la in (d.get("poly") or []):
        _pc, _pr = ~ortho.transform * (lo, la)
        _dc.append(_pc)
        _dr.append(_pr)
pv = np.concatenate(panels)
c0 = max(0, int(min(pv[:, 0].min(), min(_dc))) - args.le)
r0 = max(0, int(min(pv[:, 1].min(), min(_dr))) - args.le)
c1 = min(ortho.width, int(max(pv[:, 0].max(), max(_dc))) + args.le + 1)
r1 = min(ortho.height, int(max(pv[:, 1].max(), max(_dr))) + args.le + 1)
GW, GH = c1 - c0, r1 - r0
OW = min(args.rong, GW)
OH = max(1, int(round(GH * OW / GW)))
S = OW / float(GW)                                  # ortho px -> px ảnh nền
print("[CỬA SỔ] ortho px c%d..%d r%d..%d  (%d x %d)" % (c0, c1, r0, r1, GW, GH))
print("[NỀN]    %d x %d px, %.2f cm/px" % (OW, OH, GSD_CM / S))

LON0 = ortho.transform.c + ortho.transform.a * c0
LON1 = ortho.transform.c + ortho.transform.a * c1
LAT0 = ortho.transform.f + ortho.transform.e * r0       # mép TRÊN
LAT1 = ortho.transform.f + ortho.transform.e * r1


def ghi(ten, im):
    p = os.path.join(THU_MUC, ten)
    cv2.imwrite(p, im, [cv2.IMWRITE_JPEG_QUALITY, args.cl])
    print("         -> %s  (%.1f MB, %.0fs)"
          % (p, os.path.getsize(p) / 1e6, time.time() - t0))


TRONG = (26, 26, 26)         # màu của vùng không có dữ liệu, dùng chung hai lớp

if not args.bo_nen:
    # Cắt lớp NHIỆT trước, vì mặt nạ vùng trống của nó dùng để xén luôn lớp màu.
    print("[NỀN]    cắt lớp nhiệt (%s)..." % os.path.basename(args.nhiet))
    with rasterio.open(args.nhiet) as s:
        # Quy qua lon/lat rồi ép về ĐÚNG (OH, OW) -> hai lớp trùng khít từng pixel,
        # gạt qua lại không xê dịch. Không cắt theo pixel vì bước pixel khác nhau.
        w = from_bounds(LON0, LAT1, LON1, LAT0, s.transform)
        g = s.read(1, window=w, out_shape=(OH, OW), boundless=True, fill_value=0,
                   resampling=rasterio.enums.Resampling.average)
    trong = g == 0
    v = g[~trong]
    lo, hi = np.percentile(v, args.pct) if v.size else (0.0, 1.0)
    if hi <= lo:
        lo, hi = float(g.min()), float(g.max() + 1)
    out = cv2.applyColorMap(
        np.clip((g.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8),
        cv2.COLORMAP_INFERNO)
    out[trong] = TRONG
    print("         phân vị %g-%g%% -> %.0f..%.0f, %.1f%% khung trống"
          % (args.pct[0], args.pct[1], lo, hi, 100.0 * trong.mean()))
    ghi("nen_nhiet.jpg", out)
    del out, g

    print("[NỀN]    cắt lớp màu...")
    im = ortho.read([1, 2, 3], window=Window(c0, r0, GW, GH), out_shape=(3, OH, OW),
                    resampling=rasterio.enums.Resampling.average)
    im = cv2.merge([im[2], im[1], im[0]])
    if args.cat_theo_nhiet:
        # Xén lớp màu theo đúng vùng phủ nhiệt. Lý do: lỗi chỉ suy ra được từ ảnh
        # nhiệt, nên chỗ nào không có nhiệt thì ảnh màu ở đó không dùng để phán
        # được — để nguyên chỉ tổ làm người soi tưởng vùng đó đã kiểm rồi.
        # MORPH_OPEN xoá các đốm trống lẻ tẻ bên trong vùng đã phủ (nhiễu ghép),
        # giữ lại đúng mảng trống thật sự lớn.
        mn = cv2.morphologyEx(trong.astype(np.uint8), cv2.MORPH_OPEN,
                              np.ones((9, 9), np.uint8)).astype(bool)
        im[mn] = TRONG
        print("         xén theo vùng phủ nhiệt: bỏ %.1f%% khung ảnh màu "
              "(--khong-cat-theo-nhiet để giữ nguyên)" % (100.0 * mn.mean()))
    ghi("nen_rgb.jpg", im)
    del im

# ------------------- 3. tấm thiếu nhiệt: còn ẢNH GỐC nào nhìn thấy không?
# "Ortho nhiệt không có" KHÁC "ảnh nhiệt không có". Ortho chỉ dựng từ 396 ảnh đạt
# bộ lọc; 202 ảnh bị loại (trễ chụp / rung) vẫn còn nguyên trên đĩa. Nên phải
# tách ba nhóm, vì việc phải làm với mỗi nhóm khác hẳn nhau:
#     0 = không ảnh nào chụp tới  -> chỉ bay lại mới soi được
#     1 = chỉ ảnh đã bị loại thấy -> moi lại được, nhưng ảnh xấu
#     2 = ảnh đạt lọc vẫn thấy    -> ortho bỏ sót, vá được
# Chiếu ngược: ECEF -> hệ camera -> pixel RGB -> qua H^-1 -> pixel ảnh nhiệt.
root = ET.parse(os.path.join(EXP, "cameras.xml")).getroot()
chunk = root.find(".//chunk")
_s = chunk.find(".//sensor[@id='0']")
_res = _s.find("resolution")
_cal = _s.find("calibration[@class='adjusted']")
_g = lambda t: float(_cal.find(t).text) if _cal.find(t) is not None else 0.0
IW_, IH_, F_, CX_, CY_ = (int(_res.get("width")), int(_res.get("height")),
                          _g("f"), _g("cx"), _g("cy"))
_tr = chunk.find(".//component").find("transform")
R_ch = np.array(list(map(float, _tr.find("rotation").text.split()))).reshape(3, 3)
T_ch = np.array(list(map(float, _tr.find("translation").text.split())))
S_ch = float(_tr.find("scale").text)
cams = {c.get("label").split("_")[2]:
        np.array(list(map(float, c.find("transform").text.split()))).reshape(4, 4)
        for c in chunk.findall(".//camera") if c.find("transform") is not None}

_ks = sorted(cams, key=int)
_C = {k: cams[k][:3, 3] for k in _ks}
_spd = {_ks[i]: np.linalg.norm(_C[_ks[i + 1]] - _C[_ks[i - 1]]) * S_ch / 2
        for i in range(1, len(_ks) - 1)}
_med = np.median(list(_spd.values()))
nhanh = {k for k in _ks if _spd.get(k, _med) > 0.6 * _med}

# LÝ DO loại, giữ riêng từng loại chứ không gộp — "ảnh đã bị loại" nói trống không
# thì người soi tưởng ảnh mờ, trong khi phần lớn ảnh vẫn nét, chỉ là ĐẶT SAI CHỖ.
d_tre = json.load(open(os.path.join(BASE, "du_lieu/anh_tre_chup_full.json"), encoding="utf-8"))
d_rung = json.load(open(os.path.join(BASE, "du_lieu/anh_rung.json"), encoding="utf-8"))
bo_tre = {str(x) for x in d_tre.get("anh_nen_loai", [])}
bo_rung = {str(x) for x in d_rung.get("anh_nen_loai", [])}
LECH = {r["seq"]: r for r in d_tre.get("chi_tiet", [])}
NGUONG_LECH_CM = float(d_tre.get("nguong_cm", 21.0))
dat_loc = nhanh - bo_tre - bo_rung

Hinv = np.linalg.inv(np.array(json.load(
    open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))["H_thermal_to_rgb"]))
TW_, THh_ = 640, 512

_lon = ortho.transform.c + ortho.transform.a * cen[:, 0].astype(np.float64)
_lat = ortho.transform.f + ortho.transform.e * cen[:, 1].astype(np.float64)
with rasterio.open(os.path.join(EXP, "dsm.tif")) as _d:
    _DSM = _d.read(1); _ND = _d.nodata
    _zm = float(np.median(_DSM[_DSM != _ND]))
    _rr = np.clip(((_lat - _d.transform.f) / _d.transform.e).astype(int), 0, _DSM.shape[0]-1)
    _cc = np.clip(((_lon - _d.transform.c) / _d.transform.a).astype(int), 0, _DSM.shape[1]-1)
_z = _DSM[_rr, _cc].astype(np.float64)
_z[_z == _ND] = _zm
_P = np.stack(Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
              .transform(_lon, _lat, _z), 1)

def vao_anh_nhiet(M, pts):
    """ECEF -> pixel ảnh nhiệt của camera M. Bỏ qua méo ống kính, y như
    quet_loi_anh_le.py."""
    Cc = S_ch * (R_ch @ M[:3, 3]) + T_ch
    Rm = R_ch @ M[:3, :3]
    dv = (pts - Cc) @ Rm                      # = Rm^T @ v, Rm trực giao
    with np.errstate(invalid="ignore", divide="ignore"):
        u = dv[:, 0] / dv[:, 2] * F_ + IW_ / 2.0 + CX_
        v = dv[:, 1] / dv[:, 2] * F_ + IH_ / 2.0 + CY_
    w = Hinv[2, 0] * u + Hinv[2, 1] * v + Hinv[2, 2]
    return ((Hinv[0, 0] * u + Hinv[0, 1] * v + Hinv[0, 2]) / w,
            (Hinv[1, 0] * u + Hinv[1, 1] * v + Hinv[1, 2]) / w,
            dv[:, 2] > 0)


n_tot = np.zeros(len(panels), np.int16)
n_loai = np.zeros(len(panels), np.int16)
# Ảnh tốt nhất để soi tấm này: ảnh mà tấm rơi gần TÂM khung nhất. Xa tâm thì méo
# ống kính và sai số H đều lớn hơn, mà đây là ảnh người ta sẽ nhìn để phán.
best = [None] * len(panels)
best_d = np.full(len(panels), 1e18)
for k, M in cams.items():
    ut, vt, truoc = vao_anh_nhiet(M, _P)
    thay = truoc & (ut >= 0) & (ut < TW_) & (vt >= 0) & (vt < THh_)
    if k in dat_loc:
        n_tot += thay
    else:
        n_loai += thay
    # ảnh đạt lọc luôn thắng ảnh bị loại, nên cộng phạt cho ảnh bị loại
    d = np.hypot(ut - TW_ / 2.0, vt - THh_ / 2.0) + (0 if k in dat_loc else 1e6)
    tot_hon = thay & (d < best_d)
    best_d = np.where(tot_hon, d, best_d)
    for i in np.flatnonzero(tot_hon):
        best[i] = k

NGUON = [int(2 if a else (1 if b else 0)) for a, b in zip(n_tot, n_loai)]
NANH = [int(a) for a in n_tot]
NXAU = [int(b) for b in n_loai]
_t = [i for i in range(len(panels)) if PHU[i] < 50]
print("[ẢNH GỐC] %d/%d ảnh đạt bộ lọc. Trong %d tấm thiếu ortho nhiệt:"
      % (len(dat_loc), len(cams), len(_t)))
for v, ten in [(0, "không ảnh nào chụp tới  -> phải bay lại"),
               (1, "chỉ ảnh đã bị loại thấy -> moi lại được, ảnh xấu"),
               (2, "ảnh đạt lọc vẫn thấy    -> ortho bỏ sót, vá được")]:
    n = sum(1 for i in _t if NGUON[i] == v)
    print("          %d = %-40s %4d  (%.1f%%)" % (v, ten, n, 100.0 * n / max(1, len(_t))))

# --------------------------------------------------- 4. tấm pin -> px ảnh nền
to_lon = lambda c: ortho.transform.c + ortho.transform.a * c
to_lat = lambda r: ortho.transform.f + ortho.transform.e * r

POLY, MA, LL = [], [], []
for i, p in enumerate(panels):
    # làm phẳng để file nhẹ: [x0,y0,x1,y1,x2,y2,x3,y3] mỗi tấm, px ảnh nền
    POLY.append([round(float((v - (c0 if k == 0 else r0)) * S), 1)
                 for x, y in p for k, v in enumerate((x, y))])
    MA.append(MA_TAM[i])
    # float() bắt buộc: cen là float32, round() giữ nguyên kiểu numpy và json
    # không xuất được kiểu đó.
    LL.append([round(float(to_lon(cen[i, 0])), 8), round(float(to_lat(cen[i, 1])), 8)])

# ---------------------------------------------------------- 4. gợi ý của model
idx_ma = {m: i for i, m in enumerate(MA)}
GOI_Y = {}          # chỉ số tấm -> danh sách lỗi model thấy trên tấm đó
LOI = []            # mọi phát hiện, để vẽ lên bản đồ
ngoai = 0
ngoai_khung = 0
# Box của model là CẢ TẤM PIN chứ không phải vệt nóng: trung vị 0,95 x 1,85 m so
# với tấm 0,88 x 1,76 m, IoU 0,716, lệch tâm 16 cm. Nên vẽ nguyên khung box —
# chấm một dấu ở tâm dễ làm người soi tưởng model chỉ đúng vào ô nóng.
for d in det:
    x = round(float((d["ocol"] - c0) * S), 1)
    y = round(float((d["orow"] - r0) * S), 1)
    # Lỗi rơi ngoài khung thì BỎ HẲN, đừng vẽ: canvas không bị ảnh chặn nên nó
    # sẽ hiện lơ lửng trên nền trang đen, nhìn ra như dữ liệu thủng.
    if not (0 <= x <= OW and 0 <= y <= OH):
        ngoai_khung += 1
        continue
    hop = []
    for lo, la in (d.get("poly") or []):
        pc, pr = ~ortho.transform * (lo, la)
        hop += [round(float((pc - c0) * S), 1), round(float((pr - r0) * S), 1)]
    LOI.append([x, y, d["cls"], round(float(d["conf"]), 3),
                d.get("panel_code"), int(d.get("n") or 1), bool(d.get("in_panel")),
                hop if len(hop) == 8 else None])
    j = idx_ma.get(d.get("panel_code"))
    if j is None:
        ngoai += 1
        continue
    GOI_Y.setdefault(j, []).append([d["cls"], round(float(d["conf"]), 3),
                                    int(d.get("n") or 1), bool(d.get("in_panel"))])

# Lớp gợi ý cho mỗi tấm: lấy lỗi có conf cao nhất. Tấm có nhiều lỗi thì người soi
# tự thấy trên khung chi tiết, nút bấm vẫn cho chọn lại.
GOI = {}
for j, ds in GOI_Y.items():
    ds.sort(key=lambda a: -a[1])
    GOI[j] = [ds[0][0], ds[0][1], len(ds), max(a[2] for a in ds)]

print("[GỢI Ý]  %d/%d lỗi trong khung -> %d tấm được model đánh dấu "
      "(%d lỗi không gán được mã tấm, %d lỗi rơi ngoài khung đã bỏ)"
      % (len(LOI), len(det), len(GOI), ngoai, ngoai_khung))

# ------------------------- 5b. cắt ẢNH NHIỆT GỐC cho những tấm cần soi kỹ
# Vì sao cần: model detect trên ẢNH GỐC rồi mới chiếu lên ortho, mà ortho chỉ
# ghép từ 396/416 ảnh detect chạy qua. 14/603 lỗi chỉ thấy được từ 20 ảnh không
# vào ortho -> trên ortho chúng nằm giữa vùng đen, người soi không có gì để nhìn.
# Cắt thẳng từ ảnh gốc thì soi được đúng cái model đã nhìn.
#
# Chỉ cắt cho tấm ĐÁNG soi (model đánh dấu, hoặc thiếu ortho nhưng còn ảnh gốc) —
# cắt cả 6473 tấm thì ra ~230 MB mà 5000 tấm trong đó không ai mở tới.
CAN = sorted(set(list(GOI.keys())
                 + [i for i in range(len(panels)) if PHU[i] < 50 and NGUON[i] > 0]))
CAN = [i for i in CAN if best[i]]
CO_ANH = 256
GOC = {}
_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)


def khung_goc(i):
    """Khung cắt của tấm i trên ảnh nhiệt gốc `best[i]`.
    Trả về (x0, y0, n, viền tấm quy về 0..1 của khung)."""
    q = panels[i].astype(np.float64)
    qp = np.stack(_ecef.transform(
        ortho.transform.c + ortho.transform.a * q[:, 0],
        ortho.transform.f + ortho.transform.e * q[:, 1],
        np.full(4, _z[i])), 1)
    ut, vt, _ = vao_anh_nhiet(cams[best[i]], qp)
    nua = max(np.ptp(ut), np.ptp(vt)) * 0.95 + 6
    x0 = int(round(float(ut.mean()) - nua))
    y0 = int(round(float(vt.mean()) - nua))
    n = max(8, int(round(nua * 2)))
    return x0, y0, n, [round(float(v), 4) for x, y in zip(ut, vt)
                       for v in ((x - x0) / n, (y - y0) / n)]


if not args.bo_nen:
    os.makedirs(os.path.join(THU_MUC, "goc"), exist_ok=True)
    duong = {r["seq"]: r["path_thermal"] for r in csv.DictReader(
        open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}
    theo_anh = {}
    for i in CAN:
        theo_anh.setdefault(best[i], []).append(i)
    print("[ẢNH GỐC] cắt %d tấm từ %d ảnh nhiệt..." % (len(CAN), len(theo_anh)))
    thieu_file = 0
    for seq, ds in sorted(theo_anh.items()):
        p = duong.get(seq)
        im = cv2.imread(p) if p and os.path.exists(p) else None
        if im is None:
            thieu_file += len(ds)
            continue
        for i in ds:
            x0, y0, n, vien = khung_goc(i)
            # cắt kiểu boundless: tấm sát mép ảnh thì phần thiếu để đen
            a = np.zeros((n, n, 3), np.uint8)
            sx0, sy0 = max(0, x0), max(0, y0)
            sx1, sy1 = min(im.shape[1], x0 + n), min(im.shape[0], y0 + n)
            if sx1 > sx0 and sy1 > sy0:
                a[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = im[sy0:sy1, sx0:sx1]
            cv2.imwrite(os.path.join(THU_MUC, "goc", "%d.jpg" % i),
                        cv2.resize(a, (CO_ANH, CO_ANH), interpolation=cv2.INTER_LANCZOS4),
                        [cv2.IMWRITE_JPEG_QUALITY, 86])
            GOC[str(i)] = [seq, vien, int(best_d[i] < 1e6)]
    print("          -> nhan/goc/  (%d tấm, %d tấm thiếu file ảnh)"
          % (len(GOC), thieu_file))
else:
    # --bo-nen: giữ nguyên ảnh đã cắt, dựng lại danh mục từ file có sẵn trên đĩa
    for i in CAN:
        if os.path.exists(os.path.join(THU_MUC, "goc", "%d.jpg" % i)):
            GOC[str(i)] = [best[i], khung_goc(i)[3], int(best_d[i] < 1e6)]
    print("[ẢNH GỐC] dùng lại %d khung đã cắt trong nhan/goc/" % len(GOC))

# ---------------------------------------------------------------- 5. xuất HTML
DATA = {
    "nen": {"rgb": "nhan/nen_rgb.jpg", "nhiet": "nhan/nen_nhiet.jpg",
            "w": OW, "h": OH},
    "cua_so": {"c0": c0, "r0": r0, "gw": GW, "gh": GH, "s": S,
               "lon0": LON0, "lon1": LON1, "lat0": LAT0, "lat1": LAT1,
               "cm_px": float(GSD_CM / S)},
    "nguon_nhiet": os.path.basename(args.nhiet),
    "poly": POLY, "ma": MA, "ll": LL, "phu": PHU,
    # hộp bao khối tấm CÓ nhiệt, px ảnh nền — công cụ dùng để bật tắt ẩn rìa
    # Cỡ chuẩn ĐẶT TAY, cm — không suy từ ảnh. Kèm luôn cỡ ĐO ĐƯỢC (trung vị của
    # chính các box best.pt) để trong công cụ đối chiếu được hai số với nhau.
    "co_tam_cm": [round(args.co_tam[0], 1), round(args.co_tam[1], 1)],
    "co_do_duoc_cm": [round(float(np.median([min(np.linalg.norm(p[1]-p[0]),
                                                 np.linalg.norm(p[2]-p[1]))
                                             for p in panels])) * GSD_CM, 1),
                      round(float(np.median([max(np.linalg.norm(p[1]-p[0]),
                                                 np.linalg.norm(p[2]-p[1]))
                                             for p in panels])) * GSD_CM, 1)],
    "vung": [round((VC0 - c0) * S, 1), round((VR0 - r0) * S, 1),
             round((VC1 - c0) * S, 1), round((VR1 - r0) * S, 1)],
    "ria": [1 if v else 0 for v in RIA],
    "nguon": NGUON, "n_anh": NANH, "n_anh_xau": NXAU,
    # chỉ số tấm -> [seq ảnh nhiệt gốc, viền tấm 0..1, ảnh có đạt bộ lọc không]
    "goc": GOC, "goc_thu_muc": "nhan/goc/",
    # seq -> [lệch thật (cm), do_net, mã lý do loại: 1=trễ chụp 2=rung 4=quay đầu]
    "anh": {s: [round(float(LECH[s]["lech_cm"]), 1) if s in LECH else None,
                round(float(LECH[s]["do_net"]), 2) if s in LECH else None,
                (1 if s in bo_tre else 0) + (2 if s in bo_rung else 0)
                + (4 if s not in nhanh else 0)]
            for s in sorted({v[0] for v in GOC.values()})},
    "nguong_lech_cm": round(NGUONG_LECH_CM, 1),
    "goi_y": {str(k): v for k, v in GOI.items()},
    "loi": LOI,
}

# ------------------------------------------------------- 5c. tuỳ chọn TRANG MẪU
if args.khoa:
    DATA["khoa"] = args.khoa
if args.tieu_de:
    DATA["tieu_de"] = args.tieu_de
if args.chi_tam:
    d = json.load(open(args.chi_tam, encoding="utf-8"))
    ma_can = d["ma_tam"] if isinstance(d, dict) else d
    idx = {m: k for k, m in enumerate(MA)}
    thieu = [m for m in ma_can if m not in idx]
    if thieu:
        raise SystemExit("[LỖI] %d mã tấm trong %s không có trong công cụ: %s"
                         % (len(thieu), args.chi_tam, ", ".join(thieu[:5])))
    DATA["chi_tam"] = sorted(idx[m] for m in ma_can)
    print("[MẪU]    khoá danh sách vào %d tấm từ %s"
          % (len(DATA["chi_tam"]), os.path.basename(args.chi_tam)))

HTML = open(os.path.join(BASE, "cong_cu/mau_gan_nhan_tam.html"), encoding="utf-8").read()
out = HTML.replace("/*__DATA__*/null", json.dumps(DATA, ensure_ascii=False,
                                                  separators=(",", ":"), default=float))
with open(args.out, "w", encoding="utf-8") as fh:
    fh.write(out)
print("\n-> %s  (%.2f MB)" % (args.out, os.path.getsize(args.out) / 1e6))
print("   mở thẳng bằng trình duyệt, KHÔNG được tách rời thư mục nhan/")
print("   %.0fs" % (time.time() - t0))
