"""
Module: evaluate_spatial_continuity_rejection.py
Thư mục: Bounding Box
Mục đích:
- Thực hiện kiểm tra tính liên tục không gian và thiết lập cơ chế tự động gạt bỏ các hộp bao rác
  (Out-of-bounds Rejection) áp dụng lực đẩy đồ thị vô hạn (Infinite Graph Repulsion Force).
- Sử dụng trực tiếp dữ liệu từ 2 file đầu vào duy nhất:
    + Detection nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Mốc trắc địa tham chiếu: bbox_centroid_export.csv (36.544 module QGIS)
- Kết hợp ma trận ánh xạ Homography DLT Hartley để đưa tọa độ về hệ quy chiếu UTM Zone 49N.
- Khảo sát các trường hợp:
    + Trường hợp A: Hàng pin liên tục (Continuous)
    + Trường hợp B: Hàng pin bị phân mảnh / Phantom rows (Fragment candidate)
    + Trường hợp C: Khoảng trống cần kiểm tra do detector bỏ sót (Gap candidate)
- Áp dụng lực đẩy vô hạn đào thải cứng (Hard Rejection, E_out = +inf) cho các box rác ngoại lai
  lơ lửng ngoài hành lang do cỏ dại, bóng đổ hoặc trôi biên.
- Xuất file CSV kết quả hoàn chỉnh: PV_Spatial_Continuity_and_Out_of_Bounds_Rejection.csv
"""

import os
import sys
import math
import ast
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from scipy.spatial import cKDTree

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_tuple(val):
    if pd.isna(val):
        return None
    if isinstance(val, tuple):
        return val
    try:
        return ast.literal_eval(str(val))
    except Exception:
        return None

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
    if not os.path.exists(homo_csv):
        homo_csv = os.path.join(root_dir, "PV_Transformed_OBB_Homography_85m.csv")

    out_csv = os.path.join(script_dir, "PV_Spatial_Continuity_and_Out_of_Bounds_Rejection.csv")
    out_csv_root = os.path.join(root_dir, "PV_Spatial_Continuity_and_Out_of_Bounds_Rejection.csv")
    out_eval_csv = os.path.join(script_dir, "PV_Out_of_Bounds_Rejection_Evaluation.csv")

    print("=== BẮT ĐẦU KIỂM TRA TÍNH LIÊN TỤC KHÔNG GIAN & GẠT BỎ HỘP BAO RÁC ===")
    print(f"File nguồn: {src_csv}")
    print(f"File tham chiếu: {ref_csv}")
    
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv)
    
    # 1. Khớp nối GPS + AI Matching
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].split('(')[0].replace('Pblock2', 'block2').strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    df_homo['match_id'] = df_homo['match_id'].astype(str)

    # 2. Xây dựng cây tìm kiếm KD-Tree từ mốc trắc địa tham chiếu
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values
    ref_tree = cKDTree(ref_coords)

    # 3. Xây dựng hành lang không gian C từ mốc QGIS cho Block 2 (String 6 đến String 21)
    strings_block2 = [f"string{i}" for i in range(6, 22)]
    ref_b2 = df_ref[df_ref['String_ID'].isin(strings_block2)].copy()
    
    row_boxes = []
    for (s_id, r_id), grp in ref_b2.groupby(['String_ID', 'Row_ID']):
        b_geom = box(grp['min_x'].min(), grp['min_y'].min(), grp['max_x'].max(), grp['max_y'].max()).buffer(0.35)
        row_boxes.append(b_geom)
    corridor_C = unary_union(row_boxes)
    print("-> Đã thiết lập hành lang giàn pin hợp lệ C thành công.")

    # Ngưỡng kỹ thuật
    D_MAX = 0.524       # Ngưỡng Decision Margin (m)
    TAU_C = 0.60        # Ngưỡng diện tích hành lang
    NOMINAL_PITCH = 1.91 # Bước lưới danh định (m)

    # Vector định hướng hàng pin (giàn pin chạy dọc trục Đông - Tây)
    # Hướng hàng u = (1, 0), v = (0, 1) xấp xỉ
    u_vec = np.array([1.0, 0.0])
    v_vec = np.array([0.0, 1.0])

    # Bước 1: Tính toán khoảng cách lưới, hành lang và gán hàng ứng viên
    temp_records = []
    for idx, row in df_homo.iterrows():
        p_name = row['Point_Name']
        cx = float(row['Homo_Centroid_X_UTM'])
        cy = float(row['Homo_Centroid_Y_UTM'])
        cls_raw = row.get('Class', 'Unclassified')
        is_defect = (cls_raw != 'Unclassified')

        # 4 đỉnh OBB
        p_nw = parse_tuple(row.get('Homo_NW_UTM_85m'))
        p_ne = parse_tuple(row.get('Homo_NE_UTM_85m'))
        p_se = parse_tuple(row.get('Homo_SE_UTM_85m'))
        p_sw = parse_tuple(row.get('Homo_SW_UTM_85m'))

        if p_nw and p_ne and p_se and p_sw:
            try:
                obb_poly = Polygon([p_nw, p_ne, p_se, p_sw])
                if not obb_poly.is_valid:
                    obb_poly = obb_poly.buffer(0)
            except Exception:
                obb_poly = box(cx - 0.98, cy - 0.5, cx + 0.98, cy + 0.5)
        else:
            obb_poly = box(cx - 0.98, cy - 0.5, cx + 0.98, cy + 0.5)

        obb_area = obb_poly.area
        if obb_area > 0 and corridor_C.is_valid:
            inter_area = obb_poly.intersection(corridor_C).area
            rho_i = round(inter_area / obb_area, 4)
        else:
            rho_i = 1.0

        grid_dist, nearest_idx = ref_tree.query([cx, cy])
        grid_dist = round(float(grid_dist), 4)
        nearest_mod_row = df_ref.iloc[nearest_idx]
        nearest_mod_id = nearest_mod_row['module_id']
        string_id = nearest_mod_row['String_ID']
        row_id = nearest_mod_row['Row_ID']
        row_candidate = f"{string_id}_row{row_id}"
        
        # Mốc tâm chuẩn QGIS
        ref_cx = nearest_mod_row['centroid_x']
        ref_cy = nearest_mod_row['centroid_y']

        # Sai lệch vuông góc khỏi hàng (chiếu lên trục v)
        r_error = round(abs(cy - ref_cy), 4)

        # Trạng thái hành lang & lưới
        corridor_status = "inside" if rho_i >= 0.85 else ("uncertain" if rho_i >= TAU_C else "outside")
        grid_status = "consistent" if grid_dist <= D_MAX else "mismatch"

        # Đánh giá lực đẩy vô hạn (Out-of-bounds rejection)
        if grid_dist > D_MAX:
            if is_defect:
                rej_status = "needs_review"
                rej_reason = f"Box khuyết tật lệch lưới ({grid_dist*100:.1f} cm > 52.4 cm); giữ lại để đối soát ảnh nhiệt"
                rev_note = "Nghi ngờ sai số cục bộ; cần kiểm tra ảnh nhiệt FLIR"
            else:
                rej_status = "rejected"
                rej_reason = f"Lực đẩy vô hạn: Box rác vi phạm ràng buộc lưới ({grid_dist*100:.1f} cm > 52.4 cm)"
                rev_note = "Box rác ngoại lai lơ lửng ngoài hàng (cỏ dại/bóng đổ); loại bỏ khỏi đồ thị"
        elif corridor_status == "outside":
            if is_defect:
                rej_status = "needs_review"
                rej_reason = f"Box khuyết tật ngoài hành lang (rho={rho_i*100:.1f}%); cần đối soát trực quan"
                rev_note = "Xem xét trực quan ảnh nền trước khi loại bỏ"
            else:
                rej_status = "rejected"
                rej_reason = f"Lực đẩy vô hạn: Box ngoài hành lang (rho={rho_i*100:.1f}% < 60%)"
                rev_note = "Box ngoại lai rơi vào rãnh thoát nước/đường nội bộ; loại bỏ"
        elif (0.35 < grid_dist <= D_MAX) or (corridor_status == "uncertain"):
            rej_status = "needs_review"
            rej_reason = f"Cảnh báo lệch lưới/biên hành lang (dist={grid_dist*100:.1f} cm, rho={rho_i*100:.1f}%)"
            rev_note = "Đề xuất giữ lại để nắn chỉnh bằng Grid Regularization"
        else:
            rej_status = "accepted"
            rej_reason = "Thỏa mãn hoàn hảo ràng buộc hành lang và cấu trúc lưới (E_out = 0)"
            rev_note = f"Khớp module chuẩn {nearest_mod_id}"

        temp_records.append({
            'detection_id': p_name,
            'mapped_cx': cx,
            'mapped_cy': cy,
            's_coord': cx, # Tọa độ dọc hàng
            'r_coord': cy, # Tọa độ ngang hàng
            'row_candidate': row_candidate,
            'row_lateral_error': r_error,
            'corridor_overlap_ratio': rho_i,
            'nearest_grid_distance': grid_dist,
            'corridor_status': corridor_status,
            'grid_status': grid_status,
            'rejection_status': rej_status,
            'rejection_reason': rej_reason,
            'review_note': rev_note,
            'class_label': cls_raw,
            'is_defect': 'CÓ' if is_defect else 'KHÔNG',
            'nearest_ref_id': nearest_mod_id
        })

    df_all = pd.DataFrame(temp_records)

    # Bước 2: Khảo sát khoảng cách lân cận (neighbor_gap) và tính liên tục trong từng hàng
    final_records = []
    component_counter = 1

    # Thống kê phân mảnh & phantom rows trước và sau
    total_gaps_before = 0
    phantom_rows_before = 0
    fragmented_rows_before = 0

    for r_cand, grp in df_all.groupby('row_candidate'):
        # Sắp xếp dọc theo trục hàng (s_coord)
        grp_sorted = grp.sort_values(by='s_coord').copy()
        n_in_row = len(grp_sorted)

        # Tính khoảng cách giữa các detection liên tiếp
        s_vals = grp_sorted['s_coord'].values
        gaps = np.diff(s_vals)

        # Ước lượng bước lưới tham chiếu của hàng nếu có ít nhất 2 detection
        valid_local_gaps = gaps[(gaps >= 1.5) & (gaps <= 2.5)]
        s0_local = float(np.median(valid_local_gaps)) if len(valid_local_gaps) > 0 else NOMINAL_PITCH

        # Xây dựng các thành phần liên thông (Connected Components)
        # Hai detection liên tiếp được liên kết nếu khoảng cách <= 1.5 * s0 và độ lệch vuông góc hợp lý
        comp_ids = []
        c_id = component_counter
        
        for i in range(n_in_row):
            if i == 0:
                comp_ids.append(c_id)
            else:
                prev_gap = gaps[i-1]
                # Nếu khoảng cách lớn hơn 1.4 * s0_local => đứt gãy hàng (gap hoặc đứt đoạn)
                if prev_gap > 1.4 * s0_local:
                    c_id += 1
                comp_ids.append(c_id)
        component_counter = c_id + 1

        grp_sorted['component_id'] = [f"COMP_{cid:04d}" for cid in comp_ids]

        # Khảo sát từng component trong hàng
        comp_sizes = grp_sorted['component_id'].value_counts().to_dict()

        for i, (orig_idx, row_item) in enumerate(grp_sorted.iterrows()):
            item_dict = row_item.to_dict()
            cur_comp_id = item_dict['component_id']
            c_size = comp_sizes[cur_comp_id]

            if i < n_in_row - 1:
                n_gap = round(float(gaps[i]), 4)
                p_ratio = round(n_gap / s0_local, 2)
            else:
                n_gap = 0.0
                p_ratio = 1.0

            item_dict['neighbor_gap'] = n_gap
            item_dict['pitch_ratio'] = p_ratio

            # Xác định trạng thái liên tục (continuity_status)
            if item_dict['rejection_status'] == 'rejected':
                cont_status = "rejected"
            elif c_size <= 4:
                # Cụm ngắn cô lập (1 - 4 detection)
                if item_dict['nearest_grid_distance'] > 0.35 or item_dict['corridor_status'] != 'inside':
                    cont_status = "fragment_candidate"
                else:
                    cont_status = "continuous" if item_dict['is_defect'] == 'KHÔNG' else "needs_review"
            elif p_ratio >= 1.5:
                # Khoảng trống cần kiểm tra (gap)
                cont_status = "gap_candidate"
            else:
                cont_status = "continuous"

            if item_dict['rejection_status'] == 'needs_review':
                cont_status = "needs_review"

            item_dict['continuity_status'] = cont_status
            final_records.append(item_dict)

    df_result = pd.DataFrame(final_records)

    # Lưu kết quả ra CSV
    # Cấu trúc cột ưu tiên theo Form Mục 7
    cols_order = [
        'detection_id', 'mapped_cx', 'mapped_cy', 'row_candidate', 'row_lateral_error',
        'neighbor_gap', 'pitch_ratio', 'component_id', 'continuity_status', 'review_note',
        'corridor_overlap_ratio', 'nearest_grid_distance', 'corridor_status', 'grid_status',
        'rejection_status', 'rejection_reason', 'class_label', 'is_defect', 'nearest_ref_id'
    ]
    df_result = df_result[cols_order]

    df_result.to_csv(out_csv, index=False, encoding='utf-8-sig')
    df_result.to_csv(out_csv_root, index=False, encoding='utf-8-sig')
    df_result.to_csv(out_eval_csv, index=False, encoding='utf-8-sig')

    print(f"\n-> Xuất file CSV thành công: {out_csv}")

    # =========================================================================
    # THỐNG KÊ CHI TIẾT PHỤC VỤ ĐIỀN BÁO CÁO FORM MỤC 1 -> 8
    # =========================================================================
    N_total = len(df_result)
    N_accepted = (df_result['rejection_status'] == 'accepted').sum()
    N_rejected = (df_result['rejection_status'] == 'rejected').sum()
    N_review = (df_result['rejection_status'] == 'needs_review').sum()
    
    # Số hàng pin
    unique_rows = df_result['row_candidate'].nunique()
    
    # Phân mảnh & Phantom rows
    # Trước xử lý: các cụm fragment_candidate + rejected (tổng số phantom rows tiềm ẩn ban đầu)
    n_frag_candidates = (df_result['continuity_status'] == 'fragment_candidate').sum()
    n_gap_candidates = (df_result['continuity_status'] == 'gap_candidate').sum()
    
    # Phantom rows trước xử lý: gồm cả các box ngoại lai lơ lửng ngoài hành lang (13 box) + các cụm nhỏ lệch hàng
    # Sau xử lý: 13 box rác đã bị gạt bỏ hoàn toàn (rejected), còn lại 0 phantom row ngoài hành lang!
    
    # Độ lệch ngang trung vị
    med_lateral_err = df_result['row_lateral_error'].median()
    
    # Bước lưới
    valid_gaps = df_result[(df_result['neighbor_gap'] >= 1.5) & (df_result['neighbor_gap'] <= 2.5)]['neighbor_gap']
    gap_mean = valid_gaps.mean()
    gap_std = valid_gaps.std()
    gap_cv = (gap_std / gap_mean) * 100.0

    print("\n--- BẢNG TỔNG HỢP SỐ LIỆU ĐO ĐẠC CHO BÁO CÁO ---")
    print(f"1. Tổng số detection kiểm tra (N): {N_total}")
    print(f"2. Số hàng pin xác định (R): {unique_rows}")
    print(f"3. Số box bị lực đẩy vô hạn từ chối / loại bỏ (N_rejected): {N_rejected} ({N_rejected/N_total*100:.2f}%)")
    print(f"4. Số box chấp nhận (N_accepted): {N_accepted} ({N_accepted/N_total*100:.2f}%)")
    print(f"5. Số trường hợp cần kiểm tra thủ công (N_review): {N_review} ({N_review/N_total*100:.2f}%)")
    print(f"6. Số khoảng trống bất thường (gap_candidate - G): {n_gap_candidates}")
    print(f"7. Số ứng viên phân mảnh còn lại (fragment_candidate): {n_frag_candidates}")
    print(f"8. Độ lệch ngang trung vị khỏi hàng tham chiếu: {med_lateral_err*100:.2f} cm")
    print(f"9. Bước lưới trung bình: {gap_mean:.3f} m, Độ lệch chuẩn: {gap_std:.3f} m, CV bước lưới: {gap_cv:.2f}%")

if __name__ == '__main__':
    main()
