#!/usr/bin/env python3
"""
Ghép ORTHO NHIỆT cho toàn nhà máy, từ các ảnh nhiệt lẻ.

Nguyên lý: với mỗi pixel của lưới ortho
    pixel -> lon/lat -> cao độ từ DSM -> điểm 3D trong không gian
    -> chiếu ngược vào ảnh RGB -> qua nghịch đảo H -> pixel ảnh nhiệt -> lấy giá trị

Ba điểm khiến nó chạy được trong vài phút thay vì vài giờ:
  1. Độ phân giải đầu ra đặt theo ảnh NHIỆT (~2,9 cm/px), không phóng to vô ích
     lên 0,96 cm/px của ortho màu.
  2. Mỗi pixel chỉ tính với MỘT ảnh — ảnh có tâm chụp gần nhất, tìm bằng cây KD.
     Nếu duyệt mọi ảnh phủ pixel đó thì tốn gấp ~16 lần.
  3. Loại sẵn ảnh ở đoạn quay đầu (bay chậm), nơi sai số dọc trục rất lớn.

    python ma/ghep_ortho_nhiet.py               # toàn nhà máy
    python ma/ghep_ortho_nhiet.py --step 6      # nhanh gấp 4, thô hơn
"""
import argparse
import csv
import json
import os
import time
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--step", type=float, default=3.0,
                help="thu nhỏ so với ortho màu (3 -> ~2,9 cm/px)")
ap.add_argument("--tile", type=int, default=2048)
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/ortho/ortho_nhiet_tu_lam.tif"))
ap.add_argument("--window", type=int, nargs=4, default=None,
                metavar=("COL", "ROW", "W", "H"), help="chỉ làm một vùng của ortho màu")
ap.add_argument("--lech", default=os.path.join(BASE, "du_lieu/anh_tre_chup_full.json"),
                help="kết quả loc_anh_tre.py: bỏ ảnh đo được là lệch nhiều")
ap.add_argument("--bo-loc-lech", action="store_true", dest="bo_loc_lech",
                help="không dùng file --lech, giữ mọi ảnh")
ap.add_argument("--rung", default=os.path.join(BASE, "du_lieu/anh_rung.json"),
                help="kết quả loc_anh_rung.py: bỏ ảnh chụp lúc drone không bay đều")
ap.add_argument("--bo-loc-rung", action="store_true", dest="bo_loc_rung",
                help="không dùng file --rung")
ap.add_argument("--khong-can-sang", action="store_false", dest="can_sang",
                help="TẮT cân bằng độ sáng giữa các ảnh (mặc định bật)")
ap.add_argument("--khong-bu-tung-anh", action="store_false", dest="bu_tung_anh",
                help="TẮT bù lệch riêng từng ảnh (mặc định bật)")
ap.add_argument("--do-net-toi-thieu", type=float, default=0.5,
                help="ảnh có do_net dưới mức này thì không bù (phép đo không đáng tin)")
# --- thêm 12/08/2026, MẶC ĐỊNH TẮT: không truyền thì chạy y hệt như trước ---
ap.add_argument("--lech-tay", default=None, dest="lech_tay",
                help="file can_tay.json từ lam_can_tay.py — GHI ĐÈ bù tự động bằng "
                     "số người chấm tay. Không truyền thì không đổi gì so với trước.")
ap.add_argument("--bu-rgb", default=None, dest="bu_rgb",
                help="file bu_theo_rgb.json — CỘNG THÊM phần bù đo từ ortho màu. "
                     "Không truyền thì không đổi gì so với trước.")
args = ap.parse_args()

t0 = time.time()
# KHÔNG dùng H_da_bu từ loc_anh_tre.py: đã thử và ortho không tốt hơn (15,5 ->
# 14,4 cm, hướng lệch còn đảo dấu). Đo trên 31 vùng khắp nhà máy thấy lệch chia
# đôi 50/50 hai hướng — là nhiễu cục bộ, không bù được bằng MỘT HẰNG SỐ.
#
# Nhưng bù RIÊNG TỪNG ẢNH thì được, và được nhiều: dùng dx,dy mà loc_anh_tre.py
# đã đo sẵn cho từng ảnh, sai số đặt chỗ của ortho giảm 14,1 -> 4,3 cm (trung vị
# trên 275 cửa sổ, 238 tốt lên / 37 xấu đi). Xem mục 4a bên dưới và do_khop_ortho.py.
# File --lech nay dùng cho cả hai việc: LOẠI ảnh lệch bất thường, và BÙ phần còn lại.
def doc_loc(duong, tat, ten_script):
    """Đọc file danh sách ảnh cần loại. Thiếu file thì NÓI RA, đừng im lặng bỏ qua."""
    if tat:
        return None
    if not os.path.exists(duong):
        print(f"[!] không thấy {os.path.basename(duong)} — chạy {ten_script} trước, "
              f"lần dựng này KHÔNG lọc theo tiêu chí đó")
        return None
    return json.load(open(duong, encoding="utf-8"))


d_lech = doc_loc(args.lech, args.bo_loc_lech, "ma/loc_anh_tre.py")
d_rung = doc_loc(args.rung, args.bo_loc_rung, "ma/loc_anh_rung.py")
H = np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                            encoding="utf-8"))["H_thermal_to_rgb"])
Hinv = np.linalg.inv(H)

# ---------------------------------------------------------------- 1. XML
root = ET.parse(os.path.join(EXP, "cameras.xml")).getroot()
chunk = root.find(".//chunk")
s = chunk.find(".//sensor[@id='0']")
res = s.find("resolution")
cal = s.find("calibration[@class='adjusted']")
g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
IW, IH, F, CX, CY = int(res.get("width")), int(res.get("height")), g("f"), g("cx"), g("cy")

tr = chunk.find(".//component").find("transform")
R_ch = np.array(list(map(float, tr.find("rotation").text.split()))).reshape(3, 3)
T_ch = np.array(list(map(float, tr.find("translation").text.split())))
S_ch = float(tr.find("scale").text)

cams = {c.get("label").split("_")[2]:
        np.array(list(map(float, c.find("transform").text.split()))).reshape(4, 4)
        for c in chunk.findall(".//camera") if c.find("transform") is not None}

# ------------------------------------------------- 2. loại ảnh ở đoạn quay đầu
ks = sorted(cams, key=int)
Cch = {k: cams[k][:3, 3] for k in ks}
spd = {}
for i in range(1, len(ks) - 1):
    spd[ks[i]] = np.linalg.norm(Cch[ks[i + 1]] - Cch[ks[i - 1]]) * S_ch / 2
med = np.median(list(spd.values()))
good = [k for k in ks if spd.get(k, med) > 0.6 * med]
print(f"[LỌC] {len(good)}/{len(cams)} ảnh bay đều (bỏ {len(cams)-len(good)} ảnh quay đầu)")

# Bỏ thêm ảnh nhiệt lệch bất thường so với ảnh RGB cùng cặp — đo bằng loc_anh_tre.py.
# Ảnh lệch nửa mét đặt sai chỗ cả một vùng ortho; bỏ đi thì lấy từ ảnh lân cận,
# vốn đã chồng phủ nhiều lần nên không thủng.
if d_lech and d_lech.get("anh_nen_loai"):
    bo = set(d_lech["anh_nen_loai"])
    truoc = len(good)
    good = [k for k in good if k not in bo]
    print(f"[LỆCH] bỏ thêm {truoc-len(good)} ảnh lệch quá "
          f"{d_lech['nguong_cm']:.0f} cm -> còn {len(good)} ảnh")

# Bỏ ảnh bấm đúng lúc drone không bay đều — giật, rung, phanh gấp. Ảnh nhiệt và ảnh
# RGB của một lần bấm không nổ cùng lúc; bay đều thì H bù được, đang đổi tốc thì
# không. Đọc thẳng tốc độ bay trong XMP nên biết trước, không phải đo từng ảnh.
if d_rung and d_rung.get("anh_nen_loai"):
    bo = set(d_rung["anh_nen_loai"])
    truoc = len(good)
    good = [k for k in good if k not in bo]
    ng = d_rung["nguong"]
    print(f"[RUNG]  bỏ thêm {truoc-len(good)} ảnh drone không bay đều "
          f"(lệch tốc độ 2 cảm biến > {ng['dv_m_s']:g} m/s) -> còn {len(good)} ảnh")

if len(good) < 0.4 * len(cams):
    print(f"[!] chỉ còn {100*len(good)/len(cams):.0f}% số ảnh — lọc có thể quá tay, "
          f"ortho dễ bị thủng lỗ")

# ---------------------------------------------------------------- 3. raster
ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))

if args.window:
    c0, r0, ww, hh = args.window
else:
    c0, r0, ww, hh = 0, 0, ortho.width, ortho.height
base_tf = rasterio.windows.transform(rasterio.windows.Window(c0, r0, ww, hh), ortho.transform)
OT = base_tf * rasterio.Affine.scale(args.step, args.step)
OW, OH = int(ww / args.step), int(hh / args.step)
mdeg = 111320 * np.cos(np.radians(11.424))
print(f"[LƯỚI] {OW} x {OH} px, GSD {abs(OT.a)*mdeg*100:.2f} cm/px "
      f"({OW*abs(OT.a)*mdeg:.0f} x {OH*abs(OT.e)*110570:.0f} m)")

to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)

# --------------------------------------- 4. tâm chụp dưới đất của từng ảnh
lab, nad, Cecef, Minv = [], [], [], []
for k in good:
    M = cams[k]
    C = S_ch * (R_ch @ M[:3, 3]) + T_ch
    lon, lat, alt = to_wgs.transform(*C)
    up = np.array([np.cos(np.radians(lat)) * np.cos(np.radians(lon)),
                   np.cos(np.radians(lat)) * np.sin(np.radians(lon)),
                   np.sin(np.radians(lat))])
    d = R_ch @ (M[:3, :3] @ np.array([-CX / F, -CY / F, 1.0]))
    d /= np.linalg.norm(d)
    t = (alt - zmed) / max(1e-6, -(d @ up))
    glon, glat, _ = to_wgs.transform(*(C + t * d))
    lab.append(k); nad.append((glon, glat)); Cecef.append(C); Minv.append(np.linalg.inv(M))
nad = np.array(nad); Cecef = np.array(Cecef); Minv = np.array(Minv)
print(f"[TÂM]  tính xong tâm chụp dưới đất của {len(lab)} ảnh, {time.time()-t0:.0f}s")

try:
    from scipy.spatial import cKDTree
    tree = cKDTree(np.c_[nad[:, 0] * mdeg, nad[:, 1] * 110570])
    knn = lambda P, k: tree.query(P, k=k)[1]
except ImportError:
    def knn(P, k):
        D = ((P[:, None, 0] - nad[None, :, 0] * mdeg) ** 2
             + (P[:, None, 1] - nad[None, :, 1] * 110570) ** 2)
        return np.argsort(D, 1)[:, :k]

rows_csv = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}
cache = {}

# ------------------------------------------- 4a. bù lệch riêng từng ảnh (tuỳ chọn)
# KHÁC HẲN với H_da_bu đã thất bại ở trên. H_da_bu lấy MỘT cặp bù chung áp cho mọi
# ảnh; đo lại trên 31 vùng thì thấy 15 vùng lệch lên, 16 lệch xuống, nên một hằng số
# làm nửa số ảnh bị bù ngược — đúng như kết quả quan sát được (hướng lệch đảo dấu).
#
# Chính vì lệch đổi hướng tuỳ chỗ nên phải bù RIÊNG từng ảnh. loc_anh_tre.py đã đo
# sẵn dx,dy cho cả 598 ảnh nhưng tới giờ chỉ dùng để LOẠI ảnh, chưa dùng để sửa.
#
# Chiều dấu: trong loc_anh_tre.py, viền DỰ ĐOÁN dịch đi (dx,dy) thì khớp viền THẬT.
# Nên nội dung nhiệt thật nằm ở (tu+dx, tv+dy) — lấy mẫu phải cộng vào.
bu_anh = {}
if args.bu_tung_anh:
    if not d_lech or not d_lech.get("chi_tiet"):
        print("[!] không có chi_tiet trong file --lech, bỏ qua --bu-tung-anh")
        args.bu_tung_anh = False
    else:
        yeu = 0
        for x in d_lech["chi_tiet"]:
            if x.get("dx") is None:
                continue
            if x.get("do_net", 0) < args.do_net_toi_thieu:
                yeu += 1
                continue
            bu_anh[x["seq"]] = (float(x["dx"]), float(x["dy"]))
        co = [k for k in lab if k in bu_anh]
        if co:
            v = np.array([np.hypot(*bu_anh[k]) for k in co])
            print(f"[BÙ]   bù riêng {len(co)}/{len(lab)} ảnh đang dùng "
                  f"(bỏ {yeu} ảnh do_net thấp), dịch trung vị {np.median(v):.2f} px "
                  f"= {np.median(v)*2.87:.0f} cm, lớn nhất {v.max():.2f} px")

# --- CĂN TAY: ghi đè phép đo tự động bằng số người chấm (lam_can_tay.py) ---
# GHI ĐÈ chứ không cộng dồn, khác hẳn --bu-rgb bên dưới: người căn nhìn thẳng viền
# tấm pin trên ảnh nhiệt và kéo tới khi khít, tức họ đo LẠI đúng đại lượng mà
# loc_anh_tre.py đo — cộng hai số đo của cùng một đại lượng là bù gấp đôi.
#
# Dùng cho hai chỗ phép đo tự động bó tay, không tự sửa được:
#   chạm mép bán kính trượt 16 px -> chỉ biết "≥16 px", số ghi ra là số kẹp
#   do_net thấp                   -> đỉnh khớp không nổi, số ghi ra là nhiễu
# `anh_nen_loai` trong file căn tay là ảnh người căn tuyên bố không căn nổi.
if args.lech_tay:
    if not os.path.exists(args.lech_tay):
        print(f"[!] không thấy {args.lech_tay} — chạy lam_can_tay.py trước, "
              f"lần dựng này KHÔNG dùng số căn tay")
    else:
        d_tay = json.load(open(args.lech_tay, encoding="utf-8"))
        n = 0
        for k, d in (d_tay.get("bu") or {}).items():
            bu_anh[k] = (float(d[0]), float(d[1]))
            n += 1
        bo_tay = {str(x) for x in (d_tay.get("anh_nen_loai") or [])}
        truoc = len(lab)
        lab = [k for k in lab if k not in bo_tay]
        print(f"[TAY]  ghi đè bù cho {n} ảnh bằng số căn tay "
              f"({os.path.basename(args.lech_tay)}); "
              f"loại thêm {truoc-len(lab)} ảnh người căn báo không căn nổi")
        if n:
            args.bu_tung_anh = True

# --- thêm 12/08/2026: CỘNG THÊM phần bù đo từ ortho màu (bu_theo_rgb.py) ---
# Cộng dồn chứ không thay thế: bù cũ chỉnh theo viền tấm pin trong ảnh nhiệt,
# bù này chỉnh theo vị trí thật trên ortho màu. Hai phép đo độc lập.
# Gộp vào đây để ảnh chỉ bị NỘI SUY MỘT LẦN — nắn ortho đã ghép thì mất 22% độ nét.
if args.bu_rgb:
    if not os.path.exists(args.bu_rgb):
        print(f"[!] không thấy {args.bu_rgb} — chạy bu_theo_rgb.py trước, "
              f"lần dựng này KHÔNG cộng bù theo ortho màu")
    else:
        them = json.load(open(args.bu_rgb, encoding="utf-8")).get("bu", {})
        n = 0
        for k, d in them.items():
            cu = bu_anh.get(k, (0.0, 0.0))
            bu_anh[k] = (cu[0] + float(d[0]), cu[1] + float(d[1]))
            n += 1
        print(f"[BÙ+]  cộng thêm bù theo ortho màu cho {n} ảnh "
              f"(từ {os.path.basename(args.bu_rgb)})")
        args.bu_tung_anh = True

# ------------------------------------------------- 4b. cân bằng độ sáng (tuỳ chọn)
# Ảnh nhiệt đọc vào bằng IMREAD_GRAYSCALE là ảnh HIỂN THỊ 8-bit do DJI dựng, đã qua
# tự chỉnh gain RIÊNG CHO TỪNG ẢNH — không phải nhiệt độ tuyệt đối. Nên hai ảnh kề
# nhau chụp cùng một dãy pin vẫn ra hai mức sáng khác nhau, ghép vào là lộ mảng.
#
# Vì giá trị vốn đã không mang nghĩa nhiệt độ, việc kéo chúng về cùng một thang
# KHÔNG làm mất thông tin vật lý nào — chỉ hoàn tác phần gain mà DJI đã áp.
#
# Cách làm: mỗi ảnh lấy trung vị và khoảng tứ phân vị (bền với điểm nóng cá biệt,
# khác với min/max), rồi ánh xạ tuyến tính về mốc chung của cả tập.
sang_ke = {}
if args.can_sang:
    t1 = time.time()
    for k in lab:
        im = cv2.imread(rows_csv[k]["path_thermal"], cv2.IMREAD_GRAYSCALE)
        co = im[im > 0]
        if co.size < 100:
            continue
        p25, p50, p75 = np.percentile(co, [25, 50, 75])
        sang_ke[k] = (float(p50), max(float(p75 - p25), 1.0))
    if sang_ke:
        M_REF = float(np.median([v[0] for v in sang_ke.values()]))
        S_REF = float(np.median([v[1] for v in sang_ke.values()]))
        rr_ = [v[0] for v in sang_ke.values()]
        print(f"[SÁNG] {len(sang_ke)} ảnh, trung vị trải {min(rr_):.0f}..{max(rr_):.0f} "
              f"-> kéo hết về {M_REF:.0f} (giãn {S_REF:.0f}), {time.time()-t1:.0f}s")
    else:
        args.can_sang = False


def thermal(i):
    k = lab[i]
    if k not in cache:
        if len(cache) > 24:
            cache.pop(next(iter(cache)))
        im = cv2.imread(rows_csv[k]["path_thermal"],
                        cv2.IMREAD_GRAYSCALE).astype(np.float32)
        if args.can_sang and k in sang_ke:
            m, s = sang_ke[k]
            im = np.clip((im - m) * (S_REF / s) + M_REF, 1, 255)
        cache[k] = im
    return cache[k]


# ---------------------------------------------------------------- 5. chạy
prof = dict(driver="GTiff", height=OH, width=OW, count=1, dtype="uint8",
            crs=ortho.crs, transform=OT, compress="deflate", nodata=0,
            tiled=True, blockxsize=512, blockysize=512)
filled = total = 0
# Vùng phủ của ảnh NHIỆT dưới đất chỉ ~15 x 12 m (41% x 44% khung RGB), nhỏ hơn
# nhiều so với ảnh RGB, nên ảnh có tâm gần nhất thường vẫn không chứa pixel cần
# lấy. Phải thử nhiều ứng viên; chi phí chỉ tính trên các pixel còn trống.
K = min(24, len(lab))

with rasterio.open(args.out, "w", **prof) as dst:
    for ty in range(0, OH, args.tile):
        th_ = min(args.tile, OH - ty)
        for tx in range(0, OW, args.tile):
            tw_ = min(args.tile, OW - tx)
            cc, rr = np.meshgrid(np.arange(tx, tx + tw_) + .5,
                                 np.arange(ty, ty + th_) + .5)
            LON = OT.c + OT.a * cc
            LAT = OT.f + OT.e * rr

            dc = np.clip(((LON - dsm.transform.c) / dsm.transform.a).astype(np.int32),
                         0, dsm.width - 1)
            dr = np.clip(((LAT - dsm.transform.f) / dsm.transform.e).astype(np.int32),
                         0, dsm.height - 1)
            Z = DSM[dr, dc].astype(np.float64)
            Z[(Z == dsm.nodata) | ~np.isfinite(Z)] = zmed

            X, Y, Zc = to_ecef.transform(LON.ravel(), LAT.ravel(), Z.ravel())
            P4 = np.vstack([R_ch.T @ (np.stack([X, Y, Zc]) - T_ch[:, None]) / S_ch,
                            np.ones(X.size)])

            out = np.zeros(X.size, np.float32)
            done = np.zeros(X.size, bool)
            nn = knn(np.c_[LON.ravel() * mdeg, LAT.ravel() * 110570], K)
            if nn.ndim == 1:
                nn = nn[:, None]

            for kk in range(nn.shape[1]):
                todo = np.where(~done)[0]
                if todo.size == 0:
                    break
                order = np.argsort(nn[todo, kk], kind="stable")
                todo = todo[order]
                ci = nn[todo, kk]
                bounds = np.searchsorted(ci, np.arange(len(lab) + 1))
                for i in range(len(lab)):
                    sl = todo[bounds[i]:bounds[i + 1]]
                    if sl.size == 0:
                        continue
                    Pc = Minv[i] @ P4[:, sl]
                    z = Pc[2]
                    m = z > 0
                    if not m.any():
                        continue
                    u = F * Pc[0] / z + IW / 2 + CX
                    v = F * Pc[1] / z + IH / 2 + CY
                    m &= (u >= 0) & (u < IW) & (v >= 0) & (v < IH)
                    if not m.any():
                        continue
                    q = Hinv @ np.vstack([u[m], v[m], np.ones(m.sum())])
                    tu, tv = q[0] / q[2], q[1] / q[2]
                    if args.bu_tung_anh:
                        b = bu_anh.get(lab[i])
                        if b is not None:
                            tu = tu + b[0]
                            tv = tv + b[1]
                    T = thermal(i)
                    ok = (tu >= 0) & (tu < T.shape[1] - 1) & (tv >= 0) & (tv < T.shape[0] - 1)
                    if not ok.any():
                        continue
                    idx = sl[m][ok]
                    xu, yv = tu[ok], tv[ok]
                    x0 = xu.astype(np.int32); y0 = yv.astype(np.int32)
                    fx = (xu - x0).astype(np.float32); fy = (yv - y0).astype(np.float32)
                    out[idx] = (T[y0, x0] * (1 - fx) * (1 - fy) + T[y0, x0 + 1] * fx * (1 - fy)
                                + T[y0 + 1, x0] * (1 - fx) * fy + T[y0 + 1, x0 + 1] * fx * fy)
                    done[idx] = True

            dst.write(np.maximum(out.reshape(th_, tw_), 1).astype(np.uint8)
                      * done.reshape(th_, tw_), 1,
                      window=rasterio.windows.Window(tx, ty, tw_, th_))
            filled += done.sum(); total += done.size
            print(f"   ô ({tx:5d},{ty:5d})  phủ {100*done.mean():5.1f}%   "
                  f"tổng {100*filled/total:5.1f}%   {time.time()-t0:6.0f}s")

print(f"\n[XONG] phủ {100*filled/total:.1f}% diện tích, {time.time()-t0:.0f}s")
print(f"-> {args.out}")

with rasterio.open(args.out) as src:
    sc = min(1.0, 1800 / src.width)
    im = src.read(1, out_shape=(int(src.height * sc), int(src.width * sc)))
col = cv2.applyColorMap(cv2.normalize(im, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                        cv2.COLORMAP_INFERNO)
col[im == 0] = (28, 28, 28)
p = os.path.join(BASE, "ket_qua/kiem_tra_warp", "ortho_nhiet_tu_lam.jpg")
cv2.imwrite(p, col, [cv2.IMWRITE_JPEG_QUALITY, 90])
print(f"-> {p}")
