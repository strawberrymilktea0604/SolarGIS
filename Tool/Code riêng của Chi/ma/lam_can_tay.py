#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng công cụ CĂN TAY độ lệch nhiệt↔RGB cho từng ảnh, thay cho phép đo tự động.

Vì sao cần. `loc_anh_tre.py` đo `dx, dy` cho từng ảnh bằng cách chiếu viền tấm pin
(detector chạy trên ảnh RGB) sang toạ độ ảnh nhiệt qua H, rồi TRƯỢT tìm chỗ khớp
nhất trong bán kính 16 px. Phép đo đó hỏng ở hai chỗ, và cả hai đều không tự sửa
được:

  - **chạm mép** (21 ảnh): lệch thật lớn hơn bán kính trượt, thuật toán chỉ biết
    "≥ 16 px" chứ không biết bao nhiêu. Số ghi ra là số kẹp, không dùng được.
  - **do_net thấp** (16 ảnh): đỉnh khớp không nổi so với nền — ảnh không đủ cấu
    trúc để trượt. Số đo ra là nhiễu.

Còn 61 ảnh nữa nằm trong danh sách loại mà phép đo vẫn tốt. Chúng được nạp sẵn
`dx, dy` tự động làm vị trí xuất phát, người căn chỉ xác nhận hoặc nhích thêm.

Quy ước dấu — giữ ĐÚNG của `loc_anh_tre.py`, vì `ghep_ortho_nhiet.py` đọc thẳng:
viền DỰ ĐOÁN dịch đi `(dx, dy)` thì khớp viền THẬT. Nên trong công cụ này, vector
người dùng kéo viền đi CHÍNH LÀ `(dx, dy)`.

    py -3.13 ma/lam_can_tay.py                  # 90 ảnh đang bị loại
    py -3.13 ma/lam_can_tay.py --tat-ca         # cả 598 ảnh
    py -3.13 ma/lam_can_tay.py --seq 0022 0045  # chỉ vài ảnh

-> can_tay.html + nhan/cantay/<seq>.jpg
   Căn xong bấm "Tải kết quả" -> can_tay.json, rồi:
       py -3.13 ma/ghep_ortho_nhiet.py --lech-tay can_tay.json
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
TW, TH_ = 640, 512

ap = argparse.ArgumentParser()
ap.add_argument("--nhom", default="tre", choices=["kho", "tre", "loai", "tat_ca"],
                help="kho = 20 ảnh phép đo tự động bó tay (đáng làm nhất); "
                     "tre = 90 ảnh loại vì lệch (mặc định); "
                     "loai = 182 ảnh loại vì mọi lý do; tat_ca = cả 598 ảnh")
ap.add_argument("--seq", nargs="*", default=None, help="chỉ vài ảnh, theo số hiệu")
ap.add_argument("--chatluong", type=int, default=88, dest="cl")
ap.add_argument("--out", default=os.path.join(BASE, "cong_cu/can_tay.html"))
args = ap.parse_args()

t0 = time.time()
THU_MUC = os.path.join(BASE, "cong_cu/nhan", "cantay")
os.makedirs(THU_MUC, exist_ok=True)

# ------------------------------------------------------------------ 1. XML + H
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
Hinv = np.linalg.inv(np.array(json.load(
    open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"), encoding="utf-8"))["H_thermal_to_rgb"]))


def vao_anh_nhiet(M, pts):
    """ECEF -> pixel ảnh nhiệt. Bỏ qua méo ống kính, y như quet_loi_anh_le.py."""
    Cc = S_ch * (R_ch @ M[:3, 3]) + T_ch
    Rm = R_ch @ M[:3, :3]
    dv = (pts - Cc) @ Rm
    with np.errstate(invalid="ignore", divide="ignore"):
        u = dv[:, 0] / dv[:, 2] * F + IW / 2.0 + CX
        v = dv[:, 1] / dv[:, 2] * F + IH / 2.0 + CY
    w = Hinv[2, 0] * u + Hinv[2, 1] * v + Hinv[2, 2]
    return ((Hinv[0, 0] * u + Hinv[0, 1] * v + Hinv[0, 2]) / w,
            (Hinv[1, 0] * u + Hinv[1, 1] * v + Hinv[1, 2]) / w,
            dv[:, 2] > 0)


# ------------------------------------------------- 2. tấm pin -> điểm ECEF
panels = [np.array(p, np.float32) for p in
          json.load(open(os.path.join(BASE, "ket_qua/tam_pin_polygon_4lop.json")))]
ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
GSD_CM = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
# cm trên một pixel ẢNH NHIỆT: dùng để đổi dx,dy ra cm cho người căn hiểu
TI_LE = abs(np.array(json.load(open(os.path.join(BASE, "ket_qua/thermal_to_rgb.json"),
                                    encoding="utf-8"))["H_thermal_to_rgb"])[0, 0])
CM_PX_NHIET = TI_LE * GSD_CM

pv = np.concatenate(panels).astype(np.float64)
lon = ortho.transform.c + ortho.transform.a * pv[:, 0]
lat = ortho.transform.f + ortho.transform.e * pv[:, 1]
with rasterio.open(os.path.join(EXP, "dsm.tif")) as d:
    DSM = d.read(1); ND = d.nodata
    zm = float(np.median(DSM[DSM != ND]))
    rr = np.clip(((lat - d.transform.f) / d.transform.e).astype(int), 0, DSM.shape[0] - 1)
    cc = np.clip(((lon - d.transform.c) / d.transform.a).astype(int), 0, DSM.shape[1] - 1)
z = DSM[rr, cc].astype(np.float64)
z[z == ND] = zm
P = np.stack(Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
             .transform(lon, lat, z), 1)                      # (4N, 3)

# ---------------------------------------------------------- 3. chọn ảnh
d_tre = json.load(open(os.path.join(BASE, "du_lieu/anh_tre_chup_full.json"), encoding="utf-8"))
CT = {r["seq"]: r for r in d_tre["chi_tiet"]}
R_TRUOT = float(d_tre.get("ban_kinh_px", 16))
bo_tre = [str(x) for x in d_tre.get("anh_nen_loai", [])]


def kho_do(r):
    """Phép đo tự động có tin được không, và vì sao không."""
    if r is None:
        return "khong_do"
    if max(abs(r["dx"]), abs(r["dy"])) >= R_TRUOT - 0.01:
        return "cham_mep"
    if r["do_net"] < 0.5:
        return "net_thap"
    return ""


bo_rung = [str(x) for x in json.load(
    open(os.path.join(BASE, "du_lieu/anh_rung.json"), encoding="utf-8")).get("anh_nen_loai", [])]

# Ảnh phép đo tự động bó tay KHÔNG nằm gọn trong danh sách loại: 21/29 ảnh khó
# nằm ngoài `bo_tre`. Nên các nhóm dưới đây đều HỢP thêm nhóm khó vào, không thì
# sót đúng những ảnh cần tay nhất.
khon = {s for s in cams if kho_do(CT.get(s))}
if args.seq:
    muc = [s for s in args.seq if s in cams]
elif args.nhom == "kho":
    muc = sorted(khon)
elif args.nhom == "tre":
    muc = sorted(set(bo_tre) | khon)
elif args.nhom == "loai":
    muc = sorted(set(bo_tre) | set(bo_rung) | khon)
else:
    muc = sorted(cams)
# Ảnh phép đo tự động bó tay đứng trước — đó là chỗ công sức tay đáng giá nhất.
# Mấy ảnh còn lại máy đã đo tốt, người căn chỉ việc xác nhận.
muc.sort(key=lambda s: (kho_do(CT.get(s)) == "", s))
print("[ẢNH]   nhóm '%s': %d ảnh cần căn (%d ảnh phép đo tự động bó tay, xếp trước)"
      % (args.nhom, len(muc), sum(1 for s in muc if kho_do(CT.get(s)))))

# ------------------------------------------------- 4. cắt ảnh + chiếu viền
duong = {r["seq"]: r["path_thermal"] for r in csv.DictReader(
    open(os.path.join(BASE, "du_lieu/manifest_anh.csv"), encoding="utf-8-sig"))}
ANH = {}
thieu = 0
for n, seq in enumerate(muc, 1):
    p = duong.get(seq)
    im = cv2.imread(p) if p and os.path.exists(p) else None
    if im is None:
        thieu += 1
        continue
    ut, vt, truoc = vao_anh_nhiet(cams[seq], P)
    ut, vt = ut.reshape(-1, 4), vt.reshape(-1, 4)
    truoc = truoc.reshape(-1, 4).all(1)
    # giữ tấm nào có ít nhất một góc trong khung, nới 40 px để kéo vẫn còn viền
    trong = (truoc & (ut > -40).any(1) & (ut < TW + 40).any(1)
             & (vt > -40).any(1) & (vt < TH_ + 40).any(1))
    idx = np.flatnonzero(trong)
    quads = [[round(float(v), 1) for k in range(4) for v in (ut[i, k], vt[i, k])]
             for i in idx]
    cv2.imwrite(os.path.join(THU_MUC, "%s.jpg" % seq), im,
                [cv2.IMWRITE_JPEG_QUALITY, args.cl])
    r = CT.get(seq)
    ANH[seq] = {
        "quad": quads,
        # vị trí xuất phát: dùng phép đo tự động NẾU tin được, còn không thì 0
        "dx0": round(float(r["dx"]), 2) if r and not kho_do(r) else 0.0,
        "dy0": round(float(r["dy"]), 2) if r and not kho_do(r) else 0.0,
        "kho": kho_do(r),
        "lech_cm": round(float(r["lech_cm"]), 1) if r else None,
        "do_net": round(float(r["do_net"]), 2) if r else None,
        "bi_loai": seq in set(bo_tre),
    }
    if n % 20 == 0:
        print("   ...%d/%d ảnh, %.0fs" % (n, len(muc), time.time() - t0))

print("[ẢNH]   cắt xong %d ảnh (%d ảnh thiếu file), %.0fs"
      % (len(ANH), thieu, time.time() - t0))

DATA = {"anh": ANH, "thu_muc": "nhan/cantay/", "w": TW, "h": TH_,
        "cm_px": round(float(CM_PX_NHIET), 2), "ban_kinh": R_TRUOT,
        "thu_tu": [s for s in muc if s in ANH]}

HTML = open(os.path.join(BASE, "cong_cu/mau_can_tay.html"), encoding="utf-8").read()
with open(args.out, "w", encoding="utf-8") as fh:
    fh.write(HTML.replace("/*__DATA__*/null",
                          json.dumps(DATA, ensure_ascii=False, separators=(",", ":"))))
print("\n-> %s  (%.2f MB)" % (args.out, os.path.getsize(args.out) / 1e6))
print("   căn xong -> can_tay.json -> py -3.13 ma/ghep_ortho_nhiet.py --lech-tay can_tay.json")
