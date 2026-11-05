# Kết quả đánh giá — hệ thống định vị lỗi tấm pin từ ảnh nhiệt

**Dự án:** 1008-stage1-rgb-thermal · **Ngày:** 14/08/2026

## Đánh giá model — chấm bằng NHÃN TAY trên ortho

Mốc so sánh: 511 tấm người soi chốt tay trong `cong_cu/gan_nhan_tam.html`
(443 tấm có lỗi + 68 tấm tốt). Đơn vị chấm là **tấm pin**, không phải box —
người vận hành nhận danh sách mã tấm đi thay, không ai đi thay "một box".
Chỉ tính lỗi rơi **đúng trong** polygon tấm.

| Chỉ số | Kết quả | Cách đo |
|---|---|---|
| **Precision** | **0,865** | 429 đúng / 496 tấm model khoanh |
| **Recall** | **0,968** | 429 / 443 lỗi người soi tìm ra |
| **F1** | **0,914** | |
| **Đúng tên lớp** | **0,972** | 417/429 tấm bắt trúng · 12 ca nhầm đều Single ↔ Multi |
| Lỗi rơi ngoài mọi tấm pin | 41/603 = **6,8 %** | hạn chế khâu CHIẾU, không phải khâu phát hiện |

**Từng lớp:** SingleHotSpot P 0,826 · R 0,955 (309 tấm) — MultiHotSpot P 0,883 ·
R 0,883 (103) — Bypass P 0,861 · R 1,000 (31). ModuleOpenCircuit **không đánh giá
được**: cả model lẫn người soi đều không gán tấm nào lớp này trên nhà máy.

**Đổi ngưỡng conf:** 0,25 → P 0,865 / R 0,968 · **0,30 → 0,889 / 0,957 (F1 cao
nhất)** · 0,40 → 0,917 / 0,921 · 0,64 → 0,951 / 0,829 · 0,80 → 0,977 / 0,763.
Đang chạy ở 0,25 vì bỏ sót một tấm cháy đắt hơn cho thợ kiểm tra oan một tấm lành.

**Ba điều phải nói kèm:**

1. **Recall đo bằng quét tay toàn bản đồ** — người soi rà cả phần model không
   khoanh chứ không chỉ xem lại chỗ model đã khoanh, nên 14 tấm FN là số đếm hết
   chứ không phải ước lượng. Không kèm khoảng tin cậy vì đây là census, không
   phải mẫu.
2. **1065 tấm rìa / phủ nhiệt < 50 % nằm ngoài phạm vi** — không có ảnh nhiệt thì
   không ai phán được, kể cả người. Mọi con số trên tính trên 5408 tấm soi được.
3. **5 trong 14 tấm bỏ sót là do `best.pt` không dò ra cả TẤM PIN** (mã
   `TAY-001`…`TAY-005`, người soi phải vẽ tay), không phải model lỗi bỏ sót —
   hỏng ở tầng trước đó.

Chạy lại: `py -3.13 ma/danh_gia_model_theo_nhan.py` · notebook đầy đủ:
`tai_lieu/DANH_GIA_THEO_NHAN.ipynb`

## Các chỉ số khác

| Chỉ số | Kết quả | Ngưỡng đề bài | Kết luận |
|---|---|---|---|
| ~~mAP@50 — "tập test độc lập" 91 ảnh~~ | ~~0,965~~ | — | **BỎ** — tập test lẫn 81 % ảnh train, model đã thấy đáp án |
| ~~Precision · Recall tại conf 0,64~~ | ~~0,946 · 0,897~~ | — | **BỎ** — cùng bộ chia bị lệch, lại không phải ngưỡng chạy thật |
| Sai số định vị trên orthophoto | RMSE **2,56 cm** | ≤ 30 cm | **Đạt** — dư hơn 10 lần |
| Sai số trên ảnh lẻ (598 ảnh, sau lọc) | trung vị 14,1 cm · P90 24,6 cm | — | trước lọc: P90 31,7 cm |
| Hiệu chuẩn H nhiệt → RGB | **4,38 px** | ≤ 3 px | **Không đạt** — nhưng tốt hơn H của hãng (22,34 px) 5,1 lần |
| Gán lỗi vào mã tấm pin | gán được **92,4 %** | ≥ 95 % đúng | **Chưa đạt / chưa kết luận** — cần soi tay 100 lỗi mẫu |
| IoU box lỗi ↔ polygon tấm pin | trung vị **0,687** | — | trần lý thuyết ~0,5–0,8 vì box lỗi nhỏ hơn tấm |
| Khử trùng lặp | 407 quan sát → 211 lỗi, nén **1,93 lần** | sót ≤ 5 % | **Chưa đo được** — cần đếm tay khu vực mẫu |
| Kiểm tra vị trí sai | không có điểm nào văng ra ngoài nhà máy | — | box quy ra thực địa 1,79 × 0,91 m, khớp tấm pin thật |
| Model mượn 8 lớp (đối chứng) | bắt **45,7 %** · đúng lớp 22,9 % | — | kém hơn hẳn, không thay thế được model dự án |
