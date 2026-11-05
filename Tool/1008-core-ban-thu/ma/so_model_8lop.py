#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""So model MUON 8 LOP voi model 4 LOP cua du an, tren cung tap test.

Vi sao khong dung model.val() duoc cho model 8 lop:
  - task 'detect' (hop thang truc) chu khong phai 'obb'
  - bang lop khac han: 8 ten cua bo du lieu ngoai, chi 5 ten ve duoc lop that
    qua aliases trong config/classes.json
  - an ANH XAM chu khong phai Ironbow
Nen phai tu ghep: quy tat ca ve HOP THANG TRUC roi ghep tham lam theo IoU.
Model 4 lop cung do bang DUNG code nay (hop OBB -> hop thang truc bao ngoai)
de hai con so so sanh duoc voi nhau.

Ba cau hoi:
  1. Phat hien duoc bao nhieu / 280 doi tuong that (khong xet ten lop)?
  2. Trong so bat duoc, gan dung ten lop bao nhieu?
  3. Bao nhieu box thua (bao dong gia)?
"""
import glob
import json
import os

import cv2
import numpy as np
from ultralytics import YOLO

BO = r"du_lieu\colab\solar_cls4_nhom"
MODELS = r"mo_hinh"
RA = r"ket_qua\ket_qua_val"

LOP = ["SingleHotSpot", "MultiHotSpot", "Bypass", "ModuleOpenCircuit"]

# aliases lay tu config/classes.json cua du an annotator
VE_LOP_THAT = {
    "SingleHotSpot": "SingleHotSpot", "HotSpot": "SingleHotSpot",
    "MultiHotSpot": "MultiHotSpot",
    "SingleDiode": "Bypass", "MultiDiode": "Bypass", "DiodeFault": "Bypass",
    "Bypass": "Bypass",
    "SingleByPassed": "ModuleOpenCircuit", "ModuleOpenCircuit": "ModuleOpenCircuit",
    # ba lop du an CO Y bo -> khong ve lop nao
    "MultiByPassed": None, "StringOpenCircuit": None, "StringReversedPolarity": None,
}

CONF = 0.25
IOU_THR = 0.5


def doc_gt(anh):
    """Nhan OBB (class + 4 dinh chuan hoa) -> hop thang truc theo pixel."""
    nhan = anh.replace(os.sep + "images" + os.sep, os.sep + "labels" + os.sep)
    nhan = os.path.splitext(nhan)[0] + ".txt"
    h, w = cv2.imread(anh).shape[:2]
    ra = []
    if not os.path.exists(nhan):
        return ra, (w, h)
    for d in open(nhan, encoding="utf-8"):
        p = d.split()
        if len(p) < 9:
            continue
        c = int(p[0])
        xs = np.array([float(p[i]) for i in (1, 3, 5, 7)]) * w
        ys = np.array([float(p[i]) for i in (2, 4, 6, 8)]) * h
        ra.append((c, xs.min(), ys.min(), xs.max(), ys.max()))
    return ra, (w, h)


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    giao = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if giao <= 0:
        return 0.0
    sa = (a[2] - a[0]) * (a[3] - a[1])
    sb = (b[2] - b[0]) * (b[3] - b[1])
    return giao / (sa + sb - giao)


def du_doan(model, anh, xam):
    """Tra ve [(ten_lop_that_hoac_None, conf, x1,y1,x2,y2)] da quy ve hop thang truc."""
    img = cv2.imread(anh)
    if xam:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    r = model.predict(img, conf=CONF, imgsz=640, device="cpu", verbose=False)[0]
    ra = []
    if getattr(r, "obb", None) is not None and r.obb is not None and len(r.obb):
        for poly, c, cf in zip(r.obb.xyxyxyxy.cpu().numpy(),
                               r.obb.cls.cpu().numpy(), r.obb.conf.cpu().numpy()):
            ten = model.names[int(c)]
            ra.append((VE_LOP_THAT.get(ten, ten), float(cf),
                       poly[:, 0].min(), poly[:, 1].min(),
                       poly[:, 0].max(), poly[:, 1].max()))
    elif r.boxes is not None and len(r.boxes):
        for b, c, cf in zip(r.boxes.xyxy.cpu().numpy(),
                            r.boxes.cls.cpu().numpy(), r.boxes.conf.cpu().numpy()):
            ten = model.names[int(c)]
            ra.append((VE_LOP_THAT.get(ten, ten), float(cf), b[0], b[1], b[2], b[3]))
    return ra


def chay(duong_model, xam, nhan_hien):
    model = YOLO(duong_model)
    anhs = sorted(glob.glob(os.path.join(BO, "test", "images", "*")))
    tong_gt = 0
    bat_duoc = 0            # GT co box nao do trum len (khong xet lop)
    dung_lop = 0            # ... va dung ca ten lop
    khong_ve_lop = 0        # bat duoc nhung model doan lop ngoai bang lop du an
    fp = 0
    cm = {t: {u: 0 for u in LOP + ["ngoai bang lop"]} for t in LOP}
    sot_theo_lop = {t: 0 for t in LOP}
    gt_theo_lop = {t: 0 for t in LOP}

    for anh in anhs:
        gts, _ = doc_gt(anh)
        preds = sorted(du_doan(model, anh, xam), key=lambda p: -p[1])
        tong_gt += len(gts)
        for g in gts:
            gt_theo_lop[LOP[g[0]]] += 1
        da_dung = [False] * len(preds)
        for gi, g in enumerate(gts):
            ten_that = LOP[g[0]]
            tot, chon = IOU_THR, -1
            for pi, p in enumerate(preds):
                if da_dung[pi]:
                    continue
                v = iou(g[1:], p[2:])
                if v >= tot:
                    tot, chon = v, pi
            if chon < 0:
                sot_theo_lop[ten_that] += 1
                continue
            da_dung[chon] = True
            bat_duoc += 1
            ten_doan = preds[chon][0]
            if ten_doan is None:
                khong_ve_lop += 1
                cm[ten_that]["ngoai bang lop"] += 1
            else:
                cm[ten_that][ten_doan] += 1
                if ten_doan == ten_that:
                    dung_lop += 1
        fp += sum(1 for u in da_dung if not u)

    print()
    print("=" * 78)
    print(nhan_hien)
    print("=" * 78)
    print("So doi tuong that              : %d" % tong_gt)
    print("PHAT HIEN DUOC (bat ky lop)    : %d/%d = %.1f%%"
          % (bat_duoc, tong_gt, 100.0 * bat_duoc / tong_gt))
    print("GAN DUNG CA TEN LOP            : %d/%d = %.1f%%"
          % (dung_lop, tong_gt, 100.0 * dung_lop / tong_gt))
    print("   (bat duoc nhung lop ngoai bang du an: %d)" % khong_ve_lop)
    print("BO SOT HAN                     : %d" % (tong_gt - bat_duoc))
    print("BOX THUA (bao dong gia)        : %d" % fp)
    print()
    print("%-20s%8s%8s%s" % ("lop that", "so GT", "sot", "".join("%18s" % c[:17] for c in LOP + ["ngoai bang lop"])))
    for t in LOP:
        if gt_theo_lop[t] == 0:
            continue
        print("%-20s%8d%8d%s" % (t, gt_theo_lop[t], sot_theo_lop[t],
              "".join("%18d" % cm[t][u] for u in LOP + ["ngoai bang lop"])))

    return {"so_GT": tong_gt, "phat_hien_duoc": bat_duoc, "gan_dung_lop": dung_lop,
            "lop_ngoai_bang": khong_ve_lop, "bo_sot": tong_gt - bat_duoc,
            "box_thua": fp, "ma_tran": cm, "sot_theo_lop": sot_theo_lop,
            "gt_theo_lop": gt_theo_lop}


out = {"ghi_chu": "IoU >= %.2f, conf >= %.2f, moi box quy ve hop thang truc"
                  % (IOU_THR, CONF)}
out["4lop_ironbow"] = chay(os.path.join(MODELS, "fault_obb_4class.pt"), False,
                           "MODEL 4 LOP CUA DU AN (OBB, anh Ironbow)")
out["8lop_xam"] = chay(os.path.join(MODELS, "muon_det_8class.pt"), True,
                       "MODEL MUON 8 LOP (detect, ANH XAM)")
out["8lop_ironbow"] = chay(os.path.join(MODELS, "muon_det_8class.pt"), False,
                           "MODEL MUON 8 LOP (detect, anh IRONBOW - de kiem chung y 'phai dua anh xam')")

with open(os.path.join(RA, "so_model_8lop.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print()
print("Da luu ket_qua_val/so_model_8lop.json")
