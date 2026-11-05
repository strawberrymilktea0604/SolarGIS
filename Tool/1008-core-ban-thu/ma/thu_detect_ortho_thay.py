#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quét `fault_obb_4class.pt` thẳng trên ORTHO NHIỆT THẦY GHÉP (Metashape).

CÂU HỎI: `ma/thu_detect_tren_ortho.py` đã đo ortho TỰ GHÉP. Ortho của thầy
(`du_lieu/Thermal2_31M_full_export/thermal_ortho.tif`) khác ở HAI điểm ngược
chiều nhau, nên không suy ra được, phải đo:

  (+) GIỮ NGUYÊN BẢNG MÀU GỐC. Ortho tự ghép dựng từ ảnh đã IMREAD_GRAYSCALE
      (`ghep_ortho_nhiet.py:288`) rồi tô lại INFERNO — mất 10,4 điểm chỉ vì đổi
      màu. Ortho thầy là RGBA, gam màu của nó cách gam màu ảnh lẻ ironbow trung
      bình 1,6/255 → cùng bảng màu mà model được train trên đó.
  (-) LỆCH ĐỊA LÝ CỠ MÉT. Trung vị 268 cm so với RGB (bản tự ghép 2,56 cm) và
      không phải dịch đều (std dx/dy ~142 cm). Nên KHÔNG được chấm bằng ngưỡng
      1 m như bản kia — sẽ ra gần 0 vì lỗi ĐỊNH VỊ chứ không phải vì model mù.

CÁCH CHẤM: không chốt một ngưỡng, mà ghi lại KHOẢNG CÁCH rồi vẽ đường cong
recall theo dung sai 0,5→6 m. Ortho tự ghép bão hoà ngay ở 1 m; ortho thầy phải
nới tới vài mét mới bão hoà — chênh lệch giữa hai đường cong CHÍNH LÀ sai số
định vị, tách khỏi năng lực nhìn của model.

CHỐNG TỰ LỪA: cửa sổ 640x512 chỉ rộng 16,8 x 13,4 m nên dung sai 5 m gần bằng
"có phát hiện nào trong ô không". Vì thế mỗi ô còn ghi số phát hiện; mục
`_lam_phong_dung_sai` cho biết nếu chấm bừa (ô nào có phát hiện cũng tính đúng)
thì recall là bao nhiêu — đọc số ở dung sai lớn phải trừ hao theo mốc đó.

    py -3.13 ma/thu_detect_ortho_thay.py --so-loi 160     # dò nhanh ma trận
    py -3.13 ma/thu_detect_ortho_thay.py                  # đủ 603, ~25 phút CPU
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np
import rasterio
from rasterio.windows import Window

import goc  # dua tien trinh ve goc du an  # noqa: F401

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = r"mo_hinh\fault_obb_4class.pt"
THAY = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export/thermal_ortho.tif")
TULAM = os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif")

ap = argparse.ArgumentParser()
ap.add_argument("--conf", type=float, default=0.25, help="ngưỡng chốt của pipeline")
ap.add_argument("--so-loi", type=int, default=0, dest="so_loi",
                help="0 = ca 603. Khac 0 thi LAY RAI DEU, khong cat dau danh sach "
                     "(12 dong dau toan ca conf cao, cat dau la tu lua)")
ap.add_argument("--gop-m", type=float, default=0.60, dest="gop_m")
ap.add_argument("--phu-toi-thieu", type=float, default=0.90, dest="phu_min")
ap.add_argument("--bo-qua-D", action="store_true", dest="bo_D")
ap.add_argument("--model", default=MODEL)
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/detect_ortho_thay.json"))
args = ap.parse_args()

TW, TH = 640, 512
DUNG_SAI = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]   # m
XOAY = [0, 90, 180, 270]


def met(lat):
    return 111320.0 * np.cos(np.radians(lat)), 110574.0


def to_inferno(xam):
    """Xam -> INFERNO, dung cach ortho tu ghep duoc to (ghep_ortho_nhiet.py:409)."""
    g = cv2.normalize(xam, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)


def xoay_anh(col, deg):
    if not deg:
        return col
    return cv2.rotate(col, {90: cv2.ROTATE_90_CLOCKWISE,
                            180: cv2.ROTATE_180,
                            270: cv2.ROTATE_90_COUNTERCLOCKWISE}[deg])


def go_xoay(x, y, W, H, deg):
    """Toa do trong anh DA XOAY -> toa do trong o goc W x H."""
    if deg == 90:
        return y, H - 1 - x
    if deg == 270:
        return W - 1 - y, x
    if deg == 180:
        return W - 1 - x, H - 1 - y
    return x, y


def tam_obb(r, names):
    if getattr(r, "obb", None) is None or len(r.obb) == 0:
        return np.zeros((0, 2)), np.zeros(0), []
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    tam = np.stack([q[:, :, 0].mean(1), q[:, :, 1].mean(1)], 1)
    return tam, r.obb.conf.cpu().numpy(), [names[int(c)] for c in r.obb.cls.cpu().numpy()]


def duong_cong(dmin, n_o):
    """dmin = khoang cach (m) toi phat hien gan nhat, inf neu o trong."""
    d = np.asarray(dmin, float)
    return {("%.1f" % t): round(float((d < t).sum()) / max(n_o, 1), 4) for t in DUNG_SAI}


# ------------------------------------------------------------------ du lieu vao
loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
if args.so_loi and args.so_loi < len(loi):
    loi = [loi[k] for k in np.linspace(0, len(loi) - 1, args.so_loi).astype(int)]
ML, MT = met(float(np.mean([x["lat"] for x in loi])))

from ultralytics import YOLO           # noqa: E402
model = YOLO(args.model)
names = model.names

kq = {
    "_cau_hoi": "cung fault_obb_4class.pt, quet tren ortho nhiet THAY GHEP thi duoc gi",
    "_ortho_thay": os.path.relpath(THAY, BASE).replace("\\", "/"),
    "conf": args.conf, "so_loi_moc": len(loi), "dung_sai_m": DUNG_SAI,
    "_moc": ("603 loi trong loi_4lop_cuoi.json DEU do chinh model nay bat tren anh le "
             "ironbow goc -> nhanh anh le = 100 % theo dinh nghia, la MOC chu khong "
             "phai phep do doc lap."),
}
print("=" * 78)
print("QUET ORTHO THAY GHEP - %s, conf %.2f, %d loi moc"
      % (os.path.basename(args.model), args.conf, len(loi)))
print("=" * 78)


# ------------------------------------------- C: cua so quanh loi, moi cau hinh
def chay_C(ten, duong_dan, che_do_mau, deg):
    """che_do_mau: 'goc' = lay thang RGB cua ortho; 'inferno' = xam -> INFERNO."""
    src = rasterio.open(duong_dan)
    gsd_cm = abs(src.transform[0]) * ML * 100.0
    t0 = time.time()
    dmin, n_det, bo_mep, bo_thung = [], [], 0, 0
    for d in loi:
        r_, c_ = src.index(d["lon"], d["lat"])
        c0, r0 = int(c_ - TW / 2), int(r_ - TH / 2)
        if c0 < 0 or r0 < 0 or c0 + TW > src.width or r0 + TH > src.height:
            bo_mep += 1
            continue
        if src.count >= 3:
            a = src.read([1, 2, 3], window=Window(c0, r0, TW, TH))
            phu = (a.sum(0) > 0).mean()
            col = a.transpose(1, 2, 0)[:, :, ::-1].copy() if che_do_mau == "goc" \
                else to_inferno(cv2.cvtColor(a.transpose(1, 2, 0), cv2.COLOR_RGB2GRAY))
        else:
            im = src.read(1, window=Window(c0, r0, TW, TH))
            phu = (im != 0).mean()
            col = to_inferno(im)
        if phu < args.phu_min:
            bo_thung += 1
            continue
        col = xoay_anh(col, deg)
        ch, cw = col.shape[:2]
        r = model.predict(col, imgsz=640, conf=args.conf, verbose=False)[0]
        tam, cf, cl = tam_obb(r, names)
        n_det.append(len(tam))
        if not len(tam):
            dmin.append(np.inf)
            continue
        # tam cua so CHINH LA loi moc; xoay quanh tam giu nguyen khoang cach toi tam
        dm = np.hypot(tam[:, 0] - cw / 2, tam[:, 1] - ch / 2) * gsd_cm / 100.0
        dmin.append(float(dm.min()))
    src.close()
    n_o = len(dmin)
    co_det = int(np.sum(np.asarray(n_det) > 0))
    huu_han = [x for x in dmin if np.isfinite(x)]
    out = {
        "o_thu": n_o, "bo_vi_mep": bo_mep, "bo_vi_thung": bo_thung,
        "gsd_cm_per_px": round(gsd_cm, 3),
        "recall_theo_dung_sai_m": duong_cong(dmin, n_o),
        "_lam_phong_dung_sai": {
            "_y": "cham bua: o nao co phat hien cung tinh dung. Tran cua cot dung sai lon.",
            "o_co_phat_hien": co_det, "recall_neu_cham_bua": round(co_det / max(n_o, 1), 4),
            "phat_hien_tren_o_trung_vi": float(np.median(n_det)) if n_det else 0.0,
        },
        "lech_trung_vi_m": round(float(np.median(huu_han)), 2) if huu_han else None,
        "giay": round(time.time() - t0, 1),
    }
    rc = out["recall_theo_dung_sai_m"]
    print("  %-32s 1m %5.1f%% | 2m %5.1f%% | 3m %5.1f%% | 5m %5.1f%%   (bua %5.1f%%, lech TV %s m)"
          % (ten, 100 * rc["1.0"], 100 * rc["2.0"], 100 * rc["3.0"], 100 * rc["5.0"],
             100 * out["_lam_phong_dung_sai"]["recall_neu_cham_bua"], out["lech_trung_vi_m"]))
    return out


print("")
print("[C] cua so 640x512 dat loi vao chinh giua - do huong canh & bang mau")
print("-" * 78)
kq["C"] = {}
for deg in XOAY:
    kq["C"]["thay_mau_goc_xoay%d" % deg] = chay_C(
        "THAY  mau goc    xoay %3d" % deg, THAY, "goc", deg)
for deg in XOAY:
    kq["C"]["thay_inferno_xoay%d" % deg] = chay_C(
        "THAY  ->INFERNO  xoay %3d" % deg, THAY, "inferno", deg)
for deg in (0, 270):
    kq["C"]["tulam_inferno_xoay%d" % deg] = chay_C(
        "TU GHEP ->INFERNO xoay %3d" % deg, TULAM, "inferno", deg)

# huong + bang mau tot nhat tren ortho thay. Cham bang TONG ca duong cong chu khong
# mot nguong - o day 90 va 270 do sat nhau, chot theo mot nguong la chot theo nhieu.
tot = max([k for k in kq["C"] if k.startswith("thay_")],
          key=lambda k: sum(kq["C"][k]["recall_theo_dung_sai_m"].values()))
deg_tot = int(tot.split("xoay")[1])
mau_tot = "goc" if "mau_goc" in tot else "inferno"
kq["cau_hinh_tot_nhat"] = {"khoa": tot, "xoay": deg_tot, "bang_mau": mau_tot}
print("-" * 78)
print("-> cau hinh tot nhat tren ortho thay: %s" % tot)

# ------------------------------------------- D: quet truot toan ortho thay
if not args.bo_D:
    print("")
    print("[D] quet truot TOAN ortho thay (%s, xoay %d)" % (mau_tot, deg_tot))
    print("-" * 78)
    t0 = time.time()
    src = rasterio.open(THAY)
    gsd_cm = abs(src.transform[0]) * ML * 100.0
    SX, SY = int(TW * 0.8), int(TH * 0.8)
    phat, o_thu, o_bo = [], 0, 0
    rows_ = list(range(0, src.height - TH + 1, SY))
    cols_ = list(range(0, src.width - TW + 1, SX))
    for a_i, r0 in enumerate(rows_, 1):
        for c0 in cols_:
            a = src.read([1, 2, 3], window=Window(c0, r0, TW, TH))
            if (a.sum(0) > 0).mean() < 0.30:
                o_bo += 1
                continue
            o_thu += 1
            col = a.transpose(1, 2, 0)[:, :, ::-1].copy() if mau_tot == "goc" \
                else to_inferno(cv2.cvtColor(a.transpose(1, 2, 0), cv2.COLOR_RGB2GRAY))
            r = model.predict(xoay_anh(col, deg_tot), imgsz=640, conf=args.conf,
                              verbose=False)[0]
            if getattr(r, "obb", None) is None or len(r.obb) == 0:
                continue
            quad = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
            cf = r.obb.conf.cpu().numpy()
            cl = [names[int(c)] for c in r.obb.cls.cpu().numpy()]
            for k in range(len(quad)):
                g = np.array([go_xoay(x, y, TW, TH, deg_tot) for x, y in quad[k]], float)
                lon, lat = src.xy(r0 + g[:, 1].mean(), c0 + g[:, 0].mean())
                phat.append({
                    "lon": lon, "lat": lat, "conf": float(cf[k]), "cls": cl[k],
                    "poly": [list(src.xy(r0 + gy, c0 + gx)) for gx, gy in g],
                    "w_m": float(np.ptp(g[:, 0]) * gsd_cm / 100),
                    "h_m": float(np.ptp(g[:, 1]) * gsd_cm / 100),
                })
        print("  hang %d/%d ... %d o, %d phat hien tho" % (a_i, len(rows_), o_thu, len(phat)))
    src.close()

    phat.sort(key=lambda x: -x["conf"])
    cum = []
    for p in phat:
        if all(np.hypot((p["lon"] - q["lon"]) * ML, (p["lat"] - q["lat"]) * MT) >= args.gop_m
               for q in cum):
            cum.append(p)

    P = np.array([[p["lon"] * ML, p["lat"] * MT] for p in cum])
    G = np.array([[d["lon"] * ML, d["lat"] * MT] for d in loi])
    DX = P[:, None, 0] - G[None, :, 0]
    DY = P[:, None, 1] - G[None, :, 1]
    DM = np.hypot(DX, DY)
    d_moc = DM.min(0)          # moi loi moc -> phat hien gan nhat
    d_phat = DM.min(1)         # moi phat hien -> loi moc gan nhat
    for i, p in enumerate(cum):
        p["lech_toi_loi_gan_nhat_cm"] = round(float(d_phat[i]) * 100, 1)

    # bu dich deu tot nhat: xem bao nhieu phan khoang cach chi la mot phep tinh tien
    b = np.linspace(-5, 5, 101)
    luoi = np.array([[float(np.median(np.hypot(DX - dx, DY - dy).min(0)))
                      for dx in b] for dy in b])
    iy, ix = np.unravel_index(np.argmin(luoi), luoi.shape)
    d_moc_bu = np.hypot(DX - b[ix], DY - b[iy]).min(0)

    # --- doi mot-doi-mot: moi phat hien chi duoc nhan MOT loi moc -----------
    # Lang gieng gan nhat cho phep MOT phat hien "bat trung" nhieu loi moc cung
    # luc, nen o dung sai lon no dem ca do DAY DAC chu khong phai do trung khop.
    def doi_mot_mot(Dm, t):
        thu = np.argwhere(Dm < t)
        thu = thu[np.argsort(Dm[thu[:, 0], thu[:, 1]])]
        dung_p, dung_g, n = set(), set(), 0
        for i, j in thu:
            if i not in dung_p and j not in dung_g:
                dung_p.add(int(i)); dung_g.add(int(j)); n += 1
        return n

    # --- moc ngau nhien: rai lai chinh so phat hien do vao vung ortho co phu --
    # Neu "recall o 3 m" cua moc ngau nhien cung cao thi con so that khong noi
    # len dieu gi - do la mat do, khong phai nang luc.
    rng = np.random.default_rng(0)
    lo, la_ = P[:, 0].min(), P[:, 1].min()
    hi, ha = P[:, 0].max(), P[:, 1].max()
    R = np.stack([rng.uniform(lo, hi, len(P)), rng.uniform(la_, ha, len(P))], 1)
    DMr = np.hypot(R[:, None, 0] - G[None, :, 0], R[:, None, 1] - G[None, :, 1])

    ds = args.out.replace(".json", "_ds_phat_hien.json")
    json.dump(cum, open(ds, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    kq["D_quet_truot"] = {
        "_mo_ta": "quet truot ca ortho thay, gop trung %.2f m, doi chieu %d loi nhanh anh le"
                  % (args.gop_m, len(loi)),
        "_canh_bao": ("603 loi KHONG phai chan ly day du, chung la dau ra nhanh anh le. "
                      "'khong khop' la CAN TREN cua bao dong gia, chua soi tay."),
        "bang_mau": mau_tot, "xoay": deg_tot,
        "o_quet": o_thu, "o_bo_vi_trong": o_bo,
        "phat_hien_tho": len(phat), "sau_gop_trung": len(cum),
        "recall_theo_dung_sai_m": duong_cong(d_moc, len(loi)),
        "ty_le_phat_hien_khop_theo_dung_sai_m": duong_cong(d_phat, len(cum)),
        "lech_trung_vi_phat_hien_m": round(float(np.median(d_phat)), 2),
        "recall_doi_mot_mot": {
            "_y": "moi phat hien chi nhan duoc mot loi moc - chan viec mot phat hien "
                  "'bat trung' nhieu loi cung luc o dung sai lon",
            **{("%.1f" % t): round(doi_mot_mot(DM, t) / max(len(loi), 1), 4)
               for t in DUNG_SAI},
        },
        "moc_ngau_nhien": {
            "_y": "rai lai dung so phat hien do vao vung phu, cham y het. Day la san "
                  "nha - con so that phai vuot han moc nay moi co y nghia.",
            "recall_lang_gieng": duong_cong(DMr.min(0), len(loi)),
            "recall_doi_mot_mot": {("%.1f" % t): round(doi_mot_mot(DMr, t) / max(len(loi), 1), 4)
                                   for t in DUNG_SAI},
        },
        "bu_dich_deu_tot_nhat": {
            "_y": "sai so dinh vi ortho thay co phai mot phep tinh tien khong",
            "dx_m": round(float(b[ix]), 2), "dy_m": round(float(b[iy]), 2),
            "recall_sau_bu": duong_cong(d_moc_bu, len(loi)),
            "recall_doi_mot_mot_sau_bu": {
                ("%.1f" % t): round(doi_mot_mot(np.hypot(DX - b[ix], DY - b[iy]), t)
                                    / max(len(loi), 1), 4) for t in DUNG_SAI},
        },
        "danh_sach": os.path.relpath(ds, BASE).replace("\\", "/"),
        "giay": round(time.time() - t0, 1),
    }
    rc = kq["D_quet_truot"]["recall_theo_dung_sai_m"]
    print("  %d o -> %d tho -> %d sau gop" % (o_thu, len(phat), len(cum)))
    print("  bat lai loi moc: 1m %.1f%% | 2m %.1f%% | 3m %.1f%% | 5m %.1f%%"
          % (100 * rc["1.0"], 100 * rc["2.0"], 100 * rc["3.0"], 100 * rc["5.0"]))
    r11 = kq["D_quet_truot"]["recall_doi_mot_mot"]
    rnn = kq["D_quet_truot"]["moc_ngau_nhien"]["recall_doi_mot_mot"]
    print("  doi 1-1        : 1m %.1f%% | 2m %.1f%% | 3m %.1f%% | 5m %.1f%%"
          % (100 * r11["1.0"], 100 * r11["2.0"], 100 * r11["3.0"], 100 * r11["5.0"]))
    print("  moc ngau nhien : 1m %.1f%% | 2m %.1f%% | 3m %.1f%% | 5m %.1f%%   <- san nha"
          % (100 * rnn["1.0"], 100 * rnn["2.0"], 100 * rnn["3.0"], 100 * rnn["5.0"]))
    rb = kq["D_quet_truot"]["bu_dich_deu_tot_nhat"]["recall_sau_bu"]
    print("  sau bu dich deu (%.2f, %.2f) m: 1m %.1f%% | 2m %.1f%%"
          % (b[ix], b[iy], 100 * rb["1.0"], 100 * rb["2.0"]))

json.dump(kq, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("=" * 78)
try:
    print("-> %s" % os.path.relpath(args.out, BASE))
except ValueError:                    # --out tro sang o khac
    print("-> %s" % args.out)
