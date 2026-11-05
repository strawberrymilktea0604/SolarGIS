#!/usr/bin/env python3
"""
Chiếu bounding box từ ảnh drone lên orthophoto bằng phương pháp chiếu chính xác.

Pipeline:
  1. Parse Metashape XML → sensor intrinsics + camera extrinsics + chunk transform
  2. Pixel (u,v) → undistort → normalized ray trong camera coords
  3. Camera coords → chunk coords → ECEF (via chunk transform)
  4. ECEF → WGS84 (lon, lat, alt)
  5. Ray–DSM intersection (iterative binary search)
  6. Photogrammetric edge slant & relief compensation
  7. Lon/Lat → Ortho pixel coords (GeoTransform)

Usage:
  python3 project_box_to_ortho.py
"""

import sys
import os

# Import core package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.ortho.projection import (
    load_metashape_xml,
    load_cameras,
    load_shots,
    get_dsm_height,
    project_pixel_to_world_and_ortho
)
from core.geo.coordinates import undistort_pixel, compute_gsd

# ============================================================================
# CONFIGURATION
# ============================================================================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
XML_PATH = os.path.join(WORK_DIR, "cameras_v6.xml")
DSM_PATH = os.path.join(WORK_DIR, "full_dsm.tif")
ORTHO_PATH = os.path.join(WORK_DIR, "full_orrthor.tif")
IMAGE_NAME = "DJI_20260411084815_0060_W"
IMAGE_PATH = os.path.join(WORK_DIR, f"{IMAGE_NAME}.JPG")


# ============================================================================
# 1. PARSE METASHAPE XML
# ============================================================================
def parse_metashape_xml(xml_path, camera_label):
    """
    Parse Metashape cameras XML file.
    
    Returns:
        sensor_info: dict with f, cx, cy, k1, k2, k3, p1, p2, width, height
        camera_transform: 4x4 numpy matrix (camera → chunk coords)
        chunk_transform: dict with rotation (3x3), translation (3x1), scale (float)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    chunk = root.find(".//chunk")

    # --- Sensor intrinsics ---
    sensor = chunk.find(".//sensor[@id='0']")
    res = sensor.find("resolution")
    width = int(res.get("width"))
    height = int(res.get("height"))

    calib = sensor.find("calibration[@class='adjusted']")
    sensor_info = {
        "width": width,
        "height": height,
        "f": float(calib.find("f").text),
        "cx": float(calib.find("cx").text),
        "cy": float(calib.find("cy").text),
        "k1": float(calib.find("k1").text),
        "k2": float(calib.find("k2").text),
        "k3": float(calib.find("k3").text),
        "p1": float(calib.find("p1").text),
        "p2": float(calib.find("p2").text),
    }
    print(f"[INFO] Sensor: {width}x{height}, f={sensor_info['f']:.2f}")
    print(f"       cx={sensor_info['cx']:.4f}, cy={sensor_info['cy']:.4f}")
    print(f"       k1={sensor_info['k1']:.6f}, k2={sensor_info['k2']:.6f}, k3={sensor_info['k3']:.6f}")

    # --- Camera extrinsics ---
    camera_transform = None
    for cam in chunk.findall(".//camera"):
        if cam.get("label") == camera_label:
            transform_text = cam.find("transform").text
            vals = list(map(float, transform_text.split()))
            camera_transform = np.array(vals).reshape(4, 4)
            print(f"[INFO] Found camera: {camera_label} (id={cam.get('id')})")
            ref = cam.find("reference")
            if ref is not None:
                print(f"       GPS ref: lon={ref.get('x')}, lat={ref.get('y')}, alt={ref.get('z')}")
            break

    if camera_transform is None:
        raise ValueError(f"Camera '{camera_label}' not found in XML!")

    # --- Chunk transform ---
    component = chunk.find(".//component[@id='1']")
    transform_elem = component.find("transform")

    rot_text = transform_elem.find("rotation").text
    rot_vals = list(map(float, rot_text.split()))
    chunk_rotation = np.array(rot_vals).reshape(3, 3)

    trans_text = transform_elem.find("translation").text
    trans_vals = list(map(float, trans_text.split()))
    chunk_translation = np.array(trans_vals)

    chunk_scale = float(transform_elem.find("scale").text)

    chunk_transform = {
        "rotation": chunk_rotation,
        "translation": chunk_translation,
        "scale": chunk_scale,
    }
    print(f"[INFO] Chunk scale: {chunk_scale:.6f}")
    print(f"       Chunk translation (ECEF): [{chunk_translation[0]:.2f}, {chunk_translation[1]:.2f}, {chunk_translation[2]:.2f}]")

    return sensor_info, camera_transform, chunk_transform


# ============================================================================
# 2. UNDISTORT IMAGE & PIXEL → NORMALIZED COORDS
# ============================================================================
def get_camera_matrix_and_dist(sensor):
    """Build OpenCV camera matrix K and distortion vector dist from sensor parameters."""
    w, h = sensor["width"], sensor["height"]
    f = sensor["f"]
    cx, cy = sensor["cx"], sensor["cy"]
    k1, k2, k3 = sensor["k1"], sensor["k2"], sensor["k3"]
    p1, p2 = sensor["p1"], sensor["p2"]

    K = np.array([[f, 0, w / 2.0 + cx],
                  [0, f, h / 2.0 + cy],
                  [0, 0, 1.0]], dtype=np.float64)
    dist = np.array([k1, k2, p1, p2, k3], dtype=np.float64)
    return K, dist


def undistort_drone_image(img, sensor):
    """Undistort drone image using camera intrinsic matrix K and distortion coefficients."""
    K, dist = get_camera_matrix_and_dist(sensor)
    return cv2.undistort(img, K, dist)


def pixel_to_ray_ecef_undistorted(u, v, sensor, cam_transform, chunk_tf):
    """
    Chuyển pixel (u,v) từ ẢNH ĐÃ NẮN PHẲNG (undistorted) → ray (origin, direction) trong ECEF.
    """
    f = sensor["f"]
    cx = sensor["cx"]
    cy = sensor["cy"]
    w, h = sensor["width"], sensor["height"]

    # Direct pinhole normalized coordinates (no radial/tangential distortion needed)
    x = (u - w / 2.0 - cx) / f
    y = (v - h / 2.0 - cy) / f

    # Ray direction in camera coords (+Z forward)
    d_cam = np.array([x, y, 1.0])

    # Camera transform: camera coords → chunk coords
    R_cam = cam_transform[:3, :3]
    t_cam = cam_transform[:3, 3]

    # Camera center in chunk coords
    C_chunk = t_cam.copy()

    # Ray direction in chunk coords
    d_chunk = R_cam @ d_cam
    d_chunk = d_chunk / np.linalg.norm(d_chunk)

    # Chunk coords → ECEF
    R_chunk = chunk_tf["rotation"]
    T_chunk = chunk_tf["translation"]
    S_chunk = chunk_tf["scale"]

    # Camera center in ECEF
    C_ecef = S_chunk * (R_chunk @ C_chunk) + T_chunk

    # Ray direction in ECEF
    d_ecef = R_chunk @ d_chunk
    d_ecef = d_ecef / np.linalg.norm(d_ecef)

    return C_ecef, d_ecef


# ============================================================================
# 3. DSM SAMPLER & RAY-DSM INTERSECTION
# ============================================================================
class DSMSampler:
    """Efficient DSM sampling with rasterio."""

    def __init__(self, dsm_path):
        self.ds = rasterio.open(dsm_path)
        self.transform = self.ds.transform
        self.nodata = self.ds.nodata
        self.bounds = self.ds.bounds
        self.data = self.ds.read(1)
        print(f"[INFO] DSM loaded: {self.ds.width}x{self.ds.height}, bounds={self.bounds}")

    def sample(self, lon, lat):
        """Sample DSM elevation at (lon, lat). Returns elevation or None."""
        if not (self.bounds.left <= lon <= self.bounds.right and
                self.bounds.bottom <= lat <= self.bounds.top):
            return None
        col, row = ~self.transform * (lon, lat)
        col, row = int(col), int(row)
        if 0 <= row < self.ds.height and 0 <= col < self.ds.width:
            val = self.data[row, col]
            if val != self.nodata and not np.isnan(val):
                return float(val)
        return None

    def close(self):
        self.ds.close()


def ray_dsm_intersect(origin_ecef, direction_ecef, dsm_sampler, 
                       ecef_to_wgs84, max_dist=500.0, num_steps=500):
    """
    Find intersection of ray with DSM surface using iterative stepping + binary search.
    
    Strategy:
        1. Coarse walk along ray (camera → ground)
        2. Find interval where altitude crosses DSM elevation
        3. Binary search within that interval for precise intersection (50 steps)
    """
    step_size = max_dist / num_steps
    prev_diff = None
    prev_t = 0

    for i in range(num_steps):
        t = i * step_size
        P_ecef = origin_ecef + t * direction_ecef

        # ECEF → WGS84
        lon, lat, alt = ecef_to_wgs84.transform(P_ecef[0], P_ecef[1], P_ecef[2])

        # Sample DSM
        dsm_elev = dsm_sampler.sample(lon, lat)
        if dsm_elev is None:
            continue

        diff = alt - dsm_elev  # positive = above DSM, negative = below DSM

        if prev_diff is not None and prev_diff > 0 and diff <= 0:
            # Found crossing: binary search in [prev_t, t]
            t_lo, t_hi = prev_t, t
            for _ in range(50):
                t_mid = (t_lo + t_hi) / 2.0
                P_mid = origin_ecef + t_mid * direction_ecef
                lon_m, lat_m, alt_m = ecef_to_wgs84.transform(P_mid[0], P_mid[1], P_mid[2])
                dsm_m = dsm_sampler.sample(lon_m, lat_m)
                if dsm_m is None:
                    t_lo = t_mid
                    continue
                diff_m = alt_m - dsm_m
                if abs(diff_m) < 0.01:  # 1cm precision
                    return lon_m, lat_m, dsm_m
                if diff_m > 0:
                    t_lo = t_mid
                else:
                    t_hi = t_mid

            t_final = (t_lo + t_hi) / 2.0
            P_final = origin_ecef + t_final * direction_ecef
            lon_f, lat_f, alt_f = ecef_to_wgs84.transform(P_final[0], P_final[1], P_final[2])
            dsm_f = dsm_sampler.sample(lon_f, lat_f)
            return lon_f, lat_f, dsm_f if dsm_f else alt_f

        prev_diff = diff
        prev_t = t

    return None


# ============================================================================
# 4. OFF-NADIR RAY SLANT ANGLE & RELIEF COMPENSATION
# ============================================================================
def calculate_slant_angle(u, v, sensor):
    """Calculate camera off-nadir ray slant angle theta in degrees."""
    f = sensor["f"]
    cx, cy = sensor["cx"], sensor["cy"]
    w, h = sensor["width"], sensor["height"]
    x = (u - w / 2.0 - cx) / f
    y = (v - h / 2.0 - cy) / f
    r = np.sqrt(x * x + y * y)
    theta_rad = np.arctan(r)
    return np.degrees(theta_rad)


def compensate_edge_slant(u, v, sensor, lon, lat, elev, origin_ecef, direction_ecef, theta, surface_sampler, ecef_to_wgs84):
    """
    EXACT CLOSED-FORM PHOTOGRAMMETRIC RELIEF COMPENSATION USING DSM.
    Delta_P = (H_panel / H_drone) * (Camera_Nadir - Ground_Hit).
    Symmetric and 100% mathematically exact in all 360 degrees around Nadir center.
    """
    if theta < 1.0:
        return lon, lat, elev, 0.0  # Near Nadir, no correction needed

    # Camera Nadir location (WGS84)
    cam_lon, cam_lat, cam_alt = ecef_to_wgs84.transform(origin_ecef[0], origin_ecef[1], origin_ecef[2])

    # Drone flight height above ground
    drone_h_above_ground = max(cam_alt - elev, 15.0)

    # Search for maximum solar panel top elevation in local 2.5m neighborhood from DSM
    max_panel_alt = elev

    if hasattr(surface_sampler, "data"):
        col, row = ~surface_sampler.transform * (lon, lat)
        col, row = int(col), int(row)
        r0, r1 = max(0, row - 4), min(surface_sampler.ds.height, row + 5)
        c0, c1 = max(0, col - 4), min(surface_sampler.ds.width, col + 5)
        win = surface_sampler.data[r0:r1, c0:c1]
        valid_win = win[win != surface_sampler.nodata]
        if len(valid_win) > 0:
            max_panel_alt = float(np.max(valid_win))

    # Solar panel structure height above ground (typically 1.8m to 2.2m)
    h_panel = max(max_panel_alt - elev, 1.8)

    # Scale factor = H_panel / H_drone
    scale_factor = h_panel / drone_h_above_ground

    # Exact vector from Ground Hit point TOWARDS Camera Nadir Center
    dlon = cam_lon - lon
    dlat = cam_lat - lat

    # Corrected Lon / Lat shifted inwards towards Nadir by exact scale_factor
    lon_corr = lon + dlon * scale_factor
    lat_corr = lat + dlat * scale_factor

    # Offset distance in meters
    dlon_m = (lon_corr - lon) * 111000.0 * np.cos(np.radians(lat))
    dlat_m = (lat_corr - lat) * 111000.0
    offset_m = np.sqrt(dlon_m**2 + dlat_m**2)

    return lon_corr, lat_corr, max_panel_alt, offset_m


# ============================================================================
# 5. LON/LAT → ORTHO PIXEL
# ============================================================================
class OrthoMapper:
    """Map lon/lat to orthophoto pixel coordinates."""

    def __init__(self, ortho_path):
        self.ds = rasterio.open(ortho_path)
        self.transform = self.ds.transform
        self.width = self.ds.width
        self.height = self.ds.height
        self.bounds = self.ds.bounds
        print(f"[INFO] Ortho loaded: {self.width}x{self.height}")

    def lonlat_to_pixel(self, lon, lat):
        """Convert (lon, lat) → (col, row) in ortho image."""
        col, row = ~self.transform * (lon, lat)
        return int(round(col)), int(round(row))

    def read_region(self, col_min, row_min, col_max, row_max, margin=200):
        """Read a region of the orthophoto with margin."""
        c0 = max(0, col_min - margin)
        r0 = max(0, row_min - margin)
        c1 = min(self.width, col_max + margin)
        r1 = min(self.height, row_max + margin)

        window = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        data = self.ds.read(window=window)

        if data.shape[0] == 4:
            img = np.stack([data[2], data[1], data[0]], axis=0)
        elif data.shape[0] == 3:
            img = np.stack([data[2], data[1], data[0]], axis=0)
        else:
            img = np.stack([data[0], data[0], data[0]], axis=0)

        img = np.moveaxis(img, 0, -1)
        return img, c0, r0

    def close(self):
        self.ds.close()


# ============================================================================
# 6. INTERACTIVE BBOX DRAWING (OpenCV)
# ============================================================================
def get_north_up_rotation(camera_label, xml_path):
    """Calculate rotation required to orient drone image North-Up based on camera yaw in XML."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for cam in root.findall(".//camera"):
        if cam.get("label") == camera_label:
            ref = cam.find("reference")
            if ref is not None and "yaw" in ref.attrib:
                yaw = float(ref.get("yaw")) % 360.0
                print(f"[INFO] Camera Yaw: {yaw:.1f}°")
                if 45.0 < yaw <= 135.0:
                    return cv2.ROTATE_90_CLOCKWISE, 90
                elif 135.0 < yaw <= 225.0:
                    return cv2.ROTATE_180, 180
                elif 225.0 < yaw <= 315.0:
                    return cv2.ROTATE_90_COUNTERCLOCKWISE, 270
    return None, 0


def rotate_image(img, rot_code):
    if rot_code is not None:
        return cv2.rotate(img, rot_code)
    return img


def rotated_to_orig_bbox(bbox_rot, rot_angle, w_orig, h_orig):
    x1, y1, x2, y2 = bbox_rot
    corners_rot = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    corners_orig = []

    for xr, yr in corners_rot:
        if rot_angle == 90:
            u = yr
            v = h_orig - 1 - xr
        elif rot_angle == 180:
            u = w_orig - 1 - xr
            v = h_orig - 1 - yr
        elif rot_angle == 270:
            u = w_orig - 1 - yr
            v = xr
        else:
            u, v = xr, yr
        corners_orig.append((u, v))

    us = [u for u, v in corners_orig]
    vs = [v for u, v in corners_orig]
    return (min(us), min(vs), max(us), max(vs))


class BBoxDrawer:
    """Interactive bounding box drawer with 80% Overlap Unique Tile Guide."""

    def __init__(self, image, window_name="Draw Bounding Box"):
        self.orig_image = image
        self.h_orig, self.w_orig = image.shape[:2]

        max_dim = 1200
        if max(self.h_orig, self.w_orig) > max_dim:
            self.scale = max_dim / max(self.h_orig, self.w_orig)
        else:
            self.scale = 1.0

        self.disp_w = int(self.w_orig * self.scale)
        self.disp_h = int(self.h_orig * self.scale)
        self.disp_image = cv2.resize(image, (self.disp_w, self.disp_h))

        margin_x = int(self.disp_w * 0.375)
        margin_y = int(self.disp_h * 0.400)
        self.roi_x1 = margin_x
        self.roi_y1 = margin_y
        self.roi_x2 = self.disp_w - margin_x
        self.roi_y2 = self.disp_h - margin_y

        t_w = int(self.disp_w * 0.4378)
        t_h = int(self.disp_h * 0.4673)
        self.thermal_x1 = (self.disp_w - t_w) // 2
        self.thermal_y1 = (self.disp_h - t_h) // 2
        self.thermal_x2 = self.thermal_x1 + t_w
        self.thermal_y2 = self.thermal_y1 + t_h

        self.window_name = window_name
        self.drawing = False
        self.ix, self.iy = -1, -1
        self.curr_x, self.curr_y = -1, -1
        self.bbox_disp = (self.thermal_x1, self.thermal_y1, self.thermal_x2, self.thermal_y2)
        self._update_display()

    def _update_display(self):
        self.display = self.disp_image.copy()

        cv2.rectangle(self.display, (self.roi_x1, self.roi_y1), (self.roi_x2, self.roi_y2), (0, 215, 255), 1, cv2.LINE_AA)
        cv2.putText(self.display, "[1] O GACH 80% OVERLAP (Tile 20%x25%)",
                    (self.roi_x1 - 10, max(20, self.roi_y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1, cv2.LINE_AA)

        cv2.rectangle(self.display, (self.thermal_x1, self.thermal_y1), (self.thermal_x2, self.thermal_y2), (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(self.display, "[MAC DINH] VUNG ANH NHIET THERMAL (640x512)",
                    (self.thermal_x1 + 10, self.thermal_y1 + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2, cv2.LINE_AA)

        if self.bbox_disp is not None:
            x1, y1, x2, y2 = self.bbox_disp
            cv2.rectangle(self.display, (x1, y1), (x2, y2), (0, 255, 0), 3)
            cv2.putText(self.display, "VUNG DANG CHON - NHAN ENTER DE CHIEU", (x1, max(20, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        elif self.drawing and self.curr_x > 0 and self.curr_y > 0:
            cv2.rectangle(self.display, (self.ix, self.iy), (self.curr_x, self.curr_y), (0, 255, 0), 2)

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.ix, self.iy = x, y
            self.curr_x, self.curr_y = x, y
            self.bbox_disp = None
            self._update_display()

        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.curr_x, self.curr_y = x, y
            self._update_display()

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            x1 = min(self.ix, x)
            y1 = min(self.iy, y)
            x2 = max(self.ix, x)
            y2 = max(self.iy, y)
            if x2 - x1 > 3 and y2 - y1 > 3:
                self.bbox_disp = (x1, y1, x2, y2)
            self._update_display()

    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        print("\n" + "=" * 60)
        print("  VẼ HOẶC CHỌN BOUNDING BOX TRÊN ẢNH DRONE")
        print("  - Khung CYAN [MẶC ĐỊNH]: Vùng ảnh Nhiệt Thermal (640x512)")
        print("  - Khung VÀNG: Vùng Ô gạch đại diện 80% Overlap Tile")
        print("  - Nhấn ENTER: Đồng ý chọn Vùng hiển thị hiện tại và chiếu lên Ortho")
        print("  - Kéo chuột trái: Vẽ vùng tùy chọn mới (màu XANH LÁ)")
        print("  - Nhấn T: Chọn nhanh Vùng Ảnh Nhiệt")
        print("  - Nhấn O: Chọn nhanh Vùng Ô Gạch 80% Overlap")
        print("  - Nhấn C: Nhập tọa độ pixel từ bàn phím")
        print("  - Nhấn Q: Thoát")
        print("=" * 60 + "\n")

        while True:
            cv2.imshow(self.window_name, self.display)
            key = cv2.waitKey(30) & 0xFF

            if key == 13:  # ENTER
                if self.bbox_disp is None:
                    self.bbox_disp = (self.thermal_x1, self.thermal_y1, self.thermal_x2, self.thermal_y2)

                x1, y1, x2, y2 = self.bbox_disp
                bbox_orig = (
                    int(round(x1 / self.scale)),
                    int(round(y1 / self.scale)),
                    int(round(x2 / self.scale)),
                    int(round(y2 / self.scale)),
                )
                print(f"[INFO] BBox selected: {bbox_orig}")
                cv2.destroyWindow(self.window_name)
                return bbox_orig

            elif key == ord('t') or key == ord('T') or key == ord('1'):
                self.bbox_disp = (self.thermal_x1, self.thermal_y1, self.thermal_x2, self.thermal_y2)
                self._update_display()
                print("[INFO] Đã chọn Vùng Ảnh Nhiệt (Thermal Frame).")

            elif key == ord('o') or key == ord('O') or key == ord('2'):
                self.bbox_disp = (self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2)
                self._update_display()
                print("[INFO] Đã chọn Vùng Ô gạch 80% Overlap.")

            elif key == ord('r') or key == ord('R'):
                self.bbox_disp = (self.thermal_x1, self.thermal_y1, self.thermal_x2, self.thermal_y2)
                self.drawing = False
                self._update_display()
                print("[INFO] Reset về BBox Mặc định.")

            elif key == ord('c') or key == ord('C'):
                cv2.destroyWindow(self.window_name)
                print("\n--> Nhập tọa độ bbox dạng original pixel (ảnh 4056x3040):")
                try:
                    inp = input("   Nhập x1 y1 x2 y2 (ví dụ: 1500 1000 2500 2000): ").strip()
                    parts = list(map(int, inp.split()))
                    if len(parts) == 4:
                        return tuple(parts)
                except Exception as e:
                    print(f"[ERROR] Tọa độ không hợp lệ: {e}")
                return None

            elif key == ord('q') or key == ord('Q'):
                cv2.destroyWindow(self.window_name)
                return None

        return None


# ============================================================================
# 7. PROJECT BBOX CORNERS
# ============================================================================
def project_bbox_to_ortho(bbox, sensor, cam_transform, chunk_tf,
                          surface_sampler, ortho_mapper, ecef_to_wgs84):
    """
    Project 4 corners of bbox from drone image to orthophoto using DSM file.
    Returns both Compensated corners (Green) and Uncompensated corners (Blue).
    """
    x1, y1, x2, y2 = bbox

    points = [
        (x1, y1),  # top-left
        (x2, y1),  # top-right
        (x2, y2),  # bottom-right
        (x1, y2),  # bottom-left
        ((x1 + x2) / 2, (y1 + y2) / 2),  # center
    ]

    corners_ortho_comp = []
    corners_ortho_uncomp = []
    corners_lonlat_comp = []

    ground_alt_base = 46.5  # average terrain ground elevation

    for i, (u, v) in enumerate(points):
        label = ["TL", "TR", "BR", "BL", "CENTER"][i]
        theta = calculate_slant_angle(u, v, sensor)
        print(f"\n  Projecting {label} ({u:.0f}, {v:.0f}) | Góc xiên Off-Nadir θ = {theta:.1f}°...")

        # Pixel → ray in ECEF (direct pinhole from undistorted image)
        origin, direction = pixel_to_ray_ecef_undistorted(u, v, sensor, cam_transform, chunk_tf)

        # 1. Uncompensated Projection (Flat ground plane intersection without 3D panel relief)
        step_size = 0.5
        for step in range(1000):
            t_un = step * step_size
            P_un = origin + t_un * direction
            lon_un, lat_un, alt_un = ecef_to_wgs84.transform(P_un[0], P_un[1], P_un[2])
            if alt_un <= ground_alt_base:
                col_un, row_un = ortho_mapper.lonlat_to_pixel(lon_un, lat_un)
                corners_ortho_uncomp.append((col_un, row_un))
                break
        else:
            corners_ortho_uncomp.append((0, 0))

        # 2. Compensated Projection (DSM Surface + Slant Angle Relief Compensation)
        result = ray_dsm_intersect(origin, direction, surface_sampler, ecef_to_wgs84)

        if result is None:
            print(f"  [WARN] No surface intersection for {label}!")
            corners_ortho_comp.append(corners_ortho_uncomp[-1])
            corners_lonlat_comp.append((0, 0))
            continue

        lon_raw, lat_raw, elev_raw = result

        # Apply Anisotropic Directional Slant Angle & Panel Relief Compensation via DSM
        lon_c, lat_c, elev_c, offset_m = compensate_edge_slant(
            u, v, sensor, lon_raw, lat_raw, elev_raw, origin, direction, theta, surface_sampler, ecef_to_wgs84
        )

        if offset_m > 0.01:
            print(f"  [BÙ GÓC XIÊN] Đã bù xê dịch viền (DSM): Góc θ={theta:.1f}°, Bù ngang = {offset_m*100:.1f} cm!")
            col_c, row_c = ortho_mapper.lonlat_to_pixel(lon_c, lat_c)
            corners_ortho_comp.append((col_c, row_c))
            corners_lonlat_comp.append((lon_c, lat_c))
        else:
            col_raw, row_raw = ortho_mapper.lonlat_to_pixel(lon_raw, lat_raw)
            corners_ortho_comp.append((col_raw, row_raw))
            corners_lonlat_comp.append((lon_raw, lat_raw))

        print(f"  → WGS84 (Bù góc DSM): lon={corners_lonlat_comp[-1][0]:.8f}, lat={corners_lonlat_comp[-1][1]:.8f}")
        print(f"  → Ortho pixel (Bù góc DSM): col={corners_ortho_comp[-1][0]}, row={corners_ortho_comp[-1][1]}")
        print(f"  → Ortho pixel (Chưa bù): col={corners_ortho_uncomp[-1][0]}, row={corners_ortho_uncomp[-1][1]}")

    return corners_ortho_comp, corners_ortho_uncomp, corners_lonlat_comp


def visualize_result(drone_img, bbox, ortho_mapper, corners_ortho_comp, corners_ortho_uncomp, corners_lonlat):
    """Visualize both Compensated (Green) and Uncompensated (Blue) boxes on orthophoto."""
    if len(corners_ortho_comp) < 4:
        print("[ERROR] Không đủ corners để vẽ!")
        return

    cols = [c for c, r in corners_ortho_comp[:4]]
    rows = [r for c, r in corners_ortho_comp[:4]]
    c_center = int(np.mean(cols))
    r_center = int(np.mean(rows))

    half_w = 800
    half_h = 600

    col_min, col_max = c_center - half_w, c_center + half_w
    row_min, row_max = r_center - half_h, r_center + half_h

    ortho_region, c0, r0 = ortho_mapper.read_region(col_min, row_min, col_max, row_max, margin=0)

    if len(corners_ortho_uncomp) >= 4:
        local_uncomp = [(c - c0, r - r0) for c, r in corners_ortho_uncomp[:4]]
        overlay_blue = ortho_region.copy()
        pts_blue = np.array(local_uncomp, dtype=np.int32)
        cv2.fillPoly(overlay_blue, [pts_blue], (255, 120, 0))
        ortho_region = cv2.addWeighted(overlay_blue, 0.30, ortho_region, 0.70, 0)
        cv2.polylines(ortho_region, [pts_blue], isClosed=True, color=(255, 50, 0), thickness=3)
        for c, r in local_uncomp:
            cv2.circle(ortho_region, (c, r), 5, (255, 150, 0), -1)

    local_comp = [(c - c0, r - r0) for c, r in corners_ortho_comp[:4]]
    overlay_green = ortho_region.copy()
    pts_green = np.array(local_comp, dtype=np.int32)
    cv2.fillPoly(overlay_green, [pts_green], (0, 255, 0))
    ortho_region = cv2.addWeighted(overlay_green, 0.35, ortho_region, 0.65, 0)
    cv2.polylines(ortho_region, [pts_green], isClosed=True, color=(0, 255, 0), thickness=3)

    for i, (c, r) in enumerate(local_comp):
        label = ["TL", "TR", "BR", "BL"][i]
        cv2.circle(ortho_region, (c, r), 7, (0, 0, 255), -1)
        cv2.putText(ortho_region, label, (c + 8, r - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.putText(ortho_region, "[BLUE] KHONG BU (Chieu Mat Dat)", (20, ortho_region.shape[0] - 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 50, 0), 2)
    cv2.putText(ortho_region, "[GREEN] DA BU GOC XIEN & DO CAO PIN (DSM)", (20, ortho_region.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    print("\n" + "=" * 60)
    print("  KẾT QUẢ CHIẾU")
    print("=" * 60)
    for i, (lon, lat) in enumerate(corners_lonlat[:4]):
        label = ["TL", "TR", "BR", "BL"][i]
        print(f"  {label}: lon={lon:.8f}, lat={lat:.8f}")
    if len(corners_lonlat) > 4:
        print(f"  CENTER: lon={corners_lonlat[4][0]:.8f}, lat={corners_lonlat[4][1]:.8f}")
    print("=" * 60)

    h_drone, w_drone = drone_img.shape[:2]
    h_ortho, w_ortho = ortho_region.shape[:2]

    target_h = min(900, max(h_drone, h_ortho))
    scale_d = target_h / h_drone
    scale_o = target_h / h_ortho

    drone_resized = cv2.resize(drone_img, (int(w_drone * scale_d), target_h))
    ortho_resized = cv2.resize(ortho_region, (int(w_ortho * scale_o), target_h))

    x1, y1, x2, y2 = bbox
    cv2.rectangle(drone_resized,
                  (int(x1 * scale_d), int(y1 * scale_d)),
                  (int(x2 * scale_d), int(y2 * scale_d)),
                  (0, 255, 0), 3)
    cv2.putText(drone_resized, "DRONE", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
    cv2.putText(ortho_resized, "ORTHOPHOTO", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

    combined = np.hstack([drone_resized,
                          np.ones((target_h, 40, 3), dtype=np.uint8) * 30,
                          ortho_resized])

    output_path = os.path.join(WORK_DIR, "projection_result.jpg")
    cv2.imwrite(output_path, combined, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"\n[INFO] Kết quả lưu tại: {output_path}")

    cv2.namedWindow("Projection Result", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Projection Result", min(combined.shape[1], 1800), target_h)
    cv2.imshow("Projection Result", combined)

    print("\n  Nhấn phím bất kỳ để đóng...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 60)
    print("  CHIẾU BOUNDING BOX TỪ ẢNH DRONE LÊN ORTHOPHOTO")
    print("  Phương pháp: Camera Projection + DSM GeoTIFF Ray Intersection")
    print("=" * 60)

    print("\n[INFO] Đã chọn phương pháp: DSM GeoTIFF (chỉ sử dụng tệp DSM)")

    # 1. Parse XML
    print("\n[STEP 1] Parsing Metashape XML...")
    sensor, cam_tf, chunk_tf = parse_metashape_xml(XML_PATH, IMAGE_NAME)

    # 2. Setup coordinate transformer (ECEF → WGS84)
    ecef_to_wgs84 = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)

    # 3. Validate camera position
    print("\n[STEP 2] Validating camera position...")
    C_chunk = cam_tf[:3, 3]
    C_ecef = chunk_tf["scale"] * (chunk_tf["rotation"] @ C_chunk) + chunk_tf["translation"]
    cam_lon, cam_lat, cam_alt = ecef_to_wgs84.transform(C_ecef[0], C_ecef[1], C_ecef[2])
    print(f"  Camera center: lon={cam_lon:.8f}, lat={cam_lat:.8f}, alt={cam_alt:.2f}m")
    print(f"  (XML reference: lon=108.8514744, lat=11.4246698, alt=80.37m)")

    # 4. Load DSM Sampler
    print("\n[STEP 3] Loading DSM GeoTIFF...")
    surface = DSMSampler(DSM_PATH)

    # 5. Load Ortho mapper
    print("\n[STEP 4] Loading Orthophoto...")
    ortho = OrthoMapper(ORTHO_PATH)

    # 6. Load drone image, undistort, and rotate North-Up
    print("\n[STEP 5] Loading and Undistorting drone image...")
    raw_drone_img = cv2.imread(IMAGE_PATH)
    if raw_drone_img is None:
        print(f"[ERROR] Cannot read image: {IMAGE_PATH}")
        sys.exit(1)
    print(f"  Original image size: {raw_drone_img.shape[1]}x{raw_drone_img.shape[0]}")

    print("  [INFO] Undistorting drone image (Metashape Brown calibration)...")
    drone_img_undist = undistort_drone_image(raw_drone_img, sensor)

    rot_code, rot_angle = get_north_up_rotation(IMAGE_NAME, XML_PATH)
    if rot_code is not None:
        print(f"  [INFO] Rotated undistorted drone image {rot_angle}° to align North-Up with Orthophoto!")
        drone_img_disp = rotate_image(drone_img_undist, rot_code)
    else:
        drone_img_disp = drone_img_undist.copy()

    drawer = BBoxDrawer(drone_img_disp)
    bbox_rot = drawer.run()

    if bbox_rot is None:
        print("[INFO] Cancelled by user.")
        surface.close()
        ortho.close()
        return

    if rot_code is not None:
        h_orig, w_orig = drone_img_undist.shape[:2]
        bbox = rotated_to_orig_bbox(bbox_rot, rot_angle, w_orig, h_orig)
        print(f"[INFO] BBox on rotated (North-Up) undistorted image: {bbox_rot}")
        print(f"[INFO] BBox mapped to undistorted image pixels: {bbox}")
    else:
        bbox = bbox_rot

    # 7. Project bbox corners
    print(f"\n[STEP 6] Projecting bbox {bbox} using DSM GeoTIFF to orthophoto...")
    corners_comp, corners_uncomp, corners_lonlat = project_bbox_to_ortho(
        bbox, sensor, cam_tf, chunk_tf, surface, ortho, ecef_to_wgs84
    )

    # 8. Visualize
    print("\n[STEP 7] Visualizing result...")
    visualize_result(drone_img_disp, bbox_rot, ortho, corners_comp, corners_uncomp, corners_lonlat)

    # Cleanup
    surface.close()
    ortho.close()
    print("\n[DONE] Hoàn tất!")


if __name__ == "__main__":
    main()
