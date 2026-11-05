import os
import glob
import json
import tempfile
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
import cv2
import numpy as np
import csv
import io
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ortho_processor import OrthoProcessor

app = FastAPI(title="OrthoScope Bounding Box Web", version="1.0.0")

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware vô hiệu hóa cache cho JS/CSS/HTML để trình duyệt luôn nạp mã nguồn mới nhất
@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

processor = OrthoProcessor()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class PathLoadRequest(BaseModel):
    file_path: str

class MatchRequest(BaseModel):
    big_path: str
    sub_path: str

@app.get("/api/quick-files")
def get_quick_files():
    """Tự động tìm kiếm các file GeoTIFF/ortho có sẵn trong máy để người dùng chọn nhanh"""
    found_files = []
    search_dirs = [
        os.path.dirname(__file__),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        os.path.expanduser(r"~\Downloads\Kho làm việc riêng"),
    ]
    
    seen = set()
    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            for ext in ["*.tif", "*.tiff", "*.TIF", "*.TIFF"]:
                for p in glob.glob(os.path.join(s_dir, "**", ext), recursive=True):
                    norm = os.path.abspath(p)
                    if norm not in seen and os.path.isfile(norm):
                        seen.add(norm)
                        try:
                            sz_mb = round(os.path.getsize(norm) / (1024 * 1024), 2)
                            found_files.append({
                                "path": norm,
                                "name": os.path.basename(norm),
                                "size_mb": sz_mb,
                                "dir": os.path.basename(os.path.dirname(norm)),
                            })
                        except Exception:
                            pass

    # Sắp xếp file theo dung lượng hoặc tên
    found_files.sort(key=lambda x: x["size_mb"], reverse=True)
    return {"files": found_files[:20]}

def save_upload_file(upload_file: UploadFile, dest_dir: str) -> str:
    import time
    safe_filename = "".join(c for c in upload_file.filename if c.isalnum() or c in " ._-").strip()
    if not safe_filename:
        safe_filename = "upload_ortho.tif"
    
    target_path = os.path.join(dest_dir, safe_filename)
    
    # Dọn dẹp ổ cứng: xóa file trong uploads cũ hơn 2 giờ
    now = time.time()
    for fname in os.listdir(dest_dir):
        fpath = os.path.join(dest_dir, fname)
        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 7200:
            try:
                os.remove(fpath)
            except Exception:
                pass

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return target_path
    except OSError:
        # Nếu file bị khóa bởi GDAL/Rasterio trên Windows, dùng tên mới
        unique_filename = f"{int(time.time())}_{safe_filename}"
        target_path = os.path.join(dest_dir, unique_filename)
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return target_path

@app.post("/api/load-ortho")
async def load_ortho(
    file_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """Nạp file Orthophoto lớn từ đường dẫn hoặc upload"""
    target_path = None
    if file_path and file_path.strip():
        target_path = os.path.normpath(file_path.strip().strip('"').strip("'"))
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy file: {target_path}")
    elif file:
        target_path = save_upload_file(file, UPLOAD_DIR)
    else:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp file_path hoặc tải file lên")

    try:
        info = processor.get_info(target_path)
        preview_path = processor.generate_preview(target_path, max_size=3072)
        info["preview_filename"] = os.path.basename(preview_path)
        return {"status": "success", "data": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi phân tích Ortho: {str(e)}")

@app.post("/api/match-region")
async def match_region(
    big_path: str = Form(...),
    sub_path: Optional[str] = Form(None),
    sub_file: Optional[UploadFile] = File(None)
):
    """Xác định Bounding Box của Ortho vùng trên Ortho lớn"""
    big_target = os.path.normpath(big_path.strip().strip('"').strip("'"))
    if not os.path.exists(big_target):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file Ortho lớn: {big_target}")

    sub_target = None
    if sub_path and sub_path.strip():
        sub_target = os.path.normpath(sub_path.strip().strip('"').strip("'"))
        if not os.path.exists(sub_target):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy file Ortho vùng: {sub_target}")
    elif sub_file:
        sub_target = save_upload_file(sub_file, UPLOAD_DIR)
    else:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp sub_path hoặc upload file Ortho vùng")

    try:
        result = processor.calculate_bounding_box(big_target, sub_target)
        # Sinh preview cho cả 2
        big_prev = processor.generate_preview(big_target, max_size=3072)
        sub_prev = processor.generate_preview(sub_target, max_size=3072)
        result["big_ortho"]["preview_filename"] = os.path.basename(big_prev)
        result["sub_ortho"]["preview_filename"] = os.path.basename(sub_prev)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tính toán Bounding Box: {str(e)}")

@app.post("/api/match-two-subs")
async def match_two_subs(
    sub1_path: Optional[str] = Form(None),
    sub1_file: Optional[UploadFile] = File(None),
    sub2_path: Optional[str] = Form(None),
    sub2_file: Optional[UploadFile] = File(None),
):
    """So sánh và xác định vị trí tương quan giữa 2 ảnh Ortho vùng"""
    def resolve_target(path_val, file_val, label):
        if path_val and path_val.strip():
            p = os.path.normpath(path_val.strip().strip('"').strip("'"))
            if not os.path.exists(p):
                raise HTTPException(status_code=404, detail=f"Không tìm thấy file {label}: {p}")
            return p
        elif file_val:
            dest = os.path.join(UPLOAD_DIR, file_val.filename)
            with open(dest, "wb") as buffer:
                shutil.copyfileobj(file_val.file, buffer)
            return dest
        else:
            raise HTTPException(status_code=400, detail=f"Vui lòng cung cấp file hoặc đường dẫn cho {label}")

    s1_target = resolve_target(sub1_path, sub1_file, "Ortho Vùng 1")
    s2_target = resolve_target(sub2_path, sub2_file, "Ortho Vùng 2")

    try:
        result = processor.calculate_two_sub_orthos(s1_target, s2_target)
        s1_prev = processor.generate_preview(s1_target, max_size=3072)
        s2_prev = processor.generate_preview(s2_target, max_size=3072)
        result["sub1_ortho"]["preview_filename"] = os.path.basename(s1_prev)
        result["sub2_ortho"]["preview_filename"] = os.path.basename(s2_prev)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi so sánh 2 Ortho vùng: {str(e)}")

@app.post("/api/match-two-subs-on-big")
async def match_two_subs_on_big(
    big_path: str = Form(...),
    sub1_path: Optional[str] = Form(None),
    sub1_file: Optional[UploadFile] = File(None),
    sub2_path: Optional[str] = Form(None),
    sub2_file: Optional[UploadFile] = File(None),
):
    """Xác định đồng thời vị trí của cả 2 Ortho vùng trên Ortho lớn"""
    big_target = os.path.normpath(big_path.strip().strip('"').strip("'"))
    if not os.path.exists(big_target):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file Ortho lớn: {big_target}")

    def resolve_target(path_val, file_val, label):
        if path_val and path_val.strip():
            p = os.path.normpath(path_val.strip().strip('"').strip("'"))
            if not os.path.exists(p):
                raise HTTPException(status_code=404, detail=f"Không tìm thấy file {label}: {p}")
            return p
        elif file_val:
            return save_upload_file(file_val, UPLOAD_DIR)
        else:
            raise HTTPException(status_code=400, detail=f"Vui lòng cung cấp file hoặc đường dẫn cho {label}")

    s1_target = resolve_target(sub1_path, sub1_file, "Ortho Vùng 1")
    s2_target = resolve_target(sub2_path, sub2_file, "Ortho Vùng 2")

    try:
        result = processor.calculate_two_subs_on_big(big_target, s1_target, s2_target)
        big_prev = processor.generate_preview(big_target, max_size=3072)
        s1_prev = processor.generate_preview(s1_target, max_size=3072)
        s2_prev = processor.generate_preview(s2_target, max_size=3072)
        result["big_ortho"]["preview_filename"] = os.path.basename(big_prev)
        result["sub1_ortho"]["preview_filename"] = os.path.basename(s1_prev)
        result["sub2_ortho"]["preview_filename"] = os.path.basename(s2_prev)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xác định 2 Ortho trên Ortho lớn: {str(e)}")

@app.get("/api/preview-image")
def get_preview_image(filename: str = Query(...)):
    """Trả về file ảnh preview JPEG từ thư mục tạm"""
    p = os.path.join(processor.cache_dir, filename)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Ảnh preview không tồn tại")
    return FileResponse(p, media_type="image/jpeg")

@app.get("/api/viewport-crop")
def get_viewport_crop(
    file_path: str = Query(...),
    col_off: int = Query(...),
    row_off: int = Query(...),
    width: int = Query(...),
    height: int = Query(...),
    max_dim: int = Query(2560)
):
    """Trả về ảnh độ nét cao của vùng viewport hiện tại khi người dùng phóng to"""
    clean_path = os.path.normpath(file_path.strip().strip('"').strip("'"))
    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail="File không tồn tại")
    try:
        crop_file = processor.get_viewport_crop(clean_path, col_off, row_off, width, height, max_dim)
        return FileResponse(crop_file, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi cắt HD viewport: {str(e)}")

@app.get("/api/crop-download")
def crop_download(
    big_path: str = Query(...),
    xmin: int = Query(...),
    ymin: int = Query(...),
    width: int = Query(...),
    height: int = Query(...),
    format: str = Query("GTiff")
):
    """Cắt trích xuất vùng Bounding Box từ Ortho to và cho phép người dùng tải về"""
    clean_path = big_path.strip().strip('"').strip("'")
    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail="File Ortho to không tồn tại")

    pixel_box = {
        "xmin": xmin,
        "ymin": ymin,
        "width": width,
        "height": height
    }
    try:
        out_file = processor.crop_bounding_box(clean_path, pixel_box, output_format=format)
        ext = ".tif" if format.lower() in ["tif", "tiff", "gtiff"] else ".png"
        filename = f"crop_region_{width}x{height}{ext}"
        media_type = "image/tiff" if ext == ".tif" else "image/png"
        return FileResponse(out_file, media_type=media_type, filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi cắt ảnh: {str(e)}")

class ReadUTMPixelsRequest(BaseModel):
    file_path: str
    points: list

DEFAULT_CANONICAL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "1008-core-ban-thu", "ket_qua", "pv_module_reference_canonical.json")
)
if not os.path.exists(DEFAULT_CANONICAL_PATH):
    alt_paths = [
        r"C:\Users\minhk\Downloads\Kho làm việc riêng\1008-core-ban-thu\ket_qua\pv_module_reference_canonical.json",
        r"C:\Users\minhk\Downloads\Kho làm việc riêng\Định vị trực giao\Kết quả\PP3\pv_module_reference_canonical.json",
        os.path.join(os.path.dirname(__file__), "pv_module_reference_canonical.json"),
    ]
    for ap in alt_paths:
        if os.path.exists(ap):
            DEFAULT_CANONICAL_PATH = ap
            break

class CalcCanonicalRequest(BaseModel):
    file_path: Optional[str] = None
    target_ortho_path: str
    mode: Optional[str] = "centroid"  # "centroid" hoặc "all"
    only_in_bounds: Optional[bool] = False
    filter_standard: Optional[bool] = True

@app.get("/api/canonical-info")
def get_canonical_info():
    """Kiểm tra và trả về thông tin file canonical JSON mặc định"""
    exists = os.path.exists(DEFAULT_CANONICAL_PATH)
    total_panels = 0
    size_mb = 0
    if exists:
        try:
            size_mb = round(os.path.getsize(DEFAULT_CANONICAL_PATH) / (1024 * 1024), 2)
            with open(DEFAULT_CANONICAL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                total_panels = len(data) if isinstance(data, list) else len(data.get("panels", []))
        except Exception:
            pass
    return {
        "exists": exists,
        "default_path": DEFAULT_CANONICAL_PATH,
        "total_panels": total_panels,
        "size_mb": size_mb,
        "filename": os.path.basename(DEFAULT_CANONICAL_PATH)
    }

@app.post("/api/calc-canonical-coords")
async def calc_canonical_coords_endpoint(payload: CalcCanonicalRequest):
    """Tính toán trực tiếp tọa độ pixel của các module PV trong canonical JSON trên ảnh GeoTIFF chỉ định"""
    canonical_file = payload.file_path.strip().strip('"').strip("'") if payload.file_path and payload.file_path.strip() else DEFAULT_CANONICAL_PATH
    if not os.path.exists(canonical_file):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file Canonical JSON: {canonical_file}")

    target_ortho = os.path.normpath(payload.target_ortho_path.strip().strip('"').strip("'"))
    if not os.path.exists(target_ortho):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file ảnh GeoTIFF mục tiêu: {target_ortho}")

    try:
        res = processor.process_canonical_json(
            file_path_or_data=canonical_file,
            target_ortho_path=target_ortho,
            mode=payload.mode or "centroid",
            only_in_bounds=bool(payload.only_in_bounds),
            filter_standard=bool(payload.filter_standard)
        )
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tính tọa độ từ Canonical JSON: {str(e)}")

@app.get("/api/canonical-panels-for-annotator")
def get_canonical_panels_for_annotator_endpoint(
    target_ortho_path: Optional[str] = Query(None),
    only_in_bounds: bool = Query(False),
    file_path: Optional[str] = Query(None)
):
    """Lấy danh sách các tấm PV từ canonical JSON để nạp vào PV Annotator (Tab 1)"""
    canonical_file = file_path.strip().strip('"').strip("'") if file_path and file_path.strip() else DEFAULT_CANONICAL_PATH
    if not os.path.exists(canonical_file):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file Canonical JSON: {canonical_file}")

    target_ortho = None
    if target_ortho_path and target_ortho_path.strip():
        target_ortho = os.path.normpath(target_ortho_path.strip().strip('"').strip("'"))

    try:
        panels = processor.get_canonical_panels_for_annotator(
            file_path=canonical_file,
            target_ortho_path=target_ortho,
            only_in_bounds=only_in_bounds
        )
        return {"status": "success", "total": len(panels), "panels": panels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đọc tấm PV Canonical: {str(e)}")

@app.post("/api/read-pixels-from-utm")
async def read_pixels_from_utm_endpoint(payload: ReadUTMPixelsRequest):
    """Đọc trực tiếp tọa độ điểm ảnh pixel từ file GeoTIFF bằng rasterio src.index(X, Y)"""
    clean_path = os.path.normpath(payload.file_path.strip().strip('"').strip("'"))
    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail=f"File GeoTIFF không tồn tại: {clean_path}")

    try:
        results = processor.read_pixels_from_utm(clean_path, payload.points)
        return {"status": "success", "points": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đọc file GeoTIFF: {str(e)}")

class PointMappingRequest(BaseModel):
    sub_width: float
    sub_height: float
    pixel_polygon: list
    points: list

@app.post("/api/transform-points")
async def transform_points_endpoint(payload: PointMappingRequest):
    try:
        if len(payload.pixel_polygon) != 4:
            raise ValueError("pixel_polygon must contain exactly 4 corners")

        w, h = payload.sub_width, payload.sub_height
        src_pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst_pts = np.float32([[p["col"], p["row"]] for p in payload.pixel_polygon])

        # Tính toán ma trận
        M_affine, _ = cv2.estimateAffine2D(src_pts, dst_pts)
        M_homo, _ = cv2.findHomography(src_pts, dst_pts)

        csv_affine_io = io.StringIO()
        csv_homo_io = io.StringIO()
        writer_affine = csv.writer(csv_affine_io)
        writer_homo = csv.writer(csv_homo_io)
        
        header = ["Point Name", "Original U (px)", "Original V (px)", "Mapped X (px)", "Mapped Y (px)"]
        writer_affine.writerow(header)
        writer_homo.writerow(header)

        mapped_affine_list = []
        mapped_homo_list = []

        for pt in payload.points:
            u, v = pt.get("u", 0), pt.get("v", 0)
            name = pt.get("name", "")
            pt_vec = np.array([u, v, 1.0])
            
            # Affine
            mapped_affine = M_affine.dot(pt_vec)
            x_affine, y_affine = round(mapped_affine[0], 2), round(mapped_affine[1], 2)
            writer_affine.writerow([name, round(u, 2), round(v, 2), x_affine, y_affine])
            mapped_affine_list.append({"name": name, "x": x_affine, "y": y_affine})

            # Homography
            if M_homo is not None:
                homo_vec = M_homo.dot(pt_vec)
                x_homo, y_homo = round(homo_vec[0]/homo_vec[2], 2), round(homo_vec[1]/homo_vec[2], 2)
            else:
                x_homo, y_homo = 0, 0
            writer_homo.writerow([name, round(u, 2), round(v, 2), x_homo, y_homo])
            mapped_homo_list.append({"name": name, "x": x_homo, "y": y_homo})

        return {
            "csv_affine": csv_affine_io.getvalue(),
            "csv_homography": csv_homo_io.getvalue(),
            "mapped_affine": mapped_affine_list,
            "mapped_homography": mapped_homo_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/transform-points-cv")
async def transform_points_cv_endpoint(
    big_path: str = Form(...),
    sub_path: str = Form(...),
    csv_file: UploadFile = File(...)
):
    try:
        content = await csv_file.read()
        csv_text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(csv_text))
        
        points = []
        for row in reader:
            # Lấy tên và tọa độ từ các cột của file xuất UTM
            name = row.get("Point_Name", row.get("Point Name", "Point"))
            
            # Cố gắng tìm cột U, V
            u_str = row.get("Pixel_U", row.get("Original U (px)", "0"))
            v_str = row.get("Pixel_V", row.get("Original V (px)", "0"))
            
            try:
                u = float(u_str)
                v = float(v_str)
            except ValueError:
                continue
                
            points.append({"name": name, "u": u, "v": v})

        if not points:
            raise ValueError("Không tìm thấy dữ liệu tọa độ hợp lệ trong file CSV.")

        # Gọi hàm xử lý AI
        results = processor.transform_points_by_cv(big_path, sub_path, points)
        
        # Ghi kết quả ra CSV
        csv_affine_io = io.StringIO()
        csv_homo_io = io.StringIO()
        writer_affine = csv.writer(csv_affine_io)
        writer_homo = csv.writer(csv_homo_io)
        
        header = ["Point Name", "Original U (px)", "Original V (px)", "Mapped X (px)", "Mapped Y (px)"]
        writer_affine.writerow(header)
        writer_homo.writerow(header)
        
        for pt in results["affine"]:
            writer_affine.writerow([pt["name"], pt["u"], pt["v"], pt["x"], pt["y"]])
            
        for pt in results["homography"]:
            writer_homo.writerow([pt["name"], pt["u"], pt["v"], pt["x"], pt["y"]])

        return {
            "csv_affine": csv_affine_io.getvalue(),
            "csv_homography": csv_homo_io.getvalue(),
            "mapped_affine": results["affine"],
            "mapped_homography": results["homography"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MapPanelsGPSRequest(BaseModel):
    big_path: str
    sub_path: str
    panels: list

@app.post("/api/map-panels-by-gps")
async def map_panels_by_gps_endpoint(req: MapPanelsGPSRequest):
    """Ánh xạ danh sách các tấm PV từ Ortho Vùng lên Ortho To bằng GPS thuần (Georeferencing)"""
    try:
        big_path = os.path.normpath(req.big_path.strip().strip('"').strip("'"))
        sub_path = os.path.normpath(req.sub_path.strip().strip('"').strip("'"))
        if not os.path.exists(big_path):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Ortho To: {big_path}")
        if not os.path.exists(sub_path):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Ortho Vùng: {sub_path}")
        
        mapped_panels = processor.map_panels_by_gps(big_path, sub_path, req.panels)
        return {
            "status": "success",
            "total": len(mapped_panels),
            "panels": mapped_panels
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

DEFAULT_GRID_JSON_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "bbox_centroid_export.json")
)
DEFAULT_GRID_CSV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "bbox_centroid_export.csv")
)

class LoadGridRequest(BaseModel):
    file_path: Optional[str] = None
    target_ortho_path: str

@app.get("/api/grid-info")
def get_grid_info(file_path: Optional[str] = Query(None)):
    """Kiểm tra và trả về thông tin file lưới toàn cảnh bbox_centroid_export.json / .csv"""
    p = file_path if file_path and file_path.strip() else DEFAULT_GRID_JSON_PATH
    info = processor.get_reference_grid_info(p)
    return {"status": "success", "data": info}

@app.post("/api/load-ortho-grid")
async def load_ortho_grid_endpoint(payload: LoadGridRequest):
    """Nạp file bbox_centroid_export.json hoặc .csv vào Ortho toàn cảnh (87m)"""
    target_ortho = os.path.normpath(payload.target_ortho_path.strip().strip('"').strip("'"))
    if not os.path.exists(target_ortho):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file Ortho To: {target_ortho}")

    grid_file = payload.file_path.strip().strip('"').strip("'") if payload.file_path and payload.file_path.strip() else DEFAULT_GRID_JSON_PATH
    if not os.path.exists(grid_file):
        if os.path.exists(DEFAULT_GRID_CSV_PATH):
            grid_file = DEFAULT_GRID_CSV_PATH
        else:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy file lưới module: {grid_file}")

    try:
        res = processor.load_bbox_centroid_grid(grid_file, target_ortho)
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi nạp lưới module toàn cảnh: {str(e)}")

@app.get("/api/grid-modules-viewport")
def get_grid_modules_viewport_endpoint(
    min_col: Optional[float] = Query(None),
    min_row: Optional[float] = Query(None),
    max_col: Optional[float] = Query(None),
    max_row: Optional[float] = Query(None),
    limit: Optional[int] = Query(3000),
    target_ortho: Optional[str] = Query(None)
):
    """
    Lấy danh sách các module lưới 87m nằm trong khung nhìn viewport pixel hiện tại
    để hiển thị trực quan và mượt mà trên bản đồ.
    """
    try:
        if processor.reference_grid is None:
            if target_ortho and os.path.exists(target_ortho):
                grid_f = DEFAULT_GRID_JSON_PATH if os.path.exists(DEFAULT_GRID_JSON_PATH) else DEFAULT_GRID_CSV_PATH
                processor.load_bbox_centroid_grid(grid_f, target_ortho)
        
        return processor.get_reference_grid_viewport(min_col, min_row, max_col, max_row, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy danh sách module viewport: {str(e)}")

class MapSimilarityRequest(BaseModel):
    big_path: str
    sub_path: str
    panels: list
    grid_path: Optional[str] = None
    filter_standard: Optional[bool] = True
    tolerance_params: Optional[dict] = None
    matching_mode: Optional[str] = "auto"

@app.post("/api/map-panels-similarity")
async def map_panels_similarity_endpoint(req: MapSimilarityRequest):
    """
    Ánh xạ tương đồng qua cả GPS lẫn pixel, đối chiếu mã module với bbox_centroid_export (87m),
    kiểm tra tiêu chuẩn bounding box lưới (không đạt chuẩn thì không hiện lên),
    và tính toán sai số chênh lệch khoảng cách Euclidean.
    """
    try:
        big_path = os.path.normpath(req.big_path.strip().strip('"').strip("'"))
        raw_sub = req.sub_path.strip().strip('"').strip("'") if req.sub_path else ""
        if raw_sub and os.path.exists(raw_sub):
            sub_path = os.path.normpath(raw_sub)
        else:
            sub_path = big_path

        if not os.path.exists(big_path):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Ortho To: {big_path}")

        grid_file = req.grid_path.strip().strip('"').strip("'") if req.grid_path and req.grid_path.strip() else DEFAULT_GRID_JSON_PATH
        if not os.path.exists(grid_file) and os.path.exists(DEFAULT_GRID_CSV_PATH):
            grid_file = DEFAULT_GRID_CSV_PATH

        result = processor.map_panels_similarity_and_match(
            big_path=big_path,
            sub_path=sub_path,
            panels=req.panels,
            grid_path=grid_file,
            filter_standard=bool(req.filter_standard),
            tolerance_params=req.tolerance_params,
            matching_mode=req.matching_mode or "auto"
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi ánh xạ tương đồng và tính sai số Euclidean: {str(e)}")

class MapPointsGPSRequest(BaseModel):
    big_path: str
    sub_path: str
    points: list

@app.post("/api/map-points-by-gps")
async def map_points_by_gps_endpoint(req: MapPointsGPSRequest):
    """Ánh xạ danh sách điểm từ Ortho Vùng lên Ortho To bằng GPS thuần"""
    try:
        big_path = os.path.normpath(req.big_path.strip().strip('"').strip("'"))
        sub_path = os.path.normpath(req.sub_path.strip().strip('"').strip("'"))
        if not os.path.exists(big_path):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Ortho To: {big_path}")
        if not os.path.exists(sub_path):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Ortho Vùng: {sub_path}")
        
        results = processor.map_points_by_gps(big_path, sub_path, req.points)
        
        csv_out = io.StringIO()
        csv_writer = csv.writer(csv_out)
        header = ["Point Name", "Sub U (px)", "Sub V (px)", "Big X (px)", "Big Y (px)", "UTM Easting (m)", "UTM Northing (m)", "Longitude", "Latitude", "In Bounds"]
        csv_writer.writerow(header)
        for pt in results:
            csv_writer.writerow([
                pt["name"], pt["sub_u"], pt["sub_v"], pt["big_x"], pt["big_y"],
                pt["utm_x"], pt["utm_y"], pt["lon"], pt["lat"],
                "YES" if pt["in_bounds"] else "NO"
            ])
            
        return {
            "status": "success",
            "total": len(results),
            "csv_data": csv_out.getvalue(),
            "points": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/map-points-by-gps-csv")
async def map_points_by_gps_csv_endpoint(
    big_path: str = Form(...),
    sub_path: str = Form(...),
    csv_file: UploadFile = File(...)
):
    """Ánh xạ điểm từ file CSV tải lên giữa Ortho Vùng và Ortho To bằng GPS thuần"""
    try:
        content = await csv_file.read()
        csv_text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(csv_text))
        points = []
        for row in reader:
            name = row.get("Point_Name", row.get("Point Name", row.get("name", "Point")))
            u_str = row.get("Pixel_U", row.get("Original U (px)", row.get("u", row.get("sub_u", "0"))))
            v_str = row.get("Pixel_V", row.get("Original V (px)", row.get("v", row.get("sub_v", "0"))))
            try:
                u = float(u_str)
                v = float(v_str)
            except ValueError:
                continue
            points.append({
                "name": name, 
                "u": u, 
                "v": v,
                "role": row.get("Role", row.get("role", "point")),
                "internal_code": row.get("Internal_Code", row.get("internal_code", name)),
                "class": row.get("Class", row.get("class", "Unclassified"))
            })
        if not points:
            raise ValueError("Không tìm thấy dữ liệu tọa độ hợp lệ trong file CSV.")
        
        big_path_clean = os.path.normpath(big_path.strip().strip('"').strip("'"))
        sub_path_clean = os.path.normpath(sub_path.strip().strip('"').strip("'"))
        results = processor.map_points_by_gps(big_path_clean, sub_path_clean, points)
        
        csv_out = io.StringIO()
        csv_writer = csv.writer(csv_out)
        header = ["Point Name", "Sub U (px)", "Sub V (px)", "Big X (px)", "Big Y (px)", "UTM Easting (m)", "UTM Northing (m)", "Longitude", "Latitude", "In Bounds", "Internal Code"]
        csv_writer.writerow(header)
        for pt in results:
            csv_writer.writerow([
                pt["name"], pt["sub_u"], pt["sub_v"], pt["big_x"], pt["big_y"],
                pt["utm_x"], pt["utm_y"], pt["lon"], pt["lat"],
                "YES" if pt["in_bounds"] else "NO", pt.get("internal_code", "")
            ])
            
        return {
            "status": "success",
            "total": len(results),
            "csv_data": csv_out.getvalue(),
            "points": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/batch-map-csv-to-canvas")
async def batch_map_csv_to_canvas_endpoint():
    """Thực thi chuyển đổi đồng loạt OBB từ CSV detection 35m lên Canvas map 85m và đối soát giàn pin"""
    try:
        from transform_batch_canvas import execute_batch_mapping
        df_out, panels_canvas, stats = execute_batch_mapping()
        return {
            "status": "success",
            "stats": stats,
            "total": len(panels_canvas),
            "panels": panels_canvas,
            "csv_file": "Bounding Box/PV_Batch_Transformed_Canvas_85m.csv"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi chuyển đổi đồng loạt lên Canvas: {str(e)}")

@app.post("/api/map-affine-points-csv")
async def map_affine_points_csv_endpoint(
    csv_file: Optional[UploadFile] = File(None)
):
    """Ánh xạ ma trận Affine 6 DOF từ CSV detection 35m lên Ortho To 85m"""
    try:
        from transform_batch_canvas import execute_batch_mapping
        import tempfile
        
        src_path = 'PV_Coordinates_Ortho_Vung_1_20260929_0018.csv'
        temp_path = None
        if csv_file is not None:
            content = await csv_file.read()
            if content and len(content) > 10:
                temp_f = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
                temp_f.write(content)
                temp_f.close()
                src_path = temp_f.name
                temp_path = temp_f.name

        df_out, panels_canvas, stats = execute_batch_mapping(src_csv_path=src_path)
        
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
            
        csv_buffer = io.StringIO()
        df_out.to_csv(csv_buffer, index=False, encoding='utf-8-sig')

        return {
            "status": "success",
            "total": len(panels_canvas),
            "stats": stats,
            "csv_data": csv_buffer.getvalue(),
            "panels": panels_canvas,
            "csv_file": "Bounding Box/PV_Batch_Transformed_Canvas_85m.csv"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi ánh xạ ma trận Affine: {str(e)}")

@app.post("/api/map-homography-points-csv")
async def map_homography_points_csv_endpoint(
    csv_file: Optional[UploadFile] = File(None)
):
    """Ánh xạ ma trận Homography 3x3 (8 DOF, DLT + Chuẩn hóa Hartley + RANSAC) từ CSV detection 35m lên Ortho To 85m"""
    try:
        from transform_obb_homography_corners import execute_homography_batch_mapping
        import tempfile

        src_path = 'PV_Coordinates_Ortho_Vung_1_20260929_0018.csv'
        temp_path = None
        if csv_file is not None:
            content = await csv_file.read()
            if content and len(content) > 10:
                temp_f = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
                temp_f.write(content)
                temp_f.close()
                src_path = temp_f.name
                temp_path = temp_f.name

        df_out, panels_canvas, stats = execute_homography_batch_mapping(src_csv_path=src_path)

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        csv_buffer = io.StringIO()
        df_out.to_csv(csv_buffer, index=False, encoding='utf-8-sig')

        return {
            "status": "success",
            "total": len(panels_canvas),
            "stats": stats,
            "csv_data": csv_buffer.getvalue(),
            "panels": panels_canvas,
            "csv_file": "Bounding Box/PV_Transformed_OBB_Homography_85m.csv"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi ánh xạ ma trận Homography: {str(e)}")

@app.post("/api/compare-affine-homography-visual")
async def compare_affine_homography_visual_endpoint(
    csv_file: Optional[UploadFile] = File(None)
):
    """Đối chiếu trực quan và định lượng trên cùng nền Ortho 85m giữa Affine (6 DOF) và Homography (8 DOF)"""
    try:
        from compare_affine_homography_visual import execute_visual_comparison
        import tempfile

        src_path = 'PV_Coordinates_Ortho_Vung_1_20260929_0018.csv'
        temp_path = None
        if csv_file is not None:
            content = await csv_file.read()
            if content and len(content) > 10:
                temp_f = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
                temp_f.write(content)
                temp_f.close()
                src_path = temp_f.name
                temp_path = temp_f.name

        df_out, comparison_panels, stats = execute_visual_comparison(src_csv_path=src_path)

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        csv_buffer = io.StringIO()
        df_out.to_csv(csv_buffer, index=False, encoding='utf-8-sig')

        return {
            "status": "success",
            "total": len(comparison_panels),
            "stats": stats,
            "csv_data": csv_buffer.getvalue(),
            "panels": comparison_panels,
            "csv_file": "Bounding Box/PV_Affine_vs_Homography_Visual_Comparison.csv"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đối chiếu trực quan Affine vs Homography: {str(e)}")

@app.get("/api/download-parallelism-csv")
async def download_parallelism_csv_endpoint():
    """Tải file CSV kết quả đánh giá tính bảo toàn song song của mô hình Affine"""
    from verify_affine_parallelism import resolve_file_path, run_evaluation
    target_csv = resolve_file_path("PV_Affine_Parallelism_Evaluation.csv")
    if not os.path.exists(target_csv):
        run_evaluation()
    return FileResponse(
        target_csv,
        media_type="text/csv",
        filename="PV_Affine_Parallelism_Evaluation.csv"
    )

@app.get("/api/download-iou-evaluation-csv")
async def download_iou_evaluation_csv_endpoint():
    """Tải file CSV kết quả đo đạc sai số tịnh tiến tâm và IoU so sánh giữa GPS thuần và Affine"""
    from measure_affine_vs_gps_iou import resolve_file_path, run_evaluation
    target_csv = resolve_file_path("PV_Affine_vs_GPS_IoU_Evaluation.csv")
    if not os.path.exists(target_csv):
        run_evaluation()
    return FileResponse(
        target_csv,
        media_type="text/csv",
        filename="PV_Affine_vs_GPS_IoU_Evaluation.csv"
    )

@app.get("/api/download-edge-limitation-csv")
async def download_edge_limitation_csv_endpoint(kind: str = "detail"):
    """Tải CSV ghi nhận hạn chế Affine tại vùng mép (kind=detail: từng box, kind=summary: tổng hợp vùng)"""
    from analyze_affine_edge_limitation import run_evaluation
    base = os.path.dirname(os.path.abspath(__file__))
    name = "PV_Affine_Edge_Zone_Summary.csv" if kind == "summary" else "PV_Affine_Edge_Limitation_Evaluation.csv"
    target_csv = os.path.join(base, name)
    if not os.path.exists(target_csv):
        run_evaluation()
    return FileResponse(target_csv, media_type="text/csv", filename=name)


@app.get("/api/download-homography-dlt-csv")
async def download_homography_dlt_csv_endpoint():
    """Tải file CSV kết quả ước lượng Homography 3x3 (8 DOF) bằng thuật toán DLT + Chuẩn hóa Hartley"""
    from dlt_hartley_homography import resolve_file_path, run_dlt_hartley_pipeline
    target_csv = resolve_file_path("PV_Homography_DLT_Hartley_Evaluation.csv")
    if not os.path.exists(target_csv):
        run_dlt_hartley_pipeline()
    return FileResponse(
        target_csv,
        media_type="text/csv",
        filename="PV_Homography_DLT_Hartley_Evaluation.csv"
    )


@app.get("/api/download-obb-homography-corners-csv")
async def download_obb_homography_corners_csv_endpoint():
    """Tải file CSV kết quả ánh xạ 4 đỉnh OBB khuyết tật bằng ma trận Homography lên map 85m"""
    from transform_obb_homography_corners import resolve_file_path, run_obb_homography_mapping
    target_csv = resolve_file_path("PV_Transformed_OBB_Homography_85m.csv")
    if not os.path.exists(target_csv):
        run_obb_homography_mapping()
    return FileResponse(
        target_csv,
        media_type="text/csv",
        filename="PV_Transformed_OBB_Homography_85m.csv"
    )


@app.get("/api/download-homography-morphology-csv")
async def download_homography_morphology_csv_endpoint(kind: str = "detail"):
    """Tải CSV phân tích chuyển dịch hình thái (Hình chữ nhật -> Hình bình hành Affine -> Tứ giác phối cảnh Homography)"""
    from analyze_homography_morphology import run_morphology_evaluation
    base = os.path.dirname(os.path.abspath(__file__))
    name = "PV_Homography_Morphology_Zone_Summary.csv" if kind == "summary" else "PV_Homography_Morphology_Evaluation.csv"
    target_csv = os.path.join(base, name)
    if not os.path.exists(target_csv):
        run_morphology_evaluation()
    return FileResponse(target_csv, media_type="text/csv", filename=name)


@app.get("/api/download-landmark-sensitivity-csv")
async def download_landmark_sensitivity_csv_endpoint(kind: str = "detail"):
    """Tải CSV kiểm tra độ nhạy phân bố điểm mốc (Case A cụm góc vs Case B phân bố đều)"""
    from test_homography_landmark_distribution import run_landmark_sensitivity_test
    base = os.path.dirname(os.path.abspath(__file__))
    name = "PV_Homography_Landmark_Sensitivity_Summary.csv" if kind == "summary" else "PV_Homography_Landmark_Sensitivity_Evaluation.csv"
    target_csv = os.path.join(base, name)
    if not os.path.exists(target_csv):
        run_landmark_sensitivity_test()
    return FileResponse(target_csv, media_type="text/csv", filename=name)


@app.get("/api/download-affine-homography-comparison-csv")
async def download_affine_homography_comparison_csv_endpoint():
    """Tải CSV kết quả đối chiếu trực quan và định lượng giữa Affine và Homography trên 5.092 OBB"""
    from compare_affine_homography_visual import execute_visual_comparison
    base = os.path.dirname(os.path.abspath(__file__))
    target_csv = os.path.join(base, "PV_Affine_vs_Homography_Visual_Comparison.csv")
    if not os.path.exists(target_csv):
        execute_visual_comparison()
    return FileResponse(
        target_csv,
        media_type="text/csv",
        filename="PV_Affine_vs_Homography_Visual_Comparison.csv"
    )


class SaveMarkedPointsRequest(BaseModel):
    filename: str
    csv_content: str

@app.post("/api/save-marked-points-csv")
async def save_marked_points_csv(req: SaveMarkedPointsRequest):
    """Lưu file CSV các điểm đã chấm tự do từ giao diện web xuống ổ đĩa hệ thống"""
    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.abspath(os.path.join(cur_dir, ".."))
        
        # Ghi file vào thư mục Bounding Box
        path1 = os.path.join(cur_dir, req.filename)
        with open(path1, "w", encoding="utf-8-sig") as f:
            f.write(req.csv_content)
            
        # Ghi file vào thư mục gốc workspace (Kho làm việc riêng)
        path2 = os.path.join(parent_dir, req.filename)
        with open(path2, "w", encoding="utf-8-sig") as f:
            f.write(req.csv_content)
            
        return {"status": "ok", "saved_paths": [path1, path2], "filename": req.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/load-sample-csv")
async def load_sample_csv(csv_type: str = Query("vung")):
    """Đọc nội dung file CSV mẫu có sẵn trong thư mục làm việc để nạp nhanh lên bản đồ"""
    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.abspath(os.path.join(cur_dir, ".."))
        
        if csv_type == "vung":
            candidates = [
                os.path.join(parent_dir, "PV_Marked_Points_Ortho_Vung.csv"),
                os.path.join(cur_dir, "PV_Marked_Points_Ortho_Vung.csv"),
                os.path.join(parent_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv"),
                os.path.join(cur_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv"),
            ]
        else: # "big" / "tong_quan"
            candidates = [
                os.path.join(parent_dir, "PV_Marked_Points_Ortho_Tong_Quan.csv"),
                os.path.join(cur_dir, "PV_Marked_Points_Ortho_Tong_Quan.csv"),
                os.path.join(parent_dir, "bbox_centroid_export.csv"),
                os.path.join(cur_dir, "bbox_centroid_export.csv"),
            ]
            
        found_path = None
        for p in candidates:
            if os.path.exists(p):
                found_path = p
                break
                
        if not found_path:
            raise HTTPException(status_code=404, detail="Không tìm thấy file CSV mẫu phù hợp trên hệ thống")
            
        with open(found_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            lines = []
            for i, line in enumerate(f):
                lines.append(line)
                if i >= 2000: # Giới hạn tối đa 2000 dòng để trình duyệt phản hồi mượt mà
                    break
            content = "".join(lines)
            
        return {
            "status": "ok",
            "filename": os.path.basename(found_path),
            "content": content,
            "total_lines_read": len(lines)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mount thư mục static cho giao diện web
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
