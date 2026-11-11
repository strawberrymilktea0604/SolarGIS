# Thứ tự ghép ảnh nhiệt thành orthophoto

Tài liệu này trả lời một câu hỏi: **từ ảnh RGB và ảnh nhiệt rời rạc, cái gì chạy trước
cái gì, và các ảnh được ghép lại theo thứ tự nào?**

Mọi hình trong đây đều dựng từ dữ liệu thật của chuyến bay Thuận Nam 31 m
(598 cặp ảnh, DJI ZH20T) bằng `lam_hinh_thu_tu_ghep.py`. Số in trên hình là số chạy ra
lúc vẽ, không phải số gõ tay, nên hình và chữ không thể lệch nhau.

---

## Câu trả lời ngắn, trước khi vào chi tiết

Có **hai loại "thứ tự"** trong bài này, và trộn lẫn chúng là nguồn gốc của phần lớn
hiểu nhầm:

| | Có thứ tự không? |
|---|---|
| **Thứ tự các BƯỚC** — dựng ortho màu, hiệu chuẩn H, lọc ảnh, dựng ortho nhiệt | **Có**, và bắt buộc. Bước sau cần đầu ra của bước trước. |
| **Thứ tự các ẢNH** khi ghép | **Không có.** Ortho nhiệt không được dựng bằng cách dán ảnh này chồng lên ảnh kia. |

Điểm thứ hai là chỗ dễ hiểu sai nhất. Trực giác thông thường là: *lấy ảnh 0001 đặt lên
lưới, rồi ảnh 0002 đặt chồng lên, cứ thế đến ảnh 0598*. Cách đó gọi là **dán xuôi**, và
`ghep_ortho_nhiet.py` **không** làm như vậy.

Nó chạy **ngược chiều**: duyệt từng ô của lưới ortho, rồi với mỗi ô đi tìm xem giá trị
của nó nằm ở đâu trong ảnh nhiệt nào. Vì xuất phát từ ô cần điền chứ không từ ảnh, nên
mỗi ô được ghi **đúng một lần**, và **kết quả không phụ thuộc thứ tự duyệt ảnh** — đảo
thứ tự đọc 396 ảnh vẫn ra đúng file đó. Mục 8 đo cụ thể hai cách khác nhau ra sao.

---

## 1. Toàn tuyến

![Sơ đồ thứ tự chạy](hinh_thu_tu/h1_thu_tu_chay.png)

*Hình 1 — năm bước, đọc theo số. Bước 1 và bước 2 không cần nhau nên chạy song song được;
từ bước 3 trở đi thì bắt buộc tuần tự.*

Ba điều đáng chú ý ở sơ đồ này:

**Metashape chỉ nhìn thấy ảnh RGB.** Ảnh nhiệt 640 × 512 px quá thô để dò điểm đặc trưng
và ghép khối. Toàn bộ hình học — vị trí, hướng của từng lần bấm máy, mô hình độ cao — đều
dựng từ 598 ảnh RGB. Ảnh nhiệt chỉ tham gia ở bước cuối, với vai trò *nguồn cấp giá trị
pixel*, không tham gia dựng hình học.

**Ma trận H là thứ nối hai bên lại.** Có H rồi thì mọi phép định vị làm trên khung ảnh
RGB, xong mới đổi sang khung ảnh nhiệt bằng một phép nhân ma trận.

**Hai con số phủ.** Ortho nhiệt kín 98,6% *vùng bay* nhưng chỉ 44,4% *khung chữ nhật*.
Không mâu thuẫn: khung ortho là hộp bao chữ nhật của ảnh màu, còn tuyến bay là một hình
bình hành nghiêng nằm lọt bên trong (xem hình 8). Con số đáng dùng là 98,6%.

---

## 2. Vì sao ảnh nhiệt phải đi vòng qua ảnh RGB

![Cặp ảnh RGB và nhiệt](hinh_thu_tu/h2_cap_anh.png)

*Hình 2 — một lần bấm máy cho ra hai ảnh. Khung đỏ là phần mặt đất mà ảnh nhiệt nhìn thấy,
chiếu lên ảnh RGB qua ma trận H.*

Hai ống kính nằm cạnh nhau trên cùng một gimbal, chụp cùng một lúc, nhưng nhìn thấy hai
thứ khác nhau: ống nhiệt hẹp hơn nhiều, và tâm ảnh không trùng nhau. Ảnh nhiệt chỉ phủ
**18% diện tích khung RGB**.

Ma trận **H (3 × 3)** ánh xạ pixel ảnh nhiệt sang pixel ảnh RGB. Nó gắn với **thiết bị**,
không gắn với trang trại: chấm tay 31 cặp điểm một lần cho mỗi model drone là dùng được
cho mọi chuyến bay sau. Đừng chấm lại cho từng trang trại, và **đừng thử tự động hoá** —
hai hướng tự động (tương quan pha, ghép góc tấm pin) đã thử và hỏng vì lý do bản chất;
lý do ghi ở đầu `hieu_chuan_tu_dong.py`.

---

## 3. Thứ tự chụp, và những ảnh bị loại

![Đường bay và ảnh bị loại](hinh_thu_tu/h3_thu_tu_chup.png)

*Hình 3 — trái: thứ tự bấm máy, bay rắn bò từ nam lên bắc. Phải: 202 ảnh bị loại trước
khi ghép.*

Thứ tự chụp có ý nghĩa ở **một chỗ duy nhất**: nó cho biết ảnh nào chụp lúc drone đang
quay đầu. Ngoài ra nó không tham gia gì vào việc ghép.

Ba lớp lọc, áp theo đúng thứ tự này:

| Lớp | Bỏ | Vì sao |
|---|---|---|
| **Quay đầu** — tốc độ dưới 0,6 lần trung vị | 142 | Drone giảm tốc để đổi tuyến; sai số dọc trục rất lớn |
| **Lệch nhiệt–RGB** — `loc_anh_tre.py` đo trực tiếp | 57 | Ảnh lệch nửa mét đặt sai chỗ cả một vùng ortho |
| **Rung** — `loc_anh_rung.py` đọc tốc độ trong XMP | 3 | Hai cảm biến không nổ cùng lúc; bay đều thì H bù được, đang đổi tốc thì không |

Còn lại **396 / 598 ảnh**. Số bỏ ở hai lớp sau nhỏ vì phần lớn ảnh xấu đã bị lớp quay đầu
gạt trước rồi.

Điều đáng nói: **chỉ 27% ảnh quay đầu nằm ở hai mép** đông–tây của vùng bay, phần còn lại
rải khắp nhà máy; hai loại kia cũng vậy. Nên không thể lọc bằng cách cắt theo vị trí —
phải đo từng ảnh.

> **Lọc theo tốc độ bay đọc từ EXIF thì không thay được `loc_anh_tre.py`.** Đã kiểm chứng
> trên cả 598 ảnh: tốc độ EXIF không tách được ảnh lệch khỏi ảnh tốt. Nó chỉ bắt được
> đúng nhóm "rung" ở bảng trên, và nhóm đó chỉ có 3 ảnh.

---

## 4. Vì sao "lấy ảnh nào" là một câu hỏi thật

![Độ chồng phủ](hinh_thu_tu/h4_chong_phu.png)

*Hình 4 — mỗi điểm trên mặt đất được bao nhiêu ảnh nhiệt nhìn thấy.*

Trung vị **6 ảnh cùng nhìn thấy một chỗ**. Đây là con số nền cho hai chuyện:

- **Vì sao bỏ 202 ảnh mà ortho vẫn không thủng.** Chỗ nào cũng còn ảnh khác đỡ.
- **Vì sao phải chọn có chủ đích.** Sáu ảnh cùng phủ một ô nghĩa là có sáu câu trả lời
  khác nhau cho câu hỏi "ô này màu gì". Phải có quy tắc chọn, và quy tắc đó quyết định
  chất lượng ortho.

Quy tắc đang dùng: **ảnh có tâm chụp gần ô đó nhất**. Lý do là ở tâm ảnh thì tia nhìn gần
thẳng đứng nhất, nên sai số do sai lệch độ cao là nhỏ nhất; càng ra rìa ảnh, tia càng
xiên và một sai số độ cao nhỏ càng đẩy điểm đi xa.

---

## 5. Chuỗi tính cho MỘT ô lưới

![Chuỗi bảy bước cho một ô](hinh_thu_tu/h5_chuoi_mot_o.png)

*Hình 5 — bảy bước, với số thật chạy ra cho một ô cụ thể.*

Đây là hạt nhân của cả pipeline, lặp lại 8451 × 4997 ≈ **42 triệu lần**:

1. **Ô lưới** — cột, hàng trên lưới ortho nhiệt
2. **Toạ độ địa lý** — nhân với ma trận affine của lưới
3. **Cao độ** — tra DSM **riêng cho từng ô**, không giả định mặt phẳng
4. **Điểm 3D** — đổi (lon, lat, z) sang toạ độ ECEF, rồi về hệ toạ độ của Metashape
5. **Chiếu vào ảnh RGB** — qua ma trận camera của ảnh đã chọn, ra pixel (u, v)
6. **Sang ảnh nhiệt** — nhân với **H⁻¹**, ra pixel (u′, v′)
7. **Nội suy song tuyến** — bốn pixel lân cận, cân theo phần thập phân

Bước 3 là chỗ tách phương pháp này khỏi cách dán xuôi. Tấm pin cao hơn mặt đất 1–2 m;
tra DSM cho từng ô thì bám được, giả định mặt phẳng thì không (mục 8).

**Hai điều làm nó chạy trong vài phút thay vì vài giờ.** Thứ nhất, độ phân giải đầu ra
đặt theo ảnh **nhiệt** (2,87 cm/px), không phóng to vô ích lên 0,96 cm/px của ortho màu.
Thứ hai, mỗi ô chỉ thử với ảnh gần nhất trước, tìm bằng **cây KD**; chỉ khi ảnh đó không
chứa ô cần lấy mới thử ảnh kế tiếp, tối đa 24 ứng viên. Toàn bộ phép tính vector hoá bằng
numpy theo lô 2048 × 2048 ô.

---

## 6. Ai cấp giá trị cho ô nào

![Bản đồ nguồn](hinh_thu_tu/h6_ban_do_nguon.png)

*Hình 6 — trái: mỗi màu là một ảnh nguồn, nhãn là số thứ tự ảnh. Phải: ortho nhiệt dựng ra
từ chính phép chia đó. Vùng 25 × 19 m ở giữa nhà máy.*

Đây là hình trả lời trực tiếp câu hỏi "ghép theo thứ tự nào":

**Không có thứ tự. Có một phép chia.** Lưới ortho được chia thành các mảnh, mỗi mảnh về
tay một ảnh — mảnh gồm những ô có tâm chụp của ảnh đó gần nhất. Ranh giới giữa hai mảnh là
đường trung trực của đoạn nối hai tâm chụp; đó là lý do các mảnh trông như tổ ong.

Đọc nhãn trên hình thấy rõ cấu trúc chuyến bay: hàng trên là 0249 → 0255 (một tuyến bay),
hàng giữa 0305 → 0298 (tuyến kế tiếp, **ngược chiều**), hàng dưới 0345 → 0352. Đúng kiểu
bay rắn bò ở hình 3.

Hệ quả thực tế: **mỗi ô được ghi đúng một lần, và đảo thứ tự đọc ảnh vẫn ra đúng file đó.**
Không có chuyện "ảnh dán sau đè lên ảnh dán trước".

---

## 7. Cân bằng sáng giữa các ảnh

![Cân bằng sáng](hinh_thu_tu/h7_can_sang.png)

*Hình 7 — dựng cùng một vùng hai lần, chỉ khác bật/tắt cân bằng sáng, rồi đo bước nhảy tại
mép ghép.*

Ảnh nhiệt đọc bằng `IMREAD_GRAYSCALE` là ảnh **hiển thị** 8-bit do DJI dựng, đã qua tự
chỉnh gain **riêng cho từng ảnh** — không phải nhiệt độ tuyệt đối. Trung vị độ sáng của
396 ảnh trải từ 68 đến 155. Vì giá trị vốn đã không mang nghĩa nhiệt độ, kéo chúng về cùng
một thang (trung vị + khoảng tứ phân vị → mốc chung) **không làm mất thông tin vật lý nào**.

**Nhưng đo thì thấy nó không phải thứ làm mối ghép biến mất.** Bước nhảy giữa hai ô kề nhau
lấy từ hai ảnh khác nhau: **18,1 khi tắt, 17,7 khi bật** — gần như không đổi. Đo thêm hai
cửa sổ khác khắp nhà máy cũng vậy (19,2 → 20,1 và 24,3 → 22,7; có chỗ còn xấu đi chút).

Lý do: bước nhảy tại mép ghép gấp khoảng 4 lần bước nhảy trong lòng ảnh, tức mép ghép đúng
là có đứt đoạn thật — nhưng đứt đoạn đó do **hình học**, không do gain. Ảnh **kề nhau** vốn
nhìn gần cùng một cảnh nên gain của chúng đã sát nhau sẵn (chênh trung vị chỉ 5–7 mức xám),
trong khi mép ghép chỉ nối những ảnh kề nhau. Cân bằng sáng chỉ thực sự có nghĩa khi phải
đặt cạnh nhau hai ảnh ở hai đầu chuyến bay.

Kết luận thực dụng: **giữ bước này** — nó rẻ và chống được trường hợp xấu — nhưng đừng
trông đợi nó xoá mối ghép, và đừng đổ lỗi cho nó khi ortho có sọc.

---

## 8. Nếu làm theo thứ tự ảnh: dán xuôi

![Dán xuôi so với đi ngược](hinh_thu_tu/h9_xuoi_va_nguoc.png)

*Hình 8 — cùng vùng, cùng lưới, cùng 396 ảnh, cùng cân bằng sáng. Khác duy nhất là chiều
chạy.*

Dán xuôi là cách trực giác: lấy 4 góc ảnh nhiệt → qua H → tia → cắt mặt phẳng → 4 ô lưới;
có 4 cặp điểm thì tìm được một phép biến đổi phối cảnh, warp cả ảnh lên lưới rồi dán.

Ba khác biệt về **bản chất**, không phải lựa chọn cài đặt:

**Thứ nhất — phải giả định mặt phẳng.** Một phép biến đổi phối cảnh chỉ mô tả được ánh xạ
giữa hai *mặt phẳng*. Cả vùng ảnh phủ buộc phải coi như nằm ở cùng một cao độ. Tấm pin cao
hơn mặt đất 1–2 m nên bị đặt sai chỗ. Bản đồ chênh ở hình 8 sáng lên **đúng ở mép các dãy
pin** — chính là chỗ độ cao đổi đột ngột. Trung vị chênh giữa hai cách là 24,2 mức xám;
55,6% số ô chênh quá 20.

**Thứ hai — kết quả phụ thuộc thứ tự duyệt.** Ở vùng thử, **mọi ô đều bị ghi lại nhiều
lần**, chỗ nhiều nhất **11 lần**, và chỉ lần cuối được giữ. Nghĩa là ảnh nào được chọn cho
một ô là do nó tình cờ đứng sau trong vòng lặp, chứ không do nó phù hợp hơn. Đổi thứ tự đọc
ảnh là ra ortho khác.

**Thứ ba — phí công.** Phải warp toàn bộ ảnh lên lưới rồi vứt phần thừa.

Đi ngược không mắc cả ba: tra DSM cho từng ô nên bám được địa hình, chọn ảnh **có chủ đích**
theo tâm chụp gần nhất, và chỉ tính đúng những ô cần điền.

> Nhánh "đi ngược" trong `minh_hoa_dan_xuoi.py` tra DSM sai (gán `rowd` rồi mới lấy `cold`
> từ `rowd` đã bị ghi đè, nên chỉ số cột lấy nhầm giá trị hàng), vì vậy hình 8 ở đây dựng
> lại bằng chính đoạn mã đã dùng cho hình 6 và 7 chứ không lấy `kiem_tra_warp/so_dan_xuoi.jpg`.

---

## 9. Kết quả

![Ortho nhiệt toàn nhà máy](hinh_thu_tu/h8_ket_qua.png)

*Hình 9 — ortho nhiệt toàn nhà máy, và phóng to đúng vùng đã chia ở hình 6.*

`ortho_nhiet_tu_lam.tif` — 8451 × 4997 px, GSD 2,87 cm, ghép từ 396 ảnh nhiệt, kín 98,6%
vùng bay. Ở mức phóng to của hình 6, 27 ảnh ghép lại mà không còn nhìn ra mối nối.

Sai số đặt chỗ end-to-end đo được trên ortho này là **RMSE 2,56 cm** (ngưỡng đề bài 30 cm).

---

## 10. Chạy lại

```bash
# 1. Dựng ortho + DSM + cameras.xml bằng Metashape từ ảnh RGB
#    -> Thermal2_31M_full_export/

# 2. Chấm H — CHỈ MỘT LẦN CHO MỖI MODEL DRONE, có H rồi thì bỏ qua
python ma/calib_thermal_rgb.py --thermal ..._T.JPG --rgb ..._W.JPG --xml cameras.xml --alt 31

# 3. Lọc ảnh
python ma/loc_anh_tre.py          # đo trực tiếp, ~45 phút cho 598 ảnh
python ma/loc_anh_rung.py         # đọc EXIF, 3 giây

# 4. Dựng ortho nhiệt (tự nối hai bộ lọc trên)
python ma/ghep_ortho_nhiet.py

# vẽ lại toàn bộ hình của tài liệu này
python ma/lam_hinh_thu_tu_ghep.py
python ma/xuat_pdf.py --vao THU_TU_GHEP_ORTHO.md --ra THU_TU_GHEP_ORTHO.pdf
```

**Một lưu ý về hình.** `ghep_ortho_nhiet.py` khi chạy thật còn bù lệch **riêng từng ảnh**
(dùng dx, dy mà `loc_anh_tre.py` đã đo sẵn — sai số đặt chỗ giảm từ 14,1 xuống 4,3 cm trên
275 cửa sổ). Các hình 6, 7, 8 ở trên dựng **không** có bước bù đó, vì bù lệch dịch nội dung
đi vài pixel chứ không đổi việc ô nào lấy từ ảnh nào — tức không đổi điều mà các hình này
muốn nói. Ortho ở hình 9 thì có bù, vì đó là file thật.
