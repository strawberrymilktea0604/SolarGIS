#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Gom cac file KHONG script nao doc toi vao luu_tru/, cho thu muc goc de nhin.

Nguyen tac: chi chuyen file da doi chieu la khong .py nao nhac ten. Moi script
deu dung BASE = GOC DU AN roi ghep duong dan tuong doi vao do, nen file nao
con duoc doc thi de nguyen tai goc — chuyen di la hong.

Ghi nhat ky ra luu_tru/_da_chuyen.json de hoan tac:
    python ma/dong_goi.py --hoan-tac
"""
import argparse
import json
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUU = os.path.join(BASE, "luu_tru")
NHAT_KY = os.path.join(LUU, "_da_chuyen.json")

NHOM = {
    "ban_sao": (
        "Ban .bak sinh ra truoc moi lan va viewer",
        ["viewer_data_4model.json.bak", "so_sanh_model.html.bak",
         "so_sanh_model.html.truoc_net.bak"]),
    "viewer_cu": (
        "Cac ban viewer da bi so_sanh_model.html thay the (deu tu chua, nhung base64)",
        ["ban_do_loi.html", "ban_do_211_loi.html", "viewer_data.json",
         "viewer_data_211.json", "viewer_data_2model.json",
         "viewer_data_4model.json"]),
    "anh_tam": (
        "Anh chup man hinh / anh trung gian khi dung viewer, khong ai doc",
        ["_full_small.png", "_ghep_test.png", "_html_mau.png", "_html_nhiet.png",
         "_nhiet_metashape.png", "_nhiet_metashape.b64", "_nhiet_tulam_lop.png",
         "_nhung_mau.png", "_nhung_nhiet.png", "_tulam_small.png"]),
    "H_cu": (
        "Cac ban H cu / thu nghiem. H DANG DUNG la thermal_to_rgb.json o goc",
        ["thermal_to_rgb_backup26.json", "thermal_to_rgb_backup31.json",
         "thermal_to_rgb_ransac.json", "thermal_to_rgb_truoc_bu_ngang.json",
         "thermal_to_rgb_truoc_bu_ortho.json", "thermal_to_rgb_11diem.json",
         "dong_nhat.json", "kiem_H_goc.json"]),
    "ortho_cu": (
        "Ortho nhiet ban cu. Ban DANG DUNG la ortho_nhiet_tu_lam.tif o goc",
        ["ortho_nhiet_truoc_bu.tif", "ortho_nhiet_thu.tif"]),
    "loi_cu": (
        "Ket qua phat hien loi cua cac model cu. Ban DANG DUNG la "
        "loi_tren_ortho_nhiet.json o goc",
        ["loi_obb4.json", "loi_obb5.json", "loi_obb6.json", "loi_obb_4lop.json",
         "loi_phat_hien.json", "gan_tam_pin.json"]),
    "anh_cat": (
        "Anh cat tu ortho de doi chieu bang mat, khong script nao doc",
        ["ortho_cat_MAU.png", "ortho_cat_NHIET.png", "ortho_cat_MAU_GHEP.png"]),
    "danh_sach": (
        "Danh sach ten anh, sinh mot lan luc khao sat du lieu",
        ["danh_sach_anh_RGB.txt", "danh_sach_anh_NHIET.txt",
         "danh_sach_anh_TAT_CA.txt"]),
}

THU_MUC = ["__pycache__", "ma/__pycache__"]

ap = argparse.ArgumentParser()
ap.add_argument("--hoan-tac", action="store_true")
ap.add_argument("--thu", action="store_true", help="chi in ra se lam gi")
a = ap.parse_args()

if a.hoan_tac:
    if not os.path.exists(NHAT_KY):
        raise SystemExit("Khong co nhat ky, chua chuyen gi")
    for tu, den in json.load(open(NHAT_KY, encoding="utf-8")):
        d = os.path.join(BASE, den)
        if os.path.exists(d):
            shutil.move(d, os.path.join(BASE, tu))
            print("tra ve:", tu)
    os.remove(NHAT_KY)
    raise SystemExit("Da hoan tac")

# Chot chan: khong chuyen file nao con duoc mot .py nhac ten.
# Tru CHINH FILE NAY ra — no chua san moi ten file trong cac danh sach tren,
# khong tru thi file nao cung bi coi la "dang duoc dung" va khong chuyen gi ca.
toi = os.path.basename(os.path.abspath(__file__))
MA_DIR = os.path.join(BASE, "ma")
ma = ""
for f in os.listdir(MA_DIR):
    if f.endswith(".py") and f != toi:
        ma += open(os.path.join(MA_DIR, f), encoding="utf-8", errors="ignore").read()

nhat_ky, tong = [], 0
for nhom, (mo_ta, ds) in NHOM.items():
    dich = os.path.join(LUU, nhom)
    co = [f for f in ds if os.path.exists(os.path.join(BASE, f))]
    if not co:
        continue
    print("\n%s/  — %s" % (nhom, mo_ta))
    for f in co:
        if f in ma:
            print("   BO QUA %s (co script nhac ten)" % f)
            continue
        kt = os.path.getsize(os.path.join(BASE, f))
        print("   %-38s %8.1f MB" % (f, kt / 1e6))
        tong += kt
        if not a.thu:
            os.makedirs(dich, exist_ok=True)
            shutil.move(os.path.join(BASE, f), os.path.join(dich, f))
            nhat_ky.append([f, os.path.join("luu_tru", nhom, f)])

for d in THU_MUC:
    if os.path.isdir(os.path.join(BASE, d)) and not a.thu:
        shutil.rmtree(os.path.join(BASE, d), ignore_errors=True)
        print("\nda xoa thu muc tam: %s/" % d)

if not a.thu:
    os.makedirs(LUU, exist_ok=True)
    cu = json.load(open(NHAT_KY, encoding="utf-8")) if os.path.exists(NHAT_KY) else []
    json.dump(cu + nhat_ky, open(NHAT_KY, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

print("\nTong cong %s %.0f MB sang luu_tru/"
      % ("se chuyen" if a.thu else "da chuyen", tong / 1e6))
