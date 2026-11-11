# -*- coding: utf-8 -*-
"""Dung trang HTML soi tay 100 loi mau. Mo bang trinh duyet, bam phim, xong
bam 'Tai ket qua' -> file JSON de doi chieu.

Tu dong luu vao localStorage sau moi lan bam, dong nham tab khong mat.
"""
import json
import os

import goc  # dua tien trinh ve goc du an  # noqa: F401

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

D = json.load(open("cong_cu/_the_soi_tay.json", encoding="utf-8"))
the = D["the"]

HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>Soi tay 100 lỗi mẫu</title>
<style>
:root{
  --nen:#12141a; --the:#1c1f27; --vien:#2e3341; --chu:#e6e9ef; --mo:#98a0b0;
  --xanh:#3fb96b; --do:#e0575b; --vang:#e0a13a; --xanhduong:#4d8fd6;
}
*{box-sizing:border-box}
body{margin:0;background:var(--nen);color:var(--chu);
     font:15px/1.5 "Segoe UI",system-ui,sans-serif}
header{position:sticky;top:0;z-index:9;background:#161922;
       border-bottom:1px solid var(--vien);padding:10px 18px;
       display:flex;align-items:center;gap:20px;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600}
.thanh{flex:1;min-width:180px;height:7px;background:#2a2f3b;border-radius:4px;overflow:hidden}
.thanh i{display:block;height:100%;background:var(--xanh);width:0;transition:.2s}
.dem{font-variant-numeric:tabular-nums;color:var(--mo);font-size:13px}
button{background:#252a35;color:var(--chu);border:1px solid var(--vien);
       border-radius:7px;padding:7px 13px;cursor:pointer;font-size:14px}
button:hover{background:#2f3543}
.chinh{max-width:1000px;margin:22px auto;padding:0 18px}
.khung{background:var(--the);border:1px solid var(--vien);border-radius:12px;
       padding:18px;margin-bottom:16px}
.anh{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.o{position:relative}
.o img{width:100%;display:block;border-radius:8px;background:#000}
.nhan{position:absolute;left:9px;top:9px;background:rgba(0,0,0,.72);
      padding:3px 9px;border-radius:5px;font-size:12px;letter-spacing:.3px}
.tt{display:flex;gap:9px;flex-wrap:wrap;margin:14px 0 4px;font-size:13px}
.tag{background:#252a35;border:1px solid var(--vien);border-radius:6px;
     padding:3px 10px;color:var(--mo)}
.tag b{color:var(--chu);font-weight:600}
.hoi{margin-top:16px;padding-top:15px;border-top:1px solid var(--vien)}
.hoi h3{margin:0 0 9px;font-size:14px;font-weight:600}
.hoi p{margin:0 0 9px;color:var(--mo);font-size:13px}
.nut{display:flex;gap:9px;flex-wrap:wrap}
.nut button{min-width:112px}
.nut button.on[data-v="1"]{background:var(--xanh);border-color:var(--xanh);color:#04140a}
.nut button.on[data-v="0"]{background:var(--do);border-color:var(--do);color:#fff}
.nut button.on[data-v="?"]{background:var(--vang);border-color:var(--vang);color:#1a1204}
.dieuhuong{display:flex;justify-content:space-between;align-items:center;
           gap:12px;margin-top:6px}
.phim{color:var(--mo);font-size:12.5px}
kbd{background:#252a35;border:1px solid var(--vien);border-radius:4px;
    padding:1px 6px;font-size:11.5px;font-family:inherit}
.xong{background:#16281c;border:1px solid var(--xanh);border-radius:10px;
      padding:15px;margin-bottom:16px;display:none}
.xong.hien{display:block}
</style>

<header>
  <h1>Soi tay 100 lỗi mẫu</h1>
  <div class="thanh"><i id="thanh"></i></div>
  <div class="dem" id="dem"></div>
  <button onclick="tai()">Tải kết quả</button>
</header>

<div class="chinh">
  <div class="xong" id="xong">
    <b>Xong 100/100.</b> Bấm <b>Tải kết quả</b> ở trên, rồi báo tôi để soi lại.
  </div>
  <div class="khung">
    <div class="anh">
      <div class="o">
        <img id="im_rgb">
        <div class="nhan">Ảnh màu — viền vàng là tấm hệ thống gán</div>
      </div>
      <div class="o">
        <img id="im_nh">
        <div class="nhan">Ảnh nhiệt — vệt nóng</div>
      </div>
    </div>

    <div class="tt" id="tt"></div>

    <div class="hoi">
      <h3>1. Lỗi có nằm trên đúng tấm viền vàng không?</h3>
      <p>Nhìn ảnh màu. Dấu chữ thập đỏ là vị trí lỗi. Nếu chữ thập nằm trên tấm
         khác, hoặc rơi vào khe giữa hai tấm → bấm Sai tấm.</p>
      <div class="nut" id="n1">
        <button data-v="1" onclick="dat(1,'1')">Đúng tấm</button>
        <button data-v="0" onclick="dat(1,'0')">Sai tấm</button>
        <button data-v="?" onclick="dat(1,'?')">Không rõ</button>
      </div>
    </div>

    <div class="hoi">
      <h3>2. Chỗ đó có lỗi thật không?</h3>
      <p>Nhìn ảnh nhiệt. Có vệt sáng/nóng bất thường tại chữ thập không? Không
         có gì → báo động giả.</p>
      <div class="nut" id="n2">
        <button data-v="1" onclick="dat(2,'1')">Có lỗi thật</button>
        <button data-v="0" onclick="dat(2,'0')">Báo động giả</button>
        <button data-v="?" onclick="dat(2,'?')">Không rõ</button>
      </div>
    </div>

    <div class="dieuhuong">
      <button onclick="di(-1)">← Thẻ trước</button>
      <div class="phim">
        <kbd>1</kbd> đúng tấm · <kbd>2</kbd> sai tấm · <kbd>3</kbd> không rõ ·
        <kbd>Q</kbd> lỗi thật · <kbd>W</kbd> báo động giả · <kbd>E</kbd> không rõ ·
        <kbd>←</kbd> <kbd>→</kbd> chuyển thẻ
      </div>
      <button onclick="di(1)">Thẻ sau →</button>
    </div>
  </div>
</div>

<script>
const THE = __DATA__;
const KHOA = "soi_tay_100_v1";
let kq = JSON.parse(localStorage.getItem(KHOA) || "{}");
let vt = 0;

// nhay toi the chua lam dau tien, de mo lai la lam tiep duoc ngay
for (let i = 0; i < THE.length; i++) {
  const r = kq[THE[i].idx];
  if (!r || !r.tam || !r.that) { vt = i; break; }
}

function ve() {
  const t = THE[vt];
  im_rgb.src = "data:image/jpeg;base64," + t.rgb;
  im_nh.src  = "data:image/jpeg;base64," + t.nhiet;

  const trong = t.in_panel ? "rơi hẳn trong tấm" : "KHÔNG rơi trong tấm nào";
  tt.innerHTML =
    `<span class="tag">thẻ <b>${vt+1}/${THE.length}</b></span>` +
    `<span class="tag">loại <b>${t.cls}</b></span>` +
    `<span class="tag">conf <b>${t.conf}</b></span>` +
    `<span class="tag">IoU <b>${t.iou}</b></span>` +
    `<span class="tag">hệ thống: <b>${trong}</b></span>` +
    `<span class="tag">thấy từ <b>${t.n_anh}</b> ảnh</span>`;

  const r = kq[t.idx] || {};
  for (const [id, k] of [["n1","tam"],["n2","that"]]) {
    document.querySelectorAll("#"+id+" button").forEach(b => {
      b.classList.toggle("on", r[k] === b.dataset.v);
    });
  }
  const xong = Object.values(kq).filter(x => x.tam && x.that).length;
  thanh.style.width = (100*xong/THE.length) + "%";
  dem.textContent = xong + "/" + THE.length + " đã soi";
  document.getElementById("xong").classList.toggle("hien", xong === THE.length);
}

function dat(so, v) {
  const t = THE[vt];
  const r = kq[t.idx] || {};
  r[so === 1 ? "tam" : "that"] = v;
  kq[t.idx] = r;
  localStorage.setItem(KHOA, JSON.stringify(kq));
  ve();
  // tra loi du ca hai cau -> tu sang the sau, khoi phai bam mui ten
  if (r.tam && r.that && vt < THE.length - 1) setTimeout(() => di(1), 180);
}

function di(b) {
  vt = Math.max(0, Math.min(THE.length - 1, vt + b));
  ve();
  scrollTo(0, 0);
}

addEventListener("keydown", e => {
  const m = {"1":[1,"1"],"2":[1,"0"],"3":[1,"?"],
             "q":[2,"1"],"w":[2,"0"],"e":[2,"?"]};
  const k = e.key.toLowerCase();
  if (m[k]) { dat(m[k][0], m[k][1]); e.preventDefault(); }
  else if (e.key === "ArrowLeft")  { di(-1); e.preventDefault(); }
  else if (e.key === "ArrowRight") { di(1);  e.preventDefault(); }
});

function tai() {
  const ra = THE.map(t => ({
    idx: t.idx, cls: t.cls, conf: t.conf, iou: t.iou,
    in_panel: t.in_panel, dist_cm: t.dist_cm, n_anh: t.n_anh,
    lon: t.lon, lat: t.lat,
    nguoi_dung_tam: (kq[t.idx]||{}).tam || null,
    nguoi_loi_that: (kq[t.idx]||{}).that || null
  }));
  const b = new Blob([JSON.stringify({ket_qua: ra}, null, 1)],
                     {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b);
  a.download = "_soi_tay_ket_qua.json";
  a.click();
}

ve();
</script>
"""

nho = [{k: v for k, v in t.items()} for t in the]
out = HTML.replace("__DATA__", json.dumps(nho, ensure_ascii=False))
with open("cong_cu/soi_tay_100_loi.html", "w", encoding="utf-8") as fh:
    fh.write(out)

print("Da dung soi_tay_100_loi.html (%.1f MB)"
      % (os.path.getsize("cong_cu/soi_tay_100_loi.html") / 1e6))
