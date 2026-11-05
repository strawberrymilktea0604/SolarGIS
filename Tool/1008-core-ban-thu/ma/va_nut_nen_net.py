# -*- coding: utf-8 -*-
"""Them nut BAT/TAT nen net vao so_sanh_model.html.

Viewer khong co script dung nen phai va chuoi thang vao HTML. Moi phep thay
deu kiem tra xuat hien DUNG 1 lan roi moi ghi de - sai mot chut la hong file
38 MB khong dung lai duoc.

Cach hoat dong sau khi va:
  - Nhan 'nen 2400 px / nen goc net gap 3,3x' thanh mot NUT bam duoc.
  - Bam -> doi qua lai giua anh nen nhung san (2400 px) va file net/ (~7500 px).
  - Trang thai nho trong localStorage, mo lai van giu.
"""
import os
import shutil

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
F = "cong_cu/so_sanh_model.html"

s = open(F, encoding="utf-8").read()
print("doc %s : %.1f MB" % (F, len(s.encode()) / 1e6))

VA = []


def va(ten, cu, moi):
    VA.append((ten, cu, moi))


# ---------------------------------------------------------------- 1. CSS
# .hint co pointer-events:none nen nut ben trong se khong bam duoc -> mo lai
# rieng cho nut, va them kieu cho trang thai TAT.
va("CSS nut",
   """  .netlbl{margin-left:9px;padding:2px 7px;border-radius:999px;font:600 10px/1.4 var(--mono);
    letter-spacing:.04em;background:var(--accent-soft);color:var(--accent)}
  .netlbl[data-cho="1"]{background:var(--surface-2);color:var(--muted)}""",
   """  .netlbl{margin-left:9px;padding:3px 9px;border-radius:999px;font:600 10px/1.4 var(--mono);
    letter-spacing:.04em;background:var(--accent-soft);color:var(--accent);
    border:1px solid transparent;cursor:pointer;pointer-events:auto}
  .netlbl:hover{border-color:var(--accent)}
  .netlbl:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .netlbl[data-cho="1"]{background:var(--surface-2);color:var(--muted)}
  .netlbl[aria-pressed="false"]{background:var(--surface-2);color:var(--muted);
    border-color:var(--line)}""")

# ---------------------------------------------------------------- 2. HTML
va("the nut",
   '<span class="netlbl" id="netlbl" data-cho="1">nền 2400 px</span>',
   '<button type="button" class="netlbl" id="netlbl" data-cho="1"'
   ' aria-pressed="true" title="Bật/tắt nền độ phân giải cao (thư mục net/)">'
   'nền 2400 px</button>')

# ---------------------------------------------------------------- 3. mo()
# Them dieu kien dungNet: tat thi luon tra ve anh nhung san.
va("ham mo",
   """const mo = l => (typeof daNet.get(l)==='string' ? daNet.get(l)
                 : (DATA[NEN[l]] || DATA.overview));""",
   """let dungNet = (localStorage.getItem('dungNet') !== '0');
const mo = l => ((dungNet && typeof daNet.get(l)==='string') ? daNet.get(l)
                 : (DATA[NEN[l]] || DATA.overview));""")

# ---------------------------------------------------------------- 4. taiNet
# Tai xong ma nguoi dung da tat thi dung thay anh.
va("taiNet onload",
   """  im.onload=()=>{ daNet.set(l,NET[l]);
    if(l===lop){ const b=document.getElementById('bs');
                 if(b){ b.src=NET[l]; } }
    nhan(); };""",
   """  im.onload=()=>{ daNet.set(l,NET[l]);
    if(l===lop && dungNet){ const b=document.getElementById('bs');
                 if(b){ b.src=NET[l]; } }
    nhan(); };""")

# ---------------------------------------------------------------- 5. nhan()
# Nhanh TAT phai dat TRUOC nhanh 'xuoi' vi nhanh do return som.
va("nhan() trang thai tat",
   """function nhan(){
  const e=document.getElementById('netlbl'); if(!e)return;
  const v=daNet.get(lop), xong=typeof v==='string';
  e.dataset.cho = xong ? '0' : '1';""",
   """function nhan(){
  const e=document.getElementById('netlbl'); if(!e)return;
  const v=daNet.get(lop), xong=typeof v==='string';
  if(!dungNet){ e.dataset.cho='1'; e.setAttribute('aria-pressed','false');
    e.textContent='nền 2400 px · bấm để bật nền nét'; return; }
  e.setAttribute('aria-pressed','true');
  e.dataset.cho = xong ? '0' : '1';""")

# ---------------------------------------------------------------- 6. handler
va("bat su kien bam",
   """bRGB.onclick=()=>base('rgb'); bTH.onclick=()=>base('th'); bTHMS.onclick=()=>base('thms');
bXUOI.onclick=()=>base('xuoi');""",
   """bRGB.onclick=()=>base('rgb'); bTH.onclick=()=>base('th'); bTHMS.onclick=()=>base('thms');
bXUOI.onclick=()=>base('xuoi');

/* --- nut bat/tat nen net ---
   Tat  -> quay ve anh nhung san 2400 px, moi ghep khong lo, tai nhanh.
   Bat  -> dung file net/ (~7500 px). Neu chua tai thi tai ngay luc bam. */
document.getElementById('netlbl').addEventListener('click', ()=>{
  dungNet = !dungNet;
  localStorage.setItem('dungNet', dungNet ? '1' : '0');
  const b=document.getElementById('bs');
  if(b) b.src = mo(lop);
  if(dungNet) taiNet(lop);
  nhan();
});""")

# ---------------------------------------------------------------- chay
for ten, cu, moi in VA:
    n = s.count(cu)
    if n != 1:
        raise SystemExit("DUNG: '%s' xuat hien %d lan (can dung 1). Chua ghi gi."
                         % (ten, n))
print("kiem tra: ca %d phep thay deu khop dung 1 lan" % len(VA))

for ten, cu, moi in VA:
    s = s.replace(cu, moi, 1)
    print("   va xong: %s" % ten)

sao = "luu_tru/so_sanh_model_truoc_nut.html"
os.makedirs("luu_tru", exist_ok=True)
if not os.path.exists(sao):
    shutil.copy2(F, sao)
    print("\nda sao luu ban cu -> %s" % sao)

open(F, "w", encoding="utf-8").write(s)
print("da ghi %s : %.1f MB" % (F, len(s.encode()) / 1e6))
