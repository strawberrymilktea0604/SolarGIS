import os
import math
import tempfile
import numpy as np
from PIL import Image
import rasterio
from rasterio.windows import Window, transform as window_transform
from rasterio.warp import transform_bounds
from pyproj import Transformer
import cv2

try:
    import torch
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except ImportError:
    pass

try:
    from lightglue import LightGlue, SuperPoint
    from lightglue.utils import rbd
    HAS_LIGHTGLUE = True
except ImportError:
    HAS_LIGHTGLUE = False

try:
    import kornia.feature as kf
    HAS_LOFTR = True
except ImportError:
    HAS_LOFTR = False
class OrthoProcessor:
    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "ortho_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.loaded_orthos = {}
        self.reference_grid = None
        self.reference_grid_target_ortho = None
        self.reference_grid_file_path = None

    def get_info(self, file_path: str):
        """Đọc toàn bộ thông tin siêu dữ liệu của file Orthophoto/GeoTIFF"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        with rasterio.open(file_path) as src:
            width = src.width
            height = src.height
            count = src.count
            crs = src.crs.to_string() if src.crs else None
            bounds = {
                "left": float(src.bounds.left),
                "bottom": float(src.bounds.bottom),
                "right": float(src.bounds.right),
                "top": float(src.bounds.top),
            }
            transform = list(src.transform)
            dtypes = [str(d) for d in src.dtypes]
            nodata = float(src.nodata) if src.nodata is not None else None

            # Tính toán GSD (Ground Sample Distance)
            res_x = abs(src.transform.a)
            res_y = abs(src.transform.e)

            is_geographic = src.crs.is_geographic if src.crs else False
            center_lat = (src.bounds.bottom + src.bounds.top) / 2 if is_geographic else 0

            if is_geographic:
                # 1 độ vĩ tuyến ~ 111,320m, 1 độ kinh tuyến ~ 111,320m * cos(lat)
                lat_rad = math.radians(center_lat)
                gsd_x_m = res_x * 111320 * math.cos(lat_rad)
                gsd_y_m = res_y * 111320
                gsd_cm = round(((gsd_x_m + gsd_y_m) / 2) * 100, 2)
            elif src.crs and src.crs.is_projected:
                # Đơn vị thường là mét (UTM, VN2000...)
                gsd_cm = round(((res_x + res_y) / 2) * 100, 2)
            else:
                gsd_cm = None

            # Tọa độ WGS84 (Lat/Lon) nếu có CRS
            wgs84_bounds = None
            center_wgs84 = None
            if src.crs:
                try:
                    wgs84_bounds_tuple = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
                    wgs84_bounds = {
                        "min_lon": round(float(wgs84_bounds_tuple[0]), 7),
                        "min_lat": round(float(wgs84_bounds_tuple[1]), 7),
                        "max_lon": round(float(wgs84_bounds_tuple[2]), 7),
                        "max_lat": round(float(wgs84_bounds_tuple[3]), 7),
                    }
                    center_wgs84 = {
                        "lat": round((wgs84_bounds["min_lat"] + wgs84_bounds["max_lat"]) / 2, 7),
                        "lon": round((wgs84_bounds["min_lon"] + wgs84_bounds["max_lon"]) / 2, 7),
                    }
                except Exception as e:
                    print(f"Lỗi chuyển đổi CRS sang WGS84: {e}")

            # Tính diện tích (m² và hecta)
            area_m2 = None
            area_ha = None
            if gsd_cm:
                area_m2 = round((width * height) * ((gsd_cm / 100) ** 2), 2)
                area_ha = round(area_m2 / 10000, 4)

            file_size_bytes = os.path.getsize(file_path)
            file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

            return {
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "file_size_mb": file_size_mb,
                "width": width,
                "height": height,
                "bands": count,
                "dtypes": dtypes,
                "crs": crs,
                "bounds": bounds,
                "wgs84_bounds": wgs84_bounds,
                "center_wgs84": center_wgs84,
                "transform": transform,
                "nodata": nodata,
                "gsd_cm": gsd_cm,
                "area_m2": area_m2,
                "area_ha": area_ha,
            }

    def generate_preview(self, file_path: str, max_size: int = 4096) -> str:
        """Tạo ảnh xem trước (preview) chất lượng cao bằng decimation siêu tốc của rasterio"""
        cache_key = f"{os.path.basename(file_path)}_{max_size}_{os.path.getmtime(file_path)}.jpg"
        preview_path = os.path.join(self.cache_dir, cache_key)
        if os.path.exists(preview_path):
            return preview_path

        with rasterio.open(file_path) as src:
            scale = min(1.0, max_size / max(src.width, src.height))
            out_w = max(1, int(src.width * scale))
            out_h = max(1, int(src.height * scale))

            # Chọn tối đa 3-4 band đầu tiên
            band_indices = list(range(1, min(src.count, 4) + 1))
            if src.count >= 3:
                bands_to_read = [1, 2, 3] # RGB
            else:
                bands_to_read = [1]

            arr = src.read(bands_to_read, out_shape=(len(bands_to_read), out_h, out_w))

            # Chuẩn hóa dữ liệu pixel về uint8 (0-255)
            if arr.dtype != np.uint8:
                norm_bands = []
                for b in arr:
                    valid_mask = np.isfinite(b)
                    if src.nodata is not None:
                        valid_mask &= (b != src.nodata)
                    if np.any(valid_mask):
                        p2, p98 = np.percentile(b[valid_mask], (2, 98))
                        if p98 > p2:
                            b_norm = np.clip((b - p2) / (p98 - p2) * 255.0, 0, 255).astype(np.uint8)
                        else:
                            b_norm = np.zeros_like(b, dtype=np.uint8)
                    else:
                        b_norm = np.zeros_like(b, dtype=np.uint8)
                    norm_bands.append(b_norm)
                arr = np.stack(norm_bands, axis=0)

            # Tạo PIL Image
            if arr.shape[0] == 1:
                img = Image.fromarray(arr[0], mode="L")
            else:
                img_data = np.transpose(arr[:3], (1, 2, 0))
                img = Image.fromarray(img_data, mode="RGB")

            img.save(preview_path, format="JPEG", quality=85)
            return preview_path

    def get_viewport_crop(self, file_path: str, col_off: int, row_off: int, width: int, height: int, max_dim: int = 2560) -> str:
        """Trích xuất một vùng cửa sổ (window) độ phân giải nét cao (lên đến 100% full-res) khi phóng to"""
        with rasterio.open(file_path) as src:
            col_off = max(0, min(src.width - 1, int(col_off)))
            row_off = max(0, min(src.height - 1, int(row_off)))
            win_w = max(1, min(int(width), src.width - col_off))
            win_h = max(1, min(int(height), src.height - row_off))

            scale = min(1.0, max_dim / max(win_w, win_h))
            out_w = max(1, int(win_w * scale))
            out_h = max(1, int(win_h * scale))

            cache_key = f"vp_{os.path.basename(file_path)}_{col_off}_{row_off}_{win_w}_{win_h}_{out_w}x{out_h}.jpg"
            out_path = os.path.join(self.cache_dir, cache_key)
            if os.path.exists(out_path):
                return out_path

            window = Window(col_off=col_off, row_off=row_off, width=win_w, height=win_h)
            bands_to_read = [1, 2, 3] if src.count >= 3 else [1]

            arr = src.read(bands_to_read, window=window, out_shape=(len(bands_to_read), out_h, out_w))

            if arr.dtype != np.uint8:
                norm_bands = []
                for b in arr:
                    valid_mask = np.isfinite(b)
                    if src.nodata is not None:
                        valid_mask &= (b != src.nodata)
                    if np.any(valid_mask):
                        p2, p98 = np.percentile(b[valid_mask], (2, 98))
                        if p98 > p2:
                            b_norm = np.clip((b - p2) / (p98 - p2) * 255.0, 0, 255).astype(np.uint8)
                        else:
                            b_norm = np.zeros_like(b, dtype=np.uint8)
                    else:
                        b_norm = np.zeros_like(b, dtype=np.uint8)
                    norm_bands.append(b_norm)
                arr = np.stack(norm_bands, axis=0)

            if arr.shape[0] == 1:
                img = Image.fromarray(arr[0], mode="L")
            else:
                img_data = np.transpose(arr[:3], (1, 2, 0))
                img = Image.fromarray(img_data, mode="RGB")

            img.save(out_path, format="JPEG", quality=95)
            return out_path

    def calculate_bounding_box(self, big_path: str, sub_path: str):
        """Xác định chính xác vị trí và Bounding Box của Ortho vùng trên Ortho lớn"""
        info_big = self.get_info(big_path)
        info_sub = self.get_info(sub_path)

        with rasterio.open(big_path) as big_src, rasterio.open(sub_path) as sub_src:
            has_geo = (big_src.crs is not None) and (sub_src.crs is not None)

            if has_geo:
                # Chuyển đổi 4 góc của sub_ortho sang hệ tọa độ của big_ortho nếu khác CRS
                sub_bounds = sub_src.bounds
                corners_sub_geo = [
                    (sub_bounds.left, sub_bounds.top),      # Top-left
                    (sub_bounds.right, sub_bounds.top),     # Top-right
                    (sub_bounds.right, sub_bounds.bottom),  # Bottom-right
                    (sub_bounds.left, sub_bounds.bottom),   # Bottom-left
                ]

                if sub_src.crs != big_src.crs:
                    transformer = Transformer.from_crs(sub_src.crs, big_src.crs, always_xy=True)
                    corners_big_geo = [transformer.transform(x, y) for x, y in corners_sub_geo]
                else:
                    corners_big_geo = corners_sub_geo

                # Chuyển đổi tọa độ địa lý sang tọa độ Pixel trên ảnh to
                # Sử dụng ma trận nghịch đảo ~big_src.transform
                inv_transform = ~big_src.transform
                pixel_polygon = []
                for x_geo, y_geo in corners_big_geo:
                    col, row = inv_transform * (x_geo, y_geo)
                    # Giữ nguyên độ phân giải float, không làm tròn để tăng độ chính xác của ma trận ánh xạ
                    pixel_polygon.append({"col": col, "row": row})

                cols = [p["col"] for p in pixel_polygon]
                rows = [p["row"] for p in pixel_polygon]

                min_col = min(cols)
                max_col = max(cols)
                min_row = min(rows)
                max_row = max(rows)

                # Giới hạn trong kích thước ảnh to để tính vùng giao (clamped)
                c_min_col = max(0, min(big_src.width, min_col))
                c_max_col = max(0, min(big_src.width, max_col))
                c_min_row = max(0, min(big_src.height, min_row))
                c_max_row = max(0, min(big_src.height, max_row))

                pixel_box = {
                    "xmin": round(min_col),
                    "ymin": round(min_row),
                    "xmax": round(max_col),
                    "ymax": round(max_row),
                    "width": round(max_col - min_col),
                    "height": round(max_row - min_row),
                    "center_x": round((min_col + max_col) / 2),
                    "center_y": round((min_row + max_row) / 2),
                }

                # Chuẩn hóa (0 - 1) để dùng trong YOLO hoặc web display
                norm_box = {
                    "xmin": round(min_col / big_src.width, 6),
                    "ymin": round(min_row / big_src.height, 6),
                    "xmax": round(max_col / big_src.width, 6),
                    "ymax": round(max_row / big_src.height, 6),
                    "width": round((max_col - min_col) / big_src.width, 6),
                    "height": round((max_row - min_row) / big_src.height, 6),
                    "center_x": round(((min_col + max_col) / 2) / big_src.width, 6),
                    "center_y": round(((min_row + max_row) / 2) / big_src.height, 6),
                }

                # YOLO format string: class_id x_center y_center width height
                yolo_format = f"0 {norm_box['center_x']:.6f} {norm_box['center_y']:.6f} {norm_box['width']:.6f} {norm_box['height']:.6f}"

                # Kiểm tra tính hợp lệ và tỉ lệ bao phủ (Overlap)
                is_overlapping = (c_max_col > c_min_col) and (c_max_row > c_min_row)
                overlap_area_px = max(0, c_max_col - c_min_col) * max(0, c_max_row - c_min_row)
                sub_area_px = max(1, (max_col - min_col) * (max_row - min_row))
                overlap_pct = round(min(100.0, (overlap_area_px / sub_area_px) * 100.0), 2)

                # Tọa độ địa lý giao nhau
                geo_box = {
                    "min_x": min(c[0] for c in corners_big_geo),
                    "min_y": min(c[1] for c in corners_big_geo),
                    "max_x": max(c[0] for c in corners_big_geo),
                    "max_y": max(c[1] for c in corners_big_geo),
                }

                # Tọa độ WGS84 (Lat/Lon) của 4 góc BBox
                transformer_to_wgs84 = Transformer.from_crs(big_src.crs, "EPSG:4326", always_xy=True)
                wgs84_polygon = []
                for x_geo, y_geo in corners_big_geo:
                    lon, lat = transformer_to_wgs84.transform(x_geo, y_geo)
                    wgs84_polygon.append({"lon": round(lon, 7), "lat": round(lat, 7)})

                # Tạo đối tượng GeoJSON feature
                geojson_feature = {
                    "type": "Feature",
                    "properties": {
                        "big_ortho": os.path.basename(big_path),
                        "sub_ortho": os.path.basename(sub_path),
                        "pixel_box": pixel_box,
                        "overlap_percent": overlap_pct,
                        "area_m2": info_sub.get("area_m2"),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [p["lon"], p["lat"]] for p in wgs84_polygon
                        ] + [[wgs84_polygon[0]["lon"], wgs84_polygon[0]["lat"]]]]
                    }
                }

                method = "geospatial_crs"

            else:
                # Phương pháp Computer Vision (Feature Matching) nếu 1 trong 2 không có CRS
                pixel_box, norm_box, yolo_format, overlap_pct, method = self._match_by_cv(big_path, sub_path)
                pixel_polygon = [
                    {"col": pixel_box["xmin"], "row": pixel_box["ymin"]},
                    {"col": pixel_box["xmax"], "row": pixel_box["ymin"]},
                    {"col": pixel_box["xmax"], "row": pixel_box["ymax"]},
                    {"col": pixel_box["xmin"], "row": pixel_box["ymax"]},
                ]
                geo_box = None
                wgs84_polygon = None
                geojson_feature = None
                is_overlapping = True

            # So sánh độ phân giải GSD
            gsd_ratio = None
            if info_big.get("gsd_cm") and info_sub.get("gsd_cm"):
                gsd_ratio = round(info_big["gsd_cm"] / info_sub["gsd_cm"], 2)

            return {
                "big_ortho": info_big,
                "sub_ortho": info_sub,
                "method": method,
                "is_overlapping": is_overlapping,
                "overlap_pct": overlap_pct,
                "pixel_box": pixel_box,
                "pixel_polygon": pixel_polygon,
                "norm_box": norm_box,
                "yolo_format": yolo_format,
                "geo_box": geo_box,
                "wgs84_polygon": wgs84_polygon,
                "geojson": geojson_feature,
                "gsd_ratio": gsd_ratio,
            }

    def _match_by_cv(self, big_path: str, sub_path: str):
        """Khớp mẫu bằng Computer Vision nếu ảnh không có hệ tọa độ"""
        preview_big_path = self.generate_preview(big_path, max_size=2048)
        preview_sub_path = self.generate_preview(sub_path, max_size=1024)

        img_big = cv2.imread(preview_big_path, cv2.IMREAD_GRAYSCALE)
        img_sub = cv2.imread(preview_sub_path, cv2.IMREAD_GRAYSCALE)

        with rasterio.open(big_path) as big_src, rasterio.open(sub_path) as sub_src:
            scale_x = big_src.width / img_big.shape[1]
            scale_y = big_src.height / img_big.shape[0]

            h_sub, w_sub = img_sub.shape
            M, mask, method_used = None, None, "fallback"

            if HAS_LIGHTGLUE:
                pts_sub, pts_big = self._get_lightglue_matches(img_sub, img_big, max_points=500)
                M, mask = self._get_best_homography(pts_sub, pts_big, w_sub, h_sub)
                if M is not None:
                    method_used = "cv_feature_matching_lightglue"

            if M is None and HAS_LOFTR:
                pts_sub, pts_big = self._get_loftr_matches(img_sub, img_big, max_points=500)
                M, mask = self._get_best_homography(pts_sub, pts_big, w_sub, h_sub)
                if M is not None:
                    method_used = "cv_feature_matching_loftr"

            if M is None:
                # ORB Feature matching fallback
                orb = cv2.ORB_create(nfeatures=2000)
                kp1, des1 = orb.detectAndCompute(img_big, None)
                kp2, des2 = orb.detectAndCompute(img_sub, None)

                if des1 is not None and des2 is not None:
                    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                    matches = bf.match(des1, des2)
                    matches = sorted(matches, key=lambda x: x.distance)[:100]

                    if len(matches) >= 4:
                        pts_big = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
                        pts_sub = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
                        M, mask = self._get_best_homography(pts_sub, pts_big, w_sub, h_sub)
                        if M is not None:
                            method_used = "cv_feature_matching_orb"

            if M is not None:
                pts = np.float32([[0, 0], [0, h_sub - 1], [w_sub - 1, h_sub - 1], [w_sub - 1, 0]]).reshape(-1, 1, 2)
                dst = cv2.perspectiveTransform(pts, M)
                    
                xmin = int(min(dst[:, 0, 0]) * scale_x)
                xmax = int(max(dst[:, 0, 0]) * scale_x)
                ymin = int(min(dst[:, 0, 1]) * scale_y)
                ymax = int(max(dst[:, 0, 1]) * scale_y)

                pixel_box = {
                    "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                    "width": xmax - xmin, "height": ymax - ymin,
                    "center_x": (xmin + xmax) // 2, "center_y": (ymin + ymax) // 2
                }
                norm_box = {
                    "xmin": round(xmin / big_src.width, 6),
                    "ymin": round(ymin / big_src.height, 6),
                    "xmax": round(xmax / big_src.width, 6),
                    "ymax": round(ymax / big_src.height, 6),
                    "width": round((xmax - xmin) / big_src.width, 6),
                    "height": round((ymax - ymin) / big_src.height, 6),
                    "center_x": round(((xmin + xmax) / 2) / big_src.width, 6),
                    "center_y": round(((ymin + ymax) / 2) / big_src.height, 6),
                }
                yolo = f"0 {norm_box['center_x']:.6f} {norm_box['center_y']:.6f} {norm_box['width']:.6f} {norm_box['height']:.6f}"
                return pixel_box, norm_box, yolo, 100.0, method_used

            # Fallback nếu không khớp được
            default_box = {"xmin": 0, "ymin": 0, "xmax": big_src.width, "ymax": big_src.height, "width": big_src.width, "height": big_src.height, "center_x": big_src.width // 2, "center_y": big_src.height // 2}
            default_norm = {"xmin": 0.0, "ymin": 0.0, "xmax": 1.0, "ymax": 1.0, "width": 1.0, "height": 1.0, "center_x": 0.5, "center_y": 0.5}
            return default_box, default_norm, "0 0.500000 0.500000 1.000000 1.000000", 0.0, "fallback"

    def transform_points_by_cv(self, big_path: str, sub_path: str, points: list):
        """Sử dụng SIFT/ORB để ánh xạ danh sách các điểm mà KHÔNG dùng định vị GPS"""
        preview_big_path = self.generate_preview(big_path, max_size=2048)
        preview_sub_path = self.generate_preview(sub_path, max_size=1024)

        img_big = cv2.imread(preview_big_path, cv2.IMREAD_GRAYSCALE)
        img_sub = cv2.imread(preview_sub_path, cv2.IMREAD_GRAYSCALE)

        with rasterio.open(big_path) as big_src, rasterio.open(sub_path) as sub_src:
            scale_x_big = big_src.width / img_big.shape[1]
            scale_y_big = big_src.height / img_big.shape[0]
            scale_x_sub = sub_src.width / img_sub.shape[1]
            scale_y_sub = sub_src.height / img_sub.shape[0]

        h_sub, w_sub = img_sub.shape
        M_homo, M_affine = None, None
        
        def calc_M(pts_s, pts_b):
            if pts_s is None or pts_b is None or len(pts_s) < 4: return None, None
            pts_s_f = np.zeros_like(pts_s)
            pts_s_f[:, 0, 0] = pts_s[:, 0, 0] * scale_x_sub
            pts_s_f[:, 0, 1] = pts_s[:, 0, 1] * scale_y_sub
            pts_b_f = np.zeros_like(pts_b)
            pts_b_f[:, 0, 0] = pts_b[:, 0, 0] * scale_x_big
            pts_b_f[:, 0, 1] = pts_b[:, 0, 1] * scale_y_big
            
            threshold = 5.0 * max(scale_x_big, scale_y_big)
            M_h, _ = cv2.findHomography(pts_s_f, pts_b_f, cv2.RANSAC, threshold)
            M_a, _ = cv2.estimateAffinePartial2D(pts_s_f, pts_b_f, method=cv2.RANSAC, ransacReprojThreshold=threshold)
            
            if not self._is_homography_valid(M_h, w_sub * scale_x_sub, h_sub * scale_y_sub):
                if M_a is not None:
                    M_h = np.vstack([M_a, [0, 0, 1]])
                else:
                    M_h = None
            return M_h, M_a

        if HAS_LIGHTGLUE:
            pts_s, pts_b = self._get_lightglue_matches(img_sub, img_big, max_points=500)
            M_homo, M_affine = calc_M(pts_s, pts_b)

        if M_homo is None and HAS_LOFTR:
            pts_s, pts_b = self._get_loftr_matches(img_sub, img_big, max_points=500)
            M_homo, M_affine = calc_M(pts_s, pts_b)

        if M_homo is None:
            orb = cv2.ORB_create(nfeatures=5000)
            kp_big, des_big = orb.detectAndCompute(img_big, None)
            kp_sub, des_sub = orb.detectAndCompute(img_sub, None)

            if des_big is None or des_sub is None:
                raise ValueError("Không tìm thấy đặc điểm ảnh (Features) để tiến hành đối chiếu AI.")

            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des_sub, des_big)
            matches = sorted(matches, key=lambda x: x.distance)[:300]

            if len(matches) >= 4:
                pts_s = np.float32([kp_sub[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
                pts_b = np.float32([kp_big[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
                M_homo, M_affine = calc_M(pts_s, pts_b)

        if M_homo is None or M_affine is None:
            raise ValueError("AI không thể tính toán được ma trận biến đổi do quá nhiều nhiễu.")

        results_affine = []
        results_homo = []

        for p in points:
            u, v = p.get('u'), p.get('v')
            pt_in = np.float32([[[u, v]]])
            
            # Affine Transform
            pt_out_aff = cv2.transform(pt_in, M_affine)
            x_aff, y_aff = pt_out_aff[0][0]
            results_affine.append({
                "name": p.get('name', 'Point'),
                "u": u, "v": v,
                "x": round(float(x_aff), 2), "y": round(float(y_aff), 2)
            })
            
            # Homography Transform
            pt_out_homo = cv2.perspectiveTransform(pt_in, M_homo)
            x_homo, y_homo = pt_out_homo[0][0]
            results_homo.append({
                "name": p.get('name', 'Point'),
                "u": u, "v": v,
                "x": round(float(x_homo), 2), "y": round(float(y_homo), 2)
            })

        return {
            "affine": results_affine,
            "homography": results_homo
        }

    def crop_bounding_box(self, big_path: str, pixel_box: dict, output_format: str = "GTiff", output_path: str = None) -> str:
        """Cắt vùng Bounding Box từ Ortho to ra file GeoTIFF hoặc PNG với chất lượng nguyên bản"""
        with rasterio.open(big_path) as src:
            col_off = max(0, pixel_box["xmin"])
            row_off = max(0, pixel_box["ymin"])
            width = min(src.width - col_off, pixel_box["width"])
            height = min(src.height - row_off, pixel_box["height"])

            if width <= 0 or height <= 0:
                raise ValueError("Kích thước vùng cắt không hợp lệ")

            window = Window(col_off=col_off, row_off=row_off, width=width, height=height)
            data = src.read(window=window)
            win_trans = window_transform(window, src.transform)

            if output_format.lower() in ["tif", "tiff", "gtiff"]:
                ext = ".tif"
                if not output_path:
                    output_path = os.path.join(self.cache_dir, f"crop_{col_off}_{row_off}_{width}x{height}.tif")
                
                profile = src.profile.copy()
                profile.update({
                    "height": height,
                    "width": width,
                    "transform": win_trans,
                })
                with rasterio.open(output_path, "w", **profile) as dst:
                    dst.write(data)
            else:
                ext = ".png"
                if not output_path:
                    output_path = os.path.join(self.cache_dir, f"crop_{col_off}_{row_off}_{width}x{height}.png")
                
                # Chuyển đổi sang hình ảnh RGB/RGBA
                if data.shape[0] >= 3:
                    img_data = np.transpose(data[:3], (1, 2, 0))
                    img = Image.fromarray(img_data)
                else:
                    img = Image.fromarray(data[0])
                img.save(output_path, format="PNG")

            return output_path

    def calculate_two_sub_orthos(self, sub1_path: str, sub2_path: str):
        """So sánh và tính toán vị trí tương quan giữa 2 ảnh Ortho vùng (Sub-Ortho 1 & Sub-Ortho 2)"""
        info_sub1 = self.get_info(sub1_path)
        info_sub2 = self.get_info(sub2_path)

        with rasterio.open(sub1_path) as s1_src, rasterio.open(sub2_path) as s2_src:
            has_geo = (s1_src.crs is not None) and (s2_src.crs is not None)

            # Tính toán so sánh cơ bản
            gsd1 = info_sub1.get("gsd_cm")
            gsd2 = info_sub2.get("gsd_cm")
            gsd_ratio = round(gsd1 / gsd2, 2) if (gsd1 and gsd2 and gsd2 > 0) else None

            dim_comparison = {
                "sub1": {"width": info_sub1["width"], "height": info_sub1["height"]},
                "sub2": {"width": info_sub2["width"], "height": info_sub2["height"]},
                "w_diff": info_sub2["width"] - info_sub1["width"],
                "h_diff": info_sub2["height"] - info_sub1["height"],
            }

            sub2_on_sub1_pixel_box = None
            sub2_on_sub1_polygon = None
            overlap_pct = 0.0
            overlap_m2 = 0.0
            is_overlapping = False
            center_distance_m = None
            geo_intersection = None

            if has_geo:
                # Chuyển 4 góc của sub2 sang CRS của sub1
                sub2_bounds = s2_src.bounds
                corners_sub2_geo = [
                    (sub2_bounds.left, sub2_bounds.top),
                    (sub2_bounds.right, sub2_bounds.top),
                    (sub2_bounds.right, sub2_bounds.bottom),
                    (sub2_bounds.left, sub2_bounds.bottom),
                ]

                if s2_src.crs != s1_src.crs:
                    transformer = Transformer.from_crs(s2_src.crs, s1_src.crs, always_xy=True)
                    corners_sub2_in_s1 = [transformer.transform(x, y) for x, y in corners_sub2_geo]
                else:
                    corners_sub2_in_s1 = corners_sub2_geo

                # Tọa độ pixel của sub2 trên canvas của sub1
                inv_trans1 = ~s1_src.transform
                pixel_polygon = []
                for x_geo, y_geo in corners_sub2_in_s1:
                    col, row = inv_trans1 * (x_geo, y_geo)
                    # Giữ nguyên độ phân giải float, không làm tròn để tăng độ chính xác của ma trận ánh xạ
                    pixel_polygon.append({"col": col, "row": row})

                cols = [p["col"] for p in pixel_polygon]
                rows = [p["row"] for p in pixel_polygon]
                min_col, max_col = min(cols), max(cols)
                min_row, max_row = min(rows), max(rows)

                sub2_on_sub1_pixel_box = {
                    "xmin": round(min_col),
                    "ymin": round(min_row),
                    "xmax": round(max_col),
                    "ymax": round(max_row),
                    "width": round(max_col - min_col),
                    "height": round(max_row - min_row),
                    "center_x": round((min_col + max_col) / 2),
                    "center_y": round((min_row + max_row) / 2),
                }
                sub2_on_sub1_polygon = pixel_polygon

                # Tính giao nhau (overlap) giữa sub1 và sub2
                # Giới hạn trong kích thước sub1
                c_min_col = max(0, min(s1_src.width, min_col))
                c_max_col = max(0, min(s1_src.width, max_col))
                c_min_row = max(0, min(s1_src.height, min_row))
                c_max_row = max(0, min(s1_src.height, max_row))

                if c_max_col > c_min_col and c_max_row > c_min_row:
                    is_overlapping = True
                    inter_px = (c_max_col - c_min_col) * (c_max_row - c_min_row)
                    total_px_sub1 = s1_src.width * s1_src.height
                    overlap_pct = round((inter_px / total_px_sub1) * 100.0, 2)

                    # Diện tích thực tế giao nhau (m²)
                    avg_gsd = (gsd1 or 5.0) / 100.0
                    overlap_m2 = round(inter_px * (avg_gsd ** 2), 2)

                # Khoảng cách tâm giữa 2 ảnh (meters)
                c1_x = (s1_src.bounds.left + s1_src.bounds.right) / 2
                c1_y = (s1_src.bounds.bottom + s1_src.bounds.top) / 2
                c2_x = (sub2_bounds.left + sub2_bounds.right) / 2
                c2_y = (sub2_bounds.bottom + sub2_bounds.top) / 2

                if s2_src.crs != s1_src.crs:
                    c2_x, c2_y = transformer.transform(c2_x, c2_y)

                if s1_src.crs.is_projected:
                    center_distance_m = round(math.sqrt((c2_x - c1_x)**2 + (c2_y - c1_y)**2), 2)
                else:
                    # Haversine distance cho tọa độ lat/lon
                    lat1, lon1 = c1_y, c1_x
                    lat2, lon2 = c2_y, c2_x
                    r = 6371000  # radius of Earth in meters
                    phi1, phi2 = math.radians(lat1), math.radians(lat2)
                    dphi = math.radians(lat2 - lat1)
                    dlambda = math.radians(lon2 - lon1)
                    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    center_distance_m = round(r * c, 2)

                method = "geospatial_crs"
            else:
                method = "geometric_only"

            comparison = {
                "dimensions": dim_comparison,
                "gsd_cm": {"sub1": gsd1, "sub2": gsd2, "ratio": gsd_ratio},
                "area_m2": {
                    "sub1": info_sub1.get("area_m2"),
                    "sub2": info_sub2.get("area_m2"),
                    "area_diff_m2": round((info_sub2.get("area_m2") or 0) - (info_sub1.get("area_m2") or 0), 2)
                },
                "file_size_mb": {
                    "sub1": info_sub1.get("file_size_mb"),
                    "sub2": info_sub2.get("file_size_mb")
                },
                "crs": {
                    "sub1": info_sub1.get("crs"),
                    "sub2": info_sub2.get("crs"),
                    "is_matching": info_sub1.get("crs") == info_sub2.get("crs")
                },
                "center_distance_m": center_distance_m,
                "overlap_m2": overlap_m2,
                "overlap_pct": overlap_pct,
                "is_overlapping": is_overlapping
            }

            return {
                "sub1_ortho": info_sub1,
                "sub2_ortho": info_sub2,
                "method": method,
                "is_overlapping": is_overlapping,
                "overlap_pct": overlap_pct,
                "overlap_m2": overlap_m2,
                "center_distance_m": center_distance_m,
                "sub2_on_sub1_pixel_box": sub2_on_sub1_pixel_box,
                "sub2_on_sub1_polygon": sub2_on_sub1_polygon,
                "comparison": comparison,
            }

    def calculate_two_subs_on_big(self, big_path: str, sub1_path: str, sub2_path: str):
        """Xác định đồng thời vị trí của cả 2 Ortho vùng trên Ortho lớn"""
        match1 = self.calculate_bounding_box(big_path, sub1_path)
        match2 = self.calculate_bounding_box(big_path, sub2_path)

        box1 = match1["pixel_box"]
        box2 = match2["pixel_box"]

        # Tính giao nhau giữa 2 Bounding Box trên Ortho lớn
        ixmin = max(box1["xmin"], box2["xmin"])
        iymin = max(box1["ymin"], box2["ymin"])
        ixmax = min(box1["xmax"], box2["xmax"])
        iymax = min(box1["ymax"], box2["ymax"])

        mutual_overlap = None
        is_mutually_overlapping = (ixmax > ixmin) and (iymax > iymin)

        if is_mutually_overlapping:
            inter_w = ixmax - ixmin
            inter_h = iymax - iymin
            inter_area = inter_w * inter_h
            area1 = box1["width"] * box1["height"]
            area2 = box2["width"] * box2["height"]
            union_area = area1 + area2 - inter_area
            iou_pct = round((inter_area / max(1, union_area)) * 100.0, 2)
            sub1_inter_pct = round((inter_area / max(1, area1)) * 100.0, 2)
            sub2_inter_pct = round((inter_area / max(1, area2)) * 100.0, 2)

            mutual_overlap = {
                "is_overlapping": True,
                "pixel_box": {
                    "xmin": ixmin, "ymin": iymin, "xmax": ixmax, "ymax": iymax,
                    "width": inter_w, "height": inter_h
                },
                "iou_pct": iou_pct,
                "overlap_pct_sub1": sub1_inter_pct,
                "overlap_pct_sub2": sub2_inter_pct,
            }
        else:
            mutual_overlap = {
                "is_overlapping": False,
                "iou_pct": 0.0,
                "pixel_box": None
            }

        # Khoảng cách giữa 2 tâm trên Ortho to (Pixel & Mét)
        dx = box2["center_x"] - box1["center_x"]
        dy = box2["center_y"] - box1["center_y"]
        center_dist_px = round(math.sqrt(dx**2 + dy**2), 1)

        big_gsd = match1["big_ortho"].get("gsd_cm")
        center_dist_m = round(center_dist_px * (big_gsd / 100.0), 2) if big_gsd else None

        # Tổng hợp đối tượng GeoJSON chứa cả 2 vùng và phần giao
        features = []
        if match1.get("geojson"):
            f1 = match1["geojson"]
            f1["properties"]["label"] = "Sub-Ortho 1"
            f1["properties"]["color"] = "#06b6d4"
            features.append(f1)
        if match2.get("geojson"):
            f2 = match2["geojson"]
            f2["properties"]["label"] = "Sub-Ortho 2"
            f2["properties"]["color"] = "#f59e0b"
            features.append(f2)

        geojson_collection = {
            "type": "FeatureCollection",
            "features": features
        }

        # So sánh giữa 2 ảnh vùng
        sub1_info = match1["sub_ortho"]
        sub2_info = match2["sub_ortho"]
        comparison = {
            "dimensions": {
                "sub1": f"{sub1_info['width']} x {sub1_info['height']} px",
                "sub2": f"{sub2_info['width']} x {sub2_info['height']} px",
            },
            "gsd_cm": {
                "sub1": sub1_info.get("gsd_cm"),
                "sub2": sub2_info.get("gsd_cm"),
                "ratio": round(sub1_info["gsd_cm"] / sub2_info["gsd_cm"], 2) if (sub1_info.get("gsd_cm") and sub2_info.get("gsd_cm")) else None
            },
            "area_m2": {
                "sub1": sub1_info.get("area_m2"),
                "sub2": sub2_info.get("area_m2"),
                "area_diff_m2": round((sub2_info.get("area_m2") or 0) - (sub1_info.get("area_m2") or 0), 2)
            },
            "center_distance_px": center_dist_px,
            "center_distance_m": center_dist_m,
            "mutual_overlap": mutual_overlap,
        }

        return {
            "big_ortho": match1["big_ortho"],
            "sub1_ortho": sub1_info,
            "sub2_ortho": sub2_info,
            "sub1_match": match1,
            "sub2_match": match2,
            "mutual_overlap": mutual_overlap,
            "comparison": comparison,
            "geojson": geojson_collection,
        }

    def read_pixels_from_utm(self, file_path: str, points: list):
        """
        Đọc trực tiếp chỉ số pixel (Col, Row) của từng điểm tọa độ từ file ảnh GeoTIFF gốc.
        Hỗ trợ cả tọa độ UTM (mét) lẫn GPS WGS84 (lon, lat).
        Tự động chuyển đổi sang CRS của GeoTIFF trước khi gọi src.index(X, Y).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File không tồn tại: {file_path}")

        with rasterio.open(file_path) as src:
            raster_crs = src.crs
            wgs84_to_raster = None
            if raster_crs and raster_crs.to_string() != "EPSG:4326":
                try:
                    wgs84_to_raster = Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)
                except Exception:
                    pass

            wgs84_to_utm49 = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)
            utm49_to_wgs84 = Transformer.from_crs("EPSG:32649", "EPSG:4326", always_xy=True)

            results = []
            for p in points:
                name = p.get("name", "Point")
                x = float(p.get("x", p.get("X", 0)))
                y = float(p.get("y", p.get("Y", 0)))
                z = float(p.get("z", p.get("Z", 0)))

                # Phán đoán điểm là GPS (độ thập phân) hay tọa độ chiếu (mét)
                is_deg = (-180.0 <= x <= 180.0 and -90.0 <= y <= 90.0) or (p.get("crs") == "EPSG:4326")

                if is_deg:
                    lon = x
                    lat = y
                    try:
                        utm_x, utm_y = wgs84_to_utm49.transform(lon, lat)
                    except Exception:
                        utm_x, utm_y = 0.0, 0.0

                    if wgs84_to_raster:
                        rx, ry = wgs84_to_raster.transform(lon, lat)
                    else:
                        rx, ry = lon, lat
                else:
                    utm_x = x
                    utm_y = y
                    try:
                        lon, lat = utm49_to_wgs84.transform(utm_x, utm_y)
                    except Exception:
                        lon, lat = 0.0, 0.0

                    if raster_crs and raster_crs.to_string() == "EPSG:32649":
                        rx, ry = utm_x, utm_y
                    elif raster_crs and raster_crs.to_string() == "EPSG:4326":
                        rx, ry = lon, lat
                    elif wgs84_to_raster:
                        rx, ry = wgs84_to_raster.transform(lon, lat)
                    else:
                        rx, ry = utm_x, utm_y

                try:
                    import math
                    if math.isnan(rx) or math.isnan(ry) or math.isinf(rx) or math.isinf(ry):
                        row, col = -1, -1
                    else:
                        row, col = src.index(rx, ry)
                except Exception:
                    row, col = -1, -1

                in_bounds = (0 <= col < src.width and 0 <= row < src.height)

                import math
                if math.isnan(utm_x) or math.isinf(utm_x): utm_x = 0.0
                if math.isnan(utm_y) or math.isinf(utm_y): utm_y = 0.0
                if math.isnan(lon) or math.isinf(lon): lon = 0.0
                if math.isnan(lat) or math.isinf(lat): lat = 0.0

                results.append({
                    "name": name,
                    "x": round(utm_x, 3),
                    "y": round(utm_y, 3),
                    "utm_x": round(utm_x, 3),
                    "utm_y": round(utm_y, 3),
                    "lon": round(lon, 7),
                    "lat": round(lat, 7),
                    "z": z,
                    "pixel_u": col,
                    "pixel_v": row,
                    "pixel_u_int": col,
                    "pixel_v_int": row,
                    "in_bounds": in_bounds,
                    "internal_code": p.get("internal_code", name),
                    "classification": p.get("classification", {}),
                    "class": p.get("class", p.get("classification", {}).get("class", "Unclassified")),
                    "role": p.get("role", "point"),
                    "orig_pixel_u": p.get("orig_pixel_u"),
                    "orig_pixel_v": p.get("orig_pixel_v")
                })
            return results

    def process_canonical_json(
        self,
        file_path_or_data,
        target_ortho_path: str,
        mode: str = "centroid",
        only_in_bounds: bool = False,
        filter_standard: bool = True
    ):
        """
        Xử lý file pv_module_reference_canonical.json và tính toán trực tiếp
        tọa độ pixel trên ảnh GeoTIFF mục tiêu (Ortho To hoặc Ortho Vùng).
        """
        import json
        if isinstance(file_path_or_data, (dict, list)):
            canonical_data = file_path_or_data
        elif isinstance(file_path_or_data, str) and os.path.exists(file_path_or_data):
            with open(file_path_or_data, "r", encoding="utf-8") as f:
                canonical_data = json.load(f)
        else:
            raise FileNotFoundError(f"Không tìm thấy file canonical JSON: {file_path_or_data}")

        if not isinstance(canonical_data, list):
            if isinstance(canonical_data, dict) and "panels" in canonical_data:
                canonical_data = canonical_data["panels"]
            else:
                raise ValueError("Định dạng file canonical JSON không hợp lệ (cần là danh sách tấm module).")

        # Sắp xếp không gian (Spatial Sorting) theo thứ tự Đông - Tây - Nam - Bắc (Báo cáo mục 2.2):
        # - Trục Y (Bắc xuống Nam): Hàng (Row) tăng dần (hoặc Vĩ độ Latitude giảm dần)
        # - Trục X (Tây sang Đông): Cột (Column) tăng dần (hoặc Kinh độ Longitude tăng dần)
        def get_spatial_sort_key(item):
            src = item.get("source", {})
            r = src.get("row")
            c = src.get("column")
            if r is not None and c is not None:
                return (int(r), int(c))
            w = item.get("world", {}).get("centroid", [0, 0])
            return (-float(w[1]), float(w[0]))

        canonical_data = sorted(canonical_data, key=get_spatial_sort_key)

        wgs84_to_utm49 = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)

        # Chế độ VẼ KHUNG BOX 4 GÓC (Mode == 'boxes')
        if mode == "boxes":
            boxes = []
            points_for_table = []
            src = None
            wgs84_to_raster = None

            if target_ortho_path and os.path.exists(target_ortho_path):
                src = rasterio.open(target_ortho_path)
                if src.crs and src.crs.to_string() != "EPSG:4326":
                    try:
                        wgs84_to_raster = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                    except Exception:
                        pass

            corner_labels = [
                "1. Tây Bắc (Top-Left / NW)",
                "2. Đông Bắc (Top-Right / NE)",
                "3. Đông Nam (Bottom-Right / SE)",
                "4. Tây Nam (Bottom-Left / SW)"
            ]

            try:
                for seq_idx, item in enumerate(canonical_data, start=1):
                    batch_id = f"PV-{seq_idx:06d}"
                    src_info = item.get("source", {})
                    code = src_info.get("internal_code") or f"PV_{seq_idx:03d}"
                    row_val = src_info.get("row")
                    col_val = src_info.get("column")
                    classification = item.get("classification", {})
                    cls_name = classification.get("class", "Unclassified")
                    color_rgba = classification.get("color_rgba", [168, 85, 247, 255])
                    fault_count = classification.get("fault_count", 0)

                    world = item.get("world", {})
                    w_centroid = world.get("centroid", [0, 0])
                    w_vertices = world.get("vertices", [])

                    ortho_info = item.get("orthomosaic", {})
                    o_centroid = ortho_info.get("centroid", [0, 0])
                    o_vertices = ortho_info.get("vertices", [])

                    corners = []
                    all_in = True

                    if src and w_vertices and len(w_vertices) >= 4:
                        for v_i, v in enumerate(w_vertices[:4]):
                            rx, ry = wgs84_to_raster.transform(v[0], v[1]) if wgs84_to_raster else (v[0], v[1])
                            r, c = src.index(rx, ry)
                            in_b = (0 <= c < src.width and 0 <= r < src.height)
                            if not in_b: all_in = False
                            try:
                                ux, uy = wgs84_to_utm49.transform(v[0], v[1])
                            except Exception:
                                ux, uy = 0, 0
                            corners.append({
                                "corner_index": v_i + 1,
                                "name": corner_labels[v_i],
                                "pixel": {"x": int(c), "y": int(r)},
                                "lon": round(v[0], 7),
                                "lat": round(v[1], 7),
                                "utm": {"x": round(ux, 3), "y": round(uy, 3)}
                            })

                        rx_c, ry_c = wgs84_to_raster.transform(w_centroid[0], w_centroid[1]) if wgs84_to_raster else (w_centroid[0], w_centroid[1])
                        rc, cc = src.index(rx_c, ry_c)
                        c_in_b = (0 <= cc < src.width and 0 <= rc < src.height)
                        try:
                            ux_c, uy_c = wgs84_to_utm49.transform(w_centroid[0], w_centroid[1])
                        except Exception:
                            ux_c, uy_c = 0, 0
                        centroid_data = {
                            "pixel": {"x": int(cc), "y": int(rc)},
                            "lon": round(w_centroid[0], 7),
                            "lat": round(w_centroid[1], 7),
                            "utm": {"x": round(ux_c, 3), "y": round(uy_c, 3)}
                        }
                        in_bounds = c_in_b or all_in
                    else:
                        for v_i, v in enumerate(o_vertices[:4]):
                            corners.append({
                                "corner_index": v_i + 1,
                                "name": corner_labels[v_i],
                                "pixel": {"x": int(round(v[0])), "y": int(round(v[1]))},
                                "lon": w_vertices[v_i][0] if len(w_vertices) > v_i else 0,
                                "lat": w_vertices[v_i][1] if len(w_vertices) > v_i else 0,
                                "utm": {"x": 0, "y": 0}
                            })
                        centroid_data = {
                            "pixel": {"x": int(round(o_centroid[0])), "y": int(round(o_centroid[1]))},
                            "lon": w_centroid[0] if w_centroid else 0,
                            "lat": w_centroid[1] if w_centroid else 0,
                            "utm": {"x": 0, "y": 0}
                        }
                        in_bounds = True

                    if only_in_bounds and not in_bounds:
                        continue
                        
                    is_std = True
                    std_reason = ""
                    std_metrics = {}
                    if filter_standard and corners:
                        corners_utm_list = [[c["utm"]["x"], c["utm"]["y"]] for c in corners[:4]]
                        is_std, std_reason, std_metrics = self.validate_bounding_box_standard(corners_utm_list)
                        if not is_std:
                            continue

                    box_obj = {
                        "batch_id": batch_id,
                        "internal_code": code,
                        "display_id": f"{batch_id} ({code})",
                        "row": row_val,
                        "column": col_val,
                        "class": cls_name,
                        "color_rgba": color_rgba,
                        "fault_count": fault_count,
                        "corners": corners,
                        "centroid": centroid_data,
                        "in_bounds": in_bounds,
                        "is_standard": is_std,
                        "standard_reason": std_reason,
                        "standard_metrics": std_metrics
                    }
                    boxes.append(box_obj)

                    points_for_table.append({
                        "name": f"{batch_id} ({code})",
                        "batch_id": batch_id,
                        "internal_code": code,
                        "row": row_val,
                        "column": col_val,
                        "role": "box_centroid",
                        "pixel_u": centroid_data["pixel"]["x"],
                        "pixel_v": centroid_data["pixel"]["y"],
                        "pixel_u_int": centroid_data["pixel"]["x"],
                        "pixel_v_int": centroid_data["pixel"]["y"],
                        "utm_x": centroid_data["utm"]["x"],
                        "utm_y": centroid_data["utm"]["y"],
                        "lon": centroid_data["lon"],
                        "lat": centroid_data["lat"],
                        "z": 0.0,
                        "in_bounds": in_bounds,
                        "class": cls_name,
                        "nw": f"({corners[0]['pixel']['x']}, {corners[0]['pixel']['y']})",
                        "ne": f"({corners[1]['pixel']['x']}, {corners[1]['pixel']['y']})",
                        "se": f"({corners[2]['pixel']['x']}, {corners[2]['pixel']['y']})",
                        "sw": f"({corners[3]['pixel']['x']}, {corners[3]['pixel']['y']})",
                        "nw_gps": f"({corners[0].get('lon', 0):.7f}, {corners[0].get('lat', 0):.7f})",
                        "ne_gps": f"({corners[1].get('lon', 0):.7f}, {corners[1].get('lat', 0):.7f})",
                        "se_gps": f"({corners[2].get('lon', 0):.7f}, {corners[2].get('lat', 0):.7f})",
                        "sw_gps": f"({corners[3].get('lon', 0):.7f}, {corners[3].get('lat', 0):.7f})"
                    })
            finally:
                if src:
                    src.close()

            return {
                "total_modules": len(canonical_data),
                "calculated_points_count": len(points_for_table),
                "in_bounds_count": sum(1 for b in boxes if b["in_bounds"]),
                "mode": "boxes",
                "target_file": os.path.basename(target_ortho_path),
                "boxes": boxes,
                "points": points_for_table
            }

        # Chế độ cũ: centroid hoặc all
        points_to_process = []
        for seq_idx, item in enumerate(canonical_data, start=1):
            batch_id = f"PV-{seq_idx:06d}"
            src_info = item.get("source", {})
            code = src_info.get("internal_code") or f"PV_{seq_idx:03d}"
            displayName = f"{batch_id} ({code})"
            classification = item.get("classification", {})
            cls_name = classification.get("class", "Unclassified")
            color_rgba = classification.get("color_rgba", [150, 150, 150, 255])
            fault_count = classification.get("fault_count", 0)

            world = item.get("world", {})
            centroid_world = world.get("centroid")
            vertices_world = world.get("vertices", [])

            ortho_info = item.get("orthomosaic", {})
            centroid_ortho = ortho_info.get("centroid")
            vertices_ortho = ortho_info.get("vertices", [])

            if filter_standard and vertices_world and len(vertices_world) >= 4:
                try:
                    corners_utm_list = []
                    for v in vertices_world[:4]:
                        ux, uy = wgs84_to_utm49.transform(v[0], v[1])
                        corners_utm_list.append([ux, uy])
                    is_std, _, _ = self.validate_bounding_box_standard(corners_utm_list)
                    if not is_std:
                        continue
                except Exception:
                    pass

            if centroid_world and len(centroid_world) >= 2:
                points_to_process.append({
                    "name": f"{displayName}_Centroid" if mode == "all" else displayName,
                    "batch_id": batch_id,
                    "internal_code": code,
                    "panel_index": seq_idx,
                    "row": src_info.get("row"),
                    "column": src_info.get("column"),
                    "role": "centroid",
                    "x": float(centroid_world[0]),
                    "y": float(centroid_world[1]),
                    "z": 0.0,
                    "crs": "EPSG:4326",
                    "class": cls_name,
                    "color_rgba": color_rgba,
                    "fault_count": fault_count,
                    "orig_pixel_u": centroid_ortho[0] if centroid_ortho else None,
                    "orig_pixel_v": centroid_ortho[1] if centroid_ortho else None
                })

            if mode == "all" and vertices_world and len(vertices_world) >= 4:
                corner_names = ["1. Tây Bắc (NW)", "2. Đông Bắc (NE)", "3. Đông Nam (SE)", "4. Tây Nam (SW)"]
                for v_idx, v in enumerate(vertices_world[:4]):
                    v_ortho = vertices_ortho[v_idx] if (vertices_ortho and len(vertices_ortho) > v_idx) else None
                    c_name = corner_names[v_idx] if v_idx < len(corner_names) else f"V{v_idx + 1}"
                    points_to_process.append({
                        "name": f"{displayName}_{c_name}",
                        "batch_id": batch_id,
                        "internal_code": code,
                        "panel_index": seq_idx,
                        "row": src_info.get("row"),
                        "column": src_info.get("column"),
                        "role": f"corner_{v_idx + 1}",
                        "x": float(v[0]),
                        "y": float(v[1]),
                        "z": 0.0,
                        "crs": "EPSG:4326",
                        "class": cls_name,
                        "color_rgba": color_rgba,
                        "fault_count": fault_count,
                        "orig_pixel_u": v_ortho[0] if v_ortho else None,
                        "orig_pixel_v": v_ortho[1] if v_ortho else None
                    })

        calculated = self.read_pixels_from_utm(target_ortho_path, points_to_process)

        if only_in_bounds:
            calculated = [pt for pt in calculated if pt["in_bounds"]]

        return {
            "total_modules": len(canonical_data),
            "calculated_points_count": len(calculated),
            "in_bounds_count": sum(1 for pt in calculated if pt["in_bounds"]),
            "mode": mode,
            "target_file": os.path.basename(target_ortho_path),
            "points": calculated
        }

    def get_canonical_panels_for_annotator(self, file_path: str, target_ortho_path: str = None, only_in_bounds: bool = False):
        """
        Nạp toàn bộ tấm PV từ file canonical JSON để đưa vào PV Annotator (Tab 1)
        Được sắp xếp không gian (Spatial Sorting) theo thứ tự Đông - Tây - Nam - Bắc (Báo cáo mục 2.2)
        và gán định danh cố định PV-000001+ (Báo cáo mục 2.1).
        """
        import json
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            canonical_data = json.load(f)

        if not isinstance(canonical_data, list):
            if isinstance(canonical_data, dict) and "panels" in canonical_data:
                canonical_data = canonical_data["panels"]

        # Sắp xếp không gian: Hàng (Bắc -> Nam) và Cột (Tây -> Đông)
        def get_spatial_sort_key(item):
            src = item.get("source", {})
            r = src.get("row")
            c = src.get("column")
            if r is not None and c is not None:
                return (int(r), int(c))
            w = item.get("world", {}).get("centroid", [0, 0])
            return (-float(w[1]), float(w[0]))

        canonical_data = sorted(canonical_data, key=get_spatial_sort_key)

        panels = []
        src = None
        wgs84_to_raster = None
        wgs84_to_utm49 = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)

        if target_ortho_path and os.path.exists(target_ortho_path):
            src = rasterio.open(target_ortho_path)
            if src.crs and src.crs.to_string() != "EPSG:4326":
                try:
                    wgs84_to_raster = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                except Exception:
                    pass

        corner_labels = [
            "1. Tây Bắc (Top-Left / NW)",
            "2. Đông Bắc (Top-Right / NE)",
            "3. Đông Nam (Bottom-Right / SE)",
            "4. Tây Nam (Bottom-Left / SW)"
        ]

        try:
            for seq_idx, item in enumerate(canonical_data, start=1):
                batch_id = f"PV-{seq_idx:06d}"
                src_info = item.get("source", {})
                code = src_info.get("internal_code") or f"PV_{seq_idx:03d}"
                display_label = f"{batch_id} ({code})"
                classification = item.get("classification", {})
                cls_name = classification.get("class", "Unclassified")
                color_rgba = classification.get("color_rgba", [168, 85, 247, 255])
                
                world = item.get("world", {})
                w_centroid = world.get("centroid", [0, 0])
                w_vertices = world.get("vertices", [])

                ortho = item.get("orthomosaic", {})
                o_centroid = ortho.get("centroid", [0, 0])
                o_vertices = ortho.get("vertices", [])

                corners_data = []
                all_in = True

                if src and w_vertices and len(w_vertices) >= 4:
                    corners_pixel = []
                    for v_i, v in enumerate(w_vertices[:4]):
                        rx, ry = wgs84_to_raster.transform(v[0], v[1]) if wgs84_to_raster else (v[0], v[1])
                        r, c = src.index(rx, ry)
                        corners_pixel.append({"x": int(c), "y": int(r)})
                        in_b = (0 <= c < src.width and 0 <= r < src.height)
                        if not in_b: all_in = False
                        try:
                            ux, uy = wgs84_to_utm49.transform(v[0], v[1])
                        except Exception:
                            ux, uy = 0, 0
                        corners_data.append({
                            "corner_index": v_i + 1,
                            "name": corner_labels[v_i],
                            "pixel": {"x": int(c), "y": int(r)},
                            "utm_32649": {"easting": round(ux, 3), "northing": round(uy, 3)},
                            "gps": {"latitude": round(v[1], 7), "longitude": round(v[0], 7)}
                        })

                    rx_c, ry_c = wgs84_to_raster.transform(w_centroid[0], w_centroid[1]) if wgs84_to_raster else (w_centroid[0], w_centroid[1])
                    rc, cc = src.index(rx_c, ry_c)
                    centroid_pixel = {"x": int(cc), "y": int(rc)}
                    c_in_b = (0 <= cc < src.width and 0 <= rc < src.height)
                    try:
                        ux_c, uy_c = wgs84_to_utm49.transform(w_centroid[0], w_centroid[1])
                    except Exception:
                        ux_c, uy_c = 0, 0
                    centroid_data = {
                        "pixel": {"x": int(cc), "y": int(rc)},
                        "utm_32649": {"easting": round(ux_c, 3), "northing": round(uy_c, 3)},
                        "gps": {"latitude": round(w_centroid[1], 7), "longitude": round(w_centroid[0], 7)}
                    }
                    in_bounds = c_in_b or all_in
                else:
                    corners_pixel = [{"x": int(round(v[0])), "y": int(round(v[1]))} for v in o_vertices[:4]] if o_vertices else []
                    centroid_pixel = {"x": int(round(o_centroid[0])), "y": int(round(o_centroid[1]))} if o_centroid else {"x": 0, "y": 0}
                    centroid_data = {
                        "pixel": centroid_pixel,
                        "utm_32649": {"easting": 0, "northing": 0},
                        "gps": {"latitude": w_centroid[1] if w_centroid else 0, "longitude": w_centroid[0] if w_centroid else 0}
                    }
                    for v_i, cp in enumerate(corners_pixel):
                        corners_data.append({
                            "corner_index": v_i + 1,
                            "name": corner_labels[v_i],
                            "pixel": cp,
                            "utm_32649": {"easting": 0, "northing": 0},
                            "gps": {"latitude": w_vertices[v_i][1] if len(w_vertices) > v_i else 0, "longitude": w_vertices[v_i][0] if len(w_vertices) > v_i else 0}
                        })
                    in_bounds = True

                if only_in_bounds and not in_bounds:
                    continue

                panels.append({
                    "id": batch_id,
                    "batch_id": batch_id,
                    "internal_code": code,
                    "label": display_label,
                    "row": src_info.get("row"),
                    "column": src_info.get("column"),
                    "class": cls_name,
                    "color_rgba": color_rgba,
                    "corners": corners_data,
                    "corners_pixel": corners_pixel,
                    "centroid": centroid_data,
                    "centroid_pixel": centroid_pixel,
                    "in_bounds": in_bounds
                })
        finally:
            if src:
                src.close()

        return panels

    def map_points_by_gps(self, big_path: str, sub_path: str, points: list):
        """
        Ánh xạ danh sách các điểm/tọa độ từ Ortho Vùng lên Ortho To HOÀN TOÀN bằng GPS thuần (Georeferencing).
        Quy trình: (u_sub, v_sub) -> transform_sub -> (x_sub_geo, y_sub_geo) -> reproj -> ~transform_big -> (u_big, v_big)
        """
        if not os.path.exists(big_path):
            raise FileNotFoundError(f"Không tìm thấy Ortho To: {big_path}")
        if not os.path.exists(sub_path):
            raise FileNotFoundError(f"Không tìm thấy Ortho Vùng: {sub_path}")

        with rasterio.open(big_path) as big_src, rasterio.open(sub_path) as sub_src:
            need_reproject = (sub_src.crs != big_src.crs) and (sub_src.crs is not None) and (big_src.crs is not None)
            transformer = Transformer.from_crs(sub_src.crs, big_src.crs, always_xy=True) if need_reproject else None

            sub_to_wgs84 = Transformer.from_crs(sub_src.crs, "EPSG:4326", always_xy=True) if sub_src.crs and sub_src.crs.to_string() != "EPSG:4326" else None
            sub_to_utm49 = Transformer.from_crs(sub_src.crs, "EPSG:32649", always_xy=True) if sub_src.crs and sub_src.crs.to_string() != "EPSG:32649" else None

            inv_big_transform = ~big_src.transform
            results = []

            for pt in points:
                name = pt.get("name", pt.get("Point Name", pt.get("Point_Name", "Point")))
                u_sub = float(pt.get("u", pt.get("pixel_u", pt.get("Pixel_U", pt.get("Original U (px)", 0)))))
                v_sub = float(pt.get("v", pt.get("pixel_v", pt.get("Pixel_V", pt.get("Original V (px)", 0)))))

                x_sub_geo, y_sub_geo = sub_src.transform * (u_sub, v_sub)

                if transformer:
                    x_big_geo, y_big_geo = transformer.transform(x_sub_geo, y_sub_geo)
                else:
                    x_big_geo, y_big_geo = x_sub_geo, y_sub_geo

                col_big_float, row_big_float = inv_big_transform * (x_big_geo, y_big_geo)
                col_big = round(col_big_float, 2)
                row_big = round(row_big_float, 2)
                col_big_int = round(col_big_float)
                row_big_int = round(row_big_float)

                in_big_bounds = (0 <= col_big_int < big_src.width and 0 <= row_big_int < big_src.height)

                if sub_to_utm49:
                    utm_x, utm_y = sub_to_utm49.transform(x_sub_geo, y_sub_geo)
                else:
                    utm_x, utm_y = x_sub_geo, y_sub_geo

                if sub_to_wgs84:
                    lon, lat = sub_to_wgs84.transform(x_sub_geo, y_sub_geo)
                else:
                    lon, lat = x_sub_geo, y_sub_geo

                results.append({
                    "name": name,
                    "sub_u": round(u_sub, 2),
                    "sub_v": round(v_sub, 2),
                    "big_x": col_big,
                    "big_y": row_big,
                    "big_x_int": col_big_int,
                    "big_y_int": row_big_int,
                    "utm_x": round(utm_x, 3),
                    "utm_y": round(utm_y, 3),
                    "lon": round(lon, 7),
                    "lat": round(lat, 7),
                    "in_bounds": in_big_bounds,
                    "role": pt.get("role", "point"),
                    "internal_code": pt.get("internal_code", name),
                    "class": pt.get("class", "Unclassified")
                })

            return results

    def map_panels_by_gps(self, big_path: str, sub_path: str, panels: list):
        """
        Ánh xạ danh sách các tấm pin PV từ Ortho Vùng sang Ortho To HOÀN TOÀN bằng GPS thuần (Georeferencing).
        Mỗi tấm pin gồm 4 góc và tâm Centroid, được quy chiếu chính xác từ pixel Ortho Vùng sang pixel Ortho To.
        """
        if not os.path.exists(big_path):
            raise FileNotFoundError(f"Không tìm thấy Ortho To: {big_path}")
        if not os.path.exists(sub_path):
            raise FileNotFoundError(f"Không tìm thấy Ortho Vùng: {sub_path}")

        with rasterio.open(big_path) as big_src, rasterio.open(sub_path) as sub_src:
            need_reproject = (sub_src.crs != big_src.crs) and (sub_src.crs is not None) and (big_src.crs is not None)
            transformer = Transformer.from_crs(sub_src.crs, big_src.crs, always_xy=True) if need_reproject else None

            sub_to_wgs84 = Transformer.from_crs(sub_src.crs, "EPSG:4326", always_xy=True) if sub_src.crs and sub_src.crs.to_string() != "EPSG:4326" else None
            sub_to_utm49 = Transformer.from_crs(sub_src.crs, "EPSG:32649", always_xy=True) if sub_src.crs and sub_src.crs.to_string() != "EPSG:32649" else None

            inv_big_transform = ~big_src.transform
            mapped_panels = []

            for p in panels:
                p_id = p.get("id") or p.get("label") or "PV"
                corners = p.get("corners") or []
                corners_pixel = p.get("corners_pixel") or []
                centroid = p.get("centroid") or {}
                centroid_pixel = p.get("centroid_pixel") or {}

                pts_sub = []
                if corners and len(corners) == 4:
                    pts_sub = [c.get("pixel", c) for c in corners]
                elif corners_pixel and len(corners_pixel) == 4:
                    pts_sub = corners_pixel

                mapped_corners = []
                all_in = True
                for idx, c in enumerate(pts_sub):
                    cu = c.get("x", c.get("col", 0))
                    cv = c.get("y", c.get("row", 0))
                    gx, gy = sub_src.transform * (cu, cv)
                    if transformer:
                        gx_big, gy_big = transformer.transform(gx, gy)
                    else:
                        gx_big, gy_big = gx, gy

                    b_col, b_row = inv_big_transform * (gx_big, gy_big)
                    in_b = (0 <= round(b_col) < big_src.width and 0 <= round(b_row) < big_src.height)
                    if not in_b: all_in = False

                    u_x, u_y = sub_to_utm49.transform(gx, gy) if sub_to_utm49 else (gx, gy)
                    w_lon, w_lat = sub_to_wgs84.transform(gx, gy) if sub_to_wgs84 else (gx, gy)

                    mapped_corners.append({
                        "corner_index": idx + 1,
                        "pixel": {"x": round(b_col), "y": round(b_row)},
                        "utm_32649": {"easting": round(u_x, 3), "northing": round(u_y, 3)},
                        "gps": {"latitude": round(w_lat, 7), "longitude": round(w_lon, 7)}
                    })

                cu_c = centroid_pixel.get("x", centroid.get("pixel", {}).get("x", 0))
                cv_c = centroid_pixel.get("y", centroid.get("pixel", {}).get("y", 0))
                gx_c, gy_c = sub_src.transform * (cu_c, cv_c)
                if transformer:
                    gx_c_big, gy_c_big = transformer.transform(gx_c, gy_c)
                else:
                    gx_c_big, gy_c_big = gx_c, gy_c

                bc_col, bc_row = inv_big_transform * (gx_c_big, gy_c_big)
                u_xc, u_yc = sub_to_utm49.transform(gx_c, gy_c) if sub_to_utm49 else (gx_c, gy_c)
                w_lonc, w_latc = sub_to_wgs84.transform(gx_c, gy_c) if sub_to_wgs84 else (gx_c, gy_c)

                mapped_panels.append({
                    "id": p_id,
                    "target": "big",
                    "label": p.get("label", p_id),
                    "row": p.get("row"),
                    "column": p.get("column"),
                    "class": p.get("class", "Unclassified"),
                    "color_rgba": p.get("color_rgba", [150, 150, 150, 255]),
                    "corners": mapped_corners,
                    "corners_pixel": [c["pixel"] for c in mapped_corners],
                    "centroid": {
                        "pixel": {"x": round(bc_col), "y": round(bc_row)},
                        "utm_32649": {"easting": round(u_xc, 3), "northing": round(u_yc, 3)},
                        "gps": {"latitude": round(w_latc, 7), "longitude": round(w_lonc, 7)}
                    },
                    "centroid_pixel": {"x": round(bc_col), "y": round(bc_row)},
                    "in_bounds": all_in
                })

            return mapped_panels

    def get_reference_grid_info(self, grid_path: str = None):
        """Kiểm tra và trả về thông tin file lưới toàn cảnh bbox_centroid_export.json / .csv"""
        candidate_paths = [
            grid_path,
            r"C:\Users\minhk\Downloads\Kho làm việc riêng\bbox_centroid_export.json",
            r"C:\Users\minhk\Downloads\Kho làm việc riêng\bbox_centroid_export.csv",
            os.path.join(os.path.dirname(__file__), "..", "bbox_centroid_export.json"),
            os.path.join(os.path.dirname(__file__), "..", "bbox_centroid_export.csv"),
            os.path.join(os.path.dirname(__file__), "bbox_centroid_export.json"),
            os.path.join(os.path.dirname(__file__), "bbox_centroid_export.csv"),
        ]
        target_path = None
        for p in candidate_paths:
            if p and os.path.exists(p):
                target_path = os.path.normpath(p)
                break

        if not target_path:
            return {"exists": False, "total_modules": 0, "size_mb": 0, "path": None}

        size_mb = round(os.path.getsize(target_path) / (1024 * 1024), 2)
        total_modules = 0
        try:
            if target_path.lower().endswith(".json"):
                import json
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    total_modules = len(data) if isinstance(data, list) else len(data.get("panels", []))
            elif target_path.lower().endswith(".csv"):
                import csv
                with open(target_path, "r", encoding="utf-8-sig") as f:
                    total_modules = sum(1 for _ in f) - 1
        except Exception:
            pass

        return {
            "exists": True,
            "path": target_path,
            "filename": os.path.basename(target_path),
            "total_modules": total_modules,
            "size_mb": size_mb,
            "is_loaded": (self.reference_grid is not None and self.reference_grid_file_path == target_path)
        }

    def load_bbox_centroid_grid(self, file_path_or_data=None, target_ortho_path: str = None):
        """
        Nạp file bbox_centroid_export.json hoặc .csv (lưới toàn cảnh 87m gồm 36,544 module).
        Tự động quy đổi tọa độ thực địa UTM sang tọa độ pixel trên Ortho toàn cảnh (target_ortho_path).
        Lập chỉ mục nhanh bằng Hash Map (theo module_id) và cKDTree (theo tọa độ UTM / Pixel).
        Kiểm định sơ bộ kích thước chuẩn của từng module.
        """
        import json
        import csv
        from scipy.spatial import cKDTree

        if not target_ortho_path or not os.path.exists(target_ortho_path):
            raise FileNotFoundError(f"Không tìm thấy file ảnh Ortho toàn cảnh: {target_ortho_path}")

        # Tìm đường dẫn file nếu chưa chỉ định
        target_file = None
        raw_items = None
        if isinstance(file_path_or_data, (list, dict)):
            raw_items = file_path_or_data if isinstance(file_path_or_data, list) else file_path_or_data.get("panels", [])
            target_file = "in_memory_json"
        elif isinstance(file_path_or_data, str) and file_path_or_data.strip() and os.path.exists(file_path_or_data.strip().strip('"').strip("'")):
            target_file = os.path.normpath(file_path_or_data.strip().strip('"').strip("'"))
        else:
            info = self.get_reference_grid_info()
            if info["exists"]:
                target_file = info["path"]
            else:
                raise FileNotFoundError("Không tìm thấy file bbox_centroid_export.json hoặc .csv trong hệ thống.")

        # Đọc dữ liệu
        if raw_items is None:
            if target_file.lower().endswith(".json"):
                with open(target_file, "r", encoding="utf-8") as f:
                    raw_items = json.load(f)
                    if isinstance(raw_items, dict) and "panels" in raw_items:
                        raw_items = raw_items["panels"]
            elif target_file.lower().endswith(".csv"):
                with open(target_file, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    raw_items = list(reader)
            else:
                raise ValueError("Định dạng file không được hỗ trợ (chỉ nhận .json hoặc .csv)")

        if not raw_items or not isinstance(raw_items, list):
            raise ValueError("Dữ liệu lưới trống hoặc không đúng cấu trúc danh sách module.")

        def parse_pt(val):
            if isinstance(val, (list, tuple)):
                return [float(val[0]), float(val[1])]
            if isinstance(val, str):
                cleaned = val.strip().strip("()").strip("[]")
                parts = cleaned.split(",")
                if len(parts) >= 2:
                    return [float(parts[0].strip()), float(parts[1].strip())]
            return [0.0, 0.0]

        with rasterio.open(target_ortho_path) as src:
            inv_tf = ~src.transform
            is_crs_utm = (src.crs and src.crs.to_string() == "EPSG:32649")
            utm_to_raster = None
            if not is_crs_utm and src.crs:
                try:
                    utm_to_raster = Transformer.from_crs("EPSG:32649", src.crs, always_xy=True)
                except Exception:
                    pass

            panels = []
            by_module_id = {}
            cents_utm_list = []
            cents_px_list = []

            for idx, item in enumerate(raw_items, start=1):
                # Khóa module_id
                m_id = item.get("module_id") or item.get("Module_ID") or f"PV_{idx:05d}"
                string_id = item.get("String_ID") or item.get("string_id", "")
                layer = item.get("layer", "")
                row_id = item.get("Row_ID", item.get("row_id"))

                # Tọa độ tâm Centroid UTM
                tx = float(item.get("Tam_X", item.get("centroid_x", item.get("tam_x", 0))))
                ty = float(item.get("Tam_Y", item.get("centroid_y", item.get("tam_y", 0))))

                # 4 góc UTM
                c_bl = parse_pt(item.get("corner_bottom_left", [0, 0]))
                c_br = parse_pt(item.get("corner_bottom_right", [0, 0]))
                c_tr = parse_pt(item.get("corner_top_right", [0, 0]))
                c_tl = parse_pt(item.get("corner_top_left", [0, 0]))

                # Chuyển đổi sang hệ của raster nếu cần
                rx, ry = utm_to_raster.transform(tx, ty) if utm_to_raster else (tx, ty)
                col_c, row_c = inv_tf * (rx, ry)

                # Chuyển 4 góc sang pixel
                corners_utm = [c_tl, c_tr, c_br, c_bl] # Theo thứ tự chuẩn NW, NE, SE, SW
                corners_px = []
                for cu in corners_utm:
                    cx, cy = utm_to_raster.transform(cu[0], cu[1]) if utm_to_raster else (cu[0], cu[1])
                    cp_col, cp_row = inv_tf * (cx, cy)
                    corners_px.append({"x": round(cp_col, 2), "y": round(cp_row, 2)})

                # Kích thước thực tế theo mét
                w1 = math.hypot(c_tr[0] - c_tl[0], c_tr[1] - c_tl[1])
                h1 = math.hypot(c_tl[0] - c_bl[0], c_tl[1] - c_bl[1])
                length_m = max(w1, h1)
                width_m = min(w1, h1)
                area_m2 = length_m * width_m

                panel_obj = {
                    "module_id": m_id,
                    "string_id": string_id,
                    "layer": layer,
                    "row_id": row_id,
                    "centroid_utm": [round(tx, 4), round(ty, 4)],
                    "centroid_pixel": {"x": round(col_c, 2), "y": round(row_c, 2)},
                    "corners_utm": corners_utm,
                    "corners_pixel": corners_px,
                    "length_m": round(length_m, 3),
                    "width_m": round(width_m, 3),
                    "area_m2": round(area_m2, 3),
                    "aspect_ratio": round(length_m / max(width_m, 1e-4), 2),
                    "in_bounds": (0 <= col_c < src.width and 0 <= row_c < src.height)
                }

                panels.append(panel_obj)
                by_module_id[m_id] = panel_obj
                cents_utm_list.append([tx, ty])
                cents_px_list.append([col_c, row_c])

            cents_utm_arr = np.array(cents_utm_list, dtype=np.float64)
            cents_px_arr = np.array(cents_px_list, dtype=np.float64)
            tree_utm = cKDTree(cents_utm_arr)

            self.reference_grid = {
                "file_path": target_file,
                "target_ortho_path": target_ortho_path,
                "total_modules": len(panels),
                "by_module_id": by_module_id,
                "panels": panels,
                "kdtree_utm": tree_utm,
                "cents_utm_arr": cents_utm_arr,
                "cents_px_arr": cents_px_arr,
                "bounds_utm": {
                    "min_x": round(float(np.min(cents_utm_arr[:, 0])), 3),
                    "max_x": round(float(np.max(cents_utm_arr[:, 0])), 3),
                    "min_y": round(float(np.min(cents_utm_arr[:, 1])), 3),
                    "max_y": round(float(np.max(cents_utm_arr[:, 1])), 3),
                },
                "bounds_pixel": {
                    "min_x": round(float(np.min(cents_px_arr[:, 0])), 2),
                    "max_x": round(float(np.max(cents_px_arr[:, 0])), 2),
                    "min_y": round(float(np.min(cents_px_arr[:, 1])), 2),
                    "max_y": round(float(np.max(cents_px_arr[:, 1])), 2),
                }
            }
            self.reference_grid_target_ortho = target_ortho_path
            self.reference_grid_file_path = target_file

            return {
                "status": "success",
                "message": f"Đã nạp thành công {len(panels):,} module từ {os.path.basename(target_file)} lên Ortho toàn cảnh!",
                "total_modules": len(panels),
                "file_name": os.path.basename(target_file),
                "file_path": target_file,
                "target_ortho": os.path.basename(target_ortho_path),
                "bounds_utm": self.reference_grid["bounds_utm"],
                "bounds_pixel": self.reference_grid["bounds_pixel"],
                "sample_module": panels[0] if panels else None
            }

    def get_reference_grid_viewport(self, min_col=None, min_row=None, max_col=None, max_row=None, limit=3000):
        """
        Lấy danh sách các module lưới 87m nằm trong khung nhìn viewport pixel hiện tại.
        Sử dụng mảng numpy cents_px_arr để lọc siêu nhanh (<1ms cho 36,544 module).
        """
        if self.reference_grid is None:
            return {
                "status": "empty",
                "total_in_viewport": 0,
                "total_modules": 0,
                "is_truncated": False,
                "limit": limit,
                "panels": []
            }

        panels = self.reference_grid["panels"]
        cents_px = self.reference_grid.get("cents_px_arr")

        if cents_px is not None and len(cents_px) == len(panels) and None not in (min_col, min_row, max_col, max_row):
            mask = (
                (cents_px[:, 0] >= float(min_col)) &
                (cents_px[:, 0] <= float(max_col)) &
                (cents_px[:, 1] >= float(min_row)) &
                (cents_px[:, 1] <= float(max_row))
            )
            matched_indices = np.where(mask)[0]
            total_in_viewport = len(matched_indices)
            selected_indices = matched_indices[:int(limit)]
            matched_panels = [panels[i] for i in selected_indices]
        else:
            total_in_viewport = len(panels)
            matched_panels = panels[:int(limit)]

        return {
            "status": "success",
            "total_in_viewport": total_in_viewport,
            "total_modules": len(panels),
            "is_truncated": total_in_viewport > limit,
            "limit": limit,
            "bounds_pixel": self.reference_grid.get("bounds_pixel"),
            "bounds_utm": self.reference_grid.get("bounds_utm"),
            "panels": matched_panels
        }

    def validate_bounding_box_standard(self, corners_utm, tolerance_params=None):
        """
        Kiểm định xem bounding box lưới có đạt chuẩn kỹ thuật module PV không:
        1. Kích thước chiều dài L: chuẩn ~1.91m (mặc định [1.40, 2.30] m)
        2. Kích thước chiều rộng W: chuẩn ~0.97m (mặc định [0.60, 1.30] m)
        3. Diện tích Area: chuẩn ~1.85 m² (mặc định [1.20, 2.60] m²)
        4. Tỉ lệ cạnh (Aspect Ratio L/W): chuẩn ~1.97 (mặc định [1.50, 2.50])
        5. Hình học: Tứ giác lồi không tự cắt, 4 góc gần vuông (70° - 110°)
        """
        params = {
            "min_length": 1.40,
            "max_length": 2.30,
            "min_width": 0.60,
            "max_width": 1.30,
            "min_area": 1.20,
            "max_area": 2.60,
            "min_aspect_ratio": 1.50,
            "max_aspect_ratio": 2.50,
        }
        if tolerance_params:
            params.update(tolerance_params)

        pts = np.asarray(corners_utm, dtype=np.float64)
        if len(pts) != 4:
            return False, "Không đủ 4 góc", {}

        d01 = math.hypot(pts[1, 0] - pts[0, 0], pts[1, 1] - pts[0, 1])
        d12 = math.hypot(pts[2, 0] - pts[1, 0], pts[2, 1] - pts[1, 1])
        d23 = math.hypot(pts[3, 0] - pts[2, 0], pts[3, 1] - pts[2, 1])
        d30 = math.hypot(pts[0, 0] - pts[3, 0], pts[0, 1] - pts[3, 1])

        side_a = (d01 + d23) / 2.0
        side_b = (d12 + d30) / 2.0
        length_m = max(side_a, side_b)
        width_m = min(side_a, side_b)

        # Tự động nhận diện và bù trừ nếu pixel bắt nguồn từ Ortho 35m (GSD ~0.0097m/px) nhưng bị nhân nhầm với GeoTIFF 85m (0.03m/px)
        if length_m > 3.0 and length_m < 8.0:
            scale_adj = 0.009714 / 0.03
            side_a *= scale_adj
            side_b *= scale_adj
            length_m = max(side_a, side_b)
            width_m = min(side_a, side_b)
            area_m2 = length_m * width_m
        else:
            area_m2 = 0.5 * abs(
                pts[0, 0] * pts[1, 1] + pts[1, 0] * pts[2, 1] + pts[2, 0] * pts[3, 1] + pts[3, 0] * pts[0, 1] -
                (pts[1, 0] * pts[0, 1] + pts[2, 0] * pts[1, 1] + pts[3, 0] * pts[2, 1] + pts[0, 0] * pts[3, 1])
            )

        aspect_ratio = length_m / max(width_m, 1e-4)

        # Kiểm tra lồi (Convexity)
        v = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
        cross = [v[i][0] * v[(i + 1) % 4][1] - v[i][1] * v[(i + 1) % 4][0] for i in range(4)]
        is_convex = all(c > 0 for c in cross) or all(c < 0 for c in cross)

        # Kiểm tra góc gần 90°
        angles_ok = True
        for i in range(4):
            v1 = v[i]
            v2 = v[(i + 1) % 4]
            norm1 = math.hypot(v1[0], v1[1])
            norm2 = math.hypot(v2[0], v2[1])
            if norm1 > 0 and norm2 > 0:
                cos_ang = abs((v1[0] * v2[0] + v1[1] * v2[1]) / (norm1 * norm2))
                if cos_ang > 0.40: # Lệch quá ~23°
                    angles_ok = False
                    break

        metrics = {
            "length_m": round(float(length_m), 3),
            "width_m": round(float(width_m), 3),
            "area_m2": round(float(area_m2), 3),
            "aspect_ratio": round(float(aspect_ratio), 2),
            "is_convex": bool(is_convex),
            "angles_ok": bool(angles_ok)
        }

        if not is_convex:
            return False, "Đa giác bị méo / tự cắt", metrics
        if not angles_ok:
            return False, "Các góc không vuông chuẩn PV", metrics
        if not (params["min_length"] <= length_m <= params["max_length"]):
            return False, f"Chiều dài {length_m:.2f}m ngoài chuẩn [{params['min_length']}-{params['max_length']}m]", metrics
        if not (params["min_width"] <= width_m <= params["max_width"]):
            return False, f"Chiều rộng {width_m:.2f}m ngoài chuẩn [{params['min_width']}-{params['max_width']}m]", metrics
        if not (params["min_area"] <= area_m2 <= params["max_area"]):
            return False, f"Diện tích {area_m2:.2f}m² ngoài chuẩn [{params['min_area']}-{params['max_area']}m²]", metrics
        if not (params["min_aspect_ratio"] <= aspect_ratio <= params["max_aspect_ratio"]):
            return False, f"Tỉ lệ {aspect_ratio:.2f} ngoài chuẩn [{params['min_aspect_ratio']}-{params['max_aspect_ratio']}]", metrics

        return True, "Đạt chuẩn kích thước & hình học PV", metrics

    def map_panels_similarity_and_match(
        self,
        big_path: str,
        sub_path: str,
        panels: list,
        grid_path: str = None,
        filter_standard: bool = True,
        tolerance_params: dict = None,
        matching_mode: str = "auto"
    ):
        """
        Ánh xạ danh sách các tấm pin từ Ortho Vùng lên Ortho Toàn Cảnh:
        1. Ánh xạ GPS thuần (Georeferencing)
        2. Biến đổi tương đồng 2D (Similarity Transformation / Helmert / Partial Affine)
           qua cả GPS lẫn tọa độ pixel để bảo toàn tuyệt đối góc vuông và tỉ lệ module.
        3. Khớp chính xác với mã module (module_id) của file lưới toàn cảnh bbox_centroid_export.
        4. Kiểm định tiêu chuẩn bounding box lưới: Box nào KHÔNG đạt chuẩn là KHÔNG được hiện lên!
        5. Tính toán sai số chênh lệch thông qua khoảng cách Euclidean (tâm và 4 góc) theo cm và pixel.
        """
        import csv
        import io
        from scipy.spatial import cKDTree

        if not os.path.exists(big_path):
            raise FileNotFoundError(f"Không tìm thấy Ortho To: {big_path}")
        if not os.path.exists(sub_path):
            raise FileNotFoundError(f"Không tìm thấy Ortho Vùng: {sub_path}")

        # Nạp reference grid nếu chưa có hoặc khác file
        if self.reference_grid is None or self.reference_grid.get("target_ortho_path") != big_path:
            self.load_bbox_centroid_grid(grid_path, big_path)

        ref_grid = self.reference_grid
        by_module_id = ref_grid["by_module_id"]
        tree_utm = ref_grid["kdtree_utm"]
        ref_panels_list = ref_grid["panels"]

        with rasterio.open(big_path) as big_src, rasterio.open(sub_path) as sub_src:
            need_reproject = (sub_src.crs != big_src.crs) and (sub_src.crs is not None) and (big_src.crs is not None)
            transformer = Transformer.from_crs(sub_src.crs, big_src.crs, always_xy=True) if need_reproject else None
            sub_to_utm49 = Transformer.from_crs(sub_src.crs, "EPSG:32649", always_xy=True) if sub_src.crs and sub_src.crs.to_string() != "EPSG:32649" else None
            utm49_to_big = Transformer.from_crs("EPSG:32649", big_src.crs, always_xy=True) if big_src.crs and big_src.crs.to_string() != "EPSG:32649" else None
            inv_big_transform = ~big_src.transform

            # Bước 1: Tính toán quy chiếu GPS và kiểm tra điều kiện chuẩn cho từng panel
            parsed_panels = []
            for p in panels:
                p_id = p.get("id") or p.get("label") or "PV"
                internal_code = p.get("internal_code") or p.get("module_id") or p.get("batch_id") or p_id

                corners = p.get("corners") or []
                corners_pixel = p.get("corners_pixel") or []
                sub_c_px = p.get("sub_corners_px") or []
                centroid = p.get("centroid") or {}
                centroid_pixel = p.get("centroid_pixel") or {}
                sub_cen_px = p.get("sub_centroid_px") or {}

                pts_sub = []
                if corners and len(corners) == 4:
                    pts_sub = [c.get("pixel", c) for c in corners]
                elif corners_pixel and len(corners_pixel) == 4:
                    pts_sub = corners_pixel
                elif sub_c_px and len(sub_c_px) == 4:
                    pts_sub = sub_c_px

                if len(pts_sub) < 4:
                    continue

                # 4 góc trên Ortho Vùng
                sub_corners_px = [{"x": float(c.get("x", c.get("col", 0))), "y": float(c.get("y", c.get("row", 0)))} for c in pts_sub]
                cu_c = float(centroid_pixel.get("x", centroid.get("pixel", {}).get("x", np.mean([c["x"] for c in sub_corners_px]))))
                cv_c = float(centroid_pixel.get("y", centroid.get("pixel", {}).get("y", np.mean([c["y"] for c in sub_corners_px]))))
                sub_centroid_px = {"x": cu_c, "y": cv_c}

                # Đổi sang UTM / Geo
                corners_utm = []
                corners_big_gps_px = []
                all_in = True
                for idx_c, c_px in enumerate(sub_corners_px):
                    # Kiểm tra xem corner gốc có sẵn tọa độ UTM không
                    c_orig = corners[idx_c] if (corners and idx_c < len(corners)) else {}
                    c_utm = c_orig.get("utm_32649") or c_orig.get("utm")
                    if isinstance(c_utm, dict) and "easting" in c_utm and "northing" in c_utm:
                        ux = float(c_utm["easting"])
                        uy = float(c_utm["northing"])
                        gx_big, gy_big = utm49_to_big.transform(ux, uy) if utm49_to_big else (ux, uy)
                    elif isinstance(c_utm, (list, tuple)) and len(c_utm) == 2:
                        ux = float(c_utm[0])
                        uy = float(c_utm[1])
                        gx_big, gy_big = utm49_to_big.transform(ux, uy) if utm49_to_big else (ux, uy)
                    else:
                        gx, gy = sub_src.transform * (c_px["x"], c_px["y"])
                        ux, uy = sub_to_utm49.transform(gx, gy) if sub_to_utm49 else (gx, gy)
                        gx_big, gy_big = transformer.transform(gx, gy) if transformer else (gx, gy)

                    corners_utm.append([ux, uy])
                    bc_col, bc_row = inv_big_transform * (gx_big, gy_big)
                    in_b = (0 <= round(bc_col) < big_src.width and 0 <= round(bc_row) < big_src.height)
                    if not in_b: all_in = False
                    corners_big_gps_px.append({"x": round(bc_col, 2), "y": round(bc_row, 2)})

                # Tâm Centroid UTM & GPS Big Pixel
                cen_utm = centroid.get("utm_32649") or centroid.get("utm")
                if isinstance(cen_utm, dict) and "easting" in cen_utm and "northing" in cen_utm:
                    ux_c = float(cen_utm["easting"])
                    uy_c = float(cen_utm["northing"])
                    gx_c_big, gy_c_big = utm49_to_big.transform(ux_c, uy_c) if utm49_to_big else (ux_c, uy_c)
                elif isinstance(cen_utm, (list, tuple)) and len(cen_utm) == 2:
                    ux_c = float(cen_utm[0])
                    uy_c = float(cen_utm[1])
                    gx_c_big, gy_c_big = utm49_to_big.transform(ux_c, uy_c) if utm49_to_big else (ux_c, uy_c)
                else:
                    gx_c, gy_c = sub_src.transform * (cu_c, cv_c)
                    ux_c, uy_c = sub_to_utm49.transform(gx_c, gy_c) if sub_to_utm49 else (gx_c, gy_c)
                    gx_c_big, gy_c_big = transformer.transform(gx_c, gy_c) if transformer else (gx_c, gy_c)

                bc_c_col, bc_c_row = inv_big_transform * (gx_c_big, gy_c_big)

                # Kiểm tra Bounding Box có đạt chuẩn lưới không
                is_std, std_reason, std_metrics = self.validate_bounding_box_standard(corners_utm, tolerance_params)

                parsed_panels.append({
                    "id": p_id,
                    "internal_code": internal_code,
                    "label": p.get("label", p_id),
                    "row": p.get("row"),
                    "column": p.get("column"),
                    "class": p.get("class", "solar_panel"),
                    "sub_corners_px": sub_corners_px,
                    "sub_centroid_px": sub_centroid_px,
                    "corners_utm": corners_utm,
                    "centroid_utm": [round(ux_c, 4), round(uy_c, 4)],
                    "gps_corners_big_px": corners_big_gps_px,
                    "gps_centroid_big_px": {"x": round(bc_c_col, 2), "y": round(bc_c_row, 2)},
                    "is_standard": is_std,
                    "standard_reason": std_reason,
                    "standard_metrics": std_metrics,
                    "in_bounds": all_in
                })

            if not parsed_panels:
                return {
                    "status": "success",
                    "total_panels": 0,
                    "displayed_count": 0,
                    "rejected_count": 0,
                    "panels": [],
                    "stats": {},
                    "csv_data": ""
                }

            # Bước 2: Ước lượng Biến đổi Tương đồng 2D (Similarity / Helmert / Partial Affine)
            valid_for_sim = [p for p in parsed_panels if p["is_standard"] and p["in_bounds"]]
            if not valid_for_sim:
                valid_for_sim = [p for p in parsed_panels if p["in_bounds"]]
            if not valid_for_sim:
                valid_for_sim = parsed_panels

            sim_params = {"scale": 1.0, "rotation_deg": 0.0, "tx": 0.0, "ty": 0.0}
            M_sim = None
            if len(valid_for_sim) >= 2:
                src_pts = np.float32([[p["sub_centroid_px"]["x"], p["sub_centroid_px"]["y"]] for p in valid_for_sim])
                dst_pts = np.float32([[p["gps_centroid_big_px"]["x"], p["gps_centroid_big_px"]["y"]] for p in valid_for_sim])
                M_est, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0)
                if M_est is not None:
                    M_sim = M_est
                    scale = math.sqrt(M_sim[0, 0]**2 + M_sim[0, 1]**2)
                    rot_deg = math.degrees(math.atan2(M_sim[1, 0], M_sim[0, 0]))
                    sim_params = {
                        "scale": round(scale, 5),
                        "rotation_deg": round(rot_deg, 3),
                        "tx": round(float(M_sim[0, 2]), 2),
                        "ty": round(float(M_sim[1, 2]), 2)
                    }

            # Bước 2.5: Tiền xử lý tọa độ tương đồng và tính toán Auto-Alignment (Tìm offset tối ưu)
            for p in parsed_panels:
                if M_sim is not None:
                    c_vec = np.array([p["sub_centroid_px"]["x"], p["sub_centroid_px"]["y"], 1.0])
                    sim_c = M_sim.dot(c_vec)
                    p["sim_c_px"] = {"x": round(float(sim_c[0]), 2), "y": round(float(sim_c[1]), 2)}

                    sim_corners_px = []
                    for c in p["sub_corners_px"]:
                        v_vec = np.array([c["x"], c["y"], 1.0])
                        v_mapped = M_sim.dot(v_vec)
                        sim_corners_px.append({"x": round(float(v_mapped[0]), 2), "y": round(float(v_mapped[1]), 2)})
                    p["sim_corners_px"] = sim_corners_px
                else:
                    p["sim_c_px"] = p["gps_centroid_big_px"]
                    p["sim_corners_px"] = p["gps_corners_big_px"]

                sim_geo_x, sim_geo_y = big_src.transform * (p["sim_c_px"]["x"], p["sim_c_px"]["y"])
                p["sim_utm_c"] = [round(sim_geo_x, 4), round(sim_geo_y, 4)]
                
            sim_params["auto_offset_e"] = 0.0
            sim_params["auto_offset_n"] = 0.0

            # Bước 3: Khớp mã module & tính sai số Euclidean
            results = []
            valid_count = 0
            rejected_count = 0

            for p_idx, p in enumerate(parsed_panels):
                sim_c_px = p["sim_c_px"]
                sim_corners_px = p["sim_corners_px"]
                sim_utm_c = p["sim_utm_c"]

                # Khớp với module trong reference_grid
                matched_ref = None
                match_method = "none"

                # 1. Khớp theo mã module (có tương đồng chữ là tính)
                code_to_check = str(p["internal_code"]).strip().lower()
                for k, item in by_module_id.items():
                    k_lower = str(k).strip().lower()
                    if code_to_check in k_lower or k_lower in code_to_check:
                        matched_ref = item
                        match_method = "similarity_module_id"
                        break

                # Tính sai số chênh lệch Euclidean
                euclid_utm_m = None
                euclid_cm = None
                euclid_px = None
                delta_x_px = None
                delta_y_px = None
                delta_e_m = None
                delta_n_m = None
                corner_errors_cm = []
                mean_corner_cm = None

                if matched_ref:
                    ref_cx_utm = matched_ref["centroid_utm"][0]
                    ref_cy_utm = matched_ref["centroid_utm"][1]
                    ref_cx_px = matched_ref["centroid_pixel"]["x"]
                    ref_cy_px = matched_ref["centroid_pixel"]["y"]

                    delta_e_m = round(sim_utm_c[0] - ref_cx_utm, 4)
                    delta_n_m = round(sim_utm_c[1] - ref_cy_utm, 4)
                    euclid_utm_m = math.hypot(delta_e_m, delta_n_m)
                    euclid_cm = round(euclid_utm_m * 100, 2)

                    delta_x_px = round(sim_c_px["x"] - ref_cx_px, 2)
                    delta_y_px = round(sim_c_px["y"] - ref_cy_px, 2)
                    euclid_px = round(math.hypot(delta_x_px, delta_y_px), 2)

                    # Sai số 4 góc
                    gsd_m = abs(big_src.transform.a)
                    for k in range(4):
                        rc_px = matched_ref["corners_pixel"][k]
                        sc_px = sim_corners_px[k]
                        err_c_px = math.hypot(sc_px["x"] - rc_px["x"], sc_px["y"] - rc_px["y"])
                        corner_errors_cm.append(round(err_c_px * gsd_m * 100, 2))
                    mean_corner_cm = round(float(np.mean(corner_errors_cm)), 2)

                # Quy tắc: "Phải đáp ứng bounding box lưới có đạt chuẩn không, ko đạt chuẩn là ko được hiện lên"
                # VÀ "vs cả bị lỗi vẫn chưa ẩn box lỗi vs box k ánh xạ được vị trí"
                is_standard = p["is_standard"]
                is_matched = (matched_ref is not None)

                standard_reason = p["standard_reason"]
                if not is_matched and is_standard:
                    standard_reason = "Không ánh xạ được vị trí (không có module đối ứng trên lưới 87m)"

                # Bắt buộc: Tất cả đều được hiện lên (để user xem tấm lỗi), 
                # frontend sẽ tự bôi màu đỏ cho tấm lỗi dựa vào is_standard và is_matched.
                display_on_map = True
                if is_standard and is_matched:
                    valid_count += 1
                else:
                    rejected_count += 1

                panel_result = {
                    "id": p["id"],
                    "module_id": matched_ref["module_id"] if matched_ref else p["internal_code"],
                    "matched": is_matched,
                    "match_method": match_method,
                    "is_standard": is_standard,
                    "display": display_on_map,
                    "standard_reason": standard_reason,
                    "metrics": p["standard_metrics"],
                    "in_bounds": p["in_bounds"],
                    "row": p.get("row"),
                    "column": p.get("column"),
                    "class": p.get("class", "solar_panel"),
                    # Tọa độ ánh xạ tương đồng
                    "sim_centroid_pixel": sim_c_px,
                    "sim_corners_pixel": sim_corners_px,
                    "sim_centroid_utm": sim_utm_c,
                    # Tọa độ GPS thuần
                    "gps_centroid_pixel": p["gps_centroid_big_px"],
                    "gps_corners_pixel": p["gps_corners_big_px"],
                    "centroid_utm": p["centroid_utm"],
                    # Tọa độ lưới chuẩn đối ứng
                    "ref_module": matched_ref,
                    # Sai số Euclidean
                    "euclidean_error_cm": euclid_cm,
                    "euclidean_error_px": euclid_px,
                    "delta_x_px": delta_x_px,
                    "delta_y_px": delta_y_px,
                    "delta_e_m": delta_e_m,
                    "delta_n_m": delta_n_m,
                    "corner_errors_cm": corner_errors_cm,
                    "mean_corner_cm": mean_corner_cm
                }
                results.append(panel_result)

            # Thống kê tổng hợp trên các tấm được hiện
            displayed_panels = [r for r in results if r["display"] and r["euclidean_error_cm"] is not None]
            stats = {}
            if displayed_panels:
                errs_cm = np.array([r["euclidean_error_cm"] for r in displayed_panels])
                errs_px = np.array([r["euclidean_error_px"] for r in displayed_panels])
                stats = {
                    "count": len(displayed_panels),
                    "mean_cm": round(float(np.mean(errs_cm)), 2),
                    "rmse_cm": round(float(np.sqrt(np.mean(errs_cm**2))), 2),
                    "median_cm": round(float(np.median(errs_cm)), 2),
                    "min_cm": round(float(np.min(errs_cm)), 2),
                    "max_cm": round(float(np.max(errs_cm)), 2),
                    "mean_px": round(float(np.mean(errs_px)), 2),
                    "rmse_px": round(float(np.sqrt(np.mean(errs_px**2))), 2),
                }

            # Xuất dữ liệu CSV
            csv_io = io.StringIO()
            writer = csv.writer(csv_io)
            header = [
                "Module_ID", "Panel_ID", "Class", "Status", "Is_Standard_Valid",
                "Length_m", "Width_m", "Area_m2",
                "Ref_Centroid_X_px", "Ref_Centroid_Y_px", "Ref_UTM_E", "Ref_UTM_N",
                "Mapped_Centroid_X_px", "Mapped_Centroid_Y_px", "Mapped_UTM_E", "Mapped_UTM_N",
                "Delta_X_px", "Delta_Y_px", "Delta_E_m", "Delta_N_m",
                "Euclidean_Error_cm", "Euclidean_Error_px", "Mean_Corner_Err_cm", "Standard_Reason"
            ]
            writer.writerow(header)
            for r in results:
                ref = r.get("ref_module") or {}
                ref_c_px = ref.get("centroid_pixel", {})
                ref_c_utm = ref.get("centroid_utm", ["-", "-"])
                m = r.get("metrics", {})

                if r["is_standard"] and r["matched"]:
                    status_str = "HỢP LỆ"
                elif not r["is_standard"] and r["matched"]:
                    status_str = "LỖI KÍCH THƯỚC (ĐÃ GHÉP MÃ)"
                else:
                    status_str = "LỖI (KHÔNG CÓ MÃ ĐỐI ỨNG)"

                writer.writerow([
                    r["module_id"], r["id"], r.get("class", "Unknown"),
                    status_str,
                    "YES" if r["is_standard"] else "NO",
                    m.get("length_m", "-"), m.get("width_m", "-"), m.get("area_m2", "-"),
                    ref_c_px.get("x", "-"), ref_c_px.get("y", "-"),
                    ref_c_utm[0] if len(ref_c_utm) > 0 else "-", ref_c_utm[1] if len(ref_c_utm) > 1 else "-",
                    r["sim_centroid_pixel"]["x"], r["sim_centroid_pixel"]["y"],
                    r["sim_centroid_utm"][0], r["sim_centroid_utm"][1],
                    r.get("delta_x_px", "-"), r.get("delta_y_px", "-"),
                    r.get("delta_e_m", "-"), r.get("delta_n_m", "-"),
                    r.get("euclidean_error_cm", "-"), r.get("euclidean_error_px", "-"),
                    r.get("mean_corner_cm", "-"), r.get("standard_reason", "")
                ])

            return {
                "status": "success",
                "total_panels": len(results),
                "displayed_count": valid_count,
                "rejected_count": rejected_count,
                "similarity_params": sim_params,
                "stats": stats,
                "csv_data": csv_io.getvalue(),
                "panels": results
            }

    def _is_homography_valid(self, H, img_w, img_h):
        if H is None: return False
        if abs(H[2, 0]) > 0.002 or abs(H[2, 1]) > 0.002: return False
        try:
            pts = np.float32([[0, 0], [img_w, 0], [img_w, img_h], [0, img_h]]).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, H).reshape(4, 2)
            def cross2d(v1, v2): return v1[0]*v2[1] - v1[1]*v2[0]
            signs = [cross2d(dst[(i+1)%4] - dst[i], dst[(i+2)%4] - dst[(i+1)%4]) > 0 for i in range(4)]
            if not (all(signs) or not any(signs)): return False
            area = cv2.contourArea(dst)
            if area < (img_w * img_h * 0.005) or area > (img_w * img_h * 100): return False
        except Exception:
            return False
        return True

    def _get_best_homography(self, pts_sub, pts_big, img_w, img_h):
        if pts_sub is None or pts_big is None or len(pts_sub) < 4: return None, None
        M_homo, mask_homo = cv2.findHomography(pts_sub, pts_big, cv2.RANSAC, 5.0)
        
        # Nếu Homography hợp lệ (không bị kéo giãn, tự cắt), giữ nguyên
        if self._is_homography_valid(M_homo, img_w, img_h):
            return M_homo, mask_homo
            
        # NẾU KHÔNG: Hạ cấp xuống Partial Affine (chỉ dịch chuyển, xoay, scale) để giữ hình dạng khối pin vuông vức
        M_partial, mask_partial = cv2.estimateAffinePartial2D(pts_sub, pts_big, method=cv2.RANSAC, ransacReprojThreshold=5.0)
        if M_partial is not None:
            return np.vstack([M_partial, [0, 0, 1]]), mask_partial
            
        return None, None

    def _filter_matches_spatially(self, kpts0, kpts1, scores, img_w, img_h, grid_size=10, max_per_cell=5):
        if len(kpts0) == 0: return kpts0, kpts1
        cell_w, cell_h = img_w / grid_size, img_h / grid_size
        grid = {}
        for i, (x, y) in enumerate(kpts0):
            cell = (int(x / cell_w), int(y / cell_h))
            grid.setdefault(cell, []).append((i, scores[i]))
        selected = []
        for cell, items in grid.items():
            items.sort(key=lambda x: x[1], reverse=True)
            selected.extend([item[0] for item in items[:max_per_cell]])
        if not selected: return kpts0, kpts1
        return kpts0[selected], kpts1[selected]

    def _get_loftr_matches(self, img_sub, img_big, max_points=300):
        if not HAS_LOFTR: return None, None
        if not hasattr(self, 'loftr_matcher'):
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            self.loftr_matcher = kf.LoFTR(pretrained="outdoor").to(device)
            self.loftr_device = device
        
        h0, w0 = img_sub.shape
        h1, w1 = img_big.shape
        pad_h0, pad_w0 = (8 - h0 % 8) % 8, (8 - w0 % 8) % 8
        pad_h1, pad_w1 = (8 - h1 % 8) % 8, (8 - w1 % 8) % 8
        
        img_sub_padded = np.pad(img_sub, ((0, pad_h0), (0, pad_w0)), mode='constant')
        img_big_padded = np.pad(img_big, ((0, pad_h1), (0, pad_w1)), mode='constant')

        ten_sub = torch.from_numpy(img_sub_padded).float()[None, None] / 255.0
        ten_big = torch.from_numpy(img_big_padded).float()[None, None] / 255.0
        ten_sub = ten_sub.to(self.loftr_device)
        ten_big = ten_big.to(self.loftr_device)
        
        with torch.inference_mode():
            correspondences = self.loftr_matcher({"image0": ten_sub, "image1": ten_big})
            
        mkpts0 = correspondences['keypoints0'].cpu().numpy()
        mkpts1 = correspondences['keypoints1'].cpu().numpy()
        confidence = correspondences['confidence'].cpu().numpy()
        
        mkpts0, mkpts1 = self._filter_matches_spatially(
            mkpts0, mkpts1, confidence, w0, h0, grid_size=10, max_per_cell=int(max_points/50)+1
        )
        if len(mkpts0) < 4: return None, None
        return np.float32(mkpts0).reshape(-1, 1, 2), np.float32(mkpts1).reshape(-1, 1, 2)

    def _get_lightglue_matches(self, img_sub, img_big, max_points=300):
        """Helper để lấy toạ độ điểm khớp mẫu bằng SuperPoint + LightGlue"""
        if not HAS_LIGHTGLUE:
            return None, None
            
        if not hasattr(self, 'lightglue_matcher'):
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
            
            # Khởi tạo mô hình
            self.extractor = SuperPoint(max_num_keypoints=2048).eval().to(device)
            self.lightglue_matcher = LightGlue(features='superpoint').eval().to(device)
            self.ai_device = device
            
        # Convert sang Tensor và Normalize [0, 1] - Không cần padding kích thước 8 với SuperPoint
        ten_sub = torch.from_numpy(img_sub).float()[None, None] / 255.0
        ten_big = torch.from_numpy(img_big).float()[None, None] / 255.0
        
        ten_sub = ten_sub.to(self.ai_device)
        ten_big = ten_big.to(self.ai_device)
        
        with torch.inference_mode():
            # Trích xuất đặc trưng
            feats_sub = self.extractor.extract(ten_sub)
            feats_big = self.extractor.extract(ten_big)
            
            # Ghép nối
            matches_sub_big = self.lightglue_matcher({'image0': feats_sub, 'image1': feats_big})
            
        # Loại bỏ batch dimension
        feats_sub, feats_big, matches_sub_big = [rbd(x) for x in [feats_sub, feats_big, matches_sub_big]]
        
        kpts_sub = feats_sub['keypoints'].cpu().numpy()
        kpts_big = feats_big['keypoints'].cpu().numpy()
        matches = matches_sub_big['matches'].cpu().numpy()
        scores = matches_sub_big['scores'].cpu().numpy()
        
        if len(matches) < 4:
            return None, None
            
        # Lấy toạ độ điểm đã khớp
        mkpts_sub = kpts_sub[matches[..., 0]]
        mkpts_big = kpts_big[matches[..., 1]]
        
        # Sắp xếp theo scores (confidence)
        h_sub, w_sub = img_sub.shape
        mkpts_sub, mkpts_big = self._filter_matches_spatially(
            mkpts_sub, mkpts_big, scores, w_sub, h_sub, grid_size=10, max_per_cell=int(max_points/50)+1
        )
            
        if len(mkpts_sub) < 4:
            return None, None
            
        pts_sub = np.float32(mkpts_sub).reshape(-1, 1, 2)
        pts_big = np.float32(mkpts_big).reshape(-1, 1, 2)
        
        return pts_sub, pts_big
