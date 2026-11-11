# -*- coding: utf-8 -*-
"""Doi nut nen net ra khoi .hint, gan vao cum nut zoom.

Vi sao: .hint co pointer-events:none (de khong chan thao tac keo ban do).
Dat nut trong do phai dua vao viec trinh duyet cho con re-enable bang
pointer-events:auto - dung ly thuyet nhung mong manh. Cum .zoomctl khong he
bi chan, va nguoi dung cung nhin ra ngay do la nut bam.
"""
import os
import shutil

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
F = "cong_cu/so_sanh_model.html"
s = open(F, encoding="utf-8").read()
print("doc %s : %.1f MB" % (F, len(s.encode()) / 1e6))

NUT = ('<button type="button" class="netlbl" id="netlbl" data-cho="1"'
       ' aria-pressed="true" title="Bật/tắt nền độ phân giải cao (thư mục net/)">'
       'nền 2400 px</button>')

VA = []


def va(ten, cu, moi):
    VA.append((ten, cu, moi))


# 1. bo nut khoi .hint, tra .hint ve chu thuan
va("go nut khoi .hint",
   '<div class="hint">Lăn chuột để phóng · kéo để di chuyển · nháy đúp để về ban đầu'
   + NUT + '</div>',
   '<div class="hint">Lăn chuột để phóng · kéo để di chuyển · nháy đúp để về ban đầu</div>')

# 2. gan nut vao dau cum zoom
va("gan nut vao .zoomctl",
   '<div class="zoomctl"><button id="zOut" aria-label="Thu nhỏ">−</button>',
   '<div class="zoomctl">' + NUT + '<button id="zOut" aria-label="Thu nhỏ">−</button>')

# 3. CSS: nut nam trong cum zoom nen phai de len luat '.zoomctl button'
#    ('.zoomctl button' co do uu tien cao hon '.netlbl' nen phai viet
#     '.zoomctl .netlbl' moi thang duoc)
va("CSS trong cum zoom",
   """  .netlbl{margin-left:9px;padding:3px 9px;border-radius:999px;font:600 10px/1.4 var(--mono);
    letter-spacing:.04em;background:var(--accent-soft);color:var(--accent);
    border:1px solid transparent;cursor:pointer;pointer-events:auto}
  .netlbl:hover{border-color:var(--accent)}
  .netlbl:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .netlbl[data-cho="1"]{background:var(--surface-2);color:var(--muted)}
  .netlbl[aria-pressed="false"]{background:var(--surface-2);color:var(--muted);
    border-color:var(--line)}""",
   """  .zoomctl .netlbl{margin:0;border:0;border-right:1px solid var(--line);border-radius:0;
    font:600 10.5px/1 var(--mono);letter-spacing:.04em;padding:0 12px;cursor:pointer;
    background:var(--accent-soft);color:var(--accent);white-space:nowrap}
  .zoomctl .netlbl:hover{filter:brightness(.95)}
  .zoomctl .netlbl:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
  .zoomctl .netlbl[aria-pressed="false"]{background:var(--surface);color:var(--muted)}
  .zoomctl .netlbl[data-cho="1"][aria-pressed="true"]{background:var(--surface-2);
    color:var(--muted)}""")

for ten, cu, moi in VA:
    n = s.count(cu)
    if n != 1:
        raise SystemExit("DUNG: '%s' xuat hien %d lan (can 1). Chua ghi gi." % (ten, n))
print("kiem tra: ca %d phep thay khop dung 1 lan" % len(VA))

for ten, cu, moi in VA:
    s = s.replace(cu, moi, 1)
    print("   va xong: %s" % ten)

sao = "luu_tru/so_sanh_model_truoc_nut2.html"
if not os.path.exists(sao):
    shutil.copy2(F, sao)
    print("\nsao luu -> %s" % sao)

open(F, "w", encoding="utf-8").write(s)
print("da ghi %s : %.1f MB" % (F, len(s.encode()) / 1e6))
