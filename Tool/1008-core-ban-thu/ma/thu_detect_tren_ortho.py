#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ablation FRAME vs ORTHO — cùng MỘT model `fault_obb_4class.pt`, ba đầu vào.

CÂU HỎI: pipeline chọn hướng detect-trên-ảnh-lẻ-rồi-chiếu. Nếu quét thẳng trên
ortho nhiệt thì mất bao nhiêu? Nhánh 8 lớp cũ bắt 45,7 % nhưng đó là MODEL KHÁC
nên không tách được "ortho làm nhoè hotspot" khỏi "model đó vốn kém". Đây là so
sánh sạch: một model, đổi mỗi đầu vào.

BA ĐIỀU KIỆN — B là đối chứng mà bản cũ của script này thiếu:

  A  frame + ironbow gốc      `quet_loi_anh_le.py:194` cv2.imread(...) -> BGR
                              = ĐÚNG pipeline đang chạy. Mốc 100 %.
  B  frame + xám -> INFERNO   cùng ảnh, chỉ đổi bảng màu. Đo riêng phần mất do
                              ĐỔI MÀU, không dính gì tới ghép ortho.
  C  ortho + xám -> INFERNO   cửa sổ 640x512 cắt quanh lỗi đã biết.
                              C so với B = phần mất do GHÉP ORTHO. Đó là số cần.

Phải có B vì `ghep_ortho_nhiet.py:288` dựng ortho từ ảnh ĐÃ CHUYỂN XÁM
(IMREAD_GRAYSCALE) — ortho không giữ được palette ironbow mà model train trên đó.
So thẳng A với C là gộp hai nguyên nhân vào một con số.

  D  precision trên ortho     quét trượt TOÀN ortho, gộp trùng 0,60 m rồi đối
                              chiếu với 603 lỗi của nhánh frame. C chỉ đo được
                              recall vì nó cắt cửa sổ quanh lỗi ĐÃ BIẾT.

HAI CHỖ THIÊN LỆCH CÓ LỢI CHO ORTHO, cố ý giữ để C là CẬN TRÊN:
  - cửa sổ luôn đặt lỗi vào chính giữa, không bao giờ bị cắt ở mép cửa sổ;
  - bỏ cửa sổ nào thủng > 10 % (`--phu-toi-thieu`), tức chỉ chấm chỗ ortho lành.

    py -3.13 ma/thu_detect_tren_ortho.py                 # đủ 603 lỗi, ~10-20 phút
    py -3.13 ma/thu_detect_tren_ortho.py --so-loi 40     # thử nhanh
    py -3.13 ma/thu_detect_tren_ortho.py --bo-qua-D      # bỏ lượt quét trượt
"""
import argparse
import csv
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

ap = argparse.ArgumentParser()
ap.add_argument("--conf", type=float, default=0.25, help="ngưỡng chốt của pipeline")
ap.add_argument("--so-loi", type=int, default=0, dest="so_loi", help="0 = cả 603")
ap.add_argument("--so-anh-B", type=int, default=60, dest="so_anh_B",
                help="số ảnh lẻ lấy mẫu cho điều kiện B")
ap.add_argument("--hit-m", type=float, default=1.0, dest="hit_m",
                help="phát hiện cách tâm lỗi dưới mức này (m) coi là bắt trúng")
ap.add_argument("--gop-m", type=float, default=0.60, dest="gop_m",
                help="gộp trùng ở lượt D — giống quet_loi_anh_le.py")
ap.add_argument("--phu-toi-thieu", type=float, default=0.90, dest="phu_min",
                help="cửa sổ ít dữ liệu hơn mức này thì bỏ (điều kiện C)")
ap.add_argument("--xoay", type=int, default=0, choices=[0, 90, 180, 270],
                help="xoay ô ortho trước khi đưa vào model (điều kiện C). Drone bay "
                     "yaw ~-89 độ nên ortho bắc-lên là cảnh XOAY 90 độ so với ảnh "
                     "gốc mà model train trên đó. Xoay quanh tâm nên khoảng cách "
                     "tới tâm ô giữ nguyên, không phải map ngược toạ độ")
ap.add_argument("--bo-qua-C", action="store_true", dest="bo_C")
ap.add_argument("--bo-qua-B", action="store_true", dest="bo_B")
ap.add_argument("--bo-qua-D", action="store_true", dest="bo_D")
ap.add_argument("--model", default=MODEL)
ap.add_argument("--ortho", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
ap.add_argument("--loi", default=os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"))
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/ablation_frame_vs_ortho.json"))
args = ap.parse_args()

TW, TH = 640, 512          # đúng kích thước ảnh nhiệt gốc ZH20T


def met(lat):
    """Số mét trên 1 độ lon và 1 độ lat, xấp xỉ phẳng quanh vĩ độ này."""
    return 111320.0 * np.cos(np.radians(lat)), 110574.0


def khoang_cach_m(lon1, lat1, lon2, lat2, ml, mt):
    return float(np.hypot((lon1 - lon2) * ml, (lat1 - lat2) * mt))


def to_mau(xam):
    """Xám -> INFERNO. Đúng cách ortho được tô ở ghep_ortho_nhiet.py:409."""
    g = cv2.normalize(xam, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)


def xoay_anh(col):
    if not args.xoay:
        return col
    return cv2.rotate(col, {90: cv2.ROTATE_90_CLOCKWISE,
                            180: cv2.ROTATE_180,
                            270: cv2.ROTATE_90_COUNTERCLOCKWISE}[args.xoay])


def go_xoay(x, y, W, H):
    """Toạ độ trong ảnh ĐÃ XOAY -> toạ độ trong ô gốc W x H. Cần cho lượt D vì
    ở đó phải đổi ra lon/lat; lượt C không cần vì chỉ đo khoảng cách tới tâm."""
    if args.xoay == 90:                 # (x,y)_goc -> (H-1-y, x)
        return y, H - 1 - x
    if args.xoay == 270:                # (x,y)_goc -> (y, W-1-x)
        return W - 1 - y, x
    if args.xoay == 180:
        return W - 1 - x, H - 1 - y
    return x, y


def tam_obb(r):
    """Tâm + conf + lớp của mọi phát hiện OBB, đơn vị pixel của ảnh đưa vào."""
    if getattr(r, "obb", None) is None or len(r.obb) == 0:
        return np.zeros((0, 2)), np.zeros(0), []
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    tam = np.stack([q[:, :, 0].mean(1), q[:, :, 1].mean(1)], 1)
    return tam, r.obb.conf.cpu().numpy(), [names[int(c)] for c in r.obb.cls.cpu().numpy()]


# ---------------------------------------------------------------- dữ liệu vào
loi = json.load(open(args.loi, encoding="utf-8"))
if args.so_loi:
    loi = loi[:args.so_loi]
src = rasterio.open(args.ortho)
ML, MT = met(float(np.mean([x["lat"] for x in loi])))
GSD_CM = abs(src.transform[0]) * ML * 100.0

from ultralytics import YOLO           # noqa: E402  (nặng, nạp sau khi parse args)
model = YOLO(args.model)
names = model.names

print("=" * 72)
print("ABLATION FRAME vs ORTHO — %s (%d lớp), conf %.2f"
      % (os.path.basename(args.model), len(names), args.conf))
print("ortho %dx%d, %.2f cm/px · %d lỗi mốc · bắt trúng = trong %.1f m"
      % (src.width, src.height, GSD_CM, len(loi), args.hit_m))
print("=" * 72)

kq = {
    "_cau_hoi": "cùng một model fault_obb_4class.pt, đổi mỗi đầu vào: mất bao nhiêu?",
    "_moc_A": ("603 lỗi trong loi_4lop_cuoi.json ĐỀU do chính model này bắt được trên "
               "ảnh lẻ ironbow gốc, nên điều kiện A = 100% theo định nghĩa. A không "
               "phải phép đo độc lập, nó là mốc."),
    "conf": args.conf, "hit_m": args.hit_m, "gsd_cm_per_px": round(GSD_CM, 3),
    "so_loi_moc": len(loi),
}

# ------------------------------------------------- C: ortho, cửa sổ quanh lỗi
t0 = time.time()
c_thu = c_hit = 0
c_conf, c_lech, c_bo_thung, c_bo_mep, c_dung_lop = [], [], 0, 0, 0
for i, d in enumerate(loi if not args.bo_C else [], 1):
    r_, c_ = src.index(d["lon"], d["lat"])
    c0, r0 = int(c_ - TW / 2), int(r_ - TH / 2)
    if c0 < 0 or r0 < 0 or c0 + TW > src.width or r0 + TH > src.height:
        c_bo_mep += 1
        continue
    im = src.read(1, window=Window(c0, r0, TW, TH))
    if (im != 0).mean() < args.phu_min:
        c_bo_thung += 1
        continue
    c_thu += 1
    col = xoay_anh(to_mau(im))
    ch, cw = col.shape[:2]
    r = model.predict(col, imgsz=640, conf=args.conf, verbose=False)[0]
    tam, cf, cl = tam_obb(r)
    if not len(tam):
        continue
    # tâm cửa sổ CHÍNH LÀ lỗi mốc, nên đo thẳng bằng pixel rồi đổi ra mét.
    # Xoay quanh tâm giữ nguyên khoảng cách tới tâm nên dùng chung một công thức.
    dm = np.hypot(tam[:, 0] - cw / 2, tam[:, 1] - ch / 2) * GSD_CM / 100.0
    j = int(np.argmin(dm))
    if dm[j] < args.hit_m:
        c_hit += 1
        c_conf.append(float(cf[j]))
        c_lech.append(float(dm[j]))
        c_dung_lop += int(cl[j] == d["cls"])
    if i % 100 == 0:
        print("  [C] %d/%d ... bắt lại %d/%d" % (i, len(loi), c_hit, c_thu))

kq["C_ortho_inferno"] = None if args.bo_C else {
    "_mo_ta": "cửa sổ 640x512 cắt quanh lỗi đã biết trên ortho nhiệt, tô INFERNO",
    "o_thu": c_thu, "bat_lai": c_hit,
    "recall": round(c_hit / max(c_thu, 1), 4),
    "bo_vi_thung": c_bo_thung, "bo_vi_mep": c_bo_mep,
    "conf_trung_vi": round(float(np.median(c_conf)), 3) if c_conf else None,
    "lech_tam_trung_vi_cm": round(float(np.median(c_lech)) * 100, 1) if c_lech else None,
    "dung_lop_tren_bat_duoc": round(c_dung_lop / max(c_hit, 1), 4),
    "giay": round(time.time() - t0, 1),
}
if not args.bo_C:
    print("[C] ortho+INFERNO : %d/%d = %.1f%%  (bỏ %d ô thủng, %d ô sát mép)"
          % (c_hit, c_thu, 100 * c_hit / max(c_thu, 1), c_bo_thung, c_bo_mep))

# ------------------------------------- B: cùng ảnh lẻ, chỉ đổi ironbow -> INFERNO
if not args.bo_B:
    t0 = time.time()
    rows = {}
    with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows[row["seq"]] = row
    # lấy các ảnh THẬT SỰ sinh ra lỗi, rải đều theo chuyến bay
    seqs = sorted({d["seq"] for d in loi if d.get("seq") in rows})
    if args.so_anh_B and len(seqs) > args.so_anh_B:
        seqs = [seqs[k] for k in np.linspace(0, len(seqs) - 1, args.so_anh_B).astype(int)]
    NGUONG_PX = args.hit_m * 100.0 / GSD_CM      # ~1 m quy ra pixel ảnh nhiệt

    nA = nB = khop = 0
    b_conf = []
    for i, seq in enumerate(seqs, 1):
        im = cv2.imread(rows[seq]["path_thermal"])
        if im is None:
            continue
        rA = model.predict(im, imgsz=640, conf=args.conf, verbose=False)[0]
        tA, _, _ = tam_obb(rA)
        xam = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        rB = model.predict(to_mau(xam), imgsz=640, conf=args.conf, verbose=False)[0]
        tB, cfB, _ = tam_obb(rB)
        nA += len(tA)
        nB += len(tB)
        for k in range(len(tA)):
            if len(tB):
                dpx = np.hypot(tB[:, 0] - tA[k, 0], tB[:, 1] - tA[k, 1])
                j = int(np.argmin(dpx))
                if dpx[j] < NGUONG_PX:
                    khop += 1
                    b_conf.append(float(cfB[j]))
        if i % 20 == 0:
            print("  [B] %d/%d ... giữ %d/%d" % (i, len(seqs), khop, nA))

    kq["B_frame_inferno"] = {
        "_mo_ta": ("cùng ảnh nhiệt lẻ, chỉ thay ironbow gốc bằng xám->INFERNO. "
                   "Đo riêng phần mất do ĐỔI BẢNG MÀU, chưa dính ghép ortho."),
        "so_anh": len(seqs),
        "phat_hien_A_ironbow": nA, "phat_hien_B_inferno": nB,
        "giu_lai_duoc": khop,
        "recall": round(khop / max(nA, 1), 4),
        "nguong_khop_px": round(NGUONG_PX, 1),
        "conf_trung_vi": round(float(np.median(b_conf)), 3) if b_conf else None,
        "giay": round(time.time() - t0, 1),
    }
    print("[B] frame+INFERNO : %d/%d = %.1f%% giữ lại được (%d ảnh)"
          % (khop, nA, 100 * khop / max(nA, 1), len(seqs)))

# ------------------------------------------- D: quét trượt toàn ortho -> precision
if not args.bo_D:
    t0 = time.time()
    SX, SY = int(TW * 0.8), int(TH * 0.8)          # chồng lấn 20 %
    phat = []
    o_thu = o_bo = 0
    cols = list(range(0, src.width - TW + 1, SX))
    rows_ = list(range(0, src.height - TH + 1, SY))
    for a, r0 in enumerate(rows_, 1):
        for c0 in cols:
            im = src.read(1, window=Window(c0, r0, TW, TH))
            if (im != 0).mean() < 0.30:            # ô gần như trống thì bỏ
                o_bo += 1
                continue
            o_thu += 1
            r = model.predict(xoay_anh(to_mau(im)), imgsz=640, conf=args.conf,
                              verbose=False)[0]
            if getattr(r, "obb", None) is None or len(r.obb) == 0:
                continue
            quad = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
            cf = r.obb.conf.cpu().numpy()
            cl = [names[int(c)] for c in r.obb.cls.cpu().numpy()]
            for k in range(len(quad)):
                # gỡ xoay -> px ô -> px ortho -> lon/lat. Ortho là lưới địa lý nên
                # không cần DSM: mỗi pixel đã có sẵn toạ độ.
                g = np.array([go_xoay(x, y, TW, TH) for x, y in quad[k]], float)
                poly = [list(src.xy(r0 + gy, c0 + gx)) for gx, gy in g]
                lon, lat = src.xy(r0 + g[:, 1].mean(), c0 + g[:, 0].mean())
                phat.append({
                    "lon": lon, "lat": lat, "conf": float(cf[k]), "cls": cl[k],
                    "poly": poly,
                    "w_m": float(np.ptp(g[:, 0]) * GSD_CM / 100),
                    "h_m": float(np.ptp(g[:, 1]) * GSD_CM / 100),
                })
        print("  [D] hàng %d/%d ... %d ô, %d phát hiện thô" % (a, len(rows_), o_thu, len(phat)))

    # gộp trùng giữa các cửa sổ chồng lấn — giống khâu gộp của nhánh frame
    phat.sort(key=lambda x: -x["conf"])
    cum = []
    for p in phat:
        if all(khoang_cach_m(p["lon"], p["lat"], q["lon"], q["lat"], ML, MT) >= args.gop_m
               for q in cum):
            cum.append(p)

    # đối chiếu với 603 lỗi của nhánh frame
    khop_moc = set()
    la = 0
    for p in cum:
        gan = [(khoang_cach_m(p["lon"], p["lat"], d["lon"], d["lat"], ML, MT), j)
               for j, d in enumerate(loi)]
        dmin, j = min(gan)
        p["lech_toi_loi_gan_nhat_cm"] = round(dmin * 100, 1)
        p["khop_nhanh_frame"] = bool(dmin < args.hit_m)
        p["cls_nhanh_frame"] = loi[j]["cls"] if dmin < args.hit_m else None
        p["panel_code"] = loi[j].get("panel_code") if dmin < args.hit_m else None
        if dmin < args.hit_m:
            khop_moc.add(j)
        else:
            la += 1

    ds = args.out.replace(".json", "_ds_phat_hien.json")
    json.dump(cum, open(ds, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("    danh sách %d phát hiện -> %s" % (len(cum), os.path.basename(ds)))

    kq["D_quet_truot_toan_ortho"] = {
        "_mo_ta": "quét trượt cả ortho, gộp trùng %.2f m, đối chiếu 603 lỗi nhánh frame" % args.gop_m,
        "_canh_bao": ("603 lỗi KHÔNG phải chân lý đầy đủ — chúng là đầu ra nhánh frame. "
                      "Nên 'lạ' = không khớp nhánh frame, CẬN TRÊN của báo động giả, "
                      "không phải FP đã kiểm. Muốn FP thật phải soi tay từng cái."),
        "o_quet": o_thu, "o_bo_vi_trong": o_bo,
        "phat_hien_tho": len(phat), "sau_gop_trung": len(cum),
        "khop_moc_frame": len(khop_moc),
        "recall_so_voi_603": round(len(khop_moc) / max(len(loi), 1), 4),
        "khong_khop_nhanh_frame": la,
        "ty_le_khop": round(len(khop_moc) / max(len(cum), 1), 4),
        "giay": round(time.time() - t0, 1),
    }
    print("[D] quét trượt    : %d ô -> %d thô -> %d sau gộp; khớp %d/%d lỗi mốc, %d lạ"
          % (o_thu, len(phat), len(cum), len(khop_moc), len(loi), la))

json.dump(kq, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("=" * 72)
try:
    print("-> %s" % os.path.relpath(args.out, BASE))
except ValueError:                    # --out trỏ sang ổ khác
    print("-> %s" % args.out)
