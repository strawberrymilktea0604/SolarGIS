#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Kiem chung gia thuyet: 25 ca loi khong roi vao tam pin nao la do
detector tam pin bo sot tam o ria ortho, hay do dinh vi sai?

Cach kiem: voi moi ca lech, tim polygon tam pin GAN NHAT trong
tam_pin_polygon.json (6300 tam) roi do khoang cach.
  - Neu QUANH DO CO tam pin (gan) -> dinh vi lech, hoac loi nam o khe
  - Neu QUANH DO TRONG (xa)       -> detector bo sot tam -> gia thuyet dung
"""
import json
import math
import os
from collections import Counter

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GSD_ORTHO_CM = 0.9569205142071102  # cm/px, tu sai_so_end_to_end.json

loi = json.load(open('ket_qua/loi_tren_ortho_nhiet.json', encoding='utf-8'))
pans = json.load(open('ket_qua/tam_pin_polygon.json', encoding='utf-8'))

print("Tong so loi        : %d" % len(loi))
print("Tong so tam pin    : %d" % len(pans))


def tam(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return sum(xs) / len(xs), sum(ys) / len(ys)


# Tam cua moi polygon + hop bao (bounding box) de loc nhanh
pan_tam = [tam(p) for p in pans]
pan_minx = [min(q[0] for q in p) for p in pans]
pan_maxx = [max(q[0] for q in p) for p in pans]
pan_miny = [min(q[1] for q in p) for p in pans]
pan_maxy = [max(q[1] for q in p) for p in pans]

# Pham vi phu song cua detector tam pin
print()
print("Pham vi ortho ma detector tam pin da phu:")
print("  col: %.0f .. %.0f px" % (min(pan_minx), max(pan_maxx)))
print("  row: %.0f .. %.0f px" % (min(pan_miny), max(pan_maxy)))

ngoai = [x for x in loi if not x.get('in_panel')]
print()
print("So ca khong roi vao tam pin nao: %d" % len(ngoai))
print()

ket_qua = []
for x in ngoai:
    ox, oy = x['ocol'], x['orow']
    # tim tam gan nhat
    tot, td = None, 1e18
    for i, (cx, cy) in enumerate(pan_tam):
        d = (cx - ox) ** 2 + (cy - oy) ** 2
        if d < td:
            td, tot = d, i
    d_px = math.sqrt(td)
    d_cm = d_px * GSD_ORTHO_CM

    # dem so tam pin trong ban kinh 5 m (~522 px) quanh diem loi
    bk_px = 500.0 / GSD_ORTHO_CM
    gan = sum(1 for cx, cy in pan_tam
              if abs(cx - ox) < bk_px and abs(cy - oy) < bk_px)

    ket_qua.append({
        'cls': x['cls'], 'conf': x['conf'], 'lon': x['lon'], 'lat': x['lat'],
        'ocol': ox, 'orow': oy, 'iou': x.get('iou'),
        'tam_gan_nhat_px': d_px, 'tam_gan_nhat_cm': d_cm,
        'so_tam_trong_5m': gan,
    })

ket_qua.sort(key=lambda z: -z['conf'])

print("%-16s %6s %10s %10s %8s %10s" % ("Loai loi", "Conf", "ocol", "orow",
                                        "K/c tam", "Tam trong"))
print("%-16s %6s %10s %10s %8s %10s" % ("", "", "", "", "gan nhat", "5 m"))
print("-" * 68)
for r in ket_qua:
    print("%-16s %6.3f %10.0f %10.0f %7.0fcm %10d"
          % (r['cls'], r['conf'], r['ocol'], r['orow'],
             r['tam_gan_nhat_cm'], r['so_tam_trong_5m']))

# ---------------------------------------------------------------- phan loai
print()
print("=" * 72)
print("PHAN LOAI NGUYEN NHAN")
print("=" * 72)

# Nua chieu rong tam pin ~ 50 cm; khe giua hai day ~ 1-2 m
sot = [r for r in ket_qua if r['so_tam_trong_5m'] == 0]
khe = [r for r in ket_qua if r['so_tam_trong_5m'] > 0 and r['tam_gan_nhat_cm'] <= 150]
xa = [r for r in ket_qua if r['so_tam_trong_5m'] > 0 and r['tam_gan_nhat_cm'] > 150]

print()
print("A. Vung TRONG hoan toan (khong tam pin nao trong ban kinh 5 m): %d ca"
      % len(sot))
print("   -> detector tam pin khong phu vung do, HOAC loi that su nam ngoai day pin")
print()
print("B. Co tam pin quanh do, loi cach tam gan nhat <= 1,5 m: %d ca" % len(khe))
print("   -> loi nam o KHE giua hai tam, hoac dinh vi lech vai chuc cm")
print()
print("C. Co tam pin quanh do nhung loi cach xa > 1,5 m: %d ca" % len(xa))
print("   -> dang nghi nhat: dinh vi sai han, hoac bao dong gia")

# ------------------------------------------------- kiem gia thuyet "ria dong"
print()
print("=" * 72)
print("KIEM GIA THUYET 'TUM O RIA DONG'")
print("=" * 72)

lons_tat = [x['lon'] for x in loi]
lo, hi = min(lons_tat), max(lons_tat)
print()
print("Pham vi lon toan bo 211 loi: %.6f .. %.6f" % (lo, hi))
print()
print("Chia nha may thanh 5 dai theo chieu dong-tay:")
print("%-28s %8s %8s %9s" % ("Dai lon", "Tong loi", "Lech", "Ti le lech"))
print("-" * 56)
for i in range(5):
    a = lo + (hi - lo) * i / 5.0
    b = lo + (hi - lo) * (i + 1) / 5.0
    tong = [x for x in loi if (a <= x['lon'] < b) or (i == 4 and x['lon'] == b)]
    le = [x for x in tong if not x.get('in_panel')]
    ti = (100.0 * len(le) / len(tong)) if tong else 0.0
    nhan = "%.6f-%.6f" % (a, b)
    print("%-28s %8d %8d %8.1f %%" % (nhan, len(tong), len(le), ti))

# ------------------------------------------------------------ luu ket qua
out = {
    'so_ca_lech': len(ngoai),
    'A_vung_trong_detector_bo_sot': len(sot),
    'B_nam_o_khe_hoac_lech_nho': len(khe),
    'C_lech_han_hoac_bao_dong_gia': len(xa),
    'chi_tiet': ket_qua,
}
with open('ket_qua/soi_25_ca_lech.json', 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print()
print("Da luu: soi_25_ca_lech.json")
