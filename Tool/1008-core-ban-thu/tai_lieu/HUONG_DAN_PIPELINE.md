# Hướng dẫn kỹ thuật A→Z: pipeline định vị lỗi tấm pin từ ảnh nhiệt

**Dự án:** 1008-stage1-rgb-thermal · **Ngày:** 11/08/2026 · **Đối tượng đọc:** người tiếp nhận code

Tài liệu này mô tả **toàn bộ chuỗi xử lý**, từ thẻ nhớ drone tới một dòng "lỗi X nằm ở tấm PNL-1234,
toạ độ (lon, lat)". Mỗi khối đều kèm: nguyên lý, thư viện dùng, code thật trong repo, và **những cái
đã thử mà hỏng** — phần cuối quan trọng ngang phần code.

---

## Mục lục

1. [Bản đồ toàn cảnh](#1-bản-đồ-toàn-cảnh)
2. [Thư viện: cái nào làm gì, cái nào không thay được](#2-thư-viện)
3. [Dữ liệu đầu vào và cấu trúc thư mục](#3-dữ-liệu-đầu-vào)
4. [Nền toán học chung — 6 phép biến đổi lõi](#4-nền-toán-học-chung)
5. [F1 · Hiệu chuẩn H: ảnh nhiệt → ảnh RGB](#5-f1--hiệu-chuẩn-h)
6. [F0 · Ba bộ lọc ảnh trước khi dựng](#6-f0--ba-bộ-lọc-ảnh)
7. [Dựng ortho nhiệt](#7-dựng-ortho-nhiệt)
8. [Phát hiện lỗi bằng YOLO-OBB](#8-phát-hiện-lỗi)
9. [F2→F5 · Chiếu box lên thực địa](#9-f2f5--chiếu-box-lên-thực-địa)
10. [F6 · Khử trùng lặp](#10-f6--khử-trùng-lặp)
11. [F7 · Gán lỗi vào tấm pin](#11-f7--gán-lỗi-vào-tấm-pin)
12. [Đo sai số & đánh giá](#12-đo-sai-số--đánh-giá)
13. [Viewer và báo cáo](#13-viewer-và-báo-cáo)
14. [Backend sản phẩm chạy thật](#14-backend-sản-phẩm)
15. [Runbook — thứ tự chạy đầy đủ](#15-runbook)
16. [Bẫy đã dẫm phải](#16-bẫy-đã-dẫm-phải)
17. [Sổ tay công thức + danh mục file](#17-sổ-tay)

---

## 1. Bản đồ toàn cảnh

Có **hai codebase**, đừng lẫn:

| | Vị trí | Vai trò |
|---|---|---|
| **Repo đánh giá** | `C:\Users\Chi\Desktop\1008-stage1-rgb-thermel` | Script rời, chạy tay. Hiệu chuẩn, lọc ảnh, dựng ortho nhiệt, **đo sai số**, val model. Đây là nơi ra các con số trong `BAO_CAO_DANH_GIA.md`. |
| **Backend sản phẩm** | `D:\Remote_Project\solarfarm_inspection\backend` | Flask + RQ + MongoDB. Chạy tự động khi người dùng upload ảnh. Chứa package `core/` mà repo đánh giá import sang. |

Luồng dữ liệu, từ trên xuống:

```
       ẢNH DRONE (598 cặp: _W.JPG là RGB 4056x3040, _T.JPG là nhiệt 640x512)
                             │
        ┌────────────────────┴────────────────────┐
        │                                          │
   [Metashape]                              [F1] calib_thermal_rgb.py
   dựng SfM từ ảnh RGB                      chấm tay ~12-31 cặp điểm
        │                                          │
        ├─ cameras.xml  (nội+ngoại tham số)        └─→ thermal_to_rgb.json
        ├─ dsm.tif      (mô hình độ cao)                   (ma trận H 3x3)
        └─ ortho.tif    (ortho màu, 0,957 cm/px)            │
                             │                              │
                             ├──────────────┬───────────────┤
                             │              │               │
                    [F0] lọc ảnh      [ghép ortho     [phát hiện lỗi]
                loc_anh_rung.py        nhiệt]          YOLO-OBB chạy trên
                loc_anh_tre.py    ghep_ortho_nhiet.py  TỪNG ẢNH NHIỆT LẺ
                             │              │               │
                     396/598 ảnh    ortho_nhiet_tu_lam  407 quan sát
                             │         .tif (2,9 cm/px)      │
                             └──────────────┘               │
                                                             ▼
                                        [F2→F5] chiếu pixel → tia → DSM → lon/lat
                                                core/ortho/projection.py
                                                             │
                                                             ▼
                                        [F6] gom cụm khử trùng lặp → 211 cụm
                                                core/pipeline/clustering.py
                                                             │
                                                             ▼
                                        [F7] gán vào polygon tấm pin → 195 có mã
                                                core/pipeline/grid_matcher.py
                                                             │
                                                             ▼
                                        loi_tren_ortho_nhiet.json → viewer/PDF
```

![Bốn ca lỗi: trái là ảnh nhiệt gốc có box model tìm được, phải là vị trí đã chiếu lên ortho màu](hinh/h3_loi_that.jpg)

*Hình 1 — Toàn bộ pipeline gói trong một ảnh. Mỗi ca: **trái** = ảnh nhiệt gốc, khung trắng là box
YOLO tìm được; **phải** = ortho màu, khung đỏ là 4 đỉnh box đó sau khi chiếu qua DSM. Thanh tiêu đề
ghi số hiệu ảnh, tên lớp, conf và lon/lat cuối cùng. Chú ý ba ca dưới có khung đỏ **méo thành hình
bình hành** — đó là hiệu ứng góc off-nadir, box chụp xiên chiếu xuống không còn là hình chữ nhật.*

> **Điểm mấu chốt phải nhớ:** YOLO chạy trên **ảnh nhiệt gốc từng tấm**, KHÔNG chạy trên ortho ghép.
> Ortho chỉ là hệ toạ độ đích + nền hiển thị. Bằng chứng nội tại: một lỗi được 1–5 ảnh khác nhau nhìn
> thấy (bảng F6), nếu detect trên ortho thì mỗi lỗi chỉ xuất hiện đúng một lần và bước F6 vô nghĩa.
> Lý do kỹ thuật: ortho nhiệt là ảnh **blend trung bình** nhiều ảnh chồng phủ — hotspot nhỏ bị làm
> nhoè, mất đúng cái chênh nhiệt độ mà model dựa vào; model lại train trên Ironbow của một lần bấm máy.

---

## 2. Thư viện

Cài trong `requirements.txt` của backend:

```
flask>=3.0.0          flask-cors>=4.0.0     pymongo>=4.6.0
redis>=5.0.0          rq>=1.16.0            PyJWT>=2.8.0
opencv-python-headless>=4.9.0               numpy>=1.26.0
scipy>=1.13.0         Pillow>=10.2.0        requests>=2.31.0
rasterio>=1.4.0       pyproj>=3.6.0         ultralytics>=8.4.106
python-dotenv         python-dateutil
```

Vai trò từng cái — và **cái nào thay được**:

| Thư viện | Dùng ở đâu | Thay được không |
|---|---|---|
| **numpy** | Toàn bộ đại số tuyến tính: ma trận 4x4 tư thế camera, xoay chunk, vector hoá cả tile ortho một lần | Không. Vector hoá là thứ giữ `ghep_ortho_nhiet.py` chạy vài phút thay vì vài giờ |
| **opencv (cv2)** | `undistort`, `findHomography` + RANSAC, `warpPerspective/warpAffine`, `Sobel/Canny/GaussianBlur`, `intersectConvexConvex` (IoU tứ giác), và **toàn bộ GUI chấm điểm** | Phần GUI thì có, phần `findHomography`/`intersectConvexConvex` thì rất phiền |
| **rasterio** | Đọc/ghi GeoTIFF (DSM, ortho), `Affine transform` pixel↔lon/lat, cửa sổ `Window`, ghi tiled+deflate | GDAL trực tiếp — nhưng rasterio là wrapper của GDAL, không có lý do đổi |
| **pyproj** | `Transformer` giữa ba hệ: **EPSG:4978** (ECEF, mét, gốc tâm Trái Đất) ↔ **EPSG:4326** (WGS84 lon/lat độ) ↔ **EPSG:32649** (UTM 49N, mét) | Không. Đây là binding PROJ, không tự viết được cho đúng |
| **ultralytics** | `YOLO(...).predict()` cho detect, `.val()` cho đo mAP/PR/confusion matrix | Không, vì model `.pt` là định dạng của nó |
| **scipy** | `cKDTree` — tìm ảnh gần nhất cho mỗi pixel ortho. `spatial.transform.Rotation` — đổi ma trận xoay ↔ rotvec ↔ Euler | `cKDTree` có fallback brute-force sẵn trong code (`ghep_ortho_nhiet.py:167-171`), chậm hơn nhiều |
| **shapely** | `Point.within(Polygon)`, `poly.distance(pt)` cho F7 gán tấm pin | Có, nhưng phải tự viết point-in-polygon |
| **flask / rq / redis / pymongo** | Chỉ backend sản phẩm: API, hàng đợi job, pub/sub tiến độ, lưu anomaly | — |

**Phần mềm ngoài Python:** Agisoft Metashape (dựng SfM → `cameras.xml`, `dsm.tif`, `ortho.tif`),
pandoc + Chrome headless (`xuat_pdf.py` xuất báo cáo PDF).

---

## 3. Dữ liệu đầu vào

```
1008-stage1-rgb-thermel/
├── Thermal2_31M_full_export/     ← output của Metashape, KHÔNG sửa tay
│   ├── cameras.xml               ← nội tham số + tư thế từng ảnh + chunk transform
│   ├── dsm.tif                   ← độ cao bề mặt (gồm cả mặt tấm pin, không phải mặt đất)
│   └── ortho.tif                 ← ortho màu, GSD 0,957 cm/px
├── data_aligned/rgb/  data_aligned/thermal/   ← ảnh đã ghép cặp
├── manifest_anh.csv              ← seq, path_rgb, path_thermal (khoá nối mọi script)
├── thermal_to_rgb.json           ← ma trận H, sản phẩm của F1
├── tam_pin_polygon.json          ← 6300 polygon tấm pin trên toạ độ ortho
└── best.pt                       ← YOLO-OBB detect TẤM PIN (khác model detect LỖI)
```

**Hai model YOLO khác nhau, đừng lẫn:**

| File | Nhiệm vụ | Chạy trên | Ghi chú |
|---|---|---|---|
| `best.pt` (`solarfarm_inspection/backend/yolo_models/`) | detect **tấm pin** (OBB, lớp `solar_panel`) | **chỉ ảnh RGB** | Trên ảnh nhiệt conf tụt còn 0,30–0,38 = mức nhiễu. Không bao giờ chạy bên nhiệt |
| `fault_obb_4class.pt` (`solar-thermal-fault-annotator/models/`) | detect **lỗi** 4 lớp OBB | ảnh nhiệt | mAP@50 0,965 · P 0,946 · R 0,897 trên tập test 91 ảnh / 280 đối tượng |

Bốn lớp lỗi: `SingleHotSpot`, `MultiHotSpot`, `Bypass`, `ModuleOpenCircuit`.

`manifest_anh.csv` là khoá nối — mọi script đều `csv.DictReader` nó rồi index theo `seq` (4 chữ số
lấy từ tên file DJI):

```python
rows = {r["seq"]: r for r in csv.DictReader(
    open("du_lieu/manifest_anh.csv", encoding="utf-8-sig"))}   # utf-8-sig: Excel để lại BOM
```

---

## 4. Nền toán học chung

Sáu phép biến đổi này lặp lại ở khắp nơi. Hiểu chúng là hiểu 80% codebase.

### 4.1 Đọc nội tham số Metashape → ma trận K của OpenCV

Metashape ghi `f, cx, cy` với **cx, cy là độ lệch so với tâm ảnh**, không phải toạ độ tuyệt đối:

```python
# calib_thermal_rgb.py:62-66
K = np.array([[s["f"], 0, w/2 + s["cx"]],
              [0, s["f"], h/2 + s["cy"]],
              [0, 0,      1.0]])
dist = np.array([s["k1"], s["k2"], s["p1"], s["p2"], s["k3"]])   # THỨ TỰ NÀY BẮT BUỘC
img = cv2.undistort(img, K, dist)
```

> Thứ tự `dist` của OpenCV là `[k1, k2, p1, p2, k3]` — **p đứng giữa k2 và k3**. Metashape liệt kê
> `k1 k2 k3 p1 p2`. Chép nhầm thứ tự thì méo không được khử mà còn bị thêm vào.

### 4.2 Pixel → tia trong ECEF

Ba tầng toạ độ: **camera → chunk → ECEF**. `<transform>` của camera là 4x4 (camera→chunk);
`<component><transform>` là rotation/translation/scale (chunk→ECEF).

```python
# project_box_to_ortho.py:147-186 (rút gọn)
x = (u - w/2 - cx) / f            # chuẩn hoá pinhole, ảnh ĐÃ undistort
y = (v - h/2 - cy) / f
d_cam = np.array([x, y, 1.0])     # +Z hướng ra trước ống kính

d_chunk = cam_transform[:3,:3] @ d_cam        # camera → chunk
C_chunk = cam_transform[:3, 3]                # tâm chụp trong chunk

C_ecef = S_chunk * (R_chunk @ C_chunk) + T_chunk   # tâm chụp trong ECEF (mét)
d_ecef = R_chunk @ d_chunk                          # hướng tia trong ECEF
d_ecef /= np.linalg.norm(d_ecef)
```

Lưu ý: **translation có nhân scale, direction thì không** (vector hướng không có đơn vị).

### 4.3 Cắt tia với DSM — tìm điểm chạm đất

Không có nghiệm đóng vì DSM là raster. Cách làm: **đi thô rồi chia đôi**.

```python
# project_box_to_ortho.py:220-276
for i in range(num_steps):                       # 500 bước trên 500 m
    P = origin + i*step * direction
    lon, lat, alt = ecef_to_wgs84.transform(*P)
    diff = alt - dsm.sample(lon, lat)            # >0 = còn trên mặt đất
    if prev_diff > 0 and diff <= 0:              # vừa xuyên qua mặt
        t_lo, t_hi = prev_t, i*step
        for _ in range(50):                      # chia đôi 50 lần
            t_mid = (t_lo + t_hi)/2
            ...
            if abs(diff_m) < 0.01: return lon_m, lat_m, dsm_m   # dừng ở 1 cm
```

Bản backend (`core/ortho/projection.py:339-361`) làm gọn hơn: bỏ bước đi thô, chặn khoảng
`[t_min, t_max]` bằng `z_min/z_max` của cả DSM rồi chia đôi 50 lần thẳng. Nhanh hơn, nhưng chỉ đúng
khi tia đi xuống (`u[2] < 0`, có kiểm tra ở dòng 336).

### 4.4 Bù xê dịch do độ cao tấm pin (relief displacement)

Đây là chỗ nhiều người bỏ sót. Tấm pin cao ~1,8–2,2 m so với mặt đất. Tia cắt DSM tại **mặt trên
tấm pin**, nhưng ortho vẽ mọi thứ như phẳng — nên vật cao bị đẩy ra xa tâm ảnh. Công thức đóng:

```
Δ = (H_tấm / H_drone) × (vị_trí_nadir_camera − điểm_chạm)
```

```python
# project_box_to_ortho.py:294-341
if theta < 1.0:                       # gần nadir, không cần bù
    return lon, lat, elev, 0.0

drone_h = max(cam_alt - elev, 15.0)
win = dsm.data[row-4:row+5, col-4:col+5]        # cửa sổ 2,5 m quanh điểm chạm
max_panel_alt = float(np.max(win[win != nodata]))
h_panel = max(max_panel_alt - elev, 1.8)        # sàn 1,8 m
scale_factor = h_panel / drone_h

lon_corr = lon + (cam_lon - lon) * scale_factor  # kéo về phía nadir
lat_corr = lat + (cam_lat - lat) * scale_factor
```

Đối xứng đúng 360°, không cần chia trường hợp theo hướng. `theta` là góc off-nadir của tia:
`theta = degrees(arctan(hypot(x, y)))` với `x, y` là toạ độ chuẩn hoá ở §4.2.

### 4.5 Lon/lat → pixel ortho

`rasterio` cho sẵn Affine transform; nghịch đảo bằng toán tử `~`:

```python
col, row = ~ortho.transform * (lon, lat)     # → float, làm tròn khi cần
lon, lat = ortho.transform * (col, row)      # chiều ngược
```

### 4.6 Đổi độ sang mét ở vĩ độ nhà máy

Hằng số dùng thống nhất trong repo (nhà máy ở vĩ độ 11,424°):

```python
mdeg = 111320 * np.cos(np.radians(11.424))   # ≈ 109 111 m / độ kinh
# vĩ độ: 110570 m/độ  (ghep_ortho_nhiet.py:139, 165)
```

GSD ortho màu: `abs(transform.a) * mdeg * 100 = 0,957 cm/px`.

---

## 5. F1 · Hiệu chuẩn H

**File:** [calib_thermal_rgb.py](../ma/calib_thermal_rgb.py) · **Ra:** `thermal_to_rgb.json`

### Vấn đề

![Bốn khung: ảnh nhiệt gốc, ảnh màu gốc, ảnh nhiệt bỏ nền, ảnh màu bỏ nền](../ket_qua/kiem_tra_warp/soi_manh_tre.jpg)

*Hình 2 — Vì sao **không** ghép được hai ảnh theo độ sáng. Cùng một chỗ, trái sang phải: nhiệt gốc ·
màu gốc · nhiệt sau khi bỏ nền · màu sau khi bỏ nền. Mặt tấm pin trong ảnh nhiệt **phẳng lì**, không
có lưới cell như ảnh màu; cỏ thì sáng ở màu nhưng tối ở nhiệt. Thứ duy nhất hiện rõ ở **cả hai phổ**
là **viền tấm pin** — nên mọi thuật toán ghép trong dự án đều làm trên bản đồ viền, không làm trên
cường độ.*

Metashape dựng SfM **từ ảnh RGB**, nên `cameras.xml` chỉ có tư thế của cảm biến RGB. Muốn dùng chung
tư thế đó cho ảnh nhiệt, cần một ma trận H (3x3, homography) đưa pixel nhiệt → pixel RGB. Hai cảm
biến gắn cứng cạnh nhau nên H **gắn với model drone, không gắn với trang trại** — chấm một lần dùng
mãi cho mọi trang trại bay bằng cùng loại drone.

### Cách chạy

```bash
python ma/calib_thermal_rgb.py \
  --thermal data_aligned/thermal/DJI_..._0280_T.JPG \
  --rgb     data_aligned/rgb/DJI_..._0280_W.JPG \
  --xml     Thermal2_31M_full_export/cameras.xml \
  --alt 31 --out thermal_to_rgb.json
```

Giao diện hai khung: trái ảnh nhiệt (tô Ironbow), phải ảnh RGB. Click bên trái → dấu **+ vàng** hiện
trên RGB ở vị trí H khởi tạo dự đoán → click vào điểm thật. Khoảng lệch giữa hai chỗ chính là sai số
của H hiện tại, in ra ngay từng cặp.

Ma trận khởi tạo lấy từ `RTK350.txt` — ghi H theo **phần trăm khung ảnh**, phải quy về pixel:

```python
# calib_thermal_rgb.py:83-85
H = (np.diag([w_rgb/100.0, h_rgb/100.0, 1.0]) @ H_pct
     @ np.diag([100.0/w_th, 100.0/h_th, 1.0]))
```

### Ước lượng H — ngưỡng RANSAC phải NỚI

```python
# calib_thermal_rgb.py:115-123
_, inl = cv2.findHomography(src, dst, cv2.RANSAC, 12.0)   # 12 px, KHÔNG phải 3
keep = inl.ravel().astype(bool)
H, _ = cv2.findHomography(src[keep], dst[keep], 0)        # 0 = least-squares trên inlier
```

Lý do ghi ngay trong code: đặt chặt 3 px sẽ vứt luôn các điểm ở rìa — vốn lệch do méo ống kính
nhiệt — khiến H fit trên một nhóm nhỏ ở giữa và mất ổn định. Ngưỡng nới chỉ để loại điểm chấm sai thô.

**Kết quả:** RMSE 4,38 px (ngưỡng đề bài ≤ 3 px, chưa đạt). Chấm ~12 cặp, **rải đều ra 4 góc** ảnh nhiệt.

![Bốn khung so sánh ma trận RTK350 cũ và ma trận hiệu chuẩn lại, trên hai ảnh 0320 và 0480](hinh/h1_hieu_chuan.jpg)

*Hình 3 — Kiểm chứng H bằng mắt: viền ảnh nhiệt sau khi warp (đỏ) chồng lên ảnh RGB. Trái = ma trận
mặc định `RTK350.txt`, phải = ma trận chấm lại. Nhìn đường đỏ có bám đúng khe giữa hai tấm pin không
— bên phải bám sát hơn rõ rệt. Hai hàng là hai ảnh khác nhau (0320 và 0480), để chắc rằng H đúng cho
cả chuyến bay chứ không chỉ đúng ở ảnh dùng để chấm.*

### Đã thử tự động và hỏng — đừng làm lại

[hieu_chuan_tu_dong.py](../ma/hieu_chuan_tu_dong.py) giữ lại làm hồ sơ. Hai hướng đã chết:

1. **Tương quan pha trên bản đồ viền.** Lưới tấm pin tuần hoàn quá đều → bản đồ viền gần như là hàm
   tuần hoàn 2D. Đo trực tiếp trên cặp 0280 (biết trước đáp án): giá trị tương quan **tại chính vị
   trí đúng là ÂM (−0,0057)**, các đỉnh mạnh nhất cách nhau đúng ~37–38 px = bước tấm pin. Đây là
   hạn chế bản chất, không tham số nào cứu được.
2. **Ghép theo góc tấm + RANSAC dùng detector.** Detector chỉ nhận tấm pin trên RGB (300 tấm,
   conf 0,91–0,94); trên nhiệt được 4–10 tấm conf 0,30–0,38. Muốn đi hướng này phải train lại
   detector trên ảnh nhiệt — một dự án riêng.

![Bản đồ viền hai phổ chồng nhau, xanh là viền RGB đỏ là viền nhiệt đã nắn](../ket_qua/kiem_tra_warp/hieu_chuan_0280.jpg)

*Hình 4 — Bằng chứng "bản đồ viền tốt, khâu ghép hỏng". Xanh = viền rút từ ảnh RGB, đỏ = viền rút từ
ảnh nhiệt đã nắn. Cả hai đều sắc nét và **cấu trúc trùng nhau** — dữ liệu không có vấn đề gì. Nhưng
để ý các đường đỏ lặp lại rất đều theo lưới tấm pin: chính tính tuần hoàn đó khiến tương quan pha
không phân biệt được ô tấm này với ô kế bên, và đó là thứ giết `hieu_chuan_tu_dong.py`.*

Bản đồ viền **tự nó vẫn tốt** — vấn đề nằm ở khâu ghép. Chính vì thế bản đồ viền vẫn được tái sử dụng
ở §6.2, nơi đã biết H đúng sẵn.

---

## 6. F0 · Ba bộ lọc ảnh

Trước khi dựng ortho, loại ảnh xấu. Ba bộ lọc, độc lập, cộng dồn: **598 → 396 ảnh**.

### 6.1 Lọc theo vị trí camera — đoạn quay đầu

Nằm ngay trong `ghep_ortho_nhiet.py:92-99`. Tốc độ suy từ khoảng cách hai ảnh **kề hai bên**:

```python
for i in range(1, len(ks)-1):
    spd[ks[i]] = np.linalg.norm(Cch[ks[i+1]] - Cch[ks[i-1]]) * S_ch / 2
med  = np.median(list(spd.values()))
good = [k for k in ks if spd.get(k, med) > 0.6 * med]      # dưới 60% trung vị = quay đầu
```

**Điểm mù đã biết:** ảnh **đầu** và **cuối** chuyến bay không có đủ hàng xóm hai bên → `spd.get(k, med)`
mặc định coi chúng bay đều. Đó là lý do phải có bộ lọc EXIF ở §6.3.

### 6.2 Lọc theo lệch ĐO ĐƯỢC — bộ lọc mạnh nhất

**File:** [loc_anh_tre.py](../ma/loc_anh_tre.py) · **Ra:** `anh_tre_chup_full.json` · **~44 phút cho 598 ảnh**

Nguyên lý ba bước:

1. Chạy detector tấm pin trên **ảnh RGB** (conf ~0,93).
2. Chiếu viền tấm vừa tìm được sang toạ độ ảnh nhiệt qua `H⁻¹`.
3. **Trượt** viền đó quanh vị trí gốc, tìm chỗ khớp nhất với viền thật trong ảnh nhiệt.

```python
# loc_anh_tre.py:102-118 — bước 1+2
r = model.predict(rgb, conf=0.5, imgsz=1024, max_det=2000)[0]
poly = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)
for p in poly:
    q = Hinv @ np.vstack([p.T, np.ones(4)])      # RGB → nhiệt
    q = (q[:2] / q[2]).T                          # chia toạ độ đồng nhất
    cv2.polylines(ve, [np.round(q).astype(np.int32)], True, 255, 1)
mau = cv2.GaussianBlur(ve.astype(np.float32)/255.0, (0,0), 1.5)
```

Viền ảnh nhiệt (`vien_nhiet`, dòng 90-99) — chuỗi lọc đã kiểm chứng:

```python
f = cv2.medianBlur(cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U), 5)
f = f - cv2.GaussianBlur(f, (0,0), 15)           # bỏ nền nhiệt biến thiên chậm
f = cv2.GaussianBlur(f, (0,0), 1.2)
g = np.hypot(cv2.Sobel(f, cv2.CV_32F,1,0,3), cv2.Sobel(f, cv2.CV_32F,0,1,3))
t = np.percentile(g, 80)                          # giữ 20% gradient mạnh nhất
return np.clip((g-t)/(g.max()-t), 0, 1)
```

Trượt + tinh dưới mức pixel bằng parabol:

```python
# loc_anh_tre.py:138-163
R = 16                                            # PHẢI nhỏ hơn nửa bước tấm (~18 px)
for dy in range(-R, R+1):
  for dx in range(-R, R+1):
    mv = cv2.warpAffine(mau, np.float32([[1,0,dx],[0,1,dy]]), (TW,TH))
    diem[iy,ix] = float((mv * that).sum())        # tương quan đơn giản
iy, ix = np.unravel_index(np.argmax(diem), diem.shape)
# đỉnh parabol theo từng trục → độ chính xác dưới 1 px
dx += 0.5*(y0-y2)/(y0-2*y1+y2)
```

![Viền tấm pin dự đoán màu vàng bên trái, viền sau khi bù màu xanh lá bên phải, trên ảnh nhiệt](../ket_qua/kiem_tra_warp/anh_tre_0080.jpg)

*Hình 5 — Kết quả `python ma/loc_anh_tre.py --soi 0080`. **Vàng** = viền tấm pin lấy từ detector chạy
trên ảnh RGB rồi chiếu sang toạ độ nhiệt qua H⁻¹ (vị trí "đáng lẽ"). **Xanh lá** = sau khi trượt tìm
chỗ khớp nhất với viền thật trong ảnh nhiệt. Chênh lệch giữa hai màu chính là lệch do trễ bấm máy —
ở ảnh này (+1,5 ; −2,3) px nhiệt ≈ 7 cm mặt đất. Ảnh nhiệt vẽ ở thang xám để nhìn viền cho rõ.*

> **Vì sao bước này không dính bẫy tuần hoàn đã giết `hieu_chuan_tu_dong.py`:** ở đó dò lệch **từ
> đầu** nên vùng tìm rộng hơn bước tấm và thuật toán nhảy nhầm ô. Ở đây H đã đúng sẵn, chỉ dò lệch
> nhỏ quanh 0 trong bán kính **hẹp hơn nửa bước tấm** → không thể nhảy sang ô kế bên.

**Kết quả:** trung vị 15,3 cm · P90 31,7 cm · lớn nhất 59,3 cm (toàn bộ 598 ảnh).

> ⚠️ **`H_da_bu` trong file output: ĐỪNG DÙNG.** Hằng số bù (+1,84; −3,70) px không cải thiện ortho:
> trước bù 15,5 cm → sau bù 14,4 cm, và hướng lệch **đảo dấu**. Đo trên 31 vùng khắp nhà máy: 15 vùng
> lệch lên, 16 lệch xuống — chia đôi 50/50, tức nhiễu cục bộ chứ không phải sai lệch hệ thống.
> Chỉ dùng khoá `anh_nen_loai`.

### 6.3 Lọc theo EXIF/XMP — chỉ đọc metadata, rất nhanh

**File:** [loc_anh_rung.py](../ma/loc_anh_rung.py) · **Ra:** `anh_rung.json`

DJI ZH20T nhét gói XMP ở đầu file JPEG, **ghi riêng cho từng cảm biến**. Rút bằng regex, không cần
thư viện EXIF:

```python
# loc_anh_rung.py:129-145
b = open(path,'rb').read(600_000)                 # XMP luôn nằm trong vài trăm KB đầu
s = b[b.find(b"<x:xmpmeta") : b.find(b"</x:xmpmeta>")+12].decode("utf-8","ignore")
for k in ["FlightXSpeed","FlightYSpeed","FlightZSpeed","FlightRollDegree", ...]:
    m = re.search(r'drone-dji:%s\s*=\s*"([^"]*)"' % k, s)
```

Bốn dấu hiệu, **chỉ hai cái bật mặc định**:

| Dấu hiệu | Công thức | Mặc định |
|---|---|---|
| `dv` | \|v(RGB) − v(nhiệt)\| — hai cảm biến đo tốc độ khác nhau = đang đổi tốc ngay lúc bấm | **BẬT**, > 1,0 m/s |
| `toc_do` | \|v ngang\| nhỏ = đang quay đầu / treo | **BẬT**, < 1,0 m/s |
| `gia_toc` | \|v[i+1] − v[i−1]\|/2 dọc tuyến | TẮT |
| `d_goc` | lệch roll+pitch giữa hai cảm biến | TẮT |

> 🔴 **Bẫy lớn nhất của cả dự án, ghi ở đầu file — đọc trước khi tin bộ lọc này.**
> Đối chiếu với lệch **đo được thật** trên đủ 598 ảnh: **không dấu hiệu tốc độ nào tách được ảnh
> tốt/xấu theo trung vị**. Tỉ số lệch trung vị (nhóm loại / nhóm giữ), muốn có ích phải > 1:
> `dv > 1,0` → **x0,89** · `toc_do < 1` → **x0,87** · `gia_toc` → ngược · `d_goc` → ngược.
> Bộ lọc quay đầu ở §6.1 cũng vậy: x0,93.
>
> **Đừng lặp lại sai lầm:** chạy thử trên mẫu 60 ảnh thì `dv` trông rất tốt (x1,7). Đó là ảo — chỉ 7
> ảnh vượt ngưỡng. Quét đủ 598 ảnh thì tỉ số đảo về 0,89. **Mọi ngưỡng mới phải kiểm trên toàn bộ.**
>
> **Cái có thật:** cả bốn dấu hiệu có **đuôi** nặng hơn chứ không phải **tâm** xấu hơn (tỉ số p90:
> 1,35–1,48). Chúng bắt trúng vài ảnh rất xấu nhưng quét theo cả đống ảnh tốt. Vẫn bật `dv` và
> `toc_do` vì chúng bắt được 3 ảnh mà hai bộ lọc kia bỏ sót — trong đó có ảnh **0001** lệch 22,63 px,
> ảnh xấu nhất của cả bộ (đúng điểm mù ở §6.1). Nhờ đó lệch lớn nhất giảm 22,63 → 17,52 px.

Lệnh đối chiếu — chạy khi muốn thêm/đổi ngưỡng:

```bash
python ma/loc_anh_rung.py --doi-chieu        # in bảng "tách ĐÚNG / tách NGƯỢC" cho từng dấu hiệu
```

**Kết quả cả ba bộ lọc:** giữ 396/598 ảnh · trung vị 5,83 → 5,38 px · p90 12,10 → 9,38 px ·
lớn nhất 22,63 → 17,52 px.

### 6.4 Đo độ trễ bấm máy giữa hai cảm biến

**File:** [do_tre_chup.py](../ma/do_tre_chup.py) · **Ra:** `do_tre_chup.json`

Đây là nhánh **chẩn đoán nguyên nhân**, không nằm trong luồng chạy thường. EXIF chỉ ghi tới **giây**
và hai ảnh trùng giây → không đọc được độ trễ từ metadata, phải ước lượng từ chính hình ảnh.

Nguyên lý: nếu cảm biến nhiệt bấm sau RGB một khoảng `dt`, tư thế đúng của nó là tư thế **nội suy dọc
quỹ đạo**, dịch đi `dt` giây. Thử nhiều `dt`, mỗi `dt` dựng một mảnh ortho nhiệt nhỏ rồi đo độ khớp
với ortho màu — `dt` cho độ khớp cao nhất là độ trễ thật.

```python
# do_tre_chup.py:104-118
def tu_the_tre(k, dt_giay):
    M = cams[k].copy()
    j = i + 1 if dt_giay >= 0 else i - 1        # nội suy sang ảnh kế tiếp / kề trước
    buoc = cams[ks[j]][:3,3] - cams[k][:3,3]
    M[:3,3] = cams[k][:3,3] + buoc * abs(dt_giay) * NHIP_HZ
    return M                                     # hướng camera GIỮ NGUYÊN
```

Giữ nguyên hướng camera là có chủ ý: trong 40 ms drone gần như không đổi hướng, và sai số hướng bậc
hai nhỏ hơn nhiều so với sai số tịnh tiến bậc một.

Đo độ khớp bằng tương quan trên **ảnh gradient**, không phải cường độ — cùng lý do ở Hình 2.

![Hai khung so sánh: không bù và bù -25 ms](../ket_qua/kiem_tra_warp/do_tre_chup.jpg)

*Hình 6 — Kết quả quét `dt`. Vàng = viền tấm pin từ ortho nhiệt, chồng lên ortho màu. Trái = không
bù, phải = bù −25 ms: các đường vàng bám sát khe tấm hơn.*

> Nhịp chụp giả định 1 Hz (`NHIP_HZ = 1.0`) vì EXIF không có subsecond. Nếu nhịp thật khác, **`dt`
> tìm được vẫn đúng theo đơn vị MÉT** — chỉ nhãn "ms" bị co giãn theo. Script báo cả hai đơn vị.
> Đã đo: ảnh 0080 trễ ~159 ms (lệch 80 px RGB) trong khi 0320/0440 chỉ 4–12 ms.

---

## 7. Dựng ortho nhiệt

**File:** [ghep_ortho_nhiet.py](../ma/ghep_ortho_nhiet.py) · **Ra:** `ortho_nhiet_tu_lam.tif` (8451 × 4997 px)

### Nguyên lý: inverse mapping

Không warp từng ảnh rồi chồng lên nhau (dễ có đường nối, tốn RAM). Thay vào đó **duyệt từng pixel
đích, hỏi ngược xem lấy giá trị ở đâu**:

```
pixel ortho → lon/lat → cao độ từ DSM → điểm 3D ECEF
           → chunk → chiếu vào ảnh RGB → qua H⁻¹ → pixel ảnh nhiệt → lấy giá trị (song tuyến)
```

### Ba thứ khiến nó chạy vài phút thay vì vài giờ

**1. Độ phân giải đặt theo ảnh nhiệt, không phóng to vô ích**

```python
OT = base_tf * rasterio.Affine.scale(3.0, 3.0)   # 0,957 → ~2,9 cm/px = đúng GSD nhiệt
```

**2. Mỗi pixel chỉ tính với một ảnh, tìm bằng cây KD**

```python
# ghep_ortho_nhiet.py:163-171
tree = cKDTree(np.c_[nad[:,0]*mdeg, nad[:,1]*110570])   # nad = tâm chụp DƯỚI ĐẤT
knn  = lambda P, k: tree.query(P, k=k)[1]
```

`nad` không phải toạ độ GPS của drone mà là **giao điểm của trục quang với mặt đất**:

```python
# ghep_ortho_nhiet.py:148-159
d = R_ch @ (M[:3,:3] @ np.array([-CX/F, -CY/F, 1.0]))    # tia qua tâm ảnh
t = (alt - zmed) / max(1e-6, -(d @ up))                   # up = pháp tuyến ellipsoid tại điểm đó
glon, glat, _ = to_wgs.transform(*(C + t*d))
```

**3. Thử nhiều ứng viên, nhưng chỉ trên pixel còn trống**

```python
K = min(24, len(lab))
for kk in range(nn.shape[1]):
    todo = np.where(~done)[0]          # CHỈ pixel chưa có giá trị
    if todo.size == 0: break
```

Vì sao cần tới 24 ứng viên: vùng phủ của ảnh **nhiệt** dưới đất chỉ ~15 × 12 m (41% × 44% khung RGB),
nhỏ hơn nhiều so với ảnh RGB — ảnh có tâm gần nhất thường vẫn **không chứa** pixel cần lấy.

### Vòng lõi, vector hoá theo tile 2048×2048

```python
# ghep_ortho_nhiet.py:203-259 (rút gọn)
LON = OT.c + OT.a*cc ;  LAT = OT.f + OT.e*rr          # lưới lon/lat của tile
Z   = DSM[dr, dc]                                     # tra DSM bằng index nguyên, không nội suy
X, Y, Zc = to_ecef.transform(LON.ravel(), LAT.ravel(), Z.ravel())
P4 = np.vstack([R_ch.T @ (np.stack([X,Y,Zc]) - T_ch[:,None]) / S_ch, np.ones(X.size)])

Pc = Minv[i] @ P4[:, sl]                              # chunk → camera i
u  = F*Pc[0]/Pc[2] + IW/2 + CX                        # → pixel RGB
v  = F*Pc[1]/Pc[2] + IH/2 + CY
q  = Hinv @ np.vstack([u[m], v[m], np.ones(m.sum())]) # → pixel nhiệt
tu, tv = q[0]/q[2], q[1]/q[2]

out[idx] = (T[y0,x0]*(1-fx)*(1-fy) + T[y0,x0+1]*fx*(1-fy)      # nội suy song tuyến
          + T[y0+1,x0]*(1-fx)*fy   + T[y0+1,x0+1]*fx*fy)
```

Ba mặt nạ chồng nhau, thứ tự có ý nghĩa: `z > 0` (trước ống kính) → `0 ≤ u,v < IW,IH` (trong khung
RGB) → `0 ≤ tu,tv < TW-1,TH-1` (trong khung nhiệt).

Cache ảnh nhiệt giới hạn 24 tấm (`ghep_ortho_nhiet.py:178-185`) — đọc 396 ảnh vào RAM sẽ tràn.

Ghi ra GeoTIFF tiled + deflate, `nodata=0`, và ép giá trị hợp lệ tối thiểu bằng 1 để phân biệt với lỗ:

```python
dst.write(np.maximum(out.reshape(th_,tw_), 1).astype(np.uint8) * done.reshape(th_,tw_), 1,
          window=rasterio.windows.Window(tx, ty, tw_, th_))
```

![Một vùng ortho nhiệt đã ghép, bảng màu Ironbow](../ket_qua/kiem_tra_warp/ortho_nhiet_tu_lam.jpg)

*Hình 7 — Một góc `ortho_nhiet_tu_lam.tif` (ảnh kiểm tra script tự xuất sau khi chạy xong). Dãy pin
liền mạch, **không thấy đường nối** giữa các ảnh — đó là kết quả của inverse mapping: mỗi pixel đích
lấy trọn từ một ảnh nguồn duy nhất thay vì chồng nhiều ảnh warp lên nhau. Vùng tối màu tím là cỏ và
lối đi (nguội hơn), vùng cam là mặt tấm pin. Chấm vàng rải rác ngoài dãy pin là **nhiễu nền nóng**,
không phải lỗi — đây cũng là lý do model phải chạy trên ảnh gốc chứ không phải trên ảnh này.*

```bash
python ma/ghep_ortho_nhiet.py                  # toàn nhà máy
python ma/ghep_ortho_nhiet.py --step 6         # nhanh gấp 4, thô hơn
python ma/ghep_ortho_nhiet.py --window 1163 2274 22613 10079   # chỉ vùng viewer
```

---

## 8. Phát hiện lỗi

Model `fault_obb_4class.pt` (YOLO26s-OBB, 4 lớp, 150 epoch) chạy trên **từng ảnh nhiệt lẻ**.

```python
r = model.predict(anh_nhiet, conf=0.25, imgsz=640, verbose=False)[0]
poly = r.obb.xyxyxyxy.cpu().numpy().reshape(-1, 4, 2)   # OBB: 4 đỉnh, KHÔNG phải x1y1x2y2
cls  = r.obb.cls.cpu().numpy()
conf = r.obb.conf.cpu().numpy()
```

**OBB khác box thường:** `r.obb` chứ không phải `r.boxes`; mỗi đối tượng là **4 đỉnh** cho phép hộp
xoay theo hướng dãy pin. Muốn quy về hộp thẳng trục thì lấy bao ngoài (`so_model_8lop.py` làm vậy để
so được với model 8 lớp vốn là task `detect`).

Backend sản phẩm có thêm một quy tắc tiền xử lý **bắt buộc**:

```python
# services/anomaly_detector.py:33-52
gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
gray_3ch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)     # 3 kênh giống hệt nhau
results = model.predict(source=gray_3ch, conf=0.25)
```

Model đó (`thermal_solar_anomaly.pt`) train trên **ảnh xám**, còn `fault_obb_4class.pt` train trên
**Ironbow**. Cho sai bảng màu vào là recall tụt thẳng — luôn kiểm bảng màu đầu vào khớp với lúc train.

---

## 9. F2→F5 · Chiếu box lên thực địa

**Code chuẩn:** `D:\Remote_Project\solarfarm_inspection\backend\core\ortho\projection.py`

Với mỗi box lỗi, chiếu **4 đỉnh + tâm**. Mỗi đỉnh đi qua đúng chuỗi §4.2 → §4.5.

### Khác biệt so với bản demo: khử méo bằng Newton

Bản backend không `cv2.undistort` cả ảnh mà **giải ngược mô hình méo cho từng pixel** bằng Newton-
Raphson 12 vòng — đầy đủ `k1..k4, p1, p2, b1, b2` (Metashape có thêm b1/b2 mà OpenCV không có):

```python
# core/ortho/projection.py:304-330
x_p, y_p = x_nd, y_nd
for _ in range(12):
    r2  = x_p**2 + y_p**2
    rad = 1 + k1*r2 + k2*r2**2 + k3*r2**3 + k4*r2**4
    fx = x_p*rad + p1*(r2 + 2*x_p**2) + 2*p2*x_p*y_p + b1*x_p + b2*y_p - x_nd
    fy = y_p*rad + p2*(r2 + 2*y_p**2) + 2*p1*x_p*y_p - y_nd
    if np.hypot(fx, fy) < 1e-13: break
    # ... Jacobian 2x2 giải tích, rồi x_p -= (fx*dfy_dy - fy*dfx_dy)/det
```

Rẻ hơn undistort cả ảnh khi chỉ cần vài chục pixel, và chính xác hơn (không qua nội suy ảnh).

Bản backend làm việc trong **UTM (EPSG:32649)** thay vì ECEF — mét phẳng, tiện tra DSM. Chuỗi
transformer khai báo ở dòng 279-281 và chỉ tạo khi CRS thực sự khác nhau.

### Chọn đúng ảnh để chiếu

**File:** [camera_select.py](../ma/camera_select.py). Một điểm dưới đất nằm trong nhiều ảnh; ảnh **đúng** là
ảnh mà điểm đó **gần tâm ảnh nhất** (góc off-nadir nhỏ nhất) — vì sai số bù relief tỉ lệ với `tan θ`.
Đây cũng là tiêu chí Metashape dùng khi ghép mosaic, nên khớp với ortho.

```python
# camera_select.py:141-167 — chiếu ngược, đúng nghịch đảo của §4.2
P_chunk = R.T @ (P_ecef - T) / S
P_cam   = (np.linalg.inv(cam["transform"]) @ np.append(P_chunk, 1.0))[:3]
if P_cam[2] <= 0: return None                      # điểm sau lưng camera
u = f * P_cam[0]/P_cam[2] + w/2 + cx
theta = np.degrees(np.arctan(np.hypot(x, y)))
...
hits.sort(key=lambda d: d["theta"])                # nhỏ nhất = nên dùng
```

Script cũng lọc camera **chưa align** — không có thẻ `<transform>` thì cũng không đóng góp vào ortho:

```python
tr = cam.find("transform")
if tr is None or not (tr.text or "").strip():
    skipped.append((label, "chưa align"))
```

Và tính "ô sở hữu" theo độ chồng phủ, để cùng một lỗi không bị đếm hai lần ngay từ đầu:

```python
# camera_select.py:173-187 — overlap 0,80 → ô 20%x20% khung
tw = (1.0 - overlap_side) * width
return ((width-tw)/2, (height-th)/2, (width+tw)/2, (height+th)/2)
```

> ⚠️ **`project_box_to_ortho.py` ở cả hai repo đang HỎNG.** File dùng `np`, `cv2`, `ET`, `rasterio`,
> `Transformer` khắp nơi nhưng phần import (dòng 18-30) chỉ có `sys`, `os` và package `core`. Chạy sẽ
> `NameError`. Ngoài ra `core/` **không tồn tại** trong thư mục Desktop. Đây là file demo tương tác
> (vẽ bbox bằng chuột rồi xem kết quả), không nằm trong luồng tự động. Muốn dùng, thêm vào đầu file:
> ```python
> import numpy as np, cv2, rasterio
> import xml.etree.ElementTree as ET
> from pyproj import Transformer
> ```
> và chạy từ `D:\Remote_Project\solarfarm_inspection\backend` (nơi có `core/`).

---

## 10. F6 · Khử trùng lặp

Cùng một lỗi bị 1–5 ảnh chồng phủ nhìn thấy → phải gom. Có **hai cách trong repo**:

### 10.1 Gộp theo IoU tứ giác (chính xác hơn)

```python
# camera_select.py:242-287
def quad_iou(q1, q2):
    a1 = cv2.contourArea(np.asarray(q1, np.float32))
    inter, _ = cv2.intersectConvexConvex(np.asarray(q1,np.float32), np.asarray(q2,np.float32))
    return inter / (a1 + a2 - inter)

order = sorted(range(len(dets)), key=lambda i: dets[i]["theta"])   # off-nadir nhỏ nhất trước
for i in order:
    if used[i]: continue
    cluster = [dets[i]]
    for j in order:
        if quad_iou(dets[i]["quad"], dets[j]["quad"]) >= 0.30:
            used[j] = True; cluster.append(dets[j])
    rep = dict(dets[i])                    # đại diện = quan sát chiếu chính xác nhất
    rep["n_views"] = len(cluster)
    rep["conf"] = max(d["conf"] for d in cluster)
```

Hai lựa chọn thiết kế đáng chú ý: **đại diện cụm chọn theo θ nhỏ nhất** (không phải conf cao nhất) vì
đó là quan sát chiếu chính xác nhất; **conf lấy max** của cả cụm.

### 10.2 Gộp theo khoảng cách (backend đang chạy)

```python
# core/pipeline/clustering.py:29-48
d_lat = (anom_lat - c_lat) * 111000.0
d_lon = (anom_lon - c_lon) * 111000.0 * np.cos(np.radians(c_lat))
if np.hypot(d_lat, d_lon) <= 2.5:          # 2,5 m trên lưới trang trại
    cluster["frame_count"] += 1
    if anom["confidence"] > cluster["confidence"]:
        cluster["confidence"] = anom["confidence"]
        cluster["error_type"] = anom["error_type"]
```

Ở đây sắp xếp theo **conf giảm dần**, đại diện là quan sát conf cao nhất. Đơn giản và nhanh hơn, đổi
lại không xét hình dạng box.

**Kết quả thực tế:** 407 quan sát → **211 cụm**, nén 1,93 lần (48,2% là trùng lặp).

| Số ảnh quan sát | Số cụm | Tỉ lệ |
|---|---:|---:|
| 1 ảnh | 84 | 39,8 % |
| 2 ảnh | 86 | 40,8 % |
| 3–5 ảnh | 41 | 19,4 % |

> **Dấu hiệu cần kiểm chứng:** 84 cụm (40%) chỉ thấy từ **1 ảnh**. Với độ chồng phủ cao thì mỗi lỗi
> lẽ ra phải được nhiều ảnh nhìn thấy. Hai cách giải thích: lỗi mờ chỉ 1 ảnh bắt được (khớp với
> recall 0,897), hoặc **cụm bị tách nhầm**. Chưa có kết luận.

---

## 11. F7 · Gán lỗi vào tấm pin

**Code:** `core/pipeline/grid_matcher.py` · **Dữ liệu:** `tam_pin_polygon.json` (6300 polygon)

Hai bước, thứ tự quan trọng:

```python
pt = Point(center_lon, center_lat)                  # shapely — chú ý (lon, lat)

for item in segment_polys:                          # 1. point-in-polygon chính xác
    if item["poly"].contains(pt) or item["poly"].touches(pt):
        return item

min_dist = float('inf')                             # 2. gần nhất trong 2,0 m
for item in segment_polys:
    dist_m = item["poly"].distance(pt) * 111000.0
    if dist_m <= 2.0 and dist < min_dist:
        min_dist, best_item = dist, item
```

**Kết quả:** rơi đúng trong polygon 186/211 (88,2%) · gán được mã 195/211 (**92,4%**, nhờ bước 2) ·
không rơi vào tấm nào 25/211 (11,8%). Ngưỡng đề bài ≥ 95% → chưa đạt.

![Bốn ca gán tấm pin: khung đỏ là box lỗi, khung xanh lá là polygon tấm được gán, kèm IoU](../ket_qua/kiem_tra_warp/gan_tam_pin_v2.jpg)

*Hình 8 — Bốn ca gán thành công. **Đỏ** = box lỗi đã chiếu lên ortho, **xanh lá** = polygon tấm pin
được gán, góc dưới ghi IoU và kết luận `TRONG`. IoU chỉ 0,51–0,69 nhưng **đó là đúng**: box lỗi
(~1 × 0,9 m) nhỏ hơn cả tấm pin (~1,9 × 0,9 m) nên trần lý thuyết chỉ 0,5–0,8. Ca thứ ba cho thấy
box lỗi méo theo góc chụp mà vẫn nằm gọn trong tấm.*

IoU giữa box lỗi và polygon tấm: trung vị 0,687. **Đừng so IoU này với IoU của model** — đây là giao
giữa box lỗi (~1 × 0,9 m) và cả tấm pin (~1,9 × 0,9 m), trần lý thuyết chỉ 0,5–0,8. 0,687 là gần trần,
tức box lỗi nằm gọn trong tấm.

[soi_25_ca_lech.py](../ma/soi_25_ca_lech.py) kiểm chứng 25 ca không gán được: tìm polygon gần nhất rồi đo
khoảng cách — quanh đó có tấm thì là định vị lệch, quanh đó trống thì detector tấm pin bỏ sót.

---

## 12. Đo sai số & đánh giá

### 12.1 Sai số end-to-end trên ortho — con số báo cáo

**File:** [do_sai_so_ortho.py](../ma/do_sai_so_ortho.py) · **Ra:** `sai_so_end_to_end.json`

Lấy các điểm neo đã chấm ở F1, chiếu qua **toàn bộ chuỗi** rồi hiển thị hai khung: trái ảnh drone
(để biết đang xét vật nào), phải ortho với dấu **+ vàng** = chỗ chuỗi tính ra. Người dùng click vào
vị trí **thật**. Khoảng cách chính là sai số cả chuỗi.

Class `Chain` (dòng 38-103) là bản gọn nhất của toàn bộ §4 — 65 dòng, đáng đọc trước tiên nếu muốn
hiểu nhanh phép chiếu.

![Ba mươi ba điểm neo đã chiếu, đánh dấu chữ thập đỏ có đánh số trên ortho màu](../ket_qua/kiem_tra_warp/chieu_len_ortho.jpg)

*Hình 9 — 33 điểm neo (chấm tay ở bước F1 trên ảnh drone) sau khi đi hết chuỗi §4.2 → §4.5 và rơi
xuống ortho. Mỗi dấu **+ đỏ** là chỗ chuỗi tính ra; người đo click vào vị trí thật, khoảng cách giữa
hai chỗ là sai số. Điểm rải khắp góc tấm và mép dãy — chọn góc tấm vì đó là chỗ **định vị lại được
bằng mắt** chính xác nhất trên cả hai ảnh. RMSE của lô này là 2,56 cm ≈ 2,7 px ortho.*

**Kết quả:** 11 điểm · trung bình 2,44 · trung vị 2,69 · **RMSE 2,56 cm** · lớn nhất 3,06 cm.
Ngưỡng đề bài ≤ 30 cm → **đạt, tốt hơn 10 lần**.

> **Vì sao 2,56 cm ở đây mà 15,3 cm ở §6.2** — hai phép đo khác đối tượng, cả hai đều đúng:
> phép đo này đo lệch của **sản phẩm ortho đã ghép**, mỗi pixel lấy từ nhiều ảnh chồng phủ nên sai số
> tư thế từng ảnh được trung bình hoá. Phép đo §6.2 đo lệch giữa **hai cảm biến trong một lần bấm máy**,
> chưa qua bước trung bình hoá đó.
>
> **Con số 2,56 cm mới đúng, không phải "20 cm".** Số 20 cm là ước lượng cũ trước khi đo trực tiếp.

### 12.2 Val model

```bash
python ma/val_tap_test.py       # tập TEST chia theo NHÓM chuyến bay → con số báo cáo
python ma/val_model_4lop.py     # so hai cách chia, để thấy chênh lệch
python ma/phan_tich_recall.py   # truy nguồn recall 0,897
```

> **Chia tập theo NHÓM chuyến bay, không chia ngẫu nhiên từng ảnh.** Khung ảnh drone chồng lấn nhau
> nên chia ngẫu nhiên sẽ để **cùng một tấm pin vật lý** nằm ở cả train lẫn val — điểm cao giả.
> `val_model_4lop.py` chạy cả hai bộ để thấy rõ chênh lệch; chỉ bộ `_nhom` được báo cáo.

![Ma trận nhầm lẫn của model trên tập test](../ket_qua/ket_qua_val/test_nhom/confusion_matrix.png)

*Hình 10 — Ma trận nhầm lẫn trên tập test 91 ảnh / 280 đối tượng (`ket_qua_val/test_nhom/`). Cột =
nhãn thật, hàng = dự đoán. **Cột `background`** = báo động giả; **hàng `background`** = đối tượng
thật không ai bắt được — đây chính là con số `phan_tich_recall.py` moi ra để trả lời "sót hay gán
nhầm lớp". Bốn đường cong P/R/F1/PR nằm cùng thư mục.*

`phan_tich_recall.py` tách bạch hai câu hỏi mà `recall = 0,897` gộp lại:

```python
kq = model.val(..., plots=True)          # BẮT BUỘC plots=True, ultralytics chỉ gọi
                                          # process_batch (dựng confusion matrix) khi có plots
M = np.array(kq.confusion_matrix.matrix)  # [dự_đoán+1, thật+1]
bo_sot = M[-1, :-1]                       # hàng 'background' = GT không ai bắt được
nham   = tong_gt - np.diag(M[:-1,:-1]) - bo_sot   # bắt được nhưng gán sai tên lớp
```

Và lấy recall **theo ngưỡng conf thật** từ đường cong R-Confidence, vì `b.mr` luôn báo tại điểm F1
lớn nhất — đổi `conf` cũng không đổi số:

```python
for c in kq.curves_results:
    if "Recall" in c[3] and "Confidence" in c[2]: rc = c
```

### 12.3 Tổng hợp mọi chỉ số

```bash
python ma/danh_gia_chi_so.py        # đọc hết JSON kết quả, in bảng so với ngưỡng đề bài
```

---

## 13. Viewer và báo cáo

| File | Việc |
|---|---|
| [xuat_nen_net.py](../ma/xuat_nen_net.py) | Xuất 3 lớp nền ở độ phân giải gốc (tối đa 8192 px), ra **file rời** cạnh HTML |
| [va_viewer_net.py](../ma/va_viewer_net.py) | **Vá chuỗi** vào `so_sanh_model.html` để nó tải bản nét và thay vào |
| [xuat_pdf.py](../ma/xuat_pdf.py) | md → pandoc → HTML → Chrome headless `--print-to-pdf` |

Vì sao xuất file rời chứ không nhúng base64: file HTML đã 38 MB; nhúng ảnh 8000 px thành ~100 MB và
trình duyệt phải giải nén hết mới vẽ được ô đầu tiên. Cách hiện tại: vẽ ngay bản 2400 px nhúng sẵn,
rồi âm thầm tải bản nét và thay vào.

> 🔴 **`so_sanh_model.html` KHÔNG có script dựng** — nó là file sinh ra từ một quy trình không lưu
> lại. Muốn sửa thì phải **vá chuỗi** vào HTML (xem `va_viewer_net.py`), không dựng lại được.
>
> **Cửa sổ cắt là `FRAME = dict(c0=1163, r0=2274, w=22613, h=10079)`**, đọc thẳng từ `DATA.frame`
> nhúng trong HTML. **Đừng suy ra từ lon/lat của các lỗi** — đã thử, khớp tới 0,25 cm nhưng chiều cao
> vẫn lệch 6,8 px ortho, đủ làm nền mới trôi ~4 cm so với nền cũ. `frame` là số nguyên gốc, dùng thẳng.
> Khung lỗi neo vào đây — sửa là lệch hết.

```bash
python ma/xuat_nen_net.py                # cả ba lớp
python ma/xuat_nen_net.py --lop th       # chỉ làm lại lớp nhiệt
python ma/va_viewer_net.py
python ma/xuat_pdf.py --vao BAO_CAO_DANH_GIA.md --ra BAO_CAO_DANH_GIA.pdf
```

---

## 14. Backend sản phẩm

Kiến trúc: **Flask (API) + RQ/Redis (hàng đợi) + MongoDB (lưu trữ) + Redis pub/sub (tiến độ)**.

```
routes/images.py          → nhận upload, enqueue job
        ↓
worker.py (RQ)            → gọi services/detection.py::process_image_detections(image_id)
        ↓
  1. cv2.imread + đọc XMP/EXIF (services/gps.py)
  2. gọi API detect panel  (call_analyze_panels_api → http://192.168.88.31:8088/analyze-panels)
  3. nạp grounding: cameras.xml + dsm.tif  (has_grounding = có XML/JSON VÀ có DSM)
  4. mỗi góc box → project_pixel_to_world_and_ortho(...)   ← §9
  5. crop phối cảnh từng tấm (cv2.getPerspectiveTransform + warpPerspective)
  6. db.anomalies.insert_many(...)
  7. r.publish(f"image:{id}:detection", {...})   → frontend hiện tiến độ real-time
```

Ba chi tiết đáng lưu ý:

**Fallback khi không có grounding.** Nếu thiếu `cameras.xml` hoặc `dsm.tif`, code tụt xuống
`pixel_to_gps(...)` — phép chiếu phẳng dùng GSD + yaw/pitch/roll từ XMP. Kém chính xác hơn nhiều
nhưng vẫn ra kết quả:

```python
# services/detection.py:167, 251-262
has_grounding = (has_xml or has_json) and os.path.exists(dsm_path)
...
else:
    lat, lon = pixel_to_gps(center_lat, center_lon, pt['x'], pt['y'], img_w, img_h,
                            gsd, yaw_deg, pitch_deg, roll_deg, altitude, ...)
```

**Bỏ cả box nếu một góc không chiếu được** — không vá tạm bằng góc khác:

```python
if not all_projected:
    continue   # Skip this box entirely!
```

**GSD tính riêng cho cảm biến nhiệt.** ZH20T có sensor width khác:

```python
sensor_width_mm = 7.68 if (img_w == 640 and img_h == 512) else config.SENSOR_WIDTH_MM
if not (640x512) and focal_length_35mm:
    sensor_width_mm = (focal_length / focal_length_35mm) * 36.0
```

---

## 15. Runbook

Thứ tự chạy đầy đủ cho một trang trại mới. Bước 0–1 chỉ làm **một lần cho mỗi model drone**.

```bash
# ── 0. Metashape (ngoài Python) ───────────────────────────────────────────
#    Import ảnh RGB → Align → Build DSM → Build Ortho
#    Export: cameras.xml, dsm.tif, ortho.tif  →  Thermal2_31M_full_export/

# ── 1. F1: hiệu chuẩn H  (MỘT LẦN / MODEL DRONE) ─────────────────────────
python ma/calib_thermal_rgb.py --thermal ..._T.JPG --rgb ..._W.JPG \
       --xml Thermal2_31M_full_export/cameras.xml --alt 31
#    → thermal_to_rgb.json   · mục tiêu RMSE < 5 px · chấm ~12 cặp rải 4 góc
#    Kiểm nhanh ma trận cũ:  python ma/calib_thermal_rgb.py --check --init cu.json ...

# ── 2. F0: lọc ảnh ───────────────────────────────────────────────────────
python ma/loc_anh_rung.py                 # ~1 phút (chỉ đọc XMP)   → anh_rung.json
python ma/loc_anh_tre.py                  # ~44 phút / 598 ảnh      → anh_tre_chup_full.json
python ma/loc_anh_rung.py --doi-chieu     # kiểm bộ lọc có tách ĐÚNG không

# ── 3. Dựng ortho nhiệt ──────────────────────────────────────────────────
python ma/ghep_ortho_nhiet.py             # → ortho_nhiet_tu_lam.tif + ảnh kiểm tra JPG

# ── 4. Detect + chiếu + gom cụm + gán tấm ────────────────────────────────
#    Chạy qua backend (upload ảnh → worker tự làm), hoặc gọi trực tiếp:
#      services/detection.py::process_image_detections
#      core/pipeline/clustering.py::cluster_and_merge_boxes
#      core/pipeline/grid_matcher.py::find_matching_segment
#    → loi_tren_ortho_nhiet.json

# ── 5. Đo sai số & đánh giá ──────────────────────────────────────────────
python ma/do_sai_so_ortho.py              # chấm tay → sai_so_end_to_end.json
python ma/val_tap_test.py                 # → ket_qua_val/ket_qua_test_4lop.json
python ma/phan_tich_recall.py             # → ket_qua_val/phan_tich_recall.json
python ma/soi_25_ca_lech.py               # kiểm 25 ca không gán được tấm
python ma/danh_gia_chi_so.py              # tổng hợp, so với ngưỡng đề bài

# ── 6. Viewer & báo cáo ──────────────────────────────────────────────────
python ma/xuat_nen_net.py && python ma/va_viewer_net.py
python ma/xuat_pdf.py
```

---

## 16. Bẫy đã dẫm phải

Danh sách này quan trọng ngang phần code. Mỗi dòng đều đã tốn thời gian thật.

| # | Bẫy | Thực tế | Ghi ở |
|---|---|---|---|
| 1 | Chốt ngưỡng bộ lọc trên **mẫu nhỏ** | Mẫu 60 ảnh: `dv` cho x1,7 (rất tốt). Đủ 598 ảnh: **x0,89** (ngược). Chỉ 7 ảnh vượt ngưỡng trong mẫu | `loc_anh_rung.py:41-46` |
| 2 | Chỉ nhìn **trung vị** khi đánh giá bộ lọc | Cả 4 dấu hiệu có **đuôi** nặng hơn nhưng **tâm** không xấu hơn. Phải in cả p50 lẫn p90 | `loc_anh_rung.py:48-52` |
| 3 | Dùng `H_da_bu` để dựng lại ortho | 15,5 → 14,4 cm, hướng lệch **đảo dấu**. Lệch là nhiễu cục bộ (50/50 hai hướng trên 31 vùng), không bù được bằng hằng số | `loc_anh_tre.py:26-49` |
| 4 | Ngưỡng RANSAC **chặt** khi tính H | 3 px vứt luôn điểm rìa (vốn lệch do méo ống kính nhiệt) → H fit trên nhóm nhỏ, mất ổn định. Dùng **12 px** | `calib_thermal_rgb.py:115-118` |
| 5 | Tự động hoá H bằng **tương quan pha** | Lưới tấm pin tuần hoàn → tương quan tại vị trí đúng là **ÂM**; các đỉnh cách nhau đúng bước tấm 37–38 px. Hạn chế bản chất | `hieu_chuan_tu_dong.py:7-24` |
| 6 | Chạy detector tấm pin trên **ảnh nhiệt** | RGB: 300 tấm conf 0,91–0,94. Nhiệt: 4–10 tấm conf 0,30–0,38 = mức nhiễu | `hieu_chuan_tu_dong.py:26-34` |
| 7 | Chia tập train/val **ngẫu nhiên từng ảnh** | Khung ảnh chồng lấn → cùng tấm pin vật lý ở cả train lẫn val → điểm cao giả. Phải chia theo **nhóm chuyến bay** | `val_model_4lop.py:6-11` |
| 8 | `model.val()` mà **không** `plots=True` | ultralytics chỉ gọi `process_batch` khi có plots → confusion matrix rỗng | `phan_tich_recall.py:8-9` |
| 9 | Đọc recall từ `b.mr` khi đổi ngưỡng conf | `b.mr` luôn báo tại điểm F1 lớn nhất, không đổi theo conf. Phải lấy từ đường cong R-Confidence | `phan_tich_recall.py:10-12` |
| 10 | Suy cửa sổ viewer từ **lon/lat** | Khớp tới 0,25 cm nhưng chiều cao lệch 6,8 px ortho → nền trôi ~4 cm. Dùng thẳng `DATA.frame` | `xuat_nen_net.py:23-28` |
| 11 | Nhầm **20 cm** là sai số ortho nhiệt | Sai số thật đo được là **2,56 cm** (RMSE trên ortho). 20 cm là ước lượng cũ trước khi đo | `BAO_CAO_DANH_GIA.md` §3.2 |
| 12 | Lẫn hai loại **IoU** | IoU model–nhãn (§12.2) khác IoU box lỗi–polygon tấm (§11, trần lý thuyết chỉ 0,5–0,8) | `BAO_CAO_DANH_GIA.md` §4 |
| 13 | Bán kính trượt ≥ nửa bước tấm | Thuật toán nhảy sang ô tấm kế bên. Giữ R = 16 px < 18 px | `loc_anh_tre.py:71-72` |
| 14 | `project_box_to_ortho.py` chạy được | Thiếu import `numpy/cv2/rasterio/ET/pyproj` → NameError. `core/` không có trong thư mục Desktop | §9 |
| 15 | Chạy detector tấm pin trên ortho ở **tỉ lệ gốc** | Ở 0,96 cm/px detector khoanh ra từng **cell**, không phải cả tấm pin → IoU với box lỗi tụt còn 0,02 (NGOÀI). Thu nhỏ 2x về 1,91 cm/px thì khoanh đúng tấm, IoU 0,57 (TRONG) | Hình 11 |

![Trái: chạy ở tỉ lệ gốc khoanh nhầm ra cell. Phải: thu nhỏ 2x khoanh đúng tấm pin](hinh/h4_bay_ti_le.jpg)

*Hình 11 — Bẫy #15, nhìn là hiểu ngay. Cùng một lỗi (đỏ), cùng một detector, chỉ khác tỉ lệ ảnh đầu
vào. **Trái** (0,96 cm/px): khung xanh bé xíu — detector tưởng mỗi ô cell là một "tấm pin", IoU 0,02,
kết luận `NGOÀI`. **Phải** (thu nhỏ 2x, 1,91 cm/px): khung xanh ôm đúng cả tấm, IoU 0,57, kết luận
`TRONG`. Detector học ở tỉ lệ nào thì phải cho ăn ở tỉ lệ đó — đây là nguồn gốc của một phần trong
25 ca không gán được tấm ở §11.*

---

## 17. Sổ tay

### Hằng số hay dùng

```python
GSD_ORTHO_CM = 0.9569205142071102     # cm/px, ortho màu Metashape
GSD_RGB_CM   = 0.993                  # cm/px, ảnh RGB ở độ cao bay
GSD_NHIET_CM = 2.9                    # cm/px, ortho nhiệt tự dựng (--step 3)
mdeg         = 111320 * cos(radians(11.424))    # m/độ kinh ≈ 109 111
mlat         = 110570                            # m/độ vĩ
FRAME        = dict(c0=1163, r0=2274, w=22613, h=10079)   # cửa sổ viewer, px ortho
buoc_tam_px  = 37..38                 # bước lưới tấm pin trên ảnh nhiệt
vung_phu_nhiet = "~15 x 12 m dưới đất = 41% x 44% khung RGB"
```

### Đổi đơn vị lệch

```python
lech_cm = lech_px_nhiet * TI_LE * GSD_RGB_CM
# TI_LE = hypot(H[0,0], H[1,0])  — số px RGB trên 1 px nhiệt  (loc_anh_tre.py:81)
```

### Danh mục file JSON

| File | Sinh bởi | Nội dung |
|---|---|---|
| `thermal_to_rgb.json` | `calib_thermal_rgb.py` | H 3x3, RMSE, các cặp điểm đã chấm |
| `anh_tre_chup_full.json` | `loc_anh_tre.py` | Lệch đo được từng ảnh, `anh_nen_loai`, `H_da_bu` (**không dùng**) |
| `anh_rung.json` | `loc_anh_rung.py` | 4 dấu hiệu bay/ảnh, `anh_nen_loai`, bảng đối chiếu |
| `exif_bay.json` | `loc_anh_rung.py` | Cache XMP đã rút (xoá đi thì đọc lại từ ảnh) |
| `sai_so_end_to_end.json` | `do_sai_so_ortho.py` | RMSE 2,56 cm + từng điểm |
| `loi_tren_ortho_nhiet.json` | backend | 211 cụm lỗi đã gán tấm |
| `tam_pin_polygon.json` | — | 6300 polygon tấm pin, toạ độ ortho |
| `ket_qua_val/*.json` | `val_*.py`, `phan_tich_recall.py` | mAP, P/R theo lớp, confusion matrix |

### Ảnh kiểm chứng: ở đâu, sinh bởi gì

| Thư mục | Nội dung | Sinh bởi |
|---|---|---|
| `kiem_tra_warp/` | Ảnh chẩn đoán từng bước: warp, bù, viền, trễ chụp, polygon | Các script tự ghi khi chạy `--soi` / chạy xong |
| `hinh/` | Ảnh đã chọn lọc để đưa vào báo cáo | Chọn tay |
| `net/` | Ba lớp nền độ phân giải gốc cho viewer | `xuat_nen_net.py` |
| `ket_qua_val/*/` | Đường cong P/R/F1/PR, ma trận nhầm lẫn, batch dự đoán | `ultralytics` khi `model.val(plots=True)` |

Ảnh trong tài liệu này để ở **đường dẫn tương đối** — `xuat_pdf.py` chạy với `cwd` là thư mục dự án
nên pandoc và Chrome đều tìm thấy. Copy file md đi nơi khác thì phải copy cả thư mục ảnh.

### Ba con số phải nhớ

- **2,56 cm** — RMSE định vị trên ortho (ngưỡng 30 cm, **đạt**)
- **0,897** — recall model, tức sót ~10% số lỗi. **Đây là điểm nghẽn thật**, định vị chính xác đến
  đâu cũng không cứu được lỗi model đã bỏ sót
- **92,4%** — tỉ lệ gán được mã tấm pin (ngưỡng 95%, **chưa đạt**)
