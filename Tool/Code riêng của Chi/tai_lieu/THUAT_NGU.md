# Thuật ngữ dự án — định vị lỗi tấm pin từ ảnh nhiệt drone

Tài liệu tra cứu cho người mới vào dự án, hoặc người đọc `BAO_CAO_DANH_GIA.pdf` /
`HUONG_DAN_PIPELINE.pdf` mà vướng chữ. Mỗi mục là **nghĩa trong dự án này**, kèm con số
thật đo được ở trang trại Thuận Nam — không phải định nghĩa sách vở chung chung.

Ảnh minh hoạ lấy từ chính các bước chạy của dự án, không phải hình vẽ mô phỏng.

> **Số phải nói kèm khi trích.** Sai số **2,56 cm** là sai số *tương đối* (ortho nhiệt ↔
> ortho màu). Sai số GPS *tuyệt đối* chưa đo được vì `cameras.xml` có **0 GCP**.
> **mAP 0,965** đo trên tập có 81 % ảnh nằm trong train — xem mục [5](#5-đo-chất-lượng-model).

---

## 1. Thiết bị và dữ liệu bay

| Thuật ngữ | Nghĩa trong dự án này |
|---|---|
| **DJI ZH20T** | Camera kép trên drone: một ống **nhiệt** 640 × 512 và một ống **màu** (RGB). Một lần bấm ra hai file: `..._T.JPG` (thermal) và `..._W.JPG` (wide/RGB) |
| **Cặp ảnh nhiệt–RGB** | Hai file cùng một lần bấm. Ghép cặp theo **`seq`** (số thứ tự bấm máy), không ghép theo dòng CSV |
| **R-JPEG** | Định dạng ảnh nhiệt DJI. Ngoài ảnh xem 8-bit còn nhét mảng nhiệt **16-bit** trong các đoạn **APP3** của file JPEG — đúng 655 360 byte. `cv2.imread` chỉ đọc bản xem, **mất ~16 lần độ phân giải nhiệt** (4283 mức → 256 mức) |
| **APP3** | Đoạn phụ trong file JPEG chứa mảng 16-bit nói trên. Đọc bằng [doc_nhiet_raw.py](../ma/doc_nhiet_raw.py) |
| **ΔT** | Chênh nhiệt so với nền. Đây là đại lượng **so được** giữa hai tấm trong cùng một ảnh; nhiệt độ *tuyệt đối* phải giải bằng DJI Thermal SDK (hệ số phát xạ, nhiệt phản xạ, độ ẩm, khoảng cách) |
| **Ironbow** | Bảng màu giả của ảnh nhiệt (tím → cam → vàng → trắng). Là **màu**, không phải nhiệt độ. Mỗi ảnh tự kéo tương phản theo dải nhiệt riêng, nên cùng một nhiệt độ thật cho ra màu khác nhau ở hai ảnh khác nhau — **không đọc số từ màu được** |
| **EXIF** | Siêu dữ liệu nhúng trong ảnh: GPS, cao độ, góc gimbal, tốc độ bay. Nguồn cho `exif_bay.json` |
| **Độ trễ màn trập** | Ống nhiệt và ống màu không bấm cùng thời điểm. Drone bay được vài cm giữa hai lần chụp → ảnh nhiệt lệch so với ảnh màu. Chính là `dx, dy` mà `loc_anh_tre.py` đo |
| **Nadir / off-nadir** | Camera chĩa **thẳng đứng xuống** / chĩa **lệch**. Ảnh off-nadir làm tấm pin bị đổ nghiêng, box chiếu xuống ortho méo thành hình bình hành thay vì chữ nhật |
| **Độ chồng phủ (overlap)** | Phần diện tích hai ảnh liên tiếp cùng nhìn thấy. Cần đủ chồng phủ thì Metashape mới align được và ortho mới không thủng lỗ |

![Cặp ảnh RGB và ảnh nhiệt cùng một lần bấm máy](hinh_thu_tu/h2_cap_anh.png)

*Hình 1 — Cặp ảnh cùng `seq`: bên nào cũng là cùng một khoảnh khắc bấm máy, nhưng hai ống
kính khác tiêu cự, khác độ phân giải, và lệch nhau vì độ trễ màn trập.*

![Bản đồ độ chồng phủ giữa các ảnh trên đường bay](hinh_thu_tu/h4_chong_phu.png)

*Hình 2 — Độ chồng phủ. Chỗ nào ít ảnh nhìn thấy thì ortho ở đó mỏng, dễ thủng.*

---

## 2. Trắc địa ảnh (photogrammetry)

Đây là nhóm chữ hay gây hiểu nhầm nhất, vì cùng một chữ "ảnh" nhưng có tới ba hệ toạ độ:
**pixel ảnh gốc**, **pixel ortho**, và **lon/lat**.

| Thuật ngữ | Nghĩa |
|---|---|
| **Metashape** | Phần mềm dựng ortho + DSM từ chồng ảnh drone. Sản phẩm dùng trong dự án nằm ở `Thermal2_31M_full_export/` |
| **Align** | Bước Metashape tìm vị trí và hướng của từng camera. **598 = số camera align được**, không phải số ảnh đã chụp. Ảnh nào không align được thì không có trong `manifest_anh.csv` |
| **`cameras.xml`** | File Metashape xuất ra: ma trận tư thế từng camera + thông số ống kính. Đầu vào bắt buộc của mọi phép chiếu ảnh → ortho |
| **Orthophoto (ortho)** | Ảnh ghép đã nắn về góc nhìn thẳng đứng, mỗi pixel ứng với một ô mặt đất cố định → **đo khoảng cách trên đó được**. Ảnh drone thường thì không |
| **DSM** | Mô hình độ cao **bề mặt**. Cần để biết một tia nhìn từ camera rơi xuống mặt đất ở cao độ nào. Ở đây DSM bám được cả độ cao dãy tấm pin, không chỉ mặt đất |
| **GSD** | Kích thước một pixel ngoài thực địa. Đo được trong dự án: ortho màu **0,96 cm/px**, ortho nhiệt **2,87 cm/px** (đúng 3 lần), DSM **1,91 cm/px**. Nền công cụ gán nhãn để **2,65 cm/px** vì có phóng lại |
| **CRS / EPSG** | Hệ toạ độ. Ortho của dự án ở **EPSG:4326** — đơn vị là **độ**, không phải mét. Đừng suy cửa sổ cắt từ lon/lat, dùng chỉ số hàng/cột |
| **Ma trận H (homography)** | Phép biến hình 3 × 3 đưa toạ độ **ảnh nhiệt → ảnh RGB**. Gắn với **model drone**, không gắn với trang trại — chấm tay 31 cặp điểm một lần, dùng cho mọi trang trại cùng loại drone |
| **Warp / nắn** | Áp H (hoặc phép chiếu qua DSM) để bẻ ảnh sang hệ toạ độ khác |
| **GCP** | Điểm khống chế mặt đất đo bằng máy trắc địa. Dự án này có **0 GCP** → chỉ đo được sai số *tương đối* |
| **RTK** | GPS độ chính xác cm. Không có RTK thì GPS drone sai khoảng **1–5 m** |
| **Mosaic / ghép ortho** | Nối nhiều ảnh thành một tấm. Bốn biến thể có trong repo: `tu_lam`, `dan_xuoi`, `pha_tron`, `nan` |
| **Dán xuôi / đi ngược** | Hai chiều chạy khi ghép. **Dán xuôi**: duyệt theo thứ tự ảnh, warp cả ảnh lên lưới rồi dán chồng — kết quả phụ thuộc thứ tự và phải giả định vùng ảnh phủ là một mặt phẳng. **Đi ngược**: duyệt theo từng ô lưới ortho, mỗi ô tự tra DSM rồi đi tìm giá trị của nó |
| **Mối ghép (seam)** | Đường nối giữa hai ảnh trong mosaic. Đứt đoạn ở đó là **lỗi hình học**, không phải lỗi cân bằng sáng |
| **Cân bằng sáng** | Kéo mức xám các ảnh về cùng thang trước khi dán. Đo được: lệch mối ghép 18,1 → 17,7 mức xám. Tức **cân bằng sáng không xoá được mối ghép** |

![Ba mươi ba điểm neo đã chiếu, đánh dấu chữ thập đỏ có đánh số trên ortho màu](hinh/h2_diem_tren_ortho.jpg)

*Hình 3 — Orthophoto màu. Chữ thập đỏ là các điểm neo đã chiếu từ ảnh gốc xuống. Nhìn thẳng
đứng, tỉ lệ đều — nên đo được khoảng cách trên đó. Bóng người ở giữa cho thấy đây là ảnh
thật ghép lại chứ không phải bản đồ vẽ.*

![Bốn khung so sánh ma trận RTK350 cũ và ma trận hiệu chuẩn lại, trên hai ảnh 0320 và 0480](hinh/h1_hieu_chuan.jpg)

*Hình 4 — Ma trận **H** làm gì: chiếu viền tấm pin từ ảnh RGB sang ảnh nhiệt. H sai thì viền
trượt khỏi lưới tấm, H đúng thì khít. So sánh ma trận của hãng và ma trận chấm tay lại.*

![Bản đồ viền hai phổ chồng nhau, xanh là viền RGB đỏ là viền nhiệt đã nắn](../ket_qua/kiem_tra_warp/hieu_chuan_0280.jpg)

*Hình 5 — Cách đọc chất lượng H: chồng viền hai phổ lên nhau. Hai màu càng trùng thì H càng đúng.*

![Dán xuôi so với đi ngược, kèm bản đồ chênh lệch](hinh_thu_tu/h9_xuoi_va_nguoc.png)

*Hình 6 — **Dán xuôi** so với **đi ngược**: cùng dữ liệu, cùng 396 ảnh, cùng cân bằng sáng,
khác duy nhất chiều chạy. Chênh trung vị 24,2 mức xám, 55,6 % số ô chênh quá 20 — chênh nổi
lên đúng ở mép các dãy pin, chỗ DSM có bậc độ cao.*

![Cân bằng sáng giữa các ảnh trước khi dán](hinh_thu_tu/h7_can_sang.png)

*Hình 7 — Cân bằng sáng. Nó làm ảnh liền màu hơn, nhưng chỗ đứt gãy hình học ở mép vẫn còn.*

---

## 3. Ảnh nhiệt và ortho nhiệt

| Thuật ngữ | Nghĩa |
|---|---|
| **Ortho nhiệt** | Ortho ghép từ **ảnh nhiệt**. Dựng bằng `ghep_ortho_nhiet.py`, kích thước 8451 × 4997 |
| **Ảnh bị loại** | Ảnh chụp lúc drone rung hoặc trễ màn trập quá mức. Ortho chỉ dựng từ **396/598** ảnh đạt lọc |
| **`phu_nhiet`** | Phần trăm diện tích một tấm pin **có dữ liệu nhiệt** |
| **`phan_duoc`** | Tấm có đủ nhiệt để phán hay không. **Lọc `phan_duoc == false` trước khi tính bất kỳ chỉ số nào** — 224 tấm thiếu nhiệt không phải "tấm tốt", mà là "chưa soi được" |
| **`ria`** | Tấm ở rìa nhà máy: có ảnh màu mà không có ảnh nhiệt → thấy tấm nhưng không phán được gì. 841 tấm, mặc định ẩn |
| **"Ortho nhiệt không có" ≠ "ảnh nhiệt không có"** | Ortho chỉ ghép từ ảnh đạt lọc. Trong 224 tấm thiếu ortho nhiệt: 119 tấm **vẫn có ảnh chụp tới**, chỉ là ảnh đã bị loại — moi lại được, không phải bay lại |
| **`do_net`** | Độ nổi của đỉnh khớp khi trượt tìm lệch. **< 0,5** nghĩa là đỉnh không nổi, số đo ra là nhiễu |
| **"Chạm mép"** | Lệch thật vượt bán kính trượt 16 px → số ghi ra là số **bị kẹp**, không phải số đo được |
| **Căn tay / chấm tay** | Người kéo cho khít thay vì để máy đo. Áp dụng cho **H** (một lần cho mỗi model drone) và cho **29 ảnh** máy đo bó tay |

![Một vùng ortho nhiệt đã ghép, bảng màu Ironbow](../ket_qua/kiem_tra_warp/ortho_nhiet_tu_lam.jpg)

*Hình 8 — Ortho nhiệt, bảng màu Ironbow. Vàng sáng là nóng. Chú ý: đây là ảnh **blend trung
bình** nhiều ảnh chồng phủ, nên hotspot nhỏ bị làm nhoè — đó là lý do model chạy trên ảnh gốc
chứ không chạy trên ortho.*

![Ortho nhiệt toàn nhà máy](hinh_thu_tu/h8_ket_qua.png)

*Hình 9 — Ortho nhiệt toàn trang trại, ghép từ 396 ảnh đạt lọc. Vùng đen là chỗ không có ảnh
nhiệt đạt lọc phủ tới.*

![Hai khung so sánh: không bù và bù -25 ms](../ket_qua/kiem_tra_warp/do_tre_chup.jpg)

*Hình 10 — **Độ trễ màn trập**: cùng một ảnh, trái là không bù, phải là bù −25 ms. Đại lượng
này thay đổi theo từng ảnh, khác với H là cố định theo model drone.*

![Viền tấm pin dự đoán màu vàng bên trái, viền sau khi bù màu xanh lá bên phải, trên ảnh nhiệt](../ket_qua/kiem_tra_warp/anh_tre_0080.jpg)

*Hình 11 — Cách đo lệch: chiếu viền tấm pin qua H lên ảnh nhiệt (vàng), rồi trượt tìm vị trí
khớp nhất trong bán kính 16 px (xanh lá). Ảnh mép trang trại ít lưới tấm để bám thì phép đo
này hỏng — đó là 29 ca phải căn tay.*

---

## 4. Model phát hiện lỗi

| Thuật ngữ | Nghĩa |
|---|---|
| **YOLO / ultralytics** | Họ model detect một pha. Model đang dùng: `fault_obb_4class.pt` |
| **OBB** | *Oriented Bounding Box* — hộp **xoay được**. Tấm pin nằm chéo trong ảnh nên phải dùng OBB |
| **AABB** | Hộp **thẳng trục**, không xoay. Với tấm pin chéo thì AABB bao thừa rất nhiều nền |
| **conf** | Điểm tự tin của mỗi box, 0 → 1. **Ngưỡng chốt của dự án là 0,25**, không phải 0,64 |
| **NMS** | Khử các box trùng chồng lên nhau trên cùng một vật |
| **Lớp (class)** | Loại lỗi mà model gán cho box |
| **Box gần trọn một tấm** | Box của model bao **cả tấm pin** (trung vị 0,95 × 1,85 m so với tấm thật 0,88 × 1,76 m, IoU 0,716), chứ không khoanh riêng ô nóng. Đừng đọc tâm box như vị trí ô lỗi |
| **Polygon tấm pin** | Viền tứ giác từng tấm, do detector `best.pt` sinh trên ortho màu. 6473 polygon |
| **Mã tấm** (`D20-T131`) | Mã dãy–tấm. **Không lưu trong file polygon** — sinh lại từ vị trí, bằng cùng một đoạn code ở `gan_tam_pin_4lop.py` và `lam_gan_nhan_tam.py`. Sửa một bên là lệch mã |

### Bốn lớp lỗi

| Lớp | Nghĩa vật lý | Trên bộ Thuận Nam |
|---|---|---|
| **SingleHotSpot** | Một điểm nóng đơn lẻ — thường do bẩn, nứt tế bào, bóng che | Có |
| **MultiHotSpot** | Nhiều điểm nóng trên cùng một tấm | Có |
| **Bypass** | Diode bypass hỏng → nóng cả **một dải** (khoảng 1/3 tấm) | Có |
| **ModuleOpenCircuit** | Tấm đứt mạch, nóng đều toàn tấm | **0 phát hiện** |

> **Cặp luôn lẫn nhau: SingleHotSpot ↔ MultiHotSpot.** Ranh giới giữa "một điểm" và "vài
> điểm" phụ thuộc người gán nhãn. Khi đọc ma trận nhầm lẫn, phần lớn ô ngoài đường chéo nằm
> ở cặp này.

![Chín ảnh nhiệt với box OBB, tên lớp và điểm conf](../ket_qua/ket_qua_val/test_nhom/val_batch0_pred.jpg)

*Hình 12 — Đầu ra thô của model trên ảnh nhiệt gốc. Mỗi khung là một **OBB** — chú ý hộp
**nghiêng theo tấm pin** chứ không thẳng trục. Nhãn ghi tên lớp và **conf** (0,6 → 1,0).*

![Viền tấm pin màu xanh lá trên ortho màu](../ket_qua/kiem_tra_warp/soi_polygon.jpg)

*Hình 13 — **Polygon tấm pin** trên ortho màu. Chú ý ô xanh lá dưới bên trái khoanh ra bãi
cỏ — detector tấm pin cũng có ca sai, nên bước gán mã tấm phải kiểm bằng IoU chứ không tin
mù polygon.*

![Bốn ca gán tấm pin: khung đỏ là box lỗi, khung xanh lá là polygon tấm được gán, kèm IoU](../ket_qua/kiem_tra_warp/gan_tam_pin_v2.jpg)

*Hình 14 — Gán mã tấm: khung **đỏ** là box lỗi model tìm được, khung **xanh lá** là polygon
tấm pin được gán cho nó, con số là **IoU** giữa hai cái.*

---

## 5. Đo chất lượng model

Ba chữ viết tắt mà mọi thứ khác dựng lên từ đó:

| | Nghĩa | Cái giá phải trả |
|---|---|---|
| **TP** | Bắt trúng — có lỗi thật, model báo | — |
| **FN** | **Bỏ sót** — có lỗi thật, model không báo | Tấm hỏng nằm ngoài đồng, mất điện, có thể cháy |
| **FP** | **Báo nhầm** — không có lỗi, model vẫn báo | Người đi kiểm mất công leo ra tận nơi |

| Thuật ngữ | Công thức / nghĩa |
|---|---|
| **Recall** | `TP / (TP + FN)` — bắt được bao nhiêu phần lỗi **thật**. Dự án này ưu tiên recall vì bỏ sót đắt hơn báo nhầm |
| **Precision** | `TP / (TP + FP)` — báo ra thì đúng bao nhiêu phần |
| **F1** | Trung bình điều hoà của P và R. Cân bằng hai bên |
| **F-beta** | F1 có trọng số. `beta > 1` ưu tiên recall, `beta < 1` ưu tiên precision |
| **IoU** | Diện tích giao / diện tích hợp. **Hai loại rất dễ lẫn**: IoU *dự đoán ↔ nhãn* (dùng chấm điểm model) và IoU *box lỗi ↔ polygon tấm pin* (dùng gán mã tấm). Cùng tên, khác việc |
| **mAP@50** | Điểm tổng hợp qua mọi ngưỡng conf, tính ở IoU ≥ 0,5 |
| **mAP@50-95** | Như trên nhưng lấy trung bình qua 10 mức IoU từ 0,50 đến 0,95 — khắt khe hơn nhiều về độ khít của box |
| **Ma trận nhầm lẫn** | Bảng *lớp thật × lớp đoán*. **Hàng/cột `background` là chỗ quan trọng nhất** — đó là nơi đọc ra bỏ sót và báo nhầm |
| **train / val / test** | Ba tập dữ liệu. Ở đây chia theo **nhóm chuyến bay**, không chia ngẫu nhiên |
| **Rò rỉ dữ liệu (leakage)** | Ảnh test lọt vào train → điểm số đẹp giả. Xảy ra thật trong dự án này |
| **Held-out** | Tập thật sự chưa từng thấy lúc train. Số sạch |
| **Bootstrap / KTC** | Lấy mẫu lặp để ra khoảng tin cậy cho chỉ số, thay vì một con số trần trụi |

> **Cảnh báo về mAP 0,965.** Con số này đo trên tập mà **81 % ảnh nằm trong train** của model
> (lệch bộ chia: model train trên `solar_cls4_final_ngaunhien`, báo cáo đo trên
> `solar_cls4_nhom/test`). Trên tập held-out thật là **0,974**; kỳ vọng ở một trang trại chưa
> từng bay khoảng **0,70**. Chạy `danh_gia_lai.py` để xem lại.

![Đường Precision-Recall của model trên tập test, mAP@0.5 = 0,965](../ket_qua/ket_qua_val/test_nhom/BoxPR_curve.png)

*Hình 15 — Đường **Precision–Recall**. Đọc: kéo recall lên thì precision tụt xuống. Diện tích
dưới đường chính là **mAP@50**. Bypass gần như hoàn hảo (0,995) vì vệt nóng cả dải rất dễ
nhận; SingleHotSpot thấp nhất (0,934). **Con số 0,965 ở đây là số đã bị rò rỉ tập chia** —
xem cảnh báo bên trên.*

![Đường F1 theo ngưỡng conf, đỉnh 0,92 tại conf 0,658](../ket_qua/ket_qua_val/test_nhom/BoxF1_curve.png)

*Hình 16 — **F1 theo ngưỡng conf**. Đỉnh ở conf **0,658**, F1 = 0,92. Nhưng dự án **cố tình
không chạy ở đỉnh này**: đẩy conf từ 0,25 lên 0,64 thì mất **146/603** lỗi mà chất lượng chỉ
nhích 2 điểm — trong 146 cái mất đi có **129 cái rơi đúng trong tấm pin**. Tức cứ dọn 1 box
ngoài tấm pin thì vứt nhầm 7,6 lỗi thật. Đây là ví dụ điển hình của **cái bẫy tối ưu F1**:
F1 coi FP và FN đắt ngang nhau, còn ngoài đồng thì không.*

![Ma trận nhầm lẫn của model trên tập test](../ket_qua/ket_qua_val/test_nhom/confusion_matrix.png)

*Hình 17 — **Ma trận nhầm lẫn**. Đường chéo là đoán đúng. Cột/hàng `background` cho biết bao
nhiêu lỗi thật bị bỏ sót và bao nhiêu nền bị báo nhầm thành lỗi.*

---

## 6. Đo sai số định vị

Khác hẳn nhóm trên: nhóm 5 đo **model tìm đúng lỗi không**, nhóm này đo **lỗi được đặt đúng
chỗ không**.

| Thuật ngữ | Nghĩa | Vì sao cần |
|---|---|---|
| **Trung vị** | Ca nằm giữa khi xếp thứ tự | Không bị vài ca cá biệt kéo lệch |
| **RMSE** | Căn trung bình bình phương sai số | Phạt **nặng** ca lệch to — che giấu ít nhất |
| **P90** | 90 % số ca nằm dưới mức này | Con số để **cam kết** với khách: "9/10 ca không tệ hơn ngần này" |
| **Sai số tương đối** | Độ khớp giữa ortho nhiệt và ortho màu — hai sản phẩm dựng từ **cùng một khối ảnh** | Đo được: **RMSE 2,56 cm** (ngưỡng đề bài 30 cm) |
| **Sai số tuyệt đối** | Lệch so với toạ độ GPS thật ngoài thực địa | **Chưa đo được** — không có GCP. Bị chặn bởi GPS drone, ~1–5 m nếu không RTK |
| **End-to-end** | Sai số của **cả chuỗi**: box trên ảnh nhiệt → toạ độ trên ortho → mã tấm pin | Đây mới là con số người dùng cuối gặp |
| **Báo động khống** | Model báo lỗi ở chỗ không có lỗi. Khác **FP** ở chỗ đôi khi lỗi có thật nhưng bị chiếu sai chỗ | Phải soi tay mới tách được hai loại |

> **Ba con số phải báo cùng nhau.** Chỉ báo trung vị thì giấu mất đuôi lệch; chỉ báo RMSE thì
> một ca hỏng nặng làm xấu cả bảng; chỉ báo P90 thì không biết đa số nằm ở đâu.

![Một box lỗi trên ảnh nhiệt, có chấm trắng và dấu thập lệch nhau 25 cm](../ket_qua/kiem_tra_warp/soi_lech_tam.jpg)

*Hình 18 — Sai số định vị nhìn tận mắt. Khung xanh là box lỗi (`D11-T185`, lớp Bypass, conf
0,64). **Chấm trắng** và **dấu thập** là hai cách tính tâm của cùng một box, lệch nhau
**25 cm** — đủ để nhảy sang tấm bên cạnh. Đây là loại sai số mà `do_sai_so_ortho.py` đi đo.*

![Sáu ca báo động khống trên ảnh nhiệt](_bao_dong_gia.png)

*Hình 19 — **Báo động khống**: sáu box conf cao (0,81 → 0,89) nhưng tấm bên trong không nóng
hơn tấm hàng xóm. Khung xanh lá ở ca giữa dưới là tấm nóng thật ngay cạnh — model bắt đúng
vùng nhưng gán sai tấm. Đây là kiểu lỗi mà chỉ số mAP **không** phản ánh được.*

![Bốn ca lỗi: trái là ảnh nhiệt gốc có box model tìm được, phải là vị trí đã chiếu lên ortho màu](hinh/h3_loi_that.jpg)

*Hình 20 — Toàn bộ chuỗi định vị gói trong một ảnh. **Trái** = ảnh nhiệt gốc, khung trắng là
box model tìm được. **Phải** = ortho màu, khung đỏ là 4 đỉnh box đó sau khi chiếu qua DSM. Ba
ca dưới có khung đỏ **méo thành hình bình hành** — hiệu ứng **off-nadir**: box chụp xiên chiếu
xuống không còn là hình chữ nhật.*

---

## 7. Từ riêng của repo này

Không có trong sách vở, chỉ dùng trong dự án — nhưng đọc code và báo cáo là gặp.

| Từ | Nghĩa | Bẫy |
|---|---|---|
| **`seq`** | Số thứ tự bấm máy, khoá ghép cặp nhiệt ↔ RGB | Ghép theo dòng CSV là sai, vì manifest đã lọc bỏ ảnh không align được |
| **`manifest_anh.csv`** | Danh mục 598 cặp ảnh | **598 = số camera Metashape align được**, không phải số ảnh đã chụp |
| **`--lech-tay`** | Nạp số căn tay cho `ghep_ortho_nhiet.py` | **Ghi đè** phép đo tự động |
| **`--bu-rgb`** | Bù lệch theo ảnh RGB | **Cộng dồn**. Nhầm với `--lech-tay` là bù gấp đôi |
| **`--cat-theo-nhiet`** | Xén lớp màu theo vùng phủ nhiệt trong công cụ gán nhãn | Bản đang dùng là bản **không** xén. Xén hay không **không đụng gì tới hình học** |
| **Nút *Ẩn rìa* (`B`)** | Ẩn 841 tấm rìa khỏi mọi danh sách | Dữ liệu **luôn dựng đầy đủ**, nút chỉ đổi hiển thị |
| **`nguon_nhiet`** | Chiếu ngược tâm tấm vào cả 598 camera để biết tấm đó có ảnh nào chụp tới không | Trả về 0 / 1 / 2: không ảnh nào / chỉ ảnh đã bị loại / ảnh đạt lọc vẫn thấy |
| **`loi_tu_anh_le.json`** | Bước trung gian — lỗi đã chiếu lên ortho, **chưa có mã tấm** | Đừng dùng làm đầu ra |
| **`loi_4lop_cuoi.json`** | **Đầu ra chính** — 603 lỗi, model 4 lớp, đã gán mã tấm | |
| **`loi_tren_ortho_nhiet.json`** | Nhánh cũ, model 8 lớp quét thẳng trên ortho, 211 lỗi | **Đã bỏ.** Model 8 lớp chỉ bắt 45,7 % lỗi và gán đúng lớp 22,9 %. Mọi số mAP/P/R trong báo cáo là của model **4 lớp** — trích số của model này gán cho model kia là sai |

---

## Một bảng để cạnh khi đọc báo cáo

| Gặp con số này | Nó là gì | Cạm bẫy |
|---|---|---|
| **2,56 cm** | RMSE độ khớp ortho nhiệt ↔ ortho màu | Là sai số **tương đối**. Không phải sai số GPS |
| **1–5 m** | Chặn trên của sai số GPS **tuyệt đối** | Chưa đo, chỉ suy ra từ việc không có RTK và 0 GCP |
| **0,965** | mAP@50 in trong báo cáo | Đo trên tập rò rỉ 81 %. Số dùng được: **~0,70** ở trang trại mới |
| **0,974** | mAP@50 trên held-out thật | Vẫn là cùng một trang trại |
| **0,897** | Recall tại conf **0,64** | Ngưỡng chạy thật là **0,25**, recall ở đó là **97,5 %** |
| **0,25** | Ngưỡng conf chốt | Không đổi. Lên 0,64 mất 146/603 lỗi |
| **598** | Số camera align được | Không phải số ảnh chụp |
| **396** | Số ảnh vào ortho nhiệt | 598 chụp → 416 detect chạy → 396 vào ortho |
| **603** | Số lỗi đầu ra chính | Model 4 lớp. Nhánh 8 lớp cũ chỉ có 211 |
| **6473 / 5632** | Số tấm pin trên bản đồ, hiện rìa / ẩn rìa | 841 tấm rìa không phán được gì |
| **224** | Số tấm thiếu nhiệt sau khi cắt rìa | **Không phải "tấm tốt"** mà là "chưa soi được". 119 trong đó moi lại được |
