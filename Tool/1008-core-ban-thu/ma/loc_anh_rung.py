#!/usr/bin/env python3
"""
LOẠI ẢNH CHỤP LÚC DRONE KHÔNG BAY ĐỀU — giật, rung, phanh gấp, đang quay đầu.

Vì sao phải loại: ảnh RGB và ảnh nhiệt của CÙNG một lần bấm máy không nổ cùng lúc.
Nếu drone đang bay đều thì khoảng trễ đó chỉ dịch cảnh đi một đoạn nhỏ và đều, ma
trận H bù được. Nếu drone đang phanh gấp hay bị gió giật thì trong khoảng trễ ấy
tốc độ và tư thế đổi hẳn, cảnh trong hai ảnh lệch nhau một lượng H không tả nổi —
ghép vào ortho thì cả vùng đó đặt sai chỗ.

Cách phát hiện, chỉ đọc EXIF/XMP, KHÔNG cần mở ảnh ra tính:
ảnh DJI ZH20T ghi sẵn trong XMP tốc độ bay và tư thế thân máy tại đúng lúc bấm,
và ghi RIÊNG cho từng cảm biến. Nên với mỗi lần bấm ta có hai bản ghi ở hai thời
điểm hơi khác nhau, so ra là biết lúc đó máy có đang bay đều hay không.

Bốn dấu hiệu tính được, nhưng CHỈ HAI CÁI ĐƯỢC BẬT MẶC ĐỊNH:

  dv        | v(RGB) - v(NHIỆT) |      hai cảm biến đo được tốc độ khác nhau   [BẬT]
            ->  ĐANG TĂNG/GIẢM TỐC ngay trong lúc bấm. Dấu hiệu tốt nhất vì nó so
                hai số đo TRONG CÙNG một lần bấm, không giả định gì về nhịp chụp.
  toc_do    | v ngang | nhỏ                                                    [BẬT]
            ->  ĐANG QUAY ĐẦU hoặc treo tại chỗ, sai số dọc trục rất lớn.
  gia_toc   | v[i+1] - v[i-1] | / 2    tốc độ đổi nhanh dọc theo tuyến bay      [TẮT]
  d_goc     lệch roll+pitch giữa hai cảm biến — thân máy đang lắc              [TẮT]

####################################################################
# ĐỌC KỸ TRƯỚC KHI TIN VÀO BỘ LỌC NÀY.
#
# Đã đối chiếu với lệch ĐO ĐƯỢC THẬT trên đủ 598 ảnh (loc_anh_tre.py, chạy
# 44 phút, kết quả ở anh_tre_chup_full.json). Kết luận: KHÔNG dấu hiệu tốc
# độ nào tách được ảnh tốt/xấu theo trung vị. Cột cuối là tỉ số lệch trung
# vị nhóm-bị-loại / nhóm-giữ-lại; muốn bộ lọc có ích thì phải > 1:
#
#     dv > 1,0 m/s     loại  61 ảnh   5,19 px / 5,86 px   x0,89   NGƯỢC
#     dv > 1,5 m/s     loại  38 ảnh   4,74 px / 5,91 px   x0,80   NGƯỢC
#     toc_do < 1 m/s   loại  85 ảnh   5,12 px / 5,90 px   x0,87   NGƯỢC
#     gia_toc > 1      loại 150 ảnh                               NGƯỢC
#     d_goc > 3°       loại 176 ảnh                               NGƯỢC
#
# Bộ lọc quay đầu theo VỊ TRÍ CAMERA trong ghep_ortho_nhiet.py cũng vậy:
# loại 142 ảnh, x0,93 — cũng ngược.
#
# ĐỪNG LẶP LẠI SAI LẦM NÀY: chạy thử trên mẫu 60 ảnh thì dv trông rất tốt
# (9,28 px / 5,41 px = x1,7). Đó là ẢO, chỉ có 7 ảnh trong nhóm vượt ngưỡng.
# Quét đủ 598 ảnh thì tỉ số đảo về 0,89. Bất kỳ ngưỡng mới nào cũng phải
# kiểm trên toàn bộ, đừng chốt trên mẫu.
#
# CÁI CÓ THẬT: cả bốn dấu hiệu đều có ĐUÔI nặng hơn chứ không phải TÂM xấu
# hơn — p90 nhóm bị loại 16,2-16,3 px so với 10,9-12,0 px của nhóm giữ
# (tỉ số p90: dv 1,37 · toc_do 1,35 · gia_toc 1,46 · d_goc 1,48). Tức chúng
# bắt trúng vài ảnh rất xấu nhưng quét theo cả đống ảnh tốt. Đừng chỉ nhìn
# trung vị mà kết luận, cũng đừng chỉ nhìn p90 mà tưởng bộ lọc tốt.
#
# VÌ SAO TẮT gia_toc VÀ d_goc — không phải vì chúng "ngược" hơn hai cái kia
# (p90 của chúng còn cao hơn), mà vì KHÔNG THÊM GÌ Ở BIÊN. Sau khi đã lọc
# bằng vị trí + EXIF + phép đo trực tiếp, bật thêm chúng chỉ làm:
#     gia_toc > 1   bỏ thêm 54 ảnh   p90 9,38 -> 9,40   lớn nhất 17,52 (y nguyên)
#     d_goc   > 3   bỏ thêm 33 ảnh   p90 9,38 -> 9,42   lớn nhất 17,52 (y nguyên)
# Mất 9-14% số ảnh, không được gì. Ảnh xấu nhất chúng bắt được chỉ 11,3 px,
# trong khi ảnh còn sót tệ nhất là 17,5 px — chúng không chạm tới nó.
#
# VÌ SAO VẪN BẬT dv VÀ toc_do: chúng bắt được 3 ảnh mà cả bộ lọc vị trí lẫn
# phép đo trực tiếp đều bỏ sót — trong đó có 0001, lệch 22,63 px, ảnh xấu
# nhất còn sót lại của cả bộ. Thêm bộ lọc này thì lệch lớn nhất giảm
# 22,63 -> 17,52 px, còn trung vị và p90 gần như không đổi.
# Lý do có chỗ đó: bộ lọc theo vị trí tính tốc độ từ hai ảnh KỀ HAI BÊN nên
# ảnh ĐẦU và ẢNH CUỐI chuyến bay không có đủ hàng xóm, code mặc định coi
# chúng bay đều. EXIF đọc tốc độ ghi sẵn trong TỪNG ảnh nên không có điểm mù
# đó — 0001 và 0598 lọt lưới đúng vì lý do này.
#
# BỘ LỌC THẬT SỰ HIỆU QUẢ LÀ PHÉP ĐO TRỰC TIẾP, không phải EXIF: loc_anh_tre.py
# bắt 57 ảnh mà hai bộ lọc tốc độ bỏ sót, lệch trung vị 11,96 px. Chạy nó.
####################################################################

Đoán lý do các dấu hiệu này yếu hơn kỳ vọng: thân máy lắc thì gimbal chống rung
hấp thụ gần hết nên ảnh không lệch theo; còn gia tốc dọc tuyến tính từ hai ảnh KỀ
NHAU nên chẳng nói được gì về khoảng trễ giữa hai cảm biến trong CÙNG một lần bấm
— mà chính khoảng trễ đó mới là thứ đẩy ảnh nhiệt lệch khỏi tư thế RGB.

Kết quả cuối khi dùng cả ba bộ lọc (vị trí + EXIF + phép đo trực tiếp): giữ 396/598
ảnh, lệch trung vị 5,83 -> 5,38 px, p90 12,10 -> 9,38 px, lớn nhất 22,63 -> 17,52 px.

    python ma/loc_anh_rung.py                  # quét toàn bộ, ghi anh_rung.json
    python ma/loc_anh_rung.py --xem 0487       # xem số liệu bay của một ảnh
    python ma/loc_anh_rung.py --doi-chieu      # đối chiếu với lệch đo được thật
    python ma/loc_anh_rung.py --gia-toc 1.0    # bật lại dấu hiệu đang tắt

Kết quả ghi ra `anh_rung.json`, khoá `anh_nen_loai` — ghep_ortho_nhiet.py tự đọc.
"""
import argparse
import csv
import json
import os
import re
import time

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
TAT = float("inf")            # ngưỡng vô cực = dấu hiệu không loại ảnh nào

ap.add_argument("--dv", type=float, default=1.0,
                help="m/s — lệch tốc độ giữa hai cảm biến quá ngần này thì loại")
ap.add_argument("--toc-do-min", type=float, default=1.0, dest="toc_do_min",
                help="m/s — bay chậm hơn ngần này coi như đang quay đầu")
ap.add_argument("--gia-toc", type=float, default=TAT, dest="gia_toc",
                help="m/s^2 — TẮT mặc định (chạy ngược, xem đầu file); đặt số để bật")
ap.add_argument("--d-goc", type=float, default=TAT, dest="d_goc",
                help="độ — TẮT mặc định (chạy ngược, xem đầu file); đặt số để bật")
ap.add_argument("--manifest", default=os.path.join(BASE, "du_lieu/manifest_anh.csv"))
ap.add_argument("--cache", default=os.path.join(BASE, "du_lieu/exif_bay.json"),
                help="cache XMP đã rút, xoá đi thì đọc lại từ ảnh")
ap.add_argument("--doi-chieu", default=None, nargs="?", dest="doi_chieu",
                const=os.path.join(BASE, "du_lieu/anh_tre_chup_full.json"), metavar="FILE",
                help="đối chiếu với lệch ĐO ĐƯỢC (kết quả loc_anh_tre.py)")
ap.add_argument("--xem", default=None, metavar="SEQ", help="xem số liệu bay một ảnh")
ap.add_argument("--out", default=os.path.join(BASE, "du_lieu/anh_rung.json"))
args = ap.parse_args()

KHOA = ["FlightXSpeed", "FlightYSpeed", "FlightZSpeed",
        "FlightRollDegree", "FlightPitchDegree", "FlightYawDegree",
        "GimbalRollDegree", "GimbalPitchDegree", "GimbalYawDegree",
        "RelativeAltitude"]


# ------------------------------------------------------------------ 1. đọc XMP
def doc_xmp(path):
    """Rút các trường bay trong gói XMP mà DJI nhét ở đầu file JPEG."""
    with open(path, "rb") as f:
        b = f.read(600_000)          # gói XMP luôn nằm trong vài trăm KB đầu
    i = b.find(b"<x:xmpmeta")
    if i < 0:
        return None
    s = b[i:b.find(b"</x:xmpmeta>", i) + 12].decode("utf-8", "ignore")
    d = {}
    for k in KHOA:
        m = re.search(r'drone-dji:%s\s*=\s*"([^"]*)"' % k, s)
        if m:
            try:
                d[k] = float(m.group(1))
            except ValueError:
                pass
    return d or None


def rut_tat_ca(rows):
    out = []
    t0 = time.time()
    for n, r in enumerate(rows):
        rec = {"seq": r["seq"]}
        for tag, cot in (("rgb", "path_rgb"), ("th", "path_thermal")):
            if os.path.exists(r[cot]):
                d = doc_xmp(r[cot])
                if d:
                    rec.update({f"{tag}_{k}": v for k, v in d.items()})
        out.append(rec)
        if (n + 1) % 100 == 0:
            print(f"   đọc XMP {n+1}/{len(rows)} ảnh   {time.time()-t0:.0f}s")
    return out


rows = list(csv.DictReader(open(args.manifest, encoding="utf-8-sig")))
if os.path.exists(args.cache):
    ex = json.load(open(args.cache, encoding="utf-8"))
    if len(ex) != len(rows):                      # manifest đổi thì đọc lại
        ex = rut_tat_ca(rows)
        json.dump(ex, open(args.cache, "w", encoding="utf-8"), indent=1)
else:
    print(f"[XMP] đọc {len(rows)} cặp ảnh (lần sau lấy từ {os.path.basename(args.cache)})")
    ex = rut_tat_ca(rows)
    json.dump(ex, open(args.cache, "w", encoding="utf-8"), indent=1)

E = {r["seq"]: r for r in ex}
seqs = [s for s in sorted(E) if f"rgb_FlightXSpeed" in E[s] and f"th_FlightXSpeed" in E[s]]
if len(seqs) < len(ex):
    print(f"[XMP] {len(ex)-len(seqs)} ảnh thiếu trường bay, bỏ qua khi xét")


# ------------------------------------------------------- 2. tính bốn dấu hiệu
def vec_v(s, tag):
    r = E[s]
    return np.array([r[f"{tag}_FlightXSpeed"], r[f"{tag}_FlightYSpeed"],
                     r[f"{tag}_FlightZSpeed"]])


def vec_goc(s, tag):
    r = E[s]
    return np.array([r.get(f"{tag}_FlightRollDegree", np.nan),
                     r.get(f"{tag}_FlightPitchDegree", np.nan)])


F = {}
for i, s in enumerate(seqs):
    vr, vt = vec_v(s, "rgb"), vec_v(s, "th")
    F[s] = {
        # tốc độ ngang lúc bấm (lấy theo ảnh RGB — tư thế trong cameras.xml là của RGB)
        "toc_do": float(np.linalg.norm(vr[:2])),
        # hai cảm biến nổ lệch thời điểm; tốc độ đọc được khác nhau = đang đổi tốc
        "dv": float(np.linalg.norm(vr - vt)),
        # thân máy lắc giữa hai lần nổ (bỏ yaw: lúc quay đầu yaw đổi 180 độ, át hết)
        "d_goc": float(np.linalg.norm(vec_goc(s, "rgb") - vec_goc(s, "th"))),
    }
# gia tốc dọc tuyến: sai phân giữa hai ảnh kề. Ảnh đầu/cuối không có hàng xóm hai
# bên nên để 0 — coi như bay đều, chứ không loại oan.
for i, s in enumerate(seqs):
    if 0 < i < len(seqs) - 1:
        dv = vec_v(seqs[i + 1], "rgb") - vec_v(seqs[i - 1], "rgb")
        F[s]["gia_toc"] = float(np.linalg.norm(dv) / 2)
    else:
        F[s]["gia_toc"] = 0.0


def ly_do(s):
    """Các lý do khiến ảnh này nên loại (rỗng = ảnh tốt)."""
    f, ld = F[s], []
    if f["dv"] > args.dv:
        ld.append(f"lệch tốc độ hai cảm biến {f['dv']:.1f} m/s")
    if f["gia_toc"] > args.gia_toc:
        ld.append(f"gia tốc {f['gia_toc']:.1f} m/s²")
    if f["d_goc"] > args.d_goc:
        ld.append(f"thân lắc {f['d_goc']:.1f}°")
    if f["toc_do"] < args.toc_do_min:
        ld.append(f"bay chậm {f['toc_do']:.1f} m/s")
    return ld


# ------------------------------------------------------------ 3. xem một ảnh
if args.xem:
    s = args.xem
    if s not in F:
        raise SystemExit(f"[XEM {s}] không có dữ liệu bay")
    print(f"\n[XEM {s}]")
    for tag, ten in (("rgb", "RGB   "), ("th", "NHIỆT ")):
        v, g = vec_v(s, tag), vec_goc(s, tag)
        print(f"  {ten} v = ({v[0]:+.1f} {v[1]:+.1f} {v[2]:+.1f}) m/s"
              f"   roll {g[0]:+.2f}°  pitch {g[1]:+.2f}°")
    f = F[s]
    print(f"\n  tốc độ ngang     {f['toc_do']:6.2f} m/s   (ngưỡng > {args.toc_do_min})")
    print(f"  lệch tốc độ dv   {f['dv']:6.2f} m/s   (ngưỡng < {args.dv})")
    print(f"  gia tốc          {f['gia_toc']:6.2f} m/s²  (ngưỡng < {args.gia_toc})")
    print(f"  thân lắc d_goc   {f['d_goc']:6.2f} °     (ngưỡng < {args.d_goc})")
    ld = ly_do(s)
    print(f"\n  -> {'LOẠI: ' + '; '.join(ld) if ld else 'GIỮ (bay đều)'}")
    raise SystemExit(0)


# ------------------------------------------------------------- 4. quét toàn bộ
loai = {s: ly_do(s) for s in seqs}
xau = [s for s in seqs if loai[s]]

DAU_HIEU = (("lệch tốc độ 2 cảm biến", "dv", args.dv, ">"),
            ("tốc độ ngang", "toc_do", args.toc_do_min, "<"),
            ("gia tốc (phanh gấp)", "gia_toc", args.gia_toc, ">"),
            ("thân lắc roll+pitch", "d_goc", args.d_goc, ">"))

print(f"\n{'='*72}")
print(f"[BAY] {len(seqs)} ảnh có dữ liệu bay trong XMP")
print(f"\n  {'dấu hiệu':<26} {'p50':>7} {'p90':>7} {'p99':>7} {'max':>7}   ngưỡng")
for ten, khoa, ng, chieu in DAU_HIEU:
    x = np.array([F[s][khoa] for s in seqs])
    n = int((x > ng).sum() if chieu == ">" else (x < ng).sum())
    ket = "   TẮT" if not np.isfinite(ng) else f"{chieu}{ng:<4g} loại {n:4d} ảnh"
    print(f"  {ten:<26} {np.percentile(x,50):7.2f} {np.percentile(x,90):7.2f} "
          f"{np.percentile(x,99):7.2f} {x.max():7.2f}   {ket}")

print(f"\n  -> {len(xau)} ảnh nên loại ({100*len(xau)/len(seqs):.1f}%), "
      f"còn {len(seqs)-len(xau)} ảnh bay đều")
if xau:
    print(f"\n  Hai mươi ảnh xấu nhất (xếp theo lệch tốc độ hai cảm biến):")
    for s in sorted(xau, key=lambda s: -F[s]["dv"])[:20]:
        print(f"     {s}   {'; '.join(loai[s])}")
print(f"{'='*72}")


# ------------------------------------- 5. đối chiếu với lệch ĐO ĐƯỢC trên ảnh
tham_chieu = None
if args.doi_chieu and os.path.exists(args.doi_chieu):
    d = json.load(open(args.doi_chieu, encoding="utf-8"))
    ct = {k["seq"]: k for k in d["chi_tiet"]}
    chung = [s for s in seqs if s in ct]
    if chung:
        lech = np.array([ct[s]["lech_px"] for s in chung])
        print(f"\n[ĐỐI CHIẾU] {len(chung)} ảnh vừa có dữ liệu bay vừa đo được lệch thật"
              f"  ({os.path.basename(args.doi_chieu)})")
        # Dấu hiệu đang TẮT vẫn chấm điểm, ở ngưỡng tham khảo — để thấy nếu bật lại
        # thì nó tách đúng hay tách ngược. Đây chính là cách đã phát hiện gia_toc và
        # d_goc chạy ngược. Cột cuối là kết luận, đọc là biết nên bật hay không.
        NG_THAM_KHAO = {"gia_toc": 1.0, "d_goc": 3.0}
        print(f"\n  {'dấu hiệu':<26} {'ngưỡng':>8} {'trung vị vượt/giữ':>19}"
              f" {'p90 vượt/giữ':>17}   kết luận")
        tham_chieu = {}
        for ten, khoa, ng, chieu in DAU_HIEU:
            bat = np.isfinite(ng)
            if not bat:
                ng = NG_THAM_KHAO.get(khoa, float(np.percentile(
                    [F[s][khoa] for s in seqs], 90)))
            x = np.array([F[s][khoa] for s in chung])
            r = float(np.corrcoef(x, lech)[0, 1]) if x.std() > 0 else float("nan")
            m = x > ng if chieu == ">" else x < ng
            if not (m.any() and (~m).any()):
                print(f"  {ten:<26} {ng:8.2f}   không đủ ảnh để xét")
                continue
            a, b = float(np.median(lech[m])), float(np.median(lech[~m]))
            pa = float(np.percentile(lech[m], 90))
            pb = float(np.percentile(lech[~m], 90))
            # Tâm và đuôi có thể nói ngược nhau, và ở bộ dữ liệu này đúng là vậy:
            # dấu hiệu tốc độ bắt trúng vài ảnh rất xấu (đuôi) nhưng quét theo cả
            # đống ảnh tốt (tâm). Phải in cả hai, chỉ nhìn trung vị là kết luận sai.
            if a > b:
                kl = f"tách ĐÚNG (tâm x{a/b:.2f})"
            elif pa > pb * 1.1:
                kl = f"tâm NGƯỢC nhưng ĐUÔI đúng (p90 x{pa/pb:.2f}) — bắt được ảnh xấu hiếm"
            else:
                kl = f"tách NGƯỢC (tâm x{a/b:.2f}, đuôi x{pa/pb:.2f})"
            if not bat:
                kl += "  [đang tắt]"
            tham_chieu[khoa] = {"nguong": ng, "dang_bat": bool(bat), "tuong_quan": r,
                                "so_anh_vuot": int(m.sum()), "ket_luan": kl,
                                "lech_tv_nhom_vuot_px": a, "lech_tv_nhom_con_lai_px": b,
                                "lech_p90_nhom_vuot_px": pa, "lech_p90_nhom_con_lai_px": pb}
            print(f"  {ten:<26} {ng:8.2f} {a:8.2f} /{b:7.2f} px "
                  f"{pa:7.2f} /{pb:7.2f} px   {kl}")
        m_bo = np.array([bool(loai[s]) for s in chung])
        if m_bo.any() and (~m_bo).any():
            bat = [t for t, k, n, _ in DAU_HIEU if np.isfinite(n)]
            print(f"\n  Gộp các dấu hiệu ĐANG BẬT ({', '.join(bat)}): "
                  f"loại {m_bo.sum()}/{len(chung)} ảnh")
            print(f"     lệch trung vị nhóm BỊ LOẠI  {np.median(lech[m_bo]):5.2f} px")
            print(f"     lệch trung vị nhóm GIỮ LẠI  {np.median(lech[~m_bo]):5.2f} px")
            print(f"     lệch p90 nếu giữ tất cả     {np.percentile(lech,90):5.2f} px")
            print(f"     lệch p90 sau khi loại       {np.percentile(lech[~m_bo],90):5.2f} px")
            tham_chieu["gop"] = {
                "so_anh_loai": int(m_bo.sum()), "so_anh_doi_chieu": len(chung),
                "lech_tv_nhom_loai_px": float(np.median(lech[m_bo])),
                "lech_tv_nhom_giu_px": float(np.median(lech[~m_bo])),
                "lech_p90_giu_tat_ca_px": float(np.percentile(lech, 90)),
                "lech_p90_sau_loai_px": float(np.percentile(lech[~m_bo], 90))}
elif args.doi_chieu:
    print(f"\n[ĐỐI CHIẾU] không thấy {args.doi_chieu} — chạy loc_anh_tre.py trước")

json.dump({
    "nguong": {"dv_m_s": args.dv, "gia_toc_m_s2": args.gia_toc,
               "d_goc_do": args.d_goc, "toc_do_min_m_s": args.toc_do_min},
    "so_anh_xet": len(seqs),
    "so_anh_loai": len(xau),
    "anh_nen_loai": sorted(xau),
    "ly_do": {s: loai[s] for s in sorted(xau)},
    "doi_chieu_lech_do_duoc": tham_chieu,
    "chi_tiet": {s: F[s] for s in seqs},
    "ghi_chu": ("Dấu hiệu rút từ XMP drone-dji của CẢ ảnh RGB lẫn ảnh nhiệt. Hai cảm "
                "biến không nổ cùng lúc nên khi drone đổi tốc/lắc thì hai bản ghi khác "
                "nhau — đó là dv và d_goc. gia_toc lấy sai phân dọc tuyến bay, bắt case "
                "phanh gấp. toc_do nhỏ là đoạn quay đầu. anh_nen_loai đưa vào "
                "ghep_ortho_nhiet.py để bỏ khi dựng ortho."),
}, open(args.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"\n-> {args.out}")
