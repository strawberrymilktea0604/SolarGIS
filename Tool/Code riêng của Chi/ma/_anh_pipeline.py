#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Đóng gói ảnh minh hoạ cho tài liệu pipeline thành base64 nhúng thẳng vào HTML.

Dùng ảnh THẬT của dự án (sinh ra trong quá trình kiểm chứng) chứ không lấy ảnh
minh hoạ chung trên mạng: ảnh ở đây là chính dữ liệu đang nói tới, người đọc soi
được từng pixel, và không vướng bản quyền.

Nén lại theo bề rộng đặt trước để file HTML không phình: ảnh gốc ~2-5 MB/tấm,
sau khi hạ xuống 1400 px và JPEG q78 còn ~150-250 KB.

    python ma/_anh_pipeline.py
"""
import base64
import json
import os

import cv2

import goc  # dua tien trinh ve goc du an  # noqa: F401

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

# khoá -> (đường dẫn, bề rộng đích, chú thích)
ANH = {
    "khu_meo_truoc":  ("ket_qua/kiem_tra_warp/zoom_0300_goc.jpg", 900,
                       "Ảnh gốc — méo ống kính kéo cong hàng tấm pin ở rìa"),
    "khu_meo_sau":    ("ket_qua/kiem_tra_warp/zoom_0300_undistort.jpg", 900,
                       "Sau khử méo bằng hệ số Metashape — hàng thẳng lại"),
    "hieu_chuan":     ("ket_qua/kiem_tra_warp/hieu_chuan_0280.jpg", 1500,
                       "Chấm tay 31 cặp điểm nhiệt↔RGB, dấu + vàng là vị trí H dự đoán"),
    "kiem_cheo":      ("ket_qua/kiem_tra_warp/kiem_chung_cheo.jpg", 1500,
                       "Kiểm chéo H trên cặp ảnh khác — sai số còn 2,44 px"),
    "anh_tre":        ("ket_qua/kiem_tra_warp/anh_tre_0487.jpg", 1500,
                       "Ảnh 0487: viền tấm pin chiếu từ RGB lệch hẳn 54 cm so với ảnh nhiệt"),
    "soi_manh_tre":   ("ket_qua/kiem_tra_warp/soi_manh_tre.jpg", 1500,
                       "Trượt viền dự đoán quanh vị trí gốc để đo lệch dưới mức pixel"),
    "chon_anh":       ("ket_qua/kiem_tra_warp/chon_anh_nhiet.jpg", 1500,
                       "Một điểm nằm trong nhiều ảnh — chọn ảnh có off-nadir nhỏ nhất"),
    "ortho_tu_lam":   ("ket_qua/kiem_tra_warp/ortho_nhiet_tu_lam.jpg", 1600,
                       "Ortho nhiệt tự ghép, 8451 × 4997 px, GSD 2,87 cm/px"),
    "chieu_ortho":    ("ket_qua/kiem_tra_warp/chieu_len_ortho.jpg", 1500,
                       "Chiếu box lỗi từ ảnh drone lên orthophoto"),
    "gan_tam_pin":    ("ket_qua/kiem_tra_warp/gan_tam_pin_v2.jpg", 1500,
                       "Gán box lỗi vào polygon tấm pin để lấy mã tấm"),
    "loi_tren_ortho": ("ket_qua/kiem_tra_warp/loi_tren_ortho.jpg", 1600,
                       "211 lỗi đã gom cụm, đặt trên ortho nhiệt toàn nhà máy"),
    "truoc_sau_bu":   ("ket_qua/kiem_tra_warp/truoc_sau_bu.jpg", 1500,
                       "Trước và sau khi bù lệch"),
    "ma_tran_nham":   ("ket_qua/ket_qua_val/test_nhom/confusion_matrix.png", 1100,
                       "Ma trận nhầm lẫn trên tập test — hàng background là số bỏ sót"),
    "duong_pr":       ("ket_qua/ket_qua_val/test_nhom/BoxPR_curve.png", 1000,
                       "Đường Precision–Recall của model 4 lớp"),
    "duong_r":        ("ket_qua/ket_qua_val/test_nhom/BoxR_curve.png", 1000,
                       "Recall theo ngưỡng conf — recall là đường cong, không phải một số"),
    "nhan_vs_doan":   ("ket_qua/ket_qua_val/test_nhom/val_batch0_pred.jpg", 1500,
                       "Model dự đoán trên một batch ảnh test"),
    "so_3_ban":       ("tai_lieu/_so_bu_lech.png", 1900,
                       "Metashape / tự ghép chưa bù / tự ghép đã bù lệch từng ảnh"),
    "so_ortho_can":   ("tai_lieu/_so_3_ban.png", 1900,
                       "Ba bản ortho nhiệt, cùng một vùng ~44 m"),
}

ra, thieu, tong = {}, [], 0
for k, (p, w, cap) in ANH.items():
    if not os.path.exists(p):
        thieu.append(p)
        continue
    im = cv2.imread(p)
    if im is None:
        thieu.append(p)
        continue
    if im.shape[1] > w:
        im = cv2.resize(im, (w, int(im.shape[0] * w / im.shape[1])),
                        interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        thieu.append(p)
        continue
    ra[k] = {"src": "data:image/jpeg;base64," + base64.b64encode(buf).decode(),
             "cap": cap, "goc": p}
    tong += len(buf)
    print("  %-16s %-44s %5d px  %6.0f KB" % (k, p, im.shape[1], len(buf) / 1024))

json.dump(ra, open("tai_lieu/_anh_pipeline.json", "w", encoding="utf-8"), ensure_ascii=False)
print("\n%d ảnh, tổng %.1f MB base64 -> _anh_pipeline.json" % (len(ra), tong * 1.37 / 1e6))
if thieu:
    print("Thiếu (bỏ qua):", ", ".join(thieu))
