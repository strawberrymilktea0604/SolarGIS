#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Do lai cac chi so cua model phat hien loi mot cach kiem chung duoc.

Khac voi cac script cu o bon diem:

  1. IoU tinh tren DA GIAC XOAY THAT (shapely), khong quy ve hop thang truc.
     do_recall_theo_nguong.py / so_model_8lop.py deu quy ve hop thang truc ->
     IoU bi thoi phong, recall bao cao cao hon thuc te.

  2. Tu tinh AP (101 diem, giong COCO/ultralytics) -> BOOTSTRAP duoc khoang tin
     cay. Tap test chi 91 anh / 280 doi tuong nen mAP@50 co sai so lay mau that su.

  3. PHAN TANG theo RO RI: anh test co frame ke can (+-2) nam trong train/val la
     gan-trung-lap (drone bay chong phu 70-80%%). Do rieng hai nhom de xem con so
     0,965 duoc keo len bao nhieu.

  4. Bao ca P/R tai nguong VAN HANH that (conf 0,25), khong chi tai diem F1 max.

    py -3.13 ma/danh_gia_lai.py              # dung cache neu co
    py -3.13 ma/danh_gia_lai.py --du-doan-lai
"""
import argparse
import glob
import json
import os
import re
from collections import Counter, defaultdict

import cv2
import numpy as np
from shapely.geometry import Polygon

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BO = r"du_lieu\colab\solar_cls4_nhom"
MODEL = r"mo_hinh\fault_obb_4class.pt"
LOP = ["SingleHotSpot", "MultiHotSpot", "Bypass", "ModuleOpenCircuit"]
CACHE = os.path.join(BASE, "ket_qua/ket_qua_val", "_du_doan_test.json")
OUT = os.path.join(BASE, "ket_qua/ket_qua_val", "danh_gia_lai.json")

ap = argparse.ArgumentParser()
ap.add_argument("--du-doan-lai", action="store_true", dest="lai")
ap.add_argument("--conf-quet", type=float, default=0.02, dest="conf_quet")
ap.add_argument("--boot", type=int, default=2000, help="so lan bootstrap")
ap.add_argument("--bo", default=BO, help="thu muc bo du lieu")
ap.add_argument("--split", default="test", help="train / val / test")
ap.add_argument("--nhan", default="", help="hau to cho ten file ket qua")
args = ap.parse_args()

BO = args.bo
_h = args.nhan or (os.path.basename(BO.rstrip("\\/")) + "_" + args.split)
CACHE = os.path.join(BASE, "ket_qua/ket_qua_val", "_du_doan_%s.json" % _h)
OUT = os.path.join(BASE, "ket_qua/ket_qua_val", "danh_gia_lai_%s.json" % _h)
print("BO    : %s" % BO)
print("SPLIT : %s" % args.split)

rng = np.random.default_rng(20260812)


# ------------------------------------------------------------------ doc du lieu
def doc_gt(anh):
    lab = anh.replace(os.sep + "images" + os.sep, os.sep + "labels" + os.sep)
    lab = os.path.splitext(lab)[0] + ".txt"
    h, w = cv2.imread(anh).shape[:2]
    ra = []
    if not os.path.exists(lab):
        return ra
    for d in open(lab, encoding="utf-8"):
        v = d.split()
        if len(v) < 9:
            continue
        p = np.array(list(map(float, v[1:9]))).reshape(4, 2) * [w, h]
        ra.append({"cls": int(v[0]), "poly": p.tolist()})
    return ra


anhs = sorted(glob.glob(os.path.join(BO, args.split, "images", "*.*")))
ten = [os.path.basename(a) for a in anhs]
print("so anh : %d" % len(anhs))

if args.lai or not os.path.exists(CACHE):
    from ultralytics import YOLO
    model = YOLO(MODEL)
    du = []
    for i, a in enumerate(anhs):
        r = model.predict(a, conf=args.conf_quet, imgsz=640, verbose=False, max_det=300)[0]
        d = []
        if r.obb is not None and len(r.obb):
            q = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
            for p, c, cf in zip(q, r.obb.cls.cpu().numpy(), r.obb.conf.cpu().numpy()):
                d.append({"cls": int(c), "conf": float(cf), "poly": p.tolist()})
        du.append(d)
        if (i + 1) % 20 == 0:
            print("  du doan %d/%d" % (i + 1, len(anhs)))
    json.dump({"anh": ten, "gt": [doc_gt(a) for a in anhs], "du": du},
              open(CACHE, "w", encoding="utf-8"))
    print("-> cache %s" % CACHE)

C = json.load(open(CACHE, encoding="utf-8"))
GT, DU = C["gt"], C["du"]
assert C["anh"] == ten, "cache lech danh sach anh, chay lai voi --du-doan-lai"


# ------------------------------------------------------------------- hinh hoc
def hop(p):
    p = np.asarray(p)
    return [p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()]


def iou_hop(a, b):
    a, b = hop(a), hop(b)
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    it = max(0, x2 - x1) * max(0, y2 - y1)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - it
    return it / u if u > 0 else 0.0


def iou_obb(a, b):
    pa, pb = Polygon(a).buffer(0), Polygon(b).buffer(0)
    if not pa.is_valid or not pb.is_valid:
        return 0.0
    u = pa.union(pb).area
    return pa.intersection(pb).area / u if u > 0 else 0.0


# ma tran IoU cho tung anh, tinh mot lan roi dung lai
def bang_iou(fn):
    M = []
    for gts, dus in zip(GT, DU):
        m = np.zeros((len(dus), len(gts)))
        for i, d in enumerate(dus):
            for j, g in enumerate(gts):
                m[i, j] = fn(d["poly"], g["poly"])
        M.append(m)
    return M


print("Tinh ma tran IoU (da giac xoay va hop thang truc)...")
M_OBB = bang_iou(iou_obb)
M_HOP = bang_iou(iou_hop)


# --------------------------------------------------------------------- ghep cap
def ghep(M, thr, conf_min, theo_lop=True, idx=None):
    """Ghep tham lam theo conf giam dan. Tra ve danh sach (conf, tp, cls_du, cls_gt)
    va so GT trong pham vi xet."""
    idx = range(len(GT)) if idx is None else idx
    ban_ghi = []
    n_gt = 0
    for k in idx:
        gts, dus, m = GT[k], DU[k], M[k]
        n_gt += len(gts)
        thu_tu = sorted((i for i, d in enumerate(dus) if d["conf"] >= conf_min),
                        key=lambda i: -dus[i]["conf"])
        da = [False] * len(gts)
        for i in thu_tu:
            tot, ti = -1, thr
            for j, g in enumerate(gts):
                if da[j]:
                    continue
                if theo_lop and dus[i]["cls"] != g["cls"]:
                    continue
                if m[i, j] >= ti:
                    ti, tot = m[i, j], j
            if tot >= 0:
                da[tot] = True
                ban_ghi.append((dus[i]["conf"], 1, dus[i]["cls"], gts[tot]["cls"], m[i, tot]))
            else:
                ban_ghi.append((dus[i]["conf"], 0, dus[i]["cls"], None, 0.0))
    return ban_ghi, n_gt


def ap_mot_lop(ban_ghi, n_gt):
    """AP noi suy 101 diem (giong COCO)."""
    if n_gt == 0:
        return float("nan")
    b = sorted(ban_ghi, key=lambda x: -x[0])
    tp = np.cumsum([x[1] for x in b])
    fp = np.cumsum([1 - x[1] for x in b])
    if len(tp) == 0:
        return 0.0
    rc = tp / n_gt
    pr = tp / np.maximum(tp + fp, 1e-9)
    # bao hinh: precision khong tang khi recall tang
    pr = np.maximum.accumulate(pr[::-1])[::-1]
    x = np.linspace(0, 1, 101)
    return float(np.trapezoid(np.interp(x, rc, pr, left=pr[0] if len(pr) else 0, right=0), x))


def map_tai(thr, idx=None):
    """mAP tai mot nguong IoU, trung binh tren cac lop CO trong GT."""
    idx = list(range(len(GT))) if idx is None else list(idx)
    co = Counter(g["cls"] for k in idx for g in GT[k])
    aps = {}
    for c in sorted(co):
        bg, _ = ghep([M_OBB[k] for k in range(len(GT))], thr, 0.0, True, idx)
        bg_c = [x for x in bg if x[2] == c]
        aps[LOP[c]] = ap_mot_lop(bg_c, co[c])
    return float(np.mean(list(aps.values()))), aps


# ------------------------------------------------------ 1. mAP: hop vs da giac
print("\n" + "=" * 78)
print("1. mAP@50 — hop thang truc (cach cu) vs da giac xoay (dung)")
print("=" * 78)

ket = {}


def map_voi(M, thr, idx=None):
    idx = list(range(len(GT))) if idx is None else list(idx)
    co = Counter(g["cls"] for k in idx for g in GT[k])
    bg, _ = ghep(M, thr, 0.0, True, idx)
    aps = {}
    for c in sorted(co):
        aps[LOP[c]] = ap_mot_lop([x for x in bg if x[2] == c], co[c])
    return float(np.mean(list(aps.values()))), aps


m_obb50, ap_obb50 = map_voi(M_OBB, 0.5)
m_hop50, ap_hop50 = map_voi(M_HOP, 0.5)
m_obb75, ap_obb75 = map_voi(M_OBB, 0.75)
mm = [map_voi(M_OBB, t)[0] for t in np.arange(0.5, 0.96, 0.05)]

print("  mAP@50  (da giac xoay, dung)     : %.4f" % m_obb50)
print("  mAP@50  (hop thang truc, cach cu): %.4f   <- chenh %+.4f" % (m_hop50, m_hop50 - m_obb50))
print("  mAP@75  (da giac xoay)           : %.4f" % m_obb75)
print("  mAP@50-95 (da giac xoay)         : %.4f" % float(np.mean(mm)))
print("\n  Theo lop (mAP@50, da giac xoay):")
for k, v in ap_obb50.items():
    print("    %-18s %.4f" % (k, v))
ket["mAP"] = {"mAP50_obb": m_obb50, "mAP50_hop": m_hop50, "mAP75_obb": m_obb75,
              "mAP50_95_obb": float(np.mean(mm)), "theo_lop_50": ap_obb50}


# --------------------------------------------- 2. bootstrap khoang tin cay
print("\n" + "=" * 78)
print("2. KHOANG TIN CAY — bootstrap lay lai mau 91 anh, %d lan" % args.boot)
print("=" * 78)

n = len(GT)
boots = []
for _ in range(args.boot):
    idx = rng.integers(0, n, n)
    try:
        boots.append(map_voi(M_OBB, 0.5, idx)[0])
    except Exception:
        pass
boots = np.array(boots)
lo, hi = np.percentile(boots, [2.5, 97.5])
print("  mAP@50 = %.4f   KTC 95%%: [%.4f , %.4f]  (rong %.3f)" % (m_obb50, lo, hi, hi - lo))
print("  do lech chuan bootstrap: %.4f" % boots.std())
ket["bootstrap"] = {"mAP50": m_obb50, "ktc95": [float(lo), float(hi)],
                    "sd": float(boots.std()), "n_lan": int(len(boots))}


# ------------------------------------------------------ 3. phan tang ro ri
print("\n" + "=" * 78)
print("3. RO RI GAN-TRUNG-LAP — anh test co frame ke can trong train/val")
print("=" * 78)

RX = re.compile(r"^(.*?)DJI_(?:\d{14}_)?(\d+)_T", re.I)


def phan(nm):
    m = RX.match(nm)
    return (m.group(1).rstrip("_"), int(m.group(2))) if m else None


vitri = defaultdict(dict)
for t in ["train", "val", "test"]:
    for f in glob.glob(os.path.join(BO, t, "images", "*.*")):
        p = phan(os.path.basename(f))
        if p:
            vitri[p[0]][p[1]] = t

for R in (1, 2):
    gan, xa = [], []
    for k, nm in enumerate(ten):
        g, s = phan(nm)
        if any(vitri[g].get(s + d) in ("train", "val") for d in range(-R, R + 1) if d):
            gan.append(k)
        else:
            xa.append(k)
    n_gan = sum(len(GT[k]) for k in gan)
    n_xa = sum(len(GT[k]) for k in xa)
    mg = map_voi(M_OBB, 0.5, gan)[0] if gan else float("nan")
    mx = map_voi(M_OBB, 0.5, xa)[0] if xa else float("nan")
    print("\n  Ban kinh +-%d:" % R)
    print("    GAN train/val : %2d anh / %3d doi tuong  ->  mAP@50 = %.4f" % (len(gan), n_gan, mg))
    print("    CACH LY       : %2d anh / %3d doi tuong  ->  mAP@50 = %.4f" % (len(xa), n_xa, mx))
    print("    chenh lech    : %+.4f" % (mg - mx))
    ket.setdefault("ro_ri", {})["R%d" % R] = {
        "gan": {"n_anh": len(gan), "n_gt": n_gan, "mAP50": mg},
        "cach_ly": {"n_anh": len(xa), "n_gt": n_xa, "mAP50": mx}}


# --------------------------------------- 4. P/R tai nguong van hanh + IoU
print("\n" + "=" * 78)
print("4. PRECISION / RECALL theo nguong conf  (IoU>=0,5 tren da giac xoay)")
print("=" * 78)
print("  %-6s %8s %8s %8s %8s %8s %8s" % ("conf", "TP", "FP", "sot", "P", "R", "F1"))
print("  " + "-" * 62)
tong_gt = sum(len(g) for g in GT)
pr = {}
for c in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.64, 0.70]:
    bg, _ = ghep(M_OBB, 0.5, c, True)
    tp = sum(x[1] for x in bg)
    fp = len(bg) - tp
    p = tp / max(tp + fp, 1)
    r = tp / tong_gt
    f1 = 2 * p * r / max(p + r, 1e-9)
    pr["%.2f" % c] = {"TP": tp, "FP": fp, "sot": tong_gt - tp, "P": p, "R": r, "F1": f1}
    dau = "  <- van hanh" if abs(c - 0.25) < 1e-9 else ("  <- F1 max" if abs(c - 0.64) < 1e-9 else "")
    print("  %-6.2f %8d %8d %8d %8.3f %8.3f %8.3f%s" % (c, tp, fp, tong_gt - tp, p, r, f1, dau))
ket["PR_theo_conf"] = pr

# IoU cua cac cap khop tai conf van hanh
bg25, _ = ghep(M_OBB, 0.5, 0.25, True)
ious = sorted(x[4] for x in bg25 if x[1] == 1)
bg25h, _ = ghep(M_HOP, 0.5, 0.25, True)
iouh = sorted(x[4] for x in bg25h if x[1] == 1)


def pctl(v, q):
    return float(np.percentile(v, q)) if v else float("nan")


print("\n  Phan bo IoU cua %d cap KHOP tai conf 0,25:" % len(ious))
print("    da giac xoay : trung vi %.3f | P10 %.3f | P90 %.3f | min %.3f"
      % (pctl(ious, 50), pctl(ious, 10), pctl(ious, 90), ious[0] if ious else float("nan")))
print("    hop thang truc: trung vi %.3f | P10 %.3f | P90 %.3f"
      % (pctl(iouh, 50), pctl(iouh, 10), pctl(iouh, 90)))
print("    so cap IoU>=0,75: %d / %d (%.0f%%)"
      % (sum(1 for v in ious if v >= 0.75), len(ious),
         100.0 * sum(1 for v in ious if v >= 0.75) / max(len(ious), 1)))
ket["IoU_cap_khop"] = {"n": len(ious), "trung_vi_obb": pctl(ious, 50),
                       "P10_obb": pctl(ious, 10), "P90_obb": pctl(ious, 90),
                       "trung_vi_hop": pctl(iouh, 50)}


# --------------------------------------------------- 5. nham lop (bo qua lop)
print("\n" + "=" * 78)
print("5. BAT DUOC vs GAN DUNG LOP  (ghep KHONG phan biet lop, conf 0,25)")
print("=" * 78)
bg_kl, _ = ghep(M_OBB, 0.5, 0.25, False)
bat = sum(x[1] for x in bg_kl)
dung = sum(1 for x in bg_kl if x[1] == 1 and x[2] == x[3])
print("  Bat duoc vi tri : %d / %d = %.1f%%" % (bat, tong_gt, 100.0 * bat / tong_gt))
print("  Gan dung lop    : %d / %d = %.1f%%" % (dung, tong_gt, 100.0 * dung / tong_gt))
print("  Nham lop        : %d ca" % (bat - dung))
nham = Counter((LOP[x[3]], LOP[x[2]]) for x in bg_kl if x[1] == 1 and x[2] != x[3])
for (a, b), v in nham.most_common():
    print("      %-16s -> %-16s : %d" % (a, b, v))
ket["nham_lop"] = {"bat": bat, "dung_lop": dung, "tong_gt": tong_gt,
                   "chi_tiet": {"%s->%s" % k: v for k, v in nham.items()}}

json.dump(ket, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("\n-> %s" % OUT)
