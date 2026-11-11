#!/usr/bin/env python3
"""
Hiệu chuẩn ma trận Homography ánh xạ ảnh NHIỆT (thermal) -> ảnh RGB.

CÁCH DÙNG DỄ NHẤT (có dẫn đường):
  Công cụ nạp một ma trận khởi tạo (mặc định RTK350.txt). Bạn chỉ cần click lên
  ảnh NHIỆT, khung bên phải sẽ TỰ NHẢY tới đúng vùng tương ứng trên ảnh RGB ở
  tỉ lệ 1:1, kèm dấu + màu vàng là vị trí dự đoán. Bạn click vào đúng điểm thật.
  Khoảng lệch giữa dấu + và chỗ bạn click chính là sai số của ma trận khởi tạo.

  python ma/calib_thermal_rgb.py --thermal ..._T.JPG --rgb ..._W.JPG --xml cameras.xml --alt 31

Phím tắt:
  Chuột trái : click ảnh NHIỆT (trái) -> rồi click điểm tương ứng trên RGB (phải)
  1 / 2 / 3  : đổi độ phóng khung RGB (1x / 2x / 4x)
  Space      : bỏ điểm nhiệt đang chờ
  U          : xoá cặp điểm cuối
  C          : xoá hết
  H          : tính H, in sai số, xem ảnh chồng
  S          : lưu ra JSON
  Q / ESC    : thoát
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np

import goc  # dua tien trinh ve goc du an  # noqa: F401

DEFAULT_INIT = r"mo_hinh\RTK350.txt"


# ============================================================================
# 1. ĐỌC NỘI THAM SỐ RGB & UNDISTORT
# ============================================================================
def load_sensor_from_xml(xml_path, sensor_id="0"):
    root = ET.parse(xml_path).getroot()
    chunk = root.find(".//chunk")
    sensor = chunk.find(f".//sensor[@id='{sensor_id}']")
    if sensor is None:
        raise ValueError(f"Không tìm thấy sensor id={sensor_id} trong {xml_path}")
    res = sensor.find("resolution")
    calib = sensor.find("calibration[@class='adjusted']")
    if calib is None:
        calib = sensor.find("calibration")

    def g(tag, default=0.0):
        e = calib.find(tag)
        return float(e.text) if e is not None else default

    info = {"width": int(res.get("width")), "height": int(res.get("height")),
            "f": g("f"), "cx": g("cx"), "cy": g("cy"),
            "k1": g("k1"), "k2": g("k2"), "k3": g("k3"), "p1": g("p1"), "p2": g("p2")}
    print(f"[INFO] Sensor RGB: {info['width']}x{info['height']}, f={info['f']:.2f}, k1={info['k1']:.6f}")
    return info


def undistort_rgb(img, s):
    w, h = s["width"], s["height"]
    K = np.array([[s["f"], 0, w / 2 + s["cx"]], [0, s["f"], h / 2 + s["cy"]], [0, 0, 1.0]])
    dist = np.array([s["k1"], s["k2"], s["p1"], s["p2"], s["k3"]])
    return cv2.undistort(img, K, dist)


# ============================================================================
# 2. MA TRẬN KHỞI TẠO
# ============================================================================
def load_init_H(path, shape_rgb, shape_th):
    """Nạp ma trận khởi tạo. Chấp nhận RTK350.txt (dạng %) hoặc JSON đã lưu."""
    h_rgb, w_rgb = shape_rgb
    h_th, w_th = shape_th
    if not path or not os.path.exists(path):
        print("[INFO] Không có ma trận khởi tạo -> khung RGB sẽ căn theo tâm ảnh.")
        return None
    if path.lower().endswith(".json"):
        H = np.array(json.load(open(path))["H_thermal_to_rgb"], float)
    else:
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", open(path).read())]
        H_pct = np.array(nums[:9]).reshape(3, 3)
        H = (np.diag([w_rgb / 100.0, h_rgb / 100.0, 1.0]) @ H_pct
             @ np.diag([100.0 / w_th, 100.0 / h_th, 1.0]))
    print(f"[INFO] Ma trận khởi tạo từ {os.path.basename(path)}: "
          f"phóng đại {H[0,0]:.3f}/{H[1,1]:.3f}, dịch ({H[0,2]:.0f}, {H[1,2]:.0f}) px")
    return H


def apply_H(H, x, y):
    p = H @ np.array([x, y, 1.0])
    return p[0] / p[2], p[1] / p[2]


def wheel_delta(flags):
    """OpenCV 5 bỏ cv2.getMouseWheelDelta -> tự tách 16 bit cao của flags."""
    try:
        return cv2.getMouseWheelDelta(flags)
    except AttributeError:
        d = (flags >> 16) & 0xFFFF
        return d - 0x10000 if d >= 0x8000 else d


# ============================================================================
# 3. TÍNH H & BÁO SAI SỐ
# ============================================================================
def compute_homography(pts_th, pts_rgb, gsd_cm=None, H_init=None):
    if len(pts_th) < 4:
        print(f"[ERROR] Cần tối thiểu 4 cặp điểm (đang có {len(pts_th)}). Nên có >= 10.")
        return None
    src = np.array(pts_th, np.float64).reshape(-1, 1, 2)
    dst = np.array(pts_rgb, np.float64).reshape(-1, 1, 2)

    # Ngưỡng RANSAC phải NỚI (12 px) — chỉ để loại điểm chấm sai thô.
    # Đặt chặt (3 px) sẽ vứt luôn các điểm ở rìa vốn lệch do méo ống kính nhiệt,
    # khiến H fit trên một nhóm nhỏ và mất ổn định.
    _, inl = cv2.findHomography(src, dst, cv2.RANSAC, 12.0)
    if inl is None or inl.sum() < 4:
        inl = np.ones((len(pts_th), 1), np.uint8)
    keep = inl.ravel().astype(bool)
    # Ước lượng cuối bằng bình phương tối thiểu trên các điểm còn lại
    H, _ = cv2.findHomography(src[keep], dst[keep], 0)
    if H is None:
        print("[ERROR] Không tính được homography.")
        return None

    err = np.linalg.norm(cv2.perspectiveTransform(src, H).reshape(-1, 2) - np.array(pts_rgb), axis=1)
    rmse = float(np.sqrt((err ** 2).mean()))

    print("\n" + "=" * 66)
    print("  KẾT QUẢ HIỆU CHUẨN (thermal -> RGB)")
    print("=" * 66)
    print(f"  Số cặp điểm : {len(pts_th)} (dung {int(keep.sum())}, loai {int((~keep).sum())} diem sai tho)")
    print(f"  RMSE        : {rmse:.2f} px" + (f"  = {rmse*gsd_cm:.1f} cm" if gsd_cm else ""))
    print(f"  Trung vi    : {np.median(err):.2f} px"
          + (f"  = {np.median(err)*gsd_cm:.1f} cm" if gsd_cm else ""))
    print(f"  Lon nhat    : {err.max():.2f} px")
    print("-" * 66)
    for i, (e, ok) in enumerate(zip(err, keep)):
        print(f"   #{i:02d}  {e:6.2f} px   {'' if ok else '<-- SAI THO, nen xoa/cham lai'}")
    print("-" * 66)
    print("  H =")
    for r in H:
        print("   [{:11.5f} {:11.5f} {:11.3f}]".format(*r))
    if H_init is not None:
        print(f"\n  So voi ma tran khoi tao:")
        print(f"    phong dai : {H[0,0]:.3f}/{H[1,1]:.3f}  (khoi tao {H_init[0,0]:.3f}/{H_init[1,1]:.3f})")
        print(f"    dich      : ({H[0,2]:.0f}, {H[1,2]:.0f})  (khoi tao ({H_init[0,2]:.0f}, {H_init[1,2]:.0f}))")
        print(f"    => chenh lech dich: dx={H[0,2]-H_init[0,2]:+.0f}  dy={H[1,2]-H_init[1,2]:+.0f} px")
    print("=" * 66 + "\n")

    if rmse > 5:
        print("[WARN] RMSE > 5 px: diem cham chua chuan hoac don vao giua anh.\n")
    return H, err, inl, rmse


# ============================================================================
# 4. ẢNH CHỒNG KIỂM TRA
# ============================================================================
def show_overlay(th, rgb, H, win="CHONG ANH - nhan phim bat ky de dong"):
    h_r, w_r = rgb.shape[:2]
    gray = cv2.cvtColor(th, cv2.COLOR_BGR2GRAY) if th.ndim == 3 else th
    col = cv2.applyColorMap(cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                            cv2.COLORMAP_INFERNO)
    warped = cv2.warpPerspective(col, H, (w_r, h_r))
    mask = cv2.warpPerspective(np.full(gray.shape, 255, np.uint8), H, (w_r, h_r))
    m3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) > 0

    out = rgb.copy()
    b = cv2.addWeighted(warped, 0.45, rgb, 0.55, 0)
    out[m3] = b[m3]
    e = cv2.dilate(cv2.Canny(cv2.warpPerspective(gray, H, (w_r, h_r)), 50, 150),
                   np.ones((2, 2), np.uint8))
    out[e > 0] = (0, 0, 255)

    sc = min(1.0, 1500.0 / w_r, 900.0 / h_r)
    disp = cv2.resize(out, None, fx=sc, fy=sc)
    cv2.putText(disp, "DO = bien anh nhiet sau warp", (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(win, 60, 60)
    cv2.imshow(win, disp)
    cv2.waitKey(0)
    cv2.destroyWindow(win)


# ============================================================================
# 5. KHUNG NHÌN CÓ PHÓNG TO / KÉO ẢNH
# ============================================================================
class Viewport:
    """Một khung hiển thị ảnh full, lăn chuột để phóng, giữ chuột phải để kéo."""

    def __init__(self, img, pw, ph):
        self.img = img
        self.pw, self.ph = pw, ph
        # tháp ảnh thu nhỏ để khi zoom nhỏ không bị răng cưa
        self.pyr = [img]
        for _ in range(3):
            self.pyr.append(cv2.pyrDown(self.pyr[-1]))
        self.fit()

    @property
    def size(self):
        h, w = self.img.shape[:2]
        return w, h

    def fit(self):
        w, h = self.size
        self.z = min(self.pw / w, self.ph / h)
        self.tx = (self.pw - self.z * w) / 2.0
        self.ty = (self.ph - self.z * h) / 2.0

    # --- đổi qua lại giữa toạ độ hiển thị và toạ độ ảnh gốc ---
    def to_img(self, dx, dy):
        return (dx - self.tx) / self.z, (dy - self.ty) / self.z

    def to_disp(self, ix, iy):
        return self.z * ix + self.tx, self.z * iy + self.ty

    def zoom_at(self, dx, dy, factor):
        ix, iy = self.to_img(dx, dy)
        self.z = float(np.clip(self.z * factor, 0.05, 24.0))
        self.tx, self.ty = dx - self.z * ix, dy - self.z * iy

    def pan(self, ddx, ddy):
        self.tx += ddx
        self.ty += ddy

    def center_on(self, ix, iy):
        self.tx = self.pw / 2.0 - self.z * ix
        self.ty = self.ph / 2.0 - self.z * iy

    def render(self):
        lvl = int(np.clip(np.floor(np.log2(1.0 / max(self.z, 1e-6))), 0, len(self.pyr) - 1))
        s = 2 ** lvl
        M = np.array([[self.z * s, 0, self.tx], [0, self.z * s, self.ty]], np.float32)
        interp = cv2.INTER_NEAREST if self.z >= 1.5 else cv2.INTER_LINEAR
        return cv2.warpAffine(self.pyr[lvl], M, (self.pw, self.ph), flags=interp,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(32, 32, 32))


# ============================================================================
# 6. GIAO DIỆN CHẤM ĐIỂM
# ============================================================================
class GuidedPicker:
    WIN = "CHAM DIEM  |  TRAI = anh NHIET     PHAI = anh RGB"
    BAR = 46
    GAP = 8

    def __init__(self, th, rgb, H_init, panel=(840, 720), gsd_cm=None):
        self.th_raw, self.rgb, self.H_init, self.gsd_cm = th, rgb, H_init, gsd_cm
        self.PW, self.PH = panel

        gray = cv2.cvtColor(th, cv2.COLOR_BGR2GRAY) if th.ndim == 3 else th
        th_col = cv2.applyColorMap(
            cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
            cv2.COLORMAP_INFERNO)

        self.vL = Viewport(th_col, self.PW, self.PH)
        self.vR = Viewport(rgb, self.PW, self.PH)
        self.ROFF = self.PW + self.GAP

        self.pts_th, self.pts_rgb = [], []
        self.pending = None
        self.pred = None
        self.cur = (0, 0)
        self.drag = None
        self.H = None

    # ------------------------------------------------------------------ vẽ
    def _draw_left(self):
        v = self.vL.render()
        for i, (u, y) in enumerate(self.pts_th):
            p = tuple(int(c) for c in self.vL.to_disp(u, y))
            cv2.drawMarker(v, p, (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
            cv2.putText(v, str(i), (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 2)
        if self.pending:
            p = tuple(int(c) for c in self.vL.to_disp(*self.pending))
            cv2.drawMarker(v, p, (0, 220, 255), cv2.MARKER_TILTED_CROSS, 22, 2)
            cv2.circle(v, p, 15, (0, 220, 255), 1)
        self._crosshair(v, 0)
        cv2.putText(v, f"NHIET  {self.vL.z:.1f}x", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if self.pending is None:
            cv2.rectangle(v, (0, 0), (self.PW - 1, self.PH - 1), (0, 255, 0), 6)
        return v

    def _draw_right(self):
        v = self.vR.render()
        for i, (u, y) in enumerate(self.pts_rgb):
            p = tuple(int(c) for c in self.vR.to_disp(u, y))
            cv2.drawMarker(v, p, (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
            cv2.putText(v, str(i), (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 2)
        if self.pred is not None:
            gx, gy = (int(c) for c in self.vR.to_disp(*self.pred))
            if 0 <= gx < self.PW and 0 <= gy < self.PH:
                for rad, th_ in ((34, 2), (52, 1)):
                    cv2.circle(v, (gx, gy), rad, (0, 220, 255), th_)
                cv2.line(v, (gx - 30, gy), (gx + 30, gy), (0, 220, 255), 2)
                cv2.line(v, (gx, gy - 30), (gx, gy + 30), (0, 220, 255), 2)
                cv2.putText(v, "CLICK QUANH DAY", (gx + 40, gy - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
            else:
                # dự đoán nằm ngoài khung -> vẽ mũi tên chỉ hướng
                cx, cy = self.PW // 2, self.PH // 2
                d = np.array([gx - cx, gy - cy], float)
                d /= (np.linalg.norm(d) + 1e-6)
                p2 = (int(cx + d[0] * 260), int(cy + d[1] * 260))
                cv2.arrowedLine(v, (cx, cy), p2, (0, 220, 255), 3, tipLength=0.25)
                cv2.putText(v, "Bam G de nhay toi diem du doan", (cx - 190, cy - 26),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
        self._crosshair(v, self.ROFF)
        cv2.putText(v, f"RGB  {self.vR.z:.1f}x", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if self.pending is not None:
            cv2.rectangle(v, (0, 0), (self.PW - 1, self.PH - 1), (0, 220, 255), 6)
        return v

    def _crosshair(self, v, off):
        mx, my = self.cur
        x = mx - off
        if 0 <= x < self.PW and 0 <= my < self.PH:
            cv2.line(v, (x, 0), (x, self.PH), (255, 255, 255), 1)
            cv2.line(v, (0, my), (self.PW, my), (255, 255, 255), 1)

    def _canvas(self):
        gap = np.full((self.PH, self.GAP, 3), 70, np.uint8)
        body = np.hstack([self._draw_left(), gap, self._draw_right()])
        bar = np.full((self.BAR, body.shape[1], 3), 25, np.uint8)
        if self.pending is None:
            msg, col = (f"[{len(self.pts_th)} cap]  >>> CLICK BEN TRAI (anh NHIET) <<<  "
                        f"vien XANH LA = ben dang cho click", (0, 255, 0))
        else:
            msg, col = (f"[{len(self.pts_th)} cap]  >>> CLICK BEN PHAI (anh RGB) <<<  "
                        f"vien VANG = ben dang cho click   [G = nhay toi du doan]"), (0, 220, 255)
        cv2.putText(bar, msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62, col, 2)
        cv2.putText(bar, "Lan chuot hoac W/X = phong to/nho   Chuot phai keo = di chuyen   "
                         "F=vua khung  G=nhay toi du doan  U=undo  H=tinh  S=luu  Q=thoat",
                    (max(12, body.shape[1] - 980), 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        return np.vstack([bar, body])

    # -------------------------------------------------------------- sự kiện
    def _vp(self, x):
        if x < self.PW:
            return self.vL, 0
        if x >= self.ROFF:
            return self.vR, self.ROFF
        return None, 0

    def _zoom_at_cursor(self, factor):
        """Phóng tại vị trí con trỏ hiện tại (self.cur đã trừ thanh trạng thái)."""
        mx, my = self.cur
        vp, off = self._vp(mx)
        if vp is None or not (0 <= my < self.PH):
            return
        vp.zoom_at(mx - off, my, factor)

    def _mouse(self, event, x, y, flags, param):
        # OpenCV tren Windows tra ve TOA DO MAN HINH cho su kien lan chuot,
        # nen phai dung vi tri ghi lai tu lan di chuot gan nhat.
        if event == cv2.EVENT_MOUSEWHEEL:
            self._zoom_at_cursor(1.25 if wheel_delta(flags) > 0 else 1 / 1.25)
            return

        y -= self.BAR
        self.cur = (x, y)
        vp, off = self._vp(x)
        if vp is None or y < 0:
            return

        if event == cv2.EVENT_RBUTTONDOWN:
            self.drag = (vp, x, y)
            return
        if event == cv2.EVENT_RBUTTONUP:
            self.drag = None
            return
        if event == cv2.EVENT_MOUSEMOVE and self.drag is not None:
            v0, px, py = self.drag
            v0.pan(x - px, y - py)
            self.drag = (v0, x, y)
            return

        if event != cv2.EVENT_LBUTTONDOWN:
            return

        if vp is self.vL:
            if self.pending is not None:
                print("  [!] Dang cho diem RGB. Click ben phai, hoac Space de bo.")
                return
            tx, ty = self.vL.to_img(x, y)
            w, h = self.vL.size
            if not (0 <= tx < w and 0 <= ty < h):
                return
            self.pending = (tx, ty)
            self.pred = (apply_H(self.H_init, tx, ty) if self.H_init is not None
                         else (self.rgb.shape[1] / 2, self.rgb.shape[0] / 2))
            print(f"  nhiet ({tx:7.2f},{ty:7.2f}) -> du doan RGB "
                  f"({self.pred[0]:7.1f},{self.pred[1]:7.1f})   [G de nhay toi]")
        else:
            if self.pending is None:
                print("  [!] Click ben anh NHIET truoc.")
                return
            ux, uy = self.vR.to_img(x - self.ROFF, y)
            w, h = self.vR.size
            if not (0 <= ux < w and 0 <= uy < h):
                return
            dx, dy = ux - self.pred[0], uy - self.pred[1]
            self.pts_th.append(self.pending)
            self.pts_rgb.append((ux, uy))
            print(f"  => cap #{len(self.pts_th)-1:02d}  RGB ({ux:7.1f},{uy:7.1f})   "
                  f"lech so voi du doan: dx={dx:+6.1f} dy={dy:+6.1f} px")
            self.pending, self.pred = None, None

    # ------------------------------------------------------------------ run
    def run(self):
        cv2.namedWindow(self.WIN, cv2.WINDOW_AUTOSIZE)
        # OpenCV nho vi tri cua so lan truoc; neu lan truoc o man phu da rut thi
        # cua so se mo ra ngoai vung nhin thay duoc -> ep ve goc tren trai man chinh.
        cv2.moveWindow(self.WIN, 30, 30)
        cv2.setMouseCallback(self.WIN, self._mouse)
        print("\n" + "=" * 70)
        print("  Ca hai ben hien anh FULL. Lan chuot de phong to/thu nho tai vi tri con tro,")
        print("  giu CHUOT PHAI keo de di chuyen anh, F de ve vua khung.")
        print("  Click diem tren anh NHIET -> dau + VANG hien vi tri du doan tren RGB")
        print("  (bam G de nhay khung RGB toi do). Click dung diem that tren RGB.")
        print("  Nen cham ~12 cap, RAI DEU ra 4 goc anh nhiet.")
        print("=" * 70 + "\n")

        while True:
            cv2.imshow(self.WIN, self._canvas())
            k = cv2.waitKey(20) & 0xFF

            if k == ord(' '):
                self.pending, self.pred = None, None
            elif k in (ord('+'), ord('='), ord('w'), ord('W')):
                self._zoom_at_cursor(1.35)
            elif k in (ord('-'), ord('_'), ord('x'), ord('X')):
                self._zoom_at_cursor(1 / 1.35)
            elif k in (ord('f'), ord('F')):
                vp, _ = self._vp(self.cur[0])
                (vp or self.vL).fit()
            elif k in (ord('g'), ord('G')):
                if self.pred is not None:
                    if self.vR.z < 2.0:
                        self.vR.z = 3.0
                    self.vR.center_on(*self.pred)
            elif k in (ord('u'), ord('U')):
                if self.pending is not None:
                    self.pending, self.pred = None, None
                elif self.pts_th:
                    self.pts_th.pop(); self.pts_rgb.pop()
                    print(f"  [x] Da xoa cap cuoi, con {len(self.pts_th)}")
            elif k in (ord('c'), ord('C')):
                self.pts_th.clear(); self.pts_rgb.clear()
                self.pending = self.pred = None
            elif k in (ord('h'), ord('H')):
                r = compute_homography(self.pts_th, self.pts_rgb, self.gsd_cm, self.H_init)
                if r:
                    self.H = r[0]
                    show_overlay(self.th_raw, self.rgb, self.H)
            elif k in (ord('s'), ord('S')):
                if self.H is None:
                    r = compute_homography(self.pts_th, self.pts_rgb, self.gsd_cm, self.H_init)
                    self.H = r[0] if r else None
                if self.H is not None:
                    cv2.destroyWindow(self.WIN)
                    return self.H, self.pts_th, self.pts_rgb
            elif k in (ord('q'), ord('Q'), 27):
                cv2.destroyWindow(self.WIN)
                return None, self.pts_th, self.pts_rgb


# ============================================================================
# MAIN
# ============================================================================
def main():
    ap = argparse.ArgumentParser(description="Hiệu chuẩn homography thermal -> RGB")
    ap.add_argument("--rgb", required=True)
    ap.add_argument("--thermal", required=True)
    ap.add_argument("--xml", default=None, help="cameras XML -> undistort ảnh RGB (NÊN DÙNG)")
    ap.add_argument("--init", default=DEFAULT_INIT, help="Ma trận khởi tạo (RTK350.txt hoặc .json)")
    ap.add_argument("--out", default="ket_qua/thermal_to_rgb.json")
    ap.add_argument("--resume", action="store_true",
                    help="Nạp lại các điểm đã chấm trong --out để chấm tiếp")
    ap.add_argument("--check", action="store_true", help="Chỉ xem ảnh chồng của ma trận khởi tạo rồi thoát")
    ap.add_argument("--alt", type=float, default=None, help="Độ cao bay (m) để quy sai số ra cm")
    ap.add_argument("--panel", type=int, nargs=2, default=[840, 720], help="Kích thước mỗi khung")
    args = ap.parse_args()

    rgb = cv2.imread(args.rgb)
    th = cv2.imread(args.thermal)
    if rgb is None:
        sys.exit(f"[ERROR] Không đọc được ảnh RGB: {args.rgb}")
    if th is None:
        sys.exit(f"[ERROR] Không đọc được ảnh nhiệt: {args.thermal}")
    print(f"[INFO] RGB {rgb.shape[1]}x{rgb.shape[0]} | Thermal {th.shape[1]}x{th.shape[0]}")

    gsd_cm = None
    if args.xml:
        s = load_sensor_from_xml(args.xml)
        rgb = undistort_rgb(rgb, s)
        print("[INFO] Đã undistort ảnh RGB theo hiệu chuẩn Metashape.")
        if args.alt:
            gsd_cm = args.alt / s["f"] * 100.0
            print(f"[INFO] GSD RGB ~ {gsd_cm:.2f} cm/px tại độ cao {args.alt:.0f} m")
    else:
        print("[WARN] Không có --xml: H sẽ ứng với ảnh RGB còn méo.")

    H_init = load_init_H(args.init, rgb.shape[:2], th.shape[:2])

    if args.check:
        if H_init is None:
            sys.exit("[ERROR] --check cần --init")
        show_overlay(th, rgb, H_init)
        return

    picker = GuidedPicker(th, rgb, H_init, tuple(args.panel), gsd_cm)
    if args.resume and os.path.exists(args.out):
        old = json.load(open(args.out, encoding="utf-8"))
        picker.pts_th = [tuple(p) for p in old.get("points_thermal", [])]
        picker.pts_rgb = [tuple(p) for p in old.get("points_rgb", [])]
        print(f"[INFO] Đã nạp lại {len(picker.pts_th)} cặp điểm từ {args.out}")
        ys = [p[1] for p in picker.pts_th]
        if ys:
            gaps = [f"y {lo}-{hi}: {sum(lo <= y < hi for y in ys)} diem"
                    for lo, hi in ((0, 128), (128, 256), (256, 384), (384, 512))]
            print("[INFO] Phan bo theo chieu doc anh nhiet -> " + " | ".join(gaps))

    H, pts_th, pts_rgb = picker.run()
    if H is None:
        print("[INFO] Không lưu (người dùng thoát).")
        return

    err = np.linalg.norm(
        cv2.perspectiveTransform(np.array(pts_th, np.float64).reshape(-1, 1, 2), H).reshape(-1, 2)
        - np.array(pts_rgb, np.float64), axis=1)
    json.dump({
        "H_thermal_to_rgb": H.tolist(),
        "rgb_undistorted": bool(args.xml),
        "rgb_size": [rgb.shape[1], rgb.shape[0]],
        "thermal_size": [th.shape[1], th.shape[0]],
        "n_points": len(pts_th),
        "rmse_px": float(np.sqrt((err ** 2).mean())),
        "max_err_px": float(err.max()),
        "gsd_cm_per_px": gsd_cm,
        "points_thermal": [[float(a), float(b)] for a, b in pts_th],
        "points_rgb": [[float(a), float(b)] for a, b in pts_rgb],
        "src_rgb": os.path.basename(args.rgb),
        "src_thermal": os.path.basename(args.thermal),
        "init_matrix": os.path.basename(args.init) if H_init is not None else None,
    }, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[DONE] Đã lưu: {args.out}")


if __name__ == "__main__":
    main()
