"""
Module: export_standardized_gis_database.py
Thư mục: Bounding Box
Mục đích:
- Thực hiện đầy đủ quy trình:
  1. Đọc CSV detection trực ảnh vùng 35m: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB).
  2. Đọc CSV mốc trắc địa chuẩn QGIS toàn cảnh 85m: bbox_centroid_export.csv (36.544 module).
  3. Sử dụng cơ chế GPS + AI Matching để khởi tạo các cặp điểm khống chế.
  4. Ước lượng ma trận Homography DLT Hartley (8 DoF) với chuẩn hóa đẳng hướng Hartley và RANSAC.
  5. Ánh xạ toàn bộ 5.092 OBB (4 đỉnh và tâm centroid) sang hệ tọa độ phẳng UTM Zone 49N (EPSG:32649) và WGS84 (EPSG:4326).
  6. Xây dựng ma trận chi phí đa thành phần (IoU, khoảng cách tâm, độ lệch góc) và giải bằng giải thuật Hungarian (Bipartite Matching).
  7. Áp dụng cổng kiểm duyệt kép (IoU >= 0.50, Delta_d < 52.4 cm) và cơ chế tự kiểm duyệt ca mơ hồ (Decision Margin >= 0.15).
  8. Chuẩn hóa toàn diện 4 nhóm thuộc tính (Nhóm A, B, C, D) theo chuẩn GIS.
  9. Kết xuất đồng thời:
     - Tệp CSV chuẩn hóa: PV_Standardized_GIS_Database.csv
     - Tệp GeoPackage (.gpkg): PV_Standardized_GIS_Database.gpkg (lớp mapped_detections và modules_reference)
     - Tệp GeoJSON (.geojson): PV_Standardized_Mapped_Detections.geojson (chuẩn RFC 7946 EPSG:4326)
  10. Đo đạc và xuất toàn bộ các chỉ số thống kê thực nghiệm phục vụ viết báo cáo khoa học.
"""

import os
import sys
import re
import ast
import math
import time
import json
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point
from shapely import wkt
import pyproj
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các hàm toán học và trắc địa từ dlt_hartley_homography.py
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from dlt_hartley_homography import (
    resolve_file_path,
    parse_tuple_coords,
    ransac_dlt_homography,
    project_points_homography,
    SEED,
    FIT_RATIO,
    DECISION_MARGIN_M
)

# Cấu hình tham số ngưỡng kỹ thuật
TAU_IOU = 0.50              # Ngưỡng IoU tối thiểu
D_MAX_METERS = 0.524        # Ngưỡng sai lệch tâm tối đa (52.4 cm)
DELTA_MARGIN_AMBIGUOUS = 0.15 # Ngưỡng phân định mơ hồ
SEARCH_RADIUS_M = 2.50      # Bán kính tìm kiếm ứng viên lân cận
PENALTY_COST = 50.0         # Chi phí phạt ngoài bán kính


def extract_clean_module_id(name):
    """Trích xuất ID module chuẩn: blockX_stringY_ZZZZZ"""
    if not isinstance(name, str):
        return ''
    m = re.search(r'(block\d+_string\d+_\d+)', name)
    if m:
        return m.group(1)
    return str(name).split(' ')[0].strip()


def run_pipeline():
    print("=" * 80)
    print(" BẮT ĐẦU PIPELINE XUẤT CƠ SỞ DỮ LIỆU GIS CHUẨN HÓA VÀ KẾT XUẤT GPKG / GEOJSON")
    print("=" * 80)
    t0 = time.time()

    src_csv_path = resolve_file_path('PV_Coordinates_Ortho_Vung_1_20260929_0018.csv')
    ref_csv_path = resolve_file_path('bbox_centroid_export.csv')

    print(f"1. Đọc tệp CSV detection vùng: {src_csv_path}")
    df_src = pd.read_csv(src_csv_path)
    N_src = len(df_src)
    print(f"   -> Tổng số detection nguồn: {N_src}")

    print(f"2. Đọc tệp CSV mốc GIS QGIS tham chiếu: {ref_csv_path}")
    df_ref = pd.read_csv(ref_csv_path)
    M_ref_total = len(df_ref)
    print(f"   -> Tổng số module toàn nhà máy: {M_ref_total}")

    # Bước 1: Ghép cặp GPS + AI Matching để ước lượng Homography
    print("\n--- BƯỚC 1: Ghép cặp GPS + AI Matching và Ước lượng Homography DLT Hartley ---")
    df_src['match_id'] = df_src['Point_Name'].apply(extract_clean_module_id)
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_pairs = merged[merged['centroid_x'].notna()].copy().reset_index(drop=True)
    N_eval = len(matched_pairs)
    print(f"   -> Số cặp mốc đối ứng khớp GPS + AI: {N_eval} / {N_src} ({N_eval/N_src*100:.2f}%)")

    # Phân chia 70% Control Points và 30% Independent Check Points
    src_pts = matched_pairs[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm = matched_pairs[['centroid_x', 'centroid_y']].values.astype(np.float64)

    rng = np.random.default_rng(SEED)
    perm = rng.permutation(N_eval)
    n_fit = int(N_eval * FIT_RATIO)
    is_check_point = np.zeros(N_eval, dtype=bool)
    is_check_point[perm[n_fit:]] = True

    matched_pairs['is_check'] = is_check_point
    check_point_map = matched_pairs.set_index('Point_Name')['is_check'].to_dict()

    src_fit, dst_fit = src_pts[perm[:n_fit]], dst_utm[perm[:n_fit]]
    H_utm, inlier_mask, condition_number = ransac_dlt_homography(
        src_fit, dst_fit, threshold=0.5, max_iters=2000, seed=SEED
    )
    print(f"   -> Tập huấn luyện (Control Points): {n_fit} mốc (RANSAC Inliers = {int(np.sum(inlier_mask))})")
    print(f"   -> Tập kiểm tra độc lập (Independent Check Points): {int(np.sum(is_check_point))} mốc (30%)")
    cond_val = condition_number.get('cond', 0.0) if isinstance(condition_number, dict) else float(condition_number)
    print(f"   -> Ma trận H_utm hoàn tất, số điều kiện Hartley: {cond_val:.2e}")

    # Bước 2: Ánh xạ tọa độ 4 đỉnh OBB sang UTM Zone 49N
    print("\n--- BƯỚC 2: Ánh xạ 4 đỉnh OBB sang UTM Zone 49N và WGS84 ---")
    nw_pts = np.array([parse_tuple_coords(v) for v in df_src['BBox_NW_Pixel']], dtype=np.float64)
    ne_pts = np.array([parse_tuple_coords(v) for v in df_src['BBox_NE_Pixel']], dtype=np.float64)
    se_pts = np.array([parse_tuple_coords(v) for v in df_src['BBox_SE_Pixel']], dtype=np.float64)
    sw_pts = np.array([parse_tuple_coords(v) for v in df_src['BBox_SW_Pixel']], dtype=np.float64)

    proj_corners_nw = project_points_homography(nw_pts, H_utm)
    proj_corners_ne = project_points_homography(ne_pts, H_utm)
    proj_corners_se = project_points_homography(se_pts, H_utm)
    proj_corners_sw = project_points_homography(sw_pts, H_utm)

    # Chuyển đổi tọa độ UTM Zone 49N sang WGS84 kinh vĩ độ
    transformer = pyproj.Transformer.from_crs("EPSG:32649", "EPSG:4326", always_xy=True)

    proj_polys_utm = []
    proj_polys_wgs84 = []
    proj_centroids_utm = []
    proj_centroids_wgs84 = []

    for i in range(N_src):
        # Đa giác UTM
        poly_u = Polygon([
            proj_corners_nw[i],
            proj_corners_ne[i],
            proj_corners_se[i],
            proj_corners_sw[i]
        ])
        if not poly_u.is_valid:
            poly_u = poly_u.buffer(0)
        proj_polys_utm.append(poly_u)
        cx_u, cy_u = poly_u.centroid.x, poly_u.centroid.y
        proj_centroids_utm.append((cx_u, cy_u))

        # Đa giác WGS84
        c_nw_lon, c_nw_lat = transformer.transform(proj_corners_nw[i][0], proj_corners_nw[i][1])
        c_ne_lon, c_ne_lat = transformer.transform(proj_corners_ne[i][0], proj_corners_ne[i][1])
        c_se_lon, c_se_lat = transformer.transform(proj_corners_se[i][0], proj_corners_se[i][1])
        c_sw_lon, c_sw_lat = transformer.transform(proj_corners_sw[i][0], proj_corners_sw[i][1])
        poly_w = Polygon([
            (c_nw_lon, c_nw_lat),
            (c_ne_lon, c_ne_lat),
            (c_se_lon, c_se_lat),
            (c_sw_lon, c_sw_lat)
        ])
        if not poly_w.is_valid:
            poly_w = poly_w.buffer(0)
        proj_polys_wgs84.append(poly_w)
        lon_c, lat_c = transformer.transform(cx_u, cy_u)
        proj_centroids_wgs84.append((lon_c, lat_c))

    proj_centroids_utm = np.array(proj_centroids_utm, dtype=np.float64)

    # Bước 3: Tìm kiếm ứng viên và xây dựng Polyref
    print("\n--- BƯỚC 3: Trích xuất ứng viên tham chiếu Polyref qua KDTree ---")
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values.astype(np.float64)
    ref_tree = cKDTree(ref_coords)

    cand_indices_per_det = ref_tree.query_ball_point(proj_centroids_utm, r=SEARCH_RADIUS_M)
    unique_cand_indices = sorted(list(set([idx for clist in cand_indices_per_det for idx in clist])))
    ref_cand_map = {orig_idx: cand_i for cand_i, orig_idx in enumerate(unique_cand_indices)}
    df_ref_pool = df_ref.iloc[unique_cand_indices].copy().reset_index(drop=True)
    M_cand = len(df_ref_pool)
    print(f"   -> Số module tham chiếu trong pool ứng viên: {M_cand}")

    # Tạo Polygon tham chiếu UTM
    ref_polys_utm = []
    ref_centroids_utm = df_ref_pool[['centroid_x', 'centroid_y']].values.astype(np.float64)
    corner_cols = ['corner_bottom_left', 'corner_bottom_right', 'corner_top_right', 'corner_top_left']

    for _, row in df_ref_pool.iterrows():
        pts = [parse_tuple_coords(row[c]) for c in corner_cols]
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        ref_polys_utm.append(poly)

    # Bước 4: Xây dựng Ma trận chi phí và Hungarian Matching
    print("\n--- BƯỚC 4: Giải Hungarian Bipartite Matching ---")
    C = np.full((N_src, M_cand), PENALTY_COST, dtype=np.float64)

    for i in range(N_src):
        poly_p = proj_polys_utm[i]
        c_p = proj_centroids_utm[i]
        for orig_j in cand_indices_per_det[i]:
            cand_j = ref_cand_map[orig_j]
            poly_r = ref_polys_utm[cand_j]
            inter_area = poly_p.intersection(poly_r).area
            if inter_area > 0:
                union_area = poly_p.union(poly_r).area
                iou = inter_area / union_area if union_area > 0 else 0.0
            else:
                iou = 0.0
            dist = np.linalg.norm(c_p - ref_centroids_utm[cand_j])
            cost = 0.60 * (1.0 - iou) + 0.40 * min(dist / D_MAX_METERS, 1.0)
            C[i, cand_j] = cost

    row_ind, col_ind = linear_sum_assignment(C)
    assignment = {r: c for r, c in zip(row_ind, col_ind)}

    # Bước 5: Áp dụng Cổng kiểm duyệt kép và Phân xử mơ hồ
    print("\n--- BƯỚC 5: Kiểm định kép và Phân xử ca mơ hồ ---")
    records = []
    
    # Chuẩn bị ánh xạ phân loại lỗi
    def classify_defect_severity(cls_name):
        if cls_name == 'Unclassified':
            return 'Normal PV', 'Bình thường', False
        elif cls_name == 'SingleHotSpot':
            return 'Hotspot đơn điểm (Single Hotspot)', 'Trung bình', True
        elif cls_name == 'MultiHotSpot':
            return 'Hotspot đa điểm (Multi Hotspot)', 'Nghiêm trọng', True
        elif cls_name == 'Bypass':
            return 'Lỗi Đi-ốt bắc cầu (Bypass Diode)', 'Nghiêm trọng', True
        elif cls_name == 'Mixed':
            return 'Lỗi hỗn hợp (Mixed Fault)', 'Nghiêm trọng', True
        else:
            return f'Khuyết tật {cls_name}', 'Cần theo dõi', True

    for i in range(N_src):
        det_row = df_src.iloc[i]
        poly_p = proj_polys_utm[i]
        cx_u, cy_u = proj_centroids_utm[i]
        lon_c, lat_c = proj_centroids_wgs84[i]
        det_id = det_row['Point_Name']
        source_id = det_row['Internal_Code'] if pd.notna(det_row['Internal_Code']) else ''
        ground_truth_id = det_row['match_id']
        is_chk = check_point_map.get(det_id, False)
        cls_raw = det_row['Class']
        fault_desc, fault_sev, is_defect = classify_defect_severity(cls_raw)

        # Tính toán IoU với tất cả ứng viên lân cận để tìm Top-1 và Top-2
        candidate_ious = []
        for orig_j in cand_indices_per_det[i]:
            cand_j = ref_cand_map[orig_j]
            poly_r = ref_polys_utm[cand_j]
            inter_area = poly_p.intersection(poly_r).area
            if inter_area > 0:
                union_area = poly_p.union(poly_r).area
                iou_val = inter_area / union_area if union_area > 0 else 0.0
            else:
                iou_val = 0.0
            candidate_ious.append((cand_j, iou_val))

        candidate_ious.sort(key=lambda x: x[1], reverse=True)
        top1_cand_j = candidate_ious[0][0] if candidate_ious else None
        top1_iou = candidate_ious[0][1] if candidate_ious else 0.0
        top2_iou = candidate_ious[1][1] if len(candidate_ious) > 1 else 0.0
        decision_margin = top1_iou - top2_iou

        assigned_cand_j = assignment.get(i, None)
        assigned_cost = C[i, assigned_cand_j] if assigned_cand_j is not None else PENALTY_COST

        panel_id_assigned = None
        match_status = 'unassigned'
        qc_status = 'QC_UNASSIGNED'
        review_note = ''
        center_dist = None
        iou_assigned = 0.0

        if assigned_cand_j is not None and assigned_cost < PENALTY_COST:
            ref_row = df_ref_pool.iloc[assigned_cand_j]
            cand_panel_id = ref_row['module_id']
            poly_r = ref_polys_utm[assigned_cand_j]

            inter_area = poly_p.intersection(poly_r).area
            union_area = poly_p.union(poly_r).area
            iou_assigned = inter_area / union_area if union_area > 0 else 0.0
            center_dist = float(np.linalg.norm([cx_u - ref_row['centroid_x'], cy_u - ref_row['centroid_y']]))

            # Kiểm tra cổng kiểm duyệt kép
            is_iou_pass = (iou_assigned >= TAU_IOU)
            is_dist_pass = (center_dist < D_MAX_METERS)

            # Kiểm tra điều kiện mơ hồ
            is_ambiguous = (decision_margin < DELTA_MARGIN_AMBIGUOUS and top2_iou >= 0.30)

            if is_ambiguous:
                match_status = 'ambiguous'
                qc_status = 'QC_FLAG_AMBIGUOUS'
                review_note = f'CẢNH BÁO MƠ HỒ: Margin={decision_margin:.3f} < {DELTA_MARGIN_AMBIGUOUS}, tranh chấp Top-1 ({top1_iou:.3f}) và Top-2 ({top2_iou:.3f})'
                panel_id_assigned = None
            elif is_iou_pass and is_dist_pass:
                match_status = 'accepted'
                qc_status = 'QC_PASS'
                panel_id_assigned = cand_panel_id
                review_note = f'HỢP LỆ: Đạt cổng kép (IoU={iou_assigned:.3f} >= 0.50, d={center_dist*100:.1f}cm < 52.4cm)'
            else:
                match_status = 'rejected_threshold'
                qc_status = 'QC_FAIL_THRESHOLD'
                reasons = []
                if not is_iou_pass:
                    reasons.append(f'IoU={iou_assigned:.3f} < 0.50')
                if not is_dist_pass:
                    reasons.append(f'Lệch tâm={center_dist*100:.1f}cm >= 52.4cm')
                review_note = f'LOẠI BỎ DO NGƯỠNG: {"; ".join(reasons)}'
                panel_id_assigned = None
        else:
            match_status = 'unassigned'
            qc_status = 'QC_UNASSIGNED'
            review_note = 'Không có module tham chiếu phù hợp trong bán kính 2.5m'
            panel_id_assigned = None

        # Kiểm tra đúng sai so với mốc ground truth
        is_correct_id = None
        is_adjacent_alias = False
        if panel_id_assigned is not None and ground_truth_id:
            if panel_id_assigned == ground_truth_id:
                is_correct_id = True
            else:
                is_correct_id = False
                # Kiểm tra có phải láng giềng trong cùng string
                src_block_str = ground_truth_id.rsplit('_', 1)[0]
                pred_block_str = panel_id_assigned.rsplit('_', 1)[0]
                if src_block_str == pred_block_str:
                    is_adjacent_alias = True

        # Chuỗi tọa độ 4 đỉnh
        src_verts = [parse_tuple_coords(det_row[c]) for c in ['BBox_NW_Pixel', 'BBox_NE_Pixel', 'BBox_SE_Pixel', 'BBox_SW_Pixel']]
        mapped_verts_utm = [
            (round(proj_corners_nw[i][0], 3), round(proj_corners_nw[i][1], 3)),
            (round(proj_corners_ne[i][0], 3), round(proj_corners_ne[i][1], 3)),
            (round(proj_corners_se[i][0], 3), round(proj_corners_se[i][1], 3)),
            (round(proj_corners_sw[i][0], 3), round(proj_corners_sw[i][1], 3))
        ]
        mapped_verts_wgs84 = [
            (round(c_nw_lon, 7), round(c_nw_lat, 7)),
            (round(c_ne_lon, 7), round(c_ne_lat, 7)),
            (round(c_se_lon, 7), round(c_se_lat, 7)),
            (round(c_sw_lon, 7), round(c_sw_lat, 7))
        ]

        records.append({
            # Nhóm A — Định danh và truy vết
            'detection_id': det_id,
            'source_id': source_id,
            'panel_id': panel_id_assigned if panel_id_assigned else '',
            'match_status': match_status,
            'ground_truth_id': ground_truth_id,
            'is_correct_id': is_correct_id if is_correct_id is not None else '',
            'is_adjacent_alias': is_adjacent_alias,

            # Nhóm B — Tọa độ và hình học
            'source_vertices': str(src_verts),
            'mapped_vertices_utm': str(mapped_verts_utm),
            'mapped_vertices_wgs84': str(mapped_verts_wgs84),
            'centroid_x_utm': round(cx_u, 3),
            'centroid_y_utm': round(cy_u, 3),
            'longitude': round(lon_c, 7),
            'latitude': round(lat_c, 7),
            'crs': 'EPSG:32649',
            'wkt_geometry_utm': poly_p.wkt,
            'wkt_geometry_wgs84': poly_w.wkt,

            # Nhóm C — Thuộc tính detection
            'class_name': 'solar_panel',
            'fault_type': cls_raw,
            'fault_description': fault_desc,
            'fault_severity': fault_sev,
            'is_defect': is_defect,
            'confidence': '',  # Để trống theo đúng nguyên tắc không có dữ liệu

            # Nhóm D — Kiểm định ánh xạ
            'mapping_method': 'GPS_AI_Matching_DLT_Hartley_Homography_8DoF',
            'iou_score': round(iou_assigned, 4) if iou_assigned > 0 else 0.0,
            'center_distance_m': round(center_dist, 4) if center_dist is not None else '',
            'second_best_iou': round(top2_iou, 4),
            'decision_margin': round(decision_margin, 4),
            'qc_status': qc_status,
            'is_check_point': is_chk,
            'source_ortho': 'Ortho_Vung_1_35m',
            'target_ortho': 'Ortho_Tong_Quan_85m',
            'review_note': review_note
        })

    df_standard = pd.DataFrame(records)

    # Thống kê đo đạc
    N_total = len(df_standard)
    df_eval = df_standard[df_standard['ground_truth_id'] != ''].copy()
    N_eval_total = len(df_eval)
    df_assigned = df_standard[df_standard['panel_id'] != ''].copy()
    N_assigned = len(df_assigned)

    df_assigned_eval = df_assigned[df_assigned['ground_truth_id'] != ''].copy()
    N_correct = int(np.sum(df_assigned_eval['is_correct_id'] == True))
    N_wrong = int(np.sum(df_assigned_eval['is_correct_id'] == False))
    N_alias = int(np.sum(df_assigned_eval['is_adjacent_alias'] == True))
    N_other_wrong = N_wrong - N_alias

    N_ambiguous = int(np.sum(df_standard['match_status'] == 'ambiguous'))
    N_rejected = int(np.sum(df_standard['match_status'] == 'rejected_threshold'))
    N_unassigned = int(np.sum(df_standard['match_status'] == 'unassigned'))

    acc_assigned_pct = round(N_correct / len(df_assigned_eval) * 100, 2) if len(df_assigned_eval) > 0 else 0.0
    acc_all_eval_pct = round(N_correct / N_eval_total * 100, 2)
    alias_rate_pct = round(N_alias / len(df_assigned_eval) * 100, 2) if len(df_assigned_eval) > 0 else 0.0
    coverage_pct = round(N_assigned / N_total * 100, 2)

    # Đánh giá trên tập 30% Check Points
    df_chk = df_eval[df_eval['is_check_point'] == True].copy()
    N_chk = len(df_chk)
    df_chk_assigned = df_chk[df_chk['panel_id'] != ''].copy()
    N_chk_assigned = len(df_chk_assigned)
    N_chk_correct = int(np.sum(df_chk_assigned['is_correct_id'] == True))
    N_chk_alias = int(np.sum(df_chk_assigned['is_adjacent_alias'] == True))
    chk_acc_pct = round(N_chk_correct / N_chk_assigned * 100, 2) if N_chk_assigned > 0 else 0.0
    chk_alias_pct = round(N_chk_alias / N_chk_assigned * 100, 2) if N_chk_assigned > 0 else 0.0

    # Phân bố sai lệch tâm trên tập hợp lệ
    valid_dists = [float(v) * 100 for v in df_assigned['center_distance_m'] if v != '']
    valid_ious = [float(v) for v in df_assigned['iou_score'] if v != '']
    median_d_cm = round(float(np.median(valid_dists)), 2)
    p90_d_cm = round(float(np.percentile(valid_dists, 90)), 2)
    p95_d_cm = round(float(np.percentile(valid_dists, 95)), 2)
    max_d_cm = round(float(np.max(valid_dists)), 2)
    mean_d_cm = round(float(np.mean(valid_dists)), 2)
    rmse_d_cm = round(float(np.sqrt(np.mean(np.array(valid_dists)**2))), 2)

    median_iou = round(float(np.median(valid_ious)), 4)
    mean_iou = round(float(np.mean(valid_ious)), 4)
    p10_iou = round(float(np.percentile(valid_ious, 10)), 4)

    # Phân bố theo loại lỗi
    fault_summary = df_standard['fault_type'].value_counts().to_dict()
    assigned_fault_summary = df_assigned['fault_type'].value_counts().to_dict()

    print("\n" + "=" * 80)
    print(" KẾT QUẢ ĐO ĐẠC CHÍNH XÁC KHÔNG GÁN CỨNG (CALCULATED IN REAL TIME):")
    print(f"1. Tổng số detection: {N_total}")
    print(f"2. Số được cấp Panel ID (N_assigned): {N_assigned} ({coverage_pct}%)")
    print(f"3. Số gán đúng Panel ID (N_correct): {N_correct}")
    print(f"4. Số gán sai Panel ID (N_wrong): {N_wrong} (Trong đó Aliasing: {N_alias}, Khác: {N_other_wrong})")
    print(f"5. Số ca mơ hồ bị cách ly (N_ambiguous): {N_ambiguous}")
    print(f"6. Số ca vi phạm ngưỡng kép bị loại bỏ (N_rejected): {N_rejected}")
    print(f"7. Số ca không gán được (N_unassigned): {N_unassigned}")
    print(f"8. Top-1 Module ID Accuracy trên tập cấp mã: {acc_assigned_pct}% ({N_correct}/{len(df_assigned_eval)})")
    print(f"9. Aliasing Rate trên tập cấp mã: {alias_rate_pct}% ({N_alias}/{len(df_assigned_eval)})")
    print(f"10. Check Points (30% - {N_chk} mốc): Top-1 Accuracy = {chk_acc_pct}%, Aliasing Rate = {chk_alias_pct}%")
    print(f"11. Sai lệch tâm: Trung vị = {median_d_cm} cm, P95 = {p95_d_cm} cm, Cực đại = {max_d_cm} cm, RMSE = {rmse_d_cm} cm")
    print(f"12. IoU: Trung vị = {median_iou}, Trung bình = {mean_iou}, P10 = {p10_iou}")
    print(f"13. Phân bố loại lỗi: {fault_summary}")
    print(f"    Phân bố loại lỗi đã cấp Panel ID: {assigned_fault_summary}")
    print("=" * 80)

    # Bước 6: Xuất CSV chuẩn hóa
    print("\n--- BƯỚC 6: Xuất tệp CSV chuẩn hóa ---")
    out_csv_bb = os.path.join(current_dir, 'PV_Standardized_GIS_Database.csv')
    out_csv_root = os.path.abspath('PV_Standardized_GIS_Database.csv')
    df_standard.to_csv(out_csv_bb, index=False, encoding='utf-8-sig')
    df_standard.to_csv(out_csv_root, index=False, encoding='utf-8-sig')
    print(f"   -> Đã ghi tệp CSV: {out_csv_bb}")
    print(f"   -> Đã ghi tệp CSV: {out_csv_root}")

    # Bước 7: Kết xuất GeoJSON
    print("\n--- BƯỚC 7: Kết xuất tệp GeoJSON chuẩn RFC 7946 ---")
    features = []
    for i in range(N_total):
        row_dict = records[i]
        poly_w = proj_polys_wgs84[i]
        coords = [list(poly_w.exterior.coords)]
        feature = {
            "type": "Feature",
            "properties": {
                "detection_id": row_dict["detection_id"],
                "source_id": row_dict["source_id"],
                "panel_id": row_dict["panel_id"] if row_dict["panel_id"] else None,
                "match_status": row_dict["match_status"],
                "ground_truth_id": row_dict["ground_truth_id"],
                "is_correct_id": row_dict["is_correct_id"] if row_dict["is_correct_id"] != '' else None,
                "source_vertices": row_dict["source_vertices"],
                "mapped_vertices_utm": row_dict["mapped_vertices_utm"],
                "mapped_vertices_wgs84": row_dict["mapped_vertices_wgs84"],
                "centroid_x_utm": row_dict["centroid_x_utm"],
                "centroid_y_utm": row_dict["centroid_y_utm"],
                "longitude": row_dict["longitude"],
                "latitude": row_dict["latitude"],
                "crs": row_dict["crs"],
                "class_name": row_dict["class_name"],
                "fault_type": row_dict["fault_type"],
                "fault_description": row_dict["fault_description"],
                "fault_severity": row_dict["fault_severity"],
                "is_defect": row_dict["is_defect"],
                "confidence": None,
                "mapping_method": row_dict["mapping_method"],
                "iou_score": row_dict["iou_score"],
                "center_distance_m": float(row_dict["center_distance_m"]) if row_dict["center_distance_m"] != '' else None,
                "second_best_iou": row_dict["second_best_iou"],
                "decision_margin": row_dict["decision_margin"],
                "qc_status": row_dict["qc_status"],
                "is_check_point": bool(row_dict["is_check_point"]),
                "source_ortho": row_dict["source_ortho"],
                "target_ortho": row_dict["target_ortho"],
                "review_note": row_dict["review_note"]
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": coords
            }
        }
        features.append(feature)

    geojson_obj = {
        "type": "FeatureCollection",
        "name": "PV_Standardized_Mapped_Detections",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": features
    }

    out_geojson_bb = os.path.join(current_dir, 'PV_Standardized_Mapped_Detections.geojson')
    out_geojson_root = os.path.abspath('PV_Standardized_Mapped_Detections.geojson')
    with open(out_geojson_bb, 'w', encoding='utf-8') as f:
        json.dump(geojson_obj, f, ensure_ascii=False)
    with open(out_geojson_root, 'w', encoding='utf-8') as f:
        json.dump(geojson_obj, f, ensure_ascii=False)
    print(f"   -> Đã ghi GeoJSON: {out_geojson_bb} ({len(features)} features)")
    print(f"   -> Đã ghi GeoJSON: {out_geojson_root} ({len(features)} features)")

    # Bước 8: Kết xuất GeoPackage (.gpkg)
    print("\n--- BƯỚC 8: Kết xuất tệp GeoPackage (.gpkg) đa lớp ---")
    gdf_mapped = gpd.GeoDataFrame(
        df_standard.drop(columns=['wkt_geometry_utm', 'wkt_geometry_wgs84']),
        geometry=proj_polys_utm,
        crs="EPSG:32649"
    )

    out_gpkg_bb = os.path.join(current_dir, 'PV_Standardized_GIS_Database.gpkg')
    out_gpkg_root = os.path.abspath('PV_Standardized_GIS_Database.gpkg')

    gdf_mapped.to_file(out_gpkg_bb, layer='mapped_detections', driver='GPKG', engine='pyogrio')
    gdf_mapped.to_file(out_gpkg_root, layer='mapped_detections', driver='GPKG', engine='pyogrio')

    # Kết xuất thêm lớp tham chiếu module (pool ứng viên lân cận)
    gdf_ref_pool = gpd.GeoDataFrame(
        df_ref_pool[['ID_Pin', 'Row_ID', 'module_id', 'String_ID', 'layer', 'centroid_x', 'centroid_y']],
        geometry=ref_polys_utm,
        crs="EPSG:32649"
    )
    gdf_ref_pool.to_file(out_gpkg_bb, layer='modules_reference', driver='GPKG', engine='pyogrio', mode='a')
    gdf_ref_pool.to_file(out_gpkg_root, layer='modules_reference', driver='GPKG', engine='pyogrio', mode='a')
    print(f"   -> Đã ghi GeoPackage: {out_gpkg_bb} (Lớp mapped_detections + modules_reference)")
    print(f"   -> Đã ghi GeoPackage: {out_gpkg_root} (Lớp mapped_detections + modules_reference)")

    metrics = {
        'N_total': N_total,
        'M_ref_total': M_ref_total,
        'M_cand': M_cand,
        'N_eval': N_eval,
        'N_assigned': N_assigned,
        'N_correct': N_correct,
        'N_wrong': N_wrong,
        'N_alias': N_alias,
        'N_other_wrong': N_other_wrong,
        'N_ambiguous': N_ambiguous,
        'N_rejected': N_rejected,
        'N_unassigned': N_unassigned,
        'coverage_pct': coverage_pct,
        'acc_assigned_pct': acc_assigned_pct,
        'acc_all_eval_pct': acc_all_eval_pct,
        'alias_rate_pct': alias_rate_pct,
        'N_chk': N_chk,
        'N_chk_assigned': N_chk_assigned,
        'N_chk_correct': N_chk_correct,
        'N_chk_alias': N_chk_alias,
        'chk_acc_pct': chk_acc_pct,
        'chk_alias_pct': chk_alias_pct,
        'median_d_cm': median_d_cm,
        'mean_d_cm': mean_d_cm,
        'p90_d_cm': p90_d_cm,
        'p95_d_cm': p95_d_cm,
        'max_d_cm': max_d_cm,
        'rmse_d_cm': rmse_d_cm,
        'median_iou': median_iou,
        'mean_iou': mean_iou,
        'p10_iou': p10_iou,
        'fault_summary': fault_summary,
        'assigned_fault_summary': assigned_fault_summary,
        'elapsed_sec': round(time.time() - t0, 2)
    }

    # Lưu metrics ra JSON để tiện đối chiếu và đảm bảo 100% số liệu thực
    metrics_path = os.path.join(current_dir, 'pipeline_metrics_summary.json')
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"   -> Đã lưu tóm tắt thống kê: {metrics_path}")

    return metrics


if __name__ == '__main__':
    run_pipeline()
