# colab_B — Bảng A + B3

Tải cả thư mục này lên `MyDrive/colab_B/`, mở `chay_bangA_B3.ipynb` bằng Colab, Runtime → GPU, chạy ô 1→4.

| File | Là gì |
|---|---|
| `khung_nhan.zip` | 3.000 khung 640×512 + nhãn OBB 4 lớp (id 0..3), bỏ 189 hộp Undecided |
| `chia_khoi.csv` | bộ chia khối có đệm, 5 vòng — `ma/chia_khoi_dem_khung.py` |
| `chay_bangA_B3.ipynb` | notebook |

Kết quả về `MyDrive/colab_B/ket_qua/*.json` + `tong_hop.csv`. Mỗi lượt một JSON, đứt phiên chạy lại không mất.

Ước lượng T4: yolo26s-obb ~40–60 phút/lượt (dừng sớm), yolov9c ~2× (25,6 M tham số).
Bảng A tối thiểu (4 kiến trúc × 1 hạt) ≈ 4 giờ; đủ 3 hạt ≈ 12 giờ; B3 thêm 4 vòng ≈ 3–4 giờ.
