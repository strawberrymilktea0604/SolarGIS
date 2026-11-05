"""
Module: test_collinearity_and_spacing_evaluation.py
Mục đích:
- Chạy thử nghiệm đánh giá sự phục hồi của tính thẳng hàng (Collinearity) 
  và tính đồng đều của bước lưới (Panel Spacing) trên khối giàn pin thử nghiệm
  (tập trung chuyên sâu vào Block 2 - String 6 và mở rộng toàn bộ 64 hàng pin).
- So sánh định lượng 3 trạng thái:
    1. Trước hiệu chỉnh (Homography p_i từ ảnh trực giao 85m)
    2. Sau Mass-Spring Regularization (q_i)
    3. Sau Topological Snapping (q_snap)
    Đối soát với mốc trắc địa lý tưởng QGIS (g_i từ bbox_centroid_export.csv).
- Đo đạc:
    + Độ lệch thẳng hàng RMS E_line, Median, Max lệch.
    + Bước lưới dọc hàng s_bar, độ lệch chuẩn sigma_s, hệ số biến thiên CV_s (%).
    + Bước lưới giữa hàng s_v, độ lệch chuẩn sigma_v, hệ số biến thiên CV_v (%).
    + Tỷ lệ cải thiện I_E và I_CV.
- Xuất 2 file kết quả:
    + Bounding Box/PV_Collinearity_and_Spacing_Evaluation.csv (chi tiết từng module)
    + Bounding Box/PV_String_Row_Collinearity_Summary.csv (tổng hợp từng hàng pin)
"""

import os
import sys
import math
import numpy as np
import pandas as pd

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def fit_line_and_calc_errors(coords):
    """
    Khớp đường thẳng bình phương tối thiểu ax + by + c = 0
    và tính khoảng cách vuông góc d_i từ từng điểm đến đường thẳng.
    """
    if len(coords) < 3:
        return np.nan, np.nan, np.nan, np.zeros(len(coords)), (0, 0, 0)
    
    X = coords[:, 0]
    Y = coords[:, 1]
    
    # Do giàn pin chạy dọc trục Đông - Tây (X biến thiên lớn, Y gần như cố định),
    # khớp Y = a * X + b => a * X - Y + b = 0
    p = np.polyfit(X, Y, deg=1)
    a = float(p[0])
    b = -1.0
    c = float(p[1])
    
    denom = math.sqrt(a**2 + b**2)
    distances = np.abs(a * X + b * Y + c) / denom
    
    rms = float(np.sqrt(np.mean(distances**2)))
    med = float(np.median(distances))
    max_d = float(np.max(distances))
    
    return rms, med, max_d, distances, (a, b, c)

def calc_spacing_stats(coords, min_s=1.5, max_s=2.5):
    """
    Tính bước lưới giữa các tấm pin liên tiếp cùng hàng đã sắp xếp theo X:
    s_i = ||p_{i+1} - p_i||_2
    Lọc các bước lưới thực sự (bỏ qua khoảng trống lớn do detector bỏ sót module).
    """
    if len(coords) < 2:
        return np.nan, np.nan, np.nan, 0
    
    # Sắp xếp theo trục X
    sorted_idx = np.argsort(coords[:, 0])
    sorted_pts = coords[sorted_idx]
    
    diffs = np.diff(sorted_pts, axis=0)
    spacings = np.linalg.norm(diffs, axis=1)
    
    # Lọc các khoảng cách danh định (bước module tiêu chuẩn ~ 1.91 m)
    valid_spacings = spacings[(spacings >= min_s) & (spacings <= max_s)]
    
    if len(valid_spacings) == 0:
        return np.nan, np.nan, np.nan, 0
    
    s_mean = float(np.mean(valid_spacings))
    s_std = float(np.std(valid_spacings, ddof=1)) if len(valid_spacings) > 1 else 0.0
    cv = float((s_std / s_mean) * 100.0) if s_mean > 0 else np.nan
    
    return s_mean, s_std, cv, len(valid_spacings)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.abspath(os.path.join(script_dir, ".."))

    ref_csv = os.path.join(workspace_dir, "bbox_centroid_export.csv")
    snap_csv = os.path.join(script_dir, "PV_Topological_Snapping_Evaluation.csv")
    if not os.path.exists(snap_csv):
        snap_csv = os.path.join(workspace_dir, "PV_Topological_Snapping_Evaluation.csv")

    ms_csv = os.path.join(script_dir, "PV_Mass_Spring_Regularization_Evaluation.csv")
    if not os.path.exists(ms_csv):
        ms_csv = os.path.join(workspace_dir, "PV_Mass_Spring_Regularization_Evaluation.csv")

    out_panel_csv = os.path.join(script_dir, "PV_Collinearity_and_Spacing_Evaluation.csv")
    out_panel_csv_ws = os.path.join(workspace_dir, "PV_Collinearity_and_Spacing_Evaluation.csv")
    out_summary_csv = os.path.join(script_dir, "PV_String_Row_Collinearity_Summary.csv")
    out_summary_csv_ws = os.path.join(workspace_dir, "PV_String_Row_Collinearity_Summary.csv")

    print("Loading datasets...")
    df_ref = pd.read_csv(ref_csv)
    df_snap = pd.read_csv(snap_csv)
    df_ms = pd.read_csv(ms_csv) if os.path.exists(ms_csv) else None

    # Hợp nhất dữ liệu
    df_snap['match_id'] = df_snap['match_id'].astype(str)
    df_ref['match_id'] = df_ref['module_id'].astype(str)

    m = pd.merge(df_snap, df_ref[['match_id', 'layer', 'String_ID', 'Row_ID', 'centroid_x', 'centroid_y']], on='match_id', how='left')

    if df_ms is not None:
        df_ms['match_id'] = df_ms['match_id'].astype(str)
        m = pd.merge(m, df_ms[['match_id', 'Regularized_X_q_m', 'Regularized_Y_q_m']], on='match_id', how='left')

    # Lọc các bản ghi có đầy đủ thông tin hàng/chuỗi
    m_valid = m[m['Row_ID'].notna() & m['mapped_cx'].notna()].copy()
    m_valid['Row_ID'] = m_valid['Row_ID'].astype(int)

    print(f"Total valid modules with row metadata: {len(m_valid)}")

    # Nhóm theo Layer + String + Row_ID
    groups = m_valid.groupby(['layer', 'String_ID', 'Row_ID'])

    row_summaries = []
    panel_records = []

    for (layer, str_id, row_id), grp in groups:
        n_pts = len(grp)
        if n_pts < 5:
            continue

        pts_before = grp[['mapped_cx', 'mapped_cy']].values.astype(np.float64)
        pts_snap = grp[['snapped_cx', 'snapped_cy']].values.astype(np.float64)
        pts_ref = grp[['centroid_x', 'centroid_y']].values.astype(np.float64)

        if 'Regularized_X_q_m' in grp:
            pts_ms = grp[['Regularized_X_q_m', 'Regularized_Y_q_m']].values.astype(np.float64)
        else:
            pts_ms = pts_before.copy()

        # 1. Tính toán Collinearity
        rms_b, med_b, max_b, dists_b, line_b = fit_line_and_calc_errors(pts_before)
        rms_ms, med_ms, max_ms, dists_ms, line_ms = fit_line_and_calc_errors(pts_ms)
        rms_s, med_s, max_s, dists_s, line_s = fit_line_and_calc_errors(pts_snap)
        rms_ref, med_ref, max_ref, dists_ref, line_ref = fit_line_and_calc_errors(pts_ref)

        # 2. Tính toán Spacing dọc hàng
        s_mean_b, s_std_b, cv_b, m_pairs_b = calc_spacing_stats(pts_before)
        s_mean_ms, s_std_ms, cv_ms, m_pairs_ms = calc_spacing_stats(pts_ms)
        s_mean_s, s_std_s, cv_s, m_pairs_s = calc_spacing_stats(pts_snap)
        s_mean_ref, s_std_ref, cv_ref, m_pairs_ref = calc_spacing_stats(pts_ref)

        # Mức cải thiện (%)
        impr_rms_ms = ((rms_b - rms_ms) / rms_b * 100.0) if rms_b > 0 else 0.0
        impr_rms_snap = ((rms_b - rms_s) / rms_b * 100.0) if rms_b > 0 else 0.0
        impr_cv_snap = ((cv_b - cv_s) / cv_b * 100.0) if cv_b > 0 else 0.0

        row_summaries.append({
            'layer': layer,
            'String_ID': str_id,
            'Row_ID': row_id,
            'Row_Name': f"{layer}_{str_id}_Row{row_id}",
            'Num_Detections': n_pts,
            # Collinearity Before (cm)
            'Collinearity_RMS_Before_cm': round(rms_b * 100.0, 2),
            'Collinearity_Median_Before_cm': round(med_b * 100.0, 2),
            'Collinearity_Max_Before_cm': round(max_b * 100.0, 2),
            # Collinearity Mass-Spring (cm)
            'Collinearity_RMS_MassSpring_cm': round(rms_ms * 100.0, 2),
            'Collinearity_Median_MassSpring_cm': round(med_ms * 100.0, 2),
            'Collinearity_Max_MassSpring_cm': round(max_ms * 100.0, 2),
            # Collinearity Snapped (cm)
            'Collinearity_RMS_Snapped_cm': round(rms_s * 100.0, 2),
            'Collinearity_Median_Snapped_cm': round(med_s * 100.0, 2),
            'Collinearity_Max_Snapped_cm': round(max_s * 100.0, 2),
            # Collinearity Reference (cm)
            'Collinearity_RMS_Ref_cm': round(rms_ref * 100.0, 2),
            'Collinearity_Median_Ref_cm': round(med_ref * 100.0, 2),
            'Collinearity_Max_Ref_cm': round(max_ref * 100.0, 2),
            # Cải thiện Collinearity (%)
            'Impr_Collinearity_MassSpring_Pct': round(impr_rms_ms, 2),
            'Impr_Collinearity_Snapped_Pct': round(impr_rms_snap, 2),
            # Spacing Before (m)
            'Spacing_Mean_Before_m': round(s_mean_b, 4),
            'Spacing_Std_Before_cm': round(s_std_b * 100.0, 2),
            'Spacing_CV_Before_Pct': round(cv_b, 2),
            # Spacing Mass-Spring (m)
            'Spacing_Mean_MassSpring_m': round(s_mean_ms, 4),
            'Spacing_Std_MassSpring_cm': round(s_std_ms * 100.0, 2),
            'Spacing_CV_MassSpring_Pct': round(cv_ms, 2),
            # Spacing Snapped (m)
            'Spacing_Mean_Snapped_m': round(s_mean_s, 4),
            'Spacing_Std_Snapped_cm': round(s_std_s * 100.0, 2),
            'Spacing_CV_Snapped_Pct': round(cv_s, 2),
            # Spacing Reference (m)
            'Spacing_Mean_Ref_m': round(s_mean_ref, 4),
            'Spacing_Std_Ref_cm': round(s_std_ref * 100.0, 2),
            'Spacing_CV_Ref_Pct': round(cv_ref, 2),
            # Cải thiện Spacing (%)
            'Impr_Spacing_CV_Pct': round(impr_cv_snap, 2)
        })

        # Ghi nhận chi tiết từng panel
        for idx, (p_idx, r_p) in enumerate(grp.iterrows()):
            panel_records.append({
                'Point_Name': r_p['Point_Name'],
                'match_id': r_p['match_id'],
                'layer': layer,
                'String_ID': str_id,
                'Row_ID': row_id,
                'Class': r_p['Class'],
                'Is_Defect': r_p['Is_Defect'],
                'mapped_cx': r_p['mapped_cx'],
                'mapped_cy': r_p['mapped_cy'],
                'snapped_cx': r_p['snapped_cx'],
                'snapped_cy': r_p['snapped_cy'],
                'centroid_x_ref': r_p['centroid_x'],
                'centroid_y_ref': r_p['centroid_y'],
                'Dist_To_Row_Line_Before_cm': round(dists_b[idx] * 100.0, 2),
                'Dist_To_Row_Line_Snapped_cm': round(dists_s[idx] * 100.0, 2),
                'Dist_To_Row_Line_Ref_cm': round(dists_ref[idx] * 100.0, 2),
                'snap_status': r_p['snap_status']
            })

    df_sum = pd.DataFrame(row_summaries)
    df_panel = pd.DataFrame(panel_records)

    df_sum.to_csv(out_summary_csv, index=False, encoding='utf-8-sig')
    df_sum.to_csv(out_summary_csv_ws, index=False, encoding='utf-8-sig')

    df_panel.to_csv(out_panel_csv, index=False, encoding='utf-8-sig')
    df_panel.to_csv(out_panel_csv_ws, index=False, encoding='utf-8-sig')

    print(f"\nSaved summary to: {out_summary_csv}")
    print(f"Saved panel details to: {out_panel_csv}")
    print(f"Total evaluated rows: {len(df_sum)}")

    # 3. Phân tích chuyên sâu trên Khối giàn thử nghiệm Block 2 - String 6
    s6 = df_sum[(df_sum['layer'] == 'Block2') & (df_sum['String_ID'] == 'string6')]
    print("\n================ KẾT QUẢ TRÊN KHỐI GIÀN PIN THỬ NGHIỆM (BLOCK 2 - STRING 6) ================")
    print(f"Số hàng khảo sát: {len(s6)} hàng (Row 1..4), tổng cộng {s6['Num_Detections'].sum()} modules")
    print(f"{'Chỉ số':<35} | {'Trước hiệu chỉnh':<20} | {'Sau Snapping':<20} | {'Mốc GIS QGIS':<15} | {'Mức cải thiện':<15}")
    print("-" * 115)
    
    rms_b_s6 = np.sqrt(np.mean(s6['Collinearity_RMS_Before_cm']**2))
    rms_s_s6 = np.sqrt(np.mean(s6['Collinearity_RMS_Snapped_cm']**2))
    rms_ref_s6 = np.sqrt(np.mean(s6['Collinearity_RMS_Ref_cm']**2))
    print(f"{'Độ lệch thẳng hàng RMS (cm)':<35} | {rms_b_s6:<20.2f} | {rms_s_s6:<20.2f} | {rms_ref_s6:<15.2f} | {((rms_b_s6 - rms_s_s6)/rms_b_s6*100):<+14.2f}%")

    med_b_s6 = s6['Collinearity_Median_Before_cm'].mean()
    med_s_s6 = s6['Collinearity_Median_Snapped_cm'].mean()
    med_ref_s6 = s6['Collinearity_Median_Ref_cm'].mean()
    print(f"{'Độ lệch thẳng hàng Trung vị (cm)':<35} | {med_b_s6:<20.2f} | {med_s_s6:<20.2f} | {med_ref_s6:<15.2f} | {((med_b_s6 - med_s_s6)/med_b_s6*100):<+14.2f}%")

    max_b_s6 = s6['Collinearity_Max_Before_cm'].max()
    max_s_s6 = s6['Collinearity_Max_Snapped_cm'].max()
    max_ref_s6 = s6['Collinearity_Max_Ref_cm'].max()
    print(f"{'Độ lệch thẳng hàng Cực đại (cm)':<35} | {max_b_s6:<20.2f} | {max_s_s6:<20.2f} | {max_ref_s6:<15.2f} | {((max_b_s6 - max_s_s6)/max_b_s6*100):<+14.2f}%")

    cv_b_s6 = s6['Spacing_CV_Before_Pct'].mean()
    cv_s_s6 = s6['Spacing_CV_Snapped_Pct'].mean()
    cv_ref_s6 = s6['Spacing_CV_Ref_Pct'].mean()
    print(f"{'Hệ số biến thiên bước lưới CV (%)':<35} | {cv_b_s6:<20.2f} | {cv_s_s6:<20.2f} | {cv_ref_s6:<15.2f} | {((cv_b_s6 - cv_s_s6)/cv_b_s6*100):<+14.2f}%")

    std_b_s6 = s6['Spacing_Std_Before_cm'].mean()
    std_s_s6 = s6['Spacing_Std_Snapped_cm'].mean()
    std_ref_s6 = s6['Spacing_Std_Ref_cm'].mean()
    print(f"{'Độ lệch chuẩn bước lưới (cm)':<35} | {std_b_s6:<20.2f} | {std_s_s6:<20.2f} | {std_ref_s6:<15.2f} | {((std_b_s6 - std_s_s6)/std_b_s6*100):<+14.2f}%")

    # 4. Tính bước lưới giữa các hàng lân cận (Vertical Spacing Row 1 <-> Row 2, Row 3 <-> Row 4)
    # Tìm các cặp module có cùng số thứ tự trong cùng chuỗi
    print("\n--- ĐO ĐẠC BƯỚC LƯỚI GIỮA HAI HÀNG LÂN CẬN (VERTICAL ROW PITCH) ---")
    vert_records = []
    for str_name in ['string6', 'string7', 'string10']:
        s_data = m_valid[m_valid['String_ID'] == str_name]
        r1 = s_data[s_data['Row_ID'] == 1].set_index('candidate_col')
        r2 = s_data[s_data['Row_ID'] == 2].set_index('candidate_col')
        common = r1.index.intersection(r2.index)
        for c in common:
            p1_b = np.array([r1.loc[c, 'mapped_cx'], r1.loc[c, 'mapped_cy']])
            p2_b = np.array([r2.loc[c, 'mapped_cx'], r2.loc[c, 'mapped_cy']])
            d_b = np.linalg.norm(p2_b - p1_b)

            p1_s = np.array([r1.loc[c, 'snapped_cx'], r1.loc[c, 'snapped_cy']])
            p2_s = np.array([r2.loc[c, 'snapped_cx'], r2.loc[c, 'snapped_cy']])
            d_s = np.linalg.norm(p2_s - p1_s)

            p1_r = np.array([r1.loc[c, 'centroid_x'], r1.loc[c, 'centroid_y']])
            p2_r = np.array([r2.loc[c, 'centroid_x'], r2.loc[c, 'centroid_y']])
            d_r = np.linalg.norm(p2_r - p1_r)

            vert_records.append({'d_b': d_b, 'd_s': d_s, 'd_r': d_r})

    v_df = pd.DataFrame(vert_records)
    print(f"Tổng số cặp đối chứng bước hàng: {len(v_df)}")
    print(f"Bước hàng trước hiệu chỉnh: Mean = {v_df['d_b'].mean():.4f} m, Std = {v_df['d_b'].std()*100:.2f} cm, CV = {v_df['d_b'].std()/v_df['d_b'].mean()*100:.2f}%")
    print(f"Bước hàng sau Snapping:     Mean = {v_df['d_s'].mean():.4f} m, Std = {v_df['d_s'].std()*100:.2f} cm, CV = {v_df['d_s'].std()/v_df['d_s'].mean()*100:.2f}%")
    print(f"Bước hàng mốc GIS chuẩn:    Mean = {v_df['d_r'].mean():.4f} m, Std = {v_df['d_r'].std()*100:.2f} cm, CV = {v_df['d_r'].std()/v_df['d_r'].mean()*100:.2f}%")

    # 5. Thống kê toàn cục trên toàn bộ 64 hàng pin
    print("\n================ TỔNG HỢP TOÀN CỤC TRÊN TẤT CẢ 64 HÀNG PIN ================")
    print(f"Độ lệch thẳng hàng RMS trung bình: {df_sum['Collinearity_RMS_Before_cm'].mean():.2f} cm -> {df_sum['Collinearity_RMS_Snapped_cm'].mean():.2f} cm (Giảm {((df_sum['Collinearity_RMS_Before_cm'].mean() - df_sum['Collinearity_RMS_Snapped_cm'].mean())/df_sum['Collinearity_RMS_Before_cm'].mean()*100):.2f}%)")
    print(f"Hệ số biến thiên bước lưới CV trung bình: {df_sum['Spacing_CV_Before_Pct'].mean():.2f}% -> {df_sum['Spacing_CV_Snapped_Pct'].mean():.2f}% (Giảm {((df_sum['Spacing_CV_Before_Pct'].mean() - df_sum['Spacing_CV_Snapped_Pct'].mean())/df_sum['Spacing_CV_Before_Pct'].mean()*100):.2f}%)")

if __name__ == '__main__':
    main()
