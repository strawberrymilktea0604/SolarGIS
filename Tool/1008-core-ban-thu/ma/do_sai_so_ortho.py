#!/usr/bin/env python3
"""
Đo sai số END-TO-END của cả chuỗi: ảnh drone -> tia -> DSM -> GPS -> orthophoto.

Cách làm:
  Lấy các điểm neo đã chấm trên ảnh RGB (file thermal_to_rgb.json), chiếu từng điểm
  xuống thực địa rồi lên orthophoto. Sau đó hiển thị:
      TRÁI  = ảnh drone, đánh dấu điểm gốc  (để biết đang xét vật nào)
      PHẢI  = orthophoto quanh vị trí chiếu, dấu + VÀNG = chỗ chuỗi tính ra
  Bạn click vào vị trí THẬT của vật đó trên ortho.
  Khoảng cách giữa dấu vàng và chỗ bạn click = SAI SỐ CỦA CẢ CHUỖI.

  python ma/do_sai_so_ortho.py

Phím:
  Chuột trái = chấm vị trí thật   |  Lăn chuột / W,X = phóng to thu nhỏ
  N = bỏ qua điểm này             |  U = quay lại điểm trước
  S = lưu và thoát                |  Q = thoát không lưu
"""

import argparse
import json
import os
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import rasterio
from pyproj import Transformer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(BASE, "du_lieu/Thermal2_31M_full_export")


# ============================================================================
# 1. CHIẾU ĐIỂM RGB -> ORTHO
# ============================================================================
class Chain:
    def __init__(self, xml_path, dsm_path, label):
        root = ET.parse(xml_path).getroot()
        chunk = root.find(".//chunk")

        s = chunk.find(".//sensor[@id='0']")
        res = s.find("resolution")
        cal = s.find("calibration[@class='adjusted']")
        g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
        self.W, self.H = int(res.get("width")), int(res.get("height"))
        self.f, self.cx, self.cy = g("f"), g("cx"), g("cy")

        cam = next(c for c in chunk.findall(".//camera") if c.get("label") == label)
        self.M = np.array(list(map(float, cam.find("transform").text.split()))).reshape(4, 4)

        t = chunk.find(".//component").find("transform")
        self.R = np.array(list(map(float, t.find("rotation").text.split()))).reshape(3, 3)
        self.T = np.array(list(map(float, t.find("translation").text.split())))
        self.S = float(t.find("scale").text)

        self.tf = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
        self.C = self.S * (self.R @ self.M[:3, 3]) + self.T

        self.dsm = rasterio.open(dsm_path)
        self.D = self.dsm.read(1)

    def _dsm(self, lon, lat):
        b = self.dsm.bounds
        if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
            return None
        c, r = ~self.dsm.transform * (lon, lat)
        c, r = int(c), int(r)
        if 0 <= r < self.dsm.height and 0 <= c < self.dsm.width:
            v = self.D[r, c]
            if v != self.dsm.nodata and not np.isnan(v):
                return float(v)
        return None

    def project(self, u, v, max_dist=120.0, n=600):
        d_cam = np.array([(u - self.W / 2 - self.cx) / self.f,
                          (v - self.H / 2 - self.cy) / self.f, 1.0])
        d = self.R @ (self.M[:3, :3] @ d_cam)
        d /= np.linalg.norm(d)

        prev, step = None, max_dist / n
        for i in range(n):
            P = self.C + i * step * d
            lon, lat, alt = self.tf.transform(*P)
            e = self._dsm(lon, lat)
            if e is None:
                continue
            diff = alt - e
            if prev is not None and prev[0] > 0 >= diff:
                lo, hi = prev[1], i * step
                for _ in range(60):
                    mid = (lo + hi) / 2
                    lo_, la_, al_ = self.tf.transform(*(self.C + mid * d))
                    em = self._dsm(lo_, la_)
                    if em is None:
                        lo = mid
                        continue
                    lo, hi = (mid, hi) if al_ - em > 0 else (lo, mid)
                lon, lat, _ = self.tf.transform(*(self.C + (lo + hi) / 2 * d))
                return lon, lat, self._dsm(lon, lat)
            prev = (diff, i * step)
        return None


# ============================================================================
# 2. GIAO DIỆN ĐO
# ============================================================================
class Measurer:
    WIN = "DO SAI SO END-TO-END   |  TRAI = anh drone (vat can xet)   PHAI = orthophoto"
    BAR = 44

    def __init__(self, rgb, ortho_src, items, gsd_cm, panel=(760, 700)):
        self.rgb, self.ortho, self.items, self.gsd = rgb, ortho_src, items, gsd_cm
        self.PW, self.PH = panel
        self.ROFF = self.PW + 8
        self.i = 0
        self.zoom = 3.0
        self.cur = (0, 0)
        self.marks = {}          # index -> (col, row) that
        self.drag = None
        self.tx = self.ty = 0.0  # keo anh ortho

    # --------------------------------------------------------------- ảnh
    def _crop(self, img, cx, cy, dx=0.0, dy=0.0):
        z = self.zoom
        cw, ch = int(self.PW / z), int(self.PH / z)
        c0 = int(round(cx - cw / 2 - dx / z))
        r0 = int(round(cy - ch / 2 - dy / z))
        h, w = img.shape[:2]
        c0 = max(0, min(c0, w - cw)); r0 = max(0, min(r0, h - ch))
        out = cv2.resize(img[r0:r0 + ch, c0:c0 + cw], (self.PW, self.PH),
                         interpolation=cv2.INTER_NEAREST)
        return out, c0, r0

    def _left(self):
        it = self.items[self.i]
        v, c0, r0 = self._crop(self.rgb, it["u"], it["v"])
        p = (int((it["u"] - c0) * self.zoom), int((it["v"] - r0) * self.zoom))
        cv2.drawMarker(v, p, (0, 255, 0), cv2.MARKER_CROSS, 40, 2)
        cv2.circle(v, p, 30, (0, 255, 0), 1)
        cv2.putText(v, f"ANH DRONE - diem #{it['idx']}", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        cv2.putText(v, "vat can tim tren ortho", (12, 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
        return v

    def _right(self):
        it = self.items[self.i]
        v, c0, r0 = self._crop(self.orthoimg, it["ocol"] - self.ocol0,
                               it["orow"] - self.orow0, self.tx, self.ty)
        self.rc0, self.rr0 = c0, r0
        g = (int((it["ocol"] - self.ocol0 - c0) * self.zoom),
             int((it["orow"] - self.orow0 - r0) * self.zoom))
        cv2.line(v, (g[0] - 26, g[1]), (g[0] + 26, g[1]), (0, 220, 255), 2)
        cv2.line(v, (g[0], g[1] - 26), (g[0], g[1] + 26), (0, 220, 255), 2)
        cv2.circle(v, g, 30, (0, 220, 255), 1)

        if self.i in self.marks:
            mc, mr = self.marks[self.i]
            p = (int((mc - self.ocol0 - c0) * self.zoom), int((mr - self.orow0 - r0) * self.zoom))
            cv2.drawMarker(v, p, (0, 0, 255), cv2.MARKER_CROSS, 30, 2)
            cv2.line(v, g, p, (255, 255, 255), 1)
            d = np.hypot(mc - it["ocol"], mr - it["orow"])
            cv2.putText(v, f"lech {d:.1f} px = {d*self.gsd:.1f} cm", (12, self.PH - 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        mx, my = self.cur
        if mx >= self.ROFF:
            x = mx - self.ROFF
            cv2.line(v, (x, 0), (x, self.PH), (255, 255, 255), 1)
            cv2.line(v, (0, my), (self.PW, my), (255, 255, 255), 1)
        cv2.putText(v, f"ORTHO  {self.zoom:.1f}x   vang = chuoi tinh ra", (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
        return v

    def _canvas(self):
        body = np.hstack([self._left(), np.full((self.PH, 8, 3), 70, np.uint8), self._right()])
        bar = np.full((self.BAR, body.shape[1], 3), 25, np.uint8)
        done = len(self.marks)
        cv2.putText(bar, f"Diem {self.i+1}/{len(self.items)}   da do: {done}   "
                         f"Click vao VI TRI THAT tren ortho (ben phai)",
                    (12, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(bar, "N=bo qua  U=quay lai  W/X=zoom  S=luu  Q=thoat",
                    (body.shape[1] - 470, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        return np.vstack([bar, body])

    # ------------------------------------------------------------- chuột
    def _mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEWHEEL:
            try:
                dlt = cv2.getMouseWheelDelta(flags)
            except AttributeError:
                dd = (flags >> 16) & 0xFFFF
                dlt = dd - 0x10000 if dd >= 0x8000 else dd
            self.zoom = float(np.clip(self.zoom * (1.25 if dlt > 0 else 0.8), 0.5, 16))
            return
        y -= self.BAR
        self.cur = (x, y)
        if y < 0 or x < self.ROFF:
            return
        if event == cv2.EVENT_RBUTTONDOWN:
            self.drag = (x, y)
        elif event == cv2.EVENT_RBUTTONUP:
            self.drag = None
        elif event == cv2.EVENT_MOUSEMOVE and self.drag:
            self.tx += x - self.drag[0]; self.ty += y - self.drag[1]
            self.drag = (x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            col = self.ocol0 + self.rc0 + (x - self.ROFF) / self.zoom
            row = self.orow0 + self.rr0 + y / self.zoom
            self.marks[self.i] = (col, row)
            it = self.items[self.i]
            d = np.hypot(col - it["ocol"], row - it["orow"])
            print(f"  #{it['idx']:02d}  lech {d:6.2f} px = {d*self.gsd:6.2f} cm  "
                  f"(dcol={col-it['ocol']:+6.2f}, drow={row-it['orow']:+6.2f})")
            self._next()

    def _next(self):
        if self.i < len(self.items) - 1:
            self.i += 1
            self.tx = self.ty = 0.0

    # ---------------------------------------------------------------- run
    def run(self, ortho_img, ocol0, orow0):
        self.orthoimg, self.ocol0, self.orow0 = ortho_img, ocol0, orow0
        cv2.namedWindow(self.WIN, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.WIN, self._mouse)
        while True:
            cv2.imshow(self.WIN, self._canvas())
            k = cv2.waitKey(20) & 0xFF
            if k in (ord('n'), ord('N')):
                self._next()
            elif k in (ord('u'), ord('U')):
                if self.i > 0:
                    self.i -= 1; self.tx = self.ty = 0.0
                self.marks.pop(self.i, None)
            elif k in (ord('w'), ord('W'), ord('+'), ord('=')):
                self.zoom = min(16, self.zoom * 1.3)
            elif k in (ord('x'), ord('X'), ord('-')):
                self.zoom = max(0.5, self.zoom / 1.3)
            elif k in (ord('s'), ord('S')):
                cv2.destroyWindow(self.WIN); return self.marks
            elif k in (ord('q'), ord('Q'), 27):
                cv2.destroyWindow(self.WIN); return None


# ============================================================================
# MAIN
# ============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="DJI_20260411085535_0280_W")
    ap.add_argument("--points", default=os.path.join(BASE, "ket_qua/thermal_to_rgb.json"))
    ap.add_argument("--out", default=os.path.join(BASE, "ket_qua/sai_so_end_to_end.json"))
    args = ap.parse_args()

    cache = os.path.join(BASE, "ket_qua/chieu_diem_cache.json")
    ortho = rasterio.open(os.path.join(EXP, "ortho.tif"))
    gsd_cm = abs(ortho.transform.a) * 111320 * np.cos(np.radians(11.424)) * 100
    print(f"[ORT] {ortho.width}x{ortho.height}  GSD {gsd_cm:.3f} cm/px")

    if os.path.exists(cache):
        items = json.load(open(cache, encoding="utf-8"))
        print(f"[INFO] Nap lai {len(items)} diem da chieu tu cache")
    else:
        pts = json.load(open(args.points, encoding="utf-8"))["points_rgb"]
        ch = Chain(os.path.join(EXP, "cameras.xml"), os.path.join(EXP, "dsm.tif"), args.label)
        print(f"[INFO] Chieu {len(pts)} diem qua DSM...")
        items = []
        for i, (u, v) in enumerate(pts):
            r = ch.project(u, v)
            if r is None:
                print(f"  #{i:02d} khong cat duoc DSM, bo qua")
                continue
            lon, lat, elev = r
            col, row = ~ortho.transform * (lon, lat)
            items.append({"idx": i, "u": u, "v": v, "lon": lon, "lat": lat,
                          "elev": elev, "ocol": col, "orow": row})
        json.dump(items, open(cache, "w", encoding="utf-8"), indent=1)
        print(f"[INFO] Da chieu {len(items)} diem, luu cache")

    cols = [it["ocol"] for it in items]; rows = [it["orow"] for it in items]
    c0 = max(0, int(min(cols)) - 400); r0 = max(0, int(min(rows)) - 400)
    c1 = min(ortho.width, int(max(cols)) + 400); r1 = min(ortho.height, int(max(rows)) + 400)
    img = ortho.read(window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0))[:3]
    img = np.ascontiguousarray(np.moveaxis(img, 0, -1)[:, :, ::-1])
    print(f"[INFO] Cat ortho {img.shape[1]}x{img.shape[0]} tai ({c0},{r0})")

    rgb_path = None
    for root_, _, files in os.walk(os.path.join(BASE, "du_lieu/data_aligned", "rgb")):
        for f in files:
            if f.startswith(args.label):
                rgb_path = os.path.join(root_, f)
    rgb = cv2.imread(rgb_path)
    s = ET.parse(os.path.join(EXP, "cameras.xml")).getroot().find(".//sensor[@id='0']")
    cal = s.find("calibration[@class='adjusted']")
    g = lambda t: float(cal.find(t).text) if cal.find(t) is not None else 0.0
    h_, w_ = rgb.shape[:2]
    K = np.array([[g("f"), 0, w_ / 2 + g("cx")], [0, g("f"), h_ / 2 + g("cy")], [0, 0, 1.0]])
    rgb = cv2.undistort(rgb, K, np.array([g("k1"), g("k2"), g("p1"), g("p2"), g("k3")]))

    print("\nClick vao vi tri THAT cua vat tren ortho. Moi lan click se tu sang diem tiep.\n")
    m = Measurer(rgb, ortho, items, gsd_cm)
    marks = m.run(img, c0, r0)
    if not marks:
        print("[INFO] Khong luu.")
        return

    rec, errs = [], []
    for i, (col, row) in marks.items():
        it = items[i]
        dc, dr = col - it["ocol"], row - it["orow"]
        e = np.hypot(dc, dr)
        errs.append(e)
        rec.append({"idx": it["idx"], "d_col": dc, "d_row": dr,
                    "err_px": e, "err_cm": e * gsd_cm})
    errs = np.array(errs)
    dcol = np.array([r["d_col"] for r in rec]); drow = np.array([r["d_row"] for r in rec])

    print("\n" + "=" * 60)
    print("  SAI SO END-TO-END CUA CA CHUOI")
    print("=" * 60)
    print(f"  So diem do : {len(errs)}")
    print(f"  Trung binh : {errs.mean():6.2f} px = {errs.mean()*gsd_cm:6.1f} cm")
    print(f"  Trung vi   : {np.median(errs):6.2f} px = {np.median(errs)*gsd_cm:6.1f} cm")
    print(f"  RMSE       : {np.sqrt((errs**2).mean()):6.2f} px = "
          f"{np.sqrt((errs**2).mean())*gsd_cm:6.1f} cm")
    print(f"  Lon nhat   : {errs.max():6.2f} px = {errs.max()*gsd_cm:6.1f} cm")
    print(f"  Lech he thong: dcol={dcol.mean():+.2f} drow={drow.mean():+.2f} px "
          f"({np.hypot(dcol.mean(), drow.mean())*gsd_cm:.1f} cm)")
    print("=" * 60)

    json.dump({"gsd_cm_per_px": gsd_cm, "label": args.label, "n": len(errs),
               "mean_cm": float(errs.mean() * gsd_cm),
               "median_cm": float(np.median(errs) * gsd_cm),
               "rmse_cm": float(np.sqrt((errs ** 2).mean()) * gsd_cm),
               "max_cm": float(errs.max() * gsd_cm),
               "bias_col_px": float(dcol.mean()), "bias_row_px": float(drow.mean()),
               "points": rec}, open(args.out, "w", encoding="utf-8"), indent=2)
    print(f"[DONE] Da luu {args.out}")


if __name__ == "__main__":
    main()
