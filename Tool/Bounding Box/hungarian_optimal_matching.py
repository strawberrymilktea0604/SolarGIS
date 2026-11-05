"""
Module: hungarian_optimal_matching.py
Thư mục: Bounding Box
Mục đích:
- Lập trình thuật toán so khớp ma trận tối ưu (Hungarian Algorithm / Bipartite Matching)
  giữa tập Đa giác dự phóng (Poly_proj) từ CSV detection trực ảnh vùng 35m
  (PV_Coordinates_Ortho_Vung_1_20260929_0018.csv) và tập Đa giác danh định (Poly_ref)
  từ mốc tham chiếu GIS QGIS toàn cảnh 85m (bbox_centroid_export.csv).
- Nguyên tắc thực hiện:
  + CSV là trung tâm dữ liệu đầu vào và kết xuất đầu ra.
  + Tuyệt đối không dùng file JSON ortho, chỉ dùng PV_Coordinates_Ortho_Vung_1_20260929_0018.csv
    làm nguồn ánh xạ và bbox_centroid_export.csv làm mốc đo đạc.
  + Áp dụng GPS + AI Matching để khởi tạo các cặp điểm tương ứng, từ đó ước lượng ma trận
    Homography DLT Hartley (8 bậc tự do) nắn chuyển 4 góc OBB lên hệ phẳng UTM Zone 49N.
  + Xây dựng ma trận chi phí C đa thành phần: IoU giao thoa, sai lệch tâm chuẩn hóa theo d_max (52.4 cm),
    và sai lệch góc định hướng delta_theta.
  + Chạy thuật toán Hungarian (linear_sum_assignment) tìm phương án ghép 1-1 tối ưu toàn cục.
  + Thiết lập cơ chế kiểm định đa tầng: ngưỡng kép (IoU >= 0.50, d <= 52.4 cm) và phân xử
    ca mơ hồ theo Decision Margin (delta_margin = IoU_1 - IoU_2).
  + Tuyệt đối không gán cứng giá trị; toàn bộ chỉ số được tính toán trực tiếp từ dữ liệu.
- Xuất file kết quả:
  + Bounding Box/PV_Hungarian_Optimal_Matching_Evaluation.csv
  + PV_Hungarian_Optimal_Matching_Evaluation.csv (thư mục gốc)
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

# Thêm đường dẫn Bounding Box để import các hàm chuẩn hoá nếu có
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

# Tham số mặc định của hàm chi phí và kiểm định trắc địa
WEIGHT_IOU = 0.60
WEIGHT_DIST = 0.30
WEIGHT_ANGLE = 0.10
D_MAX_METERS = 0.524       # 52.4 cm (nửa chiều rộng module 1.048m)
THETA_MAX_DEG = 45.0      # Ngưỡng chuẩn hóa sai lệch góc xoay
TAU_IOU = 0.50            # Ngưỡng chấp nhận IoU tối thiểu
DELTA_MARGIN = 0.05       # Ngưỡng phân định mơ hồ giữa 2 ứng viên dẫn đầu
SEARCH_RADIUS_M = 2.50    # Bán kính tìm kiếm ứng viên quanh tâm OBB
PENALTY_COST = 50.0       # Chi phí phạt cho các cặp không hợp lệ / ngoài bán kính


def parse_polygon_from_row(row, corner_cols):
    """Trích xuất Polygon Shapely từ 4 đỉnh định dạng tuple chuỗi"""
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
    """Tính góc định hướng trục dài của module theo độ (0 - 180 độ)"""
    dx = pt_end[0] - pt_start[0]
    dy = pt_end[1] - pt_start[1]
    deg = math.degrees(math.atan2(dy, dx)) % 180.0
    return deg


def run_hungarian_pipeline(
    src_csv_name='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_name='bbox_centroid_export.csv',
    out_csv_name='PV_Hungarian_Optimal_Matching_Evaluation.csv',
    tau_iou=TAU_IOU,
    d_max=D_MAX_METERS,
    delta_margin=DELTA_MARGIN
):
    print("=" * 80)
    print(" LẬP TRÌNH THUẬT TOÁN SO KHỚP MA TRẬN TỐI ƯU (HUNGARIAN ALGORITHM)")
    print(" XÂY DỰNG THUẬT TOÁN SO KHỚP CẶP GIỮA ĐA GIÁC DỰ PHÓNG VÀ ĐA GIÁC DANH ĐỊNH")
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
    print(f"   -> Tổng số detection nguồn: N = {N_src}")
    print(f"   -> Tổng số module danh định toàn nhà máy: M_total = {M_ref_total}")

    # BƯỚC 1: GHÉP CẶP GPS + AI MATCHING VÀ ƯỚC LƯỢNG MA TRẬN HOMOGRAPHY DLT HARTLEY
    print("\n--- BƯỚC 1: Ghép cặp GPS + AI Matching & Ánh xạ không gian ---")
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

    # Ước lượng ma trận Homography DLT Hartley
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
    print(f"   -> Đã ước lượng ma trận Homography DLT Hartley (RANSAC Inliers = {int(np.sum(inlier_mask))}/{n_fit})")

    # BƯỚC 2: TÍNH TOÁN TỌA ĐỘ VÀ ĐA GIÁC DỰ PHÓNG (Poly_proj) CHO 100% DETECTION
    print("\n--- BƯỚC 2: Tạo lập tập Đa giác dự phóng (Poly_proj) ---")
    corner_cols_src = ['BBox_NW_Pixel', 'BBox_NE_Pixel', 'BBox_SE_Pixel', 'BBox_SW_Pixel']

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
        ang = calculate_orientation_angle(nw, ne)
        proj_angles.append(ang)

    proj_centroids = np.array(proj_centroids, dtype=np.float64)
    print(f"   -> Đã hoàn thành tính toán hình học 2.5D cho {len(proj_polys)} đa giác Poly_proj.")

    # BƯỚC 3: LỌC TẬP ĐA GIÁC DANH ĐỊNH THAM CHIẾU (Poly_ref) BẰNG KDTREE
    print("\n--- BƯỚC 3: Tạo lập tập Đa giác danh định tham chiếu (Poly_ref) ---")
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values.astype(np.float64)
    ref_tree = cKDTree(ref_coords)

    # Tìm ứng viên lân cận trong bán kính SEARCH_RADIUS_M
    cand_indices_per_det = ref_tree.query_ball_point(proj_centroids, r=SEARCH_RADIUS_M)
    unique_cand_indices = sorted(list(set([idx for clist in cand_indices_per_det for idx in clist])))
    ref_cand_map = {orig_idx: cand_i for cand_i, orig_idx in enumerate(unique_cand_indices)}
    df_cand_ref = df_ref.iloc[unique_cand_indices].copy().reset_index(drop=True)

    M_cand = len(df_cand_ref)
    print(f"   -> Số module danh định tham chiếu trong bán kính khảo sát: M_cand = {M_cand}")

    # Xây dựng Polygon và góc định hướng cho tập Poly_ref
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
        ang = calculate_orientation_angle(bl, br)
        ref_angles.append(ang)

    ref_centroids = np.array(ref_centroids, dtype=np.float64)
    print(f"   -> Đã hoàn thành dựng {len(ref_polys)} đa giác Poly_ref từ mốc QGIS.")

    # BƯỚC 4: XÂY DỰNG MA TRẬN CHI PHÍ GHÉP CẶP C [N x M_cand]
    print("\n--- BƯỚC 4: Xây dựng Ma trận chi phí ghép cặp C ---")
    t_c0 = time.time()
    C = np.full((N_src, M_cand), PENALTY_COST, dtype=np.float64)

    # Lưu trữ chi tiết các ứng viên cho từng detection để phục vụ tính Margin và Second Best
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

            # 1. Chi phí IoU
            inter = p_poly.intersection(r_poly).area
            union = p_poly.union(r_poly).area
            iou = float(inter / union) if union > 1e-9 else 0.0

            # 2. Sai lệch tâm
            d_center = math.hypot(p_cx - r_cx, p_cy - r_cy)

            # 3. Sai lệch góc định hướng
            diff_ang = abs(p_ang - r_ang)
            diff_ang = min(diff_ang, 180.0 - diff_ang)

            # 4. Hàm chi phí tổng hợp
            c_val = (
                WEIGHT_IOU * (1.0 - iou) +
                WEIGHT_DIST * (d_center / d_max) +
                WEIGHT_ANGLE * (diff_ang / THETA_MAX_DEG)
            )

            C[i, cj] = c_val
            det_candidates_data[i].append({
                'cand_col': cj,
                'orig_ref_idx': orig_j,
                'module_id': df_cand_ref.loc[cj, 'module_id'],
                'iou': iou,
                'd_center': d_center,
                'diff_ang': diff_ang,
                'cost': c_val
            })

    t_c1 = time.time()
    print(f"   -> Ma trận chi phí kích thước ({N_src} x {M_cand}) được xây dựng trong {t_c1 - t_c0:.2f} giây.")

    # BƯỚC 5: GIẢI BÀI TOÁN PHÂN CÔNG TỐI ƯU BẰNG HUNGARIAN ALGORITHM
    print("\n--- BƯỚC 5: Giải thuật toán Hungarian tối ưu hóa toàn cục ---")
    t_h0 = time.time()
    row_ind, col_ind = linear_sum_assignment(C)
    t_h1 = time.time()
    print(f"   -> Thuật toán Hungarian hoàn thành tối ưu trong {t_h1 - t_h0:.3f} giây.")

    assignment_map = {r: c for r, c in zip(row_ind, col_ind)}

    # BƯỚC 6: KIỂM DUYỆT THEO TIÊU CHÍ TRẮC ĐỊA & PHÂN XỬ CA MƠ HỒ
    print("\n--- BƯỚC 6: Thiết lập ngưỡng kiểm duyệt & xử lý ca mơ hồ ---")
    results = []

    matched_count = 0
    ambiguous_count = 0
    unassigned_count = 0

    ious_accepted = []
    dists_accepted = []
    angles_accepted = []

    correct_top1_count = 0
    aliasing_count = 0
    eval_gt_count = 0

    # Đối chiếu độc lập trên 30% Check Points
    gt_check_map = {}
    for idx_cp, row_cp in matched_pairs.iterrows():
        if is_check_point[idx_cp]:
            gt_check_map[row_cp['Point_Name']] = row_cp['match_id']

    cp_correct_count = 0
    cp_total_count = len(gt_check_map)

    for i in range(N_src):
        p_name = df_src.loc[i, 'Point_Name']
        gt_mid = df_src.loc[i, 'match_id']
        cls_raw = str(df_src.loc[i, 'Class']).strip()
        is_defect = 'CÓ' if cls_raw != 'Unclassified' else 'KHÔNG'

        cj = assignment_map[i]
        c_cost = float(C[i, cj])

        # Phân tích danh sách ứng viên đã xếp thứ tự theo IoU giảm dần
        cand_list_sorted = sorted(det_candidates_data[i], key=lambda x: x['iou'], reverse=True)

        if len(cand_list_sorted) > 0:
            best_iou_cand = cand_list_sorted[0]
            first_iou = best_iou_cand['iou']
        else:
            first_iou = 0.0

        if len(cand_list_sorted) > 1:
            second_cand = cand_list_sorted[1]
            second_iou = second_cand['iou']
            second_id = second_cand['module_id']
        else:
            second_cand = None
            second_iou = 0.0
            second_id = 'NONE'

        margin = first_iou - second_iou

        # Thông số của cặp ghép Hungarian
        hungarian_cand = [c for c in cand_list_sorted if c['cand_col'] == cj]
        if len(hungarian_cand) > 0:
            h_info = hungarian_cand[0]
            cand_mod_id = h_info['module_id']
            iou_score = h_info['iou']
            d_center = h_info['d_center']
            d_angle = h_info['diff_ang']
            orig_ref_idx = h_info['orig_ref_idx']
            ref_cx = float(df_cand_ref.loc[cj, 'centroid_x'])
            ref_cy = float(df_cand_ref.loc[cj, 'centroid_y'])
        else:
            cand_mod_id = 'UNASSIGNED'
            iou_score = 0.0
            d_center = 999.0
            d_angle = 0.0
            orig_ref_idx = -1
            ref_cx = np.nan
            ref_cy = np.nan

        # Tiêu chuẩn kiểm định (Acceptance & Ambiguity Rules)
        # 1. Unassigned: lệch tâm vượt ranh giới an toàn 52.4 cm hoặc chi phí phạt (không có module lân cận)
        if c_cost >= PENALTY_COST or d_center > d_max:
            status = 'unassigned'
            unassigned_count += 1
            cand_mod_id = 'UNASSIGNED'
            if d_center > d_max and d_center < 900:
                note = f"Loại bỏ ngoài hành lang: Lệch tâm {d_center*100:.1f}cm > 52.4cm (vượt Decision Margin)"
            else:
                note = "Không có module tham chiếu trong bán kính khảo sát 2.5m"
        # 2. Ambiguous: IoU dưới ngưỡng 0.50 hoặc cạnh tranh gay gắt giữa 2 module láng giềng (margin < delta)
        elif iou_score < tau_iou or margin < delta_margin:
            status = 'ambiguous'
            ambiguous_count += 1
            if margin < delta_margin and second_iou > 0.30:
                note = f"Ca mơ hồ (Tranh chấp láng giềng): IoU1={first_iou:.3f}, IoU2={second_iou:.3f}, Delta={margin:.3f} < {delta_margin}"
            else:
                note = f"Ca mơ hồ (Biến dạng/seamline): IoU={iou_score:.3f} < {tau_iou}; giữ nguyên chờ phân xử"
        # 3. Matched: Thỏa mãn đồng thời toàn bộ ràng buộc hình học
        else:
            status = 'matched'
            matched_count += 1
            note = f"Khớp tối ưu 1-1: IoU={iou_score:.3f}, Lệch tâm={d_center*100:.1f}cm, Delta_margin={margin:.3f}"
            ious_accepted.append(iou_score)
            dists_accepted.append(d_center)
            angles_accepted.append(d_angle)

        # Kiểm chứng với nhãn Ground Truth (GPS + AI)
        has_gt = bool(gt_mid and (gt_mid in df_ref['module_id'].values))
        is_correct = False
        if has_gt:
            eval_gt_count += 1
            if cand_mod_id == gt_mid:
                correct_top1_count += 1
                is_correct = True
            else:
                aliasing_count += 1
                is_correct = False

        if p_name in gt_check_map:
            if cand_mod_id == gt_check_map[p_name]:
                cp_correct_count += 1

        nw_coord = f"({proj_corners_nw[i][0]:.4f}, {proj_corners_nw[i][1]:.4f})"
        ne_coord = f"({proj_corners_ne[i][0]:.4f}, {proj_corners_ne[i][1]:.4f})"
        se_coord = f"({proj_corners_se[i][0]:.4f}, {proj_corners_se[i][1]:.4f})"
        sw_coord = f"({proj_corners_sw[i][0]:.4f}, {proj_corners_sw[i][1]:.4f})"
        mapped_poly_str = f"[{nw_coord}, {ne_coord}, {se_coord}, {sw_coord}]"

        results.append({
            'detection_id': p_name,
            'mapped_cx': round(float(proj_centroids[i][0]), 4),
            'mapped_cy': round(float(proj_centroids[i][1]), 4),
            'mapped_vertices': mapped_poly_str,
            'reference_id_candidate': cand_mod_id,
            'ref_centroid_x': round(ref_cx, 4) if pd.notna(ref_cx) else '',
            'ref_centroid_y': round(ref_cy, 4) if pd.notna(ref_cy) else '',
            'iou_score': round(float(iou_score), 4),
            'center_distance': round(float(d_center), 4),
            'angle_difference': round(float(d_angle), 2),
            'assignment_cost': round(float(c_cost), 4),
            'second_best_ref_id': second_id,
            'second_best_iou': round(float(second_iou), 4),
            'decision_margin': round(float(margin), 4),
            'match_status': status,
            'ground_truth_id': gt_mid if has_gt else 'NO_GT',
            'is_correct_top1': is_correct if has_gt else 'N/A',
            'is_defect': is_defect,
            'class_label': cls_raw,
            'review_note': note
        })

    df_out = pd.DataFrame(results)

    # Xuất file CSV kết quả
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))

    out_csv_path1 = os.path.join(script_dir, out_csv_name)
    out_csv_path2 = os.path.join(root_dir, out_csv_name)

    df_out.to_csv(out_csv_path1, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_path2, index=False, encoding='utf-8-sig')
    print(f"\nĐã xuất tệp CSV kết quả tại:")
    print(f" -> {out_csv_path1}")
    print(f" -> {out_csv_path2}")

    # BƯỚC 7: TỔNG HỢP VÀ THỐNG KÊ CÁC CHỈ SỐ KHOA HỌC
    ious_arr = np.array(ious_accepted, dtype=np.float64)
    dists_cm = np.array(dists_accepted, dtype=np.float64) * 100.0  # chuyển sang cm

    metrics = {
        'N_total': N_src,
        'M_total': M_ref_total,
        'M_candidate': M_cand,
        'N_matched': matched_count,
        'pct_matched': round(matched_count / N_src * 100.0, 2),
        'N_ambiguous': ambiguous_count,
        'pct_ambiguous': round(ambiguous_count / N_src * 100.0, 2),
        'N_unassigned': unassigned_count,
        'pct_unassigned': round(unassigned_count / N_src * 100.0, 2),
        'mean_iou': round(float(np.mean(ious_arr)), 4) if len(ious_arr) > 0 else 0.0,
        'median_iou': round(float(np.median(ious_arr)), 4) if len(ious_arr) > 0 else 0.0,
        'min_iou': round(float(np.min(ious_arr)), 4) if len(ious_arr) > 0 else 0.0,
        'max_iou': round(float(np.max(ious_arr)), 4) if len(ious_arr) > 0 else 0.0,
        'mean_dist_cm': round(float(np.mean(dists_cm)), 2) if len(dists_cm) > 0 else 0.0,
        'median_dist_cm': round(float(np.median(dists_cm)), 2) if len(dists_cm) > 0 else 0.0,
        'p95_dist_cm': round(float(np.percentile(dists_cm, 95)), 2) if len(dists_cm) > 0 else 0.0,
        'max_dist_cm': round(float(np.max(dists_cm)), 2) if len(dists_cm) > 0 else 0.0,
        'top1_accuracy_all_pct': round(correct_top1_count / eval_gt_count * 100.0, 2) if eval_gt_count > 0 else 0.0,
        'aliasing_rate_pct': round(aliasing_count / eval_gt_count * 100.0, 2) if eval_gt_count > 0 else 0.0,
        'top1_accuracy_checkpoints_pct': round(cp_correct_count / cp_total_count * 100.0, 2) if cp_total_count > 0 else 0.0,
        'eval_gt_count': eval_gt_count,
        'cp_total_count': cp_total_count,
        'elapsed_sec': round(time.time() - t_start, 2)
    }

    print("\n" + "=" * 80)
    print(" BẢNG CHỈ SỐ KẾT QUẢ ĐO ĐẠC THỰC TẾ CỦA THUẬT TOÁN HUNGARIAN (MỤC 7)")
    print("=" * 80)
    print(f"1. Tổng số detection đầu vào (N): {metrics['N_total']}")
    print(f"2. Tổng số module tham chiếu toàn nhà máy (M_total): {metrics['M_total']}")
    print(f"   Tổng số module tham chiếu trong pool ứng viên (M_candidate): {metrics['M_candidate']}")
    print(f"3. Số cặp được chấp nhận (N_matched): {metrics['N_matched']} ({metrics['pct_matched']}%)")
    print(f"4. Số detection mơ hồ (N_ambiguous): {metrics['N_ambiguous']} ({metrics['pct_ambiguous']}%)")
    print(f"5. Số detection chưa ghép được (N_unassigned): {metrics['N_unassigned']} ({metrics['pct_unassigned']}%)")
    print(f"6. IoU trung bình của các cặp được chấp nhận: {metrics['mean_iou']} (Trung vị: {metrics['median_iou']})")
    print(f"7. Sai lệch tâm trung bình: {metrics['mean_dist_cm']} cm | Trung vị: {metrics['median_dist_cm']} cm | P95: {metrics['p95_dist_cm']} cm | Cực đại: {metrics['max_dist_cm']} cm")
    print(f"8. Tỷ lệ gán đúng Panel ID (Top-1 Accuracy trên 5.071 mốc đối chiếu): {correct_top1_count}/{eval_gt_count} ({metrics['top1_accuracy_all_pct']}%)")
    print(f"   Độ chính xác trên tập Independent Check Points (30%): {cp_correct_count}/{cp_total_count} ({metrics['top1_accuracy_checkpoints_pct']}%)")
    print(f"9. Tỷ lệ ghép nhầm module lân cận (Aliasing Rate): {aliasing_count}/{eval_gt_count} ({metrics['aliasing_rate_pct']}%)")
    print(f"10. Thời gian thực thi toàn bộ pipeline: {metrics['elapsed_sec']} giây")
    print("=" * 80)

    return df_out, metrics


if __name__ == '__main__':
    run_hungarian_pipeline()
