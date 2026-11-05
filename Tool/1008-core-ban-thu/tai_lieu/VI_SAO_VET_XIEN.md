# Vì sao hộp vuông trên ảnh nhiệt lại thành hình bình hành trên ortho

**Dự án:** 1008-stage1-rgb-thermal · **Ngày:** 21/08/2026 · **Dữ liệu:** Thuận Nam, DJI ZH20T, bay 31 m, 603 lỗi của `loi_4lop_cuoi.json`

Câu hỏi: *model cho hộp vuông vắn trên ảnh nhiệt, sao chiếu sang ortho RGB thì méo thành hình thoi / hình bình hành?*

Trả lời ngắn, trước khi vào chi tiết:

> **Không phải do ma trận hiệu chuẩn H.** Méo sinh ra ở bước cuối — bốn góc của hộp được chiếu xuống đất **độc lập với nhau**, mỗi góc bắn một tia riêng và dừng ở chỗ tia đó cắt mô hình độ cao (DSM). Ở mép tấm pin, DSM có một **bậc cao khoảng 1,3 m** (mặt tấm so với nền đất phía sau). Góc nào rơi bên này bậc, góc nào rơi bên kia bậc thì bị đẩy ngang lệch nhau vài chục centimét. Hộp chỉ rộng chưa tới 1 m, nên vài chục centimét là đủ xé nó thành hình bình hành.

Toàn bộ số trong tài liệu chạy lại được bằng:

```
py -3.13 ma/hinh_vi_sao_vet_xien.py
```

script ghi số ra `ket_qua/vi_sao_vet_xien.json` và dựng ba hình dưới đây.

---

# 1. Méo sinh ra ở khúc nào

Từ hộp trên ảnh nhiệt tới vết trên ortho có hai bước biến đổi. Đo riêng từng bước trên cùng một lỗi thì thấy ngay khúc nào có tội.

![Ba khung ảnh cạnh nhau của cùng một lỗi: hộp OBB vuông trên ảnh nhiệt, hộp vẫn vuông trên ảnh RGB sau khi qua H, và tứ giác xiên hẳn trên ortho](hinh/xien_x1_ba_khung.png)

**Hình 1** — Cùng một lỗi (ảnh `0317`, MultiHotSpot, conf 0,93) trong ba hệ toạ độ.

| bước | phép biến đổi | độ lệch khỏi góc vuông |
|---|---|---|
| **1** · ảnh nhiệt 640×512 | đầu ra YOLO (OBB) | **0,00°** |
| **2** · ảnh RGB 4056×3040 | nhân ma trận H | **0,28°** |
| **3** · ortho RGB | 4 tia cắt DSM | **16,80°** |

Méo nằm gọn ở bước **2 → 3**.

## 1.1 Loại trừ H

H là phép biến đổi phối cảnh (homography), hàng thứ ba khác 0 nên **về lý thuyết** nó không giữ tính song song — tức là có làm méo thật. Nhưng biên độ bao nhiêu thì đo được: đẩy 300 chữ nhật mẫu (ba cỡ từ 60×40 tới 500×400 px, bốn góc xoay, rải khắp khung 640×512) qua H rồi đo lại bốn góc:

**lệch 0,02° – 0,65°, trung vị 0,37°.**

Mắt không nhìn thấy mức đó. Vậy nên **đừng giải thích độ xiên bằng hiệu chuẩn H** — hiệu chuẩn có sai thì sai ở chỗ khác (dịch cả hộp đi vài chục centimét), không phải ở chỗ làm méo hình dạng.

## 1.2 Vì sao bốn góc đi riêng

Đoạn sinh ra vết nằm ở `ma/quet_loi_anh_le.py:231`:

```python
poly = [list(chieu(gx, gy, seq)) for gx, gy in gq]
```

Mỗi góc `(gx, gy)` gọi `chieu()` một lần. Trong `chieu()`, góc đó được nhân H sang pixel RGB, dựng thành một tia trong không gian, rồi **dò nhị phân 40 vòng để tìm chỗ tia cắt DSM**. Bốn góc là bốn tia, bốn lần cắt DSM, bốn kết quả không ràng buộc gì nhau. Không có bước nào ép kết quả phải là hình chữ nhật — mà cũng **không nên** ép (xem mục 4).

---

# 2. Cơ chế: bậc DSM ở mép tấm pin

Vị trí mặt đất của một pixel phụ thuộc **độ cao tại chính chỗ tia đâm xuống**. Camera không chụp thẳng đứng tuyệt đối, nên điểm càng cao càng bị đẩy ra xa điểm nadir. Lượng đẩy đúng bằng

$$\Delta s = \Delta h \times \tan\theta$$

với $\Delta h$ là chênh cao và $\theta$ là góc nghiêng của tia so với phương thẳng đứng.

Ở trang trại này, mép mỗi hàng tấm pin là một **bậc**: mặt tấm cao hơn nền đất phía sau khoảng 1,3–1,5 m. Hộp lỗi nằm vắt qua mép tấm thì có góc đậu trên mặt tấm, có góc tuột xuống đất — và hai góc đó bị đẩy ngang lệch nhau.

![Bên trái là lát cắt đứng qua bậc DSM với hai tia chiếu, bên phải là hình nhìn từ trên xuống so vết thật với vết nếu mặt đất phẳng](hinh/xien_x2_lat_cat.png)

**Hình 2** — Vẫn ảnh `0317`. Trái: lát cắt đứng dựng từ toạ độ tia thật. Phải: nhìn từ trên xuống.

Số của ca này:

| | |
|---|---|
| tâm chụp cao hơn mặt tấm | 30,3 m |
| bậc DSM giữa góc cao nhất và góc thấp nhất | **1,46 m** |
| góc nghiêng tia của góc bị tụt xuống đất | 10,0° |
| lệch ngang = 1,46 × tan 10,0° | **0,26 m** |
| cạnh ngắn của hộp | 0,9 m |
| độ xiên thành ra | **16,8°** |

Đây là chỗ dễ hụt trực giác: **0,26 m nghe nhỏ, nhưng hộp chỉ rộng 0,9 m.** Xê một cạnh 0,26 m trên đòn bẩy 0,9 m là ra ngay 16,8°.

Bảng phải của Hình 2 tách bạch hai phần: nếu ép cả bốn tia cắt một **mặt phẳng ngang** (tức là giả vờ đất phẳng, bóc hết phần địa hình), vết ra gần như chữ nhật — lệch **0,69°**. Cho cắt DSM thật thì lệch **16,80°**. Chênh lệch đó là phần do địa hình, không phải do H, không phải do model.

---

# 3. Không phải một ca cá biệt

Chạy phép đo trên toàn bộ **603 lỗi** của nhánh ảnh lẻ, kèm tra độ cao DSM tại bốn góc mỗi lỗi:

![Biểu đồ phân tán độ xiên theo chênh cao DSM giữa bốn góc, và bảng IoU tụt dần theo nhóm độ xiên](hinh/xien_x3_bieu_do.png)

**Hình 3** — 603 lỗi. Trái: độ xiên theo chênh cao DSM. Phải: hệ quả lên bước gán tấm.

* Độ xiên toàn bộ: trung vị **2,10°**, p90 **5,37°**, lớn nhất **81,47°**. Tức là **đa số vết vẫn gần vuông** — chuyện méo chỉ xảy ra ở một nhóm nhỏ.
* Tương quan độ xiên với chênh cao DSM bốn góc: **r = 0,475**.
* Nhìn biểu đồ rõ hơn số: cụm bên trái (chênh cao < 0,5 m — cả bốn góc trên cùng mặt tấm) gần như dính sát trục, hầu hết dưới 5°. Mọi ca xiên trên 15° đều nằm bên phải mốc 0,8 m.

| nhóm độ xiên | số lỗi | chênh cao DSM (trung vị) | IoU với tấm (trung vị) |
|---|---|---|---|
| < 5° | 538 | 0,31 m | **0,726** |
| 5 – 15° | 53 | 1,13 m | 0,617 |
| > 15° | 12 | **1,33 m** | **0,478** |

1,33 m đúng bằng chiều cao một hàng tấm — nhóm xiên nặng là nhóm có góc tuột hẳn xuống đất.

**Một chi tiết nữa:** trong 12 ca xiên nhất, **8 ca có hộp chạm mép khung ảnh nhiệt** (cách mép ≤ 2 px). Hợp lý, vì công thức $\Delta h \times \tan\theta$ có hai thừa số, và $\theta$ lớn nhất chính là ở rìa khung. Ba ca xiên nhất (81,5° / 53,8° / 41,7° — ảnh `0315`, `0341`, `0338`) đều là tứ giác suy biến, cạnh ngắn chỉ 16–32 cm so với cạnh dài ~120 cm, và cả ba đều chỉ được nhìn thấy ở **một** ảnh duy nhất nên phần lớn là báo động giả.

---

# 4. Nên làm gì

**Đừng ép vết thành chữ nhật.** Đã thử và đã đo (§5.3 của `TAI_LIEU_THUAT_TOAN.md`): dựng lại hộp từ `w_m`/`h_m` thì IoU tụt gần về 0, vì drone bay yaw ≈ −89° nên hộp bao luôn nằm theo trục ảnh chứ không theo hướng nằm của tấm pin. Tứ giác xiên tuy xấu nhưng vẫn bám đúng mặt đất hơn.

**Nên đặt cờ cảnh báo** thay vì sửa. Hai điều kiện, tính được ngay lúc chiếu, không tốn thêm gì:

* lệch khỏi góc vuông > 15°, hoặc
* chênh cao DSM giữa bốn góc > 0,8 m.

Vết dính cờ thì kết quả gán mã tấm nên coi là kém tin cậy (IoU trung vị chỉ 0,478) và đưa sang soi tay. Số lượng không nhiều: 12/603 lỗi, tức 2%.

**Nếu muốn chữa tận gốc** thì phải đổi cách chiếu: thay vì bốn góc bốn tia độc lập, chiếu tâm hộp xuống DSM để lấy một mặt phẳng tựa, rồi cắt cả bốn tia với **mặt phẳng đó** thay vì với DSM. Vết ra sẽ giữ được hình chữ nhật (như cột "nếu mặt đất phẳng" ở Hình 2, lệch 0,69°). Đánh đổi: vết sẽ không còn bám địa hình ở chỗ đất thật sự dốc. Với trang trại phẳng như Thuận Nam thì đánh đổi này có lợi, nhưng đây là thay đổi pipeline nên chưa làm.

---

# Phụ lục — nguồn số

| số | lấy từ |
|---|---|
| 603 lỗi, poly 4 góc | `ket_qua/loi_4lop_cuoi.json` (model `fault_obb_4class.pt`, conf 0,25) |
| độ cao 4 góc | `du_lieu/Thermal2_31M_full_export/dsm.tif` |
| nội/ngoại tham số camera | `du_lieu/Thermal2_31M_full_export/cameras.xml` |
| ma trận H | `ket_qua/thermal_to_rgb.json` |
| IoU với tấm pin | trường `iou` của `loi_4lop_cuoi.json`, sinh bởi `ma/gan_tam_pin_4lop.py` |
| script dựng lại toàn bộ | `ma/hinh_vi_sao_vet_xien.py` → `ket_qua/vi_sao_vet_xien.json` |

Ghi chú kỹ thuật: góc nghiêng tia trong tài liệu này là góc so với **phương thẳng đứng** tại điểm chạm đất, không phải góc lệch trục quang. Trục quang của chuyến bay này đã nghiêng sẵn ~10°, nên hai đại lượng chênh nhau đáng kể (2,7° so với 10,0° ở ca Hình 2) và dùng nhầm thì công thức $\Delta h \times \tan\theta$ ra sai gấp ba.
