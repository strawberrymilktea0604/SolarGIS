#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Xuất TAI_LIEU_THUAT_TOAN.md ra .pdf — bản in của tài liệu thuật toán.

Khác `xuat_docx.py` ở chỗ PDF giữ được **công thức toán**: các khối $$...$$ trong
md (ma trận H, chuỗi chiếu) được xelatex dựng thật, còn Word thì nuốt mất.

Hai đường, tự động chọn:

  ① pandoc -> xelatex  (mặc định, đẹp hơn). Cần MiKTeX; đã có sẵn trên máy này.
    Dùng xelatex chứ không pdflatex vì tiếng Việt cần font Unicode — chỉ định
    thẳng `mainfont` là font hệ thống, không qua gói fontenc.

  ② pandoc -> HTML -> Chrome --print-to-pdf  (dự phòng, cờ `--chrome`).
    Dùng khi LaTeX hỏng. Công thức đi qua MathML — Chrome dựng được, không cần
    mạng, nhưng nét chữ toán xấu hơn xelatex.

HÌNH: ba hình SVG trong tài liệu do `xuat_docx.py` dựng ra PNG. Script này KHÔNG
dựng lại. Nếu `slide_thuat_toan.html` vừa đổi thì chạy `xuat_docx.py` trước.

    py -3.13 ma/xuat_pdf.py
    py -3.13 ma/xuat_pdf.py --chrome
    py -3.13 ma/xuat_pdf.py --vao tai_lieu/BAO_CAO_DANH_GIA.md
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--vao", default=os.path.join(BASE, "tai_lieu/TAI_LIEU_THUAT_TOAN.md"))
ap.add_argument("--ra", default=None, help="mặc định: cùng tên file vào, đuôi .pdf")
ap.add_argument("--font", default="Segoe UI", help="font chữ thân bài")
ap.add_argument("--font-ma", default="Consolas", dest="font_ma", help="font khối mã")
ap.add_argument("--le", default="2.2cm", help="lề trang")
ap.add_argument("--chrome", action="store_true", help="ép đi đường Chrome, bỏ qua LaTeX")
args = ap.parse_args()

vao = os.path.abspath(args.vao)
ra = os.path.abspath(args.ra) if args.ra else os.path.splitext(vao)[0] + ".pdf"
thu_muc = os.path.dirname(vao)

if not os.path.exists(vao):
    raise SystemExit("[DỪNG] chưa có %s" % vao)
if not shutil.which("pandoc"):
    raise SystemExit("[DỪNG] chưa cài pandoc.")

# -implicit_figures: tài liệu đã tự đánh "Hình N — ..." dưới mỗi ảnh. Bật lên thì
# pandoc lấy alt text làm caption nữa, ra hai chú thích chồng nhau và số lệch nhau
# ("Figure 1" ngay trên "Hình 2"). Tắt đi thì ảnh nằm thẳng dòng, cũng hết luôn
# khoảng trắng lớn do LaTeX thả float xuống cuối trang.
CHUNG = ["pandoc", os.path.basename(vao),
         "--from", "markdown+pipe_tables-implicit_figures",
         "--toc", "--toc-depth=2",
         "--resource-path", thu_muc]


def tim_chrome():
    for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]:
        if os.path.exists(p):
            return p
    return shutil.which("chrome") or shutil.which("msedge")


def qua_latex():
    """pandoc -> xelatex. Trả về None nếu chạy được, chuỗi lỗi nếu hỏng."""
    if not shutil.which("xelatex"):
        return "không thấy xelatex"
    lenh = CHUNG + [
        "-o", ra,
        "--pdf-engine", "xelatex",
        "-V", "mainfont=" + args.font,
        "-V", "monofont=" + args.font_ma,
        "-V", "geometry:margin=" + args.le,
        "-V", "colorlinks=true",
        "-V", "linkcolor=RoyalBlue",
        "-V", "toccolor=black",
        # bảng trong tài liệu này nhiều cột chữ dài, để pandoc tự co theo bề rộng trang
        "-V", "tables=true",
    ]
    r = subprocess.run(lenh, cwd=thu_muc, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return (r.stderr or r.stdout or "").strip()[-2000:]
    return None


def qua_chrome():
    """pandoc -> HTML (MathML) -> Chrome --print-to-pdf."""
    chrome = tim_chrome()
    if not chrome:
        raise SystemExit("[DỪNG] không tìm thấy Chrome/Edge.")
    tam = os.path.join(thu_muc, "_in_tam.html")
    css = """
    @page { size: A4; margin: 18mm 16mm; }
    body { font-family: "%s", system-ui, sans-serif; font-size: 10.5pt;
           line-height: 1.5; color: #16121b; max-width: none; }
    h1 { border-bottom: 2px solid #c24d00; padding-top: 6mm; }
    h1, h2, h3 { break-after: avoid; }
    img { max-width: 100%%; height: auto; break-inside: avoid; }
    table { border-collapse: collapse; width: 100%%; font-size: 9.5pt;
            break-inside: avoid; }
    th, td { border: 1px solid #ded5cd; padding: 4px 7px; text-align: left;
             vertical-align: top; }
    th { background: #efe9e4; }
    blockquote { border-left: 3px solid #c24d00; background: #faf6f2;
                 margin: 0; padding: 6px 12px; break-inside: avoid; }
    code { font-family: "%s", monospace; font-size: 0.92em; }
    pre { background: #f4f1ee; padding: 8px; overflow-x: auto; }
    """ % (args.font, args.font_ma)
    p_css = os.path.join(thu_muc, "_in_tam.css")
    open(p_css, "w", encoding="utf-8").write(css)
    try:
        subprocess.run(CHUNG + ["-o", tam, "--to", "html5", "--standalone",
                                "--mathml", "--embed-resources", "--css", "_in_tam.css"],
                       cwd=thu_muc, check=True)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=20000",
                        "--print-to-pdf=" + ra, tam],
                       check=True, capture_output=True)
    finally:
        for p in (tam, p_css):
            if os.path.exists(p):
                os.remove(p)


if args.chrome:
    qua_chrome()
    duong = "Chrome"
else:
    loi = qua_latex()
    if loi is None:
        duong = "xelatex"
    else:
        print("[!] xelatex hỏng, chuyển sang Chrome. Lỗi:\n%s\n" % loi)
        qua_chrome()
        duong = "Chrome (xelatex hỏng)"

print("\n-> %s  (%.0f KB, đường %s)" % (ra, os.path.getsize(ra) / 1024, duong))
