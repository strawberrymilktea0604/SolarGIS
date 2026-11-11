---
title: "Bay toàn cảnh một lần, bay khảo sát nhiều lần — có ai làm chưa?"
subtitle: "Rà soát tình trạng nghiên cứu cho thiết kế bay hai pha trong khảo sát nhiệt tấm pin bằng UAV"
date: "24/08/2026"
lang: vi
---

> **Cách rà.** 61 bài toàn văn trong `tai_lieu/bai_bao_lien_quan/pdf/` (trích chữ bằng
> `pdftotext`, đối chiếu từng câu với bản gốc để xác nhận số trang) + 80 mục trong
> `bai_bao.bib` + 12 lượt tra ngoài kho. Mọi phát hiện đều đi qua một vòng **phản biện đối
> kháng**: mỗi bài được khai là "đã làm đúng ý này" bị giao cho một agent khác với nhiệm vụ
> *bác bỏ*. **Toàn bộ 5 bài được khai ban đầu đều bị hạ xuống "gần giống, khác ở chỗ X"** —
> không bài nào sống sót.
>
> Mọi tiêu đề bài dưới đây **bấm được**, mở thẳng trang bài báo. Các hình ghi **"Cắt từ bài"**
> là ảnh gốc lấy thẳng từ PDF của chính bài đó (cắt bằng `bai_bao_lien_quan/ma/cat_hinh.py`),
> kèm số hình và số trang để đối chiếu; các hình còn lại do tài liệu này dựng.

---

# 1. Trả lời ngắn

Hai câu, và cả hai đều quan trọng:

1. **Ý tưởng không mới.** Nó đã có **tên chuẩn** trong ngành từ 2017, đã được chuẩn hoá thành
   một *lớp* phương pháp trong một bài tổng quan bình duyệt năm 2023, và đã nằm trong **hai
   sáng chế** từ 2016–2017.
2. **Nhưng trong ngành PV thì chưa ai bay thật cả hai pha.** Bài duy nhất đề xuất đúng thiết
   kế này chưa từng bay nó; chính nhóm tác giả đó đã bỏ hướng này ở bài kế tiếp.

![](hinh/bay_b1_ai_bay_that.png)

*Hình 1 — Bốn thiết kế bay đặt trên cùng một trục độ cao. Nét liền = đã bay thật. Nét đứt,
rỗng ruột = chỉ có trên giấy. Cột 1 và cột 2 là **cùng một bài**: bên trái là thứ bài đề xuất,
bên phải là thứ bài thực sự bay.*

---

# 2. Ý tưởng đã có tên chuẩn từ bao giờ

![](hinh/bay_b3_dong_thoi_gian.png)

*Hình 2 — Ý tưởng "phủ nhanh rồi soi kỹ" đã được đặt tên và cắm cờ trước khi ngành PV chạm
tới. Xanh lam = tên chuẩn của phương pháp, tím = sáng chế, gỉ = riêng ngành PV.*

**Tên phải dùng, theo thứ tự ưu tiên khi viết bài:**

| # | Tên chuẩn | Nguồn đặt tên |
|---|---|---|
| 1 | **explore-then-exploit** ← phổ biến nhất | [Roberts et al., *Submodular Trajectory Optimization for Aerial 3D Scanning*, ICCV 2017](https://arxiv.org/pdf/1705.00703) — §3: *"we adopt an explore-then-exploit approach"* |
| 2 | model-based path planning · **geometric proxy** | [Maboudi et al., *A Review on Viewpoints and Path-planning for UAV-based 3D Reconstruction*, IEEE JSTARS 2023](https://arxiv.org/pdf/2205.03716) — §2.3, chuẩn hoá thành một LỚP, có Figure 2 riêng |
| 3 | **two-phase inspection** | Khan et al., *Investigation on Bridge Assessment Using Unmanned Aerial Systems*, ASCE Structures Congress 2015, tr. 404–413 — ngành NDE cầu; dẫn lại trong [Shang, Cheng & Shen, i3CE 2019](https://arxiv.org/pdf/1904.04986) |
| 4 | multi-scale / **tiered view planning** | [Okeson et al., *Achieving Tiered Model Quality… Multi-Scale View-Planning*, Sensors 19(14), 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6630767/) |
| 5 | **RIBC** / anchor images / reference epoch — cho khâu đăng ký chuyến sau vào chuyến đầu | [Aicardi et al., *Co-registration of Multitemporal UAV Image Datasets for Monitoring Applications*, ISPRS Archives XLI-B1:757–762, 2016](https://isprs-archives.copernicus.org/articles/XLI-B1/757/2016/isprs-archives-XLI-B1-757-2016.pdf) |

**Hai sáng chế đã cắm cờ:**

- [**US 11,156,573 B2** — Skydio](https://patents.google.com/patent/US11156573B2/en), *Solar panel
  inspection using unmanned aerial vehicles*, ưu tiên 30/6/2016 — hai độ cao, so với bản đồ
  nhiệt lần trước. (Bản nối tiếp: [US 11,567,019 B2](https://patents.google.com/patent/US11567019B2/en))
- [**US 11,451,192 B2** — Acciona](https://patents.google.com/patent/US11451192B2/en),
  *Automated photovoltaic plant inspection system and method*, ưu tiên 14/12/2017 — CSDL định
  danh tấm + CSDL lỗi lịch sử.

> **Điều tuyệt đối không được viết:** *"we propose a novel two-stage flight design"* hay
> *"chúng tôi đề xuất chiến lược bay tổng quan rồi bay chi tiết"*. Reviewer nào đọc mảng UAV
> path planning cũng bắt được ngay.
>
> **Cách viết an toàn:** nhận nó là paradigm đã có, rồi chỉ rõ mình đổi cái gì —
> *"We adopt the established explore-then-exploit paradigm [Roberts 2017; Maboudi 2023], but
> repurpose the exploration output from a viewpoint-planning proxy into a georeferenced asset
> inventory…"*

---

# 3. Trong PV: bài đề xuất đúng ý này chưa từng bay nó

### [Løfstad-Lie, Marstein, Simonsen & Skauli (2022) — *Cost-Effective Flight Strategy for Aerial Thermography Inspection of Photovoltaic Power Plants*, IEEE J. Photovoltaics 12(6):1543–1549](https://doi.org/10.1109/JPHOTOV.2022.3202072)

*Bản trong kho: `bai_bao_lien_quan/pdf/10_2022_v_cost_effective_flight_strategy_for.pdf` ·
bản hội nghị PVSC 2021: [doi:10.1109/PVSC43889.2021.9518710](https://doi.org/10.1109/PVSC43889.2021.9518710)*

**Họ đề xuất đúng thiết kế em hỏi:** tầng thăm dò bay cao 80 m theo lawn mower quét nhanh toàn
nhà máy *chỉ để phát hiện*, rồi tầng phân loại dùng thuật toán đàn kiến (ACO) tính lộ trình gần
tối ưu quay lại chụp thấp 20 m đúng từng điểm đã phát hiện. Ước tính 4 + 7 = **11 phút**, giảm
58 % so lawn mower (26 phút) và 66 % so bay từng hàng (32 phút); điểm hoà vốn ở mật độ lỗi 2 %
(nhà máy dày) và 3 % (nhà máy thưa).

![](bai_bao_lien_quan/hinh/h10_bay_hai_tang.png)

*Hình 3 — **Cắt từ bài, Fig. 3 tr. 1547.** Bên trái là lawn mower thường: đường bay phủ đều
toàn nhà máy bất kể lỗi nằm đâu. Bên phải là hai tầng: vàng nhạt là tầng thăm dò bay cao phủ
thưa, nâu đậm là tầng phân loại chỉ ghé những điểm đã phát hiện. Chấm đỏ là lỗi — ở mật độ
0,5 % thì đa số diện tích nhà máy không cần bay thấp chút nào, đó là toàn bộ lý lẽ của bài.*

![](hinh/bay_b2_cho_dut_2022.png)

*Hình 4 — Chỗ đứt. Hàng trên là thứ bài định làm, hàng dưới là thứ thực sự chạy. Mũi tên đứt
màu gỉ là chỗ thay thế: đầu ra của bộ dò chạy trên ảnh 20 m được **coi như** đầu ra của tầng
80 m.*

**Chỗ đứt, nguyên văn tr. 1545 mục V:**

> *"For this initial evaluation of the proposed concept, we use high-resolution imagery of the
> entire plant recorded from an altitude of 20 m to get a sufficient module resolution for
> defect classification."*

và tr. 1547:

> *"a fast flight at 80 m with a velocity of 5 m/s for the exploration phase would require only
> 4 min to cover the plant area. **The automatic detections in Fig. 5(a) are taken to represent
> the output of this first stage.**"*

Tức toàn bộ **93 phát hiện** làm đầu vào cho ACO đều sinh từ ảnh **20 m**. Độ bền phát hiện ở
80 m chỉ được **lập luận bằng vật lý cảm biến** (2×2 px/cell × 20 cell = 800 pixel, NETD
~70 mK) — không một con số recall nào. Họ **đã có ảnh 80 m trong tay**: Hình 1 tr. 1546 so cùng
một hotspot chụp ở 30 m và 80 m để chứng minh vết nhoè gấp đôi diện tích (1,6 % → 3,3 %) —
nhưng không hề chạy bộ dò blob lên chính bộ ảnh đó.

![](bai_bao_lien_quan/hinh/h10c_hotspot_30m_vs_80m.png)

*Hình 5 — **Cắt từ bài, Fig. 1 tr. 1546. Đây là bằng chứng họ ĐÃ CÓ ảnh 80 m.** Cùng một
hotspot, (a) chụp ở 30 m và (b) chụp ở 80 m; vết nóng phình từ 1,6 % lên 3,3 % diện tích tấm do
pixel bị trung bình hoá. Hình này được dùng để **giải thích** vì sao ở 80 m vẫn phát hiện được
— nhưng bộ dò blob chưa từng được chạy lên chính bộ ảnh 80 m ấy.*

![](bai_bao_lien_quan/hinh/h10b_duong_bay_toi_uu_theo_loi.png)

*Hình 6 — **Cắt từ bài, Fig. 5 tr. 1548.** Đây đúng là hình mà câu trích tr. 1547 chỉ tới:
"the automatic detections in Fig. 5(a)". Chấm xanh là lỗi đã phát hiện, đường vàng là lộ trình
ACO cho lượt bay thấp. (a) toàn bộ phát hiện, (b) và (c) là mẫu rút ngẫu nhiên xuống mật độ
1 % và 0,5 %. Toàn bộ chấm xanh trong (a) sinh từ **ảnh 20 m**, không phải từ một lượt bay 80 m.*

**Lỗi bị bỏ sót ở tầng 1 thì tầng 2 vĩnh viễn không thấy.** Nên mọi con số tiết kiệm thời gian
của bài đều treo vào một phép đo họ chưa làm.

**Hai chỗ hở nữa cùng bài:**

- Mô hình chi phí chỉ rải tấm **lỗi thật**, không có số hạng nào cho dương tính giả — trong khi
  chính thí nghiệm của họ cho danh sách quay lại dài hơn danh sách lỗi thật 15 % (93 so với
  81), và 24/93 mục tiêu (25,8 %) không phải lỗi đủ tiêu chuẩn IEC. Ở 80 m, nơi tầng thăm dò
  chỉ có 2×2 pixel/cell, tỉ lệ FP còn cao hơn nhưng chưa ai đo.
- Recall 85 % được đo bằng cách cho người soi lại **chính bộ ảnh 20 m** mà bộ dò đã chạy —
  không đo I-V, không điện phát quang, không đối chiếu nhật ký O&M. Mẫu số 81 là *"số hotspot
  một người nhìn thấy trên chính bộ ảnh đó"*, không phải *"số hotspot có trong nhà máy"*.

---

# 4. Chính nhóm đó đã bỏ hướng hai tầng

### [Løfstad-Lie, Simonsen, Nygaard & Marstein (2025) — *Data Quality Analyses for Automatic Aerial Thermography Inspection of PV Power Plants*, IEEE J. Photovoltaics 15(5):722–731](https://doi.org/10.1109/JPHOTOV.2025.3587297)

*Bản trong kho: `bai_bao_lien_quan/pdf/09_2025_v_data_quality_analyses_for_automatic.pdf`*

Bài 2025 trích bài 2022 **đúng một lần** (ref [28], tr. 730) và chỉ để dẫn *"a detection
tracking algorithm"* — không một câu nào nhắc lại, đánh giá hay đo chiến lược hai tầng. Họ
chuyển sang **một độ cao + bầy 4 UAV**.

Và "ba lượt" của họ **nằm trong một chuyến bay** — ba hàng tấm lọt cùng khung nên mỗi hàng được
chụp ba lần từ ba đường bay khác nhau. Nguyên văn tr. 728 mục III-D:

> *"During the inspection, three module rows were imaged simultaneously, ensuring that each row
> was captured three times for robustness analyses. **This setup is equivalent to a scenario
> where the PV power plant is inspected in three separate flights**, with each module row being
> imaged once per flight."*

Kết quả đối chiếu 131 lỗi chuẩn: **91 bắt được ở cả ba lượt, 30 ở hai lượt, 7 ở một lượt, 3
không bắt được** — rồi để đó, không rút ra luật gộp nào.

![](bai_bao_lien_quan/hinh/h09b_bay_bay_ba_hang.png)

*Hình 7 — **Cắt từ bài, Fig. 7 tr. 727.** Dấu × trắng là 131 lỗi chuẩn chấm tay; chấm **đỏ, cam
và xanh** là phát hiện tự động của **ba lượt** — nhưng ba lượt ấy nằm trong cùng một chuyến bay,
vì ba hàng tấm lọt cùng khung. Đây là toàn bộ dữ liệu ba lượt mà ngành hiện có. Ô phóng to trên
cùng ghi thẳng nguyên nhân bỏ sót: "The automatic detections miss with one whole module row" —
lệch dẫn đường làm rơi hẳn một hàng. Ô thứ hai là loá nắng gây dương tính giả. Họ dừng ở mô tả
định tính, không rút ra luật gộp n/N nào.*

**Điểm vàng cho dự án** — tr. 728, họ tự viết ra đúng thứ dự án đang làm rồi **từ chối làm**:

> *"To account for terrain variations, a digital elevation model correction could be used, with
> ray tracing to determine the altitude at the detections. **However, this will require more a
> priori data for each specific park to be imaged.**"*

Dữ liệu tiên nghiệm đó dự án **đã có sẵn**: DSM dựng từ bộ Mapping1 RGB 16,6 ha, cùng site cùng
ngày. Kết luận của chính họ (tr. 730): model vẫn khoẻ tới 80–100 m, **thứ chặn lại là sai số
định vị chứ không phải năng lực mạng**.

![](bai_bao_lien_quan/hinh/h09_chat_luong_do_cao.png)

*Hình 8 — **Cắt từ bài, Fig. 6 tr. 726.** Sai số định vị theo cự ly chụp, tách riêng hướng Bắc
(cắt ngang các hàng, trên) và hướng Đông (dọc theo hàng, dưới). Đường gạch ngang là mốc quy đổi
ra số hàng tấm — 1 hàng = 9,3 m. **Flight 1** chúc 90° giữ sai số dưới 5 m suốt 10–80 m;
**Flight 2** chúc 65° chạm mốc một hàng quanh 130–150 m; **Flight 3** chúc 20° leo tới ~37 m,
gần bốn hàng, ở cự ly ~210 m. Đây là hình chở luận điểm chính của bài: ở cự ly lớn model vẫn
phát hiện được, chỗ vỡ là khâu quy lỗi về **đúng tấm**. Lưu ý vị trí thật ở đây là chấm tay trên
ảnh vệ tinh Google Earth, sai số của chính cái thước đó không được báo ở đâu.*

---

# 5. Những bài từng bị nghi là "đã làm rồi" — và vì sao đều không phải

Cả năm bài dưới đây ban đầu được khai là *"đã làm đúng ý này"*, và cả năm đều bị vòng phản biện
hạ xuống *"gần giống, khác ở chỗ X"*.

| Bài | Vì sao KHÔNG phải |
|---|---|
| [López-Fernández et al. (2017), *Automatic Evaluation of Photovoltaic Power Stations from High-Density RGB-T 3D Point Clouds*, Remote Sensing 9(6):631](https://doi.org/10.3390/rs9060631) | Đăng ký nhiệt vào nền là **bấm tay từng ảnh** (*"interactive identification of homologous entities"*) — không tự động, không dùng H, không dùng pose. Chỉ 2 chuyến cùng đợt, không lặp lại. Không báo sai số đăng ký nhiệt-so-với-nền. Nền dựa vào 9 GCP đo GNSS. |
| [Hernández-López et al. (2023), *SunMap: Towards Unattended Maintenance of Photovoltaic Plants Using Drone Photogrammetry*, Drones 7(2):129](https://doi.org/10.3390/drones7020129) | Hai chuyến Albacete được đưa vào **một bình sai chùm tia chung**, không phải "đăng ký chuyến sau vào nền chuyến trước" — chuyến sau bay ngày khác thì chuỗi này không chạy. Chỉ **một** chuyến nhiệt. Không có con số sai số định vị nào. |
| [Zefri et al. (2018), *Thermal Infrared and Visual Inspection of Photovoltaic Installations by UAV Photogrammetry — Application Case: Morocco*, Drones 2(4):41](https://doi.org/10.3390/drones2040041) | Mục đích là **so sánh GSD**, không phải chiến lược hai tầng: hai độ cao cho ra hai orthomosaic riêng rồi so định tính bằng mắt, không lượng hoá, không gộp, không tầng nào nuôi tầng nào. Hai độ cao 6 m và 11,5 m — cách dải 31/35/42 m của dự án một bậc. Có 5 GCP. |
| [Bommes et al. (2022), *Georeferencing of photovoltaic modules from aerial infrared videos using structure-from-motion*, Prog. Photovolt. 30(9):1122–1135](https://doi.org/10.1002/pip.3564) | Ba chuyến để **so sánh**, không để **gộp** — không có bước hợp nhất kết quả ba độ cao. Chỉ 12 hàng, không phải toàn nhà máy. Ortho RGB của họ đóng vai **chân lý nền**, không phải **nền hình học** — đúng chỗ dự án đổi vai. |
| [del Prado Santamaría et al. (2025), *Influence of irradiance and drone altitude in infrared thermography inspections of photovoltaic plants*, EPJ Photovoltaics 16:31](https://doi.org/10.1051/epjpv/2025020) | Là **băng thử 43 tấm hỏng chủ động**, không phải khảo sát nhà máy: không recall, không precision, không định vị, không ortho. Trần độ cao là **20 m / 3 cm-pixel** — chính bài tự khai đó là biên khảo sát, tức **dải 31/35/42 m của dự án nằm ngoài hẳn vùng đã đo**. |

---

# 6. Ba trục còn trống

![](hinh/bay_b4_ba_truc.png)

*Hình 9 — Sáu tiêu chí × sáu công trình. Chấm đặc = có làm và có số; vòng rỗng = có nhưng
không đo; dấu chéo = không có. Ba dòng tô nền là ba trục chưa ai lấp.*

1. **Vai trò pha một đổi.** Trong văn liệu, đầu ra pha một **luôn** là *geometric proxy*
   (mesh / point cloud / voxel) dùng để **lập kế hoạch điểm chụp** cho pha hai — Maboudi et al.
   §2.3.1 liệt kê đúng ba dạng proxy này và **không dạng nào là danh sách đối tượng**. Ở dự án,
   nền dùng để **đánh số 6473 tấm** và làm khung đăng ký, còn đường bay pha hai giữ nguyên lưới
   nadir. Đây là thay đổi về **vai trò** của nền, không phải về số chuyến bay.
2. **Chéo phổ: nền RGB, đo bằng NHIỆT.** Không tìm thấy tiền lệ trong nhánh explore-then-exploit.
3. **N sortie đa độ cao (31/35/42 m) cùng đăng ký vào một nền, kèm đo recall theo độ cao.**
   Văn liệu explore-then-exploit hầu như luôn là 1 explore + 1 exploit. Okeson 2019 có ba mức
   khoảng cách 15/30/60 m nhưng để đạt **chất lượng mô hình** theo tầng, không đo tỉ lệ phát
   hiện.

Thêm một điểm phân biệt quan trọng: toàn bộ văn liệu explore-then-exploit (Roberts 2017,
Peng & Isler 2019, Okeson 2019, Maboudi 2023) lấy **mục tiêu là chất lượng tái dựng 3D**, không
phải tỉ lệ phát hiện lỗi. Chỗ dự án khác là **mục tiêu của pha hai**, không phải hình dạng
đường bay.

**Và không một bài PV nào — trong hay ngoài kho — báo sai số đăng ký "chuyến thứ N so với chuyến
thứ 1".** Ngược lại, ngoài PV (địa mạo học, công trường) mạch này đã chín và có số đầy đủ:
Aicardi 2016 báo 2–8 cm; [Cook & Dietze 2019, Earth Surf. Dynam. 7:1009](https://esurf.copernicus.org/articles/7/1009/2019/)
báo 15–20 cm. Nên **chỉ được nhận**: *lần đầu làm việc đó trên nhà máy PV, nối xuống từng tấm,
bằng ảnh nhiệt.*

---

# 7. Bốn cảnh báo trước khi viết

**(1) 13 sortie trên Drive đều cùng một ngày.** Nhánh "bay lại theo thời gian" (multi-temporal,
theo dõi tiến triển lỗi) **không lập được** bằng dữ liệu hiện có — chỉ lập được nhánh **độ
cao**. Đừng viết bài như thể có dữ liệu đa thời điểm; muốn có thì phải bay thêm, không có đường
tắt.

**(2) Dự án đang ở tình huống "hai pha đã bay xong rồi".** Mapping1 RGB và 598 ảnh nhiệt cùng
site cùng ngày — không phải tình huống "pha một dẫn đường cho pha hai được lập kế hoạch". Muốn
gọi là *explore-then-exploit* thật sự thì phải có **ít nhất một chuyến bay sau được lập kế
hoạch từ nền**. Nếu không, gọi đúng tên khác: *multi-temporal co-registration to a reference
epoch* (Aicardi 2016), hoặc *data fusion through geo-referencing* (Shang 2019). **Gọi sai tên
sẽ bị bắt.**

**(3) Bài tổng quan mới nhất khuyên NGƯỢC với thiết kế đa độ cao.**
[Lee & Lee (2026), *High-Resolution Thermal Mapping for Quantitative UAV–TIR Applications*,
Aerospace 13(5):430](https://doi.org/10.3390/aerospace13050430) — bài [35] trong kho:

> *"Consistent altitude improves geometric consistency and maintains stable ground-sampling
> distance"* (tr. 11) · *"Flight height, angle, speed, and time of day should be kept as
> consistent as the application allows"* (tr. 15)

Nếu dự án gộp 31/35/42 m vào một khối thì **phải phản biện trực diện câu này**, hoặc phải đóng
khung lại: mỗi sortie dựng riêng, chỉ **đăng ký** vào một nền chung — không trộn vào một bundle.

**(4) Lợi ích đa sortie phải phát biểu ở mức PHIẾU BẦU, không phải trung bình hoá.** Ortho nhiệt
của dự án là **winner-take-all một ảnh trên mỗi pixel**, không trộn trung bình. Nên lợi ích của
đa sortie phải nói ở mức *n trên N sortie cùng thấy một phát hiện*, không phải ở mức "gộp nhiều
chuyến giúp lấy trung bình nhiễu" — nếu không sẽ lặp lại đúng lỗi tiền đề đã mắc ở các mục 7.3,
8 và 10 cũ.

---

# 8. Việc làm được ngay

| Việc | Dữ liệu cần | Trạng thái |
|---|---|---|
| Đo recall theo độ cao ở 31 / 35 / 42 m — đúng phép đo Løfstad-Lie 2022 thiếu | 3 sortie nhiệt trên Drive | **chưa tải** |
| Dựng bản đồ độ phủ: mỗi tấm trong 6473 được bao nhiêu sortie quét | manifest + nền Mapping1 | làm được ngay |
| Đo sai số đăng ký "sortie thứ N so với nền" — con số chưa bài PV nào báo | nền Mapping1 + sortie nhiệt | làm được ngay sau khi tải |
| Luật gộp theo phiếu bầu n/N — thứ Løfstad-Lie 2025 tạo ra dữ liệu rồi bỏ đó | ≥2 sortie cùng vùng | **chưa tải** |

---

*Rà soát 24/08/2026 · 19 agent · 61 PDF toàn văn + 12 lượt tra ngoài · mọi phát hiện đã qua
phản biện đối kháng. Hình dựng bằng `ma/hinh_bay_hai_tang.py`.*

*Cảnh báo về phương pháp: bộ tóm tắt của WebFetch **bịa trích dẫn** — với bài Pech 2013 nó dựng
ra nguyên hai câu tiếng Anh không có thật, ngược hẳn nội dung bài. Mọi câu trích trong tài liệu
này đều lấy từ `pdftotext` chạy trên PDF gốc và đối chiếu từng chữ.*
