#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dựng trang KẾT QUẢ: chỉ 438 tấm đã chốt là CÓ LỖI, không còn box model.

Khác với `gan_nhan_tam.html` (công cụ gán nhãn — vẽ cả 603 box gợi ý của model,
cả tấm chấm tốt, cả khung tấm rìa): trang này là bản BÀN GIAO. Trên nền chỉ còn
đúng viền của những tấm người soi đã chốt có lỗi, tô theo tình trạng. Viền lấy
theo thứ tự ưu tiên: viền người sửa tay (259 tấm) -> viền tấm của best.pt.

Nền và ảnh cắt dùng lại y nguyên thư mục `nhan/` mà công cụ gán nhãn đã sinh ra,
KHÔNG cắt lại — nên chạy trong vài giây và không cần mở lại ortho.

    py -3.13 ma/loc_tam_loi.py        # bước 1: lọc bỏ tấm chấm tốt
    py -3.13 ma/lam_trang_tam_loi.py  # bước 2: dựng trang

-> ket_qua_tam_loi.html  (mở thẳng bằng trình duyệt, để cạnh thư mục nhan/)
"""
import json
import os
import sys

import goc  # dua tien trinh ve goc du an  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

MAU = {"SingleHotSpot": "#e08a3a", "MultiHotSpot": "#e0575b",
       "Bypass": "#9a7ae0", "ModuleOpenCircuit": "#c95fa8", "khac": "#d8c447"}

# ------------------------------------------------------- 1. đọc lại DATA cũ
html = open("cong_cu/gan_nhan_tam.html", encoding="utf-8").read()
i = html.index('DATA = {"nen"')
j = html.index("\n", i)
D = json.loads(html[i + len("DATA = "):j].rstrip(";"))
IDX = {m: k for k, m in enumerate(D["ma"])}

# ------------------------------------------------------- 2. ghép viền cho tấm lỗi
LOI = json.load(open("ket_qua/nhan_tam_loi.json", encoding="utf-8"))["loi"]
TAM, thieu = [], 0
for a in LOI:
    k = IDX.get(a["ma_tam"])
    vien = a.get("vien_sua") or (D["poly"][k] if k is not None else None)
    if not vien:
        thieu += 1
        continue
    TAM.append([a["ma_tam"], a["tinh_trang"], [round(float(v), 1) for v in vien],
                a["day"], a["lon"], a["lat"], a["conf"],
                1 if a.get("vien_sua") else 0,
                D["goc"].get(str(k), [None])[0] if k is not None else None])
print("[TẤM]   %d tấm lỗi có viền (%d tấm thiếu viền đã bỏ)" % (len(TAM), thieu))
print("        %d tấm dùng viền sửa tay, %d tấm dùng viền best.pt"
      % (sum(t[7] for t in TAM), sum(1 - t[7] for t in TAM)))

DATA = {"nen": D["nen"], "cua_so": D["cua_so"], "mau": MAU, "tam": TAM,
        "goc_thu_muc": D["goc_thu_muc"],
        # mã tấm -> chỉ số ảnh nhiệt gốc đã cắt sẵn trong nhan/goc/
        "idx_goc": {t[0]: IDX[t[0]] for t in TAM if str(IDX[t[0]]) in D["goc"]}}

# ------------------------------------------------------- 3. xuất HTML
TRANG = r"""<!doctype html><html lang="vi"><meta charset="utf-8">
<title>Tấm pin có lỗi — kết quả đã chốt</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0e1013;color:#e6e8ea;font:13px/1.45 "Segoe UI",system-ui,sans-serif;
     height:100vh;display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:14px;padding:9px 14px;background:#171a1f;
       border-bottom:1px solid #262a31;flex:none}
h1{font-size:15px;font-weight:600;letter-spacing:.2px}
.tong{color:#9aa3ad}
.tong b{color:#e6e8ea}
main{flex:1;display:flex;min-height:0}
#ds{width:250px;flex:none;background:#131519;border-right:1px solid #262a31;
    display:flex;flex-direction:column}
#ds .dau{padding:8px 12px;color:#9aa3ad;border-bottom:1px solid #262a31;flex:none}
#ds .than{overflow-y:auto;flex:1}
.day{padding:6px 12px 4px;color:#6f7883;font-size:11px;letter-spacing:.6px;
     background:#131519;position:sticky;top:0}
.hang{display:flex;align-items:center;gap:8px;padding:5px 12px;cursor:pointer}
.hang:hover{background:#1c2027}
.hang.chon{background:#22303f}
.cham{width:9px;height:9px;border-radius:2px;flex:none}
.ma{font-family:Consolas,monospace}
.tt{margin-left:auto;color:#828b95;font-size:11px}
#giua{flex:1;position:relative;min-width:0}
canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab}
canvas.keo{cursor:grabbing}
#bang{position:absolute;left:12px;top:12px;display:flex;gap:6px;flex-wrap:wrap;
      align-items:center;background:#171a1fdd;padding:7px 9px;border-radius:8px;
      border:1px solid #2b3038;backdrop-filter:blur(3px)}
button{background:#22262d;color:#cfd5db;border:1px solid #333943;border-radius:6px;
       padding:5px 10px;font:inherit;cursor:pointer}
button:hover{background:#2b313a}
button.bat{background:#2f6fd0;border-color:#3f7fe0;color:#fff}
.chu{color:#8b939d;padding:0 4px}
input[type=range]{width:100px;accent-color:#2f6fd0}
#chugiai{position:absolute;right:12px;top:12px;background:#171a1fdd;padding:8px 10px;
         border-radius:8px;border:1px solid #2b3038;backdrop-filter:blur(3px)}
#chugiai div{display:flex;align-items:center;gap:7px;padding:2px 0;cursor:pointer}
#chugiai div.tat{opacity:.35}
#chugiai b{margin-left:auto;font-weight:600}
#the{position:absolute;left:12px;bottom:12px;background:#171a1fee;border:1px solid #2b3038;
     border-radius:8px;padding:10px;display:none;width:230px}
#the .ma{font-size:15px;font-weight:600}
#the .d{color:#9aa3ad;margin-top:3px}
#the img{width:100%;border-radius:5px;margin-top:8px;background:#000}
</style>
<header>
  <a href="../index.html" style="color:#8b939d;text-decoration:none">← Trang chủ</a>
  <h1>Tấm pin có lỗi</h1>
  <span class="tong" id="tong"></span>
  <span style="flex:1"></span>
  <button id="taicsv">Tải CSV</button>
</header>
<main>
  <aside id="ds"><div class="dau" id="dsdau"></div><div class="than" id="dsthan"></div></aside>
  <div id="giua">
    <canvas id="c"></canvas>
    <div id="bang">
      <button id="bmau" class="bat">Màu</button>
      <button id="bnhiet">Nhiệt</button>
      <span class="chu">trộn</span><input type="range" id="tron" min="0" max="100" value="0">
      <span class="chu">|</span>
      <button id="bto" class="bat">Tô nền</button>
      <button id="bma">Mã tấm</button>
      <button id="bve">Vừa màn</button>
    </div>
    <div id="chugiai"></div>
    <div id="the"></div>
  </div>
</main>
<script>
const DATA = /*__DATA__*/null;
const C = document.getElementById('c'), G = C.getContext('2d');
const NEN = {}, LOP = [...new Set(DATA.tam.map(t => t[1]))];
let goc = {x: 0, y: 0, z: 1}, chon = null, hienMa = false, to = true;
const tat = new Set();

for (const [k, p] of Object.entries(DATA.nen)) {
  if (typeof p !== 'string') continue;
  const im = new Image(); im.src = p; im.onload = ve; NEN[k] = im;
}

/* ------------------------------------------------ danh sách bên trái */
const dem = {}; DATA.tam.forEach(t => dem[t[1]] = (dem[t[1]] || 0) + 1);
document.getElementById('tong').innerHTML =
  '<b>' + DATA.tam.length + '</b> tấm đã chốt có lỗi · ' +
  LOP.map(l => dem[l] + ' ' + l).join(' · ');
document.getElementById('dsdau').textContent = DATA.tam.length + ' tấm · xếp theo dãy';

let h = '', dayTruoc = null;
DATA.tam.forEach((t, i) => {
  if (t[3] !== dayTruoc) { dayTruoc = t[3]; h += '<div class="day">DÃY ' + t[3] + '</div>'; }
  h += '<div class="hang" data-i="' + i + '"><span class="cham" style="background:' +
       (DATA.mau[t[1]] || DATA.mau.khac) + '"></span><span class="ma">' + t[0] +
       '</span><span class="tt">' + t[1].replace('HotSpot', '') + '</span></div>';
});
document.getElementById('dsthan').innerHTML = h;
document.getElementById('dsthan').onclick = e => {
  const d = e.target.closest('.hang'); if (d) bay(+d.dataset.i);
};

/* ------------------------------------------------ chú giải, bật tắt lớp */
document.getElementById('chugiai').innerHTML = LOP.map(l =>
  '<div data-l="' + l + '"><span class="cham" style="background:' +
  (DATA.mau[l] || DATA.mau.khac) + '"></span>' + l + '<b>' + dem[l] + '</b></div>').join('');
document.getElementById('chugiai').onclick = e => {
  const d = e.target.closest('[data-l]'); if (!d) return;
  const l = d.dataset.l;
  tat.has(l) ? tat.delete(l) : tat.add(l);
  d.classList.toggle('tat', tat.has(l)); ve();
};

/* ------------------------------------------------ vẽ */
function co() {
  const r = C.getBoundingClientRect(), d = devicePixelRatio || 1;
  C.width = r.width * d; C.height = r.height * d; G.setTransform(d, 0, 0, d, 0, 0);
  return r;
}
function ve() {
  const r = co();
  G.fillStyle = '#0b0d10'; G.fillRect(0, 0, r.width, r.height);
  G.save(); G.translate(goc.x, goc.y); G.scale(goc.z, goc.z);
  const a = +document.getElementById('tron').value / 100;
  if (NEN.rgb && NEN.rgb.complete) { G.globalAlpha = 1; G.drawImage(NEN.rgb, 0, 0); }
  if (NEN.nhiet && NEN.nhiet.complete && a > 0) {
    G.globalAlpha = a; G.drawImage(NEN.nhiet, 0, 0); G.globalAlpha = 1;
  }
  const d = 1 / goc.z;
  DATA.tam.forEach((t, i) => {
    if (tat.has(t[1])) return;
    const v = t[2], m = DATA.mau[t[1]] || DATA.mau.khac;
    G.beginPath(); G.moveTo(v[0], v[1]);
    for (let k = 2; k < 8; k += 2) G.lineTo(v[k], v[k + 1]);
    G.closePath();
    if (to) { G.fillStyle = m + '44'; G.fill(); }
    G.lineWidth = (i === chon ? 3.5 : 1.6) * d;
    G.strokeStyle = i === chon ? '#fff' : m; G.stroke();
    if (hienMa && goc.z > 1.2) {
      G.fillStyle = '#fff'; G.font = (11 * d) + 'px Consolas,monospace';
      G.fillText(t[0], v[0], v[1] - 4 * d);
    }
  });
  G.restore();
}
addEventListener('resize', ve);

/* ------------------------------------------------ pan / zoom / chọn */
let keo = null;
C.onmousedown = e => { keo = {x: e.clientX - goc.x, y: e.clientY - goc.y, dx: e.clientX, dy: e.clientY}; C.classList.add('keo'); };
addEventListener('mousemove', e => {
  if (!keo) return; goc.x = e.clientX - keo.x; goc.y = e.clientY - keo.y; ve();
});
addEventListener('mouseup', e => {
  if (keo && Math.hypot(e.clientX - keo.dx, e.clientY - keo.dy) < 4) bam(e);
  keo = null; C.classList.remove('keo');
});
C.onwheel = e => {
  e.preventDefault();
  const r = C.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  const k = Math.exp(-e.deltaY * 0.0015), z = Math.min(40, Math.max(0.05, goc.z * k));
  goc.x = x - (x - goc.x) * (z / goc.z); goc.y = y - (y - goc.y) * (z / goc.z);
  goc.z = z; ve();
};
function bam(e) {
  const r = C.getBoundingClientRect();
  const x = (e.clientX - r.left - goc.x) / goc.z, y = (e.clientY - r.top - goc.y) / goc.z;
  let gan = null, min = 1e9;
  DATA.tam.forEach((t, i) => {
    if (tat.has(t[1])) return;
    const v = t[2], cx = (v[0] + v[2] + v[4] + v[6]) / 4, cy = (v[1] + v[3] + v[5] + v[7]) / 4;
    const d = Math.hypot(x - cx, y - cy);
    if (d < min && d < 60) { min = d; gan = i; }
  });
  chon = gan; the(); ve();
  if (gan !== null) {
    document.querySelectorAll('.hang.chon').forEach(n => n.classList.remove('chon'));
    const n = document.querySelector('.hang[data-i="' + gan + '"]');
    if (n) { n.classList.add('chon'); n.scrollIntoView({block: 'nearest'}); }
  }
}
function the() {
  const el = document.getElementById('the');
  if (chon === null) { el.style.display = 'none'; return; }
  const t = DATA.tam[chon];
  el.style.display = 'block';
  el.innerHTML = '<div class="ma" style="color:' + (DATA.mau[t[1]] || DATA.mau.khac) + '">' +
    t[0] + '</div><div class="d">' + t[1] + ' · dãy ' + t[3] + '</div>' +
    '<div class="d">' + (t[6] === null ? 'model không đánh dấu — người soi tự thêm'
                                       : 'conf model ' + t[6]) + '</div>' +
    '<div class="d">viền ' + (t[7] ? 'sửa tay' : 'best.pt') + '</div>' +
    /* ảnh nhiệt gốc cắt sẵn đánh số theo CHỈ SỐ TẤM của công cụ gán nhãn chứ
       không theo thứ tự trang này — tra ngược qua bảng idx_goc đã nhúng */
    (t[0] in DATA.idx_goc
      ? '<img src="' + DATA.goc_thu_muc + DATA.idx_goc[t[0]] + '.jpg">' : '');
}
function bay(i) {
  chon = i; const t = DATA.tam[i], v = t[2];
  const cx = (v[0] + v[2] + v[4] + v[6]) / 4, cy = (v[1] + v[3] + v[5] + v[7]) / 4;
  const r = C.getBoundingClientRect();
  goc.z = 6; goc.x = r.width / 2 - cx * goc.z; goc.y = r.height / 2 - cy * goc.z;
  the(); ve();
  document.querySelectorAll('.hang.chon').forEach(n => n.classList.remove('chon'));
  const n = document.querySelector('.hang[data-i="' + i + '"]');
  if (n) n.classList.add('chon');
}

/* ------------------------------------------------ nút */
const T = document.getElementById('tron');
T.oninput = () => {
  document.getElementById('bmau').classList.toggle('bat', +T.value < 50);
  document.getElementById('bnhiet').classList.toggle('bat', +T.value >= 50);
  ve();
};
document.getElementById('bmau').onclick = () => { T.value = 0; T.oninput(); };
document.getElementById('bnhiet').onclick = () => { T.value = 100; T.oninput(); };
document.getElementById('bto').onclick = e => { to = !to; e.target.classList.toggle('bat', to); ve(); };
document.getElementById('bma').onclick = e => { hienMa = !hienMa; e.target.classList.toggle('bat', hienMa); ve(); };
document.getElementById('bve').onclick = vuaman;
function vuaman() {
  const r = C.getBoundingClientRect();
  goc.z = Math.min(r.width / DATA.nen.w, r.height / DATA.nen.h);
  goc.x = (r.width - DATA.nen.w * goc.z) / 2; goc.y = (r.height - DATA.nen.h * goc.z) / 2;
  ve();
}
document.getElementById('taicsv').onclick = () => {
  const d = ['ma_tam,day,tinh_trang,lon,lat,conf_model,vien'].concat(
    DATA.tam.map(t => [t[0], t[3], t[1], t[4], t[5], t[6] === null ? '' : t[6],
                       t[7] ? 'sua_tay' : 'best.pt'].join(','))).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + d], {type: 'text/csv'}));
  a.download = 'tam_loi.csv'; a.click();
};
addEventListener('keydown', e => {
  if (e.key === 'f') vuaman();
  if (e.key === 'm') document.getElementById('bma').click();
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && chon !== null) {
    e.preventDefault();
    bay(Math.min(DATA.tam.length - 1, Math.max(0, chon + (e.key === 'ArrowDown' ? 1 : -1))));
  }
});
vuaman();
</script>
</html>
"""

out = TRANG.replace("/*__DATA__*/null", json.dumps(
    DATA, ensure_ascii=False, separators=(",", ":"), default=float))
open("cong_cu/ket_qua_tam_loi.html", "w", encoding="utf-8").write(out)
print("\n-> ket_qua_tam_loi.html  (%.2f MB)"
      % (os.path.getsize("cong_cu/ket_qua_tam_loi.html") / 1e6))
print("   mở thẳng bằng trình duyệt, để cạnh thư mục nhan/")
