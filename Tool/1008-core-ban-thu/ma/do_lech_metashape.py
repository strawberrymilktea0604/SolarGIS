# -*- coding: utf-8 -*-
"""So hai lop ortho NHIET trong viewer: ban tu ghep bang H vs ban Metashape.

Ca hai da o cung mot khung toa do (DATA.frame) nen do lech tai nhieu o luoi la
biet ngay: lech DEU mot huong = chi khac goc toa do; lech MOI CHO MOT KIEU =
hai loi giai bo khac nhau, khong bu duoc bang hang so.

Ban kinh do 9 px overview = 85 cm, HEP hon nua buoc tam (~10 px) nen khong nhay o.
"""
import base64, json
import numpy as np, cv2

import goc  # dua tien trinh ve goc du an  # noqa: F401

s = open('cong_cu/so_sanh_model.html', encoding='utf-8').read()
i = s.index('DATA'); i = s.index('{', i)
D, _ = json.JSONDecoder().raw_decode(s, i)
F = D['frame']
CM = F['w']/2400*0.9569              # cm mat dat tren 1 px overview

def anh(k):
    b = base64.b64decode(D[k].split(',', 1)[1])
    return cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_GRAYSCALE)

TU  = anh('overview_thermal')         # tu ghep bang H
MS  = anh('overview_thermal_ms')      # Metashape
H_, W_ = TU.shape
O, R = 64, 9                          # o 64 px, ban kinh do 9 px

ket = []
for y in range(0, H_-O-R, 48):
    for x in range(0, W_-O-R, 48):
        a = TU[y:y+O, x:x+O].astype(np.float32)
        if (a > 8).mean() < 0.95: continue          # bo o co lo thung
        b = MS[y-R:y+O+R, x-R:x+O+R].astype(np.float32)
        if b.shape != (O+2*R, O+2*R) or (b > 8).mean() < 0.95: continue
        if a.std() < 12 or b.std() < 12: continue   # bo o phang li, khong do duoc
        r = cv2.matchTemplate(b, a, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx < 0.55: continue
        ket.append((x, y, loc[0]-R, loc[1]-R, mx))

A = np.array(ket, float)
dx, dy = A[:, 2], A[:, 3]
d = np.hypot(dx, dy)
cham = (np.abs(dx) >= R-0.5) | (np.abs(dy) >= R-0.5)

print("=" * 68)
print("LECH GIUA ORTHO NHIET METASHAPE VA ORTHO NHIET TU GHEP BANG H")
print("=" * 68)
print("So o do duoc      : %d  (%d o cham mep ban kinh = %.0f%%)" % (len(A), cham.sum(), 100*cham.mean()))
print()
print("Lech NGANG dx : trung vi %+6.2f px = %+7.1f cm   | do lech chuan %.2f px" % (np.median(dx), np.median(dx)*CM, dx.std()))
print("Lech DOC   dy : trung vi %+6.2f px = %+7.1f cm   | do lech chuan %.2f px" % (np.median(dy), np.median(dy)*CM, dy.std()))
print("Khoang cach   : trung vi %6.2f px = %7.1f cm   | p90 %.1f cm | lon nhat %.1f cm"
      % (np.median(d), np.median(d)*CM, np.percentile(d, 90)*CM, d.max()*CM))
print()
n_dx = (dx > 0.5).sum(); a_dx = (dx < -0.5).sum()
n_dy = (dy > 0.5).sum(); a_dy = (dy < -0.5).sum()
print("Huong lech ngang: %d o duong / %d o am" % (n_dx, a_dx))
print("Huong lech doc  : %d o duong / %d o am" % (n_dy, a_dy))
print()
# lech co phu thuoc VI TRI khong -> hoi quy tuyen tinh
for ten, v in (("dx", dx), ("dy", dy)):
    for tt, t in (("theo cot", A[:, 0]), ("theo hang", A[:, 1])):
        r = np.corrcoef(t, v)[0, 1]
        if abs(r) > 0.3:
            print("  %s %-10s tuong quan %+.2f  <- lech DOI DAN theo vi tri" % (ten, tt, r))
print()
if np.median(d)*CM > 30 and max(n_dx, a_dx) < 0.75*len(A):
    print("KET LUAN: lech LON va KHONG cung mot huong -> hai loi giai bo khac nhau,")
    print("          khong phai chi lech goc toa do. Khong bu duoc bang hang so.")
json.dump({"so_o": len(A), "cm_tren_px": CM,
           "dx_trung_vi_cm": float(np.median(dx)*CM), "dy_trung_vi_cm": float(np.median(dy)*CM),
           "lech_trung_vi_cm": float(np.median(d)*CM), "lech_p90_cm": float(np.percentile(d,90)*CM),
           "lech_max_cm": float(d.max()*CM), "ty_le_cham_mep": float(cham.mean())},
          open("ket_qua/ket_qua_val/lech_metashape.json","w",encoding="utf-8"), indent=1)
print("-> ket_qua_val/lech_metashape.json")

# ======================================================================
# BUOC 2: lech co giai thich duoc bang MOT phep bien doi toan cuc khong?
# ======================================================================
print()
print("=" * 68)
print("BUOC 2 - KHOP MOT PHEP BIEN DOI TOAN CUC ROI DO PHAN DU")
print("=" * 68)
ok = ~cham
X, Y = A[ok, 0], A[ok, 1]
M = np.c_[np.ones(len(X)), X, Y]
ax, *_ = np.linalg.lstsq(M, dx[ok], rcond=None)
ay, *_ = np.linalg.lstsq(M, dy[ok], rcond=None)
print("Khop tren %d o khong cham mep:" % ok.sum())
print("  dx = %+.3f %+.5f*cot %+.5f*hang" % tuple(ax))
print("  dy = %+.3f %+.5f*cot %+.5f*hang" % tuple(ay))
print()
print("Doc ra:")
print("  chenh ti le ngang : %+.3f %%" % (ax[1]*100))
print("  chenh ti le doc   : %+.3f %%" % (ay[2]*100))
print("  xoay tuong doi    : %+.3f do" % (np.degrees(np.arctan2(ay[1]-ax[2], 2))/1))
print("  tinh tien         : (%+.0f, %+.0f) cm" % (ax[0]*CM, ay[0]*CM))
print("  => tren chieu doc %d px, chenh ti le doc lam hai ban truot nhau %.0f cm"
      % (H_, abs(ay[2])*H_*CM))

gx, gy = np.meshgrid(np.arange(W_, dtype=np.float32), np.arange(H_, dtype=np.float32))
mx = (gx + ax[0] + ax[1]*gx + ax[2]*gy).astype(np.float32)
my = (gy + ay[0] + ay[1]*gx + ay[2]*gy).astype(np.float32)
MS2 = cv2.remap(MS, mx, my, cv2.INTER_LINEAR, borderValue=0)

du = []
for x, y, _, _, _ in ket:
    x, y = int(x), int(y)
    a = TU[y:y+O, x:x+O].astype(np.float32)
    b = MS2[y-R:y+O+R, x-R:x+O+R].astype(np.float32)
    if b.shape != (O+2*R, O+2*R) or (b > 8).mean() < 0.95: continue
    r = cv2.matchTemplate(b, a, cv2.TM_CCOEFF_NORMED)
    _, mxv, _, loc = cv2.minMaxLoc(r)
    if mxv < 0.55: continue
    du.append((loc[0]-R, loc[1]-R))
Ddu = np.hypot(*np.array(du).T)
print()
print("PHAN DU sau khi khu phep bien doi toan cuc (%d o):" % len(du))
print("  trung vi %5.1f cm  (truoc: %.1f cm)   p90 %5.1f cm   lon nhat %5.1f cm"
      % (np.median(Ddu)*CM, np.median(d)*CM, np.percentile(Ddu,90)*CM, Ddu.max()*CM))
cham2 = (np.abs(np.array(du)[:,0]) >= R-0.5) | (np.abs(np.array(du)[:,1]) >= R-0.5)
print("  o van cham mep: %.0f%%  (truoc: %.0f%%)" % (100*cham2.mean(), 100*cham.mean()))
