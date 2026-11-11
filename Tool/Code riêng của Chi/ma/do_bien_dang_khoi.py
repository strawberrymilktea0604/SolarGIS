#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Đo biến dạng khối ảnh: so tâm chụp đã bình sai với chính toạ độ RTK đã nạp vào.

Phép kiểm này **không tốn gì** — cả hai vế đều nằm sẵn trong `cameras.xml`:

- `<camera><transform>` : tâm chụp **sau bình sai**, trong hệ chunk.
- `<camera><reference>` : toạ độ **RTK quan trắc** (lat/lon/alt), tức số liệu đầu vào.
- `<chunk><transform>`  : phép đưa hệ chunk về ECEF (rotation · scale · translation).

Nếu bình sai tin RTK thì hai vế phải trùng nhau ở cỡ centimet. Ở khối này chúng lệch
**cỡ mét**, vì `accuracy_cameras = 10` (mét) được áp cho toạ độ RTK có std ngang 0,83 cm —
tức bình sai được phép bỏ qua RTK, và nó đã bỏ qua.

Script tách lệch đó thành ba tầng để biết nó có hại hay không:

1. **Dịch cứng** — vô hại cho việc gán vết lỗi về mã tấm, vì DSM, ortho và đa giác tấm
   đều sinh ra từ cùng khối này nên cùng dịch theo.
2. **Helmert 7 tham số** (thêm xoay + tỉ lệ) — phần tỉ lệ dư báo hiệu khối bị co giãn.
3. **Vòm bậc hai theo bán kính** — chữ ký kinh điển của lưới đơn nadir thiếu ràng buộc.
   Đây là phần **có hại**: nó bẻ cong hình học *bên trong* khối, nên hai vết lỗi ở hai
   đầu nhà máy lệch nhau thật sự chứ không cùng dịch.

    py -3.13 ma/do_bien_dang_khoi.py
    py -3.13 ma/do_bien_dang_khoi.py --xml <duong_dan_cameras.xml> --ra <file.json>
"""
import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

A_WGS = 6378137.0
F_WGS = 1 / 298.257223563
E2 = F_WGS * (2 - F_WGS)


def geo2ecef(lat_deg, lon_deg, h):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    n = A_WGS / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return np.array([(n + h) * math.cos(la) * math.cos(lo),
                     (n + h) * math.cos(la) * math.sin(lo),
                     (n * (1 - E2) + h) * math.sin(la)])


def enu_basis(lat_deg, lon_deg):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    return np.array([
        [-math.sin(lo), math.cos(lo), 0],
        [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
        [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)],
    ])


def doc_khoi(xml):
    """Trả về (tâm chụp đã bình sai, toạ độ RTK) — cả hai trong ECEF — và nhãn ảnh."""
    ch = ET.parse(xml).getroot().find("chunk")
    tr = ch.find("transform")
    if tr is None:
        raise SystemExit("[DỪNG] chunk không có <transform> — chưa georeference?")
    rot = np.array([float(x) for x in tr.find("rotation").text.split()]).reshape(3, 3)
    tra = np.array([float(x) for x in tr.find("translation").text.split()])
    sca = float(tr.find("scale").text)

    P, Q, nhan = [], [], []
    for c in ch.find("cameras").iter("camera"):
        tf, rf = c.find("transform"), c.find("reference")
        if tf is None or rf is None:
            continue  # camera không align được, hoặc không có RTK
        m = np.array([float(x) for x in tf.text.split()]).reshape(4, 4)
        P.append(sca * (rot @ m[:3, 3]) + tra)
        Q.append(geo2ecef(float(rf.get("y")), float(rf.get("x")), float(rf.get("z"))))
        nhan.append(c.get("label"))
    if not P:
        raise SystemExit("[DỪNG] không camera nào có cả <transform> lẫn <reference>")
    return np.array(P), np.array(Q), nhan, ch


def rms(v):
    return float(np.sqrt((v ** 2).sum(1).mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(
        BASE, "du_lieu", "Thermal2_31M_full_export", "cameras.xml"))
    ap.add_argument("--ra", default=os.path.join(BASE, "ket_qua", "bien_dang_khoi.json"))
    args = ap.parse_args()

    P, Q, nhan, ch = doc_khoi(args.xml)
    n = len(P)

    # ENU cục bộ, gốc đặt tại trọng tâm chùm RTK
    c_ecef = Q.mean(0)
    lat0 = math.degrees(math.atan2(c_ecef[2], math.hypot(c_ecef[0], c_ecef[1]) * (1 - E2)))
    lon0 = math.degrees(math.atan2(c_ecef[1], c_ecef[0]))
    E = enu_basis(lat0, lon0)
    p = (E @ (P - c_ecef).T).T
    q = (E @ (Q - c_ecef).T).T
    d = p - q

    kq = {
        "_mo_ta": "So tâm chụp đã bình sai với toạ độ RTK quan trắc, cùng nằm trong cameras.xml.",
        "xml": os.path.relpath(args.xml, BASE).replace("\\", "/"),
        "so_camera": n,
        "accuracy_cameras_m": None,
        "so_marker": 0,
        "goc_enu": {"lat": lat0, "lon": lon0},
    }
    for pr in ch.iter("property"):
        if pr.get("name") == "accuracy_cameras":
            kq["accuracy_cameras_m"] = float(pr.get("value"))
    kq["so_marker"] = sum(1 for _ in ch.iter("marker"))

    # --- tầng 1: thô ---
    kq["tho"] = {"lech_tb_enu_m": d.mean(0).round(4).tolist(),
                 "do_lech_chuan_enu_m": d.std(0).round(4).tolist(),
                 "rms_3d_m": round(rms(d), 4),
                 "rms_ngang_m": round(float(np.sqrt((d[:, :2] ** 2).sum(1).mean())), 4),
                 "max_3d_m": round(float(np.linalg.norm(d, axis=1).max()), 4)}

    # --- tầng 2: sau khi trừ dịch cứng ---
    d1 = d - d.mean(0)
    kq["sau_dich_cung"] = {"rms_3d_m": round(rms(d1), 4),
                           "do_lech_chuan_enu_m": d1.std(0).round(4).tolist()}

    # --- tầng 3: Helmert 7 tham số (Umeyama) ---
    pc, qc = p - p.mean(0), q - q.mean(0)
    U, S, Vt = np.linalg.svd(pc.T @ qc / n)
    D = np.diag([1, 1, float(np.sign(np.linalg.det(U @ Vt)))])
    Rr = U @ D @ Vt
    sc = float((S * np.diag(D)).sum() / ((qc ** 2).sum() / n))
    d2 = pc - sc * (Rr @ qc.T).T
    kq["sau_helmert7"] = {"rms_3d_m": round(rms(d2), 4),
                          "ti_le": round(sc, 8),
                          "ti_le_ppm": round((sc - 1) * 1e6, 1)}

    # --- tầng 4: vòm bậc hai theo bán kính ---
    r = np.linalg.norm(qc[:, :2], axis=1)
    u = d2[:, 2]
    k, c0 = np.linalg.lstsq(np.c_[r ** 2, np.ones_like(r)], u, rcond=None)[0]
    res = u - (k * r ** 2 + c0)
    kq["vom"] = {"he_so_tren_m2": float(k),
                 "lech_tai_r100m_m": round(float(k) * 1e4, 3),
                 "phan_du_sau_khu_vom_m": round(float(res.std()), 4),
                 "ban_kinh_khoi_max_m": round(float(r.max()), 2),
                 "ban_kinh_khoi_trung_vi_m": round(float(np.median(r)), 2)}

    os.makedirs(os.path.dirname(args.ra), exist_ok=True)
    json.dump(kq, open(args.ra, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("cameras.xml : %s" % kq["xml"])
    print("  %d camera · %d marker · accuracy_cameras = %s m"
          % (n, kq["so_marker"], kq["accuracy_cameras_m"]))
    print()
    print("1) THÔ           : RMS 3D %.3f m · ngang %.3f m · max %.3f m"
          % (kq["tho"]["rms_3d_m"], kq["tho"]["rms_ngang_m"], kq["tho"]["max_3d_m"]))
    print("   lệch trung bình E %+.3f  N %+.3f  U %+.3f  (m)" % tuple(kq["tho"]["lech_tb_enu_m"]))
    print("2) sau DỊCH CỨNG : RMS 3D %.3f m   <- còn lại thì KHÔNG phải lệch mốc chuẩn"
          % kq["sau_dich_cung"]["rms_3d_m"])
    print("3) sau HELMERT 7 : RMS 3D %.3f m   (tỉ lệ %+.0f ppm)"
          % (kq["sau_helmert7"]["rms_3d_m"], kq["sau_helmert7"]["ti_le_ppm"]))
    print("4) VÒM bậc hai   : %+.2f m tại r = 100 m · phần dư sau khi khử vòm %.3f m"
          % (kq["vom"]["lech_tai_r100m_m"], kq["vom"]["phan_du_sau_khu_vom_m"]))
    print("   bán kính khối : max %.1f m, trung vị %.1f m"
          % (kq["vom"]["ban_kinh_khoi_max_m"], kq["vom"]["ban_kinh_khoi_trung_vi_m"]))
    print()
    print("-> %s" % os.path.relpath(args.ra, BASE).replace("\\", "/"))


if __name__ == "__main__":
    main()
