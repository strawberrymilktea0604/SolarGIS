#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ba hình BẰNG SỐ THẬT cho chuỗi chiếu ở mục 5.1 — bước 2, 3, 4.

`thuat_toan_h2_chieu.png` vẽ tay cả chuỗi trong một sơ đồ; `thuc_te_r1_chieu.jpg`
cho thấy ĐẦU VÀO và ĐẦU RA. Còn khúc giữa — pixel thành tia, tia cắt DSM — thì
chưa hình nào mở ra. Ba hình ở đây mổ đúng khúc đó, chạy trên MỘT lỗi thật để
người đọc theo được một mạch từ đầu tới cuối:

  P1  bốn góc qua H    box YOLO trên ảnh nhiệt 640×512 ↔ đúng bốn góc đó trên
                       ảnh RGB 4056×3040. Vẽ kèm cái mà chỉ-chuyển-tâm sẽ ra,
                       để thấy vì sao phải chuyển cả bốn góc chứ không phải một.
  P2  pixel thành tia  mặt cắt ĐỨNG: camera ở độ cao thật, bốn tia rẽ quạt xuống
                       mặt đất, kèm góc xiên off-nadir đo được của từng góc box.
  P3  cắt DSM          đồ thị độ cao dọc tia. Đường tia hạ tuyến tính, đường DSM
                       là mặt đất thật; chỗ hai đường cắt nhau là đáp số. Vẽ đúng
                       các vòng CHIA ĐÔI mà `ray_dsm_intersect` đã chạy.

Vì sao không mượn `project_box_to_ortho.py`: file đó chạy tương tác (BBoxDrawer,
cv2.imshow, chờ phím) và trỏ vào bộ `cameras_v6.xml`/`full_dsm.tif` của dự án
solarfarm_inspection. Ở đây dựng lại phần toán thuần — cùng công thức, cùng quy
ước `cx`,`cy` là ĐỘ LỆCH so với tâm ảnh — trên bộ Thermal2_31M của chính tài liệu.

    py -3.13 ma/hinh_chuoi_chieu_thuc_te.py
    py -3.13 ma/hinh_chuoi_chieu_thuc_te.py --chi P3
"""
import argparse
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XUAT = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
MODEL = r"mo_hinh\fault_obb_4class.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="chỉ dựng một hình: P1 / P2 / P3")
ap.add_argument("--seq", default="", help="ép dùng một ảnh cụ thể, vd 0402")
ap.add_argument("--conf", type=float, default=0.25)
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

# BGR — cùng bảng màu với các hình khác trong tài liệu
TRANG = (255, 255, 255)
DEN = (28, 24, 20)
CAM = (0, 77, 194)
XANH = (158, 95, 47)
LUC = (80, 160, 60)
DO = (60, 45, 200)
LO = (235, 220, 40)
XAM = (150, 140, 132)
NEN = (250, 246, 244)
CHU = (32, 22, 27)

# ------------------------------------------------------------------ nạp dữ liệu
D = json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))
H = np.array(D["H_thermal_to_rgb"], float)
BU = D["hieu_chinh_bo_sung"]
TW, TH = D["thermal_size"]
RW, RH = D["rgb_size"]

loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
rows = {}
with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows[r["seq"]] = r

dsm = rasterio.open(os.path.join(XUAT, "dsm.tif"))
DSM = dsm.read(1)
oc = rasterio.open(os.path.join(XUAT, "ortho.tif"))
ecef2wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)


def qua_H(P):
    """Pixel ảnh nhiệt -> pixel ảnh RGB. TRỪ hiệu chỉnh bổ sung, đúng quy ước
    `lam_notebook.py:90` (`q - [dx, dy]`) — sai số trung bình của riêng H là
    (−9,65; −4,84) px nên dự đoán đúng là q trừ đi độ lệch đó."""
    P = np.asarray(P, float).reshape(-1, 2)
    q = (H @ np.c_[P, np.ones(len(P))].T).T
    q = q[:, :2] / q[:, 2:]
    return q - [BU["dx_px"], BU["dy_px"]]


# ------------------------------------------------- nội/ngoại tham số Metashape
def doc_cameras(nhan):
    ch = ET.parse(os.path.join(XUAT, "cameras.xml")).getroot().find(".//chunk")
    s = ch.find(".//sensor")
    cal = s.find("calibration[@class='adjusted']")
    ss = {k: float(cal.find(k).text) for k in ("f", "cx", "cy")}
    ss["width"] = int(s.find("resolution").get("width"))
    ss["height"] = int(s.find("resolution").get("height"))

    tf = None
    for c in ch.findall(".//camera"):
        if c.get("label") == nhan and c.find("transform") is not None:
            tf = np.array(list(map(float, c.find("transform").text.split()))).reshape(4, 4)
            break
    if tf is None:
        raise SystemExit("khong thay camera %s trong cameras.xml" % nhan)

    comp = ch.find(".//component/transform")
    ck = {
        "R": np.array(list(map(float, comp.find("rotation").text.split()))).reshape(3, 3),
        "T": np.array(list(map(float, comp.find("translation").text.split()))),
        "s": float(comp.find("scale").text),
    }
    return ss, tf, ck


def pixel_ra_tia(u, v, ss, tf, ck):
    """Pixel RGB -> (tâm chụp, vector chỉ phương) trong ECEF.

    `cx`,`cy` của Metashape là ĐỘ LỆCH so với tâm ảnh, nên phải trừ cả w/2 lẫn cx
    — đây là chỗ dễ sai nhất của cả chuỗi."""
    x = (u - ss["width"] / 2.0 - ss["cx"]) / ss["f"]
    y = (v - ss["height"] / 2.0 - ss["cy"]) / ss["f"]
    d_cam = np.array([x, y, 1.0])

    C_ecef = ck["s"] * (ck["R"] @ tf[:3, 3]) + ck["T"]
    d = ck["R"] @ (tf[:3, :3] @ d_cam)
    return C_ecef, d / np.linalg.norm(d), float(np.degrees(np.arctan(np.hypot(x, y))))


def do_cao_dsm(lon, lat):
    b = dsm.bounds
    if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
        return None
    c, r = ~dsm.transform * (lon, lat)
    c, r = int(c), int(r)
    if 0 <= r < dsm.height and 0 <= c < dsm.width:
        v = DSM[r, c]
        if v != dsm.nodata and not np.isnan(v):
            return float(v)
    return None


def cat_dsm(O, d, buoc=1.0, xa=500.0, ghi=None):
    """Đi dọc tia rồi chia đôi. `ghi` là list để nhặt lại vết dò cho hình P3."""
    truoc = None
    t_truoc = 0.0
    for i in range(int(xa / buoc)):
        t = i * buoc
        P = O + t * d
        lon, lat, alt = ecef2wgs.transform(*P)
        h = do_cao_dsm(lon, lat)
        if h is None:
            continue
        if ghi is not None:
            ghi.append(("tho", t, alt, h))
        if truoc is not None and truoc > 0 and alt - h <= 0:
            lo, hi = t_truoc, t
            for _ in range(50):
                m = (lo + hi) / 2
                Pm = O + m * d
                lo_m, la_m, al_m = ecef2wgs.transform(*Pm)
                hm = do_cao_dsm(lo_m, la_m)
                if hm is None:
                    lo = m
                    continue
                if ghi is not None:
                    ghi.append(("doi", m, al_m, hm))
                if abs(al_m - hm) < 0.01:
                    return lo_m, la_m, hm, m
                if al_m - hm > 0:
                    lo = m
                else:
                    hi = m
            m = (lo + hi) / 2
            Pm = O + m * d
            lo_m, la_m, al_m = ecef2wgs.transform(*Pm)
            return lo_m, la_m, do_cao_dsm(lo_m, la_m) or al_m, m
        truoc = alt - h
        t_truoc = t
    return None


# --------------------------------------------------------------------- vẽ vặt
def bang_ten(a, chu, cao=34, co=0.56):
    h, w = a.shape[:2]
    ra = np.full((h + cao, w, 3), DEN, np.uint8)
    ra[cao:] = a
    cv2.putText(ra, chu, (10, cao - 11), cv2.FONT_HERSHEY_SIMPLEX, co, TRANG, 1, cv2.LINE_AA)
    return ra


def vien(a, mau=(222, 213, 205), d=3):
    return cv2.copyMakeBorder(a, d, d, d, d, cv2.BORDER_CONSTANT, value=mau)


def nhan_duoi(a, chu, cao=34, co=0.55):
    """Thanh chú thích nền sáng đặt TRÊN ảnh. Tự ngắt dòng theo bề ngang thật —
    nhãn dài một dòng bị cắt cụt ở mép là lỗi đã gặp khi dựng bản đầu."""
    tu = chu.split()
    dong, d = [], ""
    for t in tu:
        thu = (d + " " + t).strip()
        if cv2.getTextSize(thu, cv2.FONT_HERSHEY_SIMPLEX, co, 1)[0][0] > a.shape[1] - 24:
            dong.append(d); d = t
        else:
            d = thu
    dong.append(d)
    h = max(cao, 12 + 22 * len(dong))
    n = np.full((h, a.shape[1], 3), NEN, np.uint8)
    for i, t in enumerate(dong):
        cv2.putText(n, t, (12, 24 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, co, CHU, 1, cv2.LINE_AA)
    return np.vstack([n, a])


# ================================================== chọn CA để cả ba hình dùng
def chon_ca():
    """Một ca dùng chung cho P1–P3: có box YOLO trên ảnh nhiệt, chiếu trúng tấm
    pin, và ảnh RGB đọc được. Ưu tiên IoU cao để hình nói được điều đúng."""
    from ultralytics import YOLO
    model = YOLO(MODEL)

    ung = [d for d in loi if d.get("in_panel") and d.get("iou", 0) > 0.65
           and d["seq"] in rows]
    if args.seq:
        ung = [d for d in loi if d["seq"] == args.seq] or ung
    ung.sort(key=lambda x: -x["iou"])

    for d in ung[:60]:
        r = rows[d["seq"]]
        th = cv2.imread(r["path_thermal"])
        rgb = cv2.imread(r["path_rgb"])
        if th is None or rgb is None:
            continue
        res = model.predict(th, imgsz=640, conf=args.conf, verbose=False)[0]
        if getattr(res, "obb", None) is None or len(res.obb) == 0:
            continue
        q = res.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
        cf = res.obb.conf.cpu().numpy()

        # Box gần TÂM ẢNH nhất trong số box conf cao: tránh box sát mép, nơi H
        # phải ngoại suy và tia xiên nhất — hình sẽ khó đọc mà không đại diện.
        j = int(np.argmin(np.hypot(q[:, :, 0].mean(1) - TW / 2, q[:, :, 1].mean(1) - TH / 2)))
        if cf[j] < 0.5:
            continue
        nhan = os.path.splitext(os.path.basename(r["path_rgb"]))[0]
        try:
            ss, tf, ck = doc_cameras(nhan)
        except SystemExit:
            continue
        print("[ca] seq %s  nhan %s  conf %.2f  IoU %.3f  %s"
              % (d["seq"], nhan, cf[j], d["iou"], d.get("panel_code")))
        return dict(d=d, th=th, rgb=rgb, box=q[j], conf=float(cf[j]),
                    cls=res.names[int(res.obb.cls.cpu().numpy()[j])],
                    ss=ss, tf=tf, ck=ck, nhan=nhan)
    raise SystemExit("khong chon duoc ca nao")


CA = chon_ca()


# ========================================================= P1 · bốn góc qua H
def lam_P1():
    box_t = CA["box"]                       # 4 góc trên ảnh NHIỆT
    box_r = qua_H(box_t)                    # 4 góc đó trên ảnh RGB
    tam_t = box_t.mean(0)
    tam_r = qua_H([tam_t])[0]

    # Cái mà "chỉ chuyển tâm rồi giữ nguyên kích thước hộp" sẽ ra: giữ nguyên
    # hình dạng box NHIỆT, chỉ dời tâm sang toạ độ đã chiếu. Không nhân hệ số
    # phóng — vì nếu đã biết mà nhân đúng k thì đã là dùng H rồi.
    giu = (box_t - tam_t) + tam_r
    lech_giu = float(np.hypot(*(box_r - giu).T).max())

    # Tách riêng phần PHỐI CẢNH: cùng box, nhưng H bị tắt hàng cuối. Đây mới là
    # phần "hình chữ nhật thành hình thang", và ở cỡ một box lỗi nó rất nhỏ.
    A = H.copy()
    A[2] = [0, 0, 1]
    qa = (A @ np.c_[box_t, np.ones(4)].T).T
    qa = qa[:, :2] / qa[:, 2:] - [BU["dx_px"], BU["dy_px"]]
    lech_pc = float(np.hypot(*(box_r - (qa - qa.mean(0) + tam_r)).T).max())

    # ...và ở cỡ CẢ KHUNG ẢNH thì lớn hẳn. Hai số này cạnh nhau là nội dung thật.
    g = np.array([[0, 0], [TW, 0], [TW, TH], [0, TH]], float)
    qg = qua_H(g)
    ga = (A @ np.c_[g, np.ones(4)].T).T
    ga = ga[:, :2] / ga[:, 2:] - [BU["dx_px"], BU["dy_px"]]
    lech_khung = float(np.hypot(*(qg - (ga - ga.mean(0) + qg.mean(0))).T).max())

    # TRÁI — ảnh nhiệt, box gốc. Nhãn đặt LỆCH RA NGOÀI theo phía của từng góc,
    # nếu không bốn nhãn chồng lên nhau (box chỉ ~40x90 px).
    a = CA["th"].copy()
    cv2.polylines(a, [box_t.astype(np.int32)], True, CAM, 2, cv2.LINE_AA)
    for (x, y) in box_t:
        cv2.circle(a, (int(x), int(y)), 5, CAM, -1, cv2.LINE_AA)
    cv2.drawMarker(a, tuple(tam_t.astype(int)), TRANG, cv2.MARKER_CROSS, 16, 2)
    a = cv2.resize(a, (TW * 2, TH * 2), interpolation=cv2.INTER_CUBIC)
    # Box chỉ ~40x90 px nên hai góc cùng phía chỉ cách nhau ~80 px sau khi phóng
    # x2 — đủ để hai nhãn đè nhau. Đẩy nhãn ra xa theo ĐƯỜNG CHÉO từ tâm rồi kẻ
    # đường dẫn về đúng góc, thay vì nhích vài pixel.
    for i, (x, y) in enumerate(box_t):
        px, py = int(x * 2), int(y * 2)
        ux = 1 if x > tam_t[0] else -1
        uy = 1 if y > tam_t[1] else -1
        tx, ty = px + ux * 96, py + uy * 74
        chu = "%d (%d,%d)" % (i + 1, x, y)
        rong = cv2.getTextSize(chu, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)[0][0]
        if ux < 0:
            tx -= rong
        cv2.line(a, (px, py), (tx + (rong // 2 if ux < 0 else 0), ty + 6), CAM, 1, cv2.LINE_AA)
        cv2.putText(a, chu, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.62, DEN, 4, cv2.LINE_AA)
        cv2.putText(a, chu, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.62, TRANG, 1, cv2.LINE_AA)
    a = bang_ten(a, "ANH NHIET 640x512  -  box YOLO %s conf %.2f" % (CA["cls"], CA["conf"]))

    # PHẢI — ảnh RGB, cắt quanh box đã chiếu
    b = CA["rgb"].copy()
    cv2.polylines(b, [giu.astype(np.int32)], True, LO, 4, cv2.LINE_AA)
    cv2.polylines(b, [box_r.astype(np.int32)], True, CAM, 5, cv2.LINE_AA)
    for i, (x, y) in enumerate(box_r):
        cv2.circle(b, (int(x), int(y)), 10, CAM, -1, cv2.LINE_AA)
    cv2.drawMarker(b, tuple(tam_r.astype(int)), TRANG, cv2.MARKER_CROSS, 34, 3)

    m = 300
    x0 = int(max(min(box_r[:, 0].min(), giu[:, 0].min()) - m, 0))
    x1 = int(min(max(box_r[:, 0].max(), giu[:, 0].max()) + m, RW))
    y0 = int(max(min(box_r[:, 1].min(), giu[:, 1].min()) - m, 0))
    y1 = int(min(max(box_r[:, 1].max(), giu[:, 1].max()) + m, RH))
    b = b[y0:y1, x0:x1]
    kk = (TH * 2) / b.shape[0]
    b = cv2.resize(b, (int(b.shape[1] * kk), TH * 2), interpolation=cv2.INTER_AREA)
    for i, (x, y) in enumerate(box_r):
        px, py = int((x - x0) * kk), int((y - y0) * kk)
        dx = 16 if x > tam_r[0] else -40
        dy = -16 if y < tam_r[1] else 36
        cv2.putText(b, "%d" % (i + 1), (px + dx, py + dy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.95, TRANG, 4, cv2.LINE_AA)
        cv2.putText(b, "%d" % (i + 1), (px + dx, py + dy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.95, CAM, 2, cv2.LINE_AA)
    # Chú thích box lơ: kẻ đường dẫn từ mép box ra chỗ trống rồi ghi chữ, chứ
    # không dán sát đáy ảnh — ở đó nó bị viền của `vien()` cắt mất chân chữ.
    gx = int((giu[:, 0].max() - x0) * kk)
    gy = int((giu[:, 1].max() - y0) * kk)
    chu = "giu nguyen kich thuoc box: sai %.0f px" % lech_giu
    rong = cv2.getTextSize(chu, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0][0]
    tx = min(gx + 46, b.shape[1] - rong - 14)     # không để chữ tràn mép phải
    ty = gy + 60
    cv2.line(b, (gx, gy), (tx + 6, ty - 6), LO, 2, cv2.LINE_AA)
    cv2.putText(b, chu, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, DEN, 4, cv2.LINE_AA)
    cv2.putText(b, chu, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, LO, 1, cv2.LINE_AA)
    b = bang_ten(b, "ANH RGB 4056x3040  -  cam: 4 goc qua H  |  lo: neu CHI chuyen tam")

    cao = max(a.shape[0], b.shape[0])
    def dem(x):
        return cv2.copyMakeBorder(x, 0, cao - x.shape[0], 0, 0,
                                  cv2.BORDER_CONSTANT, value=NEN)
    cap = np.hstack([vien(dem(a), CAM), vien(dem(b), CAM)])
    ra = nhan_duoi(cap, "Anh nhiet nho hon gap %.2f lan: chuyen tam roi giu nguyen kich thuoc "
                        "thi box sai %.0f px. Rieng phan PHOI CANH o co mot box chi %.1f px, "
                        "nhung o co ca khung anh la %.0f px."
                   % (float(np.sqrt(abs(np.linalg.det(H[:2, :2] / H[2, 2])))),
                      lech_giu, lech_pc, lech_khung), cao=52, co=0.52)
    p = os.path.join(args.ra, "chieu_p1_bon_goc_qua_h.jpg")
    cv2.imwrite(p, vien(ra), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("[P1] giu-kich-thuoc %.0f px | phoi canh: box %.1f px, ca khung %.0f px -> %s (%.0f KB)"
          % (lech_giu, lech_pc, lech_khung, os.path.basename(p),
             os.path.getsize(p) / 1024))


# ====================================================== P2 · pixel thành tia
def lam_P2():
    """Mặt cắt ĐỨNG. Trục ngang = cự ly ngang tính từ điểm dưới chân camera
    (nadir), trục dọc = độ cao. Bốn tia của bốn góc box vẽ trên cùng mặt cắt."""
    ss, tf, ck = CA["ss"], CA["tf"], CA["ck"]
    box_r = qua_H(CA["box"])

    O, _, _ = pixel_ra_tia(box_r[0][0], box_r[0][1], ss, tf, ck)
    cam_lon, cam_lat, cam_alt = ecef2wgs.transform(*O)

    def met(lon, lat):
        return ((lon - cam_lon) * 111320 * np.cos(np.radians(cam_lat)),
                (lat - cam_lat) * 110540)

    tia = []
    for (u, v) in box_r:
        Oi, d, th = pixel_ra_tia(u, v, ss, tf, ck)
        r = cat_dsm(Oi, d)
        if r is None:
            continue
        lon, lat, h, t = r
        x, y = met(lon, lat)
        tia.append(dict(theta=th, cu_ly=float(np.hypot(x, y)), cao=h, t=t, lon=lon, lat=lat))
    if len(tia) < 4:
        print("[P2] khong du 4 tia cat duoc DSM"); return

    W, Ht = 1500, 780
    L, R_, T_, B_ = 96, 40, 40, 66
    cx_max = max(x["cu_ly"] for x in tia) * 1.18
    h_min = min(x["cao"] for x in tia) - 4
    h_max = cam_alt + 6

    cv = np.full((Ht, W, 3), NEN, np.uint8)

    def X(c):
        return int(L + c / cx_max * (W - L - R_))

    def Y(h):
        return int(T_ + (h_max - h) / (h_max - h_min) * (Ht - T_ - B_))

    # lưới + trục. Bước chia phải tính TỪ bề rộng thật: bốn góc một box lỗi chỉ
    # trải ra vài mét, chốt cứng bước 10 m thì trục ngang không còn nhãn nào.
    def buoc_dep(khoang, muc=6):
        tho = khoang / muc
        mu = 10 ** np.floor(np.log10(max(tho, 1e-9)))
        return float(min([x for x in (1, 2, 2.5, 5, 10) if x * mu >= tho] or [10]) * mu)

    bh = buoc_dep(h_max - h_min)
    h = np.ceil(h_min / bh) * bh
    while h <= h_max:
        cv2.line(cv, (L, Y(h)), (W - R_, Y(h)), (232, 226, 221), 1, cv2.LINE_AA)
        cv2.putText(cv, "%g m" % round(h, 2), (10, Y(h) + 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.46, XAM, 1, cv2.LINE_AA)
        h += bh

    bc = buoc_dep(cx_max)
    c = 0.0
    while c <= cx_max:
        cv2.line(cv, (X(c), T_), (X(c), Ht - B_), (238, 233, 229), 1, cv2.LINE_AA)
        cv2.putText(cv, "%g" % round(c, 2), (X(c) - 10, Ht - B_ + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, XAM, 1, cv2.LINE_AA)
        c += bc
    cv2.putText(cv, "cu ly ngang tinh tu diem duoi chan camera (m)",
                (W // 2 - 200, Ht - B_ + 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5, XAM, 1, cv2.LINE_AA)

    # mặt đất theo DSM, lấy dọc phương ngang của tia xa nhất
    xa = max(tia, key=lambda x: x["cu_ly"])
    dlon = (xa["lon"] - cam_lon) / max(xa["cu_ly"], 1e-9)
    dlat = (xa["lat"] - cam_lat) / max(xa["cu_ly"], 1e-9)
    mat = []
    for c in np.linspace(0, cx_max, 300):
        h = do_cao_dsm(cam_lon + dlon * c, cam_lat + dlat * c)
        if h is not None:
            mat.append((X(c), Y(h)))
    if len(mat) > 1:
        cv2.polylines(cv, [np.array(mat, np.int32)], False, XANH, 3, cv2.LINE_AA)
        du = np.array(mat + [(X(cx_max), Ht - B_), (X(0), Ht - B_)], np.int32)
        lop = cv.copy()
        cv2.fillPoly(lop, [du], (222, 231, 236))
        cv = cv2.addWeighted(lop, 0.55, cv, 0.45, 0)
        cv2.polylines(cv, [np.array(mat, np.int32)], False, XANH, 3, cv2.LINE_AA)

    # bốn tia
    for i, x in enumerate(sorted(tia, key=lambda z: z["cu_ly"])):
        p0 = (X(0), Y(cam_alt))
        p1 = (X(x["cu_ly"]), Y(x["cao"]))
        cv2.line(cv, p0, p1, CAM, 2, cv2.LINE_AA)
        cv2.circle(cv, p1, 8, DO, -1, cv2.LINE_AA)
        cv2.putText(cv, "goc %d  th=%.1f do  dai %.1f m" % (i + 1, x["theta"], x["t"]),
                    (p1[0] - 150, p1[1] - 18 - (i % 2) * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, DO, 1, cv2.LINE_AA)

    # camera
    cv2.line(cv, (X(0), Y(cam_alt)), (X(0), Y(h_min)), XAM, 1, cv2.LINE_AA)
    cv2.circle(cv, (X(0), Y(cam_alt)), 13, DEN, -1, cv2.LINE_AA)
    cv2.circle(cv, (X(0), Y(cam_alt)), 13, TRANG, 2, cv2.LINE_AA)
    h_tb = float(np.mean([z["cao"] for z in tia]))
    cv2.putText(cv, "tam chup  cao do %.2f m" % cam_alt, (X(0) + 20, Y(cam_alt) - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, DEN, 2, cv2.LINE_AA)
    cv2.putText(cv, "(cao hon mat dat %.1f m)" % (cam_alt - h_tb),
                (X(0) + 20, Y(cam_alt) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, XAM, 1, cv2.LINE_AA)
    cv2.putText(cv, "nadir", (X(0) + 8, Y(h_min) - 8), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, XAM, 1, cv2.LINE_AA)
    cv2.putText(cv, "mat dat theo DSM", (X(cx_max * 0.55), Y(min(z["cao"] for z in tia)) + 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.56, XANH, 2, cv2.LINE_AA)

    cv = bang_ten(cv, "MAT CAT DUNG  -  bon tia cua bon goc box, dung noi tham so f=%.0f px "
                      "va tu the anh %s" % (ss["f"], CA["nhan"]), co=0.54)
    cao = cam_alt - float(np.mean([z["cao"] for z in tia]))
    ra = nhan_duoi(cv, "Camera cao %.1f m so voi mat dat. Goc xien off-nadir %.1f-%.1f do; "
                       "chenh cu ly giua goc gan nhat va xa nhat %.1f m."
                   % (cao, min(z["theta"] for z in tia), max(z["theta"] for z in tia),
                      max(z["cu_ly"] for z in tia) - min(z["cu_ly"] for z in tia)))
    p = os.path.join(args.ra, "chieu_p2_dung_tia.jpg")
    cv2.imwrite(p, vien(ra), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[P2] cam_alt %.2f m -> %s (%.0f KB)"
          % (cam_alt, os.path.basename(p), os.path.getsize(p) / 1024))


# ========================================================== P3 · cắt DSM
def lam_P3():
    """Đồ thị độ cao dọc tia. Đây là chỗ 'một tia + một mặt = một điểm'."""
    ss, tf, ck = CA["ss"], CA["tf"], CA["ck"]
    box_r = qua_H(CA["box"])
    u, v = box_r.mean(0)                     # dò cho tâm box, cho hình gọn
    O, d, theta = pixel_ra_tia(u, v, ss, tf, ck)

    vet = []
    r = cat_dsm(O, d, ghi=vet)
    if r is None:
        print("[P3] tia khong cat DSM"); return
    lon, lat, h_cat, t_cat = r
    tho = [x for x in vet if x[0] == "tho"]
    doi = [x for x in vet if x[0] == "doi"]

    W, Ht = 1500, 940
    L, R_, T_ = 96, 300, 40
    ZH = 236                      # dải dành riêng cho ô phóng to, nằm DƯỚI đồ thị
    B_ = 66 + ZH
    t0, t1 = max(t_cat - 26, 0), t_cat + 8
    trong = [x for x in tho if t0 <= x[1] <= t1]
    h_lo = min(min(x[3] for x in trong), h_cat) - 2
    h_hi = max(max(x[2] for x in trong), h_cat) + 3

    cv = np.full((Ht, W, 3), NEN, np.uint8)

    def X(t):
        return int(L + (t - t0) / (t1 - t0) * (W - L - R_))

    def Y(h):
        return int(T_ + (h_hi - h) / (h_hi - h_lo) * (Ht - T_ - B_))

    for h in np.arange(np.floor(h_lo), h_hi, 2):
        cv2.line(cv, (L, Y(h)), (W - R_, Y(h)), (232, 226, 221), 1, cv2.LINE_AA)
        cv2.putText(cv, "%.0f m" % h, (12, Y(h) + 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.46, XAM, 1, cv2.LINE_AA)
    for t in range(int(t0 // 5 * 5), int(t1) + 5, 5):
        if t0 <= t <= t1:
            cv2.line(cv, (X(t), T_), (X(t), Ht - B_), (238, 233, 229), 1, cv2.LINE_AA)
            cv2.putText(cv, "%d" % t, (X(t) - 8, Ht - B_ + 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.46, XAM, 1, cv2.LINE_AA)
    cv2.putText(cv, "quang duong da di doc tia, tinh tu tam chup (m)",
                (L + 180, Ht - B_ + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, XAM, 1, cv2.LINE_AA)

    # Mặt DSM. Lấy mẫu LẠI trên toàn trục chứ không dùng `trong` — vòng dò thô
    # dừng ngay khi chạm đất, nên mặt đất sẽ cụt ở đúng điểm cắt và hình trông
    # như tia đâm vào hư không.
    md = []
    for t in np.linspace(t0, t1, 400):
        lo_, la_, _ = ecef2wgs.transform(*(O + t * d))
        h_ = do_cao_dsm(lo_, la_)
        if h_ is not None:
            md.append((X(t), Y(h_)))
    md = np.array(md, np.int32)
    lop = cv.copy()
    cv2.fillPoly(lop, [np.vstack([md, [[X(t1), Ht - B_], [X(t0), Ht - B_]]])], (222, 231, 236))
    cv = cv2.addWeighted(lop, 0.6, cv, 0.4, 0)
    cv2.polylines(cv, [md], False, XANH, 3, cv2.LINE_AA)

    # độ cao của TIA — vẽ suốt trục, chấm tròn là các bước dò thô 1 m thật
    tt = []
    for t in np.linspace(t0, t1, 400):
        _, _, al = ecef2wgs.transform(*(O + t * d))
        tt.append((X(t), Y(al)))
    cv2.polylines(cv, [np.array(tt, np.int32)], False, CAM, 3, cv2.LINE_AA)
    for x in trong[::2]:
        cv2.circle(cv, (X(x[1]), Y(x[2])), 3, CAM, -1, cv2.LINE_AA)

    # Các vòng chia đôi nằm trong khoảng dưới 1 m nên ở tỉ lệ chính chúng dồn
    # vào ĐÚNG MỘT VẠCH — vẽ thẳng ở đây thì phần "chia đôi liên tục" biến mất.
    # Chỉ đánh dấu nhẹ, rồi mở riêng một ô phóng to bên dưới.
    for x in doi:
        if t0 <= x[1] <= t1:
            cv2.circle(cv, (X(x[1]), Y(x[2])), 4, (150, 60, 190), -1, cv2.LINE_AA)

    # điểm cắt
    px, py = X(t_cat), Y(h_cat)
    cv2.line(cv, (px, T_), (px, Ht - B_), DO, 2, cv2.LINE_AA)
    cv2.circle(cv, (px, py), 12, DO, -1, cv2.LINE_AA)
    cv2.circle(cv, (px, py), 12, TRANG, 2, cv2.LINE_AA)

    # ---- ô phóng to: đúng các vòng chia đôi, trục ngang tính bằng CENTIMET
    zw, zh = W - R_ - L, ZH - 28
    zo = np.full((zh, zw, 3), (245, 240, 246), np.uint8)
    tz = [x[1] for x in doi] + [t_cat]
    z0, z1 = min(tz), max(tz)
    bien = max((z1 - z0) * 0.25, 0.05)
    z0, z1 = z0 - bien, z1 + bien

    def ZX(t):
        return int(58 + (t - z0) / (z1 - z0) * (zw - 92))

    hz = [x[2] for x in doi] + [h_cat]
    hz0, hz1 = min(hz) - 0.05, max(hz) + 0.05

    def ZY(h):
        return int(26 + (hz1 - h) / (hz1 - hz0) * (zh - 62))

    md_z = [(ZX(t), ZY(do_cao_dsm(*ecef2wgs.transform(*(O + t * d))[:2]) or h_cat))
            for t in np.linspace(z0, z1, 160)]
    cv2.polylines(zo, [np.array(md_z, np.int32)], False, XANH, 3, cv2.LINE_AA)
    tia_z = []
    for t in np.linspace(z0, z1, 160):
        _, _, al = ecef2wgs.transform(*(O + t * d))
        tia_z.append((ZX(t), ZY(al)))
    cv2.polylines(zo, [np.array(tia_z, np.int32)], False, CAM, 3, cv2.LINE_AA)

    for k, x in enumerate(doi):
        zx = ZX(x[1])
        cv2.line(zo, (zx, 22), (zx, zh - 34), (206, 196, 232), 1, cv2.LINE_AA)
        cv2.circle(zo, (zx, ZY(x[2])), 6, (150, 60, 190), -1, cv2.LINE_AA)
        cv2.putText(zo, "vong %d" % (k + 1), (zx - 26, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 60, 190), 1, cv2.LINE_AA)
        cv2.putText(zo, "%+.0f cm" % ((x[2] - x[3]) * 100), (zx - 24, zh - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, CHU, 1, cv2.LINE_AA)
    cv2.line(zo, (ZX(t_cat), 22), (ZX(t_cat), zh - 34), DO, 2, cv2.LINE_AA)
    cv2.circle(zo, (ZX(t_cat), ZY(h_cat)), 9, DO, -1, cv2.LINE_AA)
    cv2.circle(zo, (ZX(t_cat), ZY(h_cat)), 9, TRANG, 2, cv2.LINE_AA)
    cv2.putText(zo, "PHONG TO khoang %.0f cm quanh diem cat  -  so duoi moi vach la"
                    " chenh lech tia-DSM con lai" % ((z1 - z0) * 100),
                (10, zh - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.48, XAM, 1, cv2.LINE_AA)
    zy = Ht - zh - 12
    cv[zy:zy + zh, L:L + zw] = zo
    cv2.rectangle(cv, (L, zy), (L + zw, zy + zh), (206, 196, 232), 1, cv2.LINE_AA)
    # nối ô phóng to với điểm cắt trên đồ thị chính, để thấy nó phóng chỗ nào
    cv2.line(cv, (px, py + 14), (L + zw // 2, zy - 2), (206, 196, 232), 1, cv2.LINE_AA)

    # chú giải bên phải
    bx = W - R_ + 18
    for i, (mau, chu) in enumerate([
            (CAM, "do cao cua TIA"),
            (XANH, "do cao mat dat (DSM)"),
            ((150, 60, 190), "cac vong chia doi"),
            (DO, "diem cat: dap so")]):
        cv2.line(cv, (bx, T_ + 24 + i * 30), (bx + 34, T_ + 24 + i * 30), mau, 4, cv2.LINE_AA)
        cv2.putText(cv, chu, (bx + 44, T_ + 29 + i * 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, CHU, 1, cv2.LINE_AA)
    for i, chu in enumerate([
            "di %.1f m thi cham dat" % t_cat,
            "cao mat dat %.2f m" % h_cat,
            "goc xien %.1f do" % theta,
            "%d vong tho + %d vong chia doi" % (len(tho), len(doi)),
            "sai so con lai < 1 cm",
            "",
            "lon %.7f" % lon,
            "lat %.7f" % lat]):
        cv2.putText(cv, chu, (bx, T_ + 168 + i * 26), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, CHU if i < 5 else DO, 1, cv2.LINE_AA)

    cv = bang_ten(cv, "CAT TIA VOI DSM  -  hai duong gap nhau o dau thi do la diem tren mat dat",
                  co=0.56)
    ra = nhan_duoi(cv, "Truoc buoc nay tia chi noi 'loi nam dau do doc duong nay'. "
                       "Sau buoc nay: mot diem duy nhat.")
    p = os.path.join(args.ra, "chieu_p3_cat_dsm.jpg")
    cv2.imwrite(p, vien(ra), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[P3] t=%.2f m, h=%.2f m, %d tho + %d doi -> %s (%.0f KB)"
          % (t_cat, h_cat, len(tho), len(doi), os.path.basename(p),
             os.path.getsize(p) / 1024))


for ten, fn in [("P1", lam_P1), ("P2", lam_P2), ("P3", lam_P3)]:
    if not args.chi or args.chi.upper() == ten:
        fn()
