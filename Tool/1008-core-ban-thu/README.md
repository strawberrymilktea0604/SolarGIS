# Định vị lỗi tấm pin từ ảnh nhiệt drone

Đưa lỗi phát hiện trên **ảnh nhiệt** ra **toạ độ GPS + mã tấm pin** trên orthophoto.
Sai số **tương đối** đo được: **RMSE 2,56 cm** (ngưỡng đề bài 30 cm).

> **Hai điều phải nói kèm khi trích số.**
> **(1)** 2,56 cm là độ khớp giữa ortho nhiệt và ortho màu — hai sản phẩm dựng từ cùng
> một khối ảnh. `cameras.xml` có **0 GCP**, `accuracy_cameras = 10 m`, nên sai số GPS
> **tuyệt đối** chưa đo được và bị chặn bởi GPS drone (~1–5 m nếu không RTK).
> **(2)** mAP@50 = 0,965 trong báo cáo đo trên tập mà **81 % ảnh nằm trong train** của
> model (lệch bộ chia — model train trên `solar_cls4_final_ngaunhien`, báo cáo đo trên
> `solar_cls4_nhom/test`). Số trên tập held-out thật là 0,974; kỳ vọng ở trang trại chưa
> từng bay khoảng **0,70**. Chạy `danh_gia_lai.py` để xem lại.

Dữ liệu đang có: trang trại Thuận Nam, bay 31 m, 598 cặp ảnh nhiệt–RGB (DJI ZH20T).

---

## Cấu trúc thư mục

```
index.html          trang chủ — mở thẳng bằng trình duyệt, dựng bằng ma/lam_trang_chu.py
ma/                 toàn bộ script. Chạy từ GỐC dự án: py -3.13 ma/<script>.py
  goc.py            1 dòng `import goc` là script đứng ở gốc dự án
  bo_dung_goc/      bộ dựng gốc khôi phục từ scratchpad — giữ nguyên bản, đường dẫn cũ
du_lieu/            ảnh gốc + sản phẩm Metashape (23 GB, ngoài git) + manifest, EXIF,
                    danh sách ảnh đã lọc
ket_qua/            *.json kết quả, thermal_to_rgb.json (ma trận H), ket_qua_val/,
                    runs/, kiem_tra_warp/
  ortho/            4 bản ortho nhiệt .tif (ngoài git)
cong_cu/            công cụ xem/gán nhãn dạng HTML + nhan/ net/ (ảnh nền) + nhan_cuu/
tai_lieu/           *.md, *.pdf, notebook, slide, hình minh hoạ
mo_hinh/            best.pt
luu_tru/            file chết đã gom, `python ma/dong_goi.py --hoan-tac` để lấy lại
```

**Đường dẫn trong code tính từ gốc dự án**, không phải từ thư mục chứa script:
`os.path.join(BASE, "ket_qua/thermal_to_rgb.json")`. Script nào dùng tên file trần
theo thư mục hiện hành thì có `import goc` ở đầu để đứng đúng chỗ.

**Đừng tách `cong_cu/` ra khỏi `nhan/` và `net/`.** Các trang HTML trỏ vào hai thư
mục này bằng đường dẫn tương đối của trình duyệt (`nhan/nen_rgb.jpg`) — rời nhau là
trang trắng.
---

## Cái gì tái dùng được, cái gì không

Đây là điều cần nắm trước khi mang sang trang trại khác:

| | Gắn với | Dùng lại được? |
|---|---|---|
| **Ma trận H nhiệt→RGB** (`thermal_to_rgb.json`) | **thiết bị** (model drone) | **Có** — chấm tay một lần cho mỗi model drone, dùng cho mọi trang trại |
| Toàn bộ script trong `ma/` | không gắn gì | **Có** |
| `Thermal2_31M_full_export/`, `data_*` | trang trại + chuyến bay | Không — thay bằng dữ liệu mới |
| `ket_qua_val/`, `*.json` kết quả, ortho | lần chạy này | Không |

Nói cách khác: **H là phần lõi**. Chấm tay 31 cặp điểm một lần, dùng được cho hàng nghìn
trang trại miễn là cùng model drone. Đừng chấm lại cho từng trang trại.

> **Đừng thử tự động hoá việc chấm H bằng tương quan pha hay ghép góc tấm pin.**
> Cả hai đã thử và hỏng vì lý do bản chất — lưới tấm pin tuần hoàn quá đều, và detector
> tấm pin không chạy được trên ảnh nhiệt. Chi tiết ghi ở đầu `hieu_chuan_tu_dong.py`.

---

## Chạy cho một trang trại mới

```bash
# 1. Dựng ortho + DSM + cameras.xml bằng Metashape từ ảnh RGB, xuất vào một thư mục
#    (thay cho Thermal2_31M_full_export/)

# 2. Chấm H — CHỈ LÀM MỘT LẦN CHO MỖI MODEL DRONE, có H rồi thì bỏ qua bước này
python ma/calib_thermal_rgb.py --thermal ..._T.JPG --rgb ..._W.JPG --xml cameras.xml --alt 31

# 3. Lọc ảnh chụp lúc drone không bay đều
python ma/loc_anh_tre.py          # đo trực tiếp, ~45 phút cho 598 ảnh — bộ lọc tốt nhất
python ma/loc_anh_rung.py         # đọc EXIF, 3 giây

# 4. Dựng ortho nhiệt toàn nhà máy (đã tự nối hai bộ lọc trên)
python ma/ghep_ortho_nhiet.py

# 5. Chạy model phát hiện lỗi trên TỪNG ẢNH GỐC, chiếu lên ortho, gộp trùng
python ma/quet_loi_anh_le.py      # -> loi_tu_anh_le.json
python ma/gan_tam_pin_4lop.py     # gán mã tấm pin -> loi_4lop_cuoi.json  ĐẦU RA CHÍNH

# 6. Đo và xuất báo cáo
python ma/danh_gia_chi_so.py
python ma/xuat_pdf.py
```

**Chỉ dùng một model lỗi: `fault_obb_4class.pt` (4 lớp OBB).** Trước đây có hai nhánh
song song — nhánh cũ quét `thermal_solar_anomaly.pt` (8 lớp) thẳng trên ortho nhiệt ra
`loi_tren_ortho_nhiet.json` (211 lỗi). Đã bỏ: cùng bộ test đó model 8 lớp chỉ bắt
**45,7 %** lỗi và gán đúng lớp 22,9 %, trong khi model 4 lớp bắt 97,5 %. Mọi con số
mAP/precision/recall trong báo cáo đều là của model 4 lớp, nên để nhánh 8 lớp làm đầu ra
là gán số của model này cho model kia. Nhánh mới tìm lại được **205/211** lỗi của nhánh
cũ (trong bán kính 1 m) và thêm 398 lỗi nữa.

### Căn tay lệch nhiệt ↔ RGB

```bash
py -3.13 ma/lam_can_tay.py                 # 111 ảnh: bị loại vì lệch + phép đo bó tay
py -3.13 ma/lam_can_tay.py --nhom kho      # 29 ảnh phép đo tự động bó tay — đáng làm nhất
py -3.13 ma/ghep_ortho_nhiet.py --lech-tay can_tay.json    # dựng lại ortho bằng số căn tay
```

`loc_anh_tre.py` đo `dx, dy` từng ảnh bằng cách chiếu viền tấm pin qua H rồi trượt
tìm chỗ khớp trong bán kính 16 px. Phép đo đó hỏng ở **29 ảnh** và không tự sửa được:

| | |
|---|---:|
| **chạm mép** — lệch thật > bán kính trượt, số ghi ra là số kẹp | 21 |
| **`do_net` < 0,5** — đỉnh khớp không nổi, số ghi ra là nhiễu | 8 |

Công cụ chồng viền tấm pin (chiếu qua H) lên ảnh nhiệt, người căn **kéo một lần**
cho tới khi khít lưới. Chỉ cần một phép tịnh tiến — H là của **model drone**, cố
định; cái thay đổi theo từng ảnh chỉ là độ trễ màn trập. Ảnh nào máy đo tốt thì
nạp sẵn số máy làm vị trí xuất phát, người căn chỉ xác nhận.

> 29 ảnh khó phần lớn là **ảnh mép trang trại**, ít lưới tấm để bám — đó vừa là lý
> do máy hỏng vừa là chỗ người căn cũng vất. Ảnh nào không căn nổi thì bấm `X`,
> nó vào `anh_nen_loai` của `can_tay.json` và bị loại hẳn.

`--lech-tay` **ghi đè** phép đo tự động chứ không cộng dồn (khác `--bu-rgb`): người
căn đo lại đúng đại lượng mà `loc_anh_tre.py` đo, cộng hai lần là bù gấp đôi.

### Gán nhãn tay theo tấm pin

```bash
py -3.13 ma/lam_gan_nhan_tam.py     # -> gan_nhan_tam.html + nhan/ (~19 MB ảnh nền)
```

Model chỉ làm bước **gợi ý sẵn**; người gán nhãn chốt lại. Vị trí phán trên ortho
**màu** (mới đọc được mép tấm, hàng, cột), có lỗi thật hay không phán trên ortho
**nhiệt** (vệt nóng chỉ hiện ở đó). Hai lớp gạt qua lại tại chỗ vì
`ortho_nhiet_bu_rgb.tif` cùng góc trên-trái với `ortho.tif` và bước pixel gấp
**đúng 3 lần** — chồng lên nhau không cần nắn gì thêm.

**Nút *Ẩn rìa* (phím `B`), bật sẵn.** Rìa nhà máy có ảnh màu mà không có ảnh nhiệt
— thấy tấm pin nhưng không phán được gì. Bộ dựng đo hộp bao của khối tấm **có**
nhiệt và gắn cờ `ria` cho từng tấm; công cụ phủ mờ phần ngoài, bỏ tấm rìa khỏi mọi
danh sách, và *vừa khung* căn theo vùng lõi.

```
ẩn rìa          hiện rìa
  5632            6473    tấm trên bản đồ      (841 tấm ở rìa)
   224            1065    tấm thiếu nhiệt
   496             496    tấm model đánh dấu   (không mất tấm nào)
```

Dữ liệu **luôn dựng đầy đủ**, nút chỉ đổi cách hiển thị — bật tắt tại chỗ, không
phải dựng lại. Cắt cứng lúc dựng thì mỗi lần đổi ý mất 10 giây và mất luôn khả
năng ngó ra ngoài xem có gì.

> **224 tấm còn lại vẫn không đủ ảnh nhiệt để phán.** Chúng **không phải "tấm
> tốt", mà là "chưa soi được"** — công cụ tô xám, tách sang tab riêng *Thiếu
> nhiệt*, loại khỏi tab *Chưa xét*. Mọi nhãn xuất ra đều kèm `phu_nhiet` (% diện
> tích có dữ liệu nhiệt) và `phan_duoc`; lọc `phan_duoc == false` trước khi tính
> bất kỳ chỉ số nào. Sau khi cắt rìa, phần lớn nhóm này (119/224) là **moi lại
> được từ ảnh đã bị loại**, chỉ 102 tấm phải bay lại.
>
> **"Ortho nhiệt không có" khác "ảnh nhiệt không có"** — ortho chỉ dựng từ 396/598
> ảnh đạt bộ lọc. Chiếu ngược tâm từng tấm vào cả 598 camera (`nguon_nhiet`),
> trong 224 tấm thiếu nhiệt còn lại sau khi cắt rìa:
>
> | | | |
> |---|---:|---|
> | `0` không ảnh nào chụp tới | 102 (45,5%) | chỉ bay lại mới soi được |
> | `1` chỉ ảnh đã bị loại thấy | **119** (53,1%) | moi lại được, nhưng ảnh trễ chụp/rung |
> | `2` ảnh đạt lọc vẫn thấy | 3 (1,3%) | ortho bỏ sót, vá được |
>
> Đối chứng: 5406/5408 tấm CÓ ortho nhiệt đều được ảnh đạt lọc nhìn thấy, trung vị
> 6 ảnh/tấm — phép chiếu ngược đúng. Trước khi cắt rìa con số là 938 tấm phải bay
> lại; **841 trong đó nằm ở rìa và đã bị cắt bỏ**, vì soi ở đó cũng không phán
> được gì.

**Xén lớp màu theo vùng phủ nhiệt là TUỲ CHỌN**, và bản đang dùng là bản **không
xén** (`--khong-cat-theo-nhiet`). Bật `--cat-theo-nhiet` thì lớp màu bị tô đen ở
chỗ không có nhiệt (bỏ 29,0% khung, hai lớp còn đúng một vùng phủ, chênh 0,02%).

Xén hay không **không đụng gì tới hình học** — cùng cửa sổ `c0=932 r0=1282`,
cùng tỉ lệ 2,65 cm/px, độ khớp nhiệt↔màu qua H giữ nguyên. Nó chỉ đổi việc tô đen
mấy pixel màu ở vùng không có nhiệt. Chọn theo ý người soi: xén thì đỡ tưởng nhầm
vùng chưa kiểm là đã kiểm, không xén thì thấy được toàn cảnh nhà máy.

**Khung nhiệt xem được cả ảnh gốc.** Model detect trên **ảnh nhiệt gốc** rồi mới
chiếu lên ortho, mà ortho chỉ ghép từ **396/416** ảnh detect chạy qua (loại thêm
142 ảnh quay đầu). Nên **14/603 lỗi (2,3%)** chỉ thấy được từ 20 ảnh không vào
ortho — trên ortho chúng nằm giữa vùng đen, tưởng là báo động khống. Công cụ cắt
sẵn khung ảnh gốc cho 619 tấm (`nhan/goc/`), nút *xem ảnh gốc* hoặc phím `G`;
tấm nào ortho trống thì **tự mở ảnh gốc** trước.

> Viền tấm vẽ trên ảnh gốc thừa hưởng sai số đặt chỗ của chính ảnh đó. Với ảnh
> **đã bị loại** (nhãn cam trong khung) viền lệch thấy rõ — soi theo nghĩa "quanh
> viền này có vệt nóng không", đừng đòi vệt nóng nằm gọn trong viền.

Nhãn gắn vào **tấm pin**, đầu ra là bảng `mã tấm → tình trạng`
(`nhan_tam_pin.json` / `.csv`, tải từ trong trang). 496/6473 tấm được model đánh
dấu sẵn — đó là danh sách mặc định phải duyệt; 5977 tấm còn lại mở ra để bắt ca
model **bỏ sót**. Bấm dở dang không mất: tự lưu localStorage, nút *Nạp lại* để
mở tiếp file đã tải ra.

> Box của model bao **gần trọn một tấm pin** (trung vị 0,95 × 1,85 m so với tấm
> 0,88 × 1,76 m, IoU 0,716), chứ không khoanh riêng ô nóng. Tức model vốn đã phán
> ở mức tấm — đúng đơn vị đang gán nhãn. Đừng đọc dấu tâm box như vị trí ô lỗi.

Bốn lớp của model là `SingleHotSpot` · `MultiHotSpot` · `Bypass` ·
**`ModuleOpenCircuit`**. Lớp thứ tư ra **0 phát hiện** trên bộ Thuận Nam, nên mọi
bảng thống kê chỉ thấy ba lớp — công cụ gán nhãn vẫn để nút cho nó, để người soi
gặp thì gán đúng tên lớp của model thay vì dồn vào "Lỗi khác".

**Ngưỡng conf chốt là 0,25** — không đổi. Đẩy lên 0,64 (tối ưu F1) thì mất **146/603**
lỗi mà chất lượng chỉ nhích 2 điểm; trong 146 cái mất đi có **129 cái rơi đúng trong tấm
pin**, tức cứ dọn 1 box ngoài tấm pin thì vứt nhầm 7,6 lỗi thật.

---

## Bản đồ thư mục

**Script** — tất cả nằm ở gốc, mỗi cái tự tìm dữ liệu cạnh nó:

| Nhóm | Script | Việc |
|---|---|---|
| Hiệu chuẩn | `calib_thermal_rgb.py` | Chấm tay H nhiệt→RGB, có dẫn đường |
| | `hieu_chuan_tu_dong.py` | **ĐÃ HỎNG** — giữ lại để không thử lại hướng này |
| Lọc ảnh | `loc_anh_tre.py` · `loc_anh_rung.py` · `do_tre_chup.py` | Loại ảnh trễ chụp / drone rung |
| Ortho | `ghep_ortho_nhiet.py` | Dựng ortho nhiệt toàn nhà máy |
| | `project_box_to_ortho.py` | Chiếu box từ ảnh drone lên ortho — **code của thầy, giữ nguyên** |
| | `camera_select.py` | Chọn ảnh đúng để chiếu + khử trùng lặp |
| Lỗi | `quet_loi_anh_le.py` | Detect trên ảnh gốc → chiếu → gộp trùng |
| | `gan_tam_pin_4lop.py` | Gán mã tấm pin cho đầu ra 4 lớp |
| Gán nhãn tay | `lam_gan_nhan_tam.py` | Dựng `gan_nhan_tam.html` — gán nhãn TAY theo tấm pin |
| | `lam_can_tay.py` | Dựng `can_tay.html` — căn TAY lệch nhiệt↔RGB từng ảnh |
| Đánh giá | `danh_gia_chi_so.py` | Toàn bộ chỉ số định vị, gán tấm pin, khử trùng lặp |
| | `danh_gia_lai.py` | mAP/P/R có IoU đa giác xoay, bootstrap KTC, soi rò rỉ tập chia |
| | `val_tap_test.py` · `val_model_4lop.py` | Val model trên tập test / val |
| | `phan_tich_recall.py` | Tách "bỏ sót" khỏi "gán nhầm lớp" |
| | `so_model_8lop.py` | So model 4 lớp với model mượn 8 lớp |
| | `do_sai_so_ortho.py` | Đo sai số end-to-end bằng đối chứng tay |
| Báo cáo | `xuat_pdf.py` | Markdown → PDF |
| | `xuat_nen_net.py` · `va_viewer_net.py` | Ảnh nền độ phân giải gốc cho viewer |
| Dọn dẹp | `dong_goi.py` | Gom file chết vào `luu_tru/`, `--hoan-tac` để trả lại |

**Dữ liệu đang dùng** (script đọc trực tiếp, đừng di chuyển):

- `thermal_to_rgb.json` — **H đang dùng**
- `Thermal2_31M_full_export/` — ortho, DSM, cameras.xml của Metashape
- `manifest_anh.csv` · `exif_bay.json` — danh mục ảnh và dữ liệu bay
- `anh_tre_chup_full.json` · `anh_rung.json` — kết quả lọc ảnh
- `ortho_nhiet_tu_lam.tif` — ortho nhiệt tự ghép (8451 × 4997)
- `loi_4lop_cuoi.json` — **603 lỗi, đầu ra chính** (model 4 lớp, đã gán mã tấm pin)
- `tam_pin_polygon_4lop.json` — 6473 polygon tấm pin để gán mã. Mã tấm (`D20-T131`)
  **không nằm trong file này** — nó được sinh lại từ vị trí polygon, cùng một đoạn
  code ở `gan_tam_pin_4lop.py` và `lam_gan_nhan_tam.py`. Sửa một bên là lệch mã
- `nhan/` — hai lớp nền của công cụ gán nhãn (8192 × 3581, 2,65 cm/px), đi kèm
  `gan_nhan_tam.html`, tách rời là trang trắng
- `loi_tu_anh_le.json` — bước trung gian, chưa có mã tấm pin
- `loi_tren_ortho_nhiet.json` · `tam_pin_polygon.json` — nhánh 8 lớp cũ, giữ để đối chứng
- `sai_so_end_to_end.json` · `kiem_chung_*.json` — số liệu sai số

**Báo cáo:**

- `TOM_TAT_KET_QUA.pdf` — 1 trang 1 bảng, gửi cho người cần con số
- `BAO_CAO_DANH_GIA.pdf` — 10 trang, đầy đủ cách đo và cảnh báo
- `HUONG_DAN_PIPELINE.pdf` — mô tả pipeline
- `YEU_CAU_BAI_TOAN.pdf` — đề bài

Hai file `.md` phải nằm ở gốc vì nhúng ảnh theo đường dẫn tương đối (`hinh/`,
`kiem_tra_warp/`, `ket_qua_val/`). Chuyển đi là mất ảnh trong PDF.

**`luu_tru/`** — 415 MB file không script nào đọc: bản `.bak`, viewer cũ, ảnh chụp màn hình,
H cũ, ortho cũ, kết quả của các model cũ. Xoá được nếu cần chỗ. Trả lại bằng
`python ma/dong_goi.py --hoan-tac`.

---

## Nguồn gốc code

| Lấy nguyên | Từ đâu |
|---|---|
| `project_box_to_ortho.py` | `D:\Remote_Project\solarfarm_inspection` — giống hệt, chỉ khác ký tự xuống dòng |
| `best.pt` (detector tấm pin) | cùng repo, md5 trùng khít |
| `RTK350.txt` (H khởi tạo của hãng) | cùng repo |

Phần còn lại viết trong dự án này. Chuỗi toán chiếu ảnh→ortho là của thầy; `ghep_ortho_nhiet.py`
dùng **ngược chiều** (chiếu từng pixel ortho về ảnh nhiệt) và vector hoá bằng numpy.

Model phát hiện lỗi `fault_obb_4class.pt` đến từ `D:\Remote_Project\solar-thermal-fault-annotator`.

---

## Môi trường

Python 3.13 · ultralytics 8.4.115 · torch 2.13.0+cpu · rasterio · pyproj · opencv
(`danh_gia_chi_so.py` chạy được với Python 3.11, không cần ultralytics)

Xuất PDF cần **pandoc** và **Chrome/Edge** — không cần LaTeX.
