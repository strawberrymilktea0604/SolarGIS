"""
Module: measure_top1_accuracy_aliasing.py
Thư mục: Bounding Box
Mục đích:
- Đo đạc chỉ số độ chính xác gán định danh (Top-1 Module ID Accuracy):
  Kiểm tra tỷ lệ gán đúng Panel ID thực tế; xác nhận tỷ lệ nhảy nhầm tấm láng giềng (Aliasing Rate) tiệm cận 0%.
- Tuân thủ nghiêm ngặt nguyên tắc:
  + CSV detection là trung tâm dữ liệu đầu vào và kết xuất đầu ra.
  + Tuyệt đối không dùng file JSON ortho, chỉ dùng:
      * File nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB detection 35m)
      * File mốc chuẩn GIS: bbox_centroid_export.csv (36.544 module GIS QGIS toàn cảnh 85m)
  + Sử dụng GPS + AI Matching để ước lượng ma trận Homography DLT Hartley (8 DoF) có chuẩn hóa Hartley
    và RANSAC, chiếu 4 đỉnh OBB sang hệ phẳng UTM Zone 49N.
  + Áp dụng Hungarian Algorithm kết hợp cổng kiểm duyệt kép (IoU >= 0.50, Delta_d < 52.4 cm).
  + Đối soát độc lập với tập Panel ID tham chiếu (Expert-annotated reference map):
      * Tập toàn bộ 5.071 mốc kiểm định (N_eval = 5.071)
      * Tập 30% Independent Check Points (1.522 mốc kiểm tra độc lập, không tham gia huấn luyện ma trận)
  + Xác định chi tiết các trường hợp nhảy nhầm tấm láng giềng (Adjacent Aliasing: cùng chuỗi/bàn nhưng lệch vị trí).
  + Tuyệt đối không gán cứng giá trị; toàn bộ chỉ số được tính toán trực tiếp từ dữ liệu.
- Xuất file kết quả:
  + Bounding Box/PV_Top1_Accuracy_Aliasing_Evaluation.csv
  + PV_Top1_Accuracy_Aliasing_Evaluation.csv (thư mục gốc)
"""

import os
import sys
import re
import ast
import math
import time
import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm đường dẫn Bounding Box để import các hàm chuẩn
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from dlt_hartley_homography import (
    resolve_file_path,
    parse_tuple_coords,
    ransac_dlt_homography,
    project_points_homography,
    SEED,
    FIT_RATIO
)

# THAM SỐ VÀ NGƯỠNG KIỂM ĐỊNH
TAU_IOU = 0.50               # Ngưỡng IoU tối thiểu
D_MAX_METERS = 0.524          # Ngưỡng lệch tâm an toàn (52.4 cm = 1.048m / 2)
DELTA_MARGIN = 0.05          # Ngưỡng phân định mơ hồ
SEARCH_RADIUS_M = 2.50       # Bán kính tìm kiếm ứng viên quanh OBB
PENALTY_COST = 50.0          # Chi phí phạt ngoài bán kính


def parse_polygon_from_row(row, corner_cols):
    """Trích xuất Polygon Shapely từ 4 đỉnh định dạng chuỗi tuple"""
    pts = []
    for c in corner_cols:
        val = row.get(c)
        pt = parse_tuple_coords(val)
        if pt is None:
            return None
        pts.append(pt)
    if len(pts) == 4:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly
    return None


def run_top1_aliasing_evaluation(
    src_csv_name='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_name='bbox_centroid_export.csv',
    out_csv_name='PV_Top1_Accuracy_Aliasing_Evaluation.csv'
):
    print("=" * 80)
    print(" ĐO ĐẠC CHỈ SỐ ĐỘ CHÍNH XÁC GÁN ĐỊNH DANH (TOP-1 MODULE ID ACCURACY)")
    print(" KIỂM TRA TỶ LỆ GÁN ĐÚNG PANEL ID THỰC TẾ & XÁC NHẬN ALIASING TIỆM CẬN 0%")
    print("=" * 80)

    t_start = time.time()
    src_csv = resolve_file_path(src_csv_name)
    ref_csv = resolve_file_path(ref_csv_name)

    print(f"1. Tệp CSV detection đầu vào: {src_csv}")
    print(f"2. Tệp CSV mốc tham chiếu chuẩn: {ref_csv}")

    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)

    N_src = len(df_src)
    M_ref_total = len(df_ref)
    print(f"   -> N detection đầu vào: {N_src}")
    print(f"   -> M module tham chiếu GIS toàn nhà máy: {M_ref_total}")

    # 1. GHÉP CẶP GPS + AI MATCHING VÀ ƯỚC LƯỢNG HOMOGRAPHY
    print("\n--- BƯỚC 1: Khởi tạo mốc GPS + AI Matching & Tách tập Check Points ---")
    def extract_module_id(name):
        if not isinstance(name, str):
            return ''
        m = re.search(r'(block\d+_string\d+_\d+)', name)
        return m.group(1) if m else str(name).split(' ')[0].strip()

    df_src['match_id'] = df_src['Point_Name'].apply(extract_module_id)
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_pairs = merged[merged['centroid_x'].notna()].copy().reset_index(drop=True)
    N_eval = len(matched_pairs)
    print(f"   -> Số detection có thể xác minh ID tham chiếu: N_eval = {N_eval} / {N_src} ({N_eval/N_src*100:.2f}%)")

    # Tách tập 70% Control Points và 30% Independent Check Points
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
    H_utm, inlier_mask, _ = ransac_dlt_homography(
        src_fit, dst_fit, threshold=0.5, max_iters=2000, seed=SEED
    )
    N_check = int(np.sum(is_check_point))
    print(f"   -> Tập Control Points: {n_fit} mốc (RANSAC Inliers = {int(np.sum(inlier_mask))})")
    print(f"   -> Tập Independent Check Points: {N_check} mốc kiểm tra độc lập (30%)")

    # 2. XÂY DỰNG TẬP ĐA GIÁC DỰ PHÓNG Poly_proj
    print("\n--- BƯỚC 2: Xây dựng tập Đa giác dự phóng Poly_proj ---")
    proj_corners_nw = project_points_homography(
        np.array([parse_tuple_coords(v) for v in df_src['BBox_NW_Pixel']], dtype=np.float64), H_utm
    )
    proj_corners_ne = project_points_homography(
        np.array([parse_tuple_coords(v) for v in df_src['BBox_NE_Pixel']], dtype=np.float64), H_utm
    )
    proj_corners_se = project_points_homography(
        np.array([parse_tuple_coords(v) for v in df_src['BBox_SE_Pixel']], dtype=np.float64), H_utm
    )
    proj_corners_sw = project_points_homography(
        np.array([parse_tuple_coords(v) for v in df_src['BBox_SW_Pixel']], dtype=np.float64), H_utm
    )

    proj_polys = []
    proj_centroids = []
    for i in range(N_src):
        poly = Polygon([proj_corners_nw[i], proj_corners_ne[i], proj_corners_se[i], proj_corners_sw[i]])
        if not poly.is_valid:
            poly = poly.buffer(0)
        proj_polys.append(poly)
        proj_centroids.append((poly.centroid.x, poly.centroid.y))

    proj_centroids = np.array(proj_centroids, dtype=np.float64)

    # 3. XÂY DỰNG TẬP ĐA GIÁC THAM CHIẾU Poly_ref
    print("\n--- BƯỚC 3: Xây dựng tập Đa giác tham chiếu Poly_ref ---")
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values.astype(np.float64)
    ref_tree = cKDTree(ref_coords)

    cand_indices_per_det = ref_tree.query_ball_point(proj_centroids, r=SEARCH_RADIUS_M)
    unique_cand_indices = sorted(list(set([idx for clist in cand_indices_per_det for idx in clist])))
    ref_cand_map = {orig_idx: cand_i for cand_i, orig_idx in enumerate(unique_cand_indices)}
    df_cand_ref = df_ref.iloc[unique_cand_indices].copy().reset_index(drop=True)
    M_cand = len(df_cand_ref)

    ref_polys = []
    ref_centroids = []
    ref_corner_cols = ['corner_bottom_left', 'corner_bottom_right', 'corner_top_right', 'corner_top_left']
    for j in range(M_cand):
        row_ref = df_cand_ref.iloc[j]
        poly = parse_polygon_from_row(row_ref, ref_corner_cols)
        ref_polys.append(poly)
        ref_centroids.append((row_ref['centroid_x'], row_ref['centroid_y']))

    ref_centroids = np.array(ref_centroids, dtype=np.float64)
    print(f"   -> Pool ứng viên tham chiếu: M_cand = {M_cand}")

    # Bản đồ tra cứu siêu dữ liệu tham chiếu (String, Row, Layer, Centroid)
    ref_info_map = df_ref.set_index('module_id').to_dict('index')

    # 4. TỐI ƯU HÓA GHÉP CẶP HUNGARIAN & CỔNG KIỂM DUYỆT KÉP
    print("\n--- BƯỚC 4: Tối ưu ghép cặp Hungarian & Kiểm định trắc địa ---")
    C = np.full((N_src, M_cand), PENALTY_COST, dtype=np.float64)
    det_cands = [[] for _ in range(N_src)]

    for i in range(N_src):
        p_poly = proj_polys[i]
        pcx, pcy = proj_centroids[i]

        for orig_j in cand_indices_per_det[i]:
            cj = ref_cand_map[orig_j]
            r_poly = ref_polys[cj]
            rcx, rcy = ref_centroids[cj]

            inter = p_poly.intersection(r_poly).area
            union = p_poly.union(r_poly).area
            iou = float(inter / union) if union > 1e-9 else 0.0
            d_val = math.hypot(pcx - rcx, pcy - rcy)

            c_val = 0.60 * (1.0 - iou) + 0.30 * (d_val / D_MAX_METERS)
            C[i, cj] = c_val

            det_cands[i].append({
                'cand_col': cj,
                'module_id': df_cand_ref.loc[cj, 'module_id'],
                'iou': iou,
                'dist': d_val,
                'cost': c_val
            })

    row_ind, col_ind = linear_sum_assignment(C)
    assignment_map = {r: c for r, c in zip(row_ind, col_ind)}
    print("   -> Phân công Hungarian một-một hoàn tất.")

    # 5. ĐO ĐẠC CHI TIẾT TOP-1 ACCURACY VÀ ADJACENT ALIASING
    print("\n--- BƯỚC 5: Đo đạc Top-1 Accuracy và Adjacent Aliasing ---")
    records = []

    # Thống kê toàn bộ N_eval (5.071 mốc)
    N_assigned = 0
    N_correct = 0
    N_wrong = 0
    N_alias = 0
    N_other_wrong = 0
    N_ambiguous = 0
    N_unassigned = 0

    # Thống kê trên tập Independent Check Points (1.522 mốc)
    N_chk_eval = 0
    N_chk_assigned = 0
    N_chk_correct = 0
    N_chk_alias = 0
    N_chk_unassigned = 0

    distances_accepted = []
    distances_all_assigned = []

    for i in range(N_src):
        p_name = df_src.loc[i, 'Point_Name']
        gt_mid = df_src.loc[i, 'match_id']
        has_gt = bool(gt_mid and (gt_mid in ref_info_map))
        is_chk = check_point_map.get(p_name, False)

        cj = assignment_map[i]
        c_cost = float(C[i, cj])

        # Tìm ứng viên được gán
        c_list = sorted(det_cands[i], key=lambda x: x['iou'], reverse=True)
        h_cand = [c for c in c_list if c['cand_col'] == cj]

        if len(h_cand) > 0 and c_cost < PENALTY_COST:
            h_item = h_cand[0]
            cand_mid = h_item['module_id']
            iou_score = h_item['iou']
            d_center = h_item['dist']
        else:
            cand_mid = 'UNASSIGNED'
            iou_score = 0.0
            d_center = 999.0

        max_iou_found = c_list[0]['iou'] if len(c_list) > 0 else 0.0
        second_iou = c_list[1]['iou'] if len(c_list) > 1 else 0.0
        margin = max_iou_found - second_iou

        # Phân loại trạng thái
        is_ambiguous_case = (max_iou_found < TAU_IOU) and (second_iou > 0.0) and (margin <= DELTA_MARGIN)

        if is_ambiguous_case:
            match_status = 'ambiguous'
            panel_id_pred = ''
            note = f"Mơ hồ: Box nằm giữa 2 tấm lân cận (IoU1={max_iou_found:.3f}, IoU2={second_iou:.3f}, Delta={margin:.3f} <= 0.05)"
            N_ambiguous += 1
        elif d_center >= D_MAX_METERS or cand_mid == 'UNASSIGNED':
            match_status = 'unassigned'
            panel_id_pred = ''
            note = f"Chưa ghép được: Lệch tâm {d_center*100:.1f}cm >= 52.4cm; hộp rác ngoài hành lang"
            N_unassigned += 1
        elif iou_score < TAU_IOU:
            match_status = 'rejected_threshold'
            panel_id_pred = ''
            note = f"Không đạt ngưỡng: IoU={iou_score:.3f} < 0.50 (méo seamline); từ chối cấp mã"
            N_unassigned += 1
        else:
            match_status = 'accepted'
            panel_id_pred = cand_mid
            note = f"Đủ điều kiện cấp Panel ID: IoU={iou_score:.3f} >= 0.50 và Delta_d={d_center*100:.1f}cm < 52.4cm"
            N_assigned += 1
            distances_accepted.append(d_center)

        distances_all_assigned.append(d_center if d_center < 900 else 0.0)

        # ĐỐI CHIẾU VỚI PANEL ID THAM CHIẾU (GROUND TRUTH)
        is_correct_id = False
        is_adjacent_alias = False

        if has_gt:
            ref_info_gt = ref_info_map[gt_mid]

            if match_status == 'accepted':
                if panel_id_pred == gt_mid:
                    is_correct_id = True
                    N_correct += 1
                else:
                    is_correct_id = False
                    N_wrong += 1
                    # Kiểm tra xem có phải module lân cận (Adjacent Aliasing)
                    ref_info_pred = ref_info_map.get(panel_id_pred, {})
                    dx_mod = ref_info_pred.get('centroid_x', 0) - ref_info_gt.get('centroid_x', 0)
                    dy_mod = ref_info_pred.get('centroid_y', 0) - ref_info_gt.get('centroid_y', 0)
                    d_between_mods = math.hypot(dx_mod, dy_mod)

                    same_string = (ref_info_pred.get('String_ID') == ref_info_gt.get('String_ID'))
                    same_layer = (ref_info_pred.get('layer') == ref_info_gt.get('layer'))

                    # Nếu cùng chuỗi/cùng bàn và khoảng cách <= 2.5m -> Aliasing
                    if same_string and same_layer and d_between_mods <= 2.50:
                        is_adjacent_alias = True
                        N_alias += 1
                        note += f" | CẢNH BÁO ALIASING: Gán nhầm sang tấm lân cận cách {d_between_mods:.2f}m (GT={gt_mid})"
                    else:
                        N_other_wrong += 1
                        note += f" | SAI MÃ KHÁC (GT={gt_mid})"

            if is_chk:
                N_chk_eval += 1
                if match_status == 'accepted':
                    N_chk_assigned += 1
                    if panel_id_pred == gt_mid:
                        N_chk_correct += 1
                    else:
                        if is_adjacent_alias:
                            N_chk_alias += 1
                else:
                    N_chk_unassigned += 1

        nw_coord = f"({proj_corners_nw[i][0]:.4f}, {proj_corners_nw[i][1]:.4f})"
        ne_coord = f"({proj_corners_ne[i][0]:.4f}, {proj_corners_ne[i][1]:.4f})"
        se_coord = f"({proj_corners_se[i][0]:.4f}, {proj_corners_se[i][1]:.4f})"
        sw_coord = f"({proj_corners_sw[i][0]:.4f}, {proj_corners_sw[i][1]:.4f})"
        mapped_poly_str = f"[{nw_coord}, {ne_coord}, {se_coord}, {sw_coord}]"

        records.append({
            'detection_id': p_name,
            'mapped_vertices': mapped_poly_str,
            'panel_id_pred': panel_id_pred if panel_id_pred != '' else 'UNASSIGNED',
            'panel_id_ref': gt_mid if has_gt else 'NO_REF_ID',
            'iou_score': round(float(iou_score), 4),
            'center_distance_m': round(float(d_center), 4),
            'is_correct_id': is_correct_id if match_status == 'accepted' else False,
            'is_adjacent_alias': is_adjacent_alias,
            'match_status': match_status,
            'review_note': note,
            # Các trường hỗ trợ phân tích chi tiết
            'is_check_point': is_chk,
            'mapped_cx': round(float(proj_centroids[i][0]), 4),
            'mapped_cy': round(float(proj_centroids[i][1]), 4),
            'is_defect': 'CÓ' if str(df_src.loc[i, 'Class']).strip() != 'Unclassified' else 'KHÔNG',
            'class_label': str(df_src.loc[i, 'Class']).strip()
        })

    df_out = pd.DataFrame(records)

    # Xuất file CSV kết quả
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))

    out_csv1 = os.path.join(script_dir, out_csv_name)
    out_csv2 = os.path.join(root_dir, out_csv_name)

    df_out.to_csv(out_csv1, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv2, index=False, encoding='utf-8-sig')

    print(f"\nĐã xuất tệp CSV kết quả Top-1 Accuracy & Aliasing tại:")
    print(f" -> {out_csv1}")
    print(f" -> {out_csv2}")

    # TÍNH TOÁN CÁC CHỈ SỐ KHOA HỌC CHUẨN XÁC
    # 1. Trên tập toàn bộ mốc đối soát có ID tham chiếu (N_eval = 5.071)
    acc_on_assigned = round(N_correct / N_assigned * 100.0, 2) if N_assigned > 0 else 0.0
    acc_on_eval_all = round(N_correct / N_eval * 100.0, 2) if N_eval > 0 else 0.0
    coverage_rate = round(N_assigned / N_eval * 100.0, 2) if N_eval > 0 else 0.0

    alias_rate_on_assigned = round(N_alias / N_assigned * 100.0, 2) if N_assigned > 0 else 0.0
    alias_rate_on_all = round(N_alias / N_eval * 100.0, 2) if N_eval > 0 else 0.0

    # 2. Trên tập Independent Check Points (N_chk = 1.522)
    chk_acc_on_assigned = round(N_chk_correct / N_chk_assigned * 100.0, 2) if N_chk_assigned > 0 else 0.0
    chk_acc_on_eval = round(N_chk_correct / N_chk_eval * 100.0, 2) if N_chk_eval > 0 else 0.0
    chk_coverage = round(N_chk_assigned / N_chk_eval * 100.0, 2) if N_chk_eval > 0 else 0.0
    chk_alias_rate = round(N_chk_alias / N_chk_assigned * 100.0, 2) if N_chk_assigned > 0 else 0.0

    # 3. Phân bố sai lệch tâm trên các detection được chấp nhận (cm)
    dists_cm = np.array(distances_accepted, dtype=np.float64) * 100.0
    median_dist_cm = round(float(np.median(dists_cm)), 2)
    p95_dist_cm = round(float(np.percentile(dists_cm, 95)), 2)
    max_dist_cm = round(float(np.max(dists_cm)), 2)
    exceed_524_count = int(np.sum(np.array(distances_all_assigned) >= D_MAX_METERS))

    metrics = {
        'N_total': N_src,
        'N_eval': N_eval,
        'N_assigned': N_assigned,
        'N_correct': N_correct,
        'N_wrong': N_wrong,
        'N_alias': N_alias,
        'N_other_wrong': N_other_wrong,
        'N_ambiguous': N_ambiguous,
        'N_unassigned': N_unassigned,
        'acc_on_assigned_pct': acc_on_assigned,
        'acc_on_eval_all_pct': acc_on_eval_all,
        'coverage_pct': coverage_rate,
        'alias_rate_pct': alias_rate_on_assigned,
        'alias_rate_all_pct': alias_rate_on_all,
        'N_chk_eval': N_chk_eval,
        'N_chk_assigned': N_chk_assigned,
        'N_chk_correct': N_chk_correct,
        'N_chk_alias': N_chk_alias,
        'chk_acc_assigned_pct': chk_acc_on_assigned,
        'chk_acc_eval_pct': chk_acc_on_eval,
        'chk_coverage_pct': chk_coverage,
        'chk_alias_rate_pct': chk_alias_rate,
        'median_dist_cm': median_dist_cm,
        'p95_dist_cm': p95_dist_cm,
        'max_dist_cm': max_dist_cm,
        'exceed_524_count': exceed_524_count,
        'elapsed_sec': round(time.time() - t_start, 2)
    }

    print("\n" + "=" * 80)
    print(" BẢNG TỔNG HỢP KẾT QUẢ ĐO ĐẠC TOP-1 ACCURACY & ALIASING RATE (MỤC 3, 4, 6)")
    print("=" * 80)
    print(f"1. Tổng số detection đầu vào (N_total): {metrics['N_total']}")
    print(f"2. Số detection đủ điều kiện kiểm định (N_eval có ID tham chiếu): {metrics['N_eval']}")
    print(f"3. Số detection được cấp phát Panel ID (N_assigned): {metrics['N_assigned']} ({metrics['coverage_pct']}%)")
    print(f"4. Số detection gán đúng Panel ID (N_correct): {metrics['N_correct']}")
    print(f"5. Số detection gán sai Panel ID (N_wrong): {metrics['N_wrong']}")
    print(f"   -- Trong đó nhảy nhầm sang module lân cận (N_alias): {metrics['N_alias']}")
    print(f"   -- Gán sai không thuộc module lân cận (N_other_wrong): {metrics['N_other_wrong']}")
    print(f"6. Số trường hợp chưa được gán ID (N_unassigned + rejected + ambiguous): {metrics['N_unassigned']}")
    print(f"7. TOP-1 MODULE ID ACCURACY (trên tập đã cấp mã): {metrics['acc_on_assigned_pct']}% ({metrics['N_correct']}/{metrics['N_assigned']})")
    print(f"   Top-1 Accuracy trên toàn bộ tập kiểm định: {metrics['acc_on_eval_all_pct']}% ({metrics['N_correct']}/{metrics['N_eval']})")
    print(f"8. TỶ LỆ CẤP PHÁT PANEL ID (Coverage Rate): {metrics['coverage_pct']}%")
    print(f"9. ADJACENT ALIASING RATE (trên tập đã cấp mã): {metrics['alias_rate_pct']}% ({metrics['N_alias']}/{metrics['N_assigned']})")
    print(f"   Tỷ lệ Aliasing trên toàn bộ tập kiểm định: {metrics['alias_rate_all_pct']}% ({metrics['N_alias']}/{metrics['N_eval']})")
    print(f"10. KẾT QUẢ TRÊN TẬP INDEPENDENT CHECK POINTS (30% - 1.522 mốc):")
    print(f"    -- Top-1 Accuracy trên tập đã cấp mã: {metrics['chk_acc_assigned_pct']}% ({metrics['N_chk_correct']}/{metrics['N_chk_assigned']})")
    print(f"    -- Top-1 Accuracy trên toàn bộ tập Check Points: {metrics['chk_acc_eval_pct']}% ({metrics['N_chk_correct']}/{metrics['N_chk_eval']})")
    print(f"    -- Adjacent Aliasing Rate trên Check Points: {metrics['chk_alias_rate_pct']}% ({metrics['N_chk_alias']}/{metrics['N_chk_assigned']})")
    print(f"11. PHÂN BỐ SAI LỆCH TÂM HÌNH HỌC:")
    print(f"    -- Sai lệch tâm trung vị: {metrics['median_dist_cm']} cm")
    print(f"    -- Sai lệch tâm P95: {metrics['p95_dist_cm']} cm")
    print(f"    -- Sai lệch tâm lớn nhất: {metrics['max_dist_cm']} cm")
    print(f"    -- Số trường hợp sai lệch vượt 52.4 cm: {metrics['exceed_524_count']}")
    print(f"12. Thời gian thực thi toàn bộ pipeline: {metrics['elapsed_sec']} giây")
    print("=" * 80)

    return df_out, metrics


if __name__ == '__main__':
    run_top1_aliasing_evaluation()
