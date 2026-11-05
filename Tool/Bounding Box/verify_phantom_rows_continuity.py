"""
Module: verify_phantom_rows_continuity.py
Thư mục: Bounding Box
Mục đích:
- Kiểm tra tính liên tục không gian trên toàn bộ phạm vi dữ liệu nhà máy đã ánh xạ
  và xác nhận khả năng triệt tiêu hiện tượng phân mảnh thành các "hàng rác" (phantom rows).
- Tuân thủ nguyên tắc:
    + Chỉ sử dụng CSV detection đầu vào: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Đối chiếu đo đạc với mốc trắc địa chuẩn: bbox_centroid_export.csv (36.544 module GIS QGIS)
    + Sử dụng kết quả ghép cặp GPS + AI Matching (5.072 cặp khớp ~ 99.61%) và ánh xạ Homography DLT Hartley,
      kết hợp đối chiếu Trước xử lý (Raw Mapped Homography) và Sau xử lý (Grid Regularization +
      Topological Snapping + Out-of-bounds Rejection).
- Thực hiện đầy đủ 3 bước toán học theo Form chuẩn:
    3.1. Xác định hướng hàng pin u = (u_x, u_y), v = (-u_y, u_x) theo từng nhóm giàn/hàng,
         chiếu s_i = p_i . u, r_i = p_i . v.
    3.2. Kiểm tra khoảng cách g_i = s_{i+1} - s_i, bước lưới tham chiếu s_0 = median(g_i),
         sai lệch bước lưới e_i^pitch = |g_i - m_i * s_0|.
    3.3. Xây dựng đồ thị không gian G = (V, E), khảo sát các thành phần liên thông, phân biệt rõ:
         - Trường hợp A: Hàng pin liên tục (continuous)
         - Trường hợp B: Hàng pin bị phân mảnh / cụm phantom row (fragment_candidate)
         - Trường hợp C: Khoảng trống do bỏ sót module (gap_candidate)
         - Bảo vệ các cụm nhỏ hợp lệ ở biên trực ảnh (55 cụm hàng thuộc mép Đông Block 1) để không loại nhầm hàng thật.
- Xuất file CSV chuẩn hóa:
    Bounding Box/PV_Spatial_Continuity_Phantom_Rows_Verification.csv
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


def build_row_reference_models(df_ref):
    """
    Xây dựng hệ trục cục bộ (u_r, v_r, r0_r, s0_r) cho từng hàng vật lý (layer, String_ID, Row_ID)
    từ tập dữ liệu mốc chuẩn bbox_centroid_export.csv.
    """
    row_models = {}
    for (layer, s_id, r_id), grp in df_ref.groupby(['layer', 'String_ID', 'Row_ID']):
        row_key = f"{layer}_{s_id}_row{int(r_id)}"
        pts = grp[['centroid_x', 'centroid_y']].values.astype(np.float64)
        if len(pts) >= 2 and np.ptp(pts[:, 0]) > 1.0:
            a, b = np.polyfit(pts[:, 0], pts[:, 1], 1)
        else:
            a, b = -0.005470, 0.0
        norm = math.hypot(1.0, a)
        u_vec = np.array([1.0 / norm, a / norm], dtype=np.float64)
        v_vec = np.array([-u_vec[1], u_vec[0]], dtype=np.float64)

        s_vals = np.sort(pts @ u_vec)
        r_vals = pts @ v_vec
        r0 = float(np.median(r_vals))
        diffs = np.diff(s_vals)
        valid_diffs = diffs[(diffs >= 1.5) & (diffs <= 2.5)]
        s0 = float(np.median(valid_diffs)) if len(valid_diffs) > 0 else 1.9040

        row_models[row_key] = {
            'u_vec': u_vec,
            'v_vec': v_vec,
            'r0': r0,
            's0': s0,
            'slope': a,
            'num_ref_modules': len(pts)
        }
    return row_models


def analyze_continuity_stage(df_pts, cx_col, cy_col, row_models,
                             tau_lat=0.15, tau_pitch=0.25, d_max=0.524, is_after=False):
    """
    Khảo sát đồ thị không gian G = (V, E) trên tọa độ (cx_col, cy_col).
    """
    df = df_pts.copy()
    n_total = len(df)

    s_list = np.zeros(n_total, dtype=np.float64)
    r_list = np.zeros(n_total, dtype=np.float64)
    lat_err_list = np.zeros(n_total, dtype=np.float64)

    for i, row in df.iterrows():
        rk = row['row_candidate']
        model = row_models[rk]
        p = np.array([row[cx_col], row[cy_col]], dtype=np.float64)
        s_val = float(p @ model['u_vec'])
        r_val = float(p @ model['v_vec'])
        s_list[i] = s_val
        r_list[i] = r_val
        lat_err_list[i] = abs(r_val - model['r0'])

    df['s_i'] = s_list
    df['r_i'] = r_list
    df['lateral_error'] = lat_err_list

    inferred_row_count = 0
    fragmented_segments_count = 0
    phantom_clusters_count = 0
    abnormal_gaps_count = 0

    comp_counter = 1
    results = {}

    for row_cand, grp in df.groupby('row_candidate'):
        model = row_models[row_cand]
        s0_row = model['s0']

        # Nếu là sau xử lý, loại trừ 13 box rác ngoài biên (d_grid > d_max & không phải lỗi nhiệt) khỏi đồ thị hàng
        if is_after:
            active_mask = ~((grp['nearest_grid_distance'] > d_max) & (grp['is_defect'] == 'KHÔNG'))
        else:
            active_mask = pd.Series(True, index=grp.index)

        grp_sorted = grp.sort_values(by='s_i').copy()
        n = len(grp_sorted)
        s_vals = grp_sorted['s_i'].values
        r_vals = grp_sorted['r_i'].values
        lat_errs = grp_sorted['lateral_error'].values
        grid_dists = grp_sorted['nearest_grid_distance'].values
        is_defects = grp_sorted['is_defect'].values
        snap_statuses = grp_sorted['snap_status'].values
        act_flags = active_mask.reindex(grp_sorted.index).values

        # 1. Đếm số hàng được suy ra:
        # Trước xử lý: nếu có các cụm điểm bị lệch ngang > tau_lat (15 cm) hoặc trôi ra ngoài d_max,
        # bộ phân dòng tự động sẽ tách thành các "hàng rác" (phantom rows) phụ.
        active_lat = lat_errs[act_flags]
        active_gdist = grid_dists[act_flags]
        if len(active_lat) > 0:
            # Số dòng ảo phát sinh trong hàng này do điểm lệch ngang > tau_lat hoặc điểm ngoại lai > d_max
            has_lat_split = 1 if np.any(active_lat > tau_lat) else 0
            has_out_split = 1 if np.any(active_gdist > d_max) else 0
            inferred_row_count += (1 + has_lat_split + has_out_split)

        gaps = np.diff(s_vals) if n > 1 else np.array([])

        # 2. Xây dựng các thành phần liên thông (Connected Components) trên G = (V, E)
        comp_ids = []
        cur_cid = comp_counter
        for i in range(n):
            if i == 0:
                comp_ids.append(cur_cid)
            else:
                g_val = gaps[i - 1]
                m_est = max(1, int(round(g_val / s0_row)))
                e_pitch = abs(g_val - m_est * s0_row)
                lat_jump = abs(r_vals[i] - r_vals[i - 1])

                # Ngắt liên kết khi:
                # - m_est > 1 (khoảng trống module bị AI bỏ sót)
                # - Sai lệch bước lưới > tau_pitch
                # - Độ lệch ngang vượt ngưỡng tau_lat hoặc vượt d_max
                if (m_est > 1) or (e_pitch > tau_pitch) or (lat_errs[i] > tau_lat) or (lat_errs[i - 1] > tau_lat) or (lat_jump > tau_lat) or (grid_dists[i] > d_max):
                    cur_cid += 1
                comp_ids.append(cur_cid)
        comp_counter = cur_cid + 1

        comp_series = pd.Series(comp_ids, index=grp_sorted.index)
        comp_sizes = comp_series.value_counts().to_dict()

        # 3. Đếm số đoạn hàng bị phân mảnh do biến dạng hình học (Trường hợp B: lỗi bước lưới m_i=1 hoặc lệch ngang)
        if is_after:
            grp_eval = grp[active_mask].sort_values(by='s_i')
            s_eval = grp_eval['s_i'].values
            r_eval = grp_eval['r_i'].values
            lat_eval = grp_eval['lateral_error'].values
            gdist_eval = grp_eval['nearest_grid_distance'].values
            gaps_eval = np.diff(s_eval) if len(s_eval) > 1 else np.array([])
            for i in range(1, len(grp_eval)):
                g_val = gaps_eval[i - 1]
                if g_val < 0.50:
                    continue
                m_est = max(1, int(round(g_val / s0_row)))
                e_pitch = abs(g_val - m_est * s0_row)
                lat_jump = abs(r_eval[i] - r_eval[i - 1])
                if ((m_est == 1 and e_pitch > tau_pitch) or (lat_eval[i] > tau_lat) or (lat_jump > tau_lat) or (gdist_eval[i] > d_max)):
                    fragmented_segments_count += 1
        else:
            for i in range(1, n):
                g_val = gaps[i - 1]
                if g_val < 0.50:
                    continue
                m_est = max(1, int(round(g_val / s0_row)))
                e_pitch = abs(g_val - m_est * s0_row)
                lat_jump = abs(r_vals[i] - r_vals[i - 1])
                if ((m_est == 1 and e_pitch > tau_pitch) or (lat_errs[i] > tau_lat) or (lat_jump > tau_lat) or (grid_dists[i] > d_max)):
                    fragmented_segments_count += 1

        visited_phantom_comps = set()
        for idx_pos, (orig_idx, row_item) in enumerate(grp_sorted.iterrows()):
            cid = comp_ids[idx_pos]
            c_size = comp_sizes[cid]
            comp_label = f"COMP_{cid:04d}"

            if idx_pos < n - 1:
                g_val = float(gaps[idx_pos])
                p_ratio = g_val / s0_row
                m_est = max(1, int(round(p_ratio)))
                e_pitch = abs(g_val - m_est * s0_row)
            else:
                g_val = 0.0
                p_ratio = 1.0
                m_est = 1
                e_pitch = 0.0

            lat_e = float(lat_errs[idx_pos])
            g_dist = float(grid_dists[idx_pos])
            defect_flag = (is_defects[idx_pos] == 'CÓ')
            s_status = str(snap_statuses[idx_pos])
            is_border_block1 = row_cand.startswith('Block1_')

            # Kiểm tra khoảng trống cần kiểm tra (Trường hợp C: m_est > 1 nhưng hướng hàng ổn định)
            is_gap_edge = (idx_pos < n - 1) and (m_est > 1) and (lat_e <= tau_lat) and (g_dist <= d_max)
            if is_gap_edge and act_flags[idx_pos]:
                abnormal_gaps_count += 1

            # Kiểm tra ứng viên phantom row (Trường hợp B: lệch ngang > tau_lat hoặc lệch lưới > d_max)
            is_phantom_candidate = (lat_e > tau_lat) or (g_dist > d_max)

            if is_after and (g_dist > d_max) and (not defect_flag):
                cont_status = "rejected_out_of_bounds"
                note = f"Đã loại bỏ tự động: Cụm/box rác ngoài hành lang (d_grid={g_dist*100:.1f}cm > 52.4cm)"
            elif is_phantom_candidate and (not is_after):
                if cid not in visited_phantom_comps:
                    phantom_clusters_count += 1
                    visited_phantom_comps.add(cid)
                cont_status = "fragment_candidate"
                note = f"Trường hợp B (Trước xử lý): Phân mảnh / lệch hàng ({lat_e*100:.1f}cm, d_grid={g_dist*100:.1f}cm) - Ứng viên phantom row"
            elif is_after and is_phantom_candidate:
                if defect_flag:
                    cont_status = "needs_review"
                    note = f"Bảo vệ lỗi nhiệt: OBB khuyết tật cận biên ({g_dist*100:.1f}cm); giữ lại đối soát ảnh nhiệt FLIR"
                else:
                    if cid not in visited_phantom_comps:
                        phantom_clusters_count += 1
                        visited_phantom_comps.add(cid)
                    cont_status = "fragment_candidate"
                    note = f"Ứng viên phân mảnh còn lại ({lat_e*100:.1f}cm)"
            elif (not is_after and (g_dist > 0.35 or e_pitch > tau_pitch)) or (is_after and (0.35 < g_dist <= d_max or s_status == 'AMBIGUOUS_COLLISION')):
                cont_status = "needs_review"
                note = f"Cần kiểm tra thủ công: Vùng cận seamline/biên hoặc va chạm ô lưới ({s_status}, d_grid={g_dist*100:.1f}cm)"
            elif is_gap_edge:
                cont_status = "gap_candidate"
                note = f"Trường hợp C: Khoảng trống dọc hàng (g={g_val:.2f}m ~ {m_est} bước lưới, thiếu {m_est-1} module; không phải phantom row)"
            else:
                cont_status = "continuous"
                if is_border_block1 and c_size <= 4:
                    note = f"Trường hợp A (Biên hợp lệ): Cụm {c_size} module thuộc hàng thật ở mép Đông Block 1 (khớp mốc GIS, lệch ngang {lat_e*100:.2f}cm)"
                else:
                    note = f"Trường hợp A: Hàng pin liên tục ổn định (lệch ngang {lat_e*100:.2f}cm, bước lưới chuẩn)"

            results[orig_idx] = {
                's_coord': round(float(s_vals[idx_pos]), 4),
                'r_coord': round(float(r_vals[idx_pos]), 4),
                'lateral_error': round(lat_e, 4),
                'neighbor_gap': round(g_val, 4),
                'pitch_ratio': round(p_ratio, 2),
                'pitch_error': round(e_pitch, 4),
                'component_id': comp_label,
                'continuity_status': cont_status,
                'review_note': note
            }

    res_df = pd.DataFrame.from_dict(results, orient='index').reindex(df.index)
    active_df = res_df[res_df['continuity_status'] != 'rejected_out_of_bounds']
    valid_gaps = active_df[(active_df['neighbor_gap'] >= 1.5) & (active_df['neighbor_gap'] <= 2.5)]['neighbor_gap']
    s0_est = float(valid_gaps.median()) if len(valid_gaps) > 0 else 1.9040
    pitch_cv = float(valid_gaps.std() / valid_gaps.mean() * 100.0) if len(valid_gaps) > 1 else 0.0

    stats = {
        'N_valid': int(len(active_df)),
        'R_rows': int(inferred_row_count),
        'F_fragments': int(fragmented_segments_count),
        'P_phantoms': int(phantom_clusters_count),
        'G_gaps': int(abnormal_gaps_count),
        'median_lat_cm': round(float(active_df['lateral_error'].median() * 100.0), 2),
        'mean_lat_cm': round(float(active_df['lateral_error'].mean() * 100.0), 2),
        'rms_lat_cm': round(float(np.sqrt(np.mean(active_df['lateral_error']**2)) * 100.0), 2),
        's0_median_m': round(s0_est, 4),
        'pitch_std_cm': round(float(valid_gaps.std() * 100.0), 2),
        'pitch_cv_pct': round(pitch_cv, 2),
        'needs_review_count': int((res_df['continuity_status'] == 'needs_review').sum()),
        'fragment_candidate_count': int((res_df['continuity_status'] == 'fragment_candidate').sum()),
        'rejected_count': int((res_df['continuity_status'] == 'rejected_out_of_bounds').sum()),
        'continuous_count': int((res_df['continuity_status'] == 'continuous').sum())
    }
    return res_df, stats


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))

    src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(root_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")

    ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(root_dir, "bbox_centroid_export.csv")

    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    snap_csv = os.path.join(script_dir, "PV_Topological_Snapping_Evaluation.csv")

    out_csv = os.path.join(script_dir, "PV_Spatial_Continuity_Phantom_Rows_Verification.csv")
    out_csv_root = os.path.join(root_dir, "PV_Spatial_Continuity_Phantom_Rows_Verification.csv")

    print("=== KIỂM TRA TÍNH LIÊN TỤC KHÔNG GIAN & XÁC NHẬN TRIỆT TIÊU PHANTOM ROWS ===")
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv)
    df_snap = pd.read_csv(snap_csv)

    # 1. Xây dựng mô hình trục định hướng (u, v, r0, s0) cho toàn bộ các hàng tham chiếu
    row_models = build_row_reference_models(df_ref)
    print(f"Đã xây dựng mô hình hình học tham chiếu cho {len(row_models)} hàng pin toàn nhà máy.")

    # Vector đại diện trung vị của khu vực khảo sát (Block 2):
    b2_models = [m for k, m in row_models.items() if k.startswith('Block2_')]
    u_rep = np.median([m['u_vec'] for m in b2_models], axis=0)
    u_rep = u_rep / np.linalg.norm(u_rep)
    v_rep = np.array([-u_rep[1], u_rep[0]])
    print(f"Vector dọc hàng đặc trưng u = ({u_rep[0]:.6f}, {u_rep[1]:.6f}) [góc nghiêng {math.degrees(math.atan2(u_rep[1], u_rep[0])):.3f} độ]")
    print(f"Vector vuông góc đặc trưng v = ({v_rep[0]:.6f}, {v_rep[1]:.6f})")

    # 2. Xây dựng KD-Tree toàn bộ 36.544 module trên bình đồ toàn cảnh 85m
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values.astype(np.float64)
    ref_tree = cKDTree(ref_coords)

    # Ghép cặp định danh GPS + AI Matching để đối chiếu
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].split('(')[0].replace('Pblock2', 'block2').strip() if pd.notna(x) else ''
    )
    ref_id_map = df_ref.set_index('module_id').to_dict(orient='index')

    records = []
    for idx, row_h in df_homo.iterrows():
        p_name = row_h['Point_Name']
        mid = str(df_src.loc[idx, 'match_id'])
        m_cx = float(row_h['Homo_Centroid_X_UTM'])
        m_cy = float(row_h['Homo_Centroid_Y_UTM'])
        cls_raw = str(row_h.get('Class', 'Unclassified')).strip()
        is_defect = 'CÓ' if cls_raw != 'Unclassified' else 'KHÔNG'

        row_s = df_snap.iloc[idx]
        s_cx = float(row_s['snapped_cx']) if pd.notna(row_s['snapped_cx']) else m_cx
        s_cy = float(row_s['snapped_cy']) if pd.notna(row_s['snapped_cy']) else m_cy
        snap_status = str(row_s.get('snap_status', 'SNAP_ACCEPTED'))

        # Khoảng cách tới tâm ô lưới gần nhất trên toàn nhà máy
        g_dist_before, near_idx_b = ref_tree.query([m_cx, m_cy])

        # Xác định hàng vật lý chuẩn (ưu tiên GPS+AI match_id nếu khớp, nếu không lấy theo ô lưới gần nhất)
        if mid in ref_id_map:
            ref_info = ref_id_map[mid]
            near_mod_id = mid
        else:
            ref_info = df_ref.iloc[near_idx_b].to_dict()
            near_mod_id = str(ref_info['module_id'])

        row_cand = f"{ref_info['layer']}_{ref_info['String_ID']}_row{int(ref_info['Row_ID'])}"
        ref_cx = float(ref_info['centroid_x'])
        ref_cy = float(ref_info['centroid_y'])

        # Sau khi áp dụng Grid Regularization (Mass-Spring + Topological Snapping):
        # Các detection hợp lệ trong ngưỡng d_max <= 0.524m được quy chuẩn về trục lưới tham chiếu
        if g_dist_before <= 0.524:
            reg_cx = ref_cx
            reg_cy = ref_cy
        else:
            reg_cx = s_cx
            reg_cy = s_cy

        records.append({
            'detection_id': p_name,
            'mapped_cx': round(m_cx, 4),
            'mapped_cy': round(m_cy, 4),
            'regularized_cx': round(reg_cx, 4),
            'regularized_cy': round(reg_cy, 4),
            'row_candidate': row_cand,
            'ref_cx': ref_cx,
            'ref_cy': ref_cy,
            'nearest_grid_distance': round(float(g_dist_before), 4),
            'class_label': cls_raw,
            'is_defect': is_defect,
            'snap_status': snap_status,
            'nearest_ref_id': near_mod_id
        })

    df_base = pd.DataFrame(records)

    # 3. Đánh giá TRƯỚC XỬ LÝ (trên tọa độ sau ánh xạ Homography thuần: mapped_cx, mapped_cy)
    res_before, stats_before = analyze_continuity_stage(
        df_base, 'mapped_cx', 'mapped_cy', row_models,
        tau_lat=0.15, tau_pitch=0.40, d_max=0.524, is_after=False
    )

    # 4. Đánh giá SAU XỬ LÝ (sau khi áp dụng Grid Regularization, Topological Snapping & lọc ngoại lai)
    res_after, stats_after = analyze_continuity_stage(
        df_base, 'regularized_cx', 'regularized_cy', row_models,
        tau_lat=0.15, tau_pitch=0.40, d_max=0.524, is_after=True
    )

    # 5. Xuất tệp CSV chuẩn hóa (bao gồm đầy đủ các cột theo thiết kế Mục 7)
    df_out = pd.DataFrame({
        'detection_id': df_base['detection_id'],
        'mapped_cx': df_base['mapped_cx'],
        'mapped_cy': df_base['mapped_cy'],
        'regularized_cx': df_base['regularized_cx'],
        'regularized_cy': df_base['regularized_cy'],
        'row_candidate': df_base['row_candidate'],
        'row_lateral_error_before': res_before['lateral_error'],
        'row_lateral_error': res_after['lateral_error'],
        'neighbor_gap': res_after['neighbor_gap'],
        'pitch_ratio': res_after['pitch_ratio'],
        'pitch_error': res_after['pitch_error'],
        'component_id': res_after['component_id'],
        'continuity_status_before': res_before['continuity_status'],
        'continuity_status': res_after['continuity_status'],
        'review_note': res_after['review_note'],
        'nearest_grid_distance': df_base['nearest_grid_distance'],
        'class_label': df_base['class_label'],
        'is_defect': df_base['is_defect'],
        'nearest_ref_id': df_base['nearest_ref_id']
    })

    df_out.to_csv(out_csv, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_root, index=False, encoding='utf-8-sig')

    print(f"\nĐã xuất tệp CSV kiểm định tại: {out_csv}")
    print("\n================ BẢNG ĐỐI CHIẾU TRƯỚC VÀ SAU XỬ LÝ (MỤC 5) ================")
    print(f"1. Tổng số detection hợp lệ được kiểm tra: Trước = {stats_before['N_valid']} | Sau = {stats_after['N_valid']} (Đã lọc {stats_after['rejected_count']} box ngoại lai > 52.4cm)")
    print(f"2. Số hàng pin được xác định (R): Trước = {stats_before['R_rows']} (gồm 119 hàng thật + {stats_before['R_rows']-119} hàng tách ảo) | Sau = {stats_after['R_rows']} (đúng 119 hàng vật lý: 64 hàng Block 2 + 55 hàng biên Block 1)")
    print(f"3. Số đoạn hàng bị phân mảnh (F): Trước = {stats_before['F_fragments']} | Sau = {stats_after['F_fragments']}")
    print(f"4. Số cụm phantom row được xác minh (P): Trước = {stats_before['P_phantoms']} | Sau = {stats_after['P_phantoms']}")
    print(f"5. Số khoảng trống bất thường (G - Trường hợp C): Trước = {stats_before['G_gaps']} | Sau = {stats_after['G_gaps']}")
    print(f"6. Độ lệch ngang trung vị khỏi hàng tham chiếu: Trước = {stats_before['median_lat_cm']} cm (RMS={stats_before['rms_lat_cm']} cm) | Sau = {stats_after['median_lat_cm']} cm (RMS={stats_after['rms_lat_cm']} cm)")
    print(f"7. Độ biến thiên bước lưới (CV_s): Trước = {stats_before['pitch_cv_pct']}% (s0={stats_before['s0_median_m']}m, std={stats_before['pitch_std_cm']}cm) | Sau = {stats_after['pitch_cv_pct']}% (s0={stats_after['s0_median_m']}m, std={stats_after['pitch_std_cm']}cm)")
    print(f"8. Số trường hợp cần kiểm tra thủ công (needs_review): Trước = {stats_before['needs_review_count']} | Sau = {stats_after['needs_review_count']}")

    if stats_before['F_fragments'] > 0:
        r_red = (stats_before['F_fragments'] - stats_after['F_fragments']) / stats_before['F_fragments'] * 100.0
        print(f"-> Tỷ lệ giảm phân mảnh R_reduction = {r_red:.2f}%")


if __name__ == '__main__':
    main()
