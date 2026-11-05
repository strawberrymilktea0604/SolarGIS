# Nội dung bài báo

**Dự án:** 1008-stage1-rgb-thermal · **Ngày:** 14/08/2026
**Tạp chí:** IEEE Geoscience and Remote Sensing Letters — Q2, đăng miễn phí, tối đa 5 trang
**Ràng buộc:** trong danh mục `TapChi-TheoHuong-TN2025-92.pdf` (mục E206) · ưu tiên Q2/Q3

---

## 1. Tên bài

**Tiếng Việt**

> **Định vị tấm pin ở mức centimet từ ảnh nhiệt UAV: độ chính xác đạt được
> và cái giá của lựa chọn xử lý**

**Tiếng Anh (bản nộp)**

> *Centimetre-level PV module localization from UAV thermal imagery:
> achievable accuracy and the cost of the processing choice*

---

## 2. Ba kết quả của bài

| # | Kết quả | Đối thủ gần nhất |
|:-:|---|---|
| **1** | Với RTK + DSM quang trắc + hiệu chuẩn H cấp thiết bị, sai số định vị tâm tấm pin đạt **mức centimet** trên 6473 tấm | [PV-Hawk](https://onlinelibrary.wiley.com/doi/full/10.1002/pip.3564): 5,87 m RMS tuyệt đối, **0,22–0,82 m** tương đối trong hàng |
| **2** | Phát hiện trên ortho ghép thay vì trên frame gốc làm mất **X %** dị thường — cùng model, cùng ngưỡng | Chưa ai đo cho ảnh nhiệt PV. [Bài cọ dừa](https://arxiv.org/pdf/2509.12400) làm cho ảnh RGB |
| **3** | **16,5 %** tấm trong nhà máy không thể kết luận vì thiếu phủ nhiệt — trần của mọi phương pháp | Chưa ai báo. [IEC TS 62446-3](https://datatec.es/wp-content/uploads/2019/09/Normativa-IEC-TS-62446-3.pdf) không bắt báo độ phủ |

Ba kết quả là một câu chuyện: **chuỗi đo này chính xác tới đâu, mất gì nếu chọn sai cách xử lý, và trần của nó ở đâu.**

> **Phải trung thực một điểm, viết hẳn vào bài.** Hơn PV-Hawk một phần vì **đầu
> vào đắt hơn**: họ dùng GPS thường + SfM, ta có RTK fix 598/598 + Metashape +
> DSM. Nên **không** viết "thuật toán của tôi tốt hơn". Viết: *khi có sẵn RTK và
> DSM quang trắc thì đạt được độ chính xác nào, và có đáng không.* Câu đó vừa
> đúng vừa có ích cho người đọc.

---

## 3. Nội dung từng mục

### I. Mở đầu — ~0,7 trang

Nhà máy điện mặt trời quy mô lớn cần đầu ra là **mã tấm pin đi thay**, nên đại
lượng cần đo là **sai số định vị cấp tấm**, không phải mAP cấp box.

Nêu hai lựa chọn xử lý mà ngành đang chia làm hai phe: ghép orthomosaic rồi
detect (Solar Energy 2023, phần mềm thương mại) so với detect trên frame rồi
georeference (PV-Hawk). **Chưa ai đo cái giá của lựa chọn đó cho ảnh nhiệt**,
và chưa ai báo trần độ phủ.

Đóng góp: ba kết quả ở §2.

### II. Dữ liệu và chuỗi đo — ~1 trang

**Thu nhận.** 598 cặp ảnh RGB + nhiệt, DJI ZH20T, nhà máy Thuận Nam 19, bay 31 m,
ngày 11/04/2026. RGB 4056×3040, nhiệt 640×512. **RTK fix 598/598, std ngang
0,83 cm.**

**Hiệu chuẩn nhiệt→RGB.** Đơn ứng H chấm tay 31 cặp điểm, **một lần cho mỗi model
drone**, dùng lại cho mọi trang trại. RMSE tái chiếu **4,38 px**, so với **22,34 px**
của ma trận do hãng cung cấp. Ghi kèm **kết quả âm**: tương quan pha và ghép góc
tấm pin đều hỏng vì lưới tấm pin tuần hoàn quá đều — hai câu, nhưng cứu thời gian
cho người sau.

**Chuỗi chiếu.** pixel nhiệt → qua H → pixel RGB → tia ECEF theo tư thế camera →
dò nhị phân cắt DSM → lon/lat. Chiếu cả **bốn góc** của tứ giác xoay để ra vết
thật trên mặt đất.

**Lọc frame.** Loại ảnh trễ chụp / rung: P90 sai số 31,7 → **24,6 cm**. Ghi kèm
kết quả âm thứ hai: **tốc độ bay trong EXIF không tách được nhóm này** (đã thử
trên cả 598 ảnh).

**Khử trùng lặp.** Ảnh chồng lấn 70–80 % nên một tấm nằm trong 5–10 ảnh. Gom cụm
theo khoảng cách thực địa, ngưỡng **0,60 m**, giữ phát hiện có conf cao nhất làm
đại diện; gộp theo **vị trí, không đòi trùng lớp**. Nén **1,93 lần**.
*Phải biện minh ngưỡng 0,60 m: tấm pin rộng 0,88 m nên hai tấm cạnh nhau không bị
gộp nhầm.*

**Mốc đối chiếu.** **511 tấm người soi chốt tay** trên toàn nhà máy (443 lỗi +
68 tốt), trong đó **305 tấm sửa lại viền**. Vị trí phán trên ortho màu, có lỗi
hay không phán trên ortho nhiệt.

### III. Độ chính xác định vị — ~1,2 trang · **KẾT QUẢ CHÍNH**

Đo **sai số vị trí tâm tấm pin trên cả 6473 tấm** — đúng đại lượng PV-Hawk đo,
để so được trực tiếp.

Bảng so sánh:

| | Nguồn vị trí | Sai số tương đối | Quy mô |
|---|---|---|---|
| PV-Hawk | SfM + GPS quỹ đạo drone | 0,22–0,82 m | 35.084 tấm, 5 nhà máy |
| **Bài này** | **RTK + Metashape + DSM** | **… cm** *(chờ đo)* | 6473 tấm, 1 nhà máy |

Kèm **ngân sách sai số** tách theo khâu: H · DSM · tư thế camera · độ trễ chụp.
Số end-to-end hiện có: RMSE **2,56 cm** trên 11 điểm đối chứng (max 3,06 cm) —
nhưng đó là độ khớp ortho nhiệt ↔ ortho màu, **không cùng đại lượng**, phải nói
rõ và thay bằng phép đo mới.

### IV. Cái giá của việc ghép trước — ~1 trang

Cùng model 4 lớp, cùng ngưỡng conf 0,25, chạy hai bên:

- **Trên frame gốc rồi chiếu** → 603 dị thường
- **Trên ortho nhiệt ghép** → *(chờ chạy)*

**Cơ chế**, nếu kịp bóc dữ liệu 16-bit: ghép ortho **lấy trung bình các khung
chồng lấn**, làm phai độ tương phản ΔT của vệt nóng nhỏ hơn ô lưới. Đo ΔT của
cùng một vệt nóng ở hai bên. Đây là cơ chế **bức xạ**, khác hẳn ảnh RGB nơi ghép
chỉ mất chi tiết kết cấu — chính chỗ này tách bài khỏi bài cọ dừa.

Kèm kết quả cấp tấm pin, **báo hai cột**: toàn bộ, và riêng phần detector chưa
từng thấy.

### V. Trần độ phủ — ~0,5 trang

**1065/6473 tấm (16,5 %) không đủ ảnh nhiệt để kết luận.** Chúng **không phải
"tấm tốt", mà là "chưa soi được"**. Tách tiếp bằng phép chiếu ngược tâm từng tấm
vào cả 598 camera:

| | | |
|---|---:|---|
| không ảnh nào chụp tới | 102 | chỉ bay lại mới soi được |
| chỉ ảnh đã bị loại thấy | 119 | moi lại được |
| ảnh đạt lọc vẫn thấy | 3 | ortho bỏ sót, vá được |

Mọi chỉ số phải tính trên phần soi được, và **phải công bố tỉ lệ này** — nếu
không thì con số đọc ra như thể đã phủ hết nhà máy.

### VI. Kết luận — ~0,4 trang

Độ chính xác cấp centimet đạt được khi có RTK và DSM; lựa chọn xử lý có giá đo
được; và mọi khảo sát đều có trần độ phủ cần công bố. Suy rộng cho khảo sát nhiệt
tìm mục tiêu nhỏ nói chung, không riêng pin mặt trời.

**Hạn chế**, viết thẳng: một nhà máy · một model drone · ground truth là người
soi ảnh nhiệt chứ không phải đối chứng điện · lớp `ModuleOpenCircuit` 0 phát hiện
nên chỉ đánh giá được 3/4 lớp.

### Hai quy tắc viết, giữ xuyên suốt

- Dùng ***thermal anomaly***, **tuyệt đối không** dùng ***fault*** — chưa có I–V
  hay EL xác nhận.
- Mọi chỉ số cấp tấm pin **báo hai con số**: toàn bộ và phần dữ liệu sạch. Giấu
  một trong hai là chỗ bài chết.

---

## 4. Hình và bảng — 5 trang chỉ đủ 4 hình

| | Nội dung | Có sẵn? |
|:-:|---|---|
| **H1** | Sơ đồ chuỗi đo: frame → H → tia ECEF → cắt DSM → mã tấm | Có, từ `slide_pipeline.html` |
| **H2** | ΔT cùng một vệt nóng: trên frame gốc vs trên ortho ghép — **hình chốt** | Chờ bóc 16-bit |
| **H3** | Bản đồ độ phủ: tấm rìa / thiếu nhiệt / soi được, ba màu | Có dữ liệu, chưa dựng |
| **H4** | H hãng vs H chấm tay, chồng viền tấm pin (22,34 px vs 4,38 px) | Có, từ `kiem_tra_warp/` |
| **B1** | So sánh độ chính xác định vị với PV-Hawk | Chờ đo |
| **B2** | P/R cấp tấm pin: frame vs ortho, toàn bộ vs dữ liệu sạch | Chờ chạy |

---

## 5. Dữ liệu đang có

| Nhóm | Nội dung |
|---|---|
| **Ảnh gốc** | 598 cặp RGB + nhiệt, ZH20T, Thuận Nam 19, 31 m, 11/04/2026. RTK fix 598/598, std 0,83 cm |
| **EXIF bay** | 598 bản ghi × 21 trường: tốc độ XYZ, roll/pitch/yaw thân + gimbal, cao độ |
| **Metashape** | `ortho.tif` 25354×14993 · `dsm.tif` 12677×7497 float32 · `cameras.xml` (**0 GCP**) |
| **Ortho nhiệt** | 4 bản tự dựng 8451×4997, bước pixel gấp đúng 3 lần ortho màu |
| **Nhãn tay** | **511 tấm gán tay** (443 lỗi + 68 tốt), 305 tấm sửa viền, 6473 polygon |
| **Hiệu chuẩn** | H: 31 cặp điểm, 4,38 px (hãng 22,34). End-to-end 11 điểm: RMSE 2,56 cm |
| **Kết quả** | 603 dị thường 4 lớp đã gán mã tấm · IoU trung vị 0,687 · 1065 tấm ngoài phạm vi |
| **Đang bỏ phí** | Dữ liệu bức xạ 16-bit trong APP3 — cần cho H2 |

---

## 6. Bốn việc phải chạy, đều là script

**① Bản lề — đo sai số vị trí tâm tấm pin trên 6473 tấm**, cùng đại lượng PV-Hawk
đo. Chưa có nó thì chưa biết kết quả chính đứng hay đổ. Làm trước tiên.

**② Ablation frame vs ortho.** `ma/thu_detect_tren_ortho.py` đã viết đúng thí
nghiệm nhưng bị chặn ở `items[:60]`, đọc dữ liệu cũ 284 lỗi từ
`so_sanh_model.html`, và không ghi kết quả ra file. Sửa ba chỗ đó, chạy cả 603 lỗi.

**③ Đo lại P/R trên nhóm dữ liệu sạch.** Đối chiếu tên file cho thấy **479/598
ảnh (80,1 %) nằm trong tập huấn luyện detector**, 330 ở tập train. Chỉ số cấp tấm
pin hiện tại (P 0,865 · R 0,968 · F1 0,914) nhiễm bẩn. Lọc nhóm tấm chỉ do 119
ảnh sạch nhìn thấy — `nguon_nhiet` đã chiếu ngược sẵn — rồi chạy lại
`danh_gia_model_theo_nhan.py`. Mức thổi tham chiếu đã đo được: **0,911 → 0,617**.

**④ Bóc ΔT từ APP3** để dựng H2. Chỉ cần so tương phản một vệt nóng trước và sau
khi ghép, không cần IEC 62446-3.

---

## 7. Lịch — 5 tuần

| Tuần | Việc |
|---:|---|
| 1 | ① đo sai số tâm tấm pin · đọc PV-Hawk 2021 + 2022 cho kỹ |
| 2 | ② ablation · ③ đo lại trên dữ liệu sạch |
| 3 | ④ ΔT · dựng H1–H4 |
| 4 | Viết bản thảo 5 trang |
| 5 | Đọc 15 bài related work, sửa, nộp |

**Trước khi bắt tay: hỏi thầy** có đồng ý tách letter này khỏi bài chính không.
Bài chính của thầy bán terrain-aware projection, grid regularization, GSD × bức
xạ — không giẫm chân nhau, và letter ra trước thì bài của thầy trích dẫn lại được.
