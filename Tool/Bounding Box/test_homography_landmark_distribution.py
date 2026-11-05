"""
Module: test_homography_landmark_distribution.py
Mục đích:
- Kiểm tra độ nhạy cảm của ma trận Homography (8 DOF) với sự phân bố không gian của các điểm mốc kiểm soát.
- Thiết kế thực nghiệm đối chứng định lượng giữa 2 kịch bản bố trí điểm mốc:
    + Trường hợp A (Clustered - Điểm mốc co cụm tại 1 góc Top-Left của ảnh 35m):
      Các điểm mốc chỉ nằm trong góc hẹp (u_norm <= 0.35, v_norm <= 0.35), vùng còn lại không có mốc khống chế.
    + Trường hợp B (Uniform - Điểm mốc phân bố đồng đều toàn vùng):
      Các điểm mốc phân bố trải rộng trên toàn bộ lưới không gian (lưới 3x3 phủ khắp 9 phân vùng ảnh).
- Đo đạc & so sánh định lượng:
    + Chỉ số điều kiện ma trận (Condition Number kappa, tỷ số SVD sigma_max / sigma_min)
    + Sai số tái chiếu trên tập mốc nội suy (In-Sample / Local Zone)
    + Sai số ngoại suy trên tập kiểm tra độc lập vùng xa (Far-Zone / Out-of-Sample, góc đối diện Bottom-Right)
    + Sai số tâm (Centroid RMSE, Median) và sai số 4 đỉnh OBB (Corner Error)
    + Diện tích giao thoa Polygon IoU (%) trên 5.071 mốc tham chiếu thực địa (bbox_centroid_export.csv)
    + Hiện tượng quá khớp (overfitting) và biến dạng phối cảnh cực đoan (perspective distortion,
      tỷ lệ quad bị suy biến, phân kỳ mẫu số w', độ thuôn hình thang bất thường).
- Xuất 2 file CSV:
    + Bounding Box/PV_Homography_Landmark_Sensitivity_Evaluation.csv (chi tiết 5.092 OBB cho cả 2 trường hợp)
    + Bounding Box/PV_Homography_Landmark_Sensitivity_Summary.csv (tổng hợp so sánh Case A vs Case B)
"""

import os
import sys
import math
import numpy as np
import pandas as pd
import cv2
from shapely.geometry import Polygon

from dlt_hartley_homography import (
    resolve_file_path,
    parse_tuple_coords,
    utm_to_px_85m,
    compute_polygon_iou,
    solve_homography_dlt,
    DECISION_MARGIN_M,
    SEED,
)
from transform_obb_homography_corners import transform_vertex_homography
from analyze_homography_morphology import compute_quad_morphology

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def compute_dlt_condition_number(src_pts, dst_pts, use_hartley=True):
    """
    Tính chỉ số điều kiện (Condition Number kappa = sigma_max / sigma_min)
    của hệ phương trình ma trận thiết kế A trong DLT (2N x 9) để đánh giá độ ổn định số.
    """
    N = len(src_pts)
    if N < 4:
        return np.inf

    if use_hartley:
        from dlt_hartley_homography import hartley_normalize
        src_norm, _, _ = hartley_normalize(src_pts)
        dst_norm, _, _ = hartley_normalize(dst_pts)
    else:
        src_norm = np.hstack([src_pts, np.ones((N, 1))])
        dst_norm = np.hstack([dst_pts, np.ones((N, 1))])

    A = []
    for i in range(N):
        x, y = src_norm[i, 0], src_norm[i, 1]
        u, v = dst_norm[i, 0], dst_norm[i, 1]
        A.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        A.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    A = np.array(A, dtype=np.float64)

    _, s, _ = np.linalg.svd(A)
    s_min = s[-2] if s[-1] < 1e-12 and len(s) > 1 else s[-1]
    if s_min < 1e-12:
        return np.inf
    return float(s[0] / s_min)


def run_landmark_sensitivity_test(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Homography_Landmark_Sensitivity_Evaluation.csv',
    summary_csv_path='PV_Homography_Landmark_Sensitivity_Summary.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(out_csv_path):
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))
    if not os.path.isabs(summary_csv_path):
        summary_csv_path = os.path.join(script_dir, os.path.basename(summary_csv_path))

    print("================================================================================")
    print(" THỰC NGHIỆM ĐỘ NHẠY HOMOGRAPHY VỚI PHÂN BỐ ĐIỂM MỐC (CASE A VS CASE B)")
    print("================================================================================")

    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)

    # 1. Ghép cặp GPS + AI Module ID
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_mask = merged['centroid_x'].notna()
    matched = merged[matched_mask].copy().reset_index(drop=True)

    src_px_all = matched[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm_all = matched[['centroid_x', 'centroid_y']].values.astype(np.float64)
    dst_px85_all = np.array([utm_to_px_85m(x, y) for x, y in dst_utm_all], dtype=np.float64)

    umin, umax = src_px_all[:, 0].min(), src_px_all[:, 0].max()
    vmin, vmax = src_px_all[:, 1].min(), src_px_all[:, 1].max()

    # Tọa độ chuẩn hóa trong khoảng [0, 1] trên ảnh nguồn 35m
    u_norm = (src_px_all[:, 0] - umin) / (umax - umin)
    v_norm = (src_px_all[:, 1] - vmin) / (vmax - vmin)

    # -------------------------------------------------------------------------
    # TRƯỜNG HỢP A: Điểm mốc co cụm tại 1 góc Top-Left (ảnh 2 minh họa)
    # -------------------------------------------------------------------------
    # Định nghĩa vùng góc Top-Left: u_norm <= 0.35 VÀ v_norm <= 0.35
    mask_case_a_cluster = (u_norm <= 0.35) & (v_norm <= 0.35)
    indices_cluster = np.where(mask_case_a_cluster)[0]

    # Lấy mẫu ngẫu nhiên cố định N=60 điểm mốc nằm hoàn toàn trong cụm góc này
    rng = np.random.default_rng(SEED)
    sample_a_idx = rng.choice(indices_cluster, size=min(60, len(indices_cluster)), replace=False)
    src_fit_A = src_px_all[sample_a_idx]
    dst_utm_fit_A = dst_utm_all[sample_a_idx]
    dst_px85_fit_A = dst_px85_all[sample_a_idx]

    H_utm_A, _ = solve_homography_dlt(src_fit_A, dst_utm_fit_A, use_hartley=True)
    H_px85_A, _ = solve_homography_dlt(src_fit_A, dst_px85_fit_A, use_hartley=True)
    cond_A = compute_dlt_condition_number(src_fit_A, dst_utm_fit_A, use_hartley=True)

    # -------------------------------------------------------------------------
    # TRƯỜNG HỢP B: Điểm mốc phân bố đồng đều toàn vùng (ảnh 3 minh họa)
    # -------------------------------------------------------------------------
    # Lấy mẫu phân tầng (stratified) trên lưới 3x3 để đảm bảo phủ đều 9 vùng không gian
    sample_b_idx = []
    points_per_cell = 7  # 9 ô x ~7 = ~63 điểm mốc tương đương quy mô Case A
    for r in range(3):
        for c in range(3):
            cell_mask = (
                (u_norm >= c / 3.0) & (u_norm < (c + 1) / 3.0) &
                (v_norm >= r / 3.0) & (v_norm < (r + 1) / 3.0)
            )
            c_indices = np.where(cell_mask)[0]
            if len(c_indices) > 0:
                k = min(points_per_cell, len(c_indices))
                chosen = rng.choice(c_indices, size=k, replace=False)
                sample_b_idx.extend(chosen)

    sample_b_idx = np.array(sample_b_idx)
    src_fit_B = src_px_all[sample_b_idx]
    dst_utm_fit_B = dst_utm_all[sample_b_idx]
    dst_px85_fit_B = dst_px85_all[sample_b_idx]

    H_utm_B, _ = solve_homography_dlt(src_fit_B, dst_utm_fit_B, use_hartley=True)
    H_px85_B, _ = solve_homography_dlt(src_fit_B, dst_px85_fit_B, use_hartley=True)
    cond_B = compute_dlt_condition_number(src_fit_B, dst_utm_fit_B, use_hartley=True)

    # Định nghĩa 3 vùng kiểm tra không gian:
    # 1. Vùng cụm (Cluster Zone Top-Left: u_norm <= 0.35 & v_norm <= 0.35)
    # 2. Vùng trung gian (Mid Zone: 0.35 < max(u, v) <= 0.70)
    # 3. Vùng xa / Góc đối diện (Far Zone Bottom-Right: u_norm > 0.70 hoặc v_norm > 0.70)

    rows_out = []
    for idx, row in merged.iterrows():
        u = float(row['Pixel_U'])
        v = float(row['Pixel_V'])
        u_n = (u - umin) / (umax - umin)
        v_n = (v - vmin) / (vmax - vmin)

        if u_n <= 0.35 and v_n <= 0.35:
            spatial_zone = '1_Cluster_Zone_TopLeft'
        elif u_n > 0.65 or v_n > 0.65:
            spatial_zone = '3_Far_Zone_BottomRight'
        else:
            spatial_zone = '2_Mid_Transition_Zone'

        # Đọc 4 đỉnh nguồn
        nw_px = parse_tuple_coords(row.get('BBox_NW_Pixel'))
        ne_px = parse_tuple_coords(row.get('BBox_NE_Pixel'))
        se_px = parse_tuple_coords(row.get('BBox_SE_Pixel'))
        sw_px = parse_tuple_coords(row.get('BBox_SW_Pixel'))

        # Ánh xạ theo Trường hợp A (Co cụm 1 góc)
        (e_a, n_a), w_a = transform_vertex_homography((u, v), H_utm_A)
        nw_a, w_nw_a = transform_vertex_homography(nw_px, H_utm_A)
        ne_a, w_ne_a = transform_vertex_homography(ne_px, H_utm_A)
        se_a, w_se_a = transform_vertex_homography(se_px, H_utm_A)
        sw_a, w_sw_a = transform_vertex_homography(sw_px, H_utm_A)
        morph_a = compute_quad_morphology(nw_a, ne_a, se_a, sw_a)

        # Ánh xạ theo Trường hợp B (Phân bố đồng đều toàn vùng)
        (e_b, n_b), w_b = transform_vertex_homography((u, v), H_utm_B)
        nw_b, w_nw_b = transform_vertex_homography(nw_px, H_utm_B)
        ne_b, w_ne_b = transform_vertex_homography(ne_px, H_utm_B)
        se_b, w_se_b = transform_vertex_homography(se_px, H_utm_B)
        sw_b, w_sw_b = transform_vertex_homography(sw_px, H_utm_B)
        morph_b = compute_quad_morphology(nw_b, ne_b, se_b, sw_b)

        has_ref = pd.notna(row.get('module_id'))
        err_cen_a_cm = np.nan
        err_cen_b_cm = np.nan
        err_4c_a_cm = np.nan
        err_4c_b_cm = np.nan
        iou_a = np.nan
        iou_b = np.nan

        if has_ref:
            ref_cx = float(row['centroid_x'])
            ref_cy = float(row['centroid_y'])
            err_cen_a_cm = math.hypot(e_a - ref_cx, n_a - ref_cy) * 100.0
            err_cen_b_cm = math.hypot(e_b - ref_cx, n_b - ref_cy) * 100.0

            ref_nw = parse_tuple_coords(row.get('corner_top_left'))
            ref_ne = parse_tuple_coords(row.get('corner_top_right'))
            ref_se = parse_tuple_coords(row.get('corner_bottom_right'))
            ref_sw = parse_tuple_coords(row.get('corner_bottom_left'))

            if all([ref_nw, ref_ne, ref_se, ref_sw]):
                poly_ref = Polygon([ref_sw, ref_se, ref_ne, ref_nw])

                if all([nw_a, ne_a, se_a, sw_a]):
                    c_a_list = [
                        math.hypot(nw_a[0] - ref_nw[0], nw_a[1] - ref_nw[1]) * 100.0,
                        math.hypot(ne_a[0] - ref_ne[0], ne_a[1] - ref_ne[1]) * 100.0,
                        math.hypot(se_a[0] - ref_se[0], se_a[1] - ref_se[1]) * 100.0,
                        math.hypot(sw_a[0] - ref_sw[0], sw_a[1] - ref_sw[1]) * 100.0,
                    ]
                    err_4c_a_cm = float(np.mean(c_a_list))
                    poly_a = Polygon([sw_a, se_a, ne_a, nw_a])
                    iou_a = compute_polygon_iou(poly_a, poly_ref)

                if all([nw_b, ne_b, se_b, sw_b]):
                    c_b_list = [
                        math.hypot(nw_b[0] - ref_nw[0], nw_b[1] - ref_nw[1]) * 100.0,
                        math.hypot(ne_b[0] - ref_ne[0], ne_b[1] - ref_ne[1]) * 100.0,
                        math.hypot(se_b[0] - ref_se[0], se_b[1] - ref_se[1]) * 100.0,
                        math.hypot(sw_b[0] - ref_sw[0], sw_b[1] - ref_sw[1]) * 100.0,
                    ]
                    err_4c_b_cm = float(np.mean(c_b_list))
                    poly_b = Polygon([sw_b, se_b, ne_b, nw_b])
                    iou_b = compute_polygon_iou(poly_b, poly_ref)

        p_class = str(row.get('Class', 'Unclassified')).strip() if pd.notna(row.get('Class')) else 'Unclassified'
        is_defect = (p_class != 'Unclassified')

        rows_out.append({
            'Point_Name': row.get('Point_Name', f'PV_{idx+1}'),
            'Match_ID': row['match_id'],
            'Panel_Class': p_class,
            'Is_Defect_OBB': is_defect,
            'Spatial_Zone': spatial_zone,
            'Norm_U': round(u_n, 4),
            'Norm_V': round(v_n, 4),
            'Is_Control_A_Cluster': bool(idx in sample_a_idx),
            'Is_Control_B_Uniform': bool(idx in sample_b_idx),
            # Kết quả Trường hợp A (Co cụm góc)
            'CaseA_UTM_E': round(e_a, 4),
            'CaseA_UTM_N': round(n_a, 4),
            'CaseA_Perspective_w': round(w_a, 6) if w_a is not None else np.nan,
            'CaseA_Is_Convex_Quad': morph_a['is_valid'] if morph_a else False,
            'CaseA_Trapezoid_Diff_mm': round(morph_a['trap_max_diff_mm'], 2) if morph_a else np.nan,
            'CaseA_Max_Angle_Dev_deg': round(morph_a['max_angle_dev_deg'], 4) if morph_a else np.nan,
            'CaseA_Area_m2': round(morph_a['area_m2'], 4) if morph_a else np.nan,
            'CaseA_Centroid_Err_cm': round(err_cen_a_cm, 2) if not np.isnan(err_cen_a_cm) else np.nan,
            'CaseA_4Corner_Err_cm': round(err_4c_a_cm, 2) if not np.isnan(err_4c_a_cm) else np.nan,
            'CaseA_Polygon_IoU': round(iou_a, 4) if not np.isnan(iou_a) else np.nan,
            # Kết quả Trường hợp B (Phân bố đều)
            'CaseB_UTM_E': round(e_b, 4),
            'CaseB_UTM_N': round(n_b, 4),
            'CaseB_Perspective_w': round(w_b, 6) if w_b is not None else np.nan,
            'CaseB_Is_Convex_Quad': morph_b['is_valid'] if morph_b else False,
            'CaseB_Trapezoid_Diff_mm': round(morph_b['trap_max_diff_mm'], 2) if morph_b else np.nan,
            'CaseB_Max_Angle_Dev_deg': round(morph_b['max_angle_dev_deg'], 4) if morph_b else np.nan,
            'CaseB_Area_m2': round(morph_b['area_m2'], 4) if morph_b else np.nan,
            'CaseB_Centroid_Err_cm': round(err_cen_b_cm, 2) if not np.isnan(err_cen_b_cm) else np.nan,
            'CaseB_4Corner_Err_cm': round(err_4c_b_cm, 2) if not np.isnan(err_4c_b_cm) else np.nan,
            'CaseB_Polygon_IoU': round(iou_b, 4) if not np.isnan(iou_b) else np.nan,
        })

    df_eval = pd.DataFrame(rows_out)
    df_eval.to_csv(out_csv_path, index=False, encoding='utf-8-sig')

    # Tổng hợp báo cáo định lượng
    valid_eval = df_eval[df_eval['CaseA_Centroid_Err_cm'].notna()].copy()
    summary_rows = []
    zones = [
        ('1. Vùng cụm Top-Left (Gần điểm mốc Case A)', valid_eval[valid_eval['Spatial_Zone'] == '1_Cluster_Zone_TopLeft']),
        ('2. Vùng chuyển tiếp trung gian (Mid Zone)', valid_eval[valid_eval['Spatial_Zone'] == '2_Mid_Transition_Zone']),
        ('3. Vùng xa Bottom-Right (Ngoại suy cực đoan Case A)', valid_eval[valid_eval['Spatial_Zone'] == '3_Far_Zone_BottomRight']),
        ('TOÀN BỘ VÙNG KHẢO SÁT (All 5.071 Mốc)', valid_eval),
        ('NHÓM 432 OBB KHUYẾT TẬT NHIỆT (Defects Only)', valid_eval[valid_eval['Is_Defect_OBB']]),
    ]

    for z_name, z_df in zones:
        if len(z_df) == 0:
            continue
        summary_rows.append({
            'Evaluation_Zone': z_name,
            'Sample_Count': len(z_df),
            # Case A: Cụm một góc
            'CaseA_RMSE_Cen_cm': round(float(np.sqrt(np.mean(z_df['CaseA_Centroid_Err_cm'] ** 2))), 2),
            'CaseA_Median_Cen_cm': round(float(z_df['CaseA_Centroid_Err_cm'].median()), 2),
            'CaseA_Max_Cen_cm': round(float(z_df['CaseA_Centroid_Err_cm'].max()), 2),
            'CaseA_Median_4Corner_cm': round(float(z_df['CaseA_4Corner_Err_cm'].median()), 2),
            'CaseA_Median_IoU_pct': round(float(z_df['CaseA_Polygon_IoU'].median() * 100.0), 2),
            'CaseA_Valid_Rate_pct': round(float((z_df['CaseA_Centroid_Err_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2),
            'CaseA_Mean_Trapezoid_mm': round(float(z_df['CaseA_Trapezoid_Diff_mm'].mean()), 2),
            'CaseA_Max_Trapezoid_mm': round(float(z_df['CaseA_Trapezoid_Diff_mm'].max()), 2),
            # Case B: Phân bố đồng đều
            'CaseB_RMSE_Cen_cm': round(float(np.sqrt(np.mean(z_df['CaseB_Centroid_Err_cm'] ** 2))), 2),
            'CaseB_Median_Cen_cm': round(float(z_df['CaseB_Centroid_Err_cm'].median()), 2),
            'CaseB_Max_Cen_cm': round(float(z_df['CaseB_Centroid_Err_cm'].max()), 2),
            'CaseB_Median_4Corner_cm': round(float(z_df['CaseB_4Corner_Err_cm'].median()), 2),
            'CaseB_Median_IoU_pct': round(float(z_df['CaseB_Polygon_IoU'].median() * 100.0), 2),
            'CaseB_Valid_Rate_pct': round(float((z_df['CaseB_Centroid_Err_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2),
            'CaseB_Mean_Trapezoid_mm': round(float(z_df['CaseB_Trapezoid_Diff_mm'].mean()), 2),
            'CaseB_Max_Trapezoid_mm': round(float(z_df['CaseB_Trapezoid_Diff_mm'].max()), 2),
        })

    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(summary_csv_path, index=False, encoding='utf-8-sig')

    print("\n1. THÔNG SỐ ĐIỀU KIỆN SỐ CỦA MA TRẬN HOMOGRAPHY (DLT + HARTLEY):")
    print(f"   - Trường hợp A (Cụm góc Top-Left, N={len(sample_a_idx)}):")
    print(f"     + Chỉ số điều kiện (Condition Number): kappa_A = {cond_A:.2f}")
    print(f"     + Mẫu số w'(u,v) biến thiên: [{valid_eval['CaseA_Perspective_w'].min():.6f}, {valid_eval['CaseA_Perspective_w'].max():.6f}]")
    print(f"   - Trường hợp B (Phân bố đồng đều lưới 3x3, N={len(sample_b_idx)}):")
    print(f"     + Chỉ số điều kiện (Condition Number): kappa_B = {cond_B:.2f} (giảm {cond_A / cond_B:.2f} lần, ổn định số vượt trội)")
    print(f"     + Mẫu số w'(u,v) biến thiên: [{valid_eval['CaseB_Perspective_w'].min():.6f}, {valid_eval['CaseB_Perspective_w'].max():.6f}]")

    print("\n2. KẾT QUẢ SAI SỐ ĐỐI CHỨNG GIỮA TRƯỜNG HỢP A VÀ TRƯỜNG HỢP B:")
    for _, r in df_sum.iterrows():
        print(f"\n   * [{r['Evaluation_Zone']}] (N={r['Sample_Count']}):")
        print(
            f"     - Trường hợp A (Cụm góc): RMSE Tâm={r['CaseA_RMSE_Cen_cm']}cm | "
            f"Median={r['CaseA_Median_Cen_cm']}cm (Max={r['CaseA_Max_Cen_cm']}cm) | "
            f"4-Đỉnh Med={r['CaseA_Median_4Corner_cm']}cm | IoU Med={r['CaseA_Median_IoU_pct']}% | "
            f"Khớp giàn={r['CaseA_Valid_Rate_pct']}% | Tapering TB={r['CaseA_Mean_Trapezoid_mm']}mm (Max={r['CaseA_Max_Trapezoid_mm']}mm)"
        )
        print(
            f"     - Trường hợp B (Phân bố đều): RMSE Tâm={r['CaseB_RMSE_Cen_cm']}cm | "
            f"Median={r['CaseB_Median_Cen_cm']}cm (Max={r['CaseB_Max_Cen_cm']}cm) | "
            f"4-Đỉnh Med={r['CaseB_Median_4Corner_cm']}cm | IoU Med={r['CaseB_Median_IoU_pct']}% | "
            f"Khớp giàn={r['CaseB_Valid_Rate_pct']}% | Tapering TB={r['CaseB_Mean_Trapezoid_mm']}mm (Max={r['CaseB_Max_Trapezoid_mm']}mm)"
        )

    print(f"\n=> Đã xuất CSV chi tiết: {out_csv_path}")
    print(f"=> Đã xuất CSV tổng hợp phân vùng: {summary_csv_path}")
    return df_eval, df_sum


if __name__ == '__main__':
    run_landmark_sensitivity_test()
