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

class OrthoProcessor:
    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "ortho_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.loaded_orthos = {}

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

            img.save(out_path, format="JPEG", quality=88)
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
                    pixel_polygon.append({"col": round(col, 2), "row": round(row, 2)})

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

            # ORB Feature matching
            orb = cv2.ORB_create(nfeatures=2000)
            kp1, des1 = orb.detectAndCompute(img_big, None)
            kp2, des2 = orb.detectAndCompute(img_sub, None)

            if des1 is not None and des2 is not None:
                bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                matches = bf.match(des1, des2)
                matches = sorted(matches, key=lambda x: x.distance)[:100]

                if len(matches) >= 4:
                    src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
                    dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
                    M, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)

                    if M is not None:
                        h_sub, w_sub = img_sub.shape
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
                        return pixel_box, norm_box, yolo, 100.0, "cv_feature_matching"

            # Fallback nếu không khớp được
            default_box = {"xmin": 0, "ymin": 0, "xmax": big_src.width, "ymax": big_src.height, "width": big_src.width, "height": big_src.height, "center_x": big_src.width // 2, "center_y": big_src.height // 2}
            default_norm = {"xmin": 0.0, "ymin": 0.0, "xmax": 1.0, "ymax": 1.0, "width": 1.0, "height": 1.0, "center_x": 0.5, "center_y": 0.5}
            return default_box, default_norm, "0 0.500000 0.500000 1.000000 1.000000", 0.0, "fallback"

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
