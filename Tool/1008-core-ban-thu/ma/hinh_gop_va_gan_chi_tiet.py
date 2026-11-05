#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng hình cho hai bước SAU khi chiếu — gộp trùng và gán vào tấm pin.

Chuỗi chiếu dừng ở "mỗi box ra 4 toạ độ GPS". Nhưng một tấm pin nằm trong 5–10 ảnh
chồng phủ, nên cùng một lỗi bị chiếu xuống nhiều lần, mỗi lần lệch một ít. Hai hình
này vẽ đúng chỗ đó:

  G0  tám ảnh nhiệt 8 ảnh nhiệt GỐC cùng thấy một lỗi, cắt quanh box, xếp thành dải.
                    Cho thấy chồng lấn là chuyện GIỮA CÁC ẢNH NHIỆT với nhau —
                    cùng một tấm pin, tám góc nhìn, tám vị trí khác nhau trong khung.
  G1  gộp trùng     8 vết của cùng một lỗi rơi xuống, tản trong bán kính 36 cm,
                    gộp bán kính 0,60 m thành MỘT lỗi. Kèm biểu đồ phân bố `n`
                    trên cả 603 lỗi — vì sao 0,60 m chứ không phải số khác.
  G2  gán tấm pin   vết đã gộp chồng lên polygon tấm pin, IoU 0,703 -> mã D20-T131.
                    Kèm phản ví dụ: dựng hộp từ w_m/h_m thì vuông góc với tấm,
                    IoU tụt gần 0.

Số lấy từ lỗi THẬT `D20-T131` (n=8) — chính ca in trong sơ đồ pipeline ở Hình 1.
Tám vết thành phần chạy lại bằng chuỗi chiếu gốc, không phải số bịa.

    py -3.13 ma/hinh_gop_va_gan_chi_tiet.py
    py -3.13 ma/hinh_gop_va_gan_chi_tiet.py --chi G2
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
import rasterio

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
MODEL = r"mo_hinh\fault_obb_4class.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="G0, G1 hoặc G2; bỏ trống thì vẽ cả ba")
ap.add_argument("--vet", default=os.path.join(BASE, "ket_qua/_tam_8vet.json"))
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

CAM = (0, 77, 194)
XANH = (158, 95, 47)
LUC = (70, 107, 30)
TRANG = (255, 255, 255)
DEN = (32, 22, 27)
XAM = (148, 131, 139)
DO = (64, 48, 176)

D = json.load(open(args.vet, encoding="utf-8"))
GOP = D["gop"]
VET = D["vet"]
LOI = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
TAM = json.load(open(os.path.join(BASE, "ket_qua/tam_pin_polygon_4lop.json"),
                     encoding="utf-8"))
ort = rasterio.open(os.path.join(EXP, "ortho.tif"))


def chu(im, s, xy, co=0.6, mau=TRANG, day=1, nen=None):
    ff = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), _ = cv2.getTextSize(s, ff, co, day)
    x, y = xy
    if nen is not None:
        cv2.rectangle(im, (x - 5, y - h - 6), (x + w + 5, y + 6), nen, -1)
    cv2.putText(im, s, (x, y), ff, co, mau, day, cv2.LINE_AA)
    return w


def cua_so(lon0, lat0, met):
    """Cắt ortho màu quanh (lon0, lat0), nửa cạnh `met`. Trả về ảnh + hàm đổi toạ độ."""
    dlon = met / (111320 * np.cos(np.radians(lat0)))
    dlat = met / 110570
    r0, c0 = ort.index(lon0 - dlon, lat0 + dlat)
    r1, c1 = ort.index(lon0 + dlon, lat0 - dlat)
    r0, r1 = max(0, min(r0, r1)), min(ort.height, max(r0, r1))
    c0, c1 = max(0, min(c0, c1)), min(ort.width, max(c0, c1))
    win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
    arr = ort.read([1, 2, 3], window=win)
    im = np.transpose(arr, (1, 2, 0))[:, :, ::-1].copy()
    T_ = ort.window_transform(win)
    return im, T_, (c0, r0)


# ----------------------------------------------------------- G0 · tám ảnh nhiệt
def ve_G0():
    """Tám ảnh nhiệt GỐC cùng thấy một lỗi — chồng lấn là chuyện giữa các ảnh nhiệt.

    Mỗi ô cắt quanh box trên đúng ảnh nhiệt đó. Điều cần thấy: cùng một tấm pin,
    nhưng nó rơi vào CHỖ KHÁC NHAU trong khung mỗi ảnh, và nhìn từ góc khác nhau —
    vì drone đứng ở tám vị trí khác nhau khi bấm.
    """
    import glob
    from ultralytics import YOLO
    mdl = YOLO(MODEL)

    O = 300                                     # cạnh mỗi ô sau khi phóng
    R = 118                                     # nửa cửa sổ cắt trên ảnh nhiệt gốc
    cot = 4
    hang = int(np.ceil(len(VET) / cot))
    GAP, TOP, BOT, NHAN = 14, 104, 92, 34
    W = cot * O + (cot - 1) * GAP
    Hh = hang * (O + NHAN) + (hang - 1) * GAP
    out = np.full((Hh + TOP + BOT, W, 3), 250, np.uint8)

    for i, v in enumerate(VET):
        p = glob.glob(os.path.join(BASE, "du_lieu/data_aligned/thermal",
                                   "*_%s_T.JPG" % v["seq"]))
        if not p:
            continue
        im = cv2.imread(p[0])
        r = mdl.predict(p[0], conf=0.25, verbose=False)[0]
        # box nào của ảnh này là lỗi đang xét: chọn box có conf khớp với vết đã lưu
        gg, dmin = None, None
        for k in range(len(r.obb)):
            c_ = float(r.obb.conf[k])
            if dmin is None or abs(c_ - v["conf"]) < dmin:
                dmin, gg = abs(c_ - v["conf"]), r.obb.xyxyxyxy.cpu().numpy()[k]
        cx, cy = gg[:, 0].mean(), gg[:, 1].mean()
        x0 = int(np.clip(cx - R, 0, im.shape[1] - 2 * R))
        y0 = int(np.clip(cy - R, 0, im.shape[0] - 2 * R))
        o = im[y0:y0 + 2 * R, x0:x0 + 2 * R].copy()
        k_ = O / o.shape[0]
        o = cv2.resize(o, (O, O), interpolation=cv2.INTER_NEAREST)
        pg = ((gg - [x0, y0]) * k_).astype(np.int32)
        cv2.polylines(o, [pg], True, TRANG, 2, cv2.LINE_AA)

        rr, cc = divmod(i, cot)
        X = cc * (O + GAP)
        Y = TOP + rr * (O + NHAN + GAP)
        out[Y:Y + O, X:X + O] = o
        cv2.rectangle(out, (X, Y), (X + O, Y + O), (215, 208, 200), 1)
        chu(out, "anh %s" % v["seq"], (X, Y + O + 19), 0.58, DEN, 2)
        chu(out, "conf %.2f   tam box (%d, %d)" % (v["conf"], cx, cy),
            (X, Y + O + 34), 0.44, XAM, 1)

    chu(out, "MOT LOI, TAM ANH NHIET KHAC NHAU", (0, 40), 0.78, DEN, 2)
    chu(out, "loi %s.  Anh nhiet goc 640x512, cat %d px quanh box, khung trang = box"
             " YOLO tren chinh anh do." % (GOP["panel_code"], 2 * R), (0, 68), 0.52,
        XAM, 1)
    yb = TOP + Hh + 30
    chu(out, "Chong lan la giua CAC ANH NHIET voi nhau - khong phai giua nhiet va RGB."
             "  Cung mot tam pin, tam goc nhin.", (0, yb), 0.52, DEN, 1)
    chu(out, "Tam box khac nhau o moi anh vi drone dung o tam cho khac nhau luc bam."
             "  Ba duong bay: 0309-0310, 0338-0340, 0402-0404.", (0, yb + 24), 0.52,
        XAM, 1)

    ra = os.path.join(args.ra, "gop_g0_tam_anh_nhiet.jpg")
    cv2.imwrite(ra, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("[G0]   %s  %dx%d" % (os.path.basename(ra), out.shape[1], out.shape[0]))


# --------------------------------------------------------------- G1 · gộp trùng
def ve_G1():
    lon0, lat0 = GOP["lon"], GOP["lat"]
    MET = 2.4
    im, T_, _ = cua_so(lon0, lat0, MET)
    K = 620 / im.shape[0]
    im = cv2.resize(im, None, fx=K, fy=K, interpolation=cv2.INTER_CUBIC)
    xy = lambda lon, lat: tuple(int(v) for v in np.array(~T_ * (lon, lat)) * K)

    trai = im.copy()
    phai = im.copy()

    # --- trái: 8 vết riêng lẻ, mỗi vết một sắc ---
    for i, v in enumerate(VET):
        t = i / max(1, len(VET) - 1)
        mau = (int(200 - 120 * t), int(90 + 40 * t), int(60 + 170 * t))
        p = np.array([xy(*q) for q in v["poly"]], np.int32)
        cv2.polylines(trai, [p], True, mau, 2, cv2.LINE_AA)
        c = xy(*v["tam"])
        cv2.circle(trai, c, 4, mau, -1, cv2.LINE_AA)
    chu(trai, "%d vet rieng le" % len(VET), (14, 30), 0.66, TRANG, 2, nen=(40, 30, 35))
    chu(trai, "cung mot loi, %d anh khac nhau" % len(VET), (14, 54), 0.5, TRANG, 1,
        nen=(40, 30, 35))

    # --- phải: vòng gộp + kết quả ---
    c0 = xy(lon0, lat0)
    r_px = int(0.60 / (2 * MET) * im.shape[1] * 2)          # bán kính 0,60 m ra pixel
    ov = phai.copy()
    cv2.circle(ov, c0, r_px, (210, 190, 170), -1)
    cv2.addWeighted(ov, .28, phai, .72, 0, phai)
    cv2.circle(phai, c0, r_px, (190, 160, 130), 2, cv2.LINE_AA)
    for v in VET:
        cv2.circle(phai, xy(*v["tam"]), 4, (150, 150, 160), -1, cv2.LINE_AA)
    p = np.array([xy(*q) for q in GOP["poly"]], np.int32)
    cv2.polylines(phai, [p], True, CAM, 3, cv2.LINE_AA)
    cv2.circle(phai, c0, 7, CAM, -1, cv2.LINE_AA)
    cv2.circle(phai, c0, 7, TRANG, 2, cv2.LINE_AA)
    chu(phai, "1 loi duy nhat", (14, 30), 0.66, TRANG, 2, nen=(40, 30, 35))
    chu(phai, "ban kinh gop 0,60 m  ->  n = %d" % GOP["n"], (14, 54), 0.5, TRANG, 1,
        nen=(40, 30, 35))

    # --- biểu đồ phân bố n trên cả 603 lỗi ---
    ns = np.array([x.get("n", 0) for x in LOI])
    BW, BH = 470, im.shape[0]
    bd = np.full((BH, BW, 3), 250, np.uint8)
    dem = [int((ns == k).sum()) for k in range(1, 15)]
    mx = max(dem)
    x0, y0, gw, gh = 56, 92, BW - 84, BH - 210
    for k, c in enumerate(dem):
        h = int(gh * c / mx)
        xa = x0 + int(gw * k / 14) + 3
        xb = x0 + int(gw * (k + 1) / 14) - 3
        mau = CAM if k + 1 >= 3 else (170, 170, 180)
        cv2.rectangle(bd, (xa, y0 + gh - h), (xb, y0 + gh), mau, -1)
        if c:
            chu(bd, str(c), ((xa + xb) // 2 - 9, y0 + gh - h - 7), 0.4, DEN, 1)
        chu(bd, str(k + 1), ((xa + xb) // 2 - 4, y0 + gh + 19), 0.44, XAM, 1)
    cv2.line(bd, (x0, y0 + gh), (x0 + gw, y0 + gh), (200, 195, 190), 2)
    chu(bd, "PHAN BO n tren ca 603 loi", (x0 - 6, 42), 0.62, DEN, 2)
    chu(bd, "n = so anh nhin thay cung mot loi", (x0 - 6, 66), 0.48, XAM, 1)
    chu(bd, "n", (x0 + gw - 6, y0 + gh + 42), 0.48, XAM, 1)
    chu(bd, "146 loi chi 1 anh thay - phan lon la bao dong gia",
        (x0 - 6, y0 + gh + 66), 0.47, DEN, 1)
    chu(bd, "trung vi n = 5, cao nhat n = 14", (x0 - 6, y0 + gh + 88), 0.47, XAM, 1)

    GAP, TOP, BOT = 26, 92, 74
    W = trai.shape[1] * 2 + BW + GAP * 2
    out = np.full((BH + TOP + BOT, W, 3), 250, np.uint8)
    xs = [0, trai.shape[1] + GAP, trai.shape[1] * 2 + GAP * 2]
    for im_, x_ in zip([trai, phai, bd], xs):
        out[TOP:TOP + BH, x_:x_ + im_.shape[1]] = im_

    chu(out, "GOP TRUNG - mot loi bi chieu xuong nhieu lan", (0, 40), 0.78, DEN, 2)
    chu(out, "loi %s, cua so %.1f m, nen la ortho mau"
        % (GOP["panel_code"], MET * 2), (0, 68), 0.54, XAM, 1)

    xa = xs[0] + trai.shape[1] + 4
    xb = xs[1] - 4
    ym = TOP + BH // 2
    cv2.arrowedLine(out, (xa, ym), (xb, ym), CAM, 3, cv2.LINE_AA, tipLength=.4)

    yb = TOP + BH + 28
    lech = [v["lech_m"] for v in VET]
    chu(out, "Tam %d vet tan trong ban kinh %.2f m (trung vi %.2f m) - deu duoi nguong"
             " 0,60 m nen gop lam mot." % (len(VET), max(lech), np.median(lech)),
        (0, yb), 0.52, DEN, 1)
    chu(out, "Nguong 0,60 m nho hon be rong tam pin 1,0 m: hai diem nong tach roi tren"
             " CUNG mot tam se bi nhap lam mot - cho ho da ghi o muc 5.2.",
        (0, yb + 24), 0.52, XAM, 1)

    ra = os.path.join(args.ra, "gop_g1_gop_trung.jpg")
    cv2.imwrite(ra, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("[G1]   %s  %dx%d" % (os.path.basename(ra), out.shape[1], out.shape[0]))


# --------------------------------------------------------------- G2 · gán tấm pin
def ve_G2():
    lon0, lat0 = GOP["lon"], GOP["lat"]
    MET = 3.2
    im, T_, (c0, r0) = cua_so(lon0, lat0, MET)
    K = 660 / im.shape[0]
    im = cv2.resize(im, None, fx=K, fy=K, interpolation=cv2.INTER_CUBIC)
    xy = lambda lon, lat: tuple(int(v) for v in np.array(~T_ * (lon, lat)) * K)
    # polygon tấm pin lưu theo PIXEL ORTHO -> trừ gốc cửa sổ rồi nhân tỉ lệ
    xy_px = lambda col, row: (int((col - c0) * K), int((row - r0) * K))

    trai = im.copy()
    phai = im.copy()

    # tấm pin quanh vùng
    oc, orow = GOP["ocol"], GOP["orow"]
    gan = []
    for poly in TAM:
        a = np.array(poly)
        if abs(a[:, 0].mean() - oc) < 260 and abs(a[:, 1].mean() - orow) < 260:
            gan.append(a)
    for a in gan:
        p = np.array([xy_px(*q) for q in a], np.int32)
        cv2.polylines(trai, [p], True, LUC, 2, cv2.LINE_AA)
        cv2.polylines(phai, [p], True, LUC, 2, cv2.LINE_AA)

    # --- trái: vết tứ giác xoay, ĐÚNG ---
    p = np.array([xy(*q) for q in GOP["poly"]], np.int32)
    ov = trai.copy()
    cv2.fillPoly(ov, [p], CAM)
    cv2.addWeighted(ov, .3, trai, .7, 0, trai)
    cv2.polylines(trai, [p], True, CAM, 3, cv2.LINE_AA)
    chu(trai, "DUNG - vet tu giac xoay", (14, 32), 0.62, TRANG, 2, nen=(30, 60, 20))
    chu(trai, "IoU %.3f  ->  %s" % (GOP["iou"], GOP["panel_code"]), (14, 56), 0.54,
        TRANG, 1, nen=(30, 60, 20))

    # --- phải: hộp dựng từ w_m/h_m, SAI ---
    w_m, h_m = GOP["w_m"], GOP["h_m"]
    dlon = w_m / 2 / (111320 * np.cos(np.radians(lat0)))
    dlat = h_m / 2 / 110570
    hop = [(lon0 - dlon, lat0 + dlat), (lon0 + dlon, lat0 + dlat),
           (lon0 + dlon, lat0 - dlat), (lon0 - dlon, lat0 - dlat)]
    q = np.array([xy(*t) for t in hop], np.int32)
    ov = phai.copy()
    cv2.fillPoly(ov, [q], DO)
    cv2.addWeighted(ov, .3, phai, .7, 0, phai)
    cv2.polylines(phai, [q], True, DO, 3, cv2.LINE_AA)
    chu(phai, "SAI - hop tu w_m / h_m", (14, 32), 0.62, TRANG, 2, nen=(40, 20, 60))
    chu(phai, "%.2f x %.2f m, thang truc anh" % (w_m, h_m), (14, 56), 0.54, TRANG, 1,
        nen=(40, 20, 60))

    GAP, TOP, BOT = 30, 96, 108
    W = trai.shape[1] * 2 + GAP
    out = np.full((im.shape[0] + TOP + BOT, W, 3), 250, np.uint8)
    out[TOP:TOP + im.shape[0], 0:trai.shape[1]] = trai
    out[TOP:TOP + im.shape[0], trai.shape[1] + GAP:] = phai

    chu(out, "GAN VAO TAM PIN - vi sao phai dung vet tu giac", (0, 42), 0.78, DEN, 2)
    chu(out, "loi %s, cua so %.1f m.  Xanh la = polygon tam pin (6 473 tam)"
        % (GOP["panel_code"], MET * 2), (0, 70), 0.54, XAM, 1)

    yb = TOP + im.shape[0] + 30
    chu(out, "Drone bay yaw ~ -89 nen tam pin nam NGANG tren ortho, con w_m/h_m la"
             " canh cua hop bao THEO TRUC ANH.", (0, yb), 0.52, DEN, 1)
    chu(out, "Hai he lech nhau ~90: hop do dung dung dung, tam pin nam ngang - IoU tut"
             " gan 0 du tam loi van dung cho.", (0, yb + 24), 0.52, DEN, 1)
    chu(out, "Vet tu giac giu duoc huong that vi no la anh chieu cua CA 4 GOC box,"
             " khong phai hai con so ben canh.", (0, yb + 48), 0.52, XAM, 1)

    ra = os.path.join(args.ra, "gop_g2_gan_tam.jpg")
    cv2.imwrite(ra, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("[G2]   %s  %dx%d  (IoU %.3f, dist %d cm)"
          % (os.path.basename(ra), out.shape[1], out.shape[0], GOP["iou"],
             GOP["dist_cm"]))


if args.chi in ("", "G0"):
    ve_G0()
if args.chi in ("", "G1"):
    ve_G1()
if args.chi in ("", "G2"):
    ve_G2()
