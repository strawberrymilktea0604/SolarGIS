#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ortho nhìn vẫn NÉT, sao model bắt được ít hơn? Đo tách hai đại lượng.

`thu_detect_tren_ortho.py` cho thấy quét trên ortho chỉ giữ 53 % số lỗi. Nhưng
nhìn bằng mắt thì ortho nhiệt sắc nét — viền tấm, hàng, cột đều rõ. Nghịch lý đó
tan khi tách "nét" thành HAI đại lượng khác nhau, suy biến theo hai kiểu:

  ĐỘ NÉT CẤU TRÚC  var(Laplacian) trên cả ô — năng lượng tần số cao. Đây là thứ
                   MẮT gọi là "nét": viền tấm pin, mép hàng. Cấu trúc lớn, tương
                   phản mạnh, nằm ĐÚNG chỗ trong mọi ảnh chồng phủ nên trung bình
                   hoá không xoá được.

  TƯƠNG PHẢN NHIỆT p99(đĩa trong) − trung vị(vành ngoài) — biên độ vệt nóng so
                   với nền quanh nó. Đây là thứ MODEL dùng. Vệt nóng nhỏ, và vị
                   trí của nó lệch vài px giữa các ảnh chồng phủ (sai số đặt chỗ),
                   nên trung bình hoá kéo đỉnh xuống trong khi vành nền không đổi.

Giả thuyết: ortho giữ được ĐỘ NÉT nhưng mất TƯƠNG PHẢN. Nếu đúng thì nhóm lỗi
model bỏ sót trên ortho phải có tương phản thấp hơn hẳn nhóm bắt được.

So sánh công bằng ở hai chỗ:
  - cùng đọc từ ẢNH XÁM. Ortho vốn dựng từ `IMREAD_GRAYSCALE` nên ảnh lẻ cũng
    phải `BGR2GRAY` — cùng một phép biến đổi, không bên nào lợi.
  - cùng BÁN KÍNH VẬT LÝ (mét), quy ra px riêng theo GSD từng bên:
    ảnh lẻ 2,523 cm/px (suy từ H), ortho 2,871 cm/px.

    py -3.13 ma/vi_sao_ortho_kem.py
"""
import argparse
import csv
import json
import os
import sys

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
ap.add_argument("--conf", type=float, default=0.25)
ap.add_argument("--so-anh", type=int, default=60, dest="so_anh")
ap.add_argument("--r-trong", type=float, default=0.45, dest="r_trong", help="m")
ap.add_argument("--r-vanh", type=float, default=0.70, dest="r_vanh", help="m")
ap.add_argument("--r-ngoai", type=float, default=1.60, dest="r_ngoai", help="m")
ap.add_argument("--model", default=MODEL)
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/vi_sao_ortho_kem.json"))
args = ap.parse_args()

GSD_FRAME = 2.523   # cm/px, = 0.9569 * sqrt(det H[:2,:2]) — suy từ thermal_to_rgb.json
GSD_ORTHO = 2.871   # cm/px, = |transform[0]| * m/độ tại vĩ độ nhà máy
TW, TH = 640, 512


def do_hai_so(xam, cx, cy, gsd_cm):
    """(tương phản nhiệt, độ nét cấu trúc) quanh điểm (cx,cy). None nếu sát mép."""
    ri = args.r_trong * 100 / gsd_cm
    rv = args.r_vanh * 100 / gsd_cm
    ro = args.r_ngoai * 100 / gsd_cm
    c0, r0 = int(cx - ro), int(cy - ro)
    c1, r1 = int(cx + ro), int(cy + ro)
    if c0 < 0 or r0 < 0 or c1 > xam.shape[1] or r1 > xam.shape[0]:
        return None
    o = xam[r0:r1, c0:c1].astype(np.float32)
    n = o.shape[0]
    yy, xx = np.mgrid[0:n, 0:o.shape[1]]
    d = np.hypot(xx - (cx - c0), yy - (cy - r0))
    trong = o[(d <= ri) & (o > 0)]
    vanh = o[(d >= rv) & (d <= ro) & (o > 0)]
    if trong.size < 20 or vanh.size < 100:
        return None
    tuong_phan = float(np.percentile(trong, 99) - np.median(vanh))
    # độ nét đo trên phần có dữ liệu; lỗ thủng (=0) làm giả Laplacian nên loại ô thủng
    if (o == 0).mean() > 0.05:
        do_net = None
    else:
        do_net = float(cv2.Laplacian(o, cv2.CV_32F, ksize=3).var())
    return tuong_phan, do_net


def tom(v):
    v = [x for x in v if x is not None]
    if not v:
        return None
    a = np.array(v, dtype=float)
    return {"n": len(a), "trung_vi": round(float(np.median(a)), 2),
            "p25": round(float(np.percentile(a, 25)), 2),
            "p75": round(float(np.percentile(a, 75)), 2)}


loi = json.load(open(os.path.join(BASE, "ket_qua/loi_4lop_cuoi.json"), encoding="utf-8"))
src = rasterio.open(os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))

from ultralytics import YOLO           # noqa: E402
model = YOLO(args.model)

print("=" * 72)
print("VÌ SAO ORTHO NÉT MÀ MODEL VẪN BẮT ÍT HƠN")
print("đĩa trong %.2f m · vành nền %.2f-%.2f m · ảnh lẻ %.3f cm/px · ortho %.3f cm/px"
      % (args.r_trong, args.r_vanh, args.r_ngoai, GSD_FRAME, GSD_ORTHO))
print("=" * 72)

# ------------------------------------------------- ảnh lẻ: đo tại chỗ model khoanh
rows = {}
with open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        rows[row["seq"]] = row
seqs = sorted({d["seq"] for d in loi if d.get("seq") in rows})
if args.so_anh and len(seqs) > args.so_anh:
    seqs = [seqs[k] for k in np.linspace(0, len(seqs) - 1, args.so_anh).astype(int)]

f_tp, f_net = [], []
for i, seq in enumerate(seqs, 1):
    im = cv2.imread(rows[seq]["path_thermal"])
    if im is None:
        continue
    r = model.predict(im, imgsz=640, conf=args.conf, verbose=False)[0]
    if getattr(r, "obb", None) is None or len(r.obb) == 0:
        continue
    q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
    xam = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)     # đúng phép ortho đã dùng
    for p in q:
        got = do_hai_so(xam, p[:, 0].mean(), p[:, 1].mean(), GSD_FRAME)
        if got:
            f_tp.append(got[0])
            f_net.append(got[1])
    if i % 20 == 0:
        print("  [ảnh lẻ] %d/%d ... %d điểm" % (i, len(seqs), len(f_tp)))

# ------------------------------------- ortho: đo tại lỗi đã biết, tách bắt / sót
o_tp_hit, o_tp_miss, o_net = [], [], []
for i, d in enumerate(loi, 1):
    r_, c_ = src.index(d["lon"], d["lat"])
    c0, r0 = int(c_ - TW / 2), int(r_ - TH / 2)
    if c0 < 0 or r0 < 0 or c0 + TW > src.width or r0 + TH > src.height:
        continue
    im = src.read(1, window=Window(c0, r0, TW, TH))
    if (im != 0).mean() < 0.90:
        continue
    got = do_hai_so(im, TW / 2, TH / 2, GSD_ORTHO)
    if not got:
        continue
    r = model.predict(cv2.applyColorMap(
        cv2.normalize(im, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
        cv2.COLORMAP_INFERNO), imgsz=640, conf=args.conf, verbose=False)[0]
    bat = False
    if getattr(r, "obb", None) is not None and len(r.obb):
        q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
        dm = np.hypot(q[:, :, 0].mean(1) - TW / 2, q[:, :, 1].mean(1) - TH / 2) * GSD_ORTHO / 100
        bat = bool(dm.min() < 1.0)
    (o_tp_hit if bat else o_tp_miss).append(got[0])
    o_net.append(got[1])
    if i % 150 == 0:
        print("  [ortho] %d/%d ... bắt %d, sót %d" % (i, len(loi), len(o_tp_hit), len(o_tp_miss)))

kq = {
    "_cau_hoi": "ortho nhìn vẫn nét, sao model bắt được ít hơn?",
    "_don_vi": "mức xám 0-255 trên ảnh xám; độ nét = var(Laplacian) cùng thang",
    "ban_kinh_m": {"trong": args.r_trong, "vanh": [args.r_vanh, args.r_ngoai]},
    "gsd_cm_per_px": {"anh_le": GSD_FRAME, "ortho": GSD_ORTHO},
    "tuong_phan_nhiet": {
        "anh_le": tom(f_tp),
        "ortho_bat_duoc": tom(o_tp_hit),
        "ortho_bo_sot": tom(o_tp_miss),
        "ortho_tat_ca": tom(o_tp_hit + o_tp_miss),
    },
    "do_net_cau_truc": {"anh_le": tom(f_net), "ortho": tom(o_net)},
}
json.dump(kq, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("=" * 72)
for ten, v in [("TƯƠNG PHẢN NHIỆT", kq["tuong_phan_nhiet"]),
               ("ĐỘ NÉT CẤU TRÚC", kq["do_net_cau_truc"])]:
    print(ten)
    for k, s in v.items():
        if s:
            print("   %-16s trung vị %8.2f   (p25 %.2f – p75 %.2f, n=%d)"
                  % (k, s["trung_vi"], s["p25"], s["p75"], s["n"]))
print("=" * 72)
print("-> ket_qua/%s" % os.path.basename(args.out))
