# Báo cáo đánh giá hệ thống định vị lỗi tấm pin từ ảnh nhiệt

**Dự án:** 1008-stage1-rgb-thermal · **Ngày:** 11/08/2026 · **Phiên bản:** 1.2

*Đổi so với bản 1.0: mục 3.2 thay số mẫu 60 ảnh bằng bản quét đủ 598 ảnh (P90 25,3 → 31,7 cm);
thêm mục 3.3 về ba bộ lọc ảnh và kết quả kiểm chứng cách lọc theo tốc độ bay trong EXIF.*

*Đổi so với bản 1.1: **sửa một kết luận sai về recall.** Bản trước viết model "sót ~10 % số
lỗi", "cứ 100 lỗi hotspot thì sót khoảng 14". Truy lại thì recall 0,897 là số **tại điểm F1
lớn nhất** (conf ≈ 0,65), không phải tại ngưỡng chạy thật. Đo ở ngưỡng vận hành conf 0,25:
sót **3,2 %**, phần thiếu hụt chủ yếu là **gán nhầm tên lớp** chứ không phải bỏ sót lỗi —
xem mục 2.4 (mới). Thêm mục 2.7 so sánh với model mượn 8 lớp. Kiến nghị 1 viết lại theo đó.*

---

## 1. Tóm tắt

Hệ thống gồm hai phần độc lập, đánh giá riêng:

- **Phần phát hiện lỗi** — model `fault_obb_4class.pt` chạy trên ảnh nhiệt.
- **Phần định vị** — đưa box lỗi từ ảnh nhiệt sang toạ độ GPS và mã tấm pin (khối F1→F7).

| Chỉ số | Kết quả | Ngưỡng đề bài | Kết luận | Mục |
|---|---|---|---|---|
| **mAP@50** (tập test độc lập 91 ảnh) | **0,965** | không quy định | mAP@50-95: 0,955 | 2.1 |
| **Precision · Recall** — tại điểm F1 lớn nhất (conf 0,64) | **0,946 · 0,897** | không quy định | đây là số ultralytics báo mặc định | 2.1 |
| **Precision · Recall** — tại ngưỡng chạy thật (conf 0,25) | **0,875 · 0,959** | không quy định | recall cao hơn, đổi lại nhiều box rác hơn | 2.4 |
| Model bắt được lỗi (conf 0,25) | 273/280 = **97,5 %** | không quy định | — | 2.4 |
| Model gán đúng tên lớp | 260/280 = **92,9 %** | không quy định | 13 ca nhầm, đều là Single↔Multi | 2.4 |
| Sai số định vị trên ortho | RMSE **2,56 cm** | ≤ 30 cm | **Đạt** — dư 10 lần | 3.2 |
| Sai số trên ảnh lẻ (598 ảnh, sau lọc) | trung vị 14,1 cm · P90 24,6 cm | — | P90 trước lọc 31,7 cm | 3.2 |
| Hiệu chuẩn H nhiệt→RGB | **4,38 px** (H hãng: 22,34 px) | ≤ 3 px | **Không đạt** — nhưng tốt hơn hãng 5,1 lần | 3.1 |
| Gán lỗi vào mã tấm pin | gán được **92,4 %** | ≥ 95 % đúng | **Chưa đạt / chưa kết luận** | 4 |
| Khử trùng lặp | 407 → 211, nén **1,93 lần** | sót ≤ 5 % | **Chưa đo được** | 6 |
| Model mượn 8 lớp | bắt **45,7 %**, đúng lớp 22,9 % | — | Kém hơn hẳn, không thay thế được | 2.7 |

**Kết luận chính:** khâu định vị tốt hơn yêu cầu hơn 10 lần, và model phát hiện lỗi **không
phải điểm nghẽn** (bắt 97,5 %, trong đó 95,2 % đúng lớp). Điểm nghẽn thật nằm ở **khâu gán
tấm pin** (11,8 % lỗi không rơi vào tấm nào) và ở **hai ngưỡng nghiệm thu chưa đo được** vì
thiếu đối chứng hiện trường (mục 7).

---

## 2. Model phát hiện lỗi

**Model:** `fault_obb_4class.pt` (YOLO26s-OBB, 4 lớp, train 150 epoch)
**Nhãn gốc:** `D:\Remote_Project\solar-thermal-fault-annotator\data\colab\`

### 2.1 Kết quả trên tập test độc lập

Tập test 91 ảnh / 280 đối tượng, chia theo **nhóm chuyến bay**, chưa từng dùng khi train
hoặc chọn epoch. **Đây là con số dùng để báo cáo.**

| Lớp | Ảnh | Đối tượng | Precision | Recall | mAP@50 | mAP@50-95 |
|---|---:|---:|---:|---:|---:|---:|
| SingleHotSpot | 68 | 173 | 0,8770 | 0,8555 | 0,9336 | 0,9319 |
| MultiHotSpot | 36 | 70 | 0,9610 | 0,8571 | 0,9675 | 0,9571 |
| Bypass | 34 | 37 | 1,0000 | 0,9778 | 0,9950 | 0,9768 |
| **Tất cả** | **91** | **280** | **0,9460** | **0,8968** | **0,9654** | **0,9553** |

### 2.2 Kết quả trên tập val

| Tập | Số ảnh | Precision | Recall | mAP@50 | mAP@50-95 |
|---|---:|---:|---:|---:|---:|
| val — chia theo nhóm chuyến bay | 1120 | 0,9292 | 0,9097 | 0,9658 | 0,9621 |
| val — chia ngẫu nhiên | 607 | 0,9374 | 0,9206 | 0,9704 | 0,9676 |

Ba phép đo (test 0,9654 · val nhóm 0,9658 · val ngẫu nhiên 0,9704) sát nhau,
cho thấy model **không overfit nặng** và kết quả ổn định.

### 2.3 Độ chặt của box — mAP theo từng ngưỡng IoU

| Ngưỡng IoU | 0,50 | 0,60 | 0,70 | 0,80 | 0,85 | 0,90 | 0,95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| mAP | 0,9654 | 0,9654 | 0,9654 | 0,9654 | 0,9484 | 0,9457 | 0,9012 |

mAP giữ nguyên từ IoU 0,50 đến 0,80 và chỉ giảm nhẹ ở 0,95 — **box model vẽ rất khít
với nhãn**. Đây là điều kiện tiên quyết để định vị chính xác: box lệch bao nhiêu pixel
thì toạ độ GPS lệch bấy nhiêu.

### 2.4 Recall 0,897 nghĩa là gì — bỏ sót hay gán nhầm lớp?

Con số recall ở bảng 2.1 dễ bị đọc thành "model sót 10 % số lỗi". Không phải vậy, vì hai lý do.

**Thứ nhất: 0,897 là recall tại điểm F1 lớn nhất**, không phải tại ngưỡng conf chạy thật.
Ultralytics luôn báo P/R tại điểm này — đổi `conf` từ 0,05 lên 0,50 mà `box.mr` vẫn đứng im
ở 0,8968 chính là dấu hiệu đó. Đo trực tiếp trên đường cong: **điểm F1 lớn nhất nằm ở
conf 0,637**. P/R thật ở từng ngưỡng:

| conf | 0,05 | 0,15 | **0,25** | 0,40 | 0,50 | **0,64** | 0,70 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Precision | 0,698 | 0,822 | **0,875** | 0,902 | 0,914 | **0,940** | 0,954 |
| Recall | 0,996 | 0,965 | **0,959** | 0,938 | 0,922 | **0,906** | 0,881 |
| F1 | 0,812 | 0,881 | 0,911 | 0,918 | 0,917 | **0,922** ← đỉnh | 0,916 |

Đọc bảng này thấy rõ: **recall không phải giới hạn của model mà là lựa chọn ngưỡng**. Muốn
recall 0,96 thì có ngay ở conf 0,25, giá phải trả là precision tụt từ 0,94 xuống 0,875. F1
gần như phẳng trong cả khoảng conf 0,25–0,70 (0,911–0,922), nên chọn ngưỡng ở đây là quyết
định vận hành chứ không phải chuyện model mạnh yếu.

Ngưỡng đang chạy thật thấp hơn 0,5 (30 % lỗi trong `loi_tren_ortho_nhiet.json` có conf < 0,5)
— hợp lý với bài toán này, vì bỏ sót một tấm hỏng đắt hơn là soi nhầm một tấm lành.

**Thứ hai: phần thiếu hụt còn lại chủ yếu là gán nhầm tên lớp, không phải bỏ sót lỗi.**
Ghép từng box dự đoán với nhãn thật ở conf 0,25 · IoU ≥ 0,5:

| Lớp | số GT | bắt được | **bỏ sót hẳn** | gán đúng lớp | nhầm sang |
|---|---:|---:|---:|---:|---|
| SingleHotSpot | 173 | 167 | 6 | 163 | 4 → MultiHotSpot |
| MultiHotSpot | 70 | 69 | 1 | 60 | 9 → SingleHotSpot |
| Bypass | 37 | 37 | **0** | 37 | — |
| **Tất cả** | **280** | **273** | **7 (2,5 %)** | **260 (92,9 %)** | 13 (4,8 %) |

Kiểm chéo bằng ma trận nhầm lẫn của ultralytics ở cùng ngưỡng conf 0,25: 9 bỏ sót, **260 gán
đúng lớp** — khớp đúng con số 260. Chênh 7 so với 9 là do phép ghép trên dùng hộp thẳng trục
bao ngoài (nới IoU một chút), ultralytics dùng hộp xoay.

**Đọc kết quả:** model bắt được **97,5 %** số lỗi thật; trong số bắt được, **95,2 %** gán đúng
tên lớp. Toàn bộ 13 ca nhầm lớp đều là **Single ↔ Multi HotSpot**. Không có ca nào nhầm sang
`Bypass`, và `Bypass` không sót ca nào.

> **Cảnh báo về ngưỡng khi đọc ma trận nhầm lẫn.** Nếu chạy `model.val()` để mặc định
> (`conf=0.001`) thì ma trận nhầm lẫn cho ra bức tranh hoàn toàn khác: 1900 box, 0 bỏ sót,
> nhưng **1620 báo động giả** và chỉ 106 gán đúng lớp. Đó là ngưỡng không ai chạy thật.
> Mọi con số ở mục này đều lấy ở **conf 0,25**.

| | conf 0,001 (mặc định của val) | **conf 0,25 (ngưỡng vận hành)** |
|---|---:|---:|
| Box dự đoán | 1900 | **335** |
| Bỏ sót | 0 | **9** |
| Gán đúng lớp | 106 | **260** |
| Báo động giả | 1620 | **64** |

### 2.5 Vì sao Single ↔ Multi lẫn nhau

Hai lớp này phân biệt bằng **đếm số điểm nóng trên một tấm**. Ca sát ranh — hai điểm nóng dính
nhau, hay một điểm nóng loang rộng — thì chính người gán nhãn cũng không nhất quán. Model 6 lớp
của dự án annotator ghi đúng hiện tượng này trong `fault_obb_6class.json`: *"32 % Multi bị đoán
thành Single, 12 % ngược lại… Sitemark và IEC đều xếp chúng làm một loại"*. Cộng thêm lệch mẫu:
173 Single so với 70 Multi.

Đây là **vấn đề định nghĩa nhãn, không phải model kém nhìn**. Bằng chứng: `Bypass` — lớp có
hình thái tách bạch hẳn (vệt nhiệt dài) — chỉ nhầm 0/37. Muốn xoá hẳn nhóm lỗi này thì gộp
hai lớp thành một `HotSpot` duy nhất, đúng như IEC xếp.

Với hệ thống định vị thì ảnh hưởng nhỏ: tấm pin vẫn bị đánh dấu và vẫn được định vị đúng chỗ,
chỉ là nhãn mức độ ghi sai. Không mất tấm nào khỏi danh sách đi sửa.

### 2.6 Nhận xét

- **`Bypass` gần như hoàn hảo** (bắt 37/37, gán đúng 37/37) — vệt nhiệt dài, tương phản mạnh.
- **`ModuleOpenCircuit` không đánh giá được**: tập test và val theo nhóm không có mẫu nào.
  Ở bộ chia ngẫu nhiên lớp này đạt R 1,0000 nhưng đó là số trên vài mẫu model đã thấy khi
  train — **không dùng được**.
- **64 báo động giả trên 91 ảnh** (0,7 ảnh⁻¹) ở conf 0,25 — đây mới là chỗ đánh đổi thật,
  không phải recall. Nâng ngưỡng lên thì bớt box rác nhưng bắt đầu sót lỗi.

### 2.7 Đối chiếu với model mượn 8 lớp

`muon_det_8class.pt` là model **ngoài dự án**, học 8 loại lỗi nhiệt PV trên ~20.800 box của
một bộ dữ liệu khác. Không val thẳng được vì ba khác biệt: task `detect` (hộp thẳng trục) chứ
không phải OBB, bảng lớp khác (chỉ 5/8 tên về được lớp thật qua `aliases` trong
`config/classes.json`), và nó ăn **ảnh xám** chứ không phải Ironbow. Nên phải quy tất cả về
hộp thẳng trục rồi ghép theo IoU — model 4 lớp đo lại bằng **đúng đoạn code đó** để hai cột
so được với nhau.

Cùng tập test 91 ảnh / 280 đối tượng, conf 0,25 · IoU ≥ 0,5:

| | **4 lớp (dự án)** | **8 lớp mượn (ảnh xám)** | 8 lớp (ảnh Ironbow) |
|---|---:|---:|---:|
| Bắt được | **273/280 = 97,5 %** | 128/280 = **45,7 %** | 4/280 = 1,4 % |
| Gán đúng tên lớp | **260/280 = 92,9 %** | 64/280 = **22,9 %** | 4/280 |
| Bỏ sót hẳn | **7** | **152** | 276 |
| Box thừa | 70 | 27 | 1 |
| Precision trên box vẽ ra | 79,6 % | 82,6 % | 80,0 % |

**Model 8 lớp sót hơn một nửa số lỗi — không thay thế được model của dự án.** Ba điều rút ra:

1. **Bắt buộc đưa ảnh xám.** Đưa Ironbow vào thì nó chết hẳn: 4/280. Ghi chú trong
   `muon_det_8class.json` nói chênh 7,6 lần; đo trên tập test này là **32 lần** (128 so với 4).
2. **Bí danh `SingleByPassed → ModuleOpenCircuit` trong `config/classes.json` có vẻ sai.**
   Trong 37 đối tượng nhãn thật là `Bypass`, model 8 lớp bắt được 32 và gọi là `SingleByPassed`
   — nhận đúng vật, chỉ là bí danh đẩy sang lớp khác. Sửa thành `SingleByPassed → Bypass` thì
   tỉ lệ gán đúng lớp nhảy **22,9 % → 34,3 %**. Về nghĩa cũng hợp hơn: `SingleByPassed` là tấm
   *nóng* do diode bypass ăn, đúng là `Bypass`; còn `ModuleOpenCircuit` là tấm *nguội*.
3. **Vẫn dùng được làm ý kiến thứ hai.** Nó chỉ vẽ 27 box thừa (so với 70) và precision trên
   box nó vẽ ra ngang model dự án — kín tiếng chứ không phải bừa bãi. Và nó học từ bộ dữ liệu
   khác nên không nhiễm thói quen gán nhãn của dự án. Dùng để xếp thứ tự soi lại thì hợp lý,
   dùng để chạy pipeline thì không.

### 2.8 Cảnh báo về bộ chia ngẫu nhiên

Model được train trên `solar_cls4_final_ngaunhien`. Chính `data.yaml` của bộ này ghi cảnh báo:
khung ảnh drone liên tiếp chồng lấn nên **cùng một tấm pin vật lý nằm ở cả train lẫn val**.
Điểm trên bộ đó là tự chấm trên dữ liệu đã thấy. Báo cáo dùng số của bộ chia theo nhóm.

> **Không nhầm với `best.pt`.** Con số precision 0,967 / recall 0,980 / mAP@50 0,988 ghi
> trong `YEU_CAU_BAI_TOAN.pdf` là của `best.pt` — model **phát hiện tấm pin** (1 lớp
> `solar_panel`), không phải model phát hiện lỗi. Bê nhầm sang báo cáo là báo sai chỉ số.

---

## 3. Sai số định vị

### 3.1 Hiệu chuẩn H: ảnh nhiệt → ảnh RGB (khối F1)

| Nguồn | Số điểm | RMSE px | RMSE cm | Max px | Max cm |
|---|---:|---:|---:|---:|---:|
| H đang dùng (ảnh 0280) | 31 | 4,38 | 4,3 | 9,25 | 9,2 |
| Kiểm chéo 0320 | 15 | 2,44 | 2,4 | 3,89 | 3,9 |
| Kiểm chéo 0440 | 11 | 4,82 | 4,3 | 13,76 | 12,2 |
| Kiểm chéo 0080 | 9 | 2,88 | 2,6 | 5,06 | 4,5 |

Đối chiếu ngưỡng mục 4.3 của đề bài:

| Chỉ tiêu | Đo được | Ngưỡng | Kết quả |
|---|---|---|---|
| RMSE trên tập điểm hiệu chuẩn | 4,38 px | ≤ 3 px | **Không đạt** |
| Sai số lớn nhất vùng rìa ảnh | 9,25 px | ≤ 6 px | **Không đạt** |
| RMSE trên cặp ảnh kiểm chéo (0320) | 2,44 px | ≤ 4 px | Đạt |
| Số điểm hiệu chuẩn | 31 cặp | ≥ 10 cặp | Đạt |

**Đánh giá:** hai chỉ tiêu không đạt, nhưng cần đặt trong bối cảnh. Ma trận H của hãng
(`RTK350.txt`) cho RMSE 22,34 px — hiệu chuẩn tay đã **cải thiện 5,1 lần**. Quan trọng hơn:
sai số end-to-end cuối cùng vẫn là 2,56 cm, thoả ngưỡng nghiệm thu 30 cm rất thoải mái.
Ngưỡng 3 px ở mục 4.3 là ngưỡng trung gian đặt ra khi chưa biết sai số cuối, thực tế chặt
hơn mức cần thiết.

### 3.2 Sai số định vị end-to-end (F1→F5)

**Phép đo 1 — đối chứng trên orthophoto** (11 điểm, ảnh 0280):

| Thống kê | Giá trị |
|---|---|
| Trung bình | 2,44 cm |
| Trung vị | 2,69 cm |
| **RMSE** | **2,56 cm** |
| Lớn nhất | 3,06 cm |
| Độ lệch chuẩn | 0,78 cm |

**Phép đo 2 — trên từng ảnh lẻ** (**toàn bộ 598 ảnh**, chiếu viền tấm pin từ RGB sang nhiệt):

| Thống kê | Giữ tất cả 598 ảnh | Sau khi lọc (396 ảnh) |
|---|---|---|
| Trung vị | 15,3 cm | **14,1 cm** |
| Trung bình | 17,4 cm | — |
| P90 | 31,7 cm | **24,6 cm** |
| Lớn nhất | 59,3 cm | **45,9 cm** |
| Số ảnh lệch > 20 cm | 205 / 598 (34 %) | — |

> **Số cũ trong bản 1.0 là của mẫu 60 ảnh** (trung vị 15,0 · P90 25,3 · lớn nhất 63,0 cm).
> Bản này quét đủ 598 ảnh (44 phút). Trung vị gần như không đổi nhưng **P90 tăng từ 25,3
> lên 31,7 cm** — mẫu 60 ảnh chưa chạm tới đuôi phân bố.

**Vì sao hai con số khác nhau:** phép đo 1 đo lệch của **sản phẩm ortho đã ghép** — mỗi
pixel lấy từ ảnh chồng phủ nhiều lần nên sai số tư thế từng ảnh được trung bình hoá.
Phép đo 2 đo lệch giữa **hai cảm biến trên một lần bấm máy**, chưa qua bước trung bình hoá đó.
Cả hai đều đúng, đo hai thứ khác nhau.

**Ngưỡng mục 7 (≤ 30 cm): ĐẠT** — RMSE 2,56 cm trên sản phẩm ortho, tức chỉ số mà ngưỡng
này xét. Cần nói rõ: **P90 của phép đo 2 là 31,7 cm, vượt 30 cm.** Không mâu thuẫn, vì phép
đo 2 đo lệch giữa hai cảm biến trên ảnh lẻ, trước bước trung bình hoá của ortho. Bản 1.0 ghi
"ngay cả P90 (25,3 cm) vẫn dưới ngưỡng" — câu đó chỉ đúng với mẫu 60 ảnh, nay đã bỏ.

> **Lưu ý về sai số GPS tuyệt đối.** Con số 2,56 cm là sai số **tương đối** — đo bằng đối
> chứng nội bộ giữa ortho nhiệt và ortho màu. Sai số **tuyệt đối** ngoài thực địa còn cộng
> thêm sai số định vị của chính orthophoto Metashape (thường 2–5 cm nếu có GCP/RTK).
> Muốn chốt con số tuyệt đối phải đo vài điểm bằng máy RTK ngoài hiện trường.

### 3.3 Loại ảnh chụp lúc drone không bay đều

Ảnh RGB và ảnh nhiệt của cùng một lần bấm máy không nổ cùng lúc. Drone bay đều thì khoảng
trễ ấy chỉ dịch cảnh một đoạn nhỏ, ma trận H bù được; drone đang phanh gấp hoặc bị gió giật
thì cảnh trong hai ảnh lệch một lượng H không tả nổi, ghép vào ortho là cả vùng đó đặt sai chỗ.

Ba bộ lọc đang chạy nối tiếp trong `ghep_ortho_nhiet.py`:

| Bộ lọc | Cách hoạt động | Bỏ | Bỏ thêm so với bộ trước |
|---|---|---:|---:|
| A. Quay đầu, theo vị trí camera | Khoảng cách tâm chụp hai ảnh kề | 142 | 142 |
| B. Phép đo trực tiếp (`loc_anh_tre.py`) | Chiếu viền tấm pin RGB sang ảnh nhiệt, trượt tìm chỗ khớp | 90 | **57** |
| C. Dữ liệu bay trong EXIF (`loc_anh_rung.py`) | Tốc độ bay DJI ghi riêng cho từng cảm biến | 112 | **3** |

Còn lại **396 / 598 ảnh (66 %)**; ortho vẫn phủ 100 % diện tích vì độ chồng phủ cao.

**Bộ lọc có giá trị nhất là B — phép đo trực tiếp**, bắt được 57 ảnh mà hai bộ kia bỏ sót,
lệch trung vị nhóm này 11,96 px (≈ 31 cm).

**Về cách lọc theo tốc độ bay trong EXIF:** đã thử đúng cách và đo đầy đủ. Trên toàn bộ 598
ảnh, **không dấu hiệu tốc độ nào tách được ảnh tốt/xấu theo trung vị** — nhóm bị đánh dấu
lại lệch *ít* hơn nhóm giữ lại:

| Dấu hiệu | Bỏ | Trung vị bỏ / giữ | P90 bỏ / giữ |
|---|---:|---|---|
| Lệch tốc độ 2 cảm biến > 1 m/s | 61 | 5,19 / 5,86 px — **ngược** | 16,3 / 11,9 px — đúng |
| Tốc độ ngang < 1 m/s | 85 | 5,12 / 5,90 px — **ngược** | 16,2 / 12,0 px — đúng |
| Gia tốc (phanh gấp) > 1 m/s² | 150 | 5,66 / 5,84 px — **ngược** | 16,2 / 11,1 px — đúng |
| Thân máy lắc > 3° | 176 | 5,62 / 5,85 px — **ngược** | 16,2 / 10,9 px — đúng |

Nghĩa là các dấu hiệu này bắt trúng vài ảnh rất xấu (P90 cao hơn ~1,4 lần) nhưng quét theo
cả đống ảnh tốt. Bộ lọc quay đầu theo vị trí camera cũng cùng tình trạng (tỉ số trung vị 0,93).

Vẫn giữ bật hai dấu hiệu đầu vì một lý do cụ thể: chúng bắt được **3 ảnh mà cả A lẫn B đều
bỏ sót**, trong đó có ảnh `0001` lệch **22,63 px — ảnh xấu nhất còn sót của cả bộ**. Bộ lọc
A tính tốc độ từ hai ảnh kề *hai bên* nên ảnh đầu và ảnh cuối chuyến bay không đủ hàng xóm,
code mặc định coi chúng bay đều; EXIF đọc tốc độ ghi sẵn trong từng ảnh nên không có điểm mù
đó. Thêm C vào thì **lệch lớn nhất giảm 22,63 → 17,52 px (59,3 → 45,9 cm)**, còn trung vị và
P90 gần như không đổi.

Hai dấu hiệu gia tốc và thân máy lắc **tắt mặc định** vì không thêm gì ở biên: bật lên bỏ
thêm 54 và 33 ảnh mà P90 giữ nguyên 9,38 → 9,40 px và lệch lớn nhất không đổi.

> **Bài học phương pháp — đừng chốt ngưỡng trên mẫu.** Trên mẫu 60 ảnh, dấu hiệu lệch tốc độ
> hai cảm biến trông rất tốt: nhóm vượt ngưỡng lệch 9,28 px so với 5,41 px, gấp 1,7 lần. Quét
> đủ 598 ảnh thì tỉ số đảo về 0,89. Nhóm vượt ngưỡng trong mẫu chỉ có **7 ảnh** — quá ít để
> kết luận. Số liệu trong bảng trên đều là của bản quét đầy đủ.

---

## 4. Gán lỗi vào tấm pin (khối F7)

Trên 211 lỗi đã gom cụm:

| Chỉ tiêu | Số lượng | Tỉ lệ |
|---|---|---|
| Rơi đúng trong polygon tấm pin | 186 / 211 | 88,2 % |
| Gán được mã tấm pin | 195 / 211 | 92,4 % |
| Không rơi vào tấm pin nào | 25 / 211 | 11,8 % |

**IoU giữa box lỗi và polygon tấm pin được gán:**

| Thống kê | Giá trị |
|---|---|
| Trung bình | 0,616 |
| Trung vị | 0,687 |
| P25 / P75 | 0,523 / 0,782 |
| Nhỏ nhất / lớn nhất | 0,000 / 0,942 |

| Ngưỡng | Số lỗi | Tỉ lệ |
|---|---|---|
| IoU ≥ 0,1 | 192 / 211 | 91,0 % |
| IoU ≥ 0,3 | 187 / 211 | 88,6 % |
| IoU ≥ 0,5 | 161 / 211 | 76,3 % |
| IoU ≥ 0,7 | 99 / 211 | 46,9 % |

> **IoU này khác IoU ở mục 2.3.** Đây là giao giữa box lỗi (nhỏ, ~1 × 0,9 m) và cả tấm pin
> (~1,9 × 0,9 m), nên trần lý thuyết chỉ khoảng 0,5–0,8 — không phải IoU giữa dự đoán và
> nhãn. Con số 0,687 gần trần, tức box lỗi nằm gọn trong tấm.

**Khoảng cách tâm box lỗi → tâm tấm pin** (195 lỗi): trung vị 18 cm, trung bình 24 cm,
P90 43 cm, lớn nhất 116 cm. **91 %** dưới 50 cm (nửa chiều rộng tấm).

**Ngưỡng mục 7 (≥ 95 % gán đúng):** đo được **92,4 % gán *được***, thiếu 2,6 điểm.
Nhưng "gán *đúng*" thì đề bài yêu cầu kiểm tra thủ công 100 lỗi mẫu — **việc này chưa làm**,
nên chưa kết luận được.

---

## 5. Kiểm tra vị trí sai

### 5.1 Kiểm tra tổng quát — không có điểm văng

- Phạm vi toạ độ: lon 108,850501–108,852165 · lat 11,424002–11,424752 (trải rộng 182 × 83 m).
  Tất cả nằm trong phạm vi nhà máy, **không có điểm nào văng ra ngoài**.
- Kích thước box quy ra thực địa: trung vị **1,79 × 0,91 m**, khớp tấm pin thật (~1,0 × 2,0 m).

### 5.2 25 lỗi không rơi vào tấm pin nào — cần soi tay

| Loại lỗi | Conf | Lon | Lat | IoU | K/c tấm pin |
|---|---:|---|---|---:|---|
| SingleHotSpot | 0,898 | 108,852077 | 11,424733 | 0,000 | — |
| SingleHotSpot | 0,893 | 108,850878 | 11,424673 | 0,048 | 80 cm |
| SingleHotSpot | 0,839 | 108,852102 | 11,424517 | 0,000 | — |
| SingleHotSpot | 0,829 | 108,851936 | 11,424104 | 0,000 | — |
| SingleHotSpot | 0,805 | 108,852067 | 11,424578 | 0,000 | — |
| SingleHotSpot | 0,802 | 108,850657 | 11,424165 | 0,000 | — |
| MultiHotSpot | 0,741 | 108,852165 | 11,424741 | 0,008 | 89 cm |
| SingleByPassed | 0,734 | 108,850616 | 11,424053 | 0,001 | 116 cm |
| SingleHotSpot | 0,725 | 108,850655 | 11,424672 | 0,281 | 37 cm |
| MultiDiode | 0,723 | 108,852061 | 11,424440 | 0,000 | — |

**Đáng chú ý:** nhiều ca có confidence rất cao (0,80–0,90) mà IoU = 0,000 — lệch hẳn ra
ngoài chứ không phải sát mép. Ba khả năng:

1. Detector tấm pin (`best.pt`) bỏ sót tấm trên tile ortho → lỗi không có tấm để gán.
2. Lỗi nằm ở khe giữa hai dãy pin (đường đi, mương).
3. Báo động giả của model phát hiện lỗi.

Nhìn phân bố toạ độ, phần lớn các ca này tập trung ở **lon ≈ 108,8520–108,8522** (rìa đông
nhà máy) — gợi ý khả năng 1: rìa ortho là nơi detector tấm pin hay bỏ sót nhất.

**1 ca gán sai rõ ràng:** `SingleByPassed` conf 0,734 gán vào tấm `D42-T012` nhưng lệch tâm
**116 cm** với IoU 0,001 — gần như chắc chắn gán nhầm sang tấm bên cạnh.

### 5.3 Phân bố độ tin cậy

Trung vị 0,654 · P10/P90 0,354/0,855 · thấp nhất 0,253.
**64 lỗi (30 %) có conf < 0,5** — ngưỡng conf khi chạy suy luận đang khá thấp, đánh đổi
precision lấy recall. Với recall model chỉ 0,897 thì lựa chọn này hợp lý, nhưng cần đội bảo
trì biết để ưu tiên kiểm tra nhóm conf cao trước.

### 5.4 Phân bố theo loại lỗi

| Loại lỗi | Số lượng | Tỉ lệ |
|---|---:|---:|
| SingleHotSpot | 129 | 61,1 % |
| MultiHotSpot | 43 | 20,4 % |
| SingleByPassed | 35 | 16,6 % |
| MultiDiode | 4 | 1,9 % |

---

## 6. Khử trùng lặp (khối F6)

| Số ảnh quan sát | Số cụm | Tỉ lệ |
|---|---:|---:|
| 1 ảnh | 84 | 39,8 % |
| 2 ảnh | 86 | 40,8 % |
| 3 ảnh | 15 | 7,1 % |
| 4 ảnh | 24 | 11,4 % |
| 5 ảnh | 2 | 0,9 % |

407 quan sát → 211 cụm, **nén 1,93 lần** (48,2 % quan sát là trùng lặp).

**Ngưỡng mục 7 (sót ≤ 5 %): chưa đo được** — cần đếm tay số lỗi thật trong một khu vực mẫu
rồi đối chiếu. Dấu hiệu gián tiếp đáng lưu ý: **84 cụm (40 %) chỉ thấy từ 1 ảnh**. Với độ
chồng phủ cao thì mỗi lỗi lẽ ra phải được nhiều ảnh nhìn thấy. Hai cách giải thích:
lỗi mờ/yếu chỉ 1 ảnh bắt được, hoặc cụm bị tách nhầm. Cần kiểm chứng.

Lưu ý: sau mục 2.4 thì cách giải thích thứ nhất **yếu đi**. Model bắt được 97,5 % số lỗi thật
ở conf 0,25, nên "lỗi mờ chỉ 1 ảnh bắt được" khó chiếm tới 40 % số cụm. Nghi vấn nghiêng về
**cụm bị tách nhầm** — cùng một lỗi nhìn từ hai ảnh nhưng lệch quá ngưỡng IoU 0,3 nên không
gộp. Nếu đúng thì con số 211 lỗi đang **đếm thừa**, và ngưỡng gộp cần nới.

---

## 7. Những gì chưa đo được

| Hạng mục | Vì sao | Cần gì |
|---|---|---|
| Precision/recall của **khối định vị** (có bỏ sót lỗi thật không) | Chỉ có đầu ra hệ thống, không có đối chứng hiện trường | Danh sách lỗi thật trong một khu vực mẫu do đội bảo trì xác nhận |
| Tỉ lệ gán **đúng** tấm pin (ngưỡng 95 %) | Mới đo được tỉ lệ gán *được* = 92,4 % | Kiểm tra thủ công 100 lỗi mẫu |
| Tỉ lệ trùng lặp còn sót (ngưỡng 5 %) | Không có số lỗi thật để so | Đếm tay một khu vực mẫu |
| Sai số GPS **tuyệt đối** (ngưỡng 30 cm) | 2,56 cm là sai số *tương đối* giữa hai ortho | Đo vài điểm bằng máy RTK ngoài hiện trường |
| Lớp `ModuleOpenCircuit` | Không có mẫu trong tập test/val theo nhóm | Gán nhãn thêm mẫu lớp này |
| Thời gian xử lý (ngưỡng 2 s/ảnh) | Chưa đo trên toàn chuyến bay | Chạy benchmark end-to-end |

---

## 8. Kiến nghị

**Ưu tiên cao**

1. **Soi tay 25 ca lệch ngoài tấm pin.** Nếu nguyên nhân là detector tấm pin bỏ sót ở rìa
   ortho thì sửa được ngay bằng cách mở rộng vùng tile hoặc hạ ngưỡng conf của `best.pt`.
2. **Kiểm tra thủ công 100 lỗi mẫu** — chốt được cả tỉ lệ gán đúng lẫn tỉ lệ trùng lặp,
   hai ngưỡng nghiệm thu đang treo.
3. **Gộp `SingleHotSpot` + `MultiHotSpot` thành một lớp `HotSpot`.** Toàn bộ 13 ca nhầm lớp
   đều nằm ở cặp này (mục 2.5), mà ranh giới "1 cell hay từ 2 cell" thì người gán nhãn cũng
   không nhất quán và IEC xếp chúng làm một loại. Gộp xong tỉ lệ gán đúng lớp lên
   **273/280 = 97,5 %** mà không phải train thêm gì. Nếu đội bảo trì cần phân biệt mức độ
   thì giữ nguyên hai lớp, nhưng phải ghi rõ cột Single/Multi là gợi ý, không phải kết luận.

**Ưu tiên trung bình**

4. Đo vài điểm RTK ngoài hiện trường để chốt sai số GPS tuyệt đối.
5. Gán nhãn thêm lớp `ModuleOpenCircuit` để đánh giá được đủ 4 lớp.
6. Xem lại 84 cụm chỉ thấy từ 1 ảnh — phân biệt lỗi mờ thật với cụm bị tách nhầm.

**Không cần làm**

7. Không cần siết hiệu chuẩn H về ngưỡng 3 px. Sai số end-to-end đã là 2,56 cm so với ngưỡng
   30 cm — dư 10 lần. Công sức bỏ vào đây không cải thiện kết quả cuối.

---

## Phụ lục — cách tái lập

| Script | Đo gì |
|---|---|
| `val_model_4lop.py` | Val model trên 2 bộ (chia nhóm / chia ngẫu nhiên) |
| `val_tap_test.py` | Val trên tập test độc lập + mAP theo từng ngưỡng IoU |
| `phan_tich_recall.py` | Tách "bỏ sót" khỏi "gán nhầm lớp", recall theo từng ngưỡng conf (mục 2.4) |
| `so_model_8lop.py` | So model 4 lớp với model mượn 8 lớp trên cùng thước đo (mục 2.7) |
| `danh_gia_chi_so.py` | Toàn bộ chỉ số định vị, gán tấm pin, khử trùng lặp, vị trí sai |
| `loc_anh_tre.py` | Đo lệch RGB↔nhiệt trên từng ảnh (mục 3.2, 3.3) — ~45 phút cho 598 ảnh |
| `loc_anh_rung.py` | Lọc theo dữ liệu bay trong EXIF (mục 3.3) — 3 giây, `--doi-chieu` để kiểm chứng |
| `ghep_ortho_nhiet.py` | Dựng ortho nhiệt, đã nối sẵn cả ba bộ lọc ở mục 3.3 |

**Kết quả:** `ket_qua_val/ket_qua_val_4lop.json` · `ket_qua_val/ket_qua_test_4lop.json` ·
`ket_qua_val/phan_tich_recall.json` · `ket_qua_val/pr_theo_conf.json` ·
`ket_qua_val/so_model_8lop.json` ·
`ket_qua_val/danh_gia_dinh_vi.txt` · biểu đồ PR/confusion matrix trong `ket_qua_val/test_nhom/`

**Môi trường:** Python 3.13, ultralytics 8.4.115, torch 2.13.0+cpu
(Python 3.11 dùng cho `danh_gia_chi_so.py`, không cần ultralytics)

**Nguồn dữ liệu:**
- Model: `D:\Remote_Project\solar-thermal-fault-annotator\models\fault_obb_4class.pt`
- Nhãn: `D:\Remote_Project\solar-thermal-fault-annotator\data\colab\solar_cls4_nhom\`
- Kết quả định vị: `loi_tren_ortho_nhiet.json` (211 lỗi), `sai_so_end_to_end.json`,
  `thermal_to_rgb.json`, `anh_tre_chup_full.json` (598 ảnh), `anh_rung.json`
  (`anh_tre_chup.json` là mẫu 60 ảnh chạy thử, đã thay bằng bản đầy đủ)
