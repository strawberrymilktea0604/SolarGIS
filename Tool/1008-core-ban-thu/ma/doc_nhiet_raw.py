# -*- coding: utf-8 -*-
"""Rut mang NHIET DO 16-bit nam trong anh nhiet DJI (R-JPEG).

Anh _T.JPG cua ZH20T KHONG chi la anh xem 8-bit. Mang nhiet 640x512 x 16-bit
duoc nhet trong cac doan APP3 cua file JPEG — dung 655.360 byte. Anh ma
cv2.imread doc ra chi la ban XEM, da tu dong keo tuong phan RIENG cho tung anh
va nen JPEG, con 256 muc.

    16-bit raw : 4283 muc khac nhau
    anh 8-bit  :  256 muc          -> mat ~16 lan do phan giai nhiet

Ke ca gia tri tuyet doi cung mat: cung mot nhiet do thuc cho ra muc xam khac
nhau o hai anh khac nhau, vi moi anh tu keo tuong phan theo dai nhiet cua rieng no.

    python ma/doc_nhiet_raw.py DJI_..._T.JPG
"""
import sys
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

W, H = 640, 512
HE_SO, OFFSET = 64.0, 273.15      # raw/64 - 273,15 -> do C (kiem bang dai gia tri hop ly)


def doc_raw(duong, w=W, h=H):
    """Tra ve mang uint16 (h, w), hoac None neu anh khong phai R-JPEG."""
    b = open(duong, 'rb').read()
    i, buf = 2, b''
    while i < len(b) - 1 and b[i] == 0xFF:
        m = b[i + 1]
        if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xDA:
            break
        ln = int.from_bytes(b[i + 2:i + 4], 'big')
        if m == 0xE3:                                   # APP3
            buf += b[i + 4:i + 2 + ln]
        i += 2 + ln
    if len(buf) < w * h * 2:
        return None
    return np.frombuffer(buf[:w * h * 2], '<u2').reshape(h, w)


def doc_do_C(duong):
    """Mang nhiet do xap xi, don vi do C.

    CANH BAO: he so 64 suy ra tu dai gia tri hop ly (27-100 do C tren tam pin
    luc trua), CHUA doi chieu voi may do nhiet cam tay. Muon so tuyet doi dung
    chuan thi phai giai bang DJI Thermal SDK, no con nhan he so phat xa, nhiet
    do phan xa, do am, khoang cach. Nhung de tinh CHENH LECH nhiet giua hai tam
    trong CUNG mot anh thi he so nay du dung, vi sai so he thong tu triet tieu.
    """
    r = doc_raw(duong)
    return None if r is None else r.astype(np.float32) / HE_SO - OFFSET


if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else None
    if not p:
        import csv, os
        p = next(iter(csv.DictReader(open('du_lieu/manifest_anh.csv', encoding='utf-8-sig'))))['path_thermal']
        print('(khong truyen duong dan, lay anh dau trong manifest)')
    t = doc_do_C(p)
    if t is None:
        raise SystemExit('Khong phai R-JPEG hoac kich thuoc khac 640x512')
    import os
    print('%s' % os.path.basename(p))
    print('  nhiet do : %.1f .. %.1f do C   trung vi %.1f' % (t.min(), t.max(), np.median(t)))
    print('  95%% duoi : %.1f do C   |  99,9%% duoi: %.1f do C'
          % (np.percentile(t, 95), np.percentile(t, 99.9)))
    nen = np.median(t)
    print('  so pixel nong hon nen 10 K : %d (%.3f%%)'
          % ((t > nen + 10).sum(), 100 * (t > nen + 10).mean()))
