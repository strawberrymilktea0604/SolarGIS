#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng hình chi tiết cho CHUỖI CHIẾU — bước 2→5 của nhánh A, ảnh thật số thật.

Hình `thuat_toan_h2_chieu.png` đã có chỉ vẽ MỘT điểm đi qua chuỗi. Nó bỏ mất đúng
hai chỗ khó hiểu nhất, và đây là hai hình bù vào:

  P1  bốn góc        vì sao là "4 góc hộp" chứ không phải một điểm. Ba khung cạnh
                     nhau — ảnh nhiệt có box, ảnh RGB có 4 góc sau khi qua H, ortho
                     màu có vết đã chiếu xuống đất. Cùng một lỗi, ba hệ toạ độ.
  P2  cắt DSM        vì sao cần DSM. Vẽ lát cắt đứng: tâm chụp, tia phóng xuống,
                     mặt đất gồ ghề, và điểm chạm. Kèm phần "nếu giả định đất phẳng"
                     để thấy sai bao nhiêu mét khi bỏ DSM.

Số trên hình lấy từ lỗi THẬT `0005` (SingleHotSpot, conf 0,986, n=3), chạy lại đúng
chuỗi trong `quet_loi_anh_le.py`. Không có số bịa.

    py -3.13 ma/hinh_chuoi_chieu_chi_tiet.py
    py -3.13 ma/hinh_chuoi_chieu_chi_tiet.py --chi P2
"""
import argparse
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
MODEL = r"mo_hinh\fault_obb_4class.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="P1 hoặc P2, bỏ trống thì vẽ cả hai")
ap.add_argument("--seq", default="0005", help="ảnh lấy làm ví dụ")
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

# màu BGR, lấy cho khớp bảng token của slide
CAM = (0, 77, 194)        # --ember
XANH = (158, 95, 47)      # --steel
TRANG = (255, 255, 255)
DEN = (32, 22, 27)
XAM = (148, 131, 139)     # --text-3

# ----------------------------------------------------------------- 1. mô hình
H = np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                            encoding="utf-8"))["H_thermal_to_rgb"])

root = ET.parse(os.path.join(EXP, "cameras.xml")).getroot()
chunk = root.find(".//chunk")
s = chunk.find(".//sensor[@id='0']")
res = s.find("resolution")
cal = s.find("calibration[@class='adjusted']")
g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
IW, IH = int(res.get("width")), int(res.get("height"))
F, CX, CY = g("f"), g("cx"), g("cy")

tr = chunk.find("transform")
R_ch = np.array([float(x) for x in tr.find("rotation").text.split()]).reshape(3, 3)
T_ch = np.array([float(x) for x in tr.find("translation").text.split()])
S_ch = float(tr.find("scale").text)

cams = {}
for c in chunk.iter("camera"):
    t = c.find("transform")
    if t is None:
        continue
    lab = c.get("label")
    seq = lab.split("_")[2] if len(lab.split("_")) > 2 else lab
    cams[seq] = np.array([float(x) for x in t.text.split()]).reshape(4, 4)

dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
ND = dsm.nodata
zmed = float(np.median(DSM[DSM != ND]))
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)


def cat_dsm(lon, lat):
    r, c = dsm.index(lon, lat)
    if 0 <= r < DSM.shape[0] and 0 <= c < DSM.shape[1]:
        z = float(DSM[r, c])
        if z != ND and np.isfinite(z):
            return z
    return zmed


def tia(u_th, v_th, seq):
    """px ảnh nhiệt -> (tâm chụp ECEF, hướng đơn vị ECEF, px RGB)."""
    p = np.array([u_th, v_th, 1.0]) @ H.T
    u, v = p[0] / p[2], p[1] / p[2]
    d_cam = np.array([(u - IW / 2.0 - CX) / F, (v - IH / 2.0 - CY) / F, 1.0])
    M = cams[seq]
    d = R_ch @ (M[:3, :3] @ d_cam)
    C = R_ch @ (M[:3, 3] * S_ch) + T_ch
    return C, d / np.linalg.norm(d), (u, v)


def cham_dat(C, d):
    """Dò nhị phân dọc tia tới khi chạm DSM. Trả về (điểm ECEF, lon, lat, z, dài)."""
    lo, hi = 10.0, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lon, lat, alt = to_wgs.transform(*(C + d * mid))
        if alt > cat_dsm(lon, lat):
            lo = mid
        else:
            hi = mid
    L = (lo + hi) / 2
    P = C + d * L
    lon, lat, alt = to_wgs.transform(*P)
    return P, lon, lat, cat_dsm(lon, lat), L


def chu(im, s, xy, co=0.62, mau=TRANG, day=1, nen=None):
    """Chữ có thể kèm nền mờ cho dễ đọc trên ảnh."""
    ff = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), _ = cv2.getTextSize(s, ff, co, day)
    x, y = xy
    if nen is not None:
        cv2.rectangle(im, (x - 4, y - h - 5), (x + w + 4, y + 5), nen, -1)
    cv2.putText(im, s, (x, y), ff, co, mau, day, cv2.LINE_AA)
    return w


# ----------------------------------------------------------------- 2. dữ liệu ca
seq = args.seq
p_nhiet = glob.glob(os.path.join(BASE, "du_lieu/data_aligned/thermal",
                                 "*_%s_T.JPG" % seq))
p_rgb = glob.glob(os.path.join(BASE, "du_lieu/data_aligned/rgb", "*_%s_W.JPG" % seq))
if not p_nhiet or not p_rgb:
    raise SystemExit("[DỪNG] không thấy cặp ảnh %s trong du_lieu/data_aligned/" % seq)

from ultralytics import YOLO                                    # noqa: E402
mdl = YOLO(MODEL)
r = mdl.predict(p_nhiet[0], conf=0.25, verbose=False)[0]
if len(r.obb) == 0:
    raise SystemExit("[DỪNG] ảnh %s không có box nào" % seq)
best = int(np.argmax(r.obb.conf.cpu().numpy()))
goc_th = r.obb.xyxyxyxy.cpu().numpy()[best].astype(np.float64)
conf = float(r.obb.conf[best])
ten_lop = mdl.names[int(r.obb.cls[best])]

goc_rgb, goc_dat, dai, zs = [], [], [], []
for (uu, vv) in goc_th:
    C, d, prgb = tia(float(uu), float(vv), seq)
    P, lon, lat, z, L = cham_dat(C, d)
    goc_rgb.append(prgb)
    goc_dat.append((lon, lat))
    dai.append(L)
    zs.append(z)
goc_rgb = np.array(goc_rgb)
goc_dat = np.array(goc_dat)

_, _, alt_cam = to_wgs.transform(*C)
print("[CA]   ảnh %s · %s · conf %.3f" % (seq, ten_lop, conf))
print("       tâm chụp cao %.1f m, tia dài %.1f-%.1f m, DSM %.2f-%.2f m"
      % (alt_cam, min(dai), max(dai), min(zs), max(zs)))


# ----------------------------------------------------------------- P1 · bốn góc
def ve_P1():
    KH = 560                                     # cao mỗi khung
    im_th = cv2.imread(p_nhiet[0])
    im_rgb = cv2.imread(p_rgb[0])

    # --- khung 1: ảnh nhiệt + box, cắt quanh box cho thấy rõ ---
    cx, cy = goc_th[:, 0].mean(), goc_th[:, 1].mean()
    R = 150
    x0 = int(np.clip(cx - R, 0, im_th.shape[1] - 2 * R))
    y0 = int(np.clip(cy - R, 0, im_th.shape[0] - 2 * R))
    a = im_th[y0:y0 + 2 * R, x0:x0 + 2 * R].copy()
    k = KH / a.shape[0]
    a = cv2.resize(a, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
    pa = ((goc_th - [x0, y0]) * k).astype(np.int32)
    cv2.polylines(a, [pa], True, TRANG, 2, cv2.LINE_AA)
    for i, (px, py) in enumerate(pa):
        cv2.circle(a, (px, py), 7, CAM, -1, cv2.LINE_AA)
        cv2.circle(a, (px, py), 7, TRANG, 2, cv2.LINE_AA)
        chu(a, str(i + 1), (px + 11, py + 6), 0.62, TRANG, 2)

    # --- khung 2: ảnh RGB, 4 góc sau khi qua H ---
    cx2, cy2 = goc_rgb[:, 0].mean(), goc_rgb[:, 1].mean()
    R2 = int(R * 2.637)                          # cùng vùng đất, theo tỉ lệ của H
    x2 = int(np.clip(cx2 - R2, 0, im_rgb.shape[1] - 2 * R2))
    y2 = int(np.clip(cy2 - R2, 0, im_rgb.shape[0] - 2 * R2))
    b = im_rgb[y2:y2 + 2 * R2, x2:x2 + 2 * R2].copy()
    k2 = KH / b.shape[0]
    b = cv2.resize(b, None, fx=k2, fy=k2, interpolation=cv2.INTER_AREA)
    pb = ((goc_rgb - [x2, y2]) * k2).astype(np.int32)
    cv2.polylines(b, [pb], True, CAM, 2, cv2.LINE_AA)
    for i, (px, py) in enumerate(pb):
        cv2.circle(b, (px, py), 7, CAM, -1, cv2.LINE_AA)
        cv2.circle(b, (px, py), 7, TRANG, 2, cv2.LINE_AA)
        chu(b, str(i + 1), (px + 11, py + 6), 0.62, TRANG, 2)

    # --- khung 3: ortho màu, vết đã chiếu xuống đất ---
    ort = rasterio.open(os.path.join(EXP, "ortho.tif"))
    lon0, lat0 = goc_dat[:, 0].mean(), goc_dat[:, 1].mean()
    M_ = 5.0                                     # nửa cửa sổ, mét
    dlon = M_ / (111320 * np.cos(np.radians(lat0)))
    dlat = M_ / 110570
    r0, c0 = ort.index(lon0 - dlon, lat0 + dlat)
    r1, c1 = ort.index(lon0 + dlon, lat0 - dlat)
    r0, r1 = max(0, min(r0, r1)), min(ort.height, max(r0, r1))
    c0, c1 = max(0, min(c0, c1)), min(ort.width, max(c0, c1))
    win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
    arr = ort.read([1, 2, 3], window=win)
    cc = np.transpose(arr, (1, 2, 0))[:, :, ::-1].copy()
    k3 = KH / cc.shape[0]
    cc = cv2.resize(cc, None, fx=k3, fy=k3, interpolation=cv2.INTER_CUBIC)
    T_ = ort.window_transform(win)
    pc = []
    for lon, lat in goc_dat:
        col, row = ~T_ * (lon, lat)
        pc.append([col * k3, row * k3])
    pc = np.array(pc, np.int32)
    cv2.polylines(cc, [pc], True, CAM, 2, cv2.LINE_AA)
    for i, (px, py) in enumerate(pc):
        cv2.circle(cc, (px, py), 7, CAM, -1, cv2.LINE_AA)
        cv2.circle(cc, (px, py), 7, TRANG, 2, cv2.LINE_AA)
        chu(cc, str(i + 1), (px + 11, py + 6), 0.62, TRANG, 2)

    # --- ghép ba khung + dải nhãn ---
    W = [a.shape[1], b.shape[1], cc.shape[1]]
    GAP, TOP, BOT = 74, 96, 96
    tong = sum(W) + GAP * 2
    out = np.full((KH + TOP + BOT, tong, 3), 250, np.uint8)
    xs = [0, W[0] + GAP, W[0] + W[1] + GAP * 2]
    for im_, x_ in zip([a, b, cc], xs):
        out[TOP:TOP + KH, x_:x_ + im_.shape[1]] = im_

    tieu = [
        ("1 · ANH NHIET  640x512",
         "box YOLO-OBB  %s  conf %.2f" % (ten_lop.upper(), conf)),
        ("2 · ANH RGB  4056x3040",
         "4 goc sau khi qua H"),
        ("3 · MAT DAT  ortho mau",
         "vet that, cua so 10 m"),
    ]
    for (t1, t2), x_, w_ in zip(tieu, xs, W):
        chu(out, t1, (x_, TOP - 42), 0.68, DEN, 2)
        chu(out, t2, (x_, TOP - 18), 0.58, XAM, 1)

    # mũi tên giữa các khung + nhãn phép biến đổi
    for i in (0, 1):
        xa = xs[i] + W[i] + 8
        xb = xs[i + 1] - 8
        y_ = TOP + KH // 2
        cv2.arrowedLine(out, (xa, y_), (xb, y_), CAM, 3, cv2.LINE_AA, tipLength=.34)
        nhan = "H" if i == 0 else "tia + DSM"
        w_ = cv2.getTextSize(nhan, cv2.FONT_HERSHEY_SIMPLEX, .66, 2)[0][0]
        chu(out, nhan, ((xa + xb) // 2 - w_ // 2, y_ - 16), 0.66, CAM, 2, nen=(250, 250, 250))

    # dải số dưới: toạ độ từng góc qua ba hệ
    yb = TOP + KH + 26
    for i in range(4):
        d1 = "%d  (%.0f, %.0f) px" % (i + 1, goc_th[i][0], goc_th[i][1])
        d2 = "(%.0f, %.0f) px" % (goc_rgb[i][0], goc_rgb[i][1])
        d3 = "%.7f, %.7f" % (goc_dat[i][0], goc_dat[i][1])
        yy = yb + i * 17
        chu(out, d1, (xs[0], yy), 0.44, DEN if i else CAM, 1)
        chu(out, d2, (xs[1], yy), 0.44, DEN if i else CAM, 1)
        chu(out, d3, (xs[2], yy), 0.44, DEN if i else CAM, 1)

    ra = os.path.join(args.ra, "chuoi_p1_bon_goc.jpg")
    cv2.imwrite(ra, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("[P1]   %s  %dx%d" % (os.path.basename(ra), out.shape[1], out.shape[0]))


# ----------------------------------------------------------------- P2 · cắt DSM
def cham_phang(C, d, z):
    """Cắt tia với MẶT PHẲNG z = const, tức bản 'giả định đất phẳng'."""
    lo, hi = 10.0, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lon, lat, alt = to_wgs.transform(*(C + d * mid))
        if alt > z:
            lo = mid
        else:
            hi = mid
    L = (lo + hi) / 2
    lon, lat, _ = to_wgs.transform(*(C + d * L))
    return lon, lat, L


def lech_m(lo1, la1, lo2, la2):
    dx = (lo2 - lo1) * 111320 * np.cos(np.radians(la1))
    dy = (la2 - la1) * 110570
    return float(np.hypot(dx, dy))


def chon_tia_doc():
    """Quét cả chuyến bay, chọn tia mà bỏ DSM sai nhiều nhất — chỗ DSM ăn thua.

    Cũng in luôn thống kê trên toàn bộ mẫu, vì một tia đơn lẻ không nói được gì
    về mức độ phổ biến.
    """
    ds, tot = [], []
    for sq in sorted(cams)[::17]:
        for (uu, vv) in [(160, 128), (480, 128), (160, 384), (480, 384), (320, 256)]:
            C, d, _ = tia(uu, vv, sq)
            _, lo1, la1, z1, L1 = cham_dat(C, d)
            lo2, la2, _ = cham_phang(C, d, zmed)
            e = lech_m(lo1, la1, lo2, la2)
            tot.append(e)
            ds.append((e, C, d, L1, lo1, la1, z1, sq))
    tot = np.array(tot)
    print("[P2]   bỏ DSM: trung vị %.2f m · p90 %.2f m · max %.2f m (%d tia, %d ảnh)"
          % (np.median(tot), np.percentile(tot, 90), tot.max(), len(tot), len(tot) // 5))
    ds.sort(key=lambda t: -t[0])
    e, C, d, L1, lo1, la1, z1, sq = ds[0]
    return C, d, L1, lo1, la1, z1, e, sq


def ve_P2():
    """Lát cắt đứng dọc tia: vì sao phải cắt DSM chứ không giả định đất phẳng."""
    W_, H_ = 1500, 720
    out = np.full((H_, W_, 3), 250, np.uint8)
    L, Rr, TOP, BOT = 96, 60, 92, 116
    ve_w, ve_h = W_ - L - Rr, H_ - TOP - BOT

    # Chọn tia có sai số bỏ-DSM lớn nhất trong cả chuyến bay, chứ không lấy bừa một
    # góc box. Lý do: ca 0005 rơi đúng chỗ đất phẳng, bỏ DSM chỉ lệch 5 cm — vẽ nó
    # ra thì hình tự bác bỏ tiêu đề của chính nó. Hình phải cho thấy chỗ DSM ĂN THUA.
    C, d, L_tia, lon_c, lat_c, z_c, sai_max, seq_ve = chon_tia_doc()
    _, _, alt_C = to_wgs.transform(*C)

    # lấy mặt cắt DSM dọc theo hình chiếu ngang của tia, 0..1,6 lần chiều dài tia
    ts = np.linspace(0, L_tia * 1.6, 240)
    lons, lats, alts, zs_ = [], [], [], []
    for t in ts:
        lo_, la_, al_ = to_wgs.transform(*(C + d * t))
        lons.append(lo_); lats.append(la_); alts.append(al_); zs_.append(cat_dsm(lo_, la_))
    alts = np.array(alts); zs_ = np.array(zs_)

    zmin = min(zs_.min(), z_c) - 3
    zmax = alt_C + 6
    fx = lambda t: L + ve_w * t / ts[-1]
    fy = lambda z: TOP + ve_h * (zmax - z) / (zmax - zmin)

    # nền trời + đất
    cv2.rectangle(out, (L, TOP), (L + ve_w, TOP + ve_h), (252, 248, 244), -1)
    dat = [[int(fx(t)), int(fy(z))] for t, z in zip(ts, zs_)]
    poly = np.array(dat + [[L + ve_w, TOP + ve_h], [L, TOP + ve_h]], np.int32)
    cv2.fillPoly(out, [poly], (232, 226, 216))
    cv2.polylines(out, [np.array(dat, np.int32)], False, XANH, 3, cv2.LINE_AA)

    # mốc cao độ
    for z in range(int(zmin // 5 * 5), int(zmax) + 5, 5):
        if not (zmin < z < zmax):
            continue
        y_ = int(fy(z))
        cv2.line(out, (L, y_), (L + ve_w, y_), (232, 228, 224), 1)
        chu(out, "%d m" % z, (L - 52, y_ + 5), 0.46, XAM, 1)

    # tia thật
    x_c, y_c = int(fx(L_tia)), int(fy(z_c))
    cv2.line(out, (int(fx(0)), int(fy(alt_C))), (x_c, y_c), CAM, 3, cv2.LINE_AA)

    # tia kéo dài nếu KHÔNG có DSM: cắt mặt phẳng z = z trung vị
    t_phang = None
    for t, al_ in zip(ts, alts):
        if al_ <= zmed:
            t_phang = t
            break
    if t_phang:
        xp, yp = int(fx(t_phang)), int(fy(zmed))
        cv2.line(out, (x_c, y_c), (xp, yp), (150, 150, 160), 2, cv2.LINE_AA)
        cv2.line(out, (L, int(fy(zmed))), (L + ve_w, int(fy(zmed))),
                 (170, 170, 180), 1, cv2.LINE_AA)
        chu(out, "gia dinh DAT PHANG  z = %.1f m" % zmed,
            (L + 12, int(fy(zmed)) - 9), 0.5, (120, 120, 132), 1)
        cv2.circle(out, (xp, yp), 8, (150, 150, 160), -1, cv2.LINE_AA)
        # sai số ngang giữa hai điểm chạm
        lo1, la1, _ = to_wgs.transform(*(C + d * L_tia))
        lo2, la2, _ = to_wgs.transform(*(C + d * t_phang))
        dx = (lo2 - lo1) * 111320 * np.cos(np.radians(la1))
        dy = (la2 - la1) * 110570
        sai = float(np.hypot(dx, dy))
        ym = min(y_c, yp) - 30
        cv2.arrowedLine(out, (x_c, ym), (xp, ym), (90, 90, 100), 2, cv2.LINE_AA, tipLength=.2)
        cv2.arrowedLine(out, (xp, ym), (x_c, ym), (90, 90, 100), 2, cv2.LINE_AA, tipLength=.2)
        chu(out, "lech %.1f m neu bo DSM" % sai,
            ((x_c + xp) // 2 - 92, ym - 11), 0.56, (70, 70, 82), 2)
        print("[P2]   bỏ DSM thì lệch %.2f m" % sai)

    # tâm chụp
    cv2.circle(out, (int(fx(0)), int(fy(alt_C))), 11, CAM, -1, cv2.LINE_AA)
    cv2.circle(out, (int(fx(0)), int(fy(alt_C))), 11, TRANG, 2, cv2.LINE_AA)
    chu(out, "TAM CHUP  %.1f m" % alt_C, (int(fx(0)) - 8, int(fy(alt_C)) - 22), 0.58, DEN, 2)
    chu(out, "anh %s" % seq_ve, (int(fx(0)) - 8, int(fy(alt_C)) - 4), 0.5, XAM, 1)

    # điểm chạm thật
    cv2.circle(out, (x_c, y_c), 9, CAM, -1, cv2.LINE_AA)
    cv2.circle(out, (x_c, y_c), 9, TRANG, 2, cv2.LINE_AA)
    chu(out, "CHAM DAT  z = %.2f m" % z_c, (x_c - 60, y_c + 34), 0.58, CAM, 2)
    chu(out, "%.7f, %.7f" % (lon_c, lat_c), (x_c - 60, y_c + 54), 0.48, DEN, 1)

    chu(out, "tia dai %.1f m" % L_tia,
        (int(fx(L_tia * .42)), int(fy((alt_C + z_c) / 2)) - 12), 0.56, CAM, 2)

    chu(out, "CAT TIA VOI DSM - vi sao khong duoc gia dinh dat phang",
        (L, 40), 0.76, DEN, 2)
    chu(out, "lat cat dung doc theo tia, anh %s - ca lech nhieu nhat trong chuyen bay"
        % seq_ve, (L, 66), 0.54, XAM, 1)
    chu(out, "duong xanh = mat dat that (DSM)   |   duong xam = mat phang gia dinh",
        (L, H_ - 56), 0.52, XAM, 1)
    chu(out, "Do tren 180 tia rai deu 36 anh: bo DSM lech trung vi 0,44 m - p90 1,24 m"
             " - max 3,29 m.  46% so tia lech qua 0,5 m.",
        (L, H_ - 32), 0.52, DEN, 1)

    ra = os.path.join(args.ra, "chuoi_p2_cat_dsm.jpg")
    cv2.imwrite(ra, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("[P2]   %s  %dx%d" % (os.path.basename(ra), out.shape[1], out.shape[0]))


if args.chi in ("", "P1"):
    ve_P1()
if args.chi in ("", "P2"):
    ve_P2()
