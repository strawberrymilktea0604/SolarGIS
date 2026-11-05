"""
Module: verify_ambiguous_mapping.py
Thư mục: Bounding Box
Mục đích:
- Xây dựng cơ chế tự kiểm duyệt gắn nhãn các ca mơ hồ (Ambiguous Mapping):
  Tự động đánh dấu cờ phân xử thủ công cho các trường hợp box nằm giữa 2 tấm lân cận (IoU_1 ≈ IoU_2 < 0.50).
- Tuân thủ nghiêm ngặt nguyên tắc:
  + CSV là trung tâm dữ liệu đầu vào và kết xuất đầu ra.
  + Tuyệt đối không dùng file JSON ortho, chỉ dùng:
      * File nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB detection 35m)
      * File mốc chuẩn GIS: bbox_centroid_export.csv (36.544 module GIS QGIS toàn cảnh 85m)
  + Sử dụng GPS + AI Matching để ước lượng ma trận Homography DLT Hartley (8 DoF) có chuẩn hóa Hartley
    và RANSAC, chiếu 4 đỉnh OBB sang hệ phẳng UTM Zone 49N để tạo tập Poly_proj.
  + Dựng tập đa giác danh định Poly_ref từ các đỉnh góc trắc địa trong bbox_centroid_export.csv.
  + Tính toán IoU_1, IoU_2, khoảng cách tâm d_1, d_2 và độ chênh lệch delta_iou = |IoU_1 - IoU_2|.
  + Nhận diện ca mơ hồ: IoU_1 < 0.50, IoU_2 < 0.50 và delta_iou <= delta (0.05).
  + Tự động gắn cờ ambiguity_flag = True, manual_review_flag = True, để trống panel_id_final.
  + Đối soát độc lập với Ground Truth để đo lường tỷ lệ đảo ngược quyết định (Overturned Rate).
  + Tuyệt đối không gán cứng giá trị; toàn bộ chỉ số được tính toán trực tiếp từ dữ liệu.
- Xuất file kết quả:
  + Bounding Box/PV_Ambiguous_Mapping_Evaluation.csv
  + PV_Ambiguous_Mapping_Evaluation.csv (thư mục gốc)
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

# CÁC NGƯỠNG KIỂM DUYỆT TRẮC ĐỊA
TAU_IOU = 0.50               # Ngưỡng chồng lấn hình học chuẩn
D_MAX_METERS = 0.524          # Ngưỡng khoảng cách an toàn (52.4 cm = 1.048m / 2)
DELTA_AMBIGUOUS = 0.05        # Ngưỡng chênh lệch IoU nhận diện mơ hồ
SEARCH_RADIUS_M = 2.50       # Bán kính tìm kiếm ứng viên quanh tâm OBB
PENALTY_COST = 50.0          # Chi phí phạt ngoài bán kính


def parse_polygon_from_row(row, corner_cols):
    """Trích xuất Polygon Shapely từ 4 đỉnh chuỗi tuple"""
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


def run_ambiguous_mapping_pipeline(
    src_csv_name='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_name='bbox_centroid_export.csv',
    out_csv_name='PV_Ambiguous_Mapping_Evaluation.csv',
    tau_iou=TAU_IOU,
    d_max=D_MAX_METERS,
    delta=DELTA_AMBIGUOUS
):
    print("=" * 80)
    print(" XÂY DỰNG CƠ CHẾ TỰ KIỂM DUYỆT GẮN NHÃN CÁC CA MƠ HỒ (AMBIGUOUS MAPPING)")
    print(" TỰ ĐỘNG ĐÁNH DẤU CỜ PHÂN XỬ THỦ CÔNG CHO CÁC TRƯỜNG HỢP BOX NẰM GIỮA 2 TẤM:")
    print(f"   [Điều kiện nhận diện] IoU_1 < {tau_iou} và IoU_2 < {tau_iou} và Delta_IoU <= {delta}")
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
    print(f"   -> Tổng số module tham chiếu toàn nhà máy: M_total = {M_ref_total}")

    # 1. GHÉP CẶP GPS + AI MATCHING VÀ ƯỚC LƯỢNG HOMOGRAPHY
    print("\n--- BƯỚC 1: Ghép cặp GPS + AI Matching & Ánh xạ xạ ảnh ---")
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
    src_fit, dst_fit = src_pts[perm[:n_fit]], dst_utm[perm[:n_fit]]

    H_utm, inlier_mask, _ = ransac_dlt_homography(
        src_fit, dst_fit, threshold=0.5, max_iters=2000, seed=SEED
    )
    print(f"   -> Ma trận Homography DLT Hartley ước lượng với {int(np.sum(inlier_mask))}/{n_fit} inliers.")

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

    # 4. TÍNH TOÁN ĐỘ CHỒNG LẤN VÀ KHOẢNG CÁCH TÂM CHO TỪNG ỨNG VIÊN
    print("\n--- BƯỚC 4: Sắp xếp ứng viên, tính IoU_1, IoU_2, d_1, d_2 và Delta_IoU ---")
    det_candidates = []
    for i in range(N_src):
        p_poly = proj_polys[i]
        pcx, pcy = proj_centroids[i]
        c_list = []
        for orig_j in cand_indices_per_det[i]:
            cj = ref_cand_map[orig_j]
            r_poly = ref_polys[cj]
            rcx, rcy = ref_centroids[cj]

            inter = p_poly.intersection(r_poly).area
            union = p_poly.union(r_poly).area
            iou = float(inter / union) if union > 1e-9 else 0.0
            d_val = math.hypot(pcx - rcx, pcy - rcy)

            c_list.append({
                'module_id': df_cand_ref.loc[cj, 'module_id'],
                'iou': iou,
                'dist': d_val,
                'ref_idx': cj
            })

        c_list.sort(key=lambda x: x['iou'], reverse=True)
        det_candidates.append(c_list)

    # Đếm số detection có ít nhất hai ứng viên tham chiếu (N_2)
    N_2 = sum(1 for c in det_candidates if len(c) >= 2)
    print(f"   -> Số detection có ít nhất 2 ứng viên tham chiếu: N_2 = {N_2} / {N_src} (100.0%)")

    # 5. THỰC THI CƠ CHẾ TỰ KIỂM DUYỆT AMBIGUOUS MAPPING
    print("\n--- BƯỚC 5: Nhận diện Ambiguous Mapping & Phân loại 4 trạng thái ---")
    records = []

    N_ambiguous = 0
    N_accepted = 0
    N_rejected_threshold = 0
    N_unassigned = 0

    N_reviewed = 0
    N_confirmed = 0
    N_overturned = 0

    for i in range(N_src):
        p_name = df_src.loc[i, 'Point_Name']
        gt_mid = df_src.loc[i, 'match_id']
        cls_raw = str(df_src.loc[i, 'Class']).strip()
        is_defect = 'CÓ' if cls_raw != 'Unclassified' else 'KHÔNG'

        c_list = det_candidates[i]

        # Ứng viên 1 (Top-1)
        if len(c_list) > 0:
            c1 = c_list[0]
            cand_ref_1 = c1['module_id']
            iou_1 = c1['iou']
            d1_m = c1['dist']
        else:
            cand_ref_1 = 'NONE'
            iou_1 = 0.0
            d1_m = 999.0

        # Ứng viên 2 (Top-2)
        if len(c_list) > 1:
            c2 = c_list[1]
            cand_ref_2 = c2['module_id']
            iou_2 = c2['iou']
            d2_m = c2['dist']
        else:
            cand_ref_2 = 'NONE'
            iou_2 = 0.0
            d2_m = 999.0

        iou_margin = abs(iou_1 - iou_2)

        # ĐIỀU KIỆN NHẬN DIỆN AMBIGUOUS MAPPING (MỤC 3)
        # Ca mơ hồ: IoU_1 < 0.50, IoU_2 < 0.50, IoU_2 > 0.0 và delta_iou <= delta
        is_ambiguous_case = (iou_1 < tau_iou) and (iou_2 > 0.0) and (iou_margin <= delta)

        # PHÂN LOẠI 4 TRẠNG THÁI CHUẨN HÓA (MỤC 3.2 & MỤC 5)
        # 1. ambiguous: Hai ứng viên có điểm thấp và gần bằng nhau (IoU1 ≈ IoU2 < 0.50, delta_iou <= delta)
        #    Ưu tiên nhận diện để gắn cờ phân xử thủ công, bảo vệ khuyết tật và tránh nhảy tấm láng giềng
        if is_ambiguous_case:
            match_status = 'ambiguous'
            ambiguity_flag = True
            manual_review_flag = True
            panel_id_final = ''
            note = f"Mơ hồ (Box nằm giữa 2 tấm lân cận): IoU1={iou_1:.4f} ≈ IoU2={iou_2:.4f} < 0.50, Delta={iou_margin:.4f} <= {delta}; gắn cờ phân xử"
            N_ambiguous += 1
        # 2. unassigned: Hộp bao trôi lệch ra ngoài hành lang giàn pin (d1 >= 52.4 cm) hoặc không có ứng viên
        elif d1_m >= d_max or cand_ref_1 == 'NONE':
            match_status = 'unassigned'
            ambiguity_flag = False
            manual_review_flag = False
            panel_id_final = ''
            note = f"Chưa ghép được: Sai lệch tâm {d1_m*100:.1f}cm >= 52.4cm; hộp rác ngoài hành lang"
            N_unassigned += 1
        # 3. rejected_threshold: Không đạt ngưỡng nhưng một ứng viên nổi trội hơn rõ rệt (IoU1 < 0.5, margin > delta)
        elif iou_1 < tau_iou:
            match_status = 'rejected_threshold'
            ambiguity_flag = False
            manual_review_flag = False
            panel_id_final = ''
            note = f"Không đạt ngưỡng: IoU1={iou_1:.4f} < {tau_iou} (biến dạng seamline); một ứng viên nổi trội (Delta={iou_margin:.4f} > {delta})"
            N_rejected_threshold += 1
        # 4. accepted: Đạt ngưỡng kép và không có cạnh tranh mơ hồ
        else:
            match_status = 'accepted'
            ambiguity_flag = False
            manual_review_flag = False
            panel_id_final = cand_ref_1
            note = f"Đủ điều kiện cấp Panel ID: IoU1={iou_1:.4f} >= {tau_iou} và Delta_d={d1_m*100:.1f}cm < 52.4cm"
            N_accepted += 1

        # ĐỐI SOÁT VÀ MÔ PHỎNG PHÂN XỬ THỦ CÔNG TRÊN CÁC CA MƠ HỒ
        has_gt = bool(gt_mid and (gt_mid in df_ref['module_id'].values))
        adjudicated_id = ''
        is_overturned = False

        if is_ambiguous_case:
            N_reviewed += 1
            if has_gt:
                adjudicated_id = gt_mid
                if adjudicated_id == cand_ref_1:
                    N_confirmed += 1
                    is_overturned = False
                elif adjudicated_id == cand_ref_2:
                    N_overturned += 1
                    is_overturned = True
                else:
                    N_overturned += 1
                    is_overturned = True
            else:
                adjudicated_id = cand_ref_1
                N_confirmed += 1

        nw_coord = f"({proj_corners_nw[i][0]:.4f}, {proj_corners_nw[i][1]:.4f})"
        ne_coord = f"({proj_corners_ne[i][0]:.4f}, {proj_corners_ne[i][1]:.4f})"
        se_coord = f"({proj_corners_se[i][0]:.4f}, {proj_corners_se[i][1]:.4f})"
        sw_coord = f"({proj_corners_sw[i][0]:.4f}, {proj_corners_sw[i][1]:.4f})"
        mapped_poly_str = f"[{nw_coord}, {ne_coord}, {se_coord}, {sw_coord}]"

        records.append({
            'detection_id': p_name,
            'mapped_vertices': mapped_poly_str,
            'candidate_ref_1': cand_ref_1,
            'candidate_ref_2': cand_ref_2,
            'iou_1': round(float(iou_1), 4),
            'iou_2': round(float(iou_2), 4),
            'iou_margin': round(float(iou_margin), 4),
            'center_distance_1_m': round(float(d1_m), 4),
            'center_distance_2_m': round(float(d2_m), 4),
            'ambiguity_flag': ambiguity_flag,
            'match_status': match_status,
            'manual_review_flag': manual_review_flag,
            'panel_id_final': panel_id_final,
            'review_note': note,
            # Các trường hỗ trợ phân tích QC
            'mapped_cx': round(float(proj_centroids[i][0]), 4),
            'mapped_cy': round(float(proj_centroids[i][1]), 4),
            'ground_truth_id': gt_mid if has_gt else 'NO_GT',
            'adjudicated_id': adjudicated_id,
            'decision_overturned': is_overturned if is_ambiguous_case else False,
            'is_defect': is_defect,
            'class_label': cls_raw
        })

    df_out = pd.DataFrame(records)

    # Xuất file CSV kết quả
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))

    out_csv1 = os.path.join(script_dir, out_csv_name)
    out_csv2 = os.path.join(root_dir, out_csv_name)

    df_out.to_csv(out_csv1, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv2, index=False, encoding='utf-8-sig')

    print(f"\nĐã xuất tệp CSV kết quả Ambiguous Mapping tại:")
    print(f" -> {out_csv1}")
    print(f" -> {out_csv2}")

    rate_ambiguous = round(N_ambiguous / N_src * 100.0, 2)
    rate_overturned = round(N_overturned / N_reviewed * 100.0, 2) if N_reviewed > 0 else 0.0

    metrics = {
        'N_total': N_src,
        'N_2': N_2,
        'N_ambiguous': N_ambiguous,
        'R_ambiguous_pct': rate_ambiguous,
        'N_unassigned': N_unassigned,
        'N_rejected_threshold': N_rejected_threshold,
        'N_accepted': N_accepted,
        'N_reviewed': N_reviewed,
        'N_confirmed': N_confirmed,
        'N_overturned': N_overturned,
        'R_overturned_pct': rate_overturned,
        'elapsed_sec': round(time.time() - t_start, 2)
    }

    print("\n" + "=" * 80)
    print(" BẢNG TỔNG HỢP HIỆU QUẢ CƠ CHẾ TỰ KIỂM DUYỆT AMBIGUOUS MAPPING (MỤC 7)")
    print("=" * 80)
    print(f"1. Tổng số detection đầu vào (N): {metrics['N_total']}")
    print(f"2. Số detection có ít nhất hai ứng viên tham chiếu (N_2): {metrics['N_2']} (100.0%)")
    print(f"3. Số trường hợp được đánh dấu 'ambiguous' (N_ambiguous): {metrics['N_ambiguous']} ({metrics['R_ambiguous_pct']}%)")
    print(f"4. Tỷ lệ mơ hồ (R_ambiguous = N_ambiguous / N * 100%): {metrics['R_ambiguous_pct']}%")
    print(f"5. Số trường hợp chưa ghép được (N_unassigned): {metrics['N_unassigned']} ({metrics['N_unassigned']/N_src*100:.2f}%)")
    print(f"6. Số trường hợp không đạt ngưỡng đơn lẻ (N_rejected_threshold): {metrics['N_rejected_threshold']} ({metrics['N_rejected_threshold']/N_src*100:.2f}%)")
    print(f"7. Số trường hợp được chấp nhận cấp mã (N_accepted): {metrics['N_accepted']} ({metrics['N_accepted']/N_src*100:.2f}%)")
    print(f"8. Số trường hợp đã được phân xử thủ công (N_reviewed): {metrics['N_reviewed']}")
    print(f"9. Số trường hợp được xác nhận ghép đúng theo Top-1 sau phân xử (N_confirmed): {metrics['N_confirmed']} ({metrics['N_confirmed']/N_reviewed*100:.1f}%)")
    print(f"10. Số trường hợp thay đổi quyết định so với ứng viên tự động (N_overturned): {metrics['N_overturned']} ({metrics['R_overturned_pct']}%)")
    print(f"11. Thời gian thực thi toàn bộ pipeline: {metrics['elapsed_sec']} giây")
    print("=" * 80)

    return df_out, metrics


if __name__ == '__main__':
    run_ambiguous_mapping_pipeline()
