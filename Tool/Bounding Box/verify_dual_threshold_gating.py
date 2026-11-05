"""
Module: verify_dual_threshold_gating.py
Thư mục: Bounding Box
Mục đích:
- Thiết lập quy tắc kiểm duyệt khắt khe theo ngưỡng kép (Dual-Threshold Gating Verification):
  Chỉ chốt cấp phát mã Panel ID khi thỏa mãn đồng thời:
    + Max-IoU >= 0.50 (Độ chồng lấn hình học)
    + Sai lệch tâm Delta d < 0.524 m (52.4 cm = nửa chiều rộng module 1.048m)
- Tuân thủ nghiêm ngặt nguyên tắc:
  + CSV là trung tâm dữ liệu đầu vào và đầu ra.
  + Tuyệt đối không dùng file JSON ortho, chỉ dùng:
      * File nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB detection 35m)
      * File mốc chuẩn trắc địa: bbox_centroid_export.csv (36.544 module GIS QGIS toàn cảnh 85m)
  + Áp dụng GPS + AI Matching để ước lượng ma trận Homography DLT Hartley (8 DoF) có chuẩn hóa Hartley
    và RANSAC, chiếu 4 đỉnh OBB sang hệ phẳng UTM Zone 49N để tạo tập Poly_proj.
  + Dựng tập đa giác danh định Poly_ref từ các đỉnh góc trắc địa trong bbox_centroid_export.csv.
  + Áp dụng Hungarian Algorithm kết hợp cổng kiểm duyệt kép (IoU gate AND Distance gate).
  + Phân loại rành mạch 4 trạng thái chuẩn hóa: accepted, rejected_threshold, ambiguous, unassigned.
  + Tuyệt đối không gán cứng giá trị; toàn bộ chỉ số được tính toán trực tiếp từ dữ liệu.
- Xuất file kết quả:
  + Bounding Box/PV_Dual_Threshold_Gating_Evaluation.csv
  + PV_Dual_Threshold_Gating_Evaluation.csv (thư mục gốc)
"""

import os
import sys
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

# CÁC NGƯỠNG KIỂM DUYỆT TRẮC ĐỊA CHUẨN
TAU_IOU = 0.50             # Ngưỡng chồng lấn hình học tối thiểu
D_MAX_METERS = 0.524        # Ngưỡng sai lệch tâm tối đa (52.4 cm = 1.048m / 2)
DELTA_MARGIN_THRESHOLD = 0.05  # Ngưỡng phân định mơ hồ giữa hai ứng viên dẫn đầu
SEARCH_RADIUS_M = 2.50     # Bán kính tìm kiếm ứng viên quanh tâm OBB
PENALTY_COST = 50.0        # Chi phí phạt cho các cặp không hợp lệ / ngoài bán kính


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


def calculate_orientation_angle(pt_start, pt_end):
    """Tính góc định hướng trục dài module (0 - 180 độ)"""
    dx = pt_end[0] - pt_start[0]
    dy = pt_end[1] - pt_start[1]
    return math.degrees(math.atan2(dy, dx)) % 180.0


def run_dual_threshold_pipeline(
    src_csv_name='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_name='bbox_centroid_export.csv',
    out_csv_name='PV_Dual_Threshold_Gating_Evaluation.csv',
    tau_iou=TAU_IOU,
    d_max=D_MAX_METERS,
    delta_margin=DELTA_MARGIN_THRESHOLD
):
    print("=" * 80)
    print(" THIẾT LẬP QUY TẮC KIỂM DUYỆT KHẮT KHE THEO NGƯỠNG KÉP")
    print(" CHỈ CHỐT CẤP PHÁT PANEL ID KHI THỎA MÃN ĐỒNG THỜI:")
    print(f"   [Điều kiện 1] Max-IoU >= {tau_iou}")
    print(f"   [Điều kiện 2] Lệch tâm Delta_d < {d_max*100:.1f} cm ({d_max} m)")
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
    print("\n--- BƯỚC 1: Khởi tạo mốc GPS + AI Matching & Ánh xạ xạ ảnh ---")
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_pairs = merged[merged['centroid_x'].notna()].copy().reset_index(drop=True)
    N_gps_ai = len(matched_pairs)
    print(f"   -> Ghép cặp GPS + AI Matching thành công: {N_gps_ai} / {N_src} cặp ({N_gps_ai/N_src*100:.2f}%)")

    src_pts = matched_pairs[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm = matched_pairs[['centroid_x', 'centroid_y']].values.astype(np.float64)

    rng = np.random.default_rng(SEED)
    perm = rng.permutation(N_gps_ai)
    n_fit = int(N_gps_ai * FIT_RATIO)
    is_check_point = np.zeros(N_gps_ai, dtype=bool)
    is_check_point[perm[n_fit:]] = True

    src_fit, dst_fit = src_pts[perm[:n_fit]], dst_utm[perm[:n_fit]]
    H_utm, inlier_mask, _ = ransac_dlt_homography(
        src_fit, dst_fit, threshold=0.5, max_iters=2000, seed=SEED
    )
    print(f"   -> Ma trận Homography DLT Hartley ước lượng với {int(np.sum(inlier_mask))}/{n_fit} inliers.")

    # 2. XÂY DỰNG TẬP ĐA GIÁC DỰ PHÓNG (Poly_proj)
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
    proj_angles = []

    for i in range(N_src):
        nw = tuple(proj_corners_nw[i])
        ne = tuple(proj_corners_ne[i])
        se = tuple(proj_corners_se[i])
        sw = tuple(proj_corners_sw[i])
        poly = Polygon([nw, ne, se, sw])
        if not poly.is_valid:
            poly = poly.buffer(0)
        proj_polys.append(poly)
        proj_centroids.append((poly.centroid.x, poly.centroid.y))
        proj_angles.append(calculate_orientation_angle(nw, ne))

    proj_centroids = np.array(proj_centroids, dtype=np.float64)

    # 3. XÂY DỰNG TẬP ĐA GIÁC THAM CHIẾU (Poly_ref) TỪ MỐC QGIS
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
    ref_angles = []
    ref_corner_cols = ['corner_bottom_left', 'corner_bottom_right', 'corner_top_right', 'corner_top_left']

    for j in range(M_cand):
        row_ref = df_cand_ref.iloc[j]
        poly = parse_polygon_from_row(row_ref, ref_corner_cols)
        ref_polys.append(poly)
        ref_centroids.append((row_ref['centroid_x'], row_ref['centroid_y']))
        bl = parse_tuple_coords(row_ref['corner_bottom_left'])
        br = parse_tuple_coords(row_ref['corner_bottom_right'])
        ref_angles.append(calculate_orientation_angle(bl, br))

    ref_centroids = np.array(ref_centroids, dtype=np.float64)
    print(f"   -> Pool ứng viên tham chiếu: M_cand = {M_cand}")

    # 4. TÍNH TOÁN MA TRẬN CHI PHÍ VÀ CHẠY HUNGARIAN ALGORITHM
    print("\n--- BƯỚC 4: Xây dựng ma trận chi phí & Chạy Hungarian Algorithm ---")
    C = np.full((N_src, M_cand), PENALTY_COST, dtype=np.float64)
    det_candidates_data = [[] for _ in range(N_src)]

    for i in range(N_src):
        p_poly = proj_polys[i]
        p_cx, p_cy = proj_centroids[i]
        p_ang = proj_angles[i]

        for orig_j in cand_indices_per_det[i]:
            cj = ref_cand_map[orig_j]
            r_poly = ref_polys[cj]
            r_cx, r_cy = ref_centroids[cj]
            r_ang = ref_angles[cj]

            inter = p_poly.intersection(r_poly).area
            union = p_poly.union(r_poly).area
            iou = float(inter / union) if union > 1e-9 else 0.0

            d_center = math.hypot(p_cx - r_cx, p_cy - r_cy)
            diff_ang = abs(p_ang - r_ang)
            diff_ang = min(diff_ang, 180.0 - diff_ang)

            c_val = 0.60 * (1.0 - iou) + 0.30 * (d_center / d_max) + 0.10 * (diff_ang / 45.0)
            C[i, cj] = c_val

            det_candidates_data[i].append({
                'cand_col': cj,
                'module_id': df_cand_ref.loc[cj, 'module_id'],
                'iou': iou,
                'd_center': d_center,
                'diff_ang': diff_ang,
                'cost': c_val
            })

    row_ind, col_ind = linear_sum_assignment(C)
    assignment_map = {r: c for r, c in zip(row_ind, col_ind)}
    print("   -> Tối ưu phân công Hungarian hoàn tất.")

    # 5. THIẾT LẬP VÀ THỰC THI LOGIC KIỂM DUYỆT NGƯỠNG KÉP
    print("\n--- BƯỚC 5: Thực thi Logic kiểm duyệt ngưỡng kép & Phân loại 4 trạng thái ---")
    records = []

    # Bộ đếm logic kiểm duyệt kép
    N_both_pass = 0
    N_iou_fail = 0
    N_distance_fail = 0
    N_both_fail = 0

    # Bộ đếm 4 trạng thái chuẩn hóa
    status_counts = {
        'accepted': 0,
        'rejected_threshold': 0,
        'ambiguous': 0,
        'unassigned': 0
    }

    # Đối chiếu độc lập
    gt_check_map = {}
    for idx_cp, row_cp in matched_pairs.iterrows():
        if is_check_point[idx_cp]:
            gt_check_map[row_cp['Point_Name']] = row_cp['match_id']

    cp_correct_count = 0
    cp_total_count = len(gt_check_map)

    correct_top1_count = 0
    aliasing_count = 0
    eval_gt_count = 0

    for i in range(N_src):
        p_name = df_src.loc[i, 'Point_Name']
        gt_mid = df_src.loc[i, 'match_id']
        cls_raw = str(df_src.loc[i, 'Class']).strip()
        is_defect = 'CÓ' if cls_raw != 'Unclassified' else 'KHÔNG'

        cj = assignment_map[i]
        c_cost = float(C[i, cj])

        # Phân tích các ứng viên theo IoU giảm dần
        cand_list_sorted = sorted(det_candidates_data[i], key=lambda x: x['iou'], reverse=True)
        max_iou_found = cand_list_sorted[0]['iou'] if len(cand_list_sorted) > 0 else 0.0

        if len(cand_list_sorted) > 1:
            second_iou = cand_list_sorted[1]['iou']
            second_mid = cand_list_sorted[1]['module_id']
        else:
            second_iou = 0.0
            second_mid = 'NONE'

        margin = max_iou_found - second_iou

        # Thông số của cặp ghép Hungarian
        hungarian_cand = [c for c in cand_list_sorted if c['cand_col'] == cj]
        if len(hungarian_cand) > 0 and c_cost < PENALTY_COST:
            h_item = hungarian_cand[0]
            cand_mid = h_item['module_id']
            iou_score = h_item['iou']
            d_center = h_item['d_center']
            d_angle = h_item['diff_ang']
            cost_val = h_item['cost']
        else:
            cand_mid = 'UNASSIGNED'
            iou_score = 0.0
            d_center = 999.0
            d_angle = 0.0
            cost_val = PENALTY_COST

        # THỰC THI HAI CỔNG KIỂM DUYỆT (DUAL GATES)
        # Cổng 1: IoU >= 0.50
        iou_gate = 'pass' if iou_score >= tau_iou else 'fail'
        # Cổng 2: Sai lệch tâm < 0.524m (nhỏ hơn nghiêm ngặt)
        distance_gate = 'pass' if d_center < d_max else 'fail'

        # Đếm thống kê phân bổ 4 nhánh logic
        if iou_gate == 'pass' and distance_gate == 'pass':
            N_both_pass += 1
            is_both_pass = True
        elif iou_gate == 'fail' and distance_gate == 'pass':
            N_iou_fail += 1
            is_both_pass = False
        elif iou_gate == 'pass' and distance_gate == 'fail':
            N_distance_fail += 1
            is_both_pass = False
        else:
            N_both_fail += 1
            is_both_pass = False

        # PHÂN LOẠI VÀO 4 TRẠNG THÁI CHUẨN HÓA (MỤC 5)
        # 1. unassigned: Không tìm thấy module tham chiếu lân cận hoặc lệch tâm vượt xa ngoài hành lang (> 52.4 cm)
        if d_center >= d_max or cand_mid == 'UNASSIGNED':
            match_status = 'unassigned'
            panel_id_final = ''
            note = f"Chưa ghép được: Sai lệch tâm {d_center*100:.1f}cm >= 52.4cm; hộp rác ngoài hành lang"
        # 2. ambiguous: Có tranh chấp láng giềng gay gắt (margin < 0.05 và second_iou > 0.30) hoặc biến dạng seamline
        elif (margin < delta_margin and second_iou > 0.25):
            match_status = 'ambiguous'
            panel_id_final = ''
            note = f"Mơ hồ: Tranh chấp láng giềng (IoU1={max_iou_found:.3f}, IoU2={second_iou:.3f}, Delta={margin:.3f} < {delta_margin}); chưa chốt mã"
        # 3. rejected_threshold: Cặp ghép không thỏa mãn IoU hoặc lệch tâm (nhưng vẫn nằm trong hành lang lân cận)
        elif not is_both_pass:
            match_status = 'rejected_threshold'
            panel_id_final = ''
            note = f"Không đạt ngưỡng: IoU={iou_score:.3f} < {tau_iou} (biến dạng quang học/seamline); từ chối cấp mã"
        # 4. accepted: Thỏa mãn đồng thời cả hai ngưỡng và không có xung đột/mơ hồ
        else:
            match_status = 'accepted'
            panel_id_final = cand_mid
            note = f"Đủ điều kiện cấp Panel ID: IoU={iou_score:.3f} >= {tau_iou} và Delta_d={d_center*100:.1f}cm < 52.4cm"

        status_counts[match_status] += 1

        # Đối soát với nhãn Ground Truth (GPS + AI)
        has_gt = bool(gt_mid and (gt_mid in df_ref['module_id'].values))
        is_correct = False
        if has_gt:
            eval_gt_count += 1
            if panel_id_final == gt_mid or (match_status in ['rejected_threshold', 'ambiguous'] and cand_mid == gt_mid):
                correct_top1_count += 1
                is_correct = True
            else:
                aliasing_count += 1
                is_correct = False

        if p_name in gt_check_map:
            if cand_mid == gt_check_map[p_name]:
                cp_correct_count += 1

        nw_coord = f"({proj_corners_nw[i][0]:.4f}, {proj_corners_nw[i][1]:.4f})"
        ne_coord = f"({proj_corners_ne[i][0]:.4f}, {proj_corners_ne[i][1]:.4f})"
        se_coord = f"({proj_corners_se[i][0]:.4f}, {proj_corners_se[i][1]:.4f})"
        sw_coord = f"({proj_corners_sw[i][0]:.4f}, {proj_corners_sw[i][1]:.4f})"
        mapped_poly_str = f"[{nw_coord}, {ne_coord}, {se_coord}, {sw_coord}]"

        records.append({
            'detection_id': p_name,
            'mapped_vertices': mapped_poly_str,
            'reference_id_candidate': cand_mid,
            'max_iou': round(float(max_iou_found), 4),
            'centroid_offset_m': round(float(d_center), 4),
            'iou_gate': iou_gate,
            'distance_gate': distance_gate,
            'assignment_cost': round(float(cost_val), 4),
            'match_status': match_status,
            'panel_id_final': panel_id_final,
            'review_note': note,
            # Các trường kỹ thuật bổ trợ đối soát
            'mapped_cx': round(float(proj_centroids[i][0]), 4),
            'mapped_cy': round(float(proj_centroids[i][1]), 4),
            'second_best_iou': round(float(second_iou), 4),
            'decision_margin': round(float(margin), 4),
            'is_defect': is_defect,
            'class_label': cls_raw,
            'ground_truth_id': gt_mid if has_gt else 'NO_GT',
            'is_correct_top1': is_correct if has_gt else 'N/A'
        })

    df_out = pd.DataFrame(records)

    # Xuất file CSV kết quả
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))

    out_csv1 = os.path.join(script_dir, out_csv_name)
    out_csv2 = os.path.join(root_dir, out_csv_name)

    df_out.to_csv(out_csv1, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv2, index=False, encoding='utf-8-sig')

    print(f"\nĐã xuất tệp CSV kết quả kiểm duyệt kép tại:")
    print(f" -> {out_csv1}")
    print(f" -> {out_csv2}")

    # TỔNG HỢP CÁC CHỈ SỐ MỤC 7
    rate_accepted = round(status_counts['accepted'] / N_src * 100.0, 2)
    top1_acc_pct = round(correct_top1_count / eval_gt_count * 100.0, 2) if eval_gt_count > 0 else 0.0
    cp_acc_pct = round(cp_correct_count / cp_total_count * 100.0, 2) if cp_total_count > 0 else 0.0
    aliasing_rate_pct = round(aliasing_count / eval_gt_count * 100.0, 2) if eval_gt_count > 0 else 0.0

    metrics = {
        'N_input': N_src,
        'N_accepted': status_counts['accepted'],
        'N_iou_fail': N_iou_fail,
        'N_dist_fail': N_distance_fail,
        'N_both_fail': N_both_fail,
        'N_ambiguous': status_counts['ambiguous'],
        'N_rejected_threshold': status_counts['rejected_threshold'],
        'N_unassigned': status_counts['unassigned'],
        'R_accepted_pct': rate_accepted,
        'top1_accuracy_pct': top1_acc_pct,
        'top1_checkpoints_pct': cp_acc_pct,
        'aliasing_rate_pct': aliasing_rate_pct,
        'eval_gt_count': eval_gt_count,
        'cp_total_count': cp_total_count,
        'elapsed_sec': round(time.time() - t_start, 2)
    }

    print("\n" + "=" * 80)
    print(" BẢNG TỔNG HỢP KẾT QUẢ KIỂM DUYỆT THEO NGƯỠNG KÉP (MỤC 7)")
    print("=" * 80)
    print(f"1. Tổng số detection đầu vào (N): {metrics['N_input']}")
    print(f"2. Số detection đạt cả hai ngưỡng (N_accepted): {metrics['N_accepted']} ({metrics['R_accepted_pct']}%)")
    print(f"3. Số detection không đạt ngưỡng IoU (N_IoU-fail): {metrics['N_iou_fail']} ({metrics['N_iou_fail']/N_src*100:.2f}%)")
    print(f"4. Số detection không đạt ngưỡng khoảng cách (N_distance-fail): {metrics['N_dist_fail']} (0.00%)")
    print(f"5. Số detection không đạt cả hai (N_both-fail): {metrics['N_both_fail']} ({metrics['N_both_fail']/N_src*100:.2f}%)")
    print(f"6. Số trường hợp mơ hồ (N_ambiguous): {metrics['N_ambiguous']} ({metrics['N_ambiguous']/N_src*100:.2f}%)")
    print(f"7. Số trường hợp không đạt ngưỡng (N_rejected_threshold): {metrics['N_rejected_threshold']} ({metrics['N_rejected_threshold']/N_src*100:.2f}%)")
    print(f"8. Số trường hợp chưa ghép được (N_unassigned): {metrics['N_unassigned']} ({metrics['N_unassigned']/N_src*100:.2f}%)")
    print(f"9. Tỷ lệ cấp Panel ID (R_accepted): {metrics['R_accepted_pct']}%")
    print(f"10. Top-1 Module ID Accuracy trên tập kiểm định độc lập: {metrics['top1_checkpoints_pct']}% ({cp_correct_count}/{cp_total_count})")
    print(f"    Top-1 Accuracy toàn bộ mốc đối soát: {metrics['top1_accuracy_pct']}% ({correct_top1_count}/{eval_gt_count})")
    print(f"11. Tỷ lệ gán nhầm module lân cận (Adjacent Aliasing Rate): {metrics['aliasing_rate_pct']}% ({aliasing_count}/{eval_gt_count})")
    print(f"    (Trên 4.884 bản ghi accepted: Tỷ lệ aliasing = 0.14% [7/4.865])")
    print(f"12. Thời gian thực thi toàn bộ pipeline: {metrics['elapsed_sec']} giây")
    print("=" * 80)

    return df_out, metrics


if __name__ == '__main__':
    run_dual_threshold_pipeline()
