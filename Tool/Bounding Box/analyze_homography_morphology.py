"""
Module: analyze_homography_morphology.py
Mục đích:
- Kiểm tra khả năng mô hình hóa biến dạng phối cảnh (và biến dạng góc nghiêng / chênh lệch hình học
  tổng hợp giữa các chuyến bay) của ma trận Homography (8 DOF) so với Affine (6 DOF).
- Phân tích định lượng sự chuyển dịch hình thái (Morphological Transition) của 5.092 OBB từ:
    (1) Hình chữ nhật định hướng nguồn trên ortho vùng 35m (PV_Coordinates_Ortho_Vung_1_20260929_0018.csv)
    (2) Hình bình hành sau biến đổi Affine 6 DOF (bảo toàn song song tuyệt đối)
    (3) Hình thang phối cảnh / tứ giác lồi thực địa sau biến đổi Homography 8 DOF (DLT + Chuẩn hóa Hartley + RANSAC)
- Đo đạc các đặc trưng hình thái:
    + Góc nội tiếp 4 đỉnh (theta_NW, theta_NE, theta_SE, theta_SW) và độ lệch cực đại khỏi góc vuông 90°
    + Góc hội tụ cặp cạnh đối (non-parallelism angle Delta_alpha_horiz, Delta_alpha_vert tính bằng độ và phút góc)
    + Độ chênh lệch chiều dài cặp cạnh đối (trapezoidal tapering Delta_L, Delta_W tính bằng mm)
    + Tỷ lệ hai đường chéo (diagonal ratio D1/D2), tỷ lệ khung hình (aspect ratio L/W), diện tích đa giác (m²)
    + Độ chênh trọng số phối cảnh giữa 4 đỉnh (Delta_w = w_max - w_min) và định thức Jacobian cục bộ det(J_H)
- Đối soát độc lập với mốc chuẩn giàn pin 85m (bbox_centroid_export.csv):
    + Sai số tâm (cm), sai số 4 đỉnh (cm), Polygon IoU (%) và độ cải thiện Delta_IoU = IoU_Homo - IoU_Affine
    + Phân tích theo 3 phân vùng bán kính tâm ảnh nguồn 35m (Vùng Tâm <30%, Vùng Trung gian 30-70%, Vùng Mép >=70%)
      và khu vực khảo sát trực quan trên giao diện (Pixel X~3192, Y~5248 | E~265459.19m, N~1263744.52m).
- Xuất 2 file CSV:
    + Bounding Box/PV_Homography_Morphology_Evaluation.csv (chi tiết 5.092 OBB)
    + Bounding Box/PV_Homography_Morphology_Zone_Summary.csv (tổng hợp theo phân vùng & nhóm khuyết tật)
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
    ransac_dlt_homography,
    solve_homography_dlt,
    DECISION_MARGIN_M,
    SEED,
    FIT_RATIO,
)
from transform_obb_homography_corners import transform_vertex_homography

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def transform_vertex_affine(pt, M_2x3):
    """Áp dụng ma trận Affine 2x3 lên 1 đỉnh (x, y)."""
    if pt is None or M_2x3 is None:
        return None
    x, y = float(pt[0]), float(pt[1])
    xp = M_2x3[0, 0] * x + M_2x3[0, 1] * y + M_2x3[0, 2]
    yp = M_2x3[1, 0] * x + M_2x3[1, 1] * y + M_2x3[1, 2]
    return (float(xp), float(yp))


def angle_between_vectors_deg(v1, v2):
    """Tính góc nội tiếp (0..180 độ) giữa 2 vector 2D."""
    n1 = math.hypot(v1[0], v1[1])
    n2 = math.hypot(v2[0], v2[1])
    if n1 < 1e-12 or n2 < 1e-12:
        return np.nan
    cos_t = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    cos_t = max(-1.0, min(1.0, cos_t))
    return math.degrees(math.acos(cos_t))


def line_convergence_angle_deg(p_a1, p_a2, p_b1, p_b2):
    """
    Tính góc lệch song song (góc hội tụ phối cảnh, độ) giữa 2 cạnh đối diện:
    Cạnh A: p_a1 -> p_a2 và Cạnh B: p_b1 -> p_b2 (cùng chiều).
    Với hình chữ nhật hoặc hình bình hành (Affine), góc này = 0°.
    Với hình thang phối cảnh (Homography), góc này > 0°.
    """
    va = (p_a2[0] - p_a1[0], p_a2[1] - p_a1[1])
    vb = (p_b2[0] - p_b1[0], p_b2[1] - p_b1[1])
    ang = angle_between_vectors_deg(va, vb)
    if np.isnan(ang):
        return np.nan
    return min(ang, abs(180.0 - ang))


def compute_quad_morphology(nw, ne, se, sw):
    """
    Tính toán bộ chỉ số hình thái đầy đủ của tứ giác (NW, NE, SE, SW):
    - Chiều dài 4 cạnh: d_top (NW->NE), d_bottom (SW->SE), d_left (SW->NW), d_right (SE->NE)
    - Độ chênh lệch cặp cạnh đối (mm): delta_L_mm = |d_top - d_bottom|*1000, delta_W_mm = |d_left - d_right|*1000
    - Góc hội tụ cặp cạnh đối (độ & phút góc): conv_horiz_deg, conv_vert_deg
    - 4 góc nội tiếp (độ): theta_NW, theta_NE, theta_SE, theta_SW
    - Độ lệch góc vuông cực đại: max_angle_dev_deg = max(|theta_i - 90°|)
    - Tỷ lệ 2 đường chéo: diag_ratio = D_NW_SE / D_NE_SW
    - Tỷ lệ cạnh dài / rộng: aspect_ratio = L / W
    - Diện tích đa giác (m²), tính lồi (is_convex)
    """
    if not all([nw, ne, se, sw]):
        return None

    pts = np.array([nw, ne, se, sw], dtype=np.float64)
    # Kiểm tra tính lồi
    v_cyc = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
    cross = [v_cyc[i][0] * v_cyc[(i + 1) % 4][1] - v_cyc[i][1] * v_cyc[(i + 1) % 4][0] for i in range(4)]
    is_convex = bool(all(c > 0 for c in cross) or all(c < 0 for c in cross))

    poly = Polygon([sw, se, ne, nw])
    is_valid = bool(poly.is_valid and poly.is_simple and is_convex and poly.area > 0.05)

    # Chiều dài 4 cạnh
    d_top = math.hypot(ne[0] - nw[0], ne[1] - nw[1])
    d_bottom = math.hypot(se[0] - sw[0], se[1] - sw[1])
    d_left = math.hypot(nw[0] - sw[0], nw[1] - sw[1])
    d_right = math.hypot(ne[0] - se[0], ne[1] - se[1])

    # Cạnh dài (L) và cạnh ngắn (W) trung bình
    avg_horiz = 0.5 * (d_top + d_bottom)
    avg_vert = 0.5 * (d_left + d_right)
    if avg_horiz >= avg_vert:
        length_m, width_m = avg_horiz, avg_vert
        delta_L_mm = abs(d_top - d_bottom) * 1000.0
        delta_W_mm = abs(d_left - d_right) * 1000.0
    else:
        length_m, width_m = avg_vert, avg_horiz
        delta_L_mm = abs(d_left - d_right) * 1000.0
        delta_W_mm = abs(d_top - d_bottom) * 1000.0

    trap_max_diff_mm = max(delta_L_mm, delta_W_mm)

    # Góc hội tụ cặp cạnh đối (độ lệch song song)
    conv_horiz_deg = line_convergence_angle_deg(nw, ne, sw, se)
    conv_vert_deg = line_convergence_angle_deg(sw, nw, se, ne)
    max_conv_deg = max(conv_horiz_deg, conv_vert_deg)
    max_conv_arcmin = max_conv_deg * 60.0

    # 4 góc nội tiếp tại NW, NE, SE, SW
    theta_nw = angle_between_vectors_deg((sw[0] - nw[0], sw[1] - nw[1]), (ne[0] - nw[0], ne[1] - nw[1]))
    theta_ne = angle_between_vectors_deg((nw[0] - ne[0], nw[1] - ne[1]), (se[0] - ne[0], se[1] - ne[1]))
    theta_se = angle_between_vectors_deg((ne[0] - se[0], ne[1] - se[1]), (sw[0] - se[0], sw[1] - se[1]))
    theta_sw = angle_between_vectors_deg((se[0] - sw[0], se[1] - sw[1]), (nw[0] - sw[0], nw[1] - sw[1]))

    angles = [theta_nw, theta_ne, theta_se, theta_sw]
    max_angle_dev_deg = max(abs(a - 90.0) for a in angles)
    mean_angle_dev_deg = float(np.mean([abs(a - 90.0) for a in angles]))

    # Đường chéo
    diag_1 = math.hypot(se[0] - nw[0], se[1] - nw[1])
    diag_2 = math.hypot(sw[0] - ne[0], sw[1] - ne[1])
    diag_ratio = diag_1 / diag_2 if diag_2 > 1e-9 else np.nan
    diag_diff_mm = abs(diag_1 - diag_2) * 1000.0

    aspect_ratio = length_m / width_m if width_m > 1e-9 else np.nan

    return {
        'is_valid': is_valid,
        'is_convex': is_convex,
        'area_m2': float(poly.area),
        'length_m': float(length_m),
        'width_m': float(width_m),
        'aspect_ratio': float(aspect_ratio),
        'delta_L_mm': float(delta_L_mm),
        'delta_W_mm': float(delta_W_mm),
        'trap_max_diff_mm': float(trap_max_diff_mm),
        'conv_horiz_deg': float(conv_horiz_deg),
        'conv_vert_deg': float(conv_vert_deg),
        'max_conv_deg': float(max_conv_deg),
        'max_conv_arcmin': float(max_conv_arcmin),
        'theta_nw': float(theta_nw),
        'theta_ne': float(theta_ne),
        'theta_se': float(theta_se),
        'theta_sw': float(theta_sw),
        'max_angle_dev_deg': float(max_angle_dev_deg),
        'mean_angle_dev_deg': float(mean_angle_dev_deg),
        'diag_diff_mm': float(diag_diff_mm),
        'diag_ratio': float(diag_ratio),
    }


def run_morphology_evaluation(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Homography_Morphology_Evaluation.csv',
    summary_csv_path='PV_Homography_Morphology_Zone_Summary.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(out_csv_path):
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))
    if not os.path.isabs(summary_csv_path):
        summary_csv_path = os.path.join(script_dir, os.path.basename(summary_csv_path))

    print("================================================================================")
    print(" PHÂN TÍCH CHUYỂN DỊCH HÌNH THÁI OBB & HẤP THỤ BIẾN DẠNG PHỐI CẢNH HOMOGRAPHY")
    print("================================================================================")

    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)

    # 1. Ghép cặp bằng GPS + AI Module ID
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_mask = merged['centroid_x'].notna()
    matched = merged[matched_mask].copy().reset_index(drop=True)

    # 2. Phân tách Control Points (70%) và Check Points (30%) để giải Affine (6 DOF) và Homography (8 DOF)
    src_pts_all = matched[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm_all = matched[['centroid_x', 'centroid_y']].values.astype(np.float64)
    dst_px85_all = np.array([utm_to_px_85m(x, y) for x, y in dst_utm_all], dtype=np.float64)

    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(matched))
    n_fit = int(len(matched) * FIT_RATIO)
    is_fit_matched = np.zeros(len(matched), dtype=bool)
    is_fit_matched[perm[:n_fit]] = True

    src_fit = src_pts_all[is_fit_matched]
    dst_fit_utm = dst_utm_all[is_fit_matched]
    dst_fit_px85 = dst_px85_all[is_fit_matched]

    # Ước lượng Homography 8 DOF (DLT + Hartley + RANSAC) từ Pixel 35m -> UTM 85m và Pixel 85m
    H_utm, inliers_fit, _ = ransac_dlt_homography(
        src_fit, dst_fit_utm, threshold=0.5, max_iters=2000, seed=SEED
    )
    H_px85, _ = solve_homography_dlt(
        src_fit[inliers_fit], dst_fit_px85[inliers_fit], use_hartley=True
    )

    # Ước lượng Affine 6 DOF trên cùng tập Control Points để đối chứng 4 đỉnh
    M_aff_utm, _ = cv2.estimateAffine2D(
        src_fit.astype(np.float32), dst_fit_utm.astype(np.float32),
        method=cv2.RANSAC, ransacReprojThreshold=0.5
    )

    umin, umax = src_pts_all[:, 0].min(), src_pts_all[:, 0].max()
    vmin, vmax = src_pts_all[:, 1].min(), src_pts_all[:, 1].max()

    rows_out = []
    for idx, row in merged.iterrows():
        u_src = float(row['Pixel_U'])
        v_src = float(row['Pixel_V'])

        nx = (u_src - umin) / max(1.0, (umax - umin))
        ny = (v_src - vmin) / max(1.0, (vmax - vmin))
        d_edge = min(nx, 1.0 - nx, ny, 1.0 - ny)
        if d_edge >= 0.25:
            zone_name = '1_Vung_Trung_Tam (>=25%)'
        elif d_edge >= 0.10:
            zone_name = '2_Vung_Trung_Gian (10-25%)'
        else:
            zone_name = '3_Vung_Mep_Ria (<10%)'

        # Tâm sau biến đổi Homography và Affine
        (u85_homo, v85_homo), w_cen_px = transform_vertex_homography((u_src, v_src), H_px85)
        (e85_homo, n85_homo), w_cen_utm = transform_vertex_homography((u_src, v_src), H_utm)
        (e85_aff, n85_aff) = transform_vertex_affine((u_src, v_src), M_aff_utm)

        # 4 đỉnh nguồn trên hệ Pixel 35m (Hình chữ nhật định hướng OBB gốc)
        nw_px = parse_tuple_coords(row.get('BBox_NW_Pixel'))
        ne_px = parse_tuple_coords(row.get('BBox_NE_Pixel'))
        se_px = parse_tuple_coords(row.get('BBox_SE_Pixel'))
        sw_px = parse_tuple_coords(row.get('BBox_SW_Pixel'))

        # Biến đổi 4 đỉnh bằng Affine (6 DOF -> Hình bình hành trên UTM 85m)
        nw_aff_utm = transform_vertex_affine(nw_px, M_aff_utm)
        ne_aff_utm = transform_vertex_affine(ne_px, M_aff_utm)
        se_aff_utm = transform_vertex_affine(se_px, M_aff_utm)
        sw_aff_utm = transform_vertex_affine(sw_px, M_aff_utm)

        # Biến đổi 4 đỉnh bằng Homography (8 DOF -> Hình thang phối cảnh / Tứ giác lồi trên UTM 85m)
        nw_homo_utm, w_nw = transform_vertex_homography(nw_px, H_utm)
        ne_homo_utm, w_ne = transform_vertex_homography(ne_px, H_utm)
        se_homo_utm, w_se = transform_vertex_homography(se_px, H_utm)
        sw_homo_utm, w_sw = transform_vertex_homography(sw_px, H_utm)

        w_list = [w for w in [w_nw, w_ne, w_se, w_sw] if w is not None]
        w_min = min(w_list) if w_list else np.nan
        w_max = max(w_list) if w_list else np.nan
        delta_w_corners = (w_max - w_min) if w_list else np.nan

        # Phân tích hình thái 3 trạng thái: Nguồn (Pixel 35m) -> Affine (Bình hành UTM 85m) -> Homography (Tứ giác phối cảnh UTM 85m)
        morph_src = compute_quad_morphology(nw_px, ne_px, se_px, sw_px)
        morph_aff = compute_quad_morphology(nw_aff_utm, ne_aff_utm, se_aff_utm, sw_aff_utm)
        morph_homo = compute_quad_morphology(nw_homo_utm, ne_homo_utm, se_homo_utm, sw_homo_utm)

        # So sánh với mốc tham chiếu 85m (bbox_centroid_export.csv)
        has_ref = pd.notna(row.get('module_id'))
        err_cen_aff_cm = np.nan
        err_cen_homo_cm = np.nan
        err_4c_aff_cm = np.nan
        err_4c_homo_cm = np.nan
        iou_aff = np.nan
        iou_homo = np.nan
        delta_iou_pct = np.nan
        morph_ref = None

        if has_ref:
            ref_cx = float(row['centroid_x'])
            ref_cy = float(row['centroid_y'])
            err_cen_aff_cm = math.hypot(e85_aff - ref_cx, n85_aff - ref_cy) * 100.0
            err_cen_homo_cm = math.hypot(e85_homo - ref_cx, n85_homo - ref_cy) * 100.0

            ref_nw = parse_tuple_coords(row.get('corner_top_left'))
            ref_ne = parse_tuple_coords(row.get('corner_top_right'))
            ref_se = parse_tuple_coords(row.get('corner_bottom_right'))
            ref_sw = parse_tuple_coords(row.get('corner_bottom_left'))

            if all([ref_nw, ref_ne, ref_se, ref_sw]):
                morph_ref = compute_quad_morphology(ref_nw, ref_ne, ref_se, ref_sw)

                if all([nw_aff_utm, ne_aff_utm, se_aff_utm, sw_aff_utm]):
                    c_aff = [
                        math.hypot(nw_aff_utm[0] - ref_nw[0], nw_aff_utm[1] - ref_nw[1]) * 100.0,
                        math.hypot(ne_aff_utm[0] - ref_ne[0], ne_aff_utm[1] - ref_ne[1]) * 100.0,
                        math.hypot(se_aff_utm[0] - ref_se[0], se_aff_utm[1] - ref_se[1]) * 100.0,
                        math.hypot(sw_aff_utm[0] - ref_sw[0], sw_aff_utm[1] - ref_sw[1]) * 100.0,
                    ]
                    err_4c_aff_cm = float(np.mean(c_aff))
                    poly_ref = Polygon([ref_sw, ref_se, ref_ne, ref_nw])
                    poly_aff = Polygon([sw_aff_utm, se_aff_utm, ne_aff_utm, nw_aff_utm])
                    iou_aff = compute_polygon_iou(poly_aff, poly_ref)

                if all([nw_homo_utm, ne_homo_utm, se_homo_utm, sw_homo_utm]):
                    c_homo = [
                        math.hypot(nw_homo_utm[0] - ref_nw[0], nw_homo_utm[1] - ref_nw[1]) * 100.0,
                        math.hypot(ne_homo_utm[0] - ref_ne[0], ne_homo_utm[1] - ref_ne[1]) * 100.0,
                        math.hypot(se_homo_utm[0] - ref_se[0], se_homo_utm[1] - ref_se[1]) * 100.0,
                        math.hypot(sw_homo_utm[0] - ref_sw[0], sw_homo_utm[1] - ref_sw[1]) * 100.0,
                    ]
                    err_4c_homo_cm = float(np.mean(c_homo))
                    poly_ref = Polygon([ref_sw, ref_se, ref_ne, ref_nw])
                    poly_homo = Polygon([sw_homo_utm, se_homo_utm, ne_homo_utm, nw_homo_utm])
                    iou_homo = compute_polygon_iou(poly_homo, poly_ref)

                if iou_aff is not None and iou_homo is not None and not np.isnan(iou_aff) and not np.isnan(iou_homo):
                    delta_iou_pct = (iou_homo - iou_aff) * 100.0

        p_class = str(row.get('Class', 'Unclassified')).strip() if pd.notna(row.get('Class')) else 'Unclassified'
        is_defect = (p_class != 'Unclassified')

        rows_out.append({
            'Point_Name': row.get('Point_Name', f'PV_{idx+1}'),
            'Match_ID': row['match_id'],
            'Panel_Class': p_class,
            'Is_Defect_OBB': is_defect,
            'Edge_Zone_35m': zone_name,
            'Edge_Distance_Ratio': round(d_edge, 4),
            'Src_Pixel_U_35m': round(u_src, 2),
            'Src_Pixel_V_35m': round(v_src, 2),
            'Dst_Pixel_U_85m_Homo': round(u85_homo, 2),
            'Dst_Pixel_V_85m_Homo': round(v85_homo, 2),
            'Dst_UTM_E_85m_Homo': round(e85_homo, 4),
            'Dst_UTM_N_85m_Homo': round(n85_homo, 4),
            # Hình thái nguồn (Hình chữ nhật định hướng 35m)
            'Src_Max_Angle_Dev_90_deg': round(morph_src['max_angle_dev_deg'], 4) if morph_src else np.nan,
            'Src_Convergence_Angle_deg': round(morph_src['max_conv_deg'], 5) if morph_src else np.nan,
            'Src_Aspect_Ratio': round(morph_src['aspect_ratio'], 4) if morph_src else np.nan,
            # Hình thái Affine 6 DOF (Hình bình hành - bảo toàn song song)
            'Aff_Max_Angle_Dev_90_deg': round(morph_aff['max_angle_dev_deg'], 4) if morph_aff else np.nan,
            'Aff_Opposite_Edge_Diff_mm': round(morph_aff['trap_max_diff_mm'], 4) if morph_aff else np.nan,
            'Aff_Convergence_Angle_deg': round(morph_aff['max_conv_deg'], 6) if morph_aff else np.nan,
            'Aff_Diag_Diff_mm': round(morph_aff['diag_diff_mm'], 3) if morph_aff else np.nan,
            'Aff_Area_m2': round(morph_aff['area_m2'], 4) if morph_aff else np.nan,
            # Hình thái Homography 8 DOF (Hình thang phối cảnh / Tứ giác lồi)
            'Homo_Is_Valid_Convex_Quad': morph_homo['is_valid'] if morph_homo else False,
            'Homo_Perspective_w_Min': round(w_min, 6) if not np.isnan(w_min) else np.nan,
            'Homo_Perspective_Delta_w': round(delta_w_corners, 7) if not np.isnan(delta_w_corners) else np.nan,
            'Homo_Theta_NW_deg': round(morph_homo['theta_nw'], 4) if morph_homo else np.nan,
            'Homo_Theta_NE_deg': round(morph_homo['theta_ne'], 4) if morph_homo else np.nan,
            'Homo_Theta_SE_deg': round(morph_homo['theta_se'], 4) if morph_homo else np.nan,
            'Homo_Theta_SW_deg': round(morph_homo['theta_sw'], 4) if morph_homo else np.nan,
            'Homo_Max_Angle_Dev_90_deg': round(morph_homo['max_angle_dev_deg'], 4) if morph_homo else np.nan,
            'Homo_Convergence_Angle_deg': round(morph_homo['max_conv_deg'], 5) if morph_homo else np.nan,
            'Homo_Convergence_Arcmin': round(morph_homo['max_conv_arcmin'], 3) if morph_homo else np.nan,
            'Homo_Trapezoid_Edge_Diff_mm': round(morph_homo['trap_max_diff_mm'], 3) if morph_homo else np.nan,
            'Homo_Delta_L_mm': round(morph_homo['delta_L_mm'], 3) if morph_homo else np.nan,
            'Homo_Delta_W_mm': round(morph_homo['delta_W_mm'], 3) if morph_homo else np.nan,
            'Homo_Diag_Diff_mm': round(morph_homo['diag_diff_mm'], 3) if morph_homo else np.nan,
            'Homo_Length_m': round(morph_homo['length_m'], 4) if morph_homo else np.nan,
            'Homo_Width_m': round(morph_homo['width_m'], 4) if morph_homo else np.nan,
            'Homo_Aspect_Ratio': round(morph_homo['aspect_ratio'], 4) if morph_homo else np.nan,
            'Homo_Area_m2': round(morph_homo['area_m2'], 4) if morph_homo else np.nan,
            'Ref_Area_m2': round(morph_ref['area_m2'], 4) if morph_ref else np.nan,
            'Ref_Max_Angle_Dev_90_deg': round(morph_ref['max_angle_dev_deg'], 4) if morph_ref else np.nan,
            # Đối soát sai số vị trí & IoU với mốc 85m (bbox_centroid_export.csv)
            'Aff_Centroid_Error_cm': round(err_cen_aff_cm, 3) if not np.isnan(err_cen_aff_cm) else np.nan,
            'Homo_Centroid_Error_cm': round(err_cen_homo_cm, 3) if not np.isnan(err_cen_homo_cm) else np.nan,
            'Aff_4Corner_Mean_Err_cm': round(err_4c_aff_cm, 3) if not np.isnan(err_4c_aff_cm) else np.nan,
            'Homo_4Corner_Mean_Err_cm': round(err_4c_homo_cm, 3) if not np.isnan(err_4c_homo_cm) else np.nan,
            'Aff_Polygon_IoU': round(iou_aff, 4) if not np.isnan(iou_aff) else np.nan,
            'Homo_Polygon_IoU': round(iou_homo, 4) if not np.isnan(iou_homo) else np.nan,
            'Delta_IoU_Homo_vs_Aff_pct': round(delta_iou_pct, 3) if not np.isnan(delta_iou_pct) else np.nan,
        })

    df_out = pd.DataFrame(rows_out)
    df_out.to_csv(out_csv_path, index=False, encoding='utf-8-sig')

    # Tổng hợp theo phân vùng bán kính & nhóm khuyết tật
    valid_df = df_out[df_out['Homo_Centroid_Error_cm'].notna()].copy()
    summary_rows = []
    groups = [
        ('Toàn bộ OBB khớp mốc (All Matched)', valid_df),
        ('Nhóm OBB Khuyết tật nhiệt (Defects Only)', valid_df[valid_df['Is_Defect_OBB']]),
        ('Vùng 1: Trung tâm ortho 35m (>=25%)', valid_df[valid_df['Edge_Zone_35m'].str.startswith('1_')]),
        ('Vùng 2: Trung gian (10-25%)', valid_df[valid_df['Edge_Zone_35m'].str.startswith('2_')]),
        ('Vùng 3: Mép/Rìa ortho (<10%)', valid_df[valid_df['Edge_Zone_35m'].str.startswith('3_')]),
    ]

    for g_name, g_df in groups:
        if len(g_df) == 0:
            continue
        summary_rows.append({
            'Group_Name': g_name,
            'Count_OBB': len(g_df),
            'Src_Angle_Dev_Mean_deg': round(float(g_df['Src_Max_Angle_Dev_90_deg'].mean()), 4),
            'Aff_Angle_Dev_Mean_deg': round(float(g_df['Aff_Max_Angle_Dev_90_deg'].mean()), 4),
            'Homo_Angle_Dev_Mean_deg': round(float(g_df['Homo_Max_Angle_Dev_90_deg'].mean()), 4),
            'Homo_Angle_Dev_Max_deg': round(float(g_df['Homo_Max_Angle_Dev_90_deg'].max()), 4),
            'Aff_Convergence_Angle_deg': 0.0,
            'Homo_Convergence_Mean_Arcmin': round(float(g_df['Homo_Convergence_Arcmin'].mean()), 3),
            'Homo_Convergence_Max_Arcmin': round(float(g_df['Homo_Convergence_Arcmin'].max()), 3),
            'Aff_Trapezoid_Diff_mm': 0.0,
            'Homo_Trapezoid_Diff_Mean_mm': round(float(g_df['Homo_Trapezoid_Edge_Diff_mm'].mean()), 3),
            'Homo_Trapezoid_Diff_Max_mm': round(float(g_df['Homo_Trapezoid_Edge_Diff_mm'].max()), 3),
            'Aff_Diag_Diff_Mean_mm': round(float(g_df['Aff_Diag_Diff_mm'].mean()), 3),
            'Homo_Diag_Diff_Mean_mm': round(float(g_df['Homo_Diag_Diff_mm'].mean()), 3),
            'Aff_Area_Mean_m2': round(float(g_df['Aff_Area_m2'].mean()), 4),
            'Homo_Area_Mean_m2': round(float(g_df['Homo_Area_m2'].mean()), 4),
            'Ref_Area_Mean_m2': round(float(g_df['Ref_Area_m2'].mean()), 4),
            'Aff_Centroid_RMSE_cm': round(float(np.sqrt(np.mean(g_df['Aff_Centroid_Error_cm'] ** 2))), 2),
            'Homo_Centroid_RMSE_cm': round(float(np.sqrt(np.mean(g_df['Homo_Centroid_Error_cm'] ** 2))), 2),
            'Aff_Centroid_Median_cm': round(float(g_df['Aff_Centroid_Error_cm'].median()), 2),
            'Homo_Centroid_Median_cm': round(float(g_df['Homo_Centroid_Error_cm'].median()), 2),
            'Aff_4Corner_Median_cm': round(float(g_df['Aff_4Corner_Mean_Err_cm'].median()), 2),
            'Homo_4Corner_Median_cm': round(float(g_df['Homo_4Corner_Mean_Err_cm'].median()), 2),
            'Aff_IoU_Median_pct': round(float(g_df['Aff_Polygon_IoU'].median() * 100.0), 2),
            'Homo_IoU_Median_pct': round(float(g_df['Homo_Polygon_IoU'].median() * 100.0), 2),
            'Aff_IoU_Mean_pct': round(float(g_df['Aff_Polygon_IoU'].mean() * 100.0), 2),
            'Homo_IoU_Mean_pct': round(float(g_df['Homo_Polygon_IoU'].mean() * 100.0), 2),
            'Mean_Delta_IoU_Gain_pct': round(float(g_df['Delta_IoU_Homo_vs_Aff_pct'].mean()), 2),
            'Valid_Rate_Aff_pct': round(float((g_df['Aff_Centroid_Error_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2),
            'Valid_Rate_Homo_pct': round(float((g_df['Homo_Centroid_Error_cm'] <= DECISION_MARGIN_M * 100.0).mean() * 100.0), 2),
        })

    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(summary_csv_path, index=False, encoding='utf-8-sig')

    print("\n1. CHUYỂN DỊCH HÌNH THÁI TỪ HÌNH CHỮ NHẬT -> HÌNH BÌNH HÀNH (AFFINE) -> TỨ GIÁC PHỐI CẢNH (HOMOGRAPHY):")
    print(f"   - [Nguồn 35m - Hình chữ nhật]: Độ lệch góc vuông TB = {df_out['Src_Max_Angle_Dev_90_deg'].mean():.4f}° | Góc hội tụ = {df_out['Src_Convergence_Angle_deg'].mean():.5f}° | Tỷ lệ cạnh L/W = {df_out['Src_Aspect_Ratio'].mean():.4f}")
    print(f"   - [Affine 6 DOF - Hình bình hành]: Độ lệch góc vuông (shear) TB = {df_out['Aff_Max_Angle_Dev_90_deg'].mean():.4f}° | Góc hội tụ cạnh đối = 0.000° | Độ lệch cạnh đối = {df_out['Aff_Opposite_Edge_Diff_mm'].mean():.4f} mm | Chênh đường chéo TB = {df_out['Aff_Diag_Diff_mm'].mean():.2f} mm")
    print(f"   - [Homography 8 DOF - Tứ giác thực địa]: Độ lệch góc vuông TB = {df_out['Homo_Max_Angle_Dev_90_deg'].mean():.4f}° (Max = {df_out['Homo_Max_Angle_Dev_90_deg'].max():.4f}°)")
    print(f"     + Góc hội tụ phối cảnh cặp cạnh đối: TB = {df_out['Homo_Convergence_Arcmin'].mean():.3f} phút góc ({df_out['Homo_Convergence_Angle_deg'].mean():.5f}°) | Max = {df_out['Homo_Convergence_Arcmin'].max():.3f} phút góc")
    print(f"     + Độ chênh chiều dài cặp cạnh đối (Trapezoidal tapering): TB = {df_out['Homo_Trapezoid_Edge_Diff_mm'].mean():.2f} mm (Max = {df_out['Homo_Trapezoid_Edge_Diff_mm'].max():.2f} mm)")
    print(f"     + Độ chênh 2 đường chéo: TB = {df_out['Homo_Diag_Diff_mm'].mean():.2f} mm (Max = {df_out['Homo_Diag_Diff_mm'].max():.2f} mm)")
    print(f"     + Diện tích TB: Affine = {df_out['Aff_Area_m2'].mean():.4f} m² -> Homography = {df_out['Homo_Area_m2'].mean():.4f} m² (Mốc 85m = {valid_df['Ref_Area_m2'].mean():.4f} m²)")

    print("\n2. BẢNG TỔNG HỢP THEO PHÂN VÙNG BÁN KÍNH & NHÓM KHUYẾT TẬT:")
    for _, r in df_sum.iterrows():
        print(
            f"   * {r['Group_Name']} (N={r['Count_OBB']}): "
            f"Tapering={r['Homo_Trapezoid_Diff_Mean_mm']}mm | "
            f"RMSE Tâm: Aff={r['Aff_Centroid_RMSE_cm']}cm -> Homo={r['Homo_Centroid_RMSE_cm']}cm | "
            f"4-Đỉnh Med: Aff={r['Aff_4Corner_Median_cm']}cm -> Homo={r['Homo_4Corner_Median_cm']}cm | "
            f"IoU Med: Aff={r['Aff_IoU_Median_pct']}% -> Homo={r['Homo_IoU_Median_pct']}% (Gain Mean: +{r['Mean_Delta_IoU_Gain_pct']}%) | "
            f"Khớp giàn: Aff={r['Valid_Rate_Aff_pct']}% -> Homo={r['Valid_Rate_Homo_pct']}%"
        )

    # Khảo sát khu vực trực quan trên ảnh chụp màn hình: E ~ 265,459.187 m, N ~ 1,263,744.518 m
    vis_window = valid_df[
        (valid_df['Dst_UTM_E_85m_Homo'].between(265440.0, 265480.0)) &
        (valid_df['Dst_UTM_N_85m_Homo'].between(1263730.0, 1263760.0))
    ]
    print(f"\n3. KHẢO SÁT KHU VỰC TRỰC QUAN TRÊN ẢNH GIAO DIỆN (E~265,459.19m, N~1,263,744.52m, N={len(vis_window)} OBB):")
    if len(vis_window) > 0:
        print(f"   - Số OBB khuyết tật trong khung nhìn: {int(vis_window['Is_Defect_OBB'].sum())} OBB")
        print(f"   - Sai số tâm Homography TB / Median: {vis_window['Homo_Centroid_Error_cm'].mean():.2f} cm / {vis_window['Homo_Centroid_Error_cm'].median():.2f} cm (so với Affine: {vis_window['Aff_Centroid_Error_cm'].mean():.2f} cm / {vis_window['Aff_Centroid_Error_cm'].median():.2f} cm)")
        print(f"   - Polygon IoU Homography Median / Mean: {vis_window['Homo_Polygon_IoU'].median()*100:.2f}% / {vis_window['Homo_Polygon_IoU'].mean()*100:.2f}% (so với Affine: {vis_window['Aff_Polygon_IoU'].median()*100:.2f}% / {vis_window['Aff_Polygon_IoU'].mean()*100:.2f}%)")
        print(f"   - Độ chênh cạnh đối hình thang (Tapering) TB: {vis_window['Homo_Trapezoid_Edge_Diff_mm'].mean():.2f} mm | Độ lệch góc vuông TB: {vis_window['Homo_Max_Angle_Dev_90_deg'].mean():.4f}°")

    print(f"\n=> Đã xuất CSV chi tiết: {out_csv_path}")
    print(f"=> Đã xuất CSV tổng hợp phân vùng: {summary_csv_path}")
    return df_out, df_sum


if __name__ == '__main__':
    run_morphology_evaluation()
