# -*- coding: utf-8 -*-
"""ORTHO NHIET METASHAPE lech bao nhieu so voi ORTHO NHIET TU GHEP BANG H?

Ban tu ghep bam theo loi giai cua anh RGB (dung tu the RGB + luoi cua ortho mau),
nen no khop voi ortho mau THEO DINH NGHIA. Do lech giua hai ban nhiet = do lech
cua ban Metashape so voi RGB.

Bay tuan hoan: luoi tam pin lap lai moi ~1,86 m nen do truc tiep se nhay o.
Cach vong: do THO tren anh thu nho 6 lan (luc do tung tam nhoe di, chi con cau
truc HANG pin, buoc ~5-6 m) roi TINH lai o do phan giai goc trong ban kinh hep.
"""
import json
import numpy as np, cv2, rasterio

import goc  # dua tien trinh ve goc du an  # noqa: F401

TU = rasterio.open('ket_qua/ortho/ortho_nhiet_tu_lam.tif')
MS = rasterio.open('du_lieu/Thermal2_31M_full_export/thermal_ortho.tif')
GSD_CM = abs(TU.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
print('GSD ban tu ghep: %.3f cm/px' % GSD_CM)

def doc(src, lon, lat, npx, gsd_dich=None):
    c, r = ~src.transform * (lon, lat)
    w = rasterio.windows.Window(int(c-npx/2), int(r-npx/2), npx, npx)
    if w.col_off < 0 or w.row_off < 0 or w.col_off+npx > src.width or w.row_off+npx > src.height:
        return None
    a = src.read(1, window=w).astype(np.float32)
    if gsd_dich:
        k = abs(src.transform.a)/gsd_dich
        a = cv2.resize(a, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    return a

def khop(a, b, R):
    if b.shape[0] < a.shape[0]+2*R: return None
    r = cv2.matchTemplate(b, a, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    return loc[0]-R, loc[1]-R, mx

bb = MS.bounds
lons = np.linspace(bb.left+0.00002, bb.right-0.00002, 14)
lats = np.linspace(bb.bottom+0.00002, bb.top-0.00002, 6)
GD = abs(TU.transform.a)                      # do/px cua ban tu ghep
A_PX, R_THO, R_TINH, HS = 200, 22, 14, 6      # HS = he so thu nho khi do tho

ket = []
for lat in lats:
    for lon in lons:
        a = doc(TU, lon, lat, A_PX)
        if a is None or (a > 4).mean() < 0.92 or a.std() < 10: continue
        npx_b = int((A_PX + 2*(R_THO*HS + R_TINH)) * GD/abs(MS.transform.a))
        b = doc(MS, lon, lat, npx_b, gsd_dich=GD)
        if b is None or (b > 4).mean() < 0.92 or b.std() < 10: continue
        M = R_THO*HS + R_TINH
        if b.shape[0] < a.shape[0] + 2*M: continue
        b = b[:a.shape[0]+2*M, :a.shape[0]+2*M]

        aT = cv2.resize(a, None, fx=1/HS, fy=1/HS, interpolation=cv2.INTER_AREA)
        bT = cv2.resize(b, None, fx=1/HS, fy=1/HS, interpolation=cv2.INTER_AREA)
        Rt = (bT.shape[0]-aT.shape[0])//2
        t = khop(aT, bT, Rt)
        if t is None or t[2] < 0.45: continue
        ox, oy = t[0]*HS, t[1]*HS

        x0, y0 = M+ox-R_TINH, M+oy-R_TINH
        if x0 < 0 or y0 < 0 or x0+a.shape[0]+2*R_TINH > b.shape[1] \
           or y0+a.shape[0]+2*R_TINH > b.shape[0]: continue
        f = khop(a, b[int(y0):int(y0)+a.shape[0]+2*R_TINH,
                      int(x0):int(x0)+a.shape[0]+2*R_TINH], R_TINH)
        if f is None or f[2] < 0.45: continue
        ket.append((lon, lat, ox+f[0], oy+f[1], f[2],
                    abs(f[0]) >= R_TINH-0.5 or abs(f[1]) >= R_TINH-0.5))

K = np.array([(k[2], k[3]) for k in ket], float)
d = np.hypot(K[:,0], K[:,1]) * GSD_CM
cham = np.array([k[5] for k in ket])
print()
print('='*66)
print('ORTHO NHIET METASHAPE  so voi  ORTHO NHIET TU GHEP BANG H')
print('='*66)
print('So diem do : %d   (%d diem cham mep buoc tinh = %.0f%%)' % (len(K), cham.sum(), 100*cham.mean()))
print()
print('Lech ngang dx : trung vi %+7.1f cm   | do lech chuan %6.1f cm' % (np.median(K[:,0])*GSD_CM, K[:,0].std()*GSD_CM))
print('Lech doc   dy : trung vi %+7.1f cm   | do lech chuan %6.1f cm' % (np.median(K[:,1])*GSD_CM, K[:,1].std()*GSD_CM))
print('Khoang cach   : trung vi %7.1f cm   | p90 %.1f cm | lon nhat %.1f cm'
      % (np.median(d), np.percentile(d,90), d.max()))
print()
print('Huong: %d diem lech phai / %d trai   |   %d xuong / %d len'
      % ((K[:,0]>0).sum(), (K[:,0]<0).sum(), (K[:,1]>0).sum(), (K[:,1]<0).sum()))
LON = np.array([k[0] for k in ket]); LAT = np.array([k[1] for k in ket])
for ten, v in (('dx', K[:,0]), ('dy', K[:,1])):
    for tt, t in (('kinh do', LON), ('vi do', LAT)):
        r = np.corrcoef(t, v)[0,1]
        print('  tuong quan %s theo %-8s : %+.2f%s' % (ten, tt, r,
              '   <- doi dan theo vi tri' if abs(r) > 0.4 else ''))
json.dump({'gsd_cm': GSD_CM, 'so_diem': len(K),
           'dx_trung_vi_cm': float(np.median(K[:,0])*GSD_CM),
           'dy_trung_vi_cm': float(np.median(K[:,1])*GSD_CM),
           'lech_trung_vi_cm': float(np.median(d)), 'lech_p90_cm': float(np.percentile(d,90)),
           'lech_max_cm': float(d.max())},
          open('ket_qua/ket_qua_val/lech_ortho_nhiet_metashape.json','w',encoding='utf-8'), indent=1)
print('\n-> ket_qua_val/lech_ortho_nhiet_metashape.json')
