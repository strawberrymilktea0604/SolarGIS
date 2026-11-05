#!/usr/bin/env python3
"""
Dò ĐỘ TRỄ CHỤP giữa cảm biến nhiệt và cảm biến RGB, hoàn toàn tự động.

Vì sao cần: ortho nhiệt tự dựng lệch ~20 cm so với ortho màu. Nguyên nhân số một
là hai cảm biến không bấm máy cùng lúc — drone bay ~5 m/s nên trễ 40 ms đã đủ
đẩy lệch 20 cm. EXIF chỉ ghi tới giây và hai ảnh trùng giây, nên không đọc được
độ trễ từ metadata; phải ước lượng từ chính hình ảnh.

Nguyên lý: tư thế trong cameras.xml là tư thế của ảnh RGB (Metashape dựng từ RGB).
Nếu cảm biến nhiệt bấm sau RGB một khoảng dt, thì lúc nó chụp, drone đã bay tiếp.
Tư thế đúng của ảnh nhiệt là tư thế NỘI SUY dọc quỹ đạo, dịch đi dt giây.
Thử nhiều dt, với mỗi dt dựng một mảnh ortho nhiệt nhỏ rồi đo độ khớp với ortho
màu; dt cho độ khớp cao nhất là độ trễ thật.

Đo độ khớp bằng tương quan trên ẢNH GRADIENT, không phải trên cường độ: nhiệt và
màu là hai phổ khác nhau nên vùng sáng/tối không tương ứng, nhưng CẠNH tấm pin thì
hiện rõ ở cả hai. Đây cũng chính là cách sẽ dùng để hiệu chuẩn H tự động sau này.

    python ma/do_tre_chup.py                      # quét mặc định -100..200 ms
    python ma/do_tre_chup.py --min -50 --max 150 --buoc 10
    python ma/do_tre_chup.py --so-vung 12         # nhiều vùng hơn -> chắc hơn, chậm hơn
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

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")

ap = argparse.ArgumentParser()
ap.add_argument("--min", type=float, default=-100.0, help="trễ nhỏ nhất (ms)")
ap.add_argument("--max", type=float, default=200.0, help="trễ lớn nhất (ms)")
ap.add_argument("--buoc", type=float, default=20.0, help="bước quét thô (ms)")
ap.add_argument("--so-vung", type=int, default=8, dest="so_vung",
                help="số vùng lấy mẫu rải khắp nhà máy")
ap.add_argument("--canh-vung", type=int, default=192, dest="canh_vung",
                help="cạnh mỗi vùng (px ortho nhiệt); 192 px ~ 5,5 m, vừa gọn "
                     "trong vùng phủ ~15x12 m của một ảnh nhiệt")
ap.add_argument("--step", type=float, default=3.0,
                help="thu nhỏ so với ortho màu (3 -> ~2,9 cm/px, bằng GSD nhiệt)")
ap.add_argument("--H", default=os.path.join(BASE, "ket_qua/thermal_to_rgb.json"))
ap.add_argument("--polygon", default=os.path.join(BASE, "ket_qua/tam_pin_polygon.json"),
                help="polygon tấm pin ở toạ độ ortho màu, dùng làm mặt nạ viền")
ap.add_argument("--day-vien", type=int, default=7, dest="day_vien",
                help="nới viền tấm pin ra bao nhiêu px trước khi đo")
ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/do_tre_chup.json"))
ap.add_argument("--soi", action="store_true", help="chỉ soi một vùng rồi thoát")
args = ap.parse_args()

t0 = time.time()
H = np.array(json.load(open(args.H, encoding="utf-8"))["H_thermal_to_rgb"])
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
ks = sorted(cams, key=int)

# ------------------------------------------------- 2. loại ảnh ở đoạn quay đầu
Cch = {k: cams[k][:3, 3] for k in ks}
spd = {}
for i in range(1, len(ks) - 1):
    spd[ks[i]] = np.linalg.norm(Cch[ks[i + 1]] - Cch[ks[i - 1]]) * S_ch / 2
med = np.median(list(spd.values()))
good = set(k for k in ks if spd.get(k, med) > 0.6 * med)
print(f"[LỌC] {len(good)}/{len(cams)} ảnh bay đều")

# --------------------------------------------- 3. nhịp chụp -> đổi ms sang mét
# Không có subsecond trong EXIF, nên suy nhịp chụp từ khoảng cách bay đều:
# giả định nhịp 1 ảnh/giây là chuẩn cho DJI ở chế độ này. Nếu sai, dt tìm được
# vẫn đúng theo ĐƠN VỊ MÉT — chỉ nhãn "ms" bị co giãn theo. Ta báo cả hai.
dts = [np.linalg.norm((Cch[ks[i + 1]] - Cch[ks[i]])) * S_ch
       for i in range(len(ks) - 1) if ks[i] in good and ks[i + 1] in good]
buoc_bay = float(np.median(dts))
NHIP_HZ = 1.0
toc_do = buoc_bay * NHIP_HZ
print(f"[BAY]  bước bay {buoc_bay:.2f} m/ảnh, giả định nhịp {NHIP_HZ:g} Hz "
      f"-> tốc độ {toc_do:.2f} m/s")


def tu_the_tre(k, dt_giay):
    """Tư thế của ảnh nhiệt nếu nó bấm máy trễ dt_giay so với ảnh RGB cùng nhãn.

    Nội suy tuyến tính tâm chụp dọc quỹ đạo sang ảnh kế tiếp (hoặc kề trước nếu
    dt âm). Hướng camera giữ nguyên: trong 40 ms drone gần như không đổi hướng,
    và sai số hướng bậc hai nhỏ hơn nhiều so với sai số tịnh tiến bậc một.
    """
    M = cams[k].copy()
    i = ks.index(k)
    j = i + 1 if dt_giay >= 0 else i - 1
    if j < 0 or j >= len(ks):
        return None
    buoc = cams[ks[j]][:3, 3] - cams[k][:3, 3]
    M[:3, 3] = cams[k][:3, 3] + buoc * abs(dt_giay) * NHIP_HZ
    return M


# ---------------------------------------------------------------- 4. raster
ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
dsm = rasterio.open(os.path.join(EXP, "dsm.tif"))
DSM = dsm.read(1)
zmed = float(np.median(DSM[DSM != dsm.nodata]))
mdeg = 111320 * np.cos(np.radians(11.424))

to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
to_wgs = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)

lab, nad, Minv0 = [], [], []
for k in sorted(good, key=int):
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
    lab.append(k); nad.append((glon, glat))
nad = np.array(nad)

from scipy.spatial import cKDTree
tree = cKDTree(np.c_[nad[:, 0] * mdeg, nad[:, 1] * 110570])

rows_csv = {r["seq"]: r for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}
cache = {}


def anh_nhiet(k):
    if k not in cache:
        if len(cache) > 40:
            cache.pop(next(iter(cache)))
        cache[k] = cv2.imread(rows_csv[k]["path_thermal"],
                              cv2.IMREAD_GRAYSCALE).astype(np.float32)
    return cache[k]


# ------------------------------------------- 5. chọn vùng lấy mẫu giàu chi tiết
# Vùng tốt là vùng có nhiều cạnh tấm pin. Vùng trống (đất, cỏ) không có tín hiệu
# để căn, đưa vào chỉ làm loãng kết quả.
OT_full = ortho.transform * rasterio.Affine.scale(args.step, args.step)
OW = int(ortho.width / args.step)
OH = int(ortho.height / args.step)
print(f"[LƯỚI] ortho nhiệt sẽ là {OW} x {OH} px, GSD {abs(OT_full.a)*mdeg*100:.2f} cm/px")

thu = ortho.read(1, out_shape=(max(1, OH // 8), max(1, OW // 8))).astype(np.float32)
gx = cv2.Sobel(thu, cv2.CV_32F, 1, 0, ksize=3)
gy = cv2.Sobel(thu, cv2.CV_32F, 0, 1, ksize=3)
manh = cv2.boxFilter(np.abs(gx) + np.abs(gy), -1, (args.canh_vung // 8,) * 2)

# Ảnh nhiệt phủ mặt đất hẹp hơn ảnh RGB nhiều, nên ortho nhiệt chỉ có dữ liệu ở
# nơi thực sự có tâm chụp gần. Cấm mọi vùng xa tâm chụp, nếu không sẽ chọn phải
# vùng giàu cạnh trên ortho màu mà ortho nhiệt hoàn toàn trống.
yy, xx = np.mgrid[0:manh.shape[0], 0:manh.shape[1]]
LONm = OT_full.c + OT_full.a * (xx * 8 + 4)
LATm = OT_full.f + OT_full.e * (yy * 8 + 4)
dmin = tree.query(np.c_[LONm.ravel() * mdeg, LATm.ravel() * 110570], k=1)[0]
dmin = dmin.reshape(manh.shape)
BAN_KINH_M = 7.0          # nửa vùng phủ ảnh nhiệt dưới đất (~15 x 12 m)
manh[dmin > BAN_KINH_M] = -1
print(f"[PHỦ]  {100*(dmin <= BAN_KINH_M).mean():.1f}% lưới nằm trong tầm ảnh nhiệt")

vung = []
manh_tmp = manh.copy()
nua = args.canh_vung // 16
for _ in range(args.so_vung):
    iy, ix = np.unravel_index(np.argmax(manh_tmp), manh_tmp.shape)
    if manh_tmp[iy, ix] < 0:
        break
    cx_ = int(ix * 8) - args.canh_vung // 2
    cy_ = int(iy * 8) - args.canh_vung // 2
    cx_ = int(np.clip(cx_, 0, OW - args.canh_vung))
    cy_ = int(np.clip(cy_, 0, OH - args.canh_vung))
    vung.append((cx_, cy_))
    # cấm vùng quanh điểm vừa chọn để các vùng rải đều, không dồn một chỗ
    y0, y1 = max(0, iy - nua * 3), min(manh_tmp.shape[0], iy + nua * 3)
    x0, x1 = max(0, ix - nua * 3), min(manh_tmp.shape[1], ix + nua * 3)
    manh_tmp[y0:y1, x0:x1] = -1
if not vung:
    raise SystemExit("Không vùng nào vừa giàu cạnh vừa trong tầm ảnh nhiệt")
print(f"[VÙNG] chọn {len(vung)} vùng {args.canh_vung}x{args.canh_vung} px giàu cạnh")


def dung_manh_nhiet(cx_, cy_, dt_giay):
    """Dựng một mảnh ortho nhiệt tại (cx_, cy_) với giả định trễ dt_giay."""
    n = args.canh_vung
    cc, rr = np.meshgrid(np.arange(cx_, cx_ + n) + .5, np.arange(cy_, cy_ + n) + .5)
    LON = OT_full.c + OT_full.a * cc
    LAT = OT_full.f + OT_full.e * rr

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
    nn = tree.query(np.c_[LON.ravel() * mdeg, LAT.ravel() * 110570],
                    k=min(24, len(lab)))[1]
    if nn.ndim == 1:
        nn = nn[:, None]

    for kk in range(nn.shape[1]):
        todo = np.where(~done)[0]
        if todo.size == 0:
            break
        ci = nn[todo, kk]
        for i in np.unique(ci):
            sl = todo[ci == i]
            M = tu_the_tre(lab[i], dt_giay)
            if M is None:
                continue
            Pc = np.linalg.inv(M) @ P4[:, sl]
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
            T = anh_nhiet(lab[i])
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

    return out.reshape(n, n), done.reshape(n, n)


def do_khop(nhiet, mask, mau, trong_so=None):
    """Độ khớp giữa mảnh nhiệt và mảnh màu, bằng THÔNG TIN TƯƠNG HỖ.

    Vì sao không dùng tương quan gradient: ảnh nhiệt tương phản thấp, chuẩn hoá
    xong thì nhiễu cảm biến bị khuếch đại thành "cạnh" giả phủ kín mặt tấm pin
    (thấy rõ ở kiem_tra_warp/do_tre_chup.jpg bản đầu). Tương quan khi đó đo nhiễu
    chứ không đo cấu trúc, cho ra giá trị quanh 0 và âm.

    Thông tin tương hỗ là chuẩn mực cho ghép ảnh khác phổ: nó chỉ hỏi "biết độ
    sáng bên này thì đoán được độ sáng bên kia bao nhiêu", không đòi hai ảnh cùng
    cực tính hay cùng thang đo. Lọc trung vị trước để dập nhiễu muối tiêu của cảm
    biến nhiệt mà vẫn giữ nguyên biên tấm pin.
    """
    if mask.sum() < mask.size * 0.6:
        return None
    m = mask.copy()
    m[:4] = m[-4:] = False
    m[:, :4] = m[:, -4:] = False
    if trong_so is not None:
        m &= trong_so
    if m.sum() < 500:
        return None

    a = cv2.medianBlur(cv2.normalize(nhiet, None, 0, 255, cv2.NORM_MINMAX,
                                     dtype=cv2.CV_8U), 5)
    b = cv2.normalize(mau, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    # bỏ nền sáng biến thiên chậm (chênh nhiệt toàn cục, bóng mây) để còn cấu trúc tấm
    a = a.astype(np.float32) - cv2.GaussianBlur(a.astype(np.float32), (0, 0), 12) + 128
    b = b.astype(np.float32) - cv2.GaussianBlur(b.astype(np.float32), (0, 0), 12) + 128

    NB = 32
    x = np.clip(a[m] / 256 * NB, 0, NB - 1).astype(np.int32)
    y = np.clip(b[m] / 256 * NB, 0, NB - 1).astype(np.int32)
    hist = np.bincount(x * NB + y, minlength=NB * NB).reshape(NB, NB).astype(np.float64)
    hist /= hist.sum()
    px, py = hist.sum(1), hist.sum(0)
    nz = hist > 0
    Hxy = -(hist[nz] * np.log(hist[nz])).sum()
    Hx = -(px[px > 0] * np.log(px[px > 0])).sum()
    Hy = -(py[py > 0] * np.log(py[py > 0])).sum()
    if Hx + Hy < 1e-9:
        return None
    # chuẩn hoá về [0,1] để các vùng giàu chi tiết khác nhau vẫn so sánh được
    return float(2 * (Hx + Hy - Hxy) / (Hx + Hy))


if args.soi:
    cx_, cy_ = vung[0]
    print(f"[SOI]  vùng {vung[0]}, lưới ortho nhiệt {OW}x{OH}")
    nhiet, mask = dung_manh_nhiet(cx_, cy_, 0.0)
    print(f"[SOI]  mask phủ {100*mask.mean():.1f}%   giá trị nhiệt max {nhiet.max():.0f}")
    n = args.canh_vung
    cc, rr = np.meshgrid(np.arange(cx_, cx_ + n) + .5, np.arange(cy_, cy_ + n) + .5)
    LON = OT_full.c + OT_full.a * cc
    LAT = OT_full.f + OT_full.e * rr
    print(f"[SOI]  lon {LON.min():.6f}..{LON.max():.6f}  lat {LAT.min():.6f}..{LAT.max():.6f}")
    print(f"[SOI]  tâm chụp: lon {nad[:,0].min():.6f}..{nad[:,0].max():.6f}  "
          f"lat {nad[:,1].min():.6f}..{nad[:,1].max():.6f}")
    d, i2 = tree.query([[LON.mean() * mdeg, LAT.mean() * 110570]], k=1)
    print(f"[SOI]  ảnh gần nhất cách {d[0]:.1f} m, nhãn {lab[int(i2[0])]}")

    w = rasterio.windows.Window(cx_ * args.step, cy_ * args.step,
                                args.canh_vung * args.step, args.canh_vung * args.step)
    mau_ = ortho.read(1, window=w,
                      out_shape=(args.canh_vung, args.canh_vung)).astype(np.float32)
    print(f"[SOI]  nhiệt: min {nhiet[mask].min():.0f} max {nhiet[mask].max():.0f} "
          f"std {nhiet[mask].std():.1f}")
    print(f"[SOI]  màu  : min {mau_.min():.0f} max {mau_.max():.0f} std {mau_.std():.1f}")

    def hien(x, ten):
        v = cv2.normalize(x, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        v = cv2.resize(v, (384, 384), interpolation=cv2.INTER_NEAREST)
        v = cv2.cvtColor(v, cv2.COLOR_GRAY2BGR)
        cv2.putText(v, ten, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 255, 255), 1)
        return v

    a8 = cv2.medianBlur(cv2.normalize(nhiet, None, 0, 255, cv2.NORM_MINMAX,
                                      dtype=cv2.CV_8U), 5).astype(np.float32)
    b8 = cv2.normalize(mau_, None, 0, 255, cv2.NORM_MINMAX,
                       dtype=cv2.CV_8U).astype(np.float32)
    ah = a8 - cv2.GaussianBlur(a8, (0, 0), 12)
    bh = b8 - cv2.GaussianBlur(b8, (0, 0), 12)
    so = np.hstack([hien(nhiet, "NHIET goc"), hien(mau_, "MAU goc"),
                    hien(ah, "NHIET bo nen"), hien(bh, "MAU bo nen")])
    p = os.path.join(BASE, "ket_qua/kiem_tra_warp", "soi_manh_tre.jpg")
    cv2.imwrite(p, so, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"-> {p}")
    raise SystemExit(0)

# ------------------------------------------------- 6. đọc sẵn mảnh ortho MÀU
# Kèm MẶT NẠ VIỀN TẤM PIN. Vì sao cần: soi kiem_tra_warp/soi_manh_tre.jpg thấy rõ
# mặt tấm pin trong ảnh nhiệt PHẲNG LÌ (không có lưới cell như ảnh màu), còn quanh
# tấm là cỏ/đất nhiễu lốm đốm chiếm quá nửa diện tích. Tín hiệu chung giữa hai phổ
# chỉ nằm ở ĐÚNG VIỀN TẤM. Đo trên toàn mảnh là pha loãng tín hiệu đó đi hàng chục
# lần — đó là lý do hai thước đo trước đều chỉ đọc ra nhiễu.
mau_vung, vien_vung = [], []
poly_all = None
if os.path.exists(args.polygon):
    poly_all = json.load(open(args.polygon, encoding="utf-8"))
    print(f"[VIỀN] đọc {len(poly_all)} polygon tấm pin -> chỉ đo độ khớp ở viền tấm")
else:
    print(f"[VIỀN] không thấy {args.polygon} -> đo trên toàn mảnh (kém nhạy hơn nhiều)")

for (cx_, cy_) in vung:
    w = rasterio.windows.Window(cx_ * args.step, cy_ * args.step,
                                args.canh_vung * args.step, args.canh_vung * args.step)
    im = ortho.read(1, window=w,
                    out_shape=(args.canh_vung, args.canh_vung)).astype(np.float32)
    mau_vung.append(im)

    if poly_all is None:
        vien_vung.append(None)
        continue
    # polygon ở toạ độ ortho MÀU -> đổi sang toạ độ mảnh (đã chia args.step)
    x0f, y0f = cx_ * args.step, cy_ * args.step
    x1f = x0f + args.canh_vung * args.step
    y1f = y0f + args.canh_vung * args.step
    ve = np.zeros((args.canh_vung, args.canh_vung), np.uint8)
    for poly in poly_all:
        p = np.array(poly)
        if p[:, 0].max() < x0f or p[:, 0].min() > x1f or \
           p[:, 1].max() < y0f or p[:, 1].min() > y1f:
            continue
        q = np.round((p - [x0f, y0f]) / args.step).astype(np.int32)
        cv2.polylines(ve, [q], True, 255, 1)
    # nới viền ra vài pixel: độ trễ cần dò tương ứng vài px, viền 1 px sẽ trượt
    # khỏi nhau hoàn toàn và phép đo mất tín hiệu thay vì giảm dần.
    ve = cv2.dilate(ve, np.ones((args.day_vien, args.day_vien), np.uint8))
    vien_vung.append(ve > 0)

if poly_all is not None:
    tl = [v.mean() for v in vien_vung if v is not None]
    print(f"[VIỀN] viền chiếm {100*np.mean(tl):.1f}% diện tích mảnh "
          f"(dày {args.day_vien} px)")
    du = [i for i, v in enumerate(vien_vung) if v is not None and v.sum() >= 500]
    if len(du) < len(vung):
        print(f"[VIỀN] bỏ {len(vung)-len(du)} vùng ít viền quá")
        vung = [vung[i] for i in du]
        mau_vung = [mau_vung[i] for i in du]
        vien_vung = [vien_vung[i] for i in du]
    if not vung:
        raise SystemExit("Không vùng nào có đủ viền tấm pin để đo")

# ---------------------------------------------------------------- 7. quét trễ
def diem_cua_tre(dt_ms):
    dt = dt_ms / 1000.0
    ds = []
    for (cx_, cy_), mau, vien in zip(vung, mau_vung, vien_vung):
        nhiet, mask = dung_manh_nhiet(cx_, cy_, dt)
        d = do_khop(nhiet, mask, mau, vien)
        if d is not None:
            ds.append(d)
    return (float(np.median(ds)), len(ds)) if ds else (float("nan"), 0)


# ------------------------------------- 7a. kiểm chứng thước đo trước khi tin nó
# Nếu thước đo có tác dụng, dịch mảnh nhiệt đi vài pixel phải làm điểm khớp TỤT rõ.
# Không có bước này thì rất dễ đọc nhiễu thành tín hiệu — đúng lỗi của bản đầu.
print("\n[KIỂM CHỨNG THƯỚC ĐO] dịch thử mảnh nhiệt, điểm khớp phải tụt")
cx0, cy0 = vung[0]
n0_, m0_ = dung_manh_nhiet(cx0, cy0, 0.0)
mau0_, vien0_ = mau_vung[0], vien_vung[0]
kc = []
for dx in (0, 2, 4, 8, 16):
    nn_ = np.roll(n0_, dx, axis=1)
    mm_ = np.roll(m0_, dx, axis=1)
    d_ = do_khop(nn_, mm_, mau0_, vien0_)
    kc.append((dx, d_))
    print(f"   dịch {dx:2d} px ({dx*2.87:5.1f} cm)  ->  khớp {d_:.4f}"
          if d_ is not None else f"   dịch {dx:2d} px -> thiếu dữ liệu")
hop = [d for _, d in kc if d is not None]
if len(hop) >= 2 and hop[0] - min(hop) < 0.01:
    print("   [CẢNH BÁO] điểm khớp gần như không đổi khi dịch — thước đo chưa nhạy,")
    print("              kết quả trễ bên dưới KHÔNG đáng tin.")
else:
    print(f"   thước đo nhạy: chênh {hop[0]-min(hop):.4f} giữa khớp đúng và lệch nhất")

print(f"\n[QUÉT THÔ] {args.min:g} .. {args.max:g} ms, bước {args.buoc:g} ms")
tho = []
for dt_ms in np.arange(args.min, args.max + 1e-9, args.buoc):
    d, n = diem_cua_tre(dt_ms)
    tho.append((float(dt_ms), d, n))
    print(f"   trễ {dt_ms:7.1f} ms  ->  khớp {d:.4f}  ({n} vùng)  {time.time()-t0:5.0f}s")

hop_le = [t for t in tho if np.isfinite(t[1])]
if not hop_le:
    raise SystemExit("Không vùng nào đủ dữ liệu — thử tăng --canh-vung hoặc --so-vung")
tot = max(hop_le, key=lambda t: t[1])
print(f"\n[THÔ]  tốt nhất {tot[0]:.1f} ms (khớp {tot[1]:.4f})")

# quét tinh quanh đỉnh
b2 = args.buoc / 5.0
print(f"\n[QUÉT TINH] quanh {tot[0]:.1f} ms, bước {b2:g} ms")
tinh = []
for dt_ms in np.arange(tot[0] - args.buoc, tot[0] + args.buoc + 1e-9, b2):
    d, n = diem_cua_tre(dt_ms)
    tinh.append((float(dt_ms), d, n))
    print(f"   trễ {dt_ms:7.1f} ms  ->  khớp {d:.4f}  ({n} vùng)  {time.time()-t0:5.0f}s")

hop_le2 = [t for t in tinh if np.isfinite(t[1])]
best = max(hop_le2, key=lambda t: t[1])

# đỉnh parabol qua 3 điểm quanh cực đại -> chính xác dưới mức bước quét
i = hop_le2.index(best)
dinh = best[0]
if 0 < i < len(hop_le2) - 1:
    y0_, y1_, y2_ = hop_le2[i - 1][1], hop_le2[i][1], hop_le2[i + 1][1]
    den = y0_ - 2 * y1_ + y2_
    if abs(den) > 1e-12:
        dinh = best[0] + b2 * 0.5 * (y0_ - y2_) / den

goc = next((t for t in tho if abs(t[0]) < 1e-9), None)
khop_goc = goc[1] if goc else diem_cua_tre(0.0)[0]
lech_m = toc_do * dinh / 1000.0

# ------------------------------------------------- có thật là đỉnh không?
# Đỉnh thật thì đường cong MƯỢT. Nhiễu thì răng cưa. So đạo hàm bậc hai trung
# bình với biên độ: dưới ~10% là đỉnh đáng tin, trên ~20% là đang đọc nhiễu.
yv = np.array([t[1] for t in hop_le2])
bien_do = float(yv.max() - yv.min())
rang_cua = float(np.abs(np.diff(yv, 2)).mean()) if len(yv) >= 3 else float("nan")
ti_le_nhieu = rang_cua / bien_do if bien_do > 1e-9 else float("inf")
dang_tin = (ti_le_nhieu < 0.10) and (bien_do > 5 * rang_cua)

print(f"\n{'='*64}")
if dang_tin:
    print(f"[KẾT QUẢ] độ trễ chụp = {dinh:.1f} ms")
    print(f"          tương ứng lệch mặt đất {lech_m*100:.1f} cm ở tốc độ {toc_do:.2f} m/s")
    print(f"          độ khớp: {khop_goc:.4f} (không bù)  ->  {best[1]:.4f} (đã bù)")
    print(f"          đường cong mượt (nhiễu {100*ti_le_nhieu:.0f}% biên độ) -> đáng tin")
else:
    print(f"[KHÔNG KẾT LUẬN ĐƯỢC] đường cong không có đỉnh thật.")
    print(f"          biên độ đỉnh-đáy chỉ {bien_do:.4f}, răng cưa {rang_cua:.4f} "
          f"= {100*ti_le_nhieu:.0f}% biên độ")
    print(f"          (đỉnh thật thì đường cong mượt, răng cưa dưới ~10%)")
    print(f"          Con số {dinh:.1f} ms bên dưới CHỈ LÀ NHIỄU — đừng dùng.")
    print(f"          Nghĩa là: trong dữ liệu này, trễ chụp KHÔNG phải nguyên nhân")
    print(f"          chính gây lệch ortho. Phải tìm nguyên nhân khác.")
print(f"{'='*64}")

json.dump({
    "dang_tin": bool(dang_tin),
    "bien_do_dinh_day": bien_do,
    "rang_cua": rang_cua,
    "ti_le_nhieu": ti_le_nhieu,
    "do_tre_ms": dinh,
    "lech_mat_dat_cm": lech_m * 100,
    "toc_do_bay_m_s": toc_do,
    "buoc_bay_m": buoc_bay,
    "nhip_gia_dinh_hz": NHIP_HZ,
    "khop_khong_bu": khop_goc,
    "khop_da_bu": best[1],
    "so_vung": len(vung),
    "canh_vung_px": args.canh_vung,
    "quet_tho": tho,
    "quet_tinh": tinh,
    "ghi_chu": ("Nhịp chụp giả định 1 Hz vì EXIF không có subsecond. Nếu nhịp thật "
                "khác, do_tre_ms co giãn theo tỉ lệ nhưng lech_mat_dat_cm vẫn đúng."),
}, open(args.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"-> {args.out}")

# ------------------------------------------------- 8. ảnh kiểm chứng mắt thường
cx_, cy_ = vung[0]
n0, m0 = dung_manh_nhiet(cx_, cy_, 0.0)
n1, m1 = dung_manh_nhiet(cx_, cy_, dinh / 1000.0)
mau = mau_vung[0]


def phu(nhiet, mask, mau):
    a = cv2.normalize(mau, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    out = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    e = cv2.Canny(cv2.normalize(nhiet, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                  60, 160)
    e[~mask] = 0
    out[e > 0] = (0, 255, 255)
    return out


so = np.hstack([phu(n0, m0, mau), np.full((args.canh_vung, 8, 3), 40, np.uint8),
                phu(n1, m1, mau)])
so = cv2.copyMakeBorder(so, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(40, 40, 40))
cv2.putText(so, "KHONG BU", (10, 23), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
cv2.putText(so, f"BU {dinh:.0f} ms", (args.canh_vung + 18, 23),
            cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 1)
p = os.path.join(BASE, "ket_qua/kiem_tra_warp", "do_tre_chup.jpg")
cv2.imwrite(p, so, [cv2.IMWRITE_JPEG_QUALITY, 92])
print(f"-> {p}   (cạnh vàng = ảnh nhiệt, nền xám = ảnh màu)")
