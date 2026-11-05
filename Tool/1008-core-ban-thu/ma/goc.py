# -*- coding: utf-8 -*-
"""Dua tien trinh ve GOC DU AN roi mo khoa loi duong dan tuong doi.

Cac script trong ma/ vien dan file du lieu theo duong dan tinh tu goc du an
("ket_qua/thermal_to_rgb.json", "du_lieu/manifest_anh.csv"...). Script nao dung
ten file tran (khong ghep voi BASE) thi `import goc` mot dong la du:

    import goc   # dung o goc du an

Script nao da co BASE = <goc du an> thi khong can — ghep voi BASE la xong.
"""
import os

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(GOC)
