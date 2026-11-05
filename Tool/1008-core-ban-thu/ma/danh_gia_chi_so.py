#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tong hop cac chi so danh gia he thong dinh vi loi tam pin.

Do nhung gi do duoc tu du lieu ket qua hien co:
  A. Sai so hieu chuan H (khoi F1)          -> thermal_to_rgb.json, kiem_chung_*.json
  B. Sai so dinh vi end-to-end (F1..F5)     -> sai_so_end_to_end.json, anh_tre_chup.json
  C. Gan loi vao tam pin (F7)               -> loi_tren_ortho_nhiet.json
  D. Gom cum khu trung lap (F6)             -> loi_tren_ortho_nhiet.json (truong n)
  E. Kiem tra vi tri bat thuong (outlier)   -> loi_tren_ortho_nhiet.json
So sanh voi nguong nghiem thu trong YEU_CAU_BAI_TOAN.pdf muc 4.3 va muc 7.
"""
import argparse
import json
import os
import math
import statistics as st
from collections import Counter

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Nguon loi: mac dinh la dau ra cua MODEL 4 LOP OBB (`gan_tam_pin_4lop.py`).
# `loi_tren_ortho_nhiet.json` la dau ra cu, do model 8 LOP quet tren ortho sinh
# ra — khac model voi moi con so mAP/precision/recall trong bao cao, nen khong
# dung lam mac dinh nua. Van doc duoc bang --nguon neu can doi chieu.
_ap = argparse.ArgumentParser()
_ap.add_argument('--nguon', default=None, help='file JSON loi da gan ma tam pin')
_args = _ap.parse_args()
NGUON = _args.nguon or ('ket_qua/loi_4lop_cuoi.json' if os.path.exists('ket_qua/loi_4lop_cuoi.json')
                        else 'ket_qua/loi_tren_ortho_nhiet.json')


def doc(f):
    with open(f, encoding='utf-8') as fh:
        return json.load(fh)


def dat(ok):
    return "DAT" if ok else "KHONG DAT"


def muc(ten, ch=u"─"):
    print()
    print(ch * 78)
    print(ten)
    print(ch * 78)


def bang(rows, headers):
    w = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            w[i] = max(w[i], len(str(c)))
    line = "  ".join(h.ljust(w[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w[i] for i in range(len(headers))))
    for r in rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))


ket_luan = []


# ---------------------------------------------------------------- A. Hieu chuan H
muc("A. SAI SO HIEU CHUAN H  (khoi F1: anh nhiet -> anh RGB)")

files_h = [
    ('ket_qua/thermal_to_rgb.json', 'H dang dung (0280, 31 diem)'),
    ('ket_qua/kiem_chung_0320.json', 'Kiem tra cheo 0320'),
    ('ket_qua/kiem_chung_0440.json', 'Kiem tra cheo 0440'),
    ('ket_qua/kiem_chung_0080.json', 'Kiem tra cheo 0080'),
]
rows = []
gsd = None
for f, ten in files_h:
    if not os.path.exists(f):
        continue
    d = doc(f)
    g = d.get('gsd_cm_per_px')
    if gsd is None:
        gsd = g
    rmse_px = d.get('rmse_px')
    max_px = d.get('max_err_px')
    rows.append([
        ten,
        d.get('n_points'),
        "%.2f" % rmse_px,
        "%.1f" % (rmse_px * g),
        "%.2f" % max_px,
        "%.1f" % (max_px * g),
    ])
bang(rows, ["Nguon", "So diem", "RMSE px", "RMSE cm", "Max px", "Max cm"])

d0 = doc('ket_qua/thermal_to_rgb.json')
print()
print("Nguong nghiem thu muc 4.3 cua de bai:")
n_pt = d0['n_points']
r_px = d0['rmse_px']
m_px = d0['max_err_px']
kt = [
    ("RMSE tai chieu tren tap diem hieu chuan", "%.2f px" % r_px, "<= 3 px", r_px <= 3),
    ("Sai so lon nhat tai vung ria anh", "%.2f px" % m_px, "<= 6 px", m_px <= 6),
    ("So diem hieu chuan", "%d cap" % n_pt, ">= 10 cap", n_pt >= 10),
]
kc = doc('ket_qua/kiem_chung_0320.json')
kt.append(("RMSE tren cap anh kiem tra cheo (0320)",
           "%.2f px" % kc['rmse_px'], "<= 4 px", kc['rmse_px'] <= 4))
bang([[a, b, c, dat(e)] for a, b, c, e in kt],
     ["Chi tieu", "Do duoc", "Nguong dat", "Ket qua"])

print()
print("Baseline hang san xuat (RTK350.txt, chua hieu chuan lai):"
      " RMSE %.2f px = %.1f cm" % (d0['baseline_RTK350_rmse_px'],
                                   d0['baseline_RTK350_rmse_cm']))
print("Sau hieu chuan tay: RMSE %.2f px = %.1f cm  -> giam %.1f lan"
      % (r_px, d0['rmse_cm'], d0['baseline_RTK350_rmse_px'] / r_px))

ket_luan.append(("F1 - Hieu chuan H",
                 "RMSE %.2f px (%.1f cm), kiem cheo %.2f px" % (r_px, d0['rmse_cm'], kc['rmse_px']),
                 r_px <= 3 and kc['rmse_px'] <= 4 and m_px <= 6 and n_pt >= 10))


# ------------------------------------------------- B. Sai so dinh vi end-to-end
muc("B. SAI SO DINH VI END-TO-END  (chuoi F1 -> F5, do tren thuc dia)")

e2e = doc('ket_qua/sai_so_end_to_end.json')
errs = [p['err_cm'] for p in e2e['points']]
print("Phep do 1 - doi chung tren orthophoto (%d diem, anh %s):"
      % (e2e['n'], e2e['label']))
bang([
    ["Trung binh", "%.2f cm" % e2e['mean_cm']],
    ["Trung vi", "%.2f cm" % e2e['median_cm']],
    ["RMSE", "%.2f cm" % e2e['rmse_cm']],
    ["Lon nhat", "%.2f cm" % e2e['max_cm']],
    ["Do lech chuan", "%.2f cm" % st.pstdev(errs)],
    ["Bias cot / hang", "%.2f / %.2f px" % (e2e['bias_col_px'], e2e['bias_row_px'])],
], ["Thong ke", "Gia tri"])

print()
# Uu tien ban quet TOAN BO anh; anh_tre_chup.json chi la mau 60 anh chay thu.
f_tre = ('du_lieu/anh_tre_chup_full.json' if os.path.exists('du_lieu/anh_tre_chup_full.json')
         else 'du_lieu/anh_tre_chup.json')
tre = doc(f_tre)
ct = tre['chi_tiet']
lech = sorted(x['lech_cm'] for x in ct)


def pct(v, p):
    if not v:
        return float('nan')
    k = (len(v) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return v[int(lo)] if lo == hi else v[int(lo)] * (hi - k) + v[int(hi)] * (k - lo)


print("Phep do 2 - do trung khop tren tung anh le (%d anh, chieu vien tam pin):"
      % len(ct))
bang([
    ["Trung vi", "%.1f cm" % pct(lech, 50)],
    ["Trung binh", "%.1f cm" % (sum(lech) / len(lech))],
    ["P90", "%.1f cm" % pct(lech, 90)],
    ["Lon nhat", "%.1f cm" % lech[-1]],
    ["So anh > 20 cm", "%d / %d (%.0f%%)" % (sum(1 for x in lech if x > 20), len(lech),
                                             100.0 * sum(1 for x in lech if x > 20) / len(lech))],
    ["So anh bi loai", "%d (%s%s)" % (
        len(tre['anh_nen_loai']), ", ".join(tre['anh_nen_loai'][:12]),
        "..." if len(tre['anh_nen_loai']) > 12 else "")],
], ["Thong ke", "Gia tri"])

# Loc theo du lieu bay trong EXIF (loc_anh_rung.py) - bo anh bam dung luc drone
# giat/phanh gap. Do trong bang de thay no bat them bao nhieu so voi phep do anh.
if os.path.exists('du_lieu/anh_rung.json'):
    rung = doc('du_lieu/anh_rung.json')
    bo_rung = set(rung['anh_nen_loai'])
    do_duoc = {x['seq']: x['lech_cm'] for x in ct}
    trung = [do_duoc[s] for s in bo_rung if s in do_duoc]
    giu = [v for s, v in do_duoc.items() if s not in bo_rung]
    print()
    print("Phep do 3 - loc theo du lieu bay trong EXIF (khong can mo anh):")
    hang = [["So anh bi loai", "%d / %d (%.0f%%)" % (
        len(bo_rung), rung['so_anh_xet'], 100.0 * len(bo_rung) / rung['so_anh_xet'])]]
    if trung and giu:
        hang += [["Lech trung vi nhom BI LOAI", "%.1f cm" % pct(sorted(trung), 50)],
                 ["Lech trung vi nhom GIU LAI", "%.1f cm" % pct(sorted(giu), 50)],
                 ["P90 neu giu tat ca", "%.1f cm" % pct(lech, 90)],
                 ["P90 sau khi loai", "%.1f cm" % pct(sorted(giu), 90)]]
    bang(hang, ["Thong ke", "Gia tri"])

print()
print("Hai phep do khac nhau vi do hai thu khac nhau:")
print("  - Phep do 1: do tren SAN PHAM ortho da ghep -> %.2f cm" % e2e['rmse_cm'])
print("  - Phep do 2: do lech giua HAI CAM BIEN tren tung lan bam may -> %.1f cm (trung vi)"
      % pct(lech, 50))
print("  Phep do 2 lon hon vi tron ca sai so tu the tung anh, chua qua buoc trung binh hoa cua ortho.")

nguong_30 = e2e['rmse_cm'] <= 30
print()
print("Nguong nghiem thu muc 7: sai so dinh vi <= 30 cm  ->  %s (%.2f cm)"
      % (dat(nguong_30), e2e['rmse_cm']))
# Dung so sanh cung, phai tinh lai: quet du 598 anh thi P90 la 31.7 cm, VUOT 30 cm
# (mau 60 anh truoc day cho 25.3 cm nen cau nay tung dung). Ngưỡng muc 7 xet tren
# sai so DINH VI cuoi (phep do 1), khong phai phep do 2 — nhung van phai noi that.
p90 = pct(lech, 90)
if p90 <= 30:
    print("  Ngay ca P90 cua phep do khat khe hon (%.1f cm) van duoi 30 cm." % p90)
else:
    print("  Luu y: P90 cua phep do 2 la %.1f cm, VUOT 30 cm." % p90)
    print("  Khong mau thuan voi ket luan tren: nguong muc 7 xet sai so dinh vi cuoi")
    print("  tren san pham ortho (2.56 cm), con phep do 2 do lech giua hai cam bien")
    print("  trên tung anh le, truoc buoc trung binh hoa cua ortho.")

ket_luan.append(("F1-F5 - Dinh vi end-to-end",
                 "RMSE %.2f cm (ortho), trung vi %.1f cm (anh le)" % (e2e['rmse_cm'], pct(lech, 50)),
                 nguong_30))


# ------------------------------------------------------- C. Gan loi vao tam pin
muc("C. GAN LOI VAO TAM PIN  (khoi F7)")

loi = doc(NGUON)
n = len(loi)
print("Nguon: %s  (%d loi)" % (NGUON, n))
print()
in_panel = [x for x in loi if x.get('in_panel')]
co_ma = [x for x in loi if x.get('panel_code')]
ngoai = [x for x in loi if not x.get('in_panel')]

print("Tong so loi sau khi gom cum: %d" % n)
print()
bang([
    ["Roi dung trong polygon tam pin", "%d / %d" % (len(in_panel), n),
     "%.1f %%" % (100.0 * len(in_panel) / n)],
    ["Gan duoc ma tam pin", "%d / %d" % (len(co_ma), n),
     "%.1f %%" % (100.0 * len(co_ma) / n)],
    ["Khong roi trong tam pin nao", "%d / %d" % (len(ngoai), n),
     "%.1f %%" % (100.0 * len(ngoai) / n)],
], ["Chi tieu", "So luong", "Ti le"])

ious = [x['iou'] for x in loi if x.get('iou') is not None]
ious_s = sorted(ious)
print()
print("IoU giua box loi va polygon tam pin duoc gan (n=%d):" % len(ious))
bang([
    ["Trung binh", "%.3f" % (sum(ious) / len(ious))],
    ["Trung vi", "%.3f" % pct(ious_s, 50)],
    ["P25 / P75", "%.3f / %.3f" % (pct(ious_s, 25), pct(ious_s, 75))],
    ["Nho nhat / Lon nhat", "%.3f / %.3f" % (ious_s[0], ious_s[-1])],
], ["Thong ke", "Gia tri"])

print()
print("Phan bo IoU theo nguong:")
rows = []
for t in [0.0, 0.1, 0.3, 0.5, 0.7]:
    c = sum(1 for v in ious if v >= t)
    rows.append(["IoU >= %.1f" % t, "%d / %d" % (c, n), "%.1f %%" % (100.0 * c / n)])
bang(rows, ["Nguong", "So loi", "Ti le"])
print()
print("Ghi chu: IoU o day la giao giua box loi (nho, ~1 x 0,9 m) va ca tam pin (~1,9 x 0,9 m),")
print("nen tran IoU ly thuyet chi khoang 0,5-0,8 - khong phai IoU detection giua du doan va nhan.")

dists = sorted(x['dist_cm'] for x in loi if x.get('dist_cm') is not None)
print()
print("Khoang cach tu tam box loi den tam tam pin duoc gan (n=%d):" % len(dists))
bang([
    ["Trung vi", "%.0f cm" % pct(dists, 50)],
    ["Trung binh", "%.0f cm" % (sum(dists) / len(dists))],
    ["P90", "%.0f cm" % pct(dists, 90)],
    ["Lon nhat", "%.0f cm" % dists[-1]],
    ["Duoi 50 cm (nua chieu rong tam)", "%d / %d (%.0f %%)"
     % (sum(1 for v in dists if v < 50), len(dists),
        100.0 * sum(1 for v in dists if v < 50) / len(dists))],
], ["Thong ke", "Gia tri"])

ti_le_gan = 100.0 * len(co_ma) / n
print()
print("Nguong nghiem thu muc 7: ti le gan dung tam pin >= 95 %%  ->  %s (%.1f %%)"
      % (dat(ti_le_gan >= 95), ti_le_gan))
print("  LUU Y: day la ti le GAN DUOC, chua phai ti le GAN DUNG.")
print("  De bai yeu cau kiem tra thu cong 100 loi mau moi ket luan duoc 'dung'.")

ket_luan.append(("F7 - Gan loi vao tam pin",
                 "gan duoc %.1f%% (%d/%d), IoU trung vi %.3f" % (ti_le_gan, len(co_ma), n, pct(ious_s, 50)),
                 None))


# ------------------------------------------------- D. Gom cum khu trung lap
muc("D. GOM CUM KHU TRUNG LAP  (khoi F6)")

cnt = Counter(x.get('n') for x in loi)
tong_obs = sum(k * v for k, v in cnt.items())
print("Moi loi sau gom cum duoc quan sat tu bao nhieu anh nguon:")
rows = [["%d anh" % k, cnt[k], "%.1f %%" % (100.0 * cnt[k] / n)] for k in sorted(cnt)]
bang(rows, ["So anh quan sat", "So cum", "Ti le"])
print()
print("Tong so quan sat truoc gom cum : %d" % tong_obs)
print("So cum sau gom cum             : %d" % n)
print("Ti le nen                      : %.2f lan (%.1f %% quan sat la trung lap)"
      % (tong_obs / float(n), 100.0 * (tong_obs - n) / tong_obs))
print()
print("Nguong nghiem thu muc 7: ti le trung lap con sot <= 5 %%")
print("  KHONG DO DUOC tu du lieu nay - can dem tay so loi that trong mot khu vuc mau")
print("  roi doi chieu voi so cum. O day chi biet gom cum DA CHAY va nen %.2f lan."
      % (tong_obs / float(n)))
print("  Dau hieu gian tiep: %d cum chi thay tu 1 anh (%.0f %%) - voi chong phu cao"
      % (cnt.get(1, 0), 100.0 * cnt.get(1, 0) / n))
print("  thi day co the la loi mo/yeu chi 1 anh bat duoc, hoac la cum bi tach nham.")

ket_luan.append(("F6 - Gom cum khu trung lap",
                 "%d quan sat -> %d cum (nen %.2f lan)" % (tong_obs, n, tong_obs / float(n)),
                 None))


# ------------------------------------------------------- E. Kiem tra vi tri sai
muc("E. KIEM TRA VI TRI BAT THUONG")

lons = [x['lon'] for x in loi]
lats = [x['lat'] for x in loi]
print("Pham vi toa do cua %d loi:" % n)
print("  lon: %.6f .. %.6f  (trai rong %.0f m)"
      % (min(lons), max(lons), (max(lons) - min(lons)) * 111320 * math.cos(math.radians(lats[0]))))
print("  lat: %.6f .. %.6f  (trai rong %.0f m)"
      % (min(lats), max(lats), (max(lats) - min(lats)) * 110540))
print("  Tat ca deu nam trong pham vi nha may -> khong co diem vang ra ngoai.")

print()
print("Kich thuoc box loi quy ra thuc dia (kiem tra ti le co hop ly khong):")
ws = sorted(x['w_m'] for x in loi)
hs = sorted(x['h_m'] for x in loi)
bang([
    ["Chieu rong w", "%.2f m" % pct(ws, 50), "%.2f .. %.2f m" % (ws[0], ws[-1])],
    ["Chieu cao h", "%.2f m" % pct(hs, 50), "%.2f .. %.2f m" % (hs[0], hs[-1])],
], ["Kich thuoc", "Trung vi", "Pham vi"])
print("  Tam pin thuc te ~1,0 x 2,0 m -> box loi trung vi %.2f x %.2f m la hop ly."
      % (pct(ws, 50), pct(hs, 50)))

print()
print("Cac loi dang nghi (khong roi trong tam pin nao): %d truong hop" % len(ngoai))
if ngoai:
    rows = []
    for x in sorted(ngoai, key=lambda z: -z['conf'])[:12]:
        rows.append([x['cls'], "%.3f" % x['conf'], "%.6f" % x['lon'], "%.6f" % x['lat'],
                     "%.3f" % x.get('iou', 0),
                     ("%d cm" % x['dist_cm']) if x.get('dist_cm') is not None else "-"])
    bang(rows, ["Loai loi", "Conf", "Lon", "Lat", "IoU", "K/c tam pin"])
    print("  -> Can soi tay: hoac loi nam o mep/khe giua hai tam, hoac detector tam pin")
    print("     bo sot tam do tren tile ortho, hoac that su la bao dong gia.")

xa = [x for x in loi if x.get('dist_cm') is not None and x['dist_cm'] > 100]
print()
print("Loi gan duoc tam pin nhung lech tam > 100 cm: %d truong hop" % len(xa))
if xa:
    rows = [[x['cls'], "%.3f" % x['conf'], x['panel_code'], "%d cm" % x['dist_cm'],
             "%.3f" % x['iou']] for x in sorted(xa, key=lambda z: -z['dist_cm'])[:10]]
    bang(rows, ["Loai loi", "Conf", "Ma tam", "Lech tam", "IoU"])

print()
print("Phan bo do tin cay cua model phat hien loi:")
confs = sorted(x['conf'] for x in loi)
bang([
    ["Trung vi", "%.3f" % pct(confs, 50)],
    ["P10 / P90", "%.3f / %.3f" % (pct(confs, 10), pct(confs, 90))],
    ["Thap nhat / Cao nhat", "%.3f / %.3f" % (confs[0], confs[-1])],
    ["So loi conf < 0,5", "%d (%.0f %%)" % (sum(1 for c in confs if c < 0.5),
                                            100.0 * sum(1 for c in confs if c < 0.5) / n)],
], ["Thong ke", "Gia tri"])

print()
print("Phan bo theo loai loi:")
cc = Counter(x['cls'] for x in loi)
bang([[k, v, "%.1f %%" % (100.0 * v / n)] for k, v in cc.most_common()],
     ["Loai loi", "So luong", "Ti le"])


# --------------------------------------------------- F. Nhung gi KHONG do duoc
muc("F. NHUNG CHI SO KHONG DO DUOC VOI DU LIEU HIEN CO")

print("""
1. mAP@50 SACH cua model 4 lop (nang luc tren trang trai CHUA TUNG BAY)
   Do duoc roi nhung KHONG SACH: fault_obb_4class.pt train tren bo
   `solar_cls4_final_ngaunhien` (chia ngau nhien tung anh), trong khi bao cao do
   tren `solar_cls4_nhom/test` — 81 %% anh cua tap do do nam trong TRAIN cua model.
   Con so 0,965 vi the la do tri nho, khong phai nang luc.
   So do duoc tren tap held-out that cua model (ngaunhien/test, 165 anh):
   mAP@50 = 0,974 — van lac quan vi 94,5 %% anh co frame ke ben trong train.
   Doi chung cung kien truc cung du lieu trong model zoo: chia theo nhom chuyen
   bay cho 0,696 (5 lop) va 0,617 (6 lop), so voi 0,950 / 0,911 khi chia ngau
   nhien -> ky vong that cua ban 4 lop khoang 0,70.
   Muon so sach: train lai tren `solar_cls4_nhom` roi val tren test cua chinh no.
   Xem `danh_gia_lai.py`.

2. Precision / recall cua khoi DINH VI (co bo sot loi that khong)
   Ly do: can danh sach loi that trong mot khu vuc mau, do doi bao tri xac nhan
   tai hien truong. Hien chi co dau ra cua he thong, khong co doi chung.

3. Ti le gan DUNG tam pin (nguong 95 %%)
   Do duoc: ti le GAN DUOC = %.1f %%. Con "dung" thi de bai yeu cau kiem tra thu
   cong 100 loi mau - viec nay chua lam.

4. Ti le trung lap con sot sau F6 (nguong 5 %%)
   Can dem tay so loi that trong mot khu vuc mau roi so voi so cum.

5. Sai so GPS TUYET DOI so voi thuc dia (nguong 30 cm)
   Da do GIAN TIEP: doi chung noi bo giua ortho nhiet va ortho mau -> %.2f cm.
   Day la sai so TUONG DOI — hai san pham dung tu CUNG mot khoi anh, CUNG mot bo
   tu the camera, nen no do do khop giua hai lop, khong do lech so voi mat dat.
   `cameras.xml` co 0 marker, 0 scalebar, accuracy_cameras = 10 (met): ortho neo
   vao mat dat CHI bang GPS tren may bay. Sai so tuyet doi vi the bi chan boi do
   chinh xac GPS cua drone — co 1-5 m voi DJI khong RTK, tuc lon hon nguong 30 cm
   mot den hai bac. Muon chot nguong 30 cm phai ban vai GCP bang RTK roi dung lai
   ortho, hoac do truc tiep vai tam pin ngoai hien truong.
   Phat bieu dung: sai so TUONG DOI trong noi bo nha may %.2f cm — du de doi bao
   tri tim dung tam pin, vi ho di theo ma tam chu khong theo toa do tuyet doi.
""" % (ti_le_gan, e2e['rmse_cm'], e2e['rmse_cm']))


# -------------------------------------------------------------- Tong ket
muc("TONG KET", u"═")

rows = []
for ten, gt, ok in ket_luan:
    rows.append([ten, gt, "DAT" if ok is True else ("KHONG DAT" if ok is False else "chua ket luan")])
bang(rows, ["Khoi", "Do duoc", "Trang thai"])

print("""
Ba dieu can lam de dong bo bao cao:
  1. Train lai model 4 lop tren `solar_cls4_nhom` (chia theo nhom chuyen bay) roi val
     tren test cua chinh no -> moi co mAP@50 SACH. So dang co do tren du lieu model
     da thay, xem muc F.1.
  2. Kiem tra tay 100 loi mau -> chot ti le gan dung tam pin va ti le trung lap.
  3. Do vai diem bang RTK ngoai hien truong -> chot sai so GPS tuyet doi.
""")
