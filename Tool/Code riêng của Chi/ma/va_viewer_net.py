#!/usr/bin/env python3
"""
Vá so_sanh_model.html để dùng ảnh nền nét trong thư mục net/ do xuat_nen_net.py tạo.

Cách hoạt động sau khi vá: bản 2400 px nhúng base64 vẫn vẽ ngay lập tức như cũ,
đồng thời trình duyệt tải ngầm ảnh nét của LỚP ĐANG XEM rồi thay vào chỗ. Không
tải sẵn cả ba lớp (31 MB, và mỗi lớp giải nén ra ~110 MB RAM) — chỉ lớp nào bấm
vào mới tải, tải rồi thì nhớ luôn.

Vá bằng thay chuỗi trên đúng bốn chỗ, mỗi chỗ bắt buộc khớp DUY NHẤT một lần;
lệch một chỗ là dừng, không ghi gì. Chạy lại nhiều lần vô hại (tự nhận ra đã vá).

    python ma/va_viewer_net.py
    python ma/va_viewer_net.py --hoan-tac
"""
import argparse
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "cong_cu/so_sanh_model.html")
SAO = HTML + ".truoc_net.bak"
DAU = "/* --- nen net --- */"

ap = argparse.ArgumentParser()
ap.add_argument("--html", default=HTML)
ap.add_argument("--hoan-tac", action="store_true", dest="hoan_tac")
args = ap.parse_args()

if args.hoan_tac:
    if not os.path.exists(SAO):
        raise SystemExit(f"Không có bản sao {SAO} để hoàn tác.")
    shutil.copy2(SAO, args.html)
    print(f"[HOÀN TÁC] đã khôi phục từ {SAO}")
    raise SystemExit

src = open(args.html, encoding="utf-8").read()
if DAU in src:
    raise SystemExit("File đã được vá rồi. Muốn vá lại thì --hoan-tac trước.")

VA = []

# ---------------------------------------------------------------- 1. CSS chip
VA.append((
    "  @media(prefers-reduced-motion:reduce){*{transition:none!important}}\n",
    "  @media(prefers-reduced-motion:reduce){*{transition:none!important}}\n"
    "  /* --- nen net --- */\n"
    "  .netlbl{margin-left:9px;padding:2px 7px;border-radius:999px;font:600 10px/1.4 var(--mono);\n"
    "    letter-spacing:.04em;background:var(--accent-soft);color:var(--accent)}\n"
    "  .netlbl[data-cho=\"1\"]{background:var(--surface-2);color:var(--muted)}\n",
))

# ------------------------------------------------------- 2. chỗ báo mức độ nét
VA.append((
    '<div class="hint">Lăn chuột để phóng · kéo để di chuyển · nháy đúp để về ban đầu</div>',
    '<div class="hint">Lăn chuột để phóng · kéo để di chuyển · nháy đúp để về ban đầu'
    '<span class="netlbl" id="netlbl" data-cho="1">nền 2400 px</span></div>',
))

# ------------------------------------------ 3. bộ nạp nền nét + đổi lớp qua mo()
CU3 = """let lop='rgb';
const NEN={rgb:'overview', th:'overview_thermal', thms:'overview_thermal_ms'};
function base(t){
  lop = (t===true?'th':t===false?'rgb':t);
  document.getElementById('bs').src = DATA[NEN[lop]] || DATA.overview;
  bRGB.setAttribute('aria-pressed',String(lop==='rgb'));
  bTH.setAttribute('aria-pressed',String(lop==='th'));
  bTHMS.setAttribute('aria-pressed',String(lop==='thms'));}"""

MOI3 = """let lop='rgb';
const NEN={rgb:'overview', th:'overview_thermal', thms:'overview_thermal_ms'};
/* --- nen net ---
   Anh nen goc do xuat_nen_net.py xuat ra, de FILE ROI canh HTML. Ban 2400 px
   nhung base64 van ve ngay; ban net tai ngam roi thay vao. Chi tai lop dang xem.
   daNet: null -> dang tai; chuoi -> duong dan da tai xong.
   Danh dau 'dang tai' bang null chu KHONG bang mot chuoi nao do: mo() nhan biet
   anh da tai xong bang typeof==='string', nen chuoi danh dau se lot qua va bi gan
   thang vao img.src. Xay ra khi doi lop roi doi nguoc lai truoc luc tai xong. */
const NET={rgb:'net/net_rgb.jpg', th:'net/net_th.jpg', thms:'net/net_thms.jpg'};
const daNet=new Map();
const mo = l => (typeof daNet.get(l)==='string' ? daNet.get(l)
                 : (DATA[NEN[l]] || DATA.overview));
function nhan(){
  const e=document.getElementById('netlbl'); if(!e)return;
  const v=daNet.get(lop), xong=typeof v==='string';
  e.dataset.cho = xong ? '0' : '1';
  e.textContent = xong ? 'nền gốc · nét gấp ~3,3×'
                : daNet.has(lop) ? 'đang tải nền nét…' : 'nền 2400 px';
}
function taiNet(l){
  if(!NET[l] || daNet.has(l)) return;
  daNet.set(l,null); nhan();
  const im=new Image();
  im.onload=()=>{ daNet.set(l,NET[l]);
    if(l===lop){ const b=document.getElementById('bs');
                 if(b){ b.src=NET[l]; } }
    nhan(); };
  /* Thieu thu muc net/ thi im lang quay ve ban 2400 px, dung vo trang. */
  im.onerror=()=>{ daNet.delete(l); nhan();
    console.warn('Khong tai duoc '+NET[l]+' — chay: python ma/xuat_nen_net.py'); };
  im.src=NET[l];
}
function base(t){
  lop = (t===true?'th':t===false?'rgb':t);
  document.getElementById('bs').src = mo(lop);
  taiNet(lop); nhan();
  bRGB.setAttribute('aria-pressed',String(lop==='rgb'));
  bTH.setAttribute('aria-pressed',String(lop==='th'));
  bTHMS.setAttribute('aria-pressed',String(lop==='thms'));}"""
VA.append((CU3, MOI3))

# ---------------------------------- 4. drawPins: dùng mo(), tính lại AR mỗi lần
CU4 = """  inner.innerHTML = `<img id="bs" src="${DATA[NEN[lop]]||DATA.overview}"
      alt="Bản đồ nhà máy với vị trí lỗi">
    <svg class="ov" viewBox="0 0 100 ${AR}" preserveAspectRatio="none"></svg>`;
  const im = document.getElementById('bs');
  const onload = () => {
    AR = 100 * im.naturalHeight / im.naturalWidth;
    box.style.aspectRatio = `${im.naturalWidth}/${im.naturalHeight}`;
    drawShapes(); apply();
  };
  if (im.complete && im.naturalWidth) onload(); else im.addEventListener('load', onload, {once:true});"""

MOI4 = """  inner.innerHTML = `<img id="bs" src="${mo(lop)}"
      alt="Bản đồ nhà máy với vị trí lỗi">
    <svg class="ov" viewBox="0 0 100 ${AR}" preserveAspectRatio="none"></svg>`;
  const im = document.getElementById('bs');
  /* --- nen net --- BO {once:true}: khi thay sang anh net, tỉ lệ khung lệch
     ~0,02% so voi ban 2400 px, phai tinh lai AR de khung loi khong troi. */
  const onload = () => {
    AR = 100 * im.naturalHeight / im.naturalWidth;
    box.style.aspectRatio = `${im.naturalWidth}/${im.naturalHeight}`;
    drawShapes(); apply();
  };
  im.addEventListener('load', onload);
  if (im.complete && im.naturalWidth) onload();
  taiNet(lop); nhan();"""
VA.append((CU4, MOI4))

for i, (cu, moi) in enumerate(VA, 1):
    n = src.count(cu)
    if n != 1:
        raise SystemExit(f"[DỪNG] chỗ vá {i} khớp {n} lần (cần đúng 1). "
                         f"HTML đã đổi so với lúc viết script — không ghi gì cả.")
    src = src.replace(cu, moi)

for k, ten in [("rgb", "net_rgb.jpg"), ("th", "net_th.jpg"), ("thms", "net_thms.jpg")]:
    p = os.path.join(BASE, "cong_cu/net", ten)
    print(f"  net/{ten:14s} {'có, %.1f MB' % (os.path.getsize(p)/1e6) if os.path.exists(p) else 'CHƯA CÓ — chạy xuat_nen_net.py'}")

if not os.path.exists(SAO):
    shutil.copy2(args.html, SAO)
    print(f"\n[SAO LƯU] {SAO}")
open(args.html, "w", encoding="utf-8").write(src)
print(f"[VÁ]      {args.html}  ({len(src)/1e6:.1f} MB)")
print("\nMở lại HTML. Nền 2400 px hiện ngay, ảnh nét thay vào sau 1-2 giây.")
print("Thư mục net/ phải nằm cạnh file HTML thì mới tải được.")
