import os
import glob
import json
import tempfile
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
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
        target_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    else:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp file_path hoặc tải file lên")

    try:
        info = processor.get_info(target_path)
        preview_path = processor.generate_preview(target_path, max_size=2048)
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
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file Ortho to: {big_target}")

    sub_target = None
    if sub_path and sub_path.strip():
        sub_target = os.path.normpath(sub_path.strip().strip('"').strip("'"))
        if not os.path.exists(sub_target):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy file Ortho vùng: {sub_target}")
    elif sub_file:
        sub_target = os.path.join(UPLOAD_DIR, sub_file.filename)
        with open(sub_target, "wb") as buffer:
            shutil.copyfileobj(sub_file.file, buffer)
    else:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp sub_path hoặc upload file Ortho vùng")

    try:
        result = processor.calculate_bounding_box(big_target, sub_target)
        # Sinh preview cho cả 2
        big_prev = processor.generate_preview(big_target, max_size=2048)
        sub_prev = processor.generate_preview(sub_target, max_size=1024)
        result["big_ortho"]["preview_filename"] = os.path.basename(big_prev)
        result["sub_ortho"]["preview_filename"] = os.path.basename(sub_prev)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tính toán Bounding Box: {str(e)}")

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

# Mount thư mục static cho giao diện web
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
