#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Xuất TAI_LIEU_THUAT_TOAN.md ra .docx — bản Word của slide thuật toán.

Hai chặng:

  ① Ba hình trong tài liệu là SVG nhúng thẳng trong `slide_thuat_toan.html`.
    Word không nhận SVG do pandoc sinh ra, nên phải dựng thành PNG trước:
    bóc từng khối <svg> ra, bọc vào một trang HTML tối giản có ĐỦ BỘ TOKEN màu
    (SVG dùng var(--ember)... nên thiếu token là hình ra đen thui), rồi chụp bằng
    Chrome headless ở 2× cho nét khi in.

    Ép sáng bằng cách khai báo token thẳng trên :root, KHÔNG qua prefers-color-scheme
    — máy đặt theme tối thì trang chụp ra sẽ tối, mà nền tối in giấy thì hỏng.

  ② pandoc md -> docx. Không cần LaTeX. Bảng, blockquote, ảnh + chú thích đều
    sang Word được; heading giữ nguyên cấp nên mục lục tự động của Word dùng được.

    py -3.13 ma/xuat_docx.py
    py -3.13 ma/xuat_docx.py --bo-qua-hinh     # md đổi, hình không đổi
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--nguon-svg", default=os.path.join(BASE, "tai_lieu/slide_thuat_toan.html"),
                dest="nguon_svg")
ap.add_argument("--vao", default=os.path.join(BASE, "tai_lieu/TAI_LIEU_THUAT_TOAN.md"))
ap.add_argument("--ra", default=os.path.join(BASE, "tai_lieu/TAI_LIEU_THUAT_TOAN.docx"))
ap.add_argument("--hinh", default=os.path.join(BASE, "tai_lieu/hinh"))
ap.add_argument("--bo-qua-hinh", action="store_true", dest="bo_hinh")
args = ap.parse_args()

# Token màu bản SÁNG, chép từ :root của slide_thuat_toan.html. Phải có đủ, vì
# mọi nét trong SVG đều trỏ vào đây.
TOKEN = """
:root{
  --ground:#f7f4f1; --surface:#ffffff; --surface-2:#efe9e4;
  --line:#ded5cd; --line-soft:#ebe4dd;
  --text:#1b1620; --text-2:#5f5769; --text-3:#8b8394;
  --ember:#c24d00; --ember-soft:#f7e3d4; --flare:#9a6b00;
  --steel:#2f5f9e; --steel-soft:#dde7f4;
  --good:#1e6b46; --bad:#b03040;
  --font-display:"Bahnschrift","DIN Alternate","Segoe UI",system-ui,sans-serif;
  --font-body:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
  --font-mono:"Cascadia Mono",Consolas,monospace;
  color:var(--text);
}
html,body{margin:0;padding:0;background:#ffffff}
svg{display:block;width:100%;height:auto}
"""

TEN = ["thuat_toan_h1_pipeline", "thuat_toan_h2_chieu", "thuat_toan_h3_huong"]


def tim_chrome():
    for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]:
        if os.path.exists(p):
            return p
    return shutil.which("chrome") or shutil.which("msedge")


def dung_hinh():
    html = open(args.nguon_svg, encoding="utf-8").read()
    svgs = re.findall(r"<svg\s.*?</svg>", html, re.S)
    if len(svgs) != len(TEN):
        raise SystemExit("[DỪNG] tìm thấy %d <svg>, chờ %d — kiểm tra lại nguồn."
                         % (len(svgs), len(TEN)))
    chrome = tim_chrome()
    if not chrome:
        raise SystemExit("[DỪNG] không tìm thấy Chrome/Edge để dựng hình.")
    os.makedirs(args.hinh, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="svg2png_")

    for svg, ten in zip(svgs, TEN):
        vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
        w, h = (float(vb.group(1)), float(vb.group(2))) if vb else (900.0, 600.0)
        K = 2                                    # 2x cho nét khi in
        trang = os.path.join(tmp, ten + ".html")
        with open(trang, "w", encoding="utf-8") as f:
            f.write("<!doctype html><meta charset='utf-8'><style>%s</style>%s" % (TOKEN, svg))
        ra = os.path.join(args.hinh, ten + ".png")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=%d" % K,
                        "--window-size=%d,%d" % (int(w), int(h)),
                        "--screenshot=" + ra, trang],
                       check=True, capture_output=True)
        kb = os.path.getsize(ra) / 1024
        print("[HÌNH] %-34s %4dx%-4d -> %.0f KB" % (ten + ".png", int(w * K), int(h * K), kb))
    shutil.rmtree(tmp, ignore_errors=True)


if not args.bo_hinh:
    dung_hinh()

if not os.path.exists(args.vao):
    raise SystemExit("[DỪNG] chưa có %s" % args.vao)
if not shutil.which("pandoc"):
    raise SystemExit("[DỪNG] chưa cài pandoc.")

subprocess.run(["pandoc", os.path.basename(args.vao),
                "-o", os.path.abspath(args.ra),
                "--from", "markdown+pipe_tables+implicit_figures",
                "--to", "docx",
                "--toc", "--toc-depth=2",
                "--resource-path", os.path.dirname(os.path.abspath(args.vao))],
               cwd=os.path.dirname(os.path.abspath(args.vao)), check=True)

print("\n-> %s  (%.0f KB)" % (args.ra, os.path.getsize(args.ra) / 1024))
