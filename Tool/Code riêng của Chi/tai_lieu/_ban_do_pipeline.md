# BẢN ĐỒ PIPELINE HỢP NHẤT — 1008-stage1-rgb-thermel

Nguồn: đọc code 18 script (code là nguồn sự thật, không tin HUONG_DAN_PIPELINE.md). Mọi đường dẫn tương đối tính từ `C:\Users\Chi\Desktop\1008-stage1-rgb-thermel\`.

Ba khối tách biệt, chỉ gặp nhau ở cuối:
- **Khối A — định vị** (ảnh nhiệt + RGB → H → ortho nhiệt → toạ độ GPS → mã tấm pin)
- **Khối B — đánh giá model phát hiện lỗi** (độc lập hoàn toàn với khối A, chỉ đụng ổ `D:\`)
- **Khối C — viewer / báo cáo** (tiêu thụ sản phẩm của A và B)

---

## 1. Chuỗi giai đoạn theo thứ tự chạy

### GĐ 0 — Dữ liệu phải có sẵn trước khi chạy bất cứ script nào
Không script nào trong khối A–D sinh ra các thứ này (xem mục 3).
Riêng `manifest_anh.csv` nay dựng lại được bằng `tao_manifest.py` (khôi phục 11/08/2026).

| Thứ cần có | Từ đâu |
|---|---|
| `Thermal2_31M_full_export\{cameras.xml, ortho.tif, dsm.tif, thermal_ortho.tif}` | Export tay từ Metashape |
| `manifest_anh.csv` (598 cặp, cột `seq,label_xml,file_rgb,file_thermal,path_rgb,path_thermal`, đường dẫn TUYỆT ĐỐI, có BOM) | `tao_manifest.py` — dựng lại được từ `cameras.xml` + ảnh gốc |
| `data_Thermel_2_31M\...` (ảnh gốc `_T.JPG` / `_W.JPG`), `data_aligned\rgb\`, `data_aligned\thermal\` | Dữ liệu bay |
| `D:\Remote_Project\solarfarm_inspection\RTK350.txt` | H khởi tạo theo model drone |
| `D:\...\backend\yolo_models\best.pt` (detector TẤM PIN) | Dự án solarfarm_inspection |
| `tam_pin_polygon.json` (6300 polygon tấm pin trên ortho màu) | `bo_dung_goc/tao_tam_pin_polygon.py` — khôi phục 12/08/2026 |

---

### GĐ 1 — `calib_thermal_rgb.py` · Hiệu chuẩn H nhiệt→RGB (CHẤM TAY, có người ngồi click)

| | |
|---|---|
| Ăn | `data_aligned/rgb/DJI_..._0280_W.JPG`, `data_aligned/thermal/DJI_..._0280_T.JPG`, `Thermal2_31M_full_export/cameras.xml` (undistort), `RTK350.txt` (H khởi tạo) |
| Đẻ | **`thermal_to_rgb.json`** (13 khoá: H_thermal_to_rgb, points_thermal/rgb, rmse_px, gsd_cm_per_px…) |
| Lệnh | `python ma/calib_thermal_rgb.py --thermal data_aligned/thermal/DJI_..._0280_T.JPG --rgb data_aligned/rgb/DJI_..._0280_W.JPG --xml Thermal2_31M_full_export/cameras.xml --alt 31` → chấm ~12 cặp rải 4 góc, bấm **H** tính, bấm **S** lưu (Q/ESC = mất hết) |

**BẪY GHI ĐÈ NGHIÊM TRỌNG:** `thermal_to_rgb.json` hiện trên đĩa có THÊM 7 khoá mà script này không ghi (`rmse_cm`, `baseline_RTK350_rmse_px`, `baseline_RTK350_rmse_cm`, `H_percent`, `fit_method`, `median_err_px`, `hieu_chinh_bo_sung`) — thêm tay hoặc bằng script đã xoá. `danh_gia_chi_so.py` dòng 102-105 ĐANG ĐỌC 3 khoá trong số đó. Chạy lại GĐ 1 với `--out thermal_to_rgb.json` sẽ xoá sạch chúng → GĐ 12 KeyError. **Muốn chấm lại thì `--out tên_khác.json` rồi trộn tay.**

Kết quả đang dùng: n_points=31, rmse_px=4.377, max_err_px=9.252, gsd=0.993 cm/px, nguồn ảnh 0280.

---

### GĐ 2 — `loc_anh_tre.py` · Lọc ảnh lệch do trễ chụp (đo trực tiếp trên từng ảnh lẻ)

| | |
|---|---|
| Ăn | `thermal_to_rgb.json`, `manifest_anh.csv`, `best.pt` (YOLO-OBB, CHỈ chạy trên ảnh RGB), ảnh `_W.JPG` + `_T.JPG` |
| Đẻ | **`anh_tre_chup_full.json`** (anh_nen_loai + `chi_tiet[]` gồm dx,dy,do_net cho từng ảnh), `kiem_tra_warp/anh_tre_<SEQ>.jpg` (chỉ khi `--soi`) |
| Lệnh | `python ma/loc_anh_tre.py --out anh_tre_chup_full.json` (~44 phút / 598 ảnh) · thử nhanh: `--so-anh 40` · soi 1 ảnh: `--soi 0080` |

**BẪY TÊN FILE:** mặc định `--out` là `anh_tre_chup.json` (bản mẫu 60 ảnh), nhưng GĐ 4 và GĐ 3 đều mặc định đọc `anh_tre_chup_full.json`. **Chạy toàn bộ phải truyền `--out anh_tre_chup_full.json`.**

**ĐỪNG dùng `H_da_bu`** trong file kết quả: đã dựng lại ortho và đo — 15,5 cm → 14,4 cm nhưng hướng lệch đảo dấu. Phần dùng được chỉ là `anh_nen_loai` và `chi_tiet` (để bù RIÊNG từng ảnh ở GĐ 4).

---

### GĐ 3 — `loc_anh_rung.py` · Lọc ảnh chụp lúc drone không bay đều (chỉ đọc XMP)

| | |
|---|---|
| Ăn | `manifest_anh.csv`, ảnh gốc (600 KB đầu mỗi JPEG), `exif_bay.json` (cache), `anh_tre_chup_full.json` (chỉ khi `--doi-chieu`) |
| Đẻ | **`anh_rung.json`**, **`exif_bay.json`** (cache XMP) |
| Lệnh | `python ma/loc_anh_rung.py` (~1 phút) · `python ma/loc_anh_rung.py --doi-chieu` để in bảng chấm điểm dấu hiệu |

Chỉ 2/4 dấu hiệu đang BẬT (`--dv 1.0`, `--toc-do-min 1.0`); `--gia-toc` và `--d-goc` mặc định `inf` = TẮT vì không thêm gì ở biên. Cache chỉ kiểm bằng SỐ DÒNG manifest — đổi nội dung mà giữ số dòng thì cache cũ vẫn dùng, muốn chắc phải xoá `exif_bay.json`.

---

### GĐ 4 — `ghep_ortho_nhiet.py` · Dựng ortho nhiệt toàn nhà máy

| | |
|---|---|
| Ăn | `cameras.xml`, `ortho.tif` (chỉ lấy lưới/CRS), `dsm.tif` (đọc trọn 296 MB vào RAM), `thermal_to_rgb.json`, `manifest_anh.csv`, ảnh `_T.JPG`, **`anh_tre_chup_full.json`** (loại ảnh + bù dx,dy từng ảnh), **`anh_rung.json`** (loại ảnh) |
| Đẻ | **`ortho_nhiet_tu_lam.tif`** (1 băng uint8, nodata=0, ~2,9 cm/px), `kiem_tra_warp/ortho_nhiet_tu_lam.jpg` |
| Lệnh | `python ma/ghep_ortho_nhiet.py` · nhanh gấp 4: `--step 6` · một vùng: `--window COL ROW W H` · giữ mọi ảnh: `--bo-loc-lech --bo-loc-rung` |

Đây là điểm hợp lưu: GĐ 1 + 2 + 3 đều đổ vào đây. Thiếu file `--lech`/`--rung` thì script NÓI RA rồi vẫn chạy nhưng không lọc. Bù riêng từng ảnh giảm sai số đặt chỗ 14,1 → 4,3 cm (trung vị trên 275 cửa sổ).

---

### GĐ 5 — `do_khop_ortho.py` · QC: đo ortho nhiệt khớp ortho màu đến đâu

| | |
|---|---|
| Ăn | `ortho.tif`, `ortho_nhiet_tu_lam.tif` (+ `ortho_nhiet_can_sang.tif`, `ortho_nhiet_bu_anh.tif` nếu có — HIỆN KHÔNG CÓ) |
| Đẻ | **`do_khop_ortho.json`** (tên bản → mảng lệch px của 300 cửa sổ) |
| Lệnh | `python ma/do_khop_ortho.py` (không argparse, hằng số ở đầu file: O=192, R=12, N=300, seed 20260811) |

**ĐỪNG nới `R` lên** — bán kính trượt ±12 px = ±34 cm cố ý hẹp hơn nửa bước hàng tấm (~2 m) để không nhảy nhầm hàng (đúng cái đã làm hỏng nhánh cụt ở mục 4).

---

### GĐ 6 — `do_sai_so_ortho.py` · Đo sai số end-to-end (TƯƠNG TÁC, chấm tay trên ortho)

| | |
|---|---|
| Ăn | `ortho.tif`, `cameras.xml` (đọc VÔ ĐIỀU KIỆN ở dòng 296), `dsm.tif`, `thermal_to_rgb.json` (khoá `points_rgb`), `data_aligned/rgb/<label>*.JPG`, `chieu_diem_cache.json` (nếu có) |
| Đẻ | **`sai_so_end_to_end.json`**, **`chieu_diem_cache.json`** |
| Lệnh | `python ma/do_sai_so_ortho.py` (mặc định `--label DJI_20260411085535_0280_W`) — chuột trái chấm, **S** lưu, Q/ESC mất hết |

**BẪY CACHE:** có `chieu_diem_cache.json` thì script nạp thẳng cache, KHÔNG mở `dsm.tif`/`thermal_to_rgb.json` nữa. Đổi `--label` hay `--points` mà quên xoá cache → toạ độ chiếu vẫn của lần cũ, trong khi ảnh panel trái lại đổi theo label. **Đổi tham số thì phải xoá cache.**

---

### GĐ 7 — **[KHUYẾT]** Phát hiện lỗi → chiếu lên ortho → gom cụm → gán mã tấm pin

Sinh ra `loi_tren_ortho_nhiet.json` (in_panel, panel_code, ocol, orow, lon, lat, iou, dist_cm, n, conf, cls, w_m, h_m). **KHÔNG script nào trong 18 file sinh ra file này** — đã grep toàn bộ `*.py` ở thư mục gốc, chỉ có 3 script ĐỌC nó (`soi_25_ca_lech.py`, `danh_gia_chi_so.py`, `soi_loi_bi_bo.py`) và `dong_goi.py` nhắc tên. File có sẵn trên đĩa (95 KB, 10/8/2026, 211 lỗi).

Hai script liên quan nhưng KHÔNG nối vào luồng:
- `camera_select.py` — chọn ảnh drone đúng để chiếu (off-nadir nhỏ nhất) + gộp box trùng theo IoU tứ giác. **Chỉ in stdout, không ghi file.** `quad_iou()`/`merge_detections()` không được `main()` gọi — là hàm thư viện chờ script khác import. Lệnh: `python ma/camera_select.py --xml Thermal2_31M_full_export/cameras.xml --lon 108.8514744 --lat 11.4246698 --alt 46.5 --top 5`
- `project_box_to_ortho.py` — **ĐANG HỎNG, KHÔNG CHẠY ĐƯỢC** (xem mục 4).

---

### GĐ 8 — `soi_25_ca_lech.py` · Soi các ca lỗi không gán được tấm pin

| | |
|---|---|
| Ăn | `loi_tren_ortho_nhiet.json`, `tam_pin_polygon.json` |
| Đẻ | **`soi_25_ca_lech.json`** (phân nhóm A/B/C + chi tiết từng ca) |
| Lệnh | `python ma/soi_25_ca_lech.py` (không cờ nào) |

`GSD_ORTHO_CM = 0.9569205142071102` bị CỨNG HOÁ, comment ghi "tu sai_so_end_to_end.json" nhưng script KHÔNG đọc lại file đó — phải chép tay sau mỗi lần đổi ortho.

---

### GĐ 9 — `xuat_nen_net.py` → GĐ 10 — `va_viewer_net.py` · Viewer nền nét

| | |
|---|---|
| GĐ 9 ăn | `ortho.tif`, `ortho_nhiet_tu_lam.tif`, `thermal_ortho.tif` |
| GĐ 9 đẻ | **`net/net_rgb.jpg`, `net/net_th.jpg`, `net/net_thms.jpg`** |
| GĐ 9 lệnh | `python ma/xuat_nen_net.py` (mặc định 8192 px) · `--lop th` chỉ làm lại lớp nhiệt |
| GĐ 10 ăn | `so_sanh_model.html`, kiểm tồn tại `net/*.jpg` |
| GĐ 10 đẻ | `so_sanh_model.html` (vá tại chỗ) + `so_sanh_model.html.truoc_net.bak` |
| GĐ 10 lệnh | `python ma/va_viewer_net.py` · hoàn tác: `--hoan-tac` |

**Bắt buộc theo thứ tự này** — GĐ 9 in ra "Chạy tiếp: python ma/va_viewer_net.py". `FRAME = (c0=1163, r0=2274, w=22613, h=10079)` là số cứng đọc từ `DATA.frame` trong HTML — đừng sửa. Vá bằng thay chuỗi ở đúng 4 chỗ, lệch một chỗ là dừng, không ghi gì. **Có script khác cũng vá cùng file** (`va_viewer_ngoai_nen.py`, bản sao riêng `.truoc_ngoai_nen.bak`) — hoàn tác chéo có thể mất phần vá của script kia.

---

### GĐ 11 — Khối B: Đánh giá model 4 lớp (độc lập, chỉ đụng ổ `D:\`)

| # | Script | Ăn | Đẻ | Lệnh |
|---|---|---|---|---|
| 11a | `val_tap_test.py` | `fault_obb_4class.pt`, `solar_cls4_nhom/data.yaml`, `test/images` (91) + `test/labels` (280 dòng) | `ket_qua_val/data_test_nhom.yaml`, `ket_qua_val/ket_qua_test_4lop.json`, `ket_qua_val/test_nhom/` (12 hình) | `python ma/val_tap_test.py` |
| 11b | `phan_tich_recall.py` | `fault_obb_4class.pt`, **`ket_qua_val/data_test_nhom.yaml`** (không tự tạo!) | `ket_qua_val/phan_tich_recall.json`, `ket_qua_val/_phan_tich/` | `python ma/phan_tich_recall.py` |
| 11c | `val_model_4lop.py` | cùng model, 2 bộ: `solar_cls4_nhom` + `solar_cls4_final_ngaunhien`, split `val` | `ket_qua_val/data_<bộ>.yaml`, `ket_qua_val/ket_qua_val_4lop.json`, `ket_qua_val/val_<bộ>/` | `python ma/val_model_4lop.py` |
| 11d | `so_model_8lop.py` | `fault_obb_4class.pt` + `muon_det_8class.pt`, ảnh + nhãn test | `ket_qua_val/so_model_8lop.json` | `python ma/so_model_8lop.py` |

**Ràng buộc cứng: 11a phải chạy trước 11b** (11b chỉ ĐỌC `data_test_nhom.yaml`, và cũng không gọi `os.makedirs`). **11d cũng không gọi `os.makedirs(RA)`** — nếu `ket_qua_val/` chưa có thì ba lượt predict chạy xong mới văng `FileNotFoundError` và mất trắng. `plots=True` là BẮT BUỘC ở 11b (ultralytics chỉ dựng confusion matrix khi có plots).

Chỉ bộ `solar_cls4_nhom` được phép báo cáo; bộ `_ngaunhien` là điểm cao giả (model được train trên chính nó, khung ảnh drone chồng lấn nên cùng tấm pin nằm ở cả train lẫn val).

**Tác dụng phụ không khai trong code:** ultralytics GHI `labels.cache` ngược vào bộ dữ liệu trên ổ `D:\` (`test/labels.cache`, `val/labels.cache`). Bộ dữ liệu không thật sự chỉ-đọc; sửa nhãn `.txt` mà cache chưa hết hạn thì val dùng nhãn cũ.

---

### GĐ 12 — `danh_gia_chi_so.py` · Bảng chỉ số nghiệm thu (điểm hợp lưu cuối)

| | |
|---|---|
| Ăn | `thermal_to_rgb.json`, `kiem_chung_0320.json` (đọc cứng), `kiem_chung_0440.json`, `kiem_chung_0080.json` (tuỳ chọn), `sai_so_end_to_end.json`, `anh_tre_chup_full.json`, `anh_rung.json`, `loi_tren_ortho_nhiet.json` |
| Đẻ | **KHÔNG GHI FILE NÀO** — chỉ in stdout, muốn giữ phải tự redirect |
| Lệnh | `python ma/danh_gia_chi_so.py` |

Thiếu `thermal_to_rgb.json`, `kiem_chung_0320.json`, `sai_so_end_to_end.json`, `anh_tre_chup*.json` hoặc `loi_tren_ortho_nhiet.json` là hỏng ngay (đọc cứng, không kiểm tồn tại).

---

### Nhánh chẩn đoán (chạy lúc nào cũng được sau GĐ 1, không ai tiêu thụ kết quả)

`do_tre_chup.py` — dò độ trễ bấm máy trên ortho. Ăn `thermal_to_rgb.json`, `cameras.xml`, `ortho.tif`, `dsm.tif`, `manifest_anh.csv`, ảnh `_T.JPG`, `tam_pin_polygon.json`. Đẻ `do_tre_chup.json` + `kiem_tra_warp/do_tre_chup.jpg` (+ `soi_manh_tre.jpg` khi `--soi`). Lệnh: `python ma/do_tre_chup.py`.
Kết quả hiện tại: **`dang_tin = false`**, ti_le_nhieu 0,286 → con số −24,8 ms CHỈ LÀ NHIỄU. Kết luận: trong dữ liệu này trễ chụp KHÔNG phải nguyên nhân chính gây lệch ortho.

---

## 2. Bảng TRA NGƯỢC file → script sinh / script tiêu thụ

Sắp theo thứ tự file xuất hiện trong pipeline.

| # | File ở gốc dự án | SINH ra bởi | TIÊU THỤ bởi |
|---|---|---|---|
| 1 | `manifest_anh.csv` | *(mồ côi)* | `hieu_chuan_tu_dong.py`, `do_tre_chup.py`, `loc_anh_tre.py`, `loc_anh_rung.py`, `ghep_ortho_nhiet.py` |
| 2 | `Thermal2_31M_full_export\cameras.xml` | *(mồ côi — Metashape)* | `calib_thermal_rgb.py`, `do_tre_chup.py`, `ghep_ortho_nhiet.py`, `camera_select.py`, `do_sai_so_ortho.py` |
| 3 | `Thermal2_31M_full_export\ortho.tif` | *(mồ côi — Metashape)* | `do_tre_chup.py`, `ghep_ortho_nhiet.py`, `xuat_nen_net.py`, `do_sai_so_ortho.py`, `do_khop_ortho.py` |
| 4 | `Thermal2_31M_full_export\dsm.tif` | *(mồ côi — Metashape)* | `do_tre_chup.py`, `ghep_ortho_nhiet.py`, `do_sai_so_ortho.py` |
| 5 | `Thermal2_31M_full_export\thermal_ortho.tif` | *(mồ côi — Metashape)* | `xuat_nen_net.py` |
| 6 | ảnh gốc `_T.JPG` / `_W.JPG` | *(mồ côi — dữ liệu bay)* | `calib_thermal_rgb.py`, `hieu_chuan_tu_dong.py`, `do_tre_chup.py`, `loc_anh_tre.py`, `loc_anh_rung.py`, `ghep_ortho_nhiet.py`, `do_sai_so_ortho.py` |
| 7 | `RTK350.txt` (ổ D:) | *(mồ côi)* | `calib_thermal_rgb.py` (`--init`) |
| 8 | `best.pt` (detector tấm pin) | *(mồ côi)* | `loc_anh_tre.py` |
| 9 | **`thermal_to_rgb.json`** | `calib_thermal_rgb.py` (+ 7 khoá thêm tay) | `hieu_chuan_tu_dong.py`, `do_tre_chup.py`, `loc_anh_tre.py`, `ghep_ortho_nhiet.py`, `do_sai_so_ortho.py`, `danh_gia_chi_so.py` |
| 10 | `kiem_chung_0320/0440/0080.json` | *(mồ côi — script đã xoá?)* | `danh_gia_chi_so.py` |
| 11 | `H_tu_dong.json` | `hieu_chuan_tu_dong.py` | **không ai** (nhánh cụt) |
| 12 | `do_tre_chup.json` | `do_tre_chup.py` | **không ai** (chẩn đoán) |
| 13 | `tam_pin_polygon.json` | *(mồ côi)* | `do_tre_chup.py`, `soi_25_ca_lech.py` |
| 14 | **`anh_tre_chup_full.json`** | `loc_anh_tre.py --out anh_tre_chup_full.json` | `ghep_ortho_nhiet.py`, `loc_anh_rung.py --doi-chieu`, `danh_gia_chi_so.py` |
| 15 | `anh_tre_chup.json` (mẫu 60 ảnh) | `loc_anh_tre.py` (mặc định) | `danh_gia_chi_so.py` (chỉ khi thiếu bản `_full`) |
| 16 | `exif_bay.json` | `loc_anh_rung.py` | `loc_anh_rung.py` (cache của chính nó) |
| 17 | **`anh_rung.json`** | `loc_anh_rung.py` | `ghep_ortho_nhiet.py`, `danh_gia_chi_so.py` |
| 18 | **`ortho_nhiet_tu_lam.tif`** | `ghep_ortho_nhiet.py` | `ghep_ortho_nhiet.py` (đọc lại để xuất JPG), `xuat_nen_net.py`, `do_khop_ortho.py` |
| 19 | `ortho_nhiet_can_sang.tif`, `ortho_nhiet_bu_anh.tif` | *(không script nào — HIỆN KHÔNG CÓ trên đĩa)* | `do_khop_ortho.py` (tự bỏ qua) |
| 20 | `do_khop_ortho.json` | `do_khop_ortho.py` | **không ai** |
| 21 | `chieu_diem_cache.json` | `do_sai_so_ortho.py` | `do_sai_so_ortho.py` (cache của chính nó) |
| 22 | **`sai_so_end_to_end.json`** | `do_sai_so_ortho.py` (chỉ khi bấm S) | `danh_gia_chi_so.py`; `soi_25_ca_lech.py` chép TAY hằng GSD |
| 23 | **`loi_tren_ortho_nhiet.json`** | *(mồ côi — GĐ 7 khuyết)* | `soi_25_ca_lech.py`, `danh_gia_chi_so.py`, `soi_loi_bi_bo.py` |
| 24 | `soi_25_ca_lech.json` | `soi_25_ca_lech.py` | **không ai** |
| 25 | `net\net_rgb.jpg`, `net_th.jpg`, `net_thms.jpg` | `xuat_nen_net.py` | `va_viewer_net.py` (chỉ kiểm tồn tại), trình duyệt |
| 26 | `so_sanh_model.html` | *(mồ côi — không có script dựng lại)* | `va_viewer_net.py` (đọc + vá), `va_viewer_ngoai_nen.py` |
| 27 | `so_sanh_model.html.truoc_net.bak` | `va_viewer_net.py` | `va_viewer_net.py --hoan-tac` |
| 28 | `kiem_tra_warp\*.jpg` | `hieu_chuan_tu_dong.py`, `do_tre_chup.py`, `loc_anh_tre.py`, `ghep_ortho_nhiet.py` | người xem (thư mục PHẢI tồn tại sẵn, không script nào `os.makedirs`) |
| 29 | `ket_qua_val\data_test_nhom.yaml` | `val_tap_test.py` | `val_tap_test.py`, **`phan_tich_recall.py`** |
| 30 | `ket_qua_val\ket_qua_test_4lop.json` | `val_tap_test.py` | báo cáo |
| 31 | `ket_qua_val\data_<bộ>.yaml`, `ket_qua_val_4lop.json` | `val_model_4lop.py` | báo cáo |
| 32 | `ket_qua_val\phan_tich_recall.json` | `phan_tich_recall.py` | báo cáo |
| 33 | `ket_qua_val\so_model_8lop.json` | `so_model_8lop.py` | báo cáo |
| 34 | `D:\...\<bộ>\{test,val}\labels.cache` | ultralytics (tác dụng phụ của 3 script val) | ultralytics |
| 35 | `fault_obb_4class.pt`, `muon_det_8class.pt`, `solar_cls4_nhom`, `solar_cls4_final_ngaunhien` | *(mồ côi — dự án annotator ổ D:)* | `val_tap_test.py`, `val_model_4lop.py`, `phan_tich_recall.py`, `so_model_8lop.py` |

---

## 3. File mồ côi — đọc mà không script nào trong dự án sinh ra

| File | Nguồn thật | Rủi ro |
|---|---|---|
| `Thermal2_31M_full_export\{cameras.xml, ortho.tif, dsm.tif, thermal_ortho.tif}` | Export tay từ Metashape | Dựng lại project Metashape = phải export lại đủ 4 file |
| ~~`manifest_anh.csv`~~ **hết mồ côi** | `tao_manifest.py` (khôi phục 11/08/2026 từ thư mục tạm, chạy lại cho ra file giống hệt từng byte) | **Chứa đường dẫn TUYỆT ĐỐI** tới `data_Thermel_2_31M` — đổi máy/ổ đĩa là `cv2.imread` trả None và 5 script vỡ. Cách chữa: chạy lại `tao_manifest.py` |
| ảnh gốc `data_Thermel_2_31M\`, `data_aligned\` | Dữ liệu bay | — |
| ~~**`tam_pin_polygon.json`**~~ **hết mồ côi** (6300 polygon) | `bo_dung_goc/tao_tam_pin_polygon.py` (khôi phục 12/08/2026) | Mất là hỏng `soi_25_ca_lech.py`; `do_tre_chup.py` vẫn chạy nhưng "kém nhạy hơn nhiều". Dựng lại được (`best.pt` trên CPU tất định), nhưng cần `loi_obb4.json` đã mất để khoanh vùng quét |
| ~~**`loi_tren_ortho_nhiet.json`**~~ **hết mồ côi** (211 lỗi) | `bo_dung_goc/quet_loi_tren_ortho.py` (khôi phục 12/08/2026) | Dựng lại được. Model 8 lớp CHỈ chạy trên ortho — trên ảnh gốc ra 0 box kể cả conf 0,02 |
| `kiem_chung_0320.json` (+0440, +0080) | Script đã xoá / làm tay | `danh_gia_chi_so.py` đọc cứng `kiem_chung_0320.json`, thiếu là crash |
| `so_sanh_model.html` (38 MB) | Không có script dựng lại | Vá hỏng thì chỉ khôi phục được từ `.bak` |
| `D:\...\RTK350.txt` | Dự án solarfarm_inspection | Thiếu thì mất dẫn đường khi chấm H, `init_matrix` = null |
| `best.pt` (53 MB, detector TẤM PIN) | solarfarm_inspection | `loc_anh_tre.py` hardcode đường dẫn `D:\...`; bản `best.pt` ở gốc dự án KHÔNG được code tự dùng, phải truyền `--model best.pt` |
| `D:\...\models\{fault_obb_4class.pt, muon_det_8class.pt}` + 2 bộ dataset | Dự án annotator | Cả khối B phụ thuộc ổ `D:\` |
| 7 khoá thêm tay trong `thermal_to_rgb.json` | Không script nào ghi | Ghi đè bằng GĐ 1 là mất vĩnh viễn |

---

## 4. Các nhánh cụt

| Script | Trạng thái | Vì sao hỏng / vì sao giữ |
|---|---|---|
| **`hieu_chuan_tu_dong.py`** | ĐÃ THỬ VÀ THẤT BẠI, banner ngay đầu file "ĐỪNG DÙNG KẾT QUẢ" | Lưới tấm pin tuần hoàn quá đều → bản đồ viền gần như hàm tuần hoàn 2 chiều, tương quan pha không phân biệt được ô này với ô kế bên. Đo trên cặp 0280: dịch ĐÚNG là (4,7; 45,3) px nhưng tương quan tại chính đó là ÂM (−0,0057); các đỉnh mạnh cách nhau đúng ~37-38 px = bước tấm pin. Là hạn chế BẢN CHẤT. `H_tu_dong.json` không ai tiêu thụ. |
| ↳ Hướng phụ #1 trong đó | Không dùng được | Ghép theo góc tấm + RANSAC bằng YOLO-OBB: RGB nhận 300 tấm conf 0,91-0,94; ảnh NHIỆT chỉ 4-10 tấm conf 0,30-0,38 (mức nhiễu). Muốn đi tiếp phải train lại detector trên ảnh nhiệt = dự án riêng. |
| ↳ Hướng phụ #2 | Chưa thử | Neo bằng vật không tuần hoàn (đường, mương, nhà trạm). Rủi ro: khung nhiệt chỉ ~15×12 m, nhiều trang trại không có đủ vật mốc. |
| **`project_box_to_ortho.py`** | KHÔNG CHẠY ĐƯỢC | (a) `from core.ortho.projection import ...` — thư mục `core/` KHÔNG tồn tại → ModuleNotFoundError ngay lúc import; (b) thiếu import `np/cv2/ET/rasterio/Transformer` dù dùng khắp nơi → NameError; (c) cả 4 đường dẫn hardcode đều sai (`cameras_v6.xml`, `full_dsm.tif`, `full_orrthor.tif` — sai chính tả, `DJI_..._0060_W.JPG`); (d) `projection_result.jpg` chưa từng được sinh ra. Theo README: "code của thầy, giữ nguyên", là demo tương tác. |
| **`H_da_bu` trong `anh_tre_chup_full.json`** | Đã thử, không cải thiện | Hằng số bù (+1,84; −3,70) px: ortho 15,5 → 14,4 cm nhưng hướng lệch ĐẢO DẤU. 31 vùng khắp nhà máy: 15 lệch lên / 16 lệch xuống (50/50), trung vị −2,0 px vs lệch trung bình 7,2 px → nhiễu cục bộ, không phải sai lệch hệ thống. **Chú ý mâu thuẫn trong chính file:** `ghi_chu` trong JSON và dòng in cuối vẫn khuyên dùng `H_da_bu` — tin khối cảnh báo đầu file, đừng tin hai câu đó. |
| **Bộ lọc EXIF `gia_toc` và `d_goc`** | Đã TẮT (mặc định `inf`) | Trên đủ 598 ảnh: `gia_toc>1` loại 150 ảnh NGƯỢC, `d_goc>3°` loại 176 ảnh NGƯỢC. Bật thêm thì mất 9-14% số ảnh mà p90 (9,38→9,42) và ảnh xấu nhất (17,52) không đổi. Bộ lọc quay đầu theo VỊ TRÍ trong `ghep_ortho_nhiet.py` cũng chạy ngược (loại 142 ảnh, x0,93). |
| **`do_tre_chup.py`** | Chạy được, kết luận là "không kết luận được" | `dang_tin=false`, ti_le_nhieu 0,286 > 0,10. Giá trị −24,8 ms là nhiễu. Có ích: đã LOẠI BỎ giả thuyết trễ chụp là nguyên nhân chính. |
| **`camera_select.py`** | Nửa vời | Chỉ in stdout, không ghi file; `quad_iou()`/`merge_detections()` không có call site trong `main()`. |
| **`ortho_nhiet_can_sang.tif` / `ortho_nhiet_bu_anh.tif`** | Không tồn tại | `do_khop_ortho.py` in "thieu \<file\>" rồi bỏ qua → hiện chỉ đo được "ban goc", `len(ket)==1`, toàn bộ phần so sánh giữa các bản bị bỏ. Ngoài ra nếu có đúng 2 bản mà thiếu "can sang" thì **KeyError** ở dòng 116-117. |

---

## 5. Đường tới hạn — chuỗi ngắn nhất từ ảnh thô tới danh sách lỗi có mã tấm pin

```
[GĐ 0] cameras.xml + ortho.tif + dsm.tif (Metashape)
       manifest_anh.csv + ảnh _T/_W + best.pt + tam_pin_polygon.json
                    │
                    ▼
[1] calib_thermal_rgb.py ────────────────► thermal_to_rgb.json      (chấm tay, 1 lần / model drone)
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
[2] loc_anh_tre.py          [3] loc_anh_rung.py
    --out anh_tre_chup_full.json    ──► anh_rung.json + exif_bay.json
    (~44 phút)                          (~1 phút)
        └───────────┬───────────┘
                    ▼
[4] ghep_ortho_nhiet.py ─────────────────► ortho_nhiet_tu_lam.tif
                    │
                    ▼
[7] ✗ KHUYẾT: detect lỗi → chiếu → gom cụm → gán mã tấm
                    │              (không có script; loi_tren_ortho_nhiet.json phải có sẵn)
                    ▼
              loi_tren_ortho_nhiet.json   ◄── SẢN PHẨM CUỐI
```

**Đường tới hạn = 4 lệnh** (giả định `loi_tren_ortho_nhiet.json` đã có sẵn hoặc GĐ 7 được viết lại):

```bash
python ma/calib_thermal_rgb.py --thermal data_aligned/thermal/DJI_..._0280_T.JPG \
       --rgb data_aligned/rgb/DJI_..._0280_W.JPG \
       --xml Thermal2_31M_full_export/cameras.xml --alt 31        # chấm tay, bấm S
python ma/loc_anh_tre.py --out anh_tre_chup_full.json                 # ~44 phút
python ma/loc_anh_rung.py                                             # ~1 phút
python ma/ghep_ortho_nhiet.py                                         # dựng ortho nhiệt
```

**Ràng buộc thứ tự không thể đảo:**
- (1) trước tất cả — 5 script sau đều cần `thermal_to_rgb.json`.
- (2) và (3) song song được, nhưng cả hai phải xong trước (4).
- (2) phải dùng `--out anh_tre_chup_full.json` đúng tên, nếu không (4) và (12) đọc hụt.
- `kiem_tra_warp/` phải tồn tại sẵn trước khi chạy (2)/(4)/`do_tre_chup.py` — không script nào tự tạo, `cv2.imwrite` thất bại lặng lẽ.
- (9) trước (10) trong khối viewer; (11a) trước (11b) trong khối model.

**Bỏ được khỏi đường tới hạn:** `do_khop_ortho.py`, `do_sai_so_ortho.py`, `do_tre_chup.py`, `soi_25_ca_lech.py`, `danh_gia_chi_so.py`, `xuat_nen_net.py`, `va_viewer_net.py`, `camera_select.py`, cả khối B (`val_*`, `phan_tich_recall`, `so_model_8lop`) — đều là QC / đo đạc / trình bày, không sinh ra dữ liệu mà bước sau cần.

---

## Phụ lục — script ở gốc dự án NGOÀI phạm vi 18 file đã kiểm chứng

Chưa đọc code, chưa xác minh quan hệ file. Liệt kê để người mới không tưởng chúng nằm ngoài dự án:

`do_lech_metashape.py`, `do_lech_ortho_nhiet.py`, `do_recall_theo_nguong.py`, `doc_nhiet_raw.py`, `dong_goi.py`, `lam_slide_thuat_ngu.py`, `so_ortho_nhiet.py`, `soi_loi_bi_bo.py` (đọc `loi_tren_ortho_nhiet.json`), `thu_detect_tren_ortho.py`, `va_viewer_ngoai_nen.py` (vá cùng `so_sanh_model.html`), `xuat_pdf.py`, `_anh_pipeline.py`, `_hinh_ve.py`.

Thư mục `ket_qua_val/_conf/`, `pr_theo_conf.json`, `recall_theo_nguong.json` có trên đĩa nhưng **không** do `phan_tich_recall.py` sinh — nhiều khả năng do `do_recall_theo_nguong.py`.