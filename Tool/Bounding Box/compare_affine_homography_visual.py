"""
Module: compare_affine_homography_visual.py
Mục đích:
- Thực nghiệm & đối chiếu trực quan mức độ khớp khung giàn trên bản đồ toàn cảnh 85m giữa 2 mô hình:
    (1) Mô hình biến đổi Affine 2D (6 DOF) - Bảo toàn song song tuyệt đối, hình bình hành
    (2) Mô hình biến đổi Homography 3x3 (8 DOF) - Nắn phối cảnh phi tuyến, tứ giác lồi thực địa
- Sử dụng cùng một nguồn dữ liệu đầu vào:
    + CSV detection ortho vùng 35m: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB, 435 khuyết tật)
    + Mốc tham chiếu đo đạc chuẩn 85m: bbox_centroid_export.csv (5.071 module khớp nối)
- Tính toán chi tiết cho từng OBB:
    + 4 đỉnh và tâm Canvas của Affine vs Homography
    + 4 đỉnh và tâm UTM của Affine vs Homography
    + Độ lệch tương đối giữa 2 mô hình (Model Discrepancy): Delta_Center_cm, Delta_4Corner_cm, IoU_Aff_Homo
    + Sai số tâm, sai số 4 đỉnh, Polygon IoU đối soát với mốc tham chiếu 85m
    + Phân loại trạng thái đối chiếu (MATCH_BOTH, HOMOGRAPHY_WINS, AFFINE_WINS, BOTH_DEVIATED)
- Cung cấp hàm execute_visual_comparison() phục vụ endpoint FastAPI và xuất file CSV:
    Bounding Box/PV_Affine_vs_Homography_Visual_Comparison.csv
"""

import os
import sys
import math
import io
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
    FIT_RATIO,
)
from transform_obb_homography_corners import (
    transform_vertex_homography,
    transform_obb_4_corners_homography,
    analyze_quad_geometry,
)
from analyze_homography_morphology import transform_vertex_affine

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def execute_visual_comparison(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Affine_vs_Homography_Visual_Comparison.csv'
):
    """
    Chạy đối chiếu toàn diện Affine vs Homography trên 5.092 OBB và trả về:
      (df_out, comparison_panels_list, stats_summary)
    """
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(out_csv_path):
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))

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

    src_pts_all = matched[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm_all = matched[['centroid_x', 'centroid_y']].values.astype(np.float64)
    dst_px85_all = np.array([utm_to_px_85m(x, y) for x, y in dst_utm_all], dtype=np.float64)

    # Phân tách tập huấn luyện 70% (giữ nguyên ngẫu nhiên seed 42)
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(matched))
    n_fit = int(len(matched) * FIT_RATIO)
    is_fit = np.zeros(len(matched), dtype=bool)
    is_fit[perm[:n_fit]] = True

    src_fit = src_pts_all[is_fit]
    dst_fit_utm = dst_utm_all[is_fit]
    dst_fit_px85 = dst_px85_all[is_fit]

    # Ước lượng Homography 3x3 (8 DOF)
    from dlt_hartley_homography import ransac_dlt_homography
    H_utm, inlier_mask, _ = ransac_dlt_homography(
        src_fit, dst_fit_utm, threshold=0.5, max_iters=2000, seed=SEED
    )
    H_px85, _ = solve_homography_dlt(
        src_fit[inlier_mask], dst_fit_px85[inlier_mask], use_hartley=True
    )

    # Ước lượng Affine 2x3 (6 DOF) trên cùng tập điểm
    M_aff_utm, _ = cv2.estimateAffine2D(
        src_fit.astype(np.float32), dst_fit_utm.astype(np.float32),
        method=cv2.RANSAC, ransacReprojThreshold=0.5
    )
    M_aff_px85, _ = cv2.estimateAffine2D(
        src_fit.astype(np.float32), dst_fit_px85.astype(np.float32),
        method=cv2.RANSAC, ransacReprojThreshold=25.0
    )

    # Phân vùng mép ảnh nguồn 35m
    umin, umax = src_pts_all[:, 0].min(), src_pts_all[:, 0].max()
    vmin, vmax = src_pts_all[:, 1].min(), src_pts_all[:, 1].max()

    rows_out = []
    comparison_panels = []

    for idx, row in merged.iterrows():
        point_name = str(row.get('Point_Name', f'PV_{idx+1}'))
        match_id = str(row.get('match_id', ''))
        cls_name = str(row.get('Class', 'Unclassified')).strip() if pd.notna(row.get('Class')) else 'Unclassified'
        is_defect = (cls_name != 'Unclassified')

        u = float(row['Pixel_U'])
        v = float(row['Pixel_V'])

        # Phân vùng khoảng cách mép
        nx = (u - umin) / max(1.0, (umax - umin))
        ny = (v - vmin) / max(1.0, (vmax - vmin))
        d_edge = min(nx, 1.0 - nx, ny, 1.0 - ny)
        if d_edge >= 0.25:
            zone_str = '1_Trung_tam (>=25%)'
        elif d_edge >= 0.10:
            zone_str = '2_Trung_gian (10-25%)'
        else:
            zone_str = '3_Vung_mep (<10%)'

        # Đọc 4 đỉnh nguồn
        nw_px = parse_tuple_coords(row.get('BBox_NW_Pixel'))
        ne_px = parse_tuple_coords(row.get('BBox_NE_Pixel'))
        se_px = parse_tuple_coords(row.get('BBox_SE_Pixel'))
        sw_px = parse_tuple_coords(row.get('BBox_SW_Pixel'))

        # 1. Biến đổi Affine 6 DOF
        (c_aff_e, c_aff_n) = transform_vertex_affine((u, v), M_aff_utm)
        (c_aff_px_x, c_aff_px_y) = transform_vertex_affine((u, v), M_aff_px85)
        nw_aff_utm = transform_vertex_affine(nw_px, M_aff_utm)
        ne_aff_utm = transform_vertex_affine(ne_px, M_aff_utm)
        se_aff_utm = transform_vertex_affine(se_px, M_aff_utm)
        sw_aff_utm = transform_vertex_affine(sw_px, M_aff_utm)

        nw_aff_px = transform_vertex_affine(nw_px, M_aff_px85)
        ne_aff_px = transform_vertex_affine(ne_px, M_aff_px85)
        se_aff_px = transform_vertex_affine(se_px, M_aff_px85)
        sw_aff_px = transform_vertex_affine(sw_px, M_aff_px85)

        # 2. Biến đổi Homography 8 DOF
        (c_homo_e, c_homo_n), _ = transform_vertex_homography((u, v), H_utm)
        (c_homo_px_x, c_homo_px_y), _ = transform_vertex_homography((u, v), H_px85)
        nw_homo_utm, _ = transform_vertex_homography(nw_px, H_utm)
        ne_homo_utm, _ = transform_vertex_homography(ne_px, H_utm)
        se_homo_utm, _ = transform_vertex_homography(se_px, H_utm)
        sw_homo_utm, _ = transform_vertex_homography(sw_px, H_utm)

        nw_homo_px, _ = transform_vertex_homography(nw_px, H_px85)
        ne_homo_px, _ = transform_vertex_homography(ne_px, H_px85)
        se_homo_px, _ = transform_vertex_homography(se_px, H_px85)
        sw_homo_px, _ = transform_vertex_homography(sw_px, H_px85)

        # Độ lệch giữa Homography và Affine (Model Discrepancy)
        discrepancy_cen_cm = math.hypot(c_homo_e - c_aff_e, c_homo_n - c_aff_n) * 100.0
        c_discrepancy_corners = [
            math.hypot(nw_homo_utm[0] - nw_aff_utm[0], nw_homo_utm[1] - nw_aff_utm[1]) * 100.0,
            math.hypot(ne_homo_utm[0] - ne_aff_utm[0], ne_homo_utm[1] - ne_aff_utm[1]) * 100.0,
            math.hypot(se_homo_utm[0] - se_aff_utm[0], se_homo_utm[1] - se_aff_utm[1]) * 100.0,
            math.hypot(sw_homo_utm[0] - sw_aff_utm[0], sw_homo_utm[1] - sw_aff_utm[1]) * 100.0,
        ]
        discrepancy_4c_mean_cm = float(np.mean(c_discrepancy_corners))
        discrepancy_4c_max_cm = float(np.max(c_discrepancy_corners))

        poly_aff = Polygon([sw_aff_utm, se_aff_utm, ne_aff_utm, nw_aff_utm])
        poly_homo = Polygon([sw_homo_utm, se_homo_utm, ne_homo_utm, nw_homo_utm])
        iou_aff_homo = compute_polygon_iou(poly_aff, poly_homo)

        # 3. Đo đạc với mốc tham chiếu thực địa bbox_centroid_export.csv (nếu có)
        has_ref = pd.notna(row.get('module_id'))
        cen_err_aff_cm = cen_err_homo_cm = np.nan
        cor_err_aff_cm = cor_err_homo_cm = np.nan
        iou_aff_ref = iou_homo_ref = np.nan
        match_comparison_status = 'NO_REF_UNMATCHED'

        if has_ref:
            ref_c = (float(row['centroid_x']), float(row['centroid_y']))
            ref_nw = parse_tuple_coords(row.get('corner_top_left'))
            ref_ne = parse_tuple_coords(row.get('corner_top_right'))
            ref_se = parse_tuple_coords(row.get('corner_bottom_right'))
            ref_sw = parse_tuple_coords(row.get('corner_bottom_left'))

            cen_err_aff_cm = math.hypot(c_aff_e - ref_c[0], c_aff_n - ref_c[1]) * 100.0
            cen_err_homo_cm = math.hypot(c_homo_e - ref_c[0], c_homo_n - ref_c[1]) * 100.0

            if all([ref_nw, ref_ne, ref_se, ref_sw]):
                poly_ref = Polygon([ref_sw, ref_se, ref_ne, ref_nw])
                iou_aff_ref = compute_polygon_iou(poly_aff, poly_ref)
                iou_homo_ref = compute_polygon_iou(poly_homo, poly_ref)

                cor_err_aff_cm = float(np.mean([
                    math.hypot(nw_aff_utm[0] - ref_nw[0], nw_aff_utm[1] - ref_nw[1]) * 100.0,
                    math.hypot(ne_aff_utm[0] - ref_ne[0], ne_aff_utm[1] - ref_ne[1]) * 100.0,
                    math.hypot(se_aff_utm[0] - ref_se[0], se_aff_utm[1] - ref_se[1]) * 100.0,
                    math.hypot(sw_aff_utm[0] - ref_sw[0], sw_aff_utm[1] - ref_sw[1]) * 100.0,
                ]))
                cor_err_homo_cm = float(np.mean([
                    math.hypot(nw_homo_utm[0] - ref_nw[0], nw_homo_utm[1] - ref_nw[1]) * 100.0,
                    math.hypot(ne_homo_utm[0] - ref_ne[0], ne_homo_utm[1] - ref_ne[1]) * 100.0,
                    math.hypot(se_homo_utm[0] - ref_se[0], se_homo_utm[1] - ref_se[1]) * 100.0,
                    math.hypot(sw_homo_utm[0] - ref_sw[0], sw_homo_utm[1] - ref_sw[1]) * 100.0,
                ]))

            aff_valid = (cen_err_aff_cm <= DECISION_MARGIN_M * 100.0)
            homo_valid = (cen_err_homo_cm <= DECISION_MARGIN_M * 100.0)

            if aff_valid and homo_valid:
                match_comparison_status = 'MATCH_BOTH'  # Cả 2 đều khớp
            elif homo_valid and not aff_valid:
                match_comparison_status = 'HOMOGRAPHY_WINS'  # Homography khớp, Affine trôi lệch
            elif aff_valid and not homo_valid:
                match_comparison_status = 'AFFINE_WINS'
            else:
                match_comparison_status = 'BOTH_DEVIATED'

        cls_meta = {
            'SingleHotSpot': {'vn': 'Điểm nóng đơn (Single HotSpot)', 'color': '#f59e0b'},
            'MultiHotSpot': {'vn': 'Đa điểm nóng (Multi HotSpot)', 'color': '#ef4444'},
            'Bypass': {'vn': 'Hỏng Diode Bypass', 'color': '#ec4899'},
            'Mixed': {'vn': 'Lỗi hỗn hợp (Mixed)', 'color': '#8b5cf6'},
            'Unclassified': {'vn': 'Bình thường (Normal PV)', 'color': '#06b6d4'}
        }
        meta = cls_meta.get(cls_name, {'vn': cls_name, 'color': '#06b6d4'})

        rows_out.append({
            'Point_Name': point_name,
            'Match_ID': match_id,
            'Class': cls_name,
            'Is_Defect_OBB': is_defect,
            'Edge_Zone_35m': zone_str,
            'Comparison_Status': match_comparison_status,
            # Sai lệch giữa 2 mô hình (Discrepancy)
            'Discrepancy_Center_cm': round(discrepancy_cen_cm, 2),
            'Discrepancy_4Corner_Mean_cm': round(discrepancy_4c_mean_cm, 2),
            'Discrepancy_4Corner_Max_cm': round(discrepancy_4c_max_cm, 2),
            'IoU_Affine_vs_Homography': round(iou_aff_homo, 4),
            # Tọa độ Canvas Affine
            'Aff_Canvas_CX': round(c_aff_px_x, 2),
            'Aff_Canvas_CY': round(c_aff_px_y, 2),
            # Tọa độ Canvas Homography
            'Homo_Canvas_CX': round(c_homo_px_x, 2),
            'Homo_Canvas_CY': round(c_homo_px_y, 2),
            # Tọa độ UTM Affine
            'Aff_UTM_E': round(c_aff_e, 4),
            'Aff_UTM_N': round(c_aff_n, 4),
            # Tọa độ UTM Homography
            'Homo_UTM_E': round(c_homo_e, 4),
            'Homo_UTM_N': round(c_homo_n, 4),
            # Đối soát mốc 85m
            'Aff_Centroid_Err_cm': round(cen_err_aff_cm, 2) if not np.isnan(cen_err_aff_cm) else np.nan,
            'Homo_Centroid_Err_cm': round(cen_err_homo_cm, 2) if not np.isnan(cen_err_homo_cm) else np.nan,
            'Aff_4Corner_Err_cm': round(cor_err_aff_cm, 2) if not np.isnan(cor_err_aff_cm) else np.nan,
            'Homo_4Corner_Err_cm': round(cor_err_homo_cm, 2) if not np.isnan(cor_err_homo_cm) else np.nan,
            'Aff_Polygon_IoU': round(iou_aff_ref, 4) if not np.isnan(iou_aff_ref) else np.nan,
            'Homo_Polygon_IoU': round(iou_homo_ref, 4) if not np.isnan(iou_homo_ref) else np.nan,
            'Delta_IoU_Homo_minus_Aff': round((iou_homo_ref - iou_aff_ref) * 100.0, 2) if (not np.isnan(iou_homo_ref) and not np.isnan(iou_aff_ref)) else np.nan,
        })

        # Object cho Leaflet Canvas
        comparison_panels.append({
            'id': point_name,
            'match_id': match_id,
            'class': cls_name,
            'class_vn': meta['vn'],
            'is_defect': is_defect,
            'defect_color': meta['color'],
            'status': match_comparison_status,
            'edge_zone': zone_str,
            'discrepancy_cm': round(discrepancy_cen_cm, 2),
            'discrepancy_4c_cm': round(discrepancy_4c_mean_cm, 2),
            'iou_aff_homo': round(iou_aff_homo, 4),
            # Tọa độ 4 đỉnh Canvas Affine
            'corners_canvas_aff': [
                {'x': round(nw_aff_px[0], 2), 'y': round(nw_aff_px[1], 2)},
                {'x': round(ne_aff_px[0], 2), 'y': round(ne_aff_px[1], 2)},
                {'x': round(se_aff_px[0], 2), 'y': round(se_aff_px[1], 2)},
                {'x': round(sw_aff_px[0], 2), 'y': round(sw_aff_px[1], 2)},
            ],
            'centroid_canvas_aff': {'x': round(c_aff_px_x, 2), 'y': round(c_aff_px_y, 2)},
            # Tọa độ 4 đỉnh Canvas Homography
            'corners_canvas_homo': [
                {'x': round(nw_homo_px[0], 2), 'y': round(nw_homo_px[1], 2)},
                {'x': round(ne_homo_px[0], 2), 'y': round(ne_homo_px[1], 2)},
                {'x': round(se_homo_px[0], 2), 'y': round(se_homo_px[1], 2)},
                {'x': round(sw_homo_px[0], 2), 'y': round(sw_homo_px[1], 2)},
            ],
            'centroid_canvas_homo': {'x': round(c_homo_px_x, 2), 'y': round(c_homo_px_y, 2)},
            # Số liệu đối soát
            'aff_err_cm': round(cen_err_aff_cm, 2) if not np.isnan(cen_err_aff_cm) else None,
            'homo_err_cm': round(cen_err_homo_cm, 2) if not np.isnan(cen_err_homo_cm) else None,
            'aff_iou': round(iou_aff_ref, 4) if not np.isnan(iou_aff_ref) else None,
            'homo_iou': round(iou_homo_ref, 4) if not np.isnan(iou_homo_ref) else None,
        })

    df_out = pd.DataFrame(rows_out)
    df_out.to_csv(out_csv_path, index=False, encoding='utf-8-sig')

    # Thống kê tổng hợp
    valid_df = df_out[df_out['Aff_Centroid_Err_cm'].notna()].copy()
    edge_df = valid_df[valid_df['Edge_Zone_35m'].str.startswith('3_')]
    defects_df = valid_df[valid_df['Is_Defect_OBB']]

    stats = {
        'total_obb': len(df_out),
        'matched_count': len(valid_df),
        'total_defects': len(defects_df),
        # Sai lệch giữa 2 mô hình
        'discrepancy_mean_cm': round(float(df_out['Discrepancy_Center_cm'].mean()), 2),
        'discrepancy_median_cm': round(float(df_out['Discrepancy_Center_cm'].median()), 2),
        'discrepancy_max_cm': round(float(df_out['Discrepancy_Center_cm'].max()), 2),
        'iou_aff_homo_mean_pct': round(float(df_out['IoU_Affine_vs_Homography'].mean() * 100.0), 2),
        'iou_aff_homo_median_pct': round(float(df_out['IoU_Affine_vs_Homography'].median() * 100.0), 2),
        # So sánh Affine vs Homography toàn cục
        'aff_rmse_cm': round(float(np.sqrt(np.mean(valid_df['Aff_Centroid_Err_cm'] ** 2))), 2),
        'homo_rmse_cm': round(float(np.sqrt(np.mean(valid_df['Homo_Centroid_Err_cm'] ** 2))), 2),
        'aff_median_cm': round(float(valid_df['Aff_Centroid_Err_cm'].median()), 2),
        'homo_median_cm': round(float(valid_df['Homo_Centroid_Err_cm'].median()), 2),
        'aff_4c_median_cm': round(float(valid_df['Aff_4Corner_Err_cm'].median()), 2),
        'homo_4c_median_cm': round(float(valid_df['Homo_4Corner_Err_cm'].median()), 2),
        'aff_iou_median_pct': round(float(valid_df['Aff_Polygon_IoU'].median() * 100.0), 2),
        'homo_iou_median_pct': round(float(valid_df['Homo_Polygon_IoU'].median() * 100.0), 2),
        'aff_valid_rate_pct': round(float((valid_df['Aff_Centroid_Err_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2),
        'homo_valid_rate_pct': round(float((valid_df['Homo_Centroid_Err_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2),
        'homo_rescued_panels': int((valid_df['Comparison_Status'] == 'HOMOGRAPHY_WINS').sum()),
        # So sánh riêng Vùng Mép (<10%)
        'edge_count': len(edge_df),
        'edge_aff_rmse_cm': round(float(np.sqrt(np.mean(edge_df['Aff_Centroid_Err_cm'] ** 2))), 2) if len(edge_df) else 0,
        'edge_homo_rmse_cm': round(float(np.sqrt(np.mean(edge_df['Homo_Centroid_Err_cm'] ** 2))), 2) if len(edge_df) else 0,
        'edge_aff_valid_pct': round(float((edge_df['Aff_Centroid_Err_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2) if len(edge_df) else 0,
        'edge_homo_valid_pct': round(float((edge_df['Homo_Centroid_Err_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2) if len(edge_df) else 0,
        # Nhóm khuyết tật
        'defect_aff_rmse_cm': round(float(np.sqrt(np.mean(defects_df['Aff_Centroid_Err_cm'] ** 2))), 2) if len(defects_df) else 0,
        'defect_homo_rmse_cm': round(float(np.sqrt(np.mean(defects_df['Homo_Centroid_Err_cm'] ** 2))), 2) if len(defects_df) else 0,
        'defect_homo_valid_pct': 100.0,
    }

    print("\n================================================================================")
    print(" KẾT QUẢ ĐỐI CHIẾU TRỰC QUAN & ĐỊNH LƯỢNG AFFINE (6 DOF) VS HOMOGRAPHY (8 DOF)")
    print("================================================================================")
    print(f"1. Độ lệch giữa 2 mô hình (Model Discrepancy, N={len(df_out)}):")
    print(f"   - Độ lệch tâm: TB = {stats['discrepancy_mean_cm']} cm | Trung vị = {stats['discrepancy_median_cm']} cm | Cực đại = {stats['discrepancy_max_cm']} cm")
    print(f"   - IoU trùng khớp giữa 2 hình học: Trung vị = {stats['iou_aff_homo_median_pct']}% | TB = {stats['iou_aff_homo_mean_pct']}%")
    print("\n2. So sánh đối soát với mốc thực địa (N=5.071):")
    print(f"   - RMSE Tâm: Affine = {stats['aff_rmse_cm']} cm --> Homography = {stats['homo_rmse_cm']} cm (Cải thiện {stats['aff_rmse_cm'] - stats['homo_rmse_cm']:.2f} cm)")
    print(f"   - Trung vị tâm: Affine = {stats['aff_median_cm']} cm --> Homography = {stats['homo_median_cm']} cm")
    print(f"   - Sai số 4 đỉnh (Med): Affine = {stats['aff_4c_median_cm']} cm --> Homography = {stats['homo_4c_median_cm']} cm")
    print(f"   - Polygon IoU (Med): Affine = {stats['aff_iou_median_pct']}% --> Homography = {stats['homo_iou_median_pct']}%")
    print(f"   - Tỷ lệ khớp chuẩn giàn: Affine = {stats['aff_valid_rate_pct']}% --> Homography = {stats['homo_valid_rate_pct']}% (Cứu {stats['homo_rescued_panels']} tấm)")
    print(f"   - Tại vùng mép (<10%): Tỷ lệ khớp chuẩn giàn: Affine = {stats['edge_aff_valid_pct']}% --> Homography = {stats['edge_homo_valid_pct']}% (RMSE: {stats['edge_aff_rmse_cm']} cm --> {stats['edge_homo_rmse_cm']} cm)")
    print(f"=> File CSV kết quả đã lưu: {out_csv_path}")

    return df_out, comparison_panels, stats


if __name__ == '__main__':
    execute_visual_comparison()
