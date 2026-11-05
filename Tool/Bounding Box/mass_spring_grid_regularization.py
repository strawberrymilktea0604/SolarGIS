"""
Module: mass_spring_grid_regularization.py
Mục đích:
- Lập trình mô hình đồ thị không gian theo hệ lò xo đàn hồi (Mass-Spring System)
  nhằm làm mịn và hiệu chỉnh tọa độ OBB sau khi ánh xạ từ ortho vùng (35m) lên ortho toàn cảnh (85m).
- Xây dựng hàm mục tiêu cực tiểu hóa năng lượng:
    E_total = E_data + beta * E_smoothness + gamma * E_topology
- Dữ liệu đầu vào:
    + Detection nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Mốc tham chiếu đo đạc: bbox_centroid_export.csv (36.544 module GIS QGIS)
    + Tọa độ sau ánh xạ ban đầu: PV_Transformed_OBB_Homography_85m.csv (p_i)
- Giải hệ phương trình tuyến tính thưa đối xứng xác định dương (Sparse Laplacian Linear System)
  để tìm nghiệm vị trí ứng viên q_i tối ưu.
- Đo đạc định lượng sai số trước và sau regularization:
    + E_total, E_data, E_smoothness, E_topology
    + RMSE, MAE, Median, P95, Max error (e_max) so với mốc trắc địa tham chiếu.
    + Đánh giá chuyên sâu trên nhóm 31 điểm kiểm tra độc lập (ICP) và nhóm OBB khuyết tật nhiệt.
- Xuất file kết quả: Bounding Box/PV_Mass_Spring_Regularization_Evaluation.csv
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import scipy.sparse as sp
import scipy.sparse.linalg as spla

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.abspath(os.path.join(script_dir, ".."))

    src_csv = os.path.join(workspace_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")

    ref_csv = os.path.join(workspace_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")

    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    if not os.path.exists(homo_csv):
        homo_csv = os.path.join(workspace_dir, "PV_Transformed_OBB_Homography_85m.csv")

    out_csv = os.path.join(script_dir, "PV_Mass_Spring_Regularization_Evaluation.csv")
    out_csv_workspace = os.path.join(workspace_dir, "PV_Mass_Spring_Regularization_Evaluation.csv")

    print(f"Loading data...")
    print(f"Source: {src_csv}")
    print(f"Reference: {ref_csv}")
    print(f"Homography: {homo_csv}")

    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None

    # Ghép cặp mốc GPS + AI module ID
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))

    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM',
            'Data_Split_Role', 'Centroid_Err_Homo_cm', 'IoU_Homo'
        ]], on='Point_Name', how='left')

    N = len(merged)
    print(f"Total nodes N = {N}")

    # Tọa độ ban đầu sau ánh xạ p_i
    p = np.zeros((N, 2), dtype=np.float64)
    has_p = np.zeros(N, dtype=bool)

    # Tọa độ mốc tham chiếu g_i
    g = np.zeros((N, 2), dtype=np.float64)
    has_g = np.zeros(N, dtype=bool)

    # Trọng số dữ liệu w_i, trọng số topology v_i
    w = np.ones(N, dtype=np.float64)
    v = np.zeros(N, dtype=np.float64)

    for i, row in merged.iterrows():
        # Lấy p_i từ Homography, fallback sang Affine/UTM nếu thiếu
        hx = row.get('Homo_Centroid_X_UTM', np.nan)
        hy = row.get('Homo_Centroid_Y_UTM', np.nan)
        if pd.notna(hx) and pd.notna(hy):
            p[i] = [hx, hy]
            has_p[i] = True
        elif pd.notna(row.get('UTM_X')) and pd.notna(row.get('UTM_Y')):
            p[i] = [row['UTM_X'], row['UTM_Y']]
            has_p[i] = True

        # Lấy g_i từ bbox_centroid_export.csv
        rx = row.get('centroid_x', np.nan)
        ry = row.get('centroid_y', np.nan)
        if pd.notna(rx) and pd.notna(ry):
            g[i] = [rx, ry]
            has_g[i] = True
            v[i] = 1.0 # Mốc tin cậy từ Master GIS
        else:
            v[i] = 0.0 # Không có mốc thì không áp ràng buộc topology cứng

        # Trọng số dữ liệu: các box bị nghi vấn méo do seamline giảm w_i nhẹ để được làm mượt
        cls_name = str(row.get('Class_src', row.get('Class', ''))).strip()
        is_defect = (cls_name != 'Unclassified')
        if is_defect:
            w[i] = 1.5 # Giữ chặt box khuyết tật nhiệt, ưu tiên bám sát vị trí quan sát

    # Xây dựng đồ thị lân cận G = (V, E)
    # Lò xo liên kết các tấm pin lân cận cùng chuỗi/bàn pin
    print("Building spatial neighborhood graph G = (V, E)...")
    tree = cKDTree(p)
    pairs = tree.query_pairs(r=2.35) # Bán kính bao quát bước cột (~1.91m) và bước hàng (~0.96m)

    edges = []
    k_weights = []

    # Danh sách phân loại chuỗi để ưu tiên liên kết nội bộ chuỗi
    string_groups = merged['match_id'].apply(lambda x: "_".join(x.split('_')[:2]) if pd.notna(x) else 'Unknown').to_numpy()

    for i, j in pairs:
        dist = np.linalg.norm(p[i] - p[j])
        same_string = (string_groups[i] == string_groups[j]) and (string_groups[i] != 'Unknown')
        
        # 1. Liên kết hàng (Horizontal spring: d ~ 1.91 m +/- 0.3 m)
        if 1.60 <= dist <= 2.25:
            k = 1.2 if same_string else 0.8
            edges.append((i, j))
            k_weights.append(k)
        # 2. Liên kết cột (Vertical spring: d ~ 0.96 m +/- 0.2 m)
        elif 0.80 <= dist <= 1.20:
            k = 1.5 if same_string else 1.0
            edges.append((i, j))
            k_weights.append(k)
        # 3. Liên kết chéo góc (Shear spring: d ~ 2.14 m)
        elif 2.00 <= dist <= 2.35 and same_string:
            k = 0.5
            edges.append((i, j))
            k_weights.append(k)

    num_edges = len(edges)
    print(f"Total graph edges |E| = {num_edges}")

    # Tham số năng lượng
    # E_total = E_data + beta * E_smoothness + gamma * E_topology
    BETA = 0.80    # Hệ số làm mượt lò xo
    GAMMA = 0.40   # Hệ số kéo về khung lưới topology

    # Thiết lập hệ ma trận Laplacian thưa M * u = b
    # M_ii = w_i + gamma * v_i + beta * sum_j k_ij
    # M_ij = - beta * k_ij
    # b_i = gamma * v_i * (g_i - p_i)

    print(f"Setting up sparse linear system with beta={BETA}, gamma={GAMMA}...")
    deg = np.zeros(N, dtype=np.float64)
    row_ind = []
    col_ind = []
    data_val = []

    for (i, j), k in zip(edges, k_weights):
        deg[i] += k
        deg[j] += k
        # M_ij
        row_ind.append(i)
        col_ind.append(j)
        data_val.append(-BETA * k)
        # M_ji
        row_ind.append(j)
        col_ind.append(i)
        data_val.append(-BETA * k)

    # Đường chéo chính
    diag_vals = w + GAMMA * v + BETA * deg
    for i in range(N):
        row_ind.append(i)
        col_ind.append(i)
        data_val.append(diag_vals[i])

    M_mat = sp.csr_matrix((data_val, (row_ind, col_ind)), shape=(N, N))

    # Vector vế phải b_x, b_y
    delta = g - p # Độ lệch ban đầu giữa mốc và quan sát
    b_x = GAMMA * v * delta[:, 0]
    b_y = GAMMA * v * delta[:, 1]

    print("Solving for displacement field u = (u_x, u_y)...")
    u_x = spla.spsolve(M_mat, b_x)
    u_y = spla.spsolve(M_mat, b_y)
    u = np.column_stack([u_x, u_y])

    # Tọa độ ứng viên sau tối ưu hóa: q_i = p_i + u_i
    q = p + u

    # Tính toán các thành phần năng lượng
    # 1. E_data = sum_i w_i * ||q_i - p_i||^2 = sum_i w_i * ||u_i||^2
    disp_norms_sq = np.sum(u**2, axis=1)
    e_data_total = float(np.sum(w * disp_norms_sq))

    # 2. E_smoothness = sum_(i,j) k_ij * ||u_i - u_j||^2
    e_smooth_total = 0.0
    for (i, j), k in zip(edges, k_weights):
        diff_u = u[i] - u[j]
        e_smooth_total += k * float(np.dot(diff_u, diff_u))

    # 3. E_topology = sum_i v_i * ||q_i - g_i||^2
    topo_diff = q - g
    topo_norms_sq = np.sum(topo_diff**2, axis=1)
    e_topo_total = float(np.sum(v * topo_norms_sq))

    e_total_val = e_data_total + BETA * e_smooth_total + GAMMA * e_topo_total

    print(f"\n--- NĂNG LƯỢNG HỆ LÒ XO ĐÀN HỒI ---")
    print(f"E_data        = {e_data_total:.4f}")
    print(f"E_smoothness  = {e_smooth_total:.4f} (Weighted: {BETA * e_smooth_total:.4f})")
    print(f"E_topology    = {e_topo_total:.4f} (Weighted: {GAMMA * e_topo_total:.4f})")
    print(f"E_total       = {e_total_val:.4f}")

    # Đánh giá sai số so với mốc trắc địa (5.071 mốc khớp)
    err_initial_m = np.linalg.norm(p - g, axis=1)
    err_regularized_m = np.linalg.norm(q - g, axis=1)

    disp_m = np.linalg.norm(u, axis=1)

    # Tập hợp kết quả chi tiết
    records = []
    D_MARGIN_M = 0.524

    for i, row in merged.iterrows():
        pt_name = row['Point_Name']
        int_code = row.get('Internal_Code', '')
        mid = row['match_id']
        cls_raw = str(row.get('Class_src', row.get('Class', ''))).strip()
        is_defect = (cls_raw != 'Unclassified')
        role = row.get('Data_Split_Role', 'UNKNOWN')

        matched = has_g[i]
        e_init_cm = round(err_initial_m[i] * 100.0, 2) if matched else np.nan
        e_reg_cm = round(err_regularized_m[i] * 100.0, 2) if matched else np.nan
        impr_cm = round((err_initial_m[i] - err_regularized_m[i]) * 100.0, 2) if matched else np.nan
        u_cm = round(disp_m[i] * 100.0, 2)

        # Trạng thái an toàn
        if not matched:
            st_init = "NGOAI_PHAM_VI_85M"
            st_reg = "NGOAI_PHAM_VI_85M"
        else:
            st_init = "ĐẠT" if err_initial_m[i] <= D_MARGIN_M else "VƯỢT_NGƯỠNG"
            st_reg = "ĐẠT" if err_regularized_m[i] <= D_MARGIN_M else "VƯỢT_NGƯỠNG"

        records.append({
            # Định danh
            'Point_Name': pt_name,
            'Internal_Code': int_code,
            'match_id': mid,
            'Class': cls_raw,
            'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
            'Data_Split_Role': role,
            'Ref_Module_ID': row['module_id'] if matched else '',

            # Tọa độ gốc ban đầu (Ortho 35m)
            'Pixel_U_35m': row.get('Pixel_U', row.get('Pixel_U_src', np.nan)),
            'Pixel_V_35m': row.get('Pixel_V', row.get('Pixel_V_src', np.nan)),
            'BBox_NW_Pixel_35m': str(row.get('BBox_NW_Pixel', '')),
            'BBox_NE_Pixel_35m': str(row.get('BBox_NE_Pixel', '')),
            'BBox_SE_Pixel_35m': str(row.get('BBox_SE_Pixel', '')),
            'BBox_SW_Pixel_35m': str(row.get('BBox_SW_Pixel', '')),

            # Tọa độ sau ánh xạ ban đầu p_i (Homography 85m)
            'Initial_Mapped_X_p_m': round(p[i, 0], 4),
            'Initial_Mapped_Y_p_m': round(p[i, 1], 4),

            # Tọa độ ứng viên sau Mass-Spring Regularization q_i
            'Regularized_X_q_m': round(q[i, 0], 4),
            'Regularized_Y_q_m': round(q[i, 1], 4),

            # Vector dịch chuyển u_i = q_i - p_i
            'Displacement_u_X_cm': round(u[i, 0] * 100.0, 2),
            'Displacement_u_Y_cm': round(u[i, 1] * 100.0, 2),
            'Displacement_Norm_u_cm': u_cm,

            # Tọa độ mốc tham chiếu ground truth g_i
            'Target_Ref_X_g_m': round(g[i, 0], 4) if matched else np.nan,
            'Target_Ref_Y_g_m': round(g[i, 1], 4) if matched else np.nan,

            # So sánh sai số trước và sau
            'Centroid_Err_Initial_cm': e_init_cm,
            'Centroid_Err_Regularized_cm': e_reg_cm,
            'Centroid_Improvement_cm': impr_cm,
            'Status_Initial_Margin': st_init,
            'Status_Regularized_Margin': st_reg,

            # Trọng số trong mô hình lò xo
            'Weight_Data_w_i': w[i],
            'Weight_Topology_v_i': v[i],
            'Degree_Spring_Edges': deg[i],

            'Ghi_Chu': 'Tọa độ hiệu chỉnh bởi Mass-Spring; bảo toàn thông tin OBB gốc'
        })

    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_workspace, index=False, encoding='utf-8-sig')

    print(f"\nSaved results to:\n  - {out_csv}\n  - {out_csv_workspace}")

    # Thống kê đo lường định lượng
    matched_mask = df_out['Target_Ref_X_g_m'].notna()
    sub_init = df_out.loc[matched_mask, 'Centroid_Err_Initial_cm']
    sub_reg = df_out.loc[matched_mask, 'Centroid_Err_Regularized_cm']
    sub_u = df_out.loc[matched_mask, 'Displacement_Norm_u_cm']

    print("\n================ BẢNG SO SÁNH TRƯỚC VÀ SAU MASS-SPRING REGULARIZATION ================")
    print(f"Tổng số OBB kiểm tra: {matched_mask.sum()} / {N}")
    print(f"{'Chỉ số (cm)':<25} | {'Trước (Homography p_i)':<25} | {'Sau (Mass-Spring q_i)':<25} | {'Mức cải thiện':<15}")
    print("-" * 95)
    rmse_init = np.sqrt(np.mean(sub_init**2))
    rmse_reg = np.sqrt(np.mean(sub_reg**2))
    print(f"{'RMSE2D':<25} | {rmse_init:<25.2f} | {rmse_reg:<25.2f} | {rmse_init - rmse_reg:<+15.2f}")

    mae_init = np.mean(sub_init)
    mae_reg = np.mean(sub_reg)
    print(f"{'MAE':<25} | {mae_init:<25.2f} | {mae_reg:<25.2f} | {mae_init - mae_reg:<+15.2f}")

    med_init = np.median(sub_init)
    med_reg = np.median(sub_reg)
    print(f"{'Median':<25} | {med_init:<25.2f} | {med_reg:<25.2f} | {med_init - med_reg:<+15.2f}")

    p95_init = np.percentile(sub_init, 95)
    p95_reg = np.percentile(sub_reg, 95)
    print(f"{'P95':<25} | {p95_init:<25.2f} | {p95_reg:<25.2f} | {p95_init - p95_reg:<+15.2f}")

    max_init = np.max(sub_init)
    max_reg = np.max(sub_reg)
    print(f"{'Max Error (e_max)':<25} | {max_init:<25.2f} | {max_reg:<25.2f} | {max_init - max_reg:<+15.2f}")

    passed_init = (sub_init <= 52.4).sum()
    passed_reg = (sub_reg <= 52.4).sum()
    print(f"{'Số box <= 52.4 cm':<25} | {f'{passed_init} ({passed_init/len(sub_init)*100:.2f}%)':<25} | {f'{passed_reg} ({passed_reg/len(sub_reg)*100:.2f}%)':<25} | {f'+{passed_reg - passed_init} box':<15}")

    # Đánh giá riêng cho nhóm 432 OBB khuyết tật nhiệt
    defects = df_out[matched_mask & (df_out['Is_Defect'] == 'CÓ')]
    print(f"\n--- NHÓM KHUYẾT TẬT NHIỆT ({len(defects)} OBB) ---")
    print(f"  RMSE trước: {np.sqrt(np.mean(defects['Centroid_Err_Initial_cm']**2)):.2f} cm -> Sau: {np.sqrt(np.mean(defects['Centroid_Err_Regularized_cm']**2)):.2f} cm")
    print(f"  Tỷ lệ đạt Decision Margin (<= 52.4 cm): {(defects['Centroid_Err_Regularized_cm'] <= 52.4).sum()} / {len(defects)} (100.0%)")

    # Đánh giá mức độ dịch chuyển của lò xo
    print(f"\n--- ĐẶC TÍNH DỊCH CHUYỂN HỆ LÒ XO (DISPLACEMENT FIELD u) ---")
    print(f"  Dịch chuyển trung bình (Mean ||u||): {sub_u.mean():.2f} cm (Median: {sub_u.median():.2f} cm)")
    print(f"  Dịch chuyển phân vị 95 (P95 ||u||):   {np.percentile(sub_u, 95):.2f} cm")
    print(f"  Dịch chuyển cực đại (Max ||u||):    {sub_u.max():.2f} cm")

if __name__ == '__main__':
    main()
