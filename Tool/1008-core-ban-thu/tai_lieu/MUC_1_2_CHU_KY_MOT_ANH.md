---
title: "Mục 1.2 — Chữ ký một-ảnh của báo động giả"
subtitle: "Gộp phát hiện đa ảnh trong toạ độ thế giới: đo lại luận điểm, soát lại tài liệu"
date: "24/08/2026"
lang: vi
---

# Tóm tắt

Bản nháp mục 1.2 định bán luận điểm *"lọc theo số ảnh nhìn thấy (n) tốt hơn lọc theo
độ tự tin (conf)"*. Đo lại trên dữ liệu thật cho thấy **luận điểm đó không đứng được**,
nhưng một luận điểm khác — mạnh hơn nhiều — thì đứng vững:

> **Báo động giả có chữ ký hình học: 68,7% chỉ xuất hiện ở đúng một ảnh,
> so với 9,6% ở lỗi thật.** Chênh 59,6 điểm, KTC 95% [+47,7; +70,2] — không chứa 0.

Đồng thời soát lại 6 bài tham chiếu bằng toàn văn PDF, phát hiện **hai dòng trong danh
mục ghi sai** và **ba dòng "còn phải bổ" đã có người làm rồi**.

![Chữ ký một-ảnh của báo động giả và hai đường lọc cắt nhau](hinh/chu_ky_mot_anh.png)

---

# 1. Cơ chế

Drone bay lưới chồng lấn, nên một tấm pin lọt vào khung của nhiều ảnh. Pipeline detect
trên **từng ảnh nhiệt gốc**, chiếu box qua ma trận **H** sang khung RGB tương ứng, rồi
cắt tia qua **DSM** để ra toạ độ WGS84. Sau đó gộp: các box rơi cùng một chỗ trên mặt
đất là cùng một lỗi.

Khâu gộp sinh ra hai thứ cùng lúc:

* **vị trí đại diện** — box có `conf` cao nhất trong cụm;
* **n** — số ảnh riêng biệt đã nhìn thấy lỗi đó, kèm danh sách `seqs`.

Lỗi thật là vật cố định trên mặt đất nên phải xuất hiện ở **mọi** ảnh phủ qua. Nhiễu cảm
biến hay phản xạ theo góc thì **biến mất** khi drone bay tiếp. Tín hiệu phân biệt nằm
**giữa các ảnh**, không nằm trong ảnh.

`conf` và `n` khác nhau về bản chất: `conf` là *model nghĩ gì về chính nó*, `n` là
*thực tế có nhất quán không*.

---

# 2. Kết quả đo

Dữ liệu: `ket_qua/loi_4lop_cuoi.json` (603 lỗi đã gộp, model `fault_obb_4class.pt`,
conf 0,25). Nhãn tay: `ket_qua/nhan_tam_pin_moi.json` — 443 tấm có lỗi, 68 tấm tốt.
Ghép theo `panel_code`, mỗi tấm giữ phát hiện conf cao nhất → **TP = 429, FP = 67**.

## 2.1 Phân bố n

Trung bình **4,3 ảnh/lỗi**. Tách theo nhãn tay:

| Nhóm | n = 1 | n trung bình |
|---|---:|---:|
| Lỗi thật (TP, 429) | **9,6 %** | 5,3 |
| Báo động giả (FP, 67) | **68,7 %** | 1,8 |

Bootstrap 2000 lần trên chênh lệch tỉ lệ n = 1:

> **ρ_FP − ρ_TP = +59,6 điểm, KTC 95% [+47,7; +70,2] — không chứa 0.**

Đây là kết quả vững nhất của mục này: chênh **gấp 7 lần**, không phải vài phần nghìn.

## 2.2 Lọc theo n so với lọc theo conf

| Ngưỡng | TP giữ | FP giữ | P | R | F1 |
|---|---:|---:|---:|---:|---:|
| n ≥ 1 | 429 | 67 | 0,865 | 1,000 | 0,928 |
| n ≥ 2 | 388 | 21 | 0,949 | 0,904 | 0,926 |
| **n ≥ 3** | 366 | 12 | **0,968** | 0,853 | 0,907 |
| n ≥ 4 | 326 | 7 | 0,979 | 0,760 | 0,856 |
| conf ≥ 0,30 | 425 | 53 | 0,889 | 0,991 | **0,937** |
| conf ≥ 0,64 | 368 | 19 | **0,951** | 0,858 | 0,902 |

Hai con số của bản nháp **tái lập đúng**: n ≥ 3 cho P 0,968; conf ≈ 0,65 ở cùng recall
0,853 cho P 0,951. Nhưng bootstrap trên chính chênh lệch đó:

> **ΔP = +0,019, KTC 95% [−0,005; +0,044] — chứa 0. Không kết luận được.**

Hình (b) cho thấy vì sao: hai đường P–R **cắt nhau**, không đường nào trội trên toàn dải.

## 2.3 Tổ hợp n & conf cũng không thắng

| Cách lọc | F1 tốt nhất |
|---|---:|
| Chỉ conf | **0,940** (conf ≥ 0,31) |
| Tổ hợp conf & n | 0,937 (conf ≥ 0,30, n ≥ 1) |

Mọi cấu hình tối ưu của tổ hợp đều rơi vào `n ≥ 1`, tức **n không đóng góp gì cho F1**.

## 2.4 Lọc theo số đợt bay — cũng không thắng

Tách `seqs` thành các đợt bay riêng (seq cách nhau > 3 là lượt bay khác). Chỉ số này
**tách TP/FP rất tốt** — FP trung bình 1,33 đợt, TP 2,47 đợt; 76,1% FP chỉ thấy từ một
đợt so với 16,8% ở TP. Nhưng khi dùng để lọc thì vẫn **thua conf**:

| Ngưỡng | P | R | conf cùng recall | ΔP |
|---|---:|---:|---:|---:|
| đợt ≥ 2 | 0,957 | 0,832 | 0,962 | **−0,005** |
| đợt ≥ 3 | 0,978 | 0,622 | 0,989 | **−0,011** |

## 2.5 Vì sao mọi so sánh precision đều gãy

**FP chỉ có 67 mẫu.** Chênh lệch vài phần nghìn trên 67 mẫu nằm trong nhiễu. Đó là lý do
cả ba luận điểm "n thắng conf" đều không đứng được, còn ρ thì vững — vì ρ là chênh lệch
gấp 7 lần.

Muốn phân định được, phải **tăng số FP**: chấm nhãn tay rộng hơn, hoặc thêm sortie nhiệt.

---

# 3. Hai lỗi dữ liệu phát hiện được

## 3.1 `n` trong file bị phồng

`ma/quet_loi_anh_le.py:258` làm `trung["seqs"].append(r["seq"])` **không kiểm tra trùng**.
Kết quả: **99 cụm có `seq` lặp lại, 158 phiếu bị đếm thừa**.

Một ảnh ra hai box gần nhau sẽ cho `n = 2` nhưng thực chất chỉ có **một nhân chứng**.
Mọi số trong tài liệu này đã đếm bằng `len(set(seqs))` nên là số sạch.

**Sửa:** `n = len(set(seqs))`.

## 3.2 Ba chỗ hở khác trong khâu gộp

* **Gộp tham lam, phụ thuộc thứ tự.** Vòng lặp `break` ngay khi gặp cụm đầu tiên đủ gần.
  Box nằm giữa hai cụm sẽ nhập vào cụm **duyệt trước** (conf cao hơn), không phải cụm
  **gần hơn**. Phải đổi sang gán-vào-cụm-gần-nhất, hoặc chứng minh kết quả không đổi.
* **Cắt theo khoảng cách tâm** — không bắt được box lồng nhau, làm mốc 603 phồng 10,4%.
* **Hệ quả lên n:** box lồng thường rơi vào n thấp, nên tỉ lệ n = 1 (26,5% trên toàn tập)
  có thể phồng theo. Con số 68,7% ở mục 2.1 đo trên tập đã ghép nhãn tay nên ít chịu ảnh
  hưởng hơn, nhưng vẫn cần nói rõ.

---

# 4. Soát lại tài liệu

Đọc toàn văn 6 bài bằng PDF gốc, kèm hình cắt từ chính bài đó.

| Bài | Toạ độ thật | Gộp đa ảnh | Dùng n lọc thật–giả |
|---|:-:|:-:|:-:|
| [57] Kabra — waterbird, ICMLA 2022 | ✗ (chỉ nêu) | trong pixel | ✗ |
| [58] Akyön — SAHI, ICIP 2022 | ✗ | trong 1 ảnh | ✗ |
| [20] Sangjan — MatchPlant, 2026 | ✓ | ✗ | ✗ |
| [9] Løfstad-Lie — J. Photovolt. 2025 | ✓ | ✗ | ✗ |
| [55] Bommes — Prog. Photovolt. 2022 | ✗ | ✓ (cho sẵn) | quá bán, **+1 điểm** |
| [56] Lysyi — Radioelectron. 2025 | ✓ | ✓ | ✗ — để **bớt trùng** |
| **Bài này** | ✓ | ✓ | **✓** |

## 4.1 [56] Lysyi — bài gần nhất, và danh mục đang ghi sai

Danh mục ghi *"không hề có toạ độ"*. **Sai.** Nguyên văn bài:

> *"project each detection's bounding box polygon from 2D pixel space into real-world
> WGS84 coordinates. This complex projection requires the full camera model, including
> its intrinsic parameters, and the precise six-degree-of-freedom pose... critically
> dependent on the availability of an RTK-GPS unit."*

Chuỗi **trùng hoàn toàn** với chuỗi của ta. Họ gộp bằng DBSCAN haversine, `eps = 1,0 m`,
`minPts = 2`, đại diện lấy *"maximum or confidence-weighted average"*.

**Nhưng mục đích khác hẳn.** Lý do họ chốt `minPts = 2` là tự khai:

> *"since we want to merge any pair of overlapping detections"*

Chỉ số họ đo là **Dup-FP** — một lỗi thật bị đếm nhiều lần thành nhiều báo cáo, phải xoá
bớt cho kỹ thuật viên. Đó là **loại FP hoàn toàn khác** với loại ta nhắm (model đoán sai).

Họ **có** nhận ra các detect đơn độc — DBSCAN gọi là noise, nguyên văn *"allowing it to
isolate single, non-overlapping detections"* — nhưng **dừng ở đó: không đếm, không dùng**.

> **[56] gộp đa ảnh để BỚT TRÙNG. Bài này dùng chính số ảnh đó để PHÂN BIỆT THẬT–GIẢ.**

## 4.2 [55] Bommes — không có "anomaly ratio"

Danh mục ghi họ *"định nghĩa anomaly ratio — tỉ lệ ảnh đồng thuận — thay cho confidence"*.
**Cụm từ này không xuất hiện trong bài.** Cần sửa danh mục.

Thực tế mục J của họ:

> *"As there are on average 39.4 IR images of each PV module we can aggregate predictions
> of those images... we predict a module as anomalous if at least one half of the
> corresponding images are predicted anomalous."*

Ba điểm khiến bài này không nuốt được đóng góp của ta:

1. **Bỏ phiếu quá bán cố định**, không có chỉ số tỉ lệ, không quét ngưỡng.
2. **Là bài phân loại, không phải phát hiện.** Họ đã biết trước tấm pin nào ở đâu; 39,4
   ảnh/tấm là **cho sẵn**, không phải do gộp không gian mà ra. Trọng tâm bài là
   **domain shift** giữa các nhà máy (A→B, B→E, F→A).
3. **Không hề bàn tới độc lập của phiếu.** 39,4 ảnh của họ đến từ **video liên tục** —
   nguyên văn *"Due to redundancies in the video"*.

Và chính họ báo cáo kết quả: bỏ phiếu quá bán chỉ nâng phát hiện lỗi **một điểm phần
trăm** (*"a one percent higher detection rate for anomalies"*).

**Đây là món quà cho mục 1.2:** luận điểm "phiếu phải độc lập" giờ tựa vào câu tự khai
của chính họ, không phải suy diễn.

## 4.3 Ba dòng "còn phải bổ" của bản nháp đã có người làm

| Bản nháp ghi | Thực tế |
|---|---|
| "Quét bán kính gộp thành đường cong" | **[56] làm rồi** — Figure 5, 4 mức eps × 2 bộ dữ liệu |
| "Đo tỉ lệ dán nhầm hai vết ở hai cell kề" | **[56] đã nêu** làm lý do chọn 1,0 m |
| "[56] không hề có toạ độ" | **Sai** — có WGS84 + RTK đầy đủ |

Cái ta quét **không phải bán kính** (họ làm rồi), mà là **ngưỡng số ảnh n** — chỗ họ chốt
cứng ở `minPts = 2`.

---

# 5. Viết mục 1.2 thế nào

## 5.1 Bỏ hẳn khung "n tốt hơn conf"

Reviewer chỉ cần đòi khoảng tin cậy là bài sập.

## 5.2 Viết theo khung "quan sát về bản chất dữ liệu"

> Báo động giả trong khảo sát nhiệt đa ảnh có chữ ký hình học: 68,7% chỉ xuất hiện ở một
> ảnh duy nhất, so với 9,6% ở lỗi thật (chênh 59,6 điểm, KTC 95% [47,7; 70,2]).
> [9] gọi tên lớp FP này nhưng không đếm; [56] gộp đa ảnh trong toạ độ thật nhưng chỉ để
> bớt trùng lặp, chốt `minPts = 2` và không dùng số ảnh làm bằng chứng; [55] có 39,4
> ảnh/tấm nhưng lấy từ video liên tục nên bỏ phiếu quá bán chỉ nâng 1 điểm.

## 5.3 Báo cáo thẳng kết quả âm

> Chúng tôi kiểm tra và **không tìm thấy** bằng chứng rằng lọc theo số ảnh vượt lọc theo
> độ tự tin ở cùng recall (ΔP = +0,019, KTC 95% [−0,005; +0,044]). Với 67 mẫu FP, cỡ mẫu
> không đủ để phân định.

Bài tự báo cáo kết quả âm đáng tin hơn bài khoe chênh lệch không có khoảng tin cậy.

## 5.4 Việc phải làm trước khi nộp

1. **Sửa `n = len(set(seqs))`** và chạy lại — số hiện tại phồng 158 phiếu.
2. **Sửa khâu gộp**: gán vào cụm gần nhất thay vì cụm duyệt trước; xử lý box lồng nhau.
3. **Tăng số FP** — 67 mẫu là trần của mọi kết luận về precision.
4. **Chốt ngưỡng trên khối khác khối báo cáo** (thiết kế chia khối out-of-fold đã có).
5. **Sửa hai dòng danh mục**: [56] có toạ độ; [55] không có "anomaly ratio".

---

*Số liệu dựng lại được bằng `ma/hinh_chu_ky_mot_anh.py`. Nguồn: `ket_qua/loi_4lop_cuoi.json`,
`ket_qua/nhan_tam_pin_moi.json`. Bootstrap 2000 lần, seed 7.*
