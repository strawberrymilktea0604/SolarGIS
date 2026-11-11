# ĐỌC TÔI — bản *core* để chạy thử

Bản rút gọn của dự án **Định vị lỗi tấm pin từ ảnh nhiệt drone**
(gốc: `1008-stage1-rgb-thermal`, 25 GB). Bản này **242 MB**: giữ mã nguồn, model,
ma trận hiệu chuẩn và toàn bộ giao diện HTML — **không kèm dữ liệu bay**.

Đọc `README.md` để hiểu dự án làm gì. File này chỉ nói: bản copy này có gì,
thiếu gì, và bấm vào đâu thì thấy chạy.

---

## Bấm là chạy — không cần cài gì

Phần giao diện đã nhúng sẵn ảnh nền, mở bằng trình duyệt là xem được ngay:

| Mở file | Là cái gì |
|---|---|
| `index.html` | trang chủ, dẫn vào mọi thứ bên dưới |
| `cong_cu/so_sanh_model.html` | so 2 model trên cùng một ảnh, ảnh đã nhúng sẵn (37 MB) |
| `cong_cu/gan_nhan_tam.html` | công cụ gán nhãn tay theo từng tấm pin |
| `cong_cu/can_tay.html` | căn tay độ lệch nhiệt ↔ RGB cho 29 ảnh máy đo hỏng |
| `cong_cu/soi_mau_recall.html` | soi mẫu để đo recall |
| `cong_cu/soi_tay_100_loi.html` | soi 100 lỗi bằng mắt (15 MB, ảnh nhúng sẵn) |
| `tai_lieu/DANH_GIA_THEO_NHAN.html` | notebook đánh giá model bằng nhãn tay |
| `tai_lieu/slide_thuat_ngu.html` | slide thuật ngữ |

> **Mở bằng cách bấm đúp (giao thức `file://`), đừng chạy qua http server.**
> Nhãn gán tay lưu trong `localStorage` — kho này gắn theo *origin*, mở kiểu khác
> là sang kho khác, nhãn cũ coi như biến mất.

## Chạy mã Python

```bash
pip install -r yeu_cau.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

Chạy **từ thư mục gốc** của bản copy này, không phải từ trong `ma/`:

```bash
py -3.13 ma/<ten_script>.py
```

Thử ngay không cần dữ liệu bay — nạp model và chạy trên một ảnh bất kỳ của bạn:

```python
from ultralytics import YOLO
YOLO("mo_hinh/fault_obb_4class.pt").predict("anh_nhiet_cua_ban.JPG", save=True)
```

Còn nguyên chuỗi xử lý chính (`ma/ghep_ortho_nhiet.py`, `ma/quet_loi_anh_le.py`,
`ma/gan_tam_pin_4lop.py`…) — nhưng phải có dữ liệu, xem mục dưới.

---

## Có gì trong bản này

```
ma/            93 script — toàn bộ mã nguồn, không cắt gì
mo_hinh/       fault_obb_4class.pt  model lỗi 4 lớp OBB — model CHÍNH
               best.pt              model dò tấm pin (1 lớp)
               RTK350.txt           ma trận H khởi tạo cho calib_thermal_rgb.py
ket_qua/       thermal_to_rgb.json  ← MA TRẬN H, phần lõi tái dùng được
               + các .json kết quả của lần chạy này (6 MB)
cong_cu/       giao diện HTML + nhan/ net/ (ảnh nền đã nhúng, 154 MB)
trang/ index.html    trang chủ và ảnh minh hoạ
tai_lieu/      tài liệu .md + 2 trang HTML mà trang chủ trỏ tới
yeu_cau.txt    danh sách thư viện
```

## Đã cắt gì

| Cắt | Nặng | Lấy lại kiểu gì |
|---|---:|---|
| `du_lieu/` — ảnh gốc, ortho + DSM + `cameras.xml` của Metashape | 24 GB | xin bản gốc, hoặc cắm dữ liệu của bạn vào |
| `ket_qua/ortho/` — 4 bản ortho nhiệt `.tif` | 61 MB | `ma/ghep_ortho_nhiet.py` dựng lại |
| `ket_qua/ket_qua_val/`, `runs/`, `kiem_tra_warp/` | 42 MB | chạy lại nhóm script `val_*` |
| `luu_tru/` — file chết đã gom | 103 MB | không cần |
| `tai_lieu/bai_bao_lien_quan/` + PDF, hình lớn, slide nặng | 700 MB | không cần để chạy |
| `mo_hinh/thermal_solar_anomaly.pt` — model 8 lớp | 21 MB | **nhánh đã bỏ**, chỉ 3 script cũ trong `ma/bo_dung_goc/` gọi tới |

## Hai điểm khác bản gốc — phải biết

**1. Đường dẫn model đã sửa cho tự đứng được.** Bản gốc ghi cứng
`D:\Remote_Project\solar-thermal-fault-annotator\models\fault_obb_4class.pt` —
gọi chéo sang 2 dự án khác trên máy tác giả. Bản này đã đổi 28 file sang đường dẫn
tương đối (`mo_hinh\fault_obb_4class.pt`), model đã chép sẵn vào `mo_hinh/`, nên
chép thư mục đi đâu cũng chạy. Đã thử nạp cả 2 model từ chính bản copy này: chạy được.

**2. Đừng chạy `ma/lam_trang_chu.py` ở bản này.** Nó dựng lại `index.html` bằng
cách quét đĩa xem có sản phẩm nào — bản này thiếu dữ liệu nên sẽ **xoá mất thẻ**
trên trang chủ. Mấy script `lam_*.py`, `va_*.py`, `hinh_*.py` cũng vậy: chúng dựng
lại giao diện/hình từ dữ liệu, thiếu dữ liệu thì ra bản rỗng.

## Nhóm script nào cần gì

| Nhóm | Cần |
|---|---|
| `calib_thermal_rgb.py` — chấm H nhiệt→RGB | 1 cặp ảnh `_T/_W` + `cameras.xml`; chấm tay 1 lần cho mỗi model drone |
| `ghep_ortho_nhiet.py`, `loc_anh_*.py` | cả bộ ảnh bay + ortho/DSM/cameras.xml |
| `quet_loi_anh_le.py`, `gan_tam_pin_4lop.py` | ảnh nhiệt gốc + ortho + `thermal_to_rgb.json` (đã có sẵn) |
| `val_*.py`, `danh_gia_*.py`, `do_recall_*.py` | tập test YOLO — đặt vào `du_lieu/colab/solar_cls4_nhom/` |
| `hinh_*.py`, `lam_*.py`, `va_*.py`, `xuat_*.py` | dựng hình/tài liệu — cần dữ liệu, xem cảnh báo (2) |

> Con số cần trích đúng: sai số khớp ortho **RMSE 2,56 cm** là sai số **tương đối**
> (ortho nhiệt so ortho màu), không phải sai số GPS tuyệt đối. mAP 0,965 trong báo
> cáo cũ đo trên tập có 81 % ảnh nằm trong train; số sạch kỳ vọng khoảng **0,70**.
> Chi tiết ở đầu `README.md`.
