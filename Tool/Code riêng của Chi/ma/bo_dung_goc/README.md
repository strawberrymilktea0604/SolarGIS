# Bộ dựng gốc — khôi phục từ thư mục tạm

Các file trong đây **đã sinh ra `tam_pin_polygon.json` và `so_sanh_model.html`**.
Bản gốc chạy từ scratchpad của phiên `19f336a5` ngày 10/08/2026 nên không nằm
trong dự án — vì thế tài liệu cũ ghi nhầm là "không có script dựng".
Khôi phục ngày 12/08/2026, **giữ nguyên nội dung, chỉ đổi tên cho dễ hiểu**.

| File ở đây | Tên gốc | Chạy lúc | Sinh ra |
|---|---|---|---|
| **`quet_loi_tren_ortho.py`** | `quet_ortho_nhiet.py` | 10/08 16:57 | **`loi_tren_ortho_nhiet.json`** (211 lỗi) — bước ⑦ |
| **`gan_loi_vao_tam_pin.py`** | `gan_211.py` | 10/08 17:09 | gán mã tấm + `in_panel`/`iou`/`dist_cm` |
| `tao_tam_pin_polygon.py` | `lam_lai_polygon.py` | 10/08 21:01 | `tam_pin_polygon.json` (6300 polygon) |
| `kiem_tam_pin_polygon.py` | `soi_polygon.py` | 10/08 21:00 | — (kiểm kích thước + chồng lấn) |
| `viewer_khuon.html` | `viewer4m.html` | 10/08 21:19 | khuôn HTML của `so_sanh_model.html` |
| `tao_viewer_data.py` | `data_4model.py` | 10/08 18:13 | `viewer_data_4model.json` |
| `tinh_lai_khung_viewer.py` | `sua_khung.py` | 10/08 21:16 | ghi `frame` vào viewer data |
| `them_polygon_vao_viewer.py` | `them_polygon.py` | 10/08 20:43 | thêm polygon vào viewer data |

---

## 0. Bước ⑦ — hết "mắt xích đứt"

Tài liệu cũ ghi *"không script nào sinh ra `loi_tren_ortho_nhiet.json`"*. Sai —
script vẫn còn, chỉ nằm ở scratchpad. `quet_loi_tren_ortho.py`:

- Chạy **`thermal_solar_anomaly.pt`** (model 8 lớp của thầy) trên
  `ortho_nhiet_tu_lam.tif`, cửa sổ trượt **640 px, chồng lấn 30%**, `conf 0.25`.
- Cửa sổ đúng 640 px vì đó là **kích thước ảnh nhiệt gốc** — quét cửa sổ to hơn
  rồi thu nhỏ thì tấm pin nhỏ hơn lúc train, model detect kém.
- Bỏ cửa sổ có dưới 35% pixel khác 0 (gần như trống).
- Gộp trùng giữa các cửa sổ bằng IoU ≥ 0,30 → còn **211 lỗi**.
- `lon/lat` = tâm box, quy từ pixel ortho nhiệt.

`gan_loi_vao_tam_pin.py` chạy tiếp: quét `best.pt` tìm tấm pin ở các ô có lỗi,
rồi gán `panel_code`, `in_panel`, `iou`, `dist_cm` vào từng lỗi.

> **Model 8 lớp CHỈ chạy được trên ortho.** Đã thử trên ảnh nhiệt gốc: **0 box**,
> kể cả khi hạ conf xuống 0,02 và phóng ảnh 0,5–3×. Cùng model đó quét cửa sổ
> ortho ra 111 box/20 cửa sổ. Ngược lại, `fault_obb_4class.pt` (4 lớp, model của
> bạn) chạy tốt trên ảnh gốc — 115 box/12 ảnh. Hai model train trên hai loại dữ
> liệu khác nhau. Đây là lý do bước ⑦ phải quét ortho, không phải lựa chọn.
>
> Xem `quet_loi_anh_le.py` ở thư mục gốc — bản đối chứng chạy trên ảnh lẻ.

---

## 1. `tam_pin_polygon.json` sinh thế nào

`tao_tam_pin_polygon.py` chạy **`best.pt` quét chính ảnh ortho màu**, không phải
ảnh gốc:

- Cắt ortho thành cửa sổ 2048 px, chồng lấn 20%, thu nhỏ 2 lần (còn 1,91 cm/px —
  tỉ lệ mà model khoanh đúng tấm pin). `conf=0.35`, `max_det=900`.
- Chỉ quét vùng có lỗi + lề 900 px, không quét cả trang trại.
- Bỏ hộp chạm biên cửa sổ (bị cắt) — sẽ lấy lại từ cửa sổ kế bên.
- Lọc theo kích thước thật: cạnh ngắn 0,6–1,3 m, cạnh dài 1,4–2,3 m.
- Khử trùng lặp giữa các cửa sổ: tâm cách nhau < 45 px thì giữ hộp lớn hơn.

Ra **6300 polygon**, mỗi cái 4 đỉnh × 2 toạ độ, đơn vị **pixel của `ortho.tif`**.

> **Tất định — đã kiểm.** Chạy `best.pt` hai lần trên cùng một cửa sổ ortho ra
> **113 hộp, toạ độ giống hệt, lệch 0,00 px**. Máy này dùng `torch 2.13.0+cpu`,
> không có CUDA, nên không dính chuyện GPU sai số. Cùng đầu vào → cùng đầu ra.

**Rào cản thật khi chạy lại:** script đọc `loi_obb4.json` + `loi_tren_ortho_nhiet.json`
để biết vùng cần quét (chỉ quét quanh chỗ có lỗi + lề 900 px, không quét cả trang
trại). `loi_obb4.json` **không còn trên đĩa** — phải sửa phần khoanh vùng trước.

Vẫn nên cân nhắc trước khi chạy lại: nếu vùng quét đổi thì số polygon đổi, và mã
tấm `D01-T001` đánh số lại theo thứ tự hàng/cột — kết quả đã báo cáo sẽ lệch.

## 2. `so_sanh_model.html` dựng thế nào

Hai bước, không phải một:

1. `tao_viewer_data.py` → `viewer_data_4model.json` (85 MB): cắt ảnh quanh từng
   lỗi ở cả ortho màu lẫn ortho nhiệt, nhúng base64, gán mã tấm bằng
   `pointPolygonTest` vào `tam_pin_polygon.json`.
2. Bơm JSON đó vào chỗ giữ chỗ `/*__DATA__*/` trong `viewer_khuon.html` bằng
   PowerShell `[IO.File]::WriteAllText(...Replace('/*__DATA__*/', ...))`.

`viewer_khuon.html` là khuôn rỗng 15,8 KB — toàn bộ 38 MB còn lại là dữ liệu.

> **File `so_sanh_model.html` hiện tại KHÔNG dựng lại được từ bộ này.** Sau khi
> dựng, nó đã bị vá nhiều lần: đổi sang SVG polygon, gắn nền nét (`va_viewer_net.py`),
> đánh dấu lỗi ngoài nền (`va_viewer_ngoai_nen.py`), cập nhật `in_panel`, và
> **rút từ 4 model xuống 2 model**. Khuôn giữ 32/33 đoạn đặc trưng của file thật,
> đủ để đọc hiểu cấu trúc — không đủ để tái tạo.
>
> Muốn sửa viewer thì **vẫn vá chuỗi** như `va_viewer_net.py` đang làm. Khuôn này
> dùng để *hiểu* JS/CSS đang chạy, không phải để dựng lại.

`tao_viewer_data.py` cũng đọc `loi_obb4/5/6.json` — cả ba đều **không còn trên
đĩa**, chỉ còn `loi_tren_ortho_nhiet.json`.
