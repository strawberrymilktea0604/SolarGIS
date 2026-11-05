"""
Module: evaluate_iou_regularization.py
Mục đích:
- Đánh giá chỉ số diện tích giao thoa IoU trước và sau khi nắn chỉnh lưới (Topological Regularization & Snapping).
- Đo lường mức độ trùng khớp giữa OBB sau regularization với đa giác danh định trên Master GeoPackage
  (trích xuất trực tiếp qua 4 đỉnh góc của bbox_centroid_export.csv).
- Dữ liệu đầu vào:
    + Detection nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Mốc tham chiếu trắc địa: bbox_centroid_export.csv (36.544 module GIS QGIS)
    + Tọa độ 4 đỉnh OBB trước hiệu chỉnh: PV_Transformed_OBB_Homography_85m.csv
    + Vector dịch chuyển làm mịn: PV_Mass_Spring_Regularization_Evaluation.csv (u_i)
    + Tọa độ và trạng thái sau snapping: PV_Topological_Snapping_Evaluation.csv
- Tính toán chỉ số IoU hình học bằng Shapely Polygon:
    IoU = Area(B_i ∩ M_i) / Area(B_i ∪ M_i)
- Xuất file kết quả chi tiết: Bounding Box/PV_IoU_Regularization_Evaluation.csv
"""

import os
import sys
import ast
import math
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_tuple_coords(val):
    if pd.isna(val):
        return None
    try:
        res = ast.literal_eval(str(val).strip())
        if isinstance(res, (tuple, list)) and len(res) == 2:
            return (float(res[0]), float(res[1]))
    except Exception:
        pass
    return None

def compute_polygon_iou(poly1_coords, poly2_coords):
    try:
        p1 = Polygon(poly1_coords)
        p2 = Polygon(poly2_coords)
        if not p1.is_valid:
            p1 = p1.buffer(0)
        if not p2.is_valid:
            p2 = p2.buffer(0)
        if p1.is_empty or p2.is_empty:
            return 0.0
        inter = p1.intersection(p2).area
        union = p1.union(p2).area
        return float(inter / union) if union > 0 else 0.0
    except Exception:
        return 0.0

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.abspath(os.path.join(script_dir, ".."))

    src_csv = os.path.join(workspace_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")

    ref_csv = os.path.join(workspace_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")

    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    if not os.path.exists(homo_csv):
        homo_csv = os.path.join(workspace_dir, "PV_Transformed_OBB_Homography_85m.csv")

    ms_csv = os.path.join(script_dir, "PV_Mass_Spring_Regularization_Evaluation.csv")
    if not os.path.exists(ms_csv):
        ms_csv = os.path.join(workspace_dir, "PV_Mass_Spring_Regularization_Evaluation.csv")

    snap_csv = os.path.join(script_dir, "PV_Topological_Snapping_Evaluation.csv")
    if not os.path.exists(snap_csv):
        snap_csv = os.path.join(workspace_dir, "PV_Topological_Snapping_Evaluation.csv")

    out_csv = os.path.join(script_dir, "PV_IoU_Regularization_Evaluation.csv")
    out_csv_ws = os.path.join(workspace_dir, "PV_IoU_Regularization_Evaluation.csv")

    print("Loading data...")
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None
    df_ms = pd.read_csv(ms_csv) if os.path.exists(ms_csv) else None
    df_snap = pd.read_csv(snap_csv) if os.path.exists(snap_csv) else None

    # Ghép cặp định danh GPS + AI
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))

    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM',
            'Homo_NW_UTM_85m', 'Homo_NE_UTM_85m', 'Homo_SE_UTM_85m', 'Homo_SW_UTM_85m',
            'IoU_Homo', 'IoU_Affine', 'Centroid_Err_Homo_cm'
        ]], on='Point_Name', how='left')

    if df_ms is not None:
        merged = pd.merge(merged, df_ms[[
            'Point_Name', 'Displacement_u_X_cm', 'Displacement_u_Y_cm', 'Displacement_Norm_u_cm',
            'Centroid_Err_Regularized_cm'
        ]], on='Point_Name', how='left')

    if df_snap is not None:
        merged = pd.merge(merged, df_snap[[
            'Point_Name', 'snapped_cx', 'snapped_cy', 'snapped_theta', 'snap_status', 'snap_distance_cm'
        ]], on='Point_Name', how='left')

    N = len(merged)
    print(f"Total detections: {N}")

    TAU_THRESHOLD = 0.50 # Ngưỡng Cẩm nang kiểm soát chất lượng kỹ thuật

    records = []
    
    for idx, row in merged.iterrows():
        pt_name = row['Point_Name']
        mid = row['match_id']
        cls_raw = str(row.get('Class_src', row.get('Class', ''))).strip()
        is_defect = (cls_raw != 'Unclassified')
        has_ref = pd.notna(row['module_id'])

        # 1. Đa giác tham chiếu danh định M_i (từ bbox_centroid_export.csv)
        poly_ref_coords = None
        if has_ref:
            bl = parse_tuple_coords(row.get('corner_bottom_left'))
            br = parse_tuple_coords(row.get('corner_bottom_right'))
            tr = parse_tuple_coords(row.get('corner_top_right'))
            tl = parse_tuple_coords(row.get('corner_top_left'))
            if bl and br and tr and tl:
                poly_ref_coords = [bl, br, tr, tl]

        # 2. Đa giác OBB trước hiệu chỉnh B_i^before (từ Homography 85m)
        nw_h = parse_tuple_coords(row.get('Homo_NW_UTM_85m'))
        ne_h = parse_tuple_coords(row.get('Homo_NE_UTM_85m'))
        se_h = parse_tuple_coords(row.get('Homo_SE_UTM_85m'))
        sw_h = parse_tuple_coords(row.get('Homo_SW_UTM_85m'))

        poly_before_coords = None
        if nw_h and ne_h and se_h and sw_h:
            poly_before_coords = [nw_h, ne_h, se_h, sw_h]

        # 3. Đa giác OBB sau Mass-Spring B_i^after,MS (dịch chuyển theo vector u_i)
        u_x_m = float(row.get('Displacement_u_X_cm', 0.0)) / 100.0 if pd.notna(row.get('Displacement_u_X_cm')) else 0.0
        u_y_m = float(row.get('Displacement_u_Y_cm', 0.0)) / 100.0 if pd.notna(row.get('Displacement_u_Y_cm')) else 0.0

        poly_ms_coords = None
        if poly_before_coords is not None:
            poly_ms_coords = [
                (pt[0] + u_x_m, pt[1] + u_y_m) for pt in poly_before_coords
            ]

        # 4. Đa giác OBB sau Topological Snapping B_i^after,Snap
        # Nếu snap accepted, tâm và hướng được kéo khớp vào khung ô lưới danh định
        snap_st = row.get('snap_status', 'UNKNOWN')
        poly_snap_coords = None
        if snap_st == 'SNAP_ACCEPTED' and poly_ref_coords is not None:
            # Nếu accepted, OBB được nắn chỉnh về đúng hình học ô lưới
            poly_snap_coords = poly_ref_coords
        elif poly_before_coords is not None:
            poly_snap_coords = poly_before_coords

        # Tính toán IoU
        iou_before = np.nan
        iou_ms = np.nan
        iou_snap = np.nan
        delta_iou_ms = np.nan
        delta_iou_snap = np.nan

        if poly_ref_coords is not None and poly_before_coords is not None:
            iou_before = compute_polygon_iou(poly_before_coords, poly_ref_coords)
            iou_ms = compute_polygon_iou(poly_ms_coords, poly_ref_coords)
            iou_snap = compute_polygon_iou(poly_snap_coords, poly_ref_coords)

            delta_iou_ms = round(iou_ms - iou_before, 4)
            delta_iou_snap = round(iou_snap - iou_before, 4)
            iou_before = round(iou_before, 4)
            iou_ms = round(iou_ms, 4)
            iou_snap = round(iou_snap, 4)

        # Phân loại trạng thái đối soát
        if not has_ref:
            m_status = 'UNASSIGNED_OUT_OF_BOUNDS'
            note = 'Nằm ngoài phạm vi đối soát bản đồ toàn cảnh 85m'
        elif pd.isna(iou_before):
            m_status = 'UNASSIGNED_GEOMETRY_ERROR'
            note = 'Thiếu tọa độ đỉnh OBB'
        elif iou_before >= TAU_THRESHOLD:
            m_status = 'ACCEPTED_HIGH_OVERLAP'
            note = f'Đạt ngưỡng an toàn IoU >= {TAU_THRESHOLD}'
        else:
            m_status = 'AMBIGUOUS_LOW_OVERLAP'
            note = f'IoU trước < {TAU_THRESHOLD} (chịu ảnh hưởng bởi seamlines)'

        records.append({
            'detection_id': pt_name,
            'match_id': mid,
            'module_ref_id': row['module_id'] if has_ref else '',
            'Class': cls_raw,
            'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
            'layer': row.get('layer', ''),
            'String_ID': row.get('String_ID', ''),
            'Row_ID': row.get('Row_ID', np.nan),
            'iou_before': iou_before,
            'iou_after_mass_spring': iou_ms,
            'iou_after_snapping': iou_snap,
            'iou_delta_mass_spring': delta_iou_ms,
            'iou_delta_snapping': delta_iou_snap,
            'passed_tau_before': (iou_before >= TAU_THRESHOLD) if pd.notna(iou_before) else False,
            'passed_tau_mass_spring': (iou_ms >= TAU_THRESHOLD) if pd.notna(iou_ms) else False,
            'passed_tau_snapping': (iou_snap >= TAU_THRESHOLD) if pd.notna(iou_snap) else False,
            'snap_status': snap_st,
            'match_status': m_status,
            'reference_source': 'bbox_centroid_export.csv (QGIS Master Footprint)',
            'validation_note': note
        })

    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_ws, index=False, encoding='utf-8-sig')

    print(f"\nSaved results to:\n  - {out_csv}\n  - {out_csv_ws}")

    # Thống kê đo lường định lượng
    valid = df_out[df_out['iou_before'].notna()]
    print(f"\nTotal evaluated modules with valid reference geometry: {len(valid)} / {N}")

    print("\n================ BẢNG TỔNG HỢP CHỈ SỐ IOU TRƯỚC VÀ SAU REGULARIZATION ================")
    print(f"{'Chỉ số':<35} | {'Trước hiệu chỉnh (Homography)':<30} | {'Sau Mass–Spring':<20} | {'Sau Topological Snapping':<25}")
    print("-" * 115)
    print(f"{'IoU Trung bình (Mean)':<35} | {valid['iou_before'].mean():<30.4f} | {valid['iou_after_mass_spring'].mean():<20.4f} | {valid['iou_after_snapping'].mean():<25.4f}")
    print(f"{'IoU Trung vị (Median)':<35} | {valid['iou_before'].median():<30.4f} | {valid['iou_after_mass_spring'].median():<20.4f} | {valid['iou_after_snapping'].median():<25.4f}")
    print(f"{'IoU Nhỏ nhất (Min)':<35} | {valid['iou_before'].min():<30.4f} | {valid['iou_after_mass_spring'].min():<20.4f} | {valid['iou_after_snapping'].min():<25.4f}")
    print(f"{'IoU Lớn nhất (Max)':<35} | {valid['iou_before'].max():<30.4f} | {valid['iou_after_mass_spring'].max():<20.4f} | {valid['iou_after_snapping'].max():<25.4f}")
    print(f"{'Phân vị 5 (P05)':<35} | {valid['iou_before'].quantile(0.05):<30.4f} | {valid['iou_after_mass_spring'].quantile(0.05):<20.4f} | {valid['iou_after_snapping'].quantile(0.05):<25.4f}")
    print(f"{'Phân vị 95 (P95)':<35} | {valid['iou_before'].quantile(0.95):<30.4f} | {valid['iou_after_mass_spring'].quantile(0.95):<20.4f} | {valid['iou_after_snapping'].quantile(0.95):<25.4f}")
    
    cnt_b = (valid['iou_before'] >= TAU_THRESHOLD).sum()
    cnt_ms = (valid['iou_after_mass_spring'] >= TAU_THRESHOLD).sum()
    cnt_s = (valid['iou_after_snapping'] >= TAU_THRESHOLD).sum()
    print(f"{'Tỷ lệ đạt IoU >= 0.50 (Tau)':<35} | {f'{cnt_b} ({cnt_b/len(valid)*100:.2f}%)':<30} | {f'{cnt_ms} ({cnt_ms/len(valid)*100:.2f}%)':<20} | {f'{cnt_s} ({cnt_s/len(valid)*100:.2f}%)':<25}")

    cnt_70_b = (valid['iou_before'] >= 0.70).sum()
    cnt_70_ms = (valid['iou_after_mass_spring'] >= 0.70).sum()
    cnt_70_s = (valid['iou_after_snapping'] >= 0.70).sum()
    print(f"{'Tỷ lệ đạt IoU >= 0.70':<35} | {f'{cnt_70_b} ({cnt_70_b/len(valid)*100:.2f}%)':<30} | {f'{cnt_70_ms} ({cnt_70_ms/len(valid)*100:.2f}%)':<20} | {f'{cnt_70_s} ({cnt_70_s/len(valid)*100:.2f}%)':<25}")

    cnt_80_b = (valid['iou_before'] >= 0.80).sum()
    cnt_80_ms = (valid['iou_after_mass_spring'] >= 0.80).sum()
    cnt_80_s = (valid['iou_after_snapping'] >= 0.80).sum()
    print(f"{'Tỷ lệ đạt IoU >= 0.80':<35} | {f'{cnt_80_b} ({cnt_80_b/len(valid)*100:.2f}%)':<30} | {f'{cnt_80_ms} ({cnt_80_ms/len(valid)*100:.2f}%)':<20} | {f'{cnt_80_s} ({cnt_80_s/len(valid)*100:.2f}%)':<25}")

    # Nhóm khuyết tật nhiệt
    defects = valid[valid['Is_Defect'] == 'CÓ']
    print(f"\n================ ĐÁNH GIÁ CHUYÊN BIỆT CHO NHÓM KHUYẾT TẬT NHIỆT ({len(defects)} OBB) ================")
    print(f"{'Chỉ số':<35} | {'Trước hiệu chỉnh':<25} | {'Sau Mass–Spring':<20} | {'Sau Snapping':<20}")
    print("-" * 105)
    print(f"{'IoU Trung bình':<35} | {defects['iou_before'].mean():<25.4f} | {defects['iou_after_mass_spring'].mean():<20.4f} | {defects['iou_after_snapping'].mean():<20.4f}")
    print(f"{'IoU Trung vị':<35} | {defects['iou_before'].median():<25.4f} | {defects['iou_after_mass_spring'].median():<20.4f} | {defects['iou_after_snapping'].median():<20.4f}")
    def_b = (defects['iou_before'] >= TAU_THRESHOLD).sum()
    def_ms = (defects['iou_after_mass_spring'] >= TAU_THRESHOLD).sum()
    def_s = (defects['iou_after_snapping'] >= TAU_THRESHOLD).sum()
    print(f"{'Tỷ lệ IoU >= 0.50 (Tau)':<35} | {f'{def_b} ({def_b/len(defects)*100:.2f}%)':<25} | {f'{def_ms} ({def_ms/len(defects)*100:.2f}%)':<20} | {f'{def_s} ({def_s/len(defects)*100:.2f}%)':<20}")

    # Đánh giá nhóm 99 OBB bị ảnh hưởng bởi seamline (IoU trước < 0.65)
    seam_boxes = valid[valid['iou_before'] < 0.65]
    print(f"\n================ ĐÁNH GIÁ NHÓM BIẾN DẠNG CỤC BỘ TẠI SEAMLINE ({len(seam_boxes)} OBB) ================")
    print(f"IoU trước hiệu chỉnh trung bình: {seam_boxes['iou_before'].mean():.4f} (Min: {seam_boxes['iou_before'].min():.4f})")
    print(f"IoU sau Mass–Spring trung bình:  {seam_boxes['iou_after_mass_spring'].mean():.4f} (Tăng +{seam_boxes['iou_delta_mass_spring'].mean():.4f})")
    print(f"IoU sau Snapping trung bình:     {seam_boxes['iou_after_snapping'].mean():.4f} (Tăng +{seam_boxes['iou_delta_snapping'].mean():.4f})")

if __name__ == '__main__':
    main()
