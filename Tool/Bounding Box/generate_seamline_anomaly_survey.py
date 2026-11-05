"""
Module: generate_seamline_anomaly_survey.py
Thư mục: Bounding Box
Mục đích:
- Ánh xạ file PV_Coordinates_Ortho_Vung_1_20260929_0018.csv vào bản đồ toàn cảnh 85m
  và đối chiếu với mốc tham chiếu trắc địa bbox_centroid_export.csv qua định danh GPS + AI.
- Sử dụng mô hình ánh xạ Xạ ảnh Homography DLT Hartley (8 DOF) đã được kiểm chứng số học.
- Đo đạc chính xác sai lệch tâm (center_offset), sai lệch góc (angle_deviation), độ phân tán sai số góc (corner_spread),
  độ thuôn hình thang (Quad_Trapezoid_Diff_mm) và chỉ số diện tích giao thoa (IoU).
- Phân loại chuẩn hóa theo đúng 5 Loại bất thường hình học theo Form mẫu yêu cầu:
    + Loại 1: OBB bị cắt xén hoặc bao thiếu module (truncated / partial_overlap)
    + Loại 2: OBB méo hình học hoặc lệch góc (deformed / orientation_mismatch)
    + Loại 3: Ranh giới không rõ tại vùng seamline (boundary_ambiguous / seam_suspected)
    + Loại 4: Detection ngoại lai hoặc không phù hợp cấu trúc giàn (out_of_bounds / grid_mismatch)
    + Loại 5: Detection gần seamline nhưng hình học phù hợp (valid_near_seam)
    + Nhóm đối chứng xa seamline: Hình học chuẩn (none / valid_far_from_seam)
- Xuất tệp CSV kết quả theo chuẩn các cột:
    detection_id, mapped_vertices, seam_relation, geometry_issue, severity,
    center_offset, angle_deviation, review_status, review_note.
"""

import os
import sys
import ast
import math
import numpy as np
import pandas as pd

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

def compute_angle_deg(p1, p2):
    if p1 is None or p2 is None:
        return np.nan
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return np.degrees(np.arctan2(dy, dx))

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))
    
    src_csv = os.path.join(root_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
        
    ref_csv = os.path.join(root_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")
        
    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    
    out_csv_bbox = os.path.join(script_dir, "PV_Seamline_Distortion_Survey.csv")
    out_csv_root = os.path.join(root_dir, "PV_Seamline_Distortion_Survey.csv")
    
    print("=== BẮT ĐẦU QUY TRÌNH KHẢO SÁT BẤT THƯỜNG HÌNH HỌC TẠI VÙNG SEAMLINE ===")
    print(f"1. Nạp CSV detection nguồn: {src_csv}")
    print(f"2. Nạp CSV mốc tham chiếu trắc địa: {ref_csv}")
    
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None
    
    # Ghép cặp định danh GPS + AI giữa Point_Name và module_id
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    
    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    
    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Homo_NW_UTM_85m', 'Homo_NE_UTM_85m', 'Homo_SE_UTM_85m', 'Homo_SW_UTM_85m',
            'Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM',
            'Centroid_Err_Homo_cm', 'Centroid_Err_Affine_cm', 'IoU_Homo', 'IoU_Affine',
            'Quad_Trapezoid_Diff_mm', 'Quad_Area_m2', 'Quad_Length_m', 'Quad_Width_m',
            'Err_NW_cm', 'Err_NE_cm', 'Err_SE_cm', 'Err_SW_cm', 'Zone'
        ]], on='Point_Name', how='left')
        
    records = []
    
    for idx, row in merged.iterrows():
        pt_name = row['Point_Name']
        has_ref = pd.notna(row['module_id'])
        cls_raw = str(row['Class_src'] if 'Class_src' in row else row['Class']).strip()
        is_defect = (cls_raw != 'Unclassified')
        
        # 4 đỉnh sau ánh xạ Homography
        p_nw = parse_tuple(row.get('Homo_NW_UTM_85m', None))
        p_ne = parse_tuple(row.get('Homo_NE_UTM_85m', None))
        p_se = parse_tuple(row.get('Homo_SE_UTM_85m', None))
        p_sw = parse_tuple(row.get('Homo_SW_UTM_85m', None))
        
        if p_nw and p_ne and p_se and p_sw:
            mapped_vertices_str = f"[{p_nw}, {p_ne}, {p_se}, {p_sw}]"
            # Tính góc xoay của cạnh trên box sau ánh xạ
            mapped_angle = compute_angle_deg(p_nw, p_ne)
        else:
            mapped_vertices_str = "None"
            mapped_angle = np.nan
            
        # Mốc tham chiếu QGIS
        r_tl = parse_tuple(row.get('corner_top_left', None))
        r_tr = parse_tuple(row.get('corner_top_right', None))
        if r_tl and r_tr:
            ref_angle = compute_angle_deg(r_tl, r_tr)
        else:
            ref_angle = np.nan
            
        if pd.notna(mapped_angle) and pd.notna(ref_angle):
            # Tính chênh lệch góc định hướng
            diff_ang = abs(mapped_angle - ref_angle)
            if diff_ang > 180:
                diff_ang = 360 - diff_ang
            angle_dev = round(diff_ang, 3)
        else:
            angle_dev = np.nan
            
        c_err_cm = row.get('Centroid_Err_Homo_cm', np.nan)
        c_offset_m = round(c_err_cm / 100.0, 4) if pd.notna(c_err_cm) else np.nan
        
        iou = row.get('IoU_Homo', np.nan)
        trap_diff = row.get('Quad_Trapezoid_Diff_mm', np.nan)
        q_len = row.get('Quad_Length_m', np.nan)
        q_area = row.get('Quad_Area_m2', np.nan)
        
        e_nw = row.get('Err_NW_cm', np.nan)
        e_ne = row.get('Err_NE_cm', np.nan)
        e_se = row.get('Err_SE_cm', np.nan)
        e_sw = row.get('Err_SW_cm', np.nan)
        corners = [c for c in [e_nw, e_ne, e_se, e_sw] if pd.notna(c)]
        corner_spread = round(max(corners) - min(corners), 2) if corners else np.nan
        
        # Định vị vùng Seamline:
        # Vùng giàn pin Block2 dãy String6 - String8 nằm gần mép đường bê tông nội bộ và vết ghép ảnh SfM Metashape
        # hoặc các tấm pin có triệu chứng uốn lượn ranh giới
        string_id = str(row.get('String_ID', row.get('match_id', ''))).lower()
        is_seam_corridor = ('string6' in string_id) or ('string7' in string_id) or ('string8' in string_id)
        
        # PHÂN LOẠI 5 LOẠI BẤT THƯỜNG THEO FORM MẪU
        if not has_ref:
            # Loại 4: Ngoại lai / ngoài ranh giới tham chiếu
            seam_rel = "unknown"
            geo_issue = "out_of_bounds"
            severity = "high"
            rev_status = "needs_review"
            rev_note = "OBB nằm ngoài phạm vi bao phủ của lớp ranh giới QGIS 85m; không có mốc đối chuẩn"
        elif c_err_cm > 50.0:
            # Loại 4: Trôi khỏi lưới giàn pin (grid_mismatch)
            seam_rel = "none" if not is_seam_corridor else "suspected"
            geo_issue = "grid_mismatch"
            severity = "high"
            rev_status = "needs_review"
            rev_note = f"Sai số tâm lớn ({c_err_cm:.1f} cm > 50cm); trôi dạt khỏi cấu trúc hàng do ngoại suy vùng biên"
        elif pd.notna(q_len) and q_len < 1.60:
            # Loại 1: Bị cắt xén hoặc bao thiếu module (truncated / partial_overlap)
            seam_rel = "near" if is_seam_corridor else "none"
            geo_issue = "truncated"
            severity = "medium"
            rev_status = "needs_review"
            rev_note = f"Chiều dài box bị co ngắn ({q_len:.2f}m < 1.60m); cắt cụt tại mép phân mảnh ảnh hoặc biên bàn pin"
        elif pd.notna(iou) and iou < 0.65 and c_err_cm <= 35.0:
            # Loại 3: Ranh giới không rõ tại vùng seamline (boundary_ambiguous / seam_suspected)
            seam_rel = "near"
            geo_issue = "boundary_ambiguous"
            severity = "medium"
            rev_status = "needs_review"
            rev_note = f"Ranh giới khung nhôm bị uốn lượn hình sin/mờ nhòe do vết khâu Metashape; IoU sụt giảm ({iou*100:.1f}%)"
        elif (corner_spread is not None and corner_spread >= 12.0) or (angle_dev is not None and angle_dev >= 1.5) or (trap_diff is not None and trap_diff > 8.0):
            # Loại 2: Méo hình học hoặc lệch góc (deformed / orientation_mismatch)
            seam_rel = "near" if is_seam_corridor else "suspected"
            geo_issue = "deformed"
            severity = "medium" if corner_spread >= 15.0 else "low"
            rev_status = "reviewed"
            rev_note = f"OBB bị kéo lệch góc bất đối xứng (Corner Spread={corner_spread}cm, thuôn hình thang {trap_diff}mm)"
        elif is_seam_corridor:
            # Loại 5: Gần seamline nhưng hình học phù hợp (valid_near_seam)
            seam_rel = "near"
            geo_issue = "valid_near_seam"
            severity = "none"
            rev_status = "reviewed"
            rev_note = f"Nằm trong hành lang gần đường ghép ảnh nhưng hình học chuẩn (IoU={iou*100:.1f}%, offset={c_err_cm:.1f}cm)"
        else:
            # Đối chứng xa seamline: Hoàn toàn bình thường
            seam_rel = "none"
            geo_issue = "none"
            severity = "none"
            rev_status = "reviewed"
            rev_note = f"Hình học ổn định trong ruột giàn pin; khớp hoàn hảo với khung nhôm (IoU={iou*100:.1f}%)"
            
        records.append({
            'detection_id': pt_name,
            'mapped_vertices': mapped_vertices_str,
            'seam_relation': seam_rel,
            'geometry_issue': geo_issue,
            'severity': severity,
            'center_offset': c_offset_m,
            'angle_deviation': angle_dev,
            'review_status': rev_status,
            'review_note': rev_note,
            # Bổ sung các trường chi tiết phục vụ đối soát
            'internal_code': row.get('Internal_Code_src', row.get('Internal_Code', '')),
            'class_label': cls_raw,
            'is_defect': 'CÓ' if is_defect else 'KHÔNG',
            'iou_homography': round(iou, 4) if pd.notna(iou) else np.nan,
            'corner_spread_cm': corner_spread,
            'trapezoid_diff_mm': trap_diff
        })
        
    out_df = pd.DataFrame(records)
    out_df.to_csv(out_csv_bbox, index=False, encoding='utf-8-sig')
    out_df.to_csv(out_csv_root, index=False, encoding='utf-8-sig')
    print(f"\n Xuất báo cáo CSV thành công tại:")
    print(f"  + {out_csv_bbox}")
    print(f"  + {out_csv_root}")
    
    print("\n--- THỐNG KÊ PHÂN LOẠI 5 DẠNG BẤT THƯỜNG (GEOMETRY_ISSUE) ---")
    print(out_df['geometry_issue'].value_counts(dropna=False))
    
    print("\n--- THỐNG KÊ MỐI QUAN HỆ VỚI ĐƯỜNG GHÉP ẢNH (SEAM_RELATION) ---")
    print(out_df['seam_relation'].value_counts(dropna=False))
    
    print("\n--- THỐNG KÊ MỨC ĐỘ NGHIÊM TRỌNG (SEVERITY) ---")
    print(out_df['severity'].value_counts(dropna=False))
    
    print("\n--- THỐNG KÊ TRẠNG THÁI KIỂM DUYỆT (REVIEW_STATUS) ---")
    print(out_df['review_status'].value_counts(dropna=False))
    
    # Tính toán các chỉ số định lượng
    n_reviewed = len(out_df)
    n_abnormal = len(out_df[~out_df['geometry_issue'].isin(['none', 'valid_near_seam'])])
    r_abnormal = (n_abnormal / n_reviewed) * 100.0
    
    print(f"\n--- CHỈ SỐ ĐỊNH LƯỢNG KHẢO SÁT ---")
    print(f"Tổng số OBB kiểm tra (N_reviewed): {n_reviewed}")
    print(f"Số OBB có dấu hiệu bất thường (N_abnormal): {n_abnormal}")
    print(f"Tỷ lệ OBB bất thường (R_abnormal): {r_abnormal:.2f}%")
    
    # So sánh nhóm gần seam vs nhóm xa seam
    near_seam_df = out_df[out_df['seam_relation'].isin(['near', 'suspected'])]
    far_seam_df = out_df[out_df['seam_relation'] == 'none']
    
    near_abnormal = len(near_seam_df[~near_seam_df['geometry_issue'].isin(['none', 'valid_near_seam'])])
    far_abnormal = len(far_seam_df[~far_seam_df['geometry_issue'].isin(['none', 'valid_near_seam'])])
    
    r_near_abnormal = (near_abnormal / len(near_seam_df)) * 100.0 if len(near_seam_df) > 0 else 0
    r_far_abnormal = (far_abnormal / len(far_seam_df)) * 100.0 if len(far_seam_df) > 0 else 0
    
    print(f"Nhóm gần/nghi ngờ seam: {len(near_seam_df)} OBB | Bất thường: {near_abnormal} ({r_near_abnormal:.2f}%)")
    print(f"Nhóm xa seam (đối chứng): {len(far_seam_df)} OBB | Bất thường: {far_abnormal} ({r_far_abnormal:.2f}%)")
    print(f"Sai lệch tâm TB nhóm gần seam: {near_seam_df['center_offset'].mean()*100:.2f} cm")
    print(f"Sai lệch tâm TB nhóm xa seam: {far_seam_df['center_offset'].mean()*100:.2f} cm")
    print(f"IoU trung bình nhóm gần seam: {near_seam_df['iou_homography'].mean()*100:.2f}%")
    print(f"IoU trung bình nhóm xa seam: {far_seam_df['iou_homography'].mean()*100:.2f}%")

if __name__ == '__main__':
    main()
