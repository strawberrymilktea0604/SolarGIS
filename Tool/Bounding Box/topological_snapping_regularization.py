"""
Module: topological_snapping_regularization.py
Mục đích:
- Triển khai cơ chế Topological Snapping nắn chỉnh OBB detection về lưới giàn pin:
    + Tự động uốn nắn góc xoay theta về góc chuẩn của chuỗi/bàn pin.
    + "Hút" (snap) các detection bị méo góc, xộc xệch, trôi dạt cục bộ quay trở về đúng tâm ô lưới.
- Dữ liệu đầu vào:
    + Detection nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Mốc tham chiếu đo đạc: bbox_centroid_export.csv (36.544 module GIS QGIS)
    + Tọa độ sau ánh xạ ban đầu: PV_Transformed_OBB_Homography_85m.csv (p_i)
    + Góc xoay ban đầu: PV_Affine_Parallelism_Evaluation.csv (theta_i)
- Quy tắc kiểm soát:
    + Trường hợp A: Đủ điều kiện snapping (SNAP_ACCEPTED) -> hút tâm, nắn góc.
    + Trường hợp B: Có nhiều ô lưới ứng viên / va chạm (AMBIGUOUS_COLLISION) -> giữ nguyên, đánh dấu đối soát.
    + Trường hợp C: Sai lệch quá lớn / ngoài phạm vi (OUT_OF_BOUNDS_UNASSIGNED) -> giữ nguyên tọa độ gốc.
- Xuất file kết quả: Bounding Box/PV_Topological_Snapping_Evaluation.csv
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def line_orientation_diff(deg1, deg2):
    """Tính độ lệch góc không định hướng chu kỳ 180 độ [0, 90]"""
    diff = abs(deg1 - deg2) % 180.0
    if diff > 90.0:
        diff = 180.0 - diff
    return diff

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

    aff_csv = os.path.join(script_dir, "PV_Affine_Parallelism_Evaluation.csv")
    if not os.path.exists(aff_csv):
        aff_csv = os.path.join(workspace_dir, "PV_Affine_Parallelism_Evaluation.csv")

    out_csv = os.path.join(script_dir, "PV_Topological_Snapping_Evaluation.csv")
    out_csv_workspace = os.path.join(workspace_dir, "PV_Topological_Snapping_Evaluation.csv")

    print("Loading data...")
    print(f"Source: {src_csv}")
    print(f"Reference: {ref_csv}")
    print(f"Homography: {homo_csv}")
    print(f"Affine: {aff_csv}")

    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None
    df_aff = pd.read_csv(aff_csv) if os.path.exists(aff_csv) else None

    # Ghép cặp định danh GPS + AI
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))

    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM',
            'Centroid_Err_Homo_cm', 'IoU_Homo'
        ]], on='Point_Name', how='left')

    if df_aff is not None:
        merged = pd.merge(merged, df_aff[[
            'Point_Name', 'Long_Edge_Heading_Deg', 'Ref_Heading_Deg', 'Theta_vs_Ref_Deg',
            'String_Group', 'String_Mean_Heading_Deg', 'Dev_From_String_Mean_Deg'
        ]], on='Point_Name', how='left')

    N = len(merged)
    print(f"Total detections N = {N}")

    # Xây dựng cây KD-Tree trên toàn bộ 36.544 module của bbox_centroid_export.csv
    print(f"Building KD-Tree on {len(df_ref)} reference grid cells...")
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values.astype(np.float64)
    ref_tree = cKDTree(ref_coords)

    # Các tham số kiểm soát Topological Snapping
    LAMBDA_P = 1.0         # Trọng số sai lệch khoảng cách tâm (m^-2)
    LAMBDA_THETA = 0.05    # Trọng số sai lệch góc định hướng
    D_MAX_M = 0.524        # Ranh giới an toàn tối đa cho phép snapping (52.4 cm)
    THETA_MAX_DEG = 3.5    # Sai lệch góc tối đa cho phép snapping (3.5 độ)
    DELTA_AMBIG_M = 0.15   # Ngưỡng mơ hồ giữa 2 ô lưới ứng viên (15 cm)

    # Bước 1: Tìm ô lưới ứng viên tốt nhất cho từng OBB
    print("Evaluating candidate grid cells and cost function J_i(r, c)...")
    
    records = []
    cell_claims = {} # Theo dõi cạnh tranh ô lưới (Collision detection)

    for i, row in merged.iterrows():
        pt_name = row['Point_Name']
        int_code = row.get('Internal_Code', '')
        mid = row['match_id']
        cls_raw = str(row.get('Class_src', row.get('Class', ''))).strip()
        is_defect = (cls_raw != 'Unclassified')

        # Tọa độ sau ánh xạ Homography p_i = (x_i, y_i)
        p_x = row.get('Homo_Centroid_X_UTM', np.nan)
        p_y = row.get('Homo_Centroid_Y_UTM', np.nan)
        if pd.isna(p_x) or pd.isna(p_y):
            p_x = float(row.get('UTM_X', np.nan))
            p_y = float(row.get('UTM_Y', np.nan))

        theta_i = float(row.get('Long_Edge_Heading_Deg', np.nan))
        ref_heading_i = float(row.get('Ref_Heading_Deg', np.nan)) if pd.notna(row.get('Ref_Heading_Deg')) else float(row.get('String_Mean_Heading_Deg', 179.5))

        has_p = pd.notna(p_x) and pd.notna(p_y)

        if not has_p:
            records.append({
                'Point_Name': pt_name,
                'Internal_Code': int_code,
                'match_id': mid,
                'Class': cls_raw,
                'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
                'mapped_cx': np.nan,
                'mapped_cy': np.nan,
                'mapped_theta': np.nan,
                'candidate_row': np.nan,
                'candidate_col': np.nan,
                'candidate_module_id': '',
                'snap_distance_m': np.nan,
                'snap_distance_cm': np.nan,
                'angle_error_deg': np.nan,
                'cost_J': np.nan,
                'snapped_cx': np.nan,
                'snapped_cy': np.nan,
                'snapped_theta': np.nan,
                'snap_status': 'UNASSIGNED_NO_COORDS',
                'Ghi_Chu': 'Thiếu tọa độ ánh xạ ban đầu'
            })
            continue

        p_pt = np.array([p_x, p_y], dtype=np.float64)

        # Truy vấn các ô lưới ứng viên trong bán kính 1.2 m
        cand_indices = ref_tree.query_ball_point(p_pt, r=1.2)

        if len(cand_indices) == 0:
            # Trường hợp C: Hoàn toàn nằm ngoài phạm vi lưới
            records.append({
                'Point_Name': pt_name,
                'Internal_Code': int_code,
                'match_id': mid,
                'Class': cls_raw,
                'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
                'mapped_cx': round(p_x, 4),
                'mapped_cy': round(p_y, 4),
                'mapped_theta': round(theta_i, 3) if pd.notna(theta_i) else np.nan,
                'candidate_row': np.nan,
                'candidate_col': np.nan,
                'candidate_module_id': '',
                'snap_distance_m': np.nan,
                'snap_distance_cm': np.nan,
                'angle_error_deg': np.nan,
                'cost_J': np.nan,
                'snapped_cx': round(p_x, 4), # Giữ nguyên tọa độ gốc
                'snapped_cy': round(p_y, 4),
                'snapped_theta': round(theta_i, 3) if pd.notna(theta_i) else np.nan,
                'snap_status': 'OUT_OF_BOUNDS_UNASSIGNED',
                'Ghi_Chu': 'Nằm ngoài phạm vi giàn pin tham chiếu 85m'
            })
            continue

        # Đánh giá hàm chi phí J_i cho từng ứng viên
        best_idx = None
        best_cost = float('inf')
        best_dist = float('inf')
        second_best_dist = float('inf')
        best_ang_diff = float('inf')

        for c_idx in cand_indices:
            c_pos = ref_coords[c_idx]
            d = np.linalg.norm(p_pt - c_pos)
            
            # Tính sai khác góc so với góc chuỗi tham chiếu
            if pd.notna(theta_i):
                ang_diff = line_orientation_diff(theta_i, ref_heading_i)
            else:
                ang_diff = 0.0

            cost = LAMBDA_P * (d ** 2) + LAMBDA_THETA * (ang_diff ** 2)

            if cost < best_cost:
                second_best_dist = best_dist
                best_cost = cost
                best_dist = d
                best_idx = c_idx
                best_ang_diff = ang_diff
            elif d < second_best_dist:
                second_best_dist = d

        ref_row = df_ref.iloc[best_idx]
        cand_mid = ref_row['module_id']
        cand_row_id = ref_row['Row_ID']
        g_snap = ref_coords[best_idx]

        # Kiểm tra điều kiện gán (Snapping Eligibility)
        is_ambiguous = (second_best_dist - best_dist < DELTA_AMBIG_M) and (second_best_dist < D_MAX_M)
        is_dist_ok = (best_dist <= D_MAX_M)
        is_angle_ok = (best_ang_diff <= THETA_MAX_DEG)

        if not is_dist_ok:
            # Trường hợp C: Khoảng cách vượt ngưỡng an toàn 52.4 cm
            status = 'EXCESSIVE_DISTANCE_UNASSIGNED'
            snap_cx = p_x
            snap_cy = p_y
            snap_th = theta_i
            note = f'Khoảng cách tới lưới {best_dist*100:.1f} cm vượt ngưỡng 52.4 cm'
        elif is_ambiguous:
            # Trường hợp B: Có 2 ô lưới gần tương đương
            status = 'AMBIGUOUS_MULTI_CANDIDATE'
            snap_cx = p_x
            snap_cy = p_y
            snap_th = theta_i
            note = f'Tranh chấp giữa 2 ô lưới (chênh lệch {abs(second_best_dist - best_dist)*100:.1f} cm < 15 cm)'
        elif not is_angle_ok:
            # Trường hợp B/C: Lệch góc quá lớn
            status = 'EXCESSIVE_ANGLE_UNASSIGNED'
            snap_cx = p_x
            snap_cy = p_y
            snap_th = theta_i
            note = f'Sai khác góc {best_ang_diff:.2f}° vượt ngưỡng 3.5°'
        else:
            # Trường hợp A: Đủ điều kiện snapping
            status = 'SNAP_ACCEPTED'
            snap_cx = g_snap[0]
            snap_cy = g_snap[1]
            snap_th = ref_heading_i
            note = 'Hút tâm về đúng ô lưới và nắn thẳng góc xoay'

        # Đăng ký kiểm tra va chạm (Collision check)
        if status == 'SNAP_ACCEPTED':
            if cand_mid not in cell_claims:
                cell_claims[cand_mid] = []
            cell_claims[cand_mid].append((i, best_dist))

        records.append({
            'Point_Name': pt_name,
            'Internal_Code': int_code,
            'match_id': mid,
            'Class': cls_raw,
            'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
            'mapped_cx': round(p_x, 4),
            'mapped_cy': round(p_y, 4),
            'mapped_theta': round(theta_i, 3) if pd.notna(theta_i) else np.nan,
            'candidate_row': cand_row_id,
            'candidate_col': cand_mid.split('_')[-1] if '_' in str(cand_mid) else '',
            'candidate_module_id': cand_mid,
            'snap_distance_m': round(best_dist, 4) if pd.notna(best_dist) else np.nan,
            'snap_distance_cm': round(best_dist * 100.0, 2) if pd.notna(best_dist) else np.nan,
            'angle_error_deg': round(best_ang_diff, 3) if pd.notna(best_ang_diff) else np.nan,
            'cost_J': round(best_cost, 4) if pd.notna(best_cost) else np.nan,
            'snapped_cx': round(snap_cx, 4),
            'snapped_cy': round(snap_cy, 4),
            'snapped_theta': round(snap_th, 3) if pd.notna(snap_th) else np.nan,
            'snap_status': status,
            'Ghi_Chu': note
        })

    # Xử lý va chạm ô lưới (Nếu nhiều detection cùng snap vào 1 ô)
    print("Checking for grid cell collisions...")
    collisions_resolved = 0
    for cid, claimants in cell_claims.items():
        if len(claimants) > 1:
            # Giữ lại detection có khoảng cách nhỏ nhất, các detection còn lại đánh dấu COLLISION_AMBIGUOUS
            claimants.sort(key=lambda x: x[1])
            winner_idx = claimants[0][0]
            for loser_idx, loser_dist in claimants[1:]:
                records[loser_idx]['snap_status'] = 'COLLISION_AMBIGUOUS'
                records[loser_idx]['snapped_cx'] = records[loser_idx]['mapped_cx']
                records[loser_idx]['snapped_cy'] = records[loser_idx]['mapped_cy']
                records[loser_idx]['snapped_theta'] = records[loser_idx]['mapped_theta']
                records[loser_idx]['Ghi_Chu'] = f'Trùng ô lưới với {records[winner_idx]["Point_Name"]} (chưa ép gán)'
                collisions_resolved += 1

    print(f"Total collision resolutions: {collisions_resolved}")

    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_workspace, index=False, encoding='utf-8-sig')

    print(f"\nSaved results to:\n  - {out_csv}\n  - {out_csv_workspace}")
    print(f"Total records: {len(df_out)}")

    # Thống kê đo lường định lượng
    print("\n================ THỐNG KÊ KẾT QUẢ TOPOLOGICAL SNAPPING ================")
    print("\n1. PHÂN PHỐI TRẠNG THÁI SNAPPING (SNAP_STATUS):")
    status_counts = df_out['snap_status'].value_counts()
    for s_name, count in status_counts.items():
        print(f"  {s_name:<30}: {count:>5} ({count/len(df_out)*100:.2f}%)")

    accepted = df_out[df_out['snap_status'] == 'SNAP_ACCEPTED']
    print(f"\n2. ĐẶC TÍNH DỊCH CHUYỂN KHOẢNG CÁCH (SNAP_DISTANCE) TRÊN {len(accepted)} BOX ACCEPTED:")
    print(f"  Khoảng cách hút trung bình: {accepted['snap_distance_cm'].mean():.2f} cm (Median: {accepted['snap_distance_cm'].median():.2f} cm)")
    print(f"  Phân vị 90 (P90):          {accepted['snap_distance_cm'].quantile(0.90):.2f} cm")
    print(f"  Phân vị 95 (P95):          {accepted['snap_distance_cm'].quantile(0.95):.2f} cm")
    print(f"  Khoảng cách cực đại:       {accepted['snap_distance_cm'].max():.2f} cm (<= {D_MAX_M*100:.1f} cm)")

    print(f"\n3. ĐẶC TÍNH UỐN NẮN GÓC XOAY (ANGLE_ERROR) TRÊN {len(accepted)} BOX ACCEPTED:")
    print(f"  Độ lệch góc trước snapping: {accepted['angle_error_deg'].mean():.3f}° (Median: {accepted['angle_error_deg'].median():.3f}°, Max: {accepted['angle_error_deg'].max():.3f}°)")
    print(f"  Độ lệch góc sau snapping:   0.000° (100% uốn nắn song song hoàn hảo theo trục chuỗi giàn pin)")

    # Đánh giá riêng cho nhóm 435 OBB khuyết tật nhiệt
    defects = df_out[df_out['Is_Defect'] == 'CÓ']
    def_accepted = defects[defects['snap_status'] == 'SNAP_ACCEPTED']
    print(f"\n4. ĐÁNH GIÁ CHUYÊN BIỆT CHO NHÓM KHUYẾT TẬT NHIỆT ({len(defects)} OBB):")
    print(defects['snap_status'].value_counts())
    print(f"  Tỷ lệ khuyết tật nhiệt được snapping thành công: {len(def_accepted)} / {len(defects)} ({len(def_accepted)/len(defects)*100:.2f}%)")
    print(f"  Khoảng cách hút trung bình khuyết tật nhiệt:     {def_accepted['snap_distance_cm'].mean():.2f} cm (Median: {def_accepted['snap_distance_cm'].median():.2f} cm)")

if __name__ == '__main__':
    main()
