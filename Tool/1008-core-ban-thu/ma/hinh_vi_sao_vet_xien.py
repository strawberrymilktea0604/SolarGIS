#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ba hình trả lời câu hỏi: vì sao hộp VUÔNG trên ảnh nhiệt hoá XIÊN trên ortho?

Câu hỏi nghe như lỗi hiệu chuẩn (H làm méo), nhưng đo ra thì không phải. Ba hình
ở đây dựng đúng ba mắt xích của lập luận, toàn bộ bằng số THẬT chạy lại từ
`ket_qua/loi_4lop_cuoi.json` + `dsm.tif`, không có số vẽ tay:

  X1  ba khung      cùng MỘT lỗi trong ba hệ toạ độ — ảnh nhiệt 640x512 (hộp OBB,
                    4 góc đúng 90 độ), ảnh RGB sau khi qua H (vẫn ~90 độ), ortho
                    sau khi chiếu qua DSM (xiên hẳn). Chỉ ra khúc nào làm méo.
  X2  lát cắt đứng  vì sao khúc đó làm méo: hai góc của hộp rơi hai bên một BẬC
                    DSM ở mép tấm pin, tia xiên nên chênh cao biến thành lệch
                    ngang. Hình cắt dựng từ toạ độ tia thật của ca đang xét.
  X3  603 lỗi       không phải một ca cá biệt: tương quan độ xiên với chênh cao
                    DSM 4 góc trên toàn bộ 603 lỗi, kèm IoU tụt theo nhóm.

Ca mặc định là `0317` — xiên 16,8 độ, thấy lại ở 10 ảnh, conf 0,93, và hộp nằm
cách mép khung ảnh nhiệt 178 px nên vẽ ra không bị cắt cụt. Ca xiên nhất (`0315`,
81,5 độ) chỉ n=1 nên phần lớn là báo động giả; hơn nữa 8 trong 12 ca xiên nhất có
hộp CHẠM mép khung (cách mép <= 2 px) — vừa bị cắt vừa là chỗ tia xiên nhất, nên
không lấy làm minh hoạ chính dù trông ấn tượng.

Số thống kê ghi ra `ket_qua/vi_sao_vet_xien.json` để tài liệu trích lại.

    py -3.13 ma/hinh_vi_sao_vet_xien.py
    py -3.13 ma/hinh_vi_sao_vet_xien.py --chi X2 --seq 0341
"""
import argparse
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET

import cv2
import matplotlib
import numpy as np
import rasterio
from pyproj import Transformer

matplotlib.use("Agg")
import matplotlib.patches as mpatches          # noqa: E402
import matplotlib.pyplot as plt                # noqa: E402
from rasterio.windows import Window            # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XUAT = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")
MODEL = r"mo_hinh\fault_obb_4class.pt"

ap = argparse.ArgumentParser()
ap.add_argument("--chi", default="", help="chỉ dựng một hình: X1 / X2 / X3")
ap.add_argument("--seq", default="0317", help="ảnh lấy làm ca minh hoạ")
ap.add_argument("--conf", type=float, default=0.25)
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/hinh"))
args = ap.parse_args()
os.makedirs(args.ra, exist_ok=True)

plt.rcParams.update({
    "font.family": "Segoe UI",
    "font.size": 11,
    "axes.titlesize": 11.5,
    "axes.labelsize": 10.5,
    "figure.facecolor": "white",
})
CAM = "#c24d00"       # --ember
XANH = "#2f5f9e"      # --steel
LUC = "#3c8f4a"
XAM = "#8b8379"
CHU = "#1b1618"

MDEG = 111320 * np.cos(np.radians(11.424))
MLAT = 110570.0

# ------------------------------------------------------------------ nạp dữ liệu
D = json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))
H = np.array(D["H_thermal_to_rgb"], float)

loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
rows = {}
with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows[r["seq"]] = r

dsm = rasterio.open(os.path.join(XUAT, "dsm.tif"))
DSM = dsm.read(1)
oc = rasterio.open(os.path.join(XUAT, "ortho.tif"))
ecef2wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
wgs2ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)


def goc_nadir_that(d, lon, lat, h):
    """Góc giữa tia và phương THẲNG ĐỨNG tại điểm chạm, tính bằng độ.

    Không dùng `atan(hypot(x, y))` của hệ camera: đó là góc lệch TRỤC QUANG, mà
    trục quang của chuyến này nghiêng sẵn ~10° so với phương đứng. Lấy nhầm là
    công thức `lệch = Δh × tan(góc)` trên hình sai gấp ba (2,7° so với 10,0°)."""
    P = np.array(wgs2ecef.transform(lon, lat, h))
    up = np.array(wgs2ecef.transform(lon, lat, h + 1.0)) - P
    up /= np.linalg.norm(up)
    return float(np.degrees(np.arccos(np.clip(-np.asarray(d) @ up, -1, 1))))


def qua_H(P):
    """Pixel ảnh nhiệt -> pixel ảnh RGB. CHỈ H, không trừ `hieu_chinh_bo_sung`.

    `hinh_chuoi_chieu_thuc_te.py` có trừ, script này thì không — vì mục đích khác:
    ở đây phải dựng lại ĐÚNG cái poly đã nằm trong `loi_4lop_cuoi.json`, mà lượt
    quét sinh ra file đó chạy H trần (không có `--bu-tung-anh`). Trừ thêm vào là
    lệch ~0,5 m, đủ để 2 trong 4 góc nhảy qua bên kia bậc DSM và độ xiên đo được
    tụt từ 24,19° xuống 4,49° — tức là hình sẽ minh hoạ một ca KHÁC với ca đang
    kể. Đã kiểm: bỏ phần trừ thì 4 góc trùng poly đã lưu tới 0,00 m."""
    P = np.asarray(P, float).reshape(-1, 2)
    q = (H @ np.c_[P, np.ones(len(P))].T).T
    return q[:, :2] / q[:, 2:]


def do_cao_dsm(lon, lat):
    c, r = ~dsm.transform * (lon, lat)
    c, r = int(c), int(r)
    if 0 <= r < dsm.height and 0 <= c < dsm.width:
        v = DSM[r, c]
        if v != dsm.nodata and not np.isnan(v):
            return float(v)
    return None


def lech_vuong(P):
    """Độ lệch khỏi góc vuông LỚN NHẤT trong 4 góc của tứ giác, tính bằng độ.

    Lấy max chứ không lấy trung bình: một tứ giác có ba góc gần vuông và một góc
    bẹp vẫn là tứ giác hỏng, trung bình sẽ giấu mất chuyện đó."""
    P = np.asarray(P, float)
    a = []
    for i in range(4):
        v1, v2 = P[(i - 1) % 4] - P[i], P[(i + 1) % 4] - P[i]
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < 1e-12 or n2 < 1e-12:
            return np.nan
        c = np.clip(v1 @ v2 / (n1 * n2), -1, 1)
        a.append(abs(np.degrees(np.arccos(c)) - 90))
    return float(max(a))


def ra_met(poly, goc=None):
    """lon/lat -> mét phẳng quanh `goc` (mặc định: đỉnh đầu của tứ giác)."""
    poly = np.asarray(poly, float)
    g = np.asarray(goc if goc is not None else poly[0], float)
    return np.c_[(poly[:, 0] - g[0]) * MDEG, (poly[:, 1] - g[1]) * MLAT]


# ============================================ 1. thống kê toàn bộ 603 lỗi (X3)
def thong_ke():
    ke = []
    for d in loi:
        p = d.get("poly")
        if not p or len(p) != 4:
            continue
        g = lech_vuong(ra_met(p))
        hs = [do_cao_dsm(x, y) for x, y in p]
        dh = np.nan if any(h is None for h in hs) else max(hs) - min(hs)
        ke.append({"seq": d["seq"], "cls": d["cls"], "n": d.get("n"),
                   "iou": d.get("iou"), "lech_do": g, "chenh_cao_m": dh})
    G = np.array([k["lech_do"] for k in ke], float)
    Dh = np.array([k["chenh_cao_m"] for k in ke], float)
    Iou = np.array([k["iou"] if k["iou"] is not None else np.nan for k in ke], float)
    m = ~np.isnan(G) & ~np.isnan(Dh)
    nhom = {}
    for lo, hi, ten in [(0, 5, "<5 do"), (5, 15, "5-15 do"), (15, 1e9, ">15 do")]:
        s = (G >= lo) & (G < hi)
        nhom[ten] = {"n": int(s.sum()),
                     "chenh_cao_trung_vi": float(np.nanmedian(Dh[s])),
                     "iou_trung_vi": float(np.nanmedian(Iou[s]))}
    tk = {
        "nguon": "ket_qua/loi_4lop_cuoi.json + du_lieu/Thermal2_31M_full_export/dsm.tif",
        "so_loi": len(ke),
        "lech_trung_vi": float(np.nanmedian(G)),
        "lech_p90": float(np.nanpercentile(G, 90)),
        "lech_max": float(np.nanmax(G)),
        "tuong_quan_r": float(np.corrcoef(G[m], Dh[m])[0, 1]),
        "nhom": nhom,
        "chi_tiet": ke,
    }
    return tk, G, Dh, Iou


def rieng_H():
    """Riêng H làm méo bao nhiêu — trả (nhỏ nhất, trung vị, lớn nhất) độ.

    Quét chữ nhật mẫu khắp khung 640×512 với ba cỡ và bốn góc xoay. Cần con số
    này để bác bỏ cách giải thích 'tại hiệu chuẩn H sai': hàng 3 của H khác 0 nên
    H đúng là phép chiếu chứ không phải affine, nhưng biên độ thì không đáng kể."""
    ke = []
    for w, h in [(60, 40), (200, 150), (500, 400)]:
        for goc in (0, 30, 45, 60):
            c, s = np.cos(np.radians(goc)), np.sin(np.radians(goc))
            R = np.array([[c, -s], [s, c]])
            n = np.array([[-w / 2, -h / 2], [w / 2, -h / 2],
                          [w / 2, h / 2], [-w / 2, h / 2]]) @ R.T
            for cx in np.linspace(w / 2, 640 - w / 2, 5):
                for cy in np.linspace(h / 2, 512 - h / 2, 5):
                    ke.append(lech_vuong(qua_H(n + [cx, cy])))
    ke = np.array(ke, float)
    return float(np.nanmin(ke)), float(np.nanmedian(ke)), float(np.nanmax(ke))


# ================================================== 2. dựng lại MỘT ca cụ thể
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
        raise SystemExit("[DUNG] khong thay camera %s trong cameras.xml" % nhan)
    comp = ch.find(".//component/transform")
    ck = {"R": np.array(list(map(float, comp.find("rotation").text.split()))).reshape(3, 3),
          "T": np.array(list(map(float, comp.find("translation").text.split()))),
          "s": float(comp.find("scale").text)}
    return ss, tf, ck


def pixel_ra_tia(u, v, ss, tf, ck):
    """Pixel RGB -> (tâm chụp ECEF, vector đơn vị, góc lệch nadir độ).

    cx, cy của Metashape là ĐỘ LỆCH so với tâm ảnh nên phải trừ cả w/2 lẫn cx."""
    x = (u - ss["width"] / 2.0 - ss["cx"]) / ss["f"]
    y = (v - ss["height"] / 2.0 - ss["cy"]) / ss["f"]
    d_cam = np.array([x, y, 1.0])
    C = ck["s"] * (ck["R"] @ tf[:3, 3]) + ck["T"]
    d = ck["R"] @ (tf[:3, :3] @ d_cam)
    return C, d / np.linalg.norm(d), float(np.degrees(np.arctan(np.hypot(x, y))))


def cat_dsm_tia(O, d):
    """Cắt tia với DSM — chép NGUYÊN VĂN `quet_loi_anh_le.chieu()`: chia đôi thẳng
    trên đoạn t ∈ [10, 200] m, 40 vòng, không dò thô tìm khoảng chứa nghiệm.

    Cố ý không "cải tiến" thành dò-thô-rồi-chia-đôi: mục đích của hình là dựng lại
    đúng cái poly đã lưu, nên phải chạy đúng thuật toán đã sinh ra nó."""
    lo, hi = 10.0, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lon, lat, alt = ecef2wgs.transform(*(O + d * mid))
        h = do_cao_dsm(lon, lat)
        lo, hi = (mid, hi) if (h is None or alt > h) else (lo, mid)
    t = (lo + hi) / 2
    lon, lat, alt = ecef2wgs.transform(*(O + d * t))
    h = do_cao_dsm(lon, lat)
    return (lon, lat, h if h is not None else alt, t)


def dung_ca(seq):
    """Chạy lại đúng chuỗi của `quet_loi_anh_le.py` cho một ảnh, ghép về đúng
    phát hiện đã lưu trong loi_4lop_cuoi.json (ghép theo tâm đã chiếu)."""
    from ultralytics import YOLO
    r = rows[seq]
    th = cv2.imread(r["path_thermal"])
    rgb = cv2.imread(r["path_rgb"])
    nhan = os.path.splitext(os.path.basename(r["path_rgb"]))[0]
    ss, tf, ck = doc_cameras(nhan)

    res = YOLO(MODEL).predict(th, imgsz=640, conf=args.conf, verbose=False)[0]
    if getattr(res, "obb", None) is None or len(res.obb) == 0:
        raise SystemExit("[DUNG] anh %s khong co phat hien OBB" % seq)
    Q = res.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    CF = res.obb.conf.cpu().numpy()
    CL = [res.names[int(c)] for c in res.obb.cls.cpu().numpy()]

    ung = [d for d in loi if d["seq"] == seq and d.get("poly")]
    if not ung:
        raise SystemExit("[DUNG] khong co loi nao cua anh %s trong loi_4lop_cuoi.json" % seq)
    ung.sort(key=lambda d: -lech_vuong(ra_met(d["poly"])))
    d = ung[0]
    tam = np.mean(d["poly"], axis=0)

    tot = None
    for q, cf, cl in zip(Q, CF, CL):
        rgb_q = qua_H(q)
        dat = []
        for u, v in rgb_q:
            O, dd, gtruc = pixel_ra_tia(u, v, ss, tf, ck)
            h = cat_dsm_tia(O, dd)
            if h is None:
                break
            dat.append({"lon": h[0], "lat": h[1], "h": h[2], "t": h[3],
                        "goc_truc": gtruc,
                        "goc_nadir": goc_nadir_that(dd, h[0], h[1], h[2]),
                        "O": O, "d": dd})
        if len(dat) != 4:
            continue
        c = np.mean([[x["lon"], x["lat"]] for x in dat], axis=0)
        e = np.hypot((c[0] - tam[0]) * MDEG, (c[1] - tam[1]) * MLAT)
        if tot is None or e < tot["sai_tam"]:
            tot = dict(sai_tam=e, obb=q, obb_rgb=rgb_q, dat=dat, conf=float(cf), cls=cl)
    if tot is None:
        raise SystemExit("[DUNG] khong chieu duoc phat hien nao cua anh %s" % seq)

    tot.update(seq=seq, th=th, rgb=rgb, d=d, ss=ss, tf=tf, ck=ck, nhan=nhan)
    tot["lech_nhiet"] = lech_vuong(tot["obb"])
    tot["lech_rgb"] = lech_vuong(tot["obb_rgb"])
    tot["lech_dat"] = lech_vuong(ra_met([[x["lon"], x["lat"]] for x in tot["dat"]]))
    tot["chenh_cao"] = max(x["h"] for x in tot["dat"]) - min(x["h"] for x in tot["dat"])
    print("[ca] seq %s  %s conf %.2f  lech: nhiet %.2f -> RGB %.2f -> dat %.2f  "
          "chenh cao 4 goc %.2f m  (ghep lech tam %.2f m)"
          % (seq, tot["cls"], tot["conf"], tot["lech_nhiet"], tot["lech_rgb"],
             tot["lech_dat"], tot["chenh_cao"], tot["sai_tam"]))
    return tot


# ------------------------------------------------------------------ tiện vẽ
def khung_anh(ax, im, P, mau=CAM, lb=True):
    """imshow ảnh BGR + vẽ tứ giác P (pixel của chính ảnh đó), đánh số 4 góc."""
    ax.imshow(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
    ax.add_patch(mpatches.Polygon(P, closed=True, fill=False, ec=mau, lw=2.0))
    if lb:
        for i, (x, y) in enumerate(P):
            ax.plot(x, y, "o", ms=5, mfc="white", mec=mau, mew=1.8, zorder=5)
            ax.text(x, y - 6, "ABCD"[i], color=mau, fontsize=9, fontweight="bold",
                    ha="center", va="bottom")
    ax.set_xticks([])
    ax.set_yticks([])


def so(x, n=2):
    """Số kiểu Việt: dấu phẩy thập phân."""
    return ("%.*f" % (n, x)).replace(".", ",")


def cat_quanh(im, P, le=0.45):
    """Cắt ảnh quanh tứ giác, chừa lề theo % cạnh dài. Trả (ảnh, P đã dời gốc)."""
    P = np.asarray(P, float)
    cx, cy = P.mean(0)
    nua = float(np.ptp(P, axis=0).max()) * (0.5 + le) + 12
    # cửa sổ VUÔNG rồi mới kẹp vào ảnh: crop chữ nhật lệch tỉ lệ thì matplotlib
    # chừa dải trắng bên dưới, nhìn như ảnh bị cắt cụt.
    a = int(np.clip(cx - nua, 0, max(0, im.shape[1] - 2 * nua)))
    b = int(np.clip(cy - nua, 0, max(0, im.shape[0] - 2 * nua)))
    c = int(min(im.shape[1], a + 2 * nua))
    e = int(min(im.shape[0], b + 2 * nua))
    return im[b:e, a:c], P - [a, b]


def _goc_cua_so(px, le):
    x0, y0 = px.min(0)
    x1, y1 = px.max(0)
    m = max(x1 - x0, y1 - y0) * le + 20
    return int(max(0, x0 - m)), int(max(0, y0 - m))


def _cua_so(px, le):
    x0, y0 = px.min(0)
    x1, y1 = px.max(0)
    m = max(x1 - x0, y1 - y0) * le + 20
    c0, r0 = _goc_cua_so(px, le)
    return Window(c0, r0, int(min(oc.width, x1 + m)) - c0,
                  int(min(oc.height, y1 + m)) - r0)


# ================================================================= HÌNH X1
def ve_X1(ca):
    fig, axs = plt.subplots(1, 3, figsize=(12.4, 4.7))

    a, P = cat_quanh(ca["th"], ca["obb"], 0.9)
    khung_anh(axs[0], a, P)
    axs[0].set_title("BƯỚC 1 · Ảnh nhiệt 640×512 — đầu ra của YOLO\n"
                     "hộp OBB là chữ nhật xoay: lệch %s°" % so(ca["lech_nhiet"]),
                     color=CHU, pad=8)

    a, P = cat_quanh(ca["rgb"], ca["obb_rgb"], 0.9)
    khung_anh(axs[1], a, P, XANH)
    axs[1].set_title("BƯỚC 2 · Ảnh RGB 4056×3040 — sau khi qua H\n"
                     "vẫn gần vuông: lệch %s°" % so(ca["lech_rgb"]),
                     color=CHU, pad=8)

    ll = np.array([[x["lon"], x["lat"]] for x in ca["dat"]])
    px = np.array([(~oc.transform * (x, y)) for x, y in ll])
    win = _cua_so(px, 1.6)
    o = np.moveaxis(oc.read([1, 2, 3], window=win), 0, -1)[:, :, ::-1].copy()
    c0, r0 = _goc_cua_so(px, 1.6)
    khung_anh(axs[2], o, px - [c0, r0], LUC)
    axs[2].set_title("BƯỚC 3 · Ortho RGB — sau khi 4 tia cắt DSM\n"
                     "tứ giác xiên: lệch %s°" % so(ca["lech_dat"]),
                     color=CHU, pad=8)

    fig.suptitle("Cùng MỘT lỗi (ảnh %s, %s, conf %s) trong ba hệ toạ độ — "
                 "méo sinh ra ở bước 2→3, không phải 1→2"
                 % (ca["seq"], ca["cls"], so(ca["conf"])),
                 fontsize=12.5, y=0.99, color=CHU)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p = os.path.join(args.ra, "xien_x1_ba_khung.png")
    fig.savefig(p, dpi=190)
    plt.close(fig)
    print("->", p)


# ================================================================= HÌNH X2
def cat_mat_phang(O, d, z):
    """Cắt tia với MẶT PHẲNG NGANG ở cao độ z (thay cho DSM) — dùng để dựng cái
    vết 'đáng lẽ' nếu mặt đất phẳng, tức phần méo do địa hình bị bóc ra hết."""
    lo, hi = 1.0, 400.0
    for _ in range(60):
        m = (lo + hi) / 2
        _, _, alt = ecef2wgs.transform(*(O + m * d))
        lo, hi = (m, hi) if alt > z else (lo, m)
    lon, lat, _ = ecef2wgs.transform(*(O + (lo + hi) / 2 * d))
    return lon, lat


def ve_X2(ca):
    """Hai bảng cho cùng một ca:

      trái  lát cắt ĐỨNG qua hai góc chênh cao nhất — thấy bậc DSM và lượng lệch
            ngang mà nó đẻ ra. Tâm chụp cao 30 m nên không vẽ vào khung được;
            hai tia cứ chạy thẳng ra khỏi mép trên, có nhãn chỉ về đâu.
      phải  nhìn TỪ TRÊN XUỐNG — vết đã chiếu (xanh lá) chồng lên vết 'đáng lẽ'
            nếu mặt đất phẳng (xám đứt). Đây là chỗ nối 'lệch vài chục cm' với
            'xiên mười mấy độ': hộp chỉ rộng ~1 m nên xê một góc 20 cm là đủ.
    """
    dat = ca["dat"]
    hs = np.array([x["h"] for x in dat])
    i_cao, i_thap = int(np.argmax(hs)), int(np.argmin(hs))
    A, B = dat[i_cao], dat[i_thap]
    buoc = float(hs.min() - hs.max())          # âm: nền đất thấp hơn mặt tấm

    # vết 'đáng lẽ': cả 4 tia cắt mặt phẳng ngang ở cao độ mặt tấm
    z_tam = float(hs.max())
    phang = [cat_mat_phang(x["O"], x["d"], z_tam) for x in dat]

    # Mặt cắt đặt dọc HƯỚNG DỊCH của góc thấp (từ chỗ nó đáng lẽ rơi tới chỗ nó
    # thật sự rơi), không phải dọc đường nối hai góc. Dịch do địa hình luôn chạy
    # theo phương xuyên tâm nadir; cắt đúng phương đó thì đoạn đo trên hình bằng
    # trọn vẹn Δh × tan(nadir), cắt lệch phương là hình ghi thiếu.
    g = np.array([A["lon"], A["lat"]])

    def en(lon, lat):
        return np.array([(lon - g[0]) * MDEG, (lat - g[1]) * MLAT])

    truc = en(B["lon"], B["lat"]) - en(*phang[i_thap])
    truc = truc / (np.linalg.norm(truc) + 1e-12)

    def toa_do(lon, lat, alt):
        return float(en(lon, lat) @ truc), float(alt - z_tam)

    lonC, latC, altC = ecef2wgs.transform(*A["O"])
    sC, uC = toa_do(lonC, latC, altC)
    sA, uA = toa_do(A["lon"], A["lat"], A["h"])
    sB, uB = toa_do(B["lon"], B["lat"], B["h"])
    sP, uP = toa_do(*phang[i_thap], z_tam)
    lech = abs(sB - sP)

    fig, axs = plt.subplots(1, 2, figsize=(11.6, 5.1),
                            gridspec_kw={"width_ratios": [1.25, 1]})

    # ------------------------------------------------------- trái: lát cắt đứng
    ax = axs[0]
    s0, s1 = min(sA, sB, sP) - 1.3, max(sA, sB, sP) + 1.3
    u0, u1 = buoc - 1.1, 2.6
    # Mép tấm nằm giữa sP và sA: tia của góc thấp KHÔNG chạm mặt tấm ở sP (nếu
    # chạm thì nó đã dừng ở đó), còn góc cao thì đậu hẳn trên tấm ở sA. Phía nào
    # là tấm suy ra từ dấu của sA so với mép — không giả định trái/phải cố định.
    canh = float(np.clip((sA + sP) / 2, s0 + 0.35, s1 - 0.35))
    tam_ben_phai = sA > canh
    o_tam = (canh, s1) if tam_ben_phai else (s0, canh)
    o_dat = (s0, canh) if tam_ben_phai else (canh, s1)

    ax.fill_between(o_tam, [u0, u0], [0, 0], color="#3b6ea8", alpha=.18, lw=0)
    ax.plot(o_tam, [0, 0], color=XANH, lw=3.2, solid_capstyle="butt")
    ax.plot([canh, canh], [0, buoc], color=XANH, lw=3.2)
    ax.fill_between(o_dat, [u0, u0], [buoc, buoc], color="#7a6a5a", alpha=.16, lw=0)
    ax.plot(o_dat, [buoc, buoc], color="#7a6a5a", lw=3.2)
    ax.text(o_tam[1] - 0.12 if tam_ben_phai else o_tam[0] + 0.12, 0.16,
            "mặt tấm pin", color=XANH, fontsize=10,
            ha="right" if tam_ben_phai else "left")
    ax.text(o_dat[0] + 0.12 if tam_ben_phai else o_dat[1] - 0.12, buoc + 0.16,
            "mặt đất phía sau", color="#7a6a5a", fontsize=10,
            ha="left" if tam_ben_phai else "right")
    lui = 0.14 if tam_ben_phai else -0.14
    ax.annotate("", xy=(canh + lui, 0), xytext=(canh + lui, buoc),
                arrowprops=dict(arrowstyle="<->", color=CAM, lw=1.7))
    ax.text(canh + 2 * lui, buoc / 2, "bậc DSM\n%s m" % so(abs(buoc)), color=CAM,
            fontsize=10.5, ha="left" if tam_ben_phai else "right",
            va="center", fontweight="bold")

    # hai tia: kéo tới mép trên khung rồi ghi chú tâm chụp nằm ngoài hình
    for (s_, u_), x_, nh, mau in [((sA, uA), A, "góc đậu trên MẶT TẤM", XANH),
                                  ((sB, uB), B, "góc TỤT XUỐNG ĐẤT", "#6b5b4b")]:
        k = (u1 - u_) / (uC - u_)
        ax.plot([s_, s_ + k * (sC - s_)], [u_, u1], color=mau, lw=1.8)
        ax.plot([s_], [u_], "o", ms=8.5, mfc="white", mec=mau, mew=2.3, zorder=6)
        ax.text(s_, u_ - 0.16, "%s\nnadir %s°" % (nh, so(x_["goc_nadir"], 1)),
                color=mau, fontsize=9.5, ha="center", va="top")
    ax.text(0.5, 0.985, "hai tia đi về tâm chụp — cao %s m so với mặt tấm" % so(uC, 1),
            transform=ax.transAxes, ha="center", va="top", fontsize=10,
            color=CAM, fontweight="bold")

    ax.plot([sP], [uP], "o", ms=8.5, mfc="white", mec=XAM, mew=2.2, zorder=6)
    ax.annotate("", xy=(sP, 0.62), xytext=(sB, 0.62),
                arrowprops=dict(arrowstyle="<->", color="#b3261e", lw=2.0))
    ax.text((sP + sB) / 2, 0.74, "LỆCH %s m = %s m × tan %s°"
            % (so(lech), so(abs(buoc)), so(B["goc_nadir"], 1)),
            color="#b3261e", fontsize=10.5, ha="center", va="bottom", fontweight="bold")
    ax.text(sP, uP - 0.16, "chỗ góc này ĐÁNG LẼ rơi\nnếu mặt đất phẳng",
            color=XAM, fontsize=9.5, ha="center", va="top")

    ax.set_xlim(s0, s1)
    ax.set_ylim(u0, u1)
    ax.set_xlabel("khoảng cách ngang trên mặt đất (m)")
    ax.set_ylabel("độ cao so với mặt tấm (m)")
    ax.set_title("Lát cắt đứng — chênh cao %s m biến thành lệch ngang %s m"
                 % (so(abs(buoc)), so(lech)), color=CHU, pad=8)
    ax.grid(alpha=.16)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    # ------------------------------------------------------- phải: nhìn từ trên
    ax = axs[1]
    that = np.array([[x["lon"], x["lat"]] for x in dat])
    tam = that.mean(0)
    Mt = ra_met(that, tam)
    Mp = ra_met(np.array(phang), tam)
    ax.add_patch(mpatches.Polygon(Mp, closed=True, fill=False, ec=XAM, lw=2.0,
                                  ls=(0, (5, 3))))
    ax.add_patch(mpatches.Polygon(Mt, closed=True, fc=LUC, alpha=.13, ec=LUC, lw=2.4))
    for i in range(4):
        ax.annotate("", xy=Mt[i], xytext=Mp[i],
                    arrowprops=dict(arrowstyle="->", color="#b3261e", lw=1.5))
        ax.text(*Mt[i], "  " + "ABCD"[i], color=LUC, fontsize=9.5, fontweight="bold",
                va="center")
    ax.plot(*Mp.T[0:2], "o", ms=4, mfc="white", mec=XAM, mew=1.4, ls="none")
    ax.set_aspect("equal")
    r = float(np.abs(np.vstack([Mt, Mp])).max()) * 1.5 + 0.25
    ax.set_xlim(-r, r)
    ax.set_ylim(-r, r)
    ax.set_xlabel("Đông (m)")
    ax.set_ylabel("Bắc (m)")
    ax.grid(alpha=.16)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Nhìn từ trên xuống — %s: nếu mặt đất phẳng (lệch %s°)\n"
                 "%s: vết thật sau khi cắt DSM (lệch %s°)"
                 % ("xám đứt", so(lech_vuong(Mp)), "xanh lá", so(lech_vuong(Mt))),
                 color=CHU, pad=8)

    fig.suptitle("Ảnh %s — hộp chỉ rộng khoảng %s m, nên xê một góc %s m là đủ "
                 "xiên %s°" % (ca["seq"], so(min(np.linalg.norm(Mt[1] - Mt[0]),
                                                 np.linalg.norm(Mt[2] - Mt[1])), 1),
                               so(lech), so(ca["lech_dat"], 1)),
                 fontsize=12.5, y=0.99, color=CHU)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    p = os.path.join(args.ra, "xien_x2_lat_cat.png")
    fig.savefig(p, dpi=190)
    plt.close(fig)
    print("->", p)



# ================================================================= HÌNH X3
def ve_X3(tk, G, Dh, Iou):
    fig, axs = plt.subplots(1, 2, figsize=(11.2, 4.5),
                            gridspec_kw={"width_ratios": [1.35, 1]})
    m = ~np.isnan(G) & ~np.isnan(Dh)
    ax = axs[0]
    ax.scatter(Dh[m], G[m], s=13, c=XANH, alpha=.35, lw=0)
    ax.axvline(0.8, color=CAM, ls=(0, (5, 3)), lw=1.4)
    ax.text(0.86, ax.get_ylim()[1] * .93, "ngưỡng cảnh báo 0,8 m",
            color=CAM, fontsize=9.5, va="top")
    ax.set_xlabel("chênh cao DSM giữa 4 góc (m)")
    ax.set_ylabel("độ lệch khỏi góc vuông (°)")
    ax.set_title("%d lỗi — càng vắt qua bậc DSM càng xiên\nhệ số tương quan r = %s"
                 % (tk["so_loi"], so(tk["tuong_quan_r"], 3)), color=CHU, pad=8)
    ax.grid(alpha=.18)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    ax = axs[1]
    ax.axis("off")
    ten = list(tk["nhom"])
    hien = {"<5 do": "< 5°", "5-15 do": "5 – 15°", ">15 do": "> 15°"}
    cot = ["nhóm độ xiên", "số lỗi", "chênh cao DSM\n(trung vị)", "IoU với tấm\n(trung vị)"]
    du = [[hien[t], str(tk["nhom"][t]["n"]),
           so(tk["nhom"][t]["chenh_cao_trung_vi"]) + " m",
           so(tk["nhom"][t]["iou_trung_vi"], 3)] for t in ten]
    b = ax.table(cellText=du, colLabels=cot, cellLoc="center", loc="center",
                 colWidths=[.24, .16, .30, .30])
    b.auto_set_font_size(False)
    b.set_fontsize(10.5)
    b.scale(1, 2.1)
    for (r, c), o in b.get_celld().items():
        o.set_edgecolor("#ddd6cf")
        if r == 0:
            o.set_facecolor("#f2ede8")
            o.set_text_props(fontweight="bold", color=CHU)
        elif r == 3:
            o.set_facecolor("#fdeee6")
    ax.set_title("Xiên nhiều thì bước gán tấm hỏng theo\n"
                 "toàn bộ %d lỗi: trung vị %s° · p90 %s° · lớn nhất %s°"
                 % (tk["so_loi"], so(tk["lech_trung_vi"]), so(tk["lech_p90"]),
                    so(tk["lech_max"], 1)),
                 color=CHU, pad=14)
    fig.tight_layout()
    p = os.path.join(args.ra, "xien_x3_bieu_do.png")
    fig.savefig(p, dpi=190)
    plt.close(fig)
    print("->", p)


# ===================================================================== chạy
tk, G, Dh, Iou = thong_ke()
print("[thong ke] %d loi | trung vi %.2f | p90 %.2f | max %.2f | r = %.3f"
      % (tk["so_loi"], tk["lech_trung_vi"], tk["lech_p90"], tk["lech_max"],
         tk["tuong_quan_r"]))
tk["rieng_H"] = dict(zip(("nho_nhat", "trung_vi", "lon_nhat"), rieng_H()))
print("[rieng H]  chu nhat mau qua H lech %.2f - %.2f do (trung vi %.2f)"
      % (tk["rieng_H"]["nho_nhat"], tk["rieng_H"]["lon_nhat"],
         tk["rieng_H"]["trung_vi"]))

ca = None
if args.chi in ("", "X1", "X2"):
    ca = dung_ca(args.seq)
    tk["ca_minh_hoa"] = {"seq": ca["seq"], "cls": ca["cls"], "conf": ca["conf"],
                         "lech_nhiet": ca["lech_nhiet"], "lech_rgb": ca["lech_rgb"],
                         "lech_dat": ca["lech_dat"], "chenh_cao_m": ca["chenh_cao"],
                         "goc_nadir": [x["goc_nadir"] for x in ca["dat"]],
                         "cao_do_4_goc": [x["h"] for x in ca["dat"]]}

if args.chi in ("", "X1"):
    ve_X1(ca)
if args.chi in ("", "X2"):
    ve_X2(ca)
if args.chi in ("", "X3"):
    ve_X3(tk, G, Dh, Iou)

p = os.path.join(BASE, "ket_qua/vi_sao_vet_xien.json")
json.dump(tk, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("->", p)
