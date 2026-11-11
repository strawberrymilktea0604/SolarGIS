# colab_A — chạy TN-A1 và TN-A2 trên Google Colab

1. Tải **cả thư mục này** lên Google Drive thành `MyDrive/colab_A/` (3 zip ≈ 71 MB).
2. Mở `chay_A1_A2.ipynb` bằng Colab (chuột phải → Open with → Google Colaboratory).
3. Runtime → Change runtime type → **GPU**. T4 miễn phí chạy được: notebook tích luỹ gradient 4×32 cho đủ batch hiệu dụng 128 của tác giả.
4. Chạy lần lượt 6 ô. Ô 4 (train) là lâu nhất; dừng sớm (patience 20) thường kết thúc ở epoch 40–75.
5. **Đứt phiên** (Colab miễn phí cắt sau vài giờ): chạy lại ô 1 → 4, `--resume` nạp `last.pt` trên Drive và chạy tiếp. Lặp tới khi ô 4 in `[dừng sớm]` hoặc đủ 100 epoch.
6. Tải `ket_qua/a1v2_tom_tat.json` và `ket_qua/a2v2/*.json` về `ket_qua/` của dự án.

Lượt v1 (`ket_qua/A1_0`, 14/09/2026) ra F1 89,70 — trùng ablation *không color-jitter* của tác giả (89,62): `train.py` công bố
chú thích mất dòng `ColorJitter(brightness=0.5)`. v2 bật lại, cộng tích luỹ gradient và dừng sớm/nối tiếp (4 chỗ vá đánh dấu `[vá TN-A1]`).

Mốc để so:
- A1, 10 lớp: F1 93,21 ± 1,24 · nhị phân F1 97,53 (tác giả, 10 hạt, A100, batch 128)
- A2, pipeline mình trên cùng 614 tấm: F1 0,918 [0,900–0,936]

Bẫy đã xử lý sẵn trong gói: tên thư mục lớp PVF-10 đã đồng nhất giữa train/test; `--model-name deit_base`
(không phải `vit_base` trong configs/train.yaml — đó là nhánh tiền huấn luyện); wandb tắt bằng biến môi trường.
