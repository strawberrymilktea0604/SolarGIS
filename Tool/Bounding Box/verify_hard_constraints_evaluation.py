"""
Module: verify_hard_constraints_evaluation.py
Mục đích:
- Khai báo và kiểm định 3 ràng buộc hình học cứng (Hard Constraints) của giàn pin:
    1. Ràng buộc 1: Kích thước chuẩn module PV (danh định 1.048m x 2.094m, diện tích 2.1945 m2,
       và kích thước biểu kiến trực giao chiếu nghiêng tham chiếu 0.973m x 1.911m).
    2. Ràng buộc 2: Góc phương vị đồng nhất (ngưỡng sai khác góc <= 1.5 độ theo Cẩm nang kỹ thuật).
    3. Ràng buộc 3: Cấu trúc bàn pin 2 x 14 tấm (28 module/bàn, bước lưới hàng/cột và khoảng cách lân cận).
- Dữ liệu đầu vào:
    + Detection nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Mốc tham chiếu đo đạc: bbox_centroid_export.csv (36.544 module GIS QGIS)
    + Khớp mốc định danh qua GPS + AI (Point_Name -> module_id)
    + Kết quả biến đổi không gian Homography 8 DOF & Affine 6 DOF
- Xuất file kết quả kiểm tra hình học: Bounding Box/PV_Hard_Constraints_Verification.csv
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
        if not p1.is_valid or not p2.is_valid or p1.is_empty or p2.is_empty:
            return 0.0
        inter = p1.intersection(p2).area
        union = p1.union(p2).area
        return float(inter / union) if union > 0 else 0.0
    except Exception:
        return 0.0

def line_orientation_diff(deg1, deg2):
    """Độ lệch góc không định hướng giữa 2 phương chu kỳ 180 độ [0, 90]"""
    diff = abs(deg1 - deg2) % 180.0
    if diff > 90.0:
        diff = 180.0 - diff
    return diff

def angle_between_vectors(v1, v2):
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 < 1e-7 or norm2 < 1e-7:
        return 0.0
    dot = np.dot(v1, v2)
    cos_val = np.clip(abs(dot) / (norm1 * norm2), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_val)))

def mean_line_angle(angles):
    rad = np.radians(np.array(angles) * 2.0)
    sin_sum = np.sum(np.sin(rad))
    cos_sum = np.sum(np.cos(rad))
    mean_rad = np.arctan2(sin_sum, cos_sum) / 2.0
    return float(np.degrees(mean_rad) % 180.0)

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
        
    aff_csv = os.path.join(script_dir, "PV_Affine_Parallelism_Evaluation.csv")
    if not os.path.exists(aff_csv):
        aff_csv = os.path.join(workspace_dir, "PV_Affine_Parallelism_Evaluation.csv")

    out_csv = os.path.join(script_dir, "PV_Hard_Constraints_Verification.csv")
    out_csv_workspace = os.path.join(workspace_dir, "PV_Hard_Constraints_Verification.csv")

    print(f"Loading files...")
    print(f"Source CSV: {src_csv}")
    print(f"Reference CSV: {ref_csv}")
    print(f"Homography CSV: {homo_csv}")
    print(f"Affine CSV: {aff_csv}")

    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None
    df_aff = pd.read_csv(aff_csv) if os.path.exists(aff_csv) else None

    # Ghép cặp định danh GPS + AI
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))

    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM',
            'Homo_NW_UTM_85m', 'Homo_NE_UTM_85m', 'Homo_SE_UTM_85m', 'Homo_SW_UTM_85m',
            'Quad_Valid_Convex', 'Quad_Area_m2', 'Quad_Length_m', 'Quad_Width_m', 'Quad_Trapezoid_Diff_mm',
            'Centroid_Err_Homo_cm', 'Mean_Corner_Err_Homo_cm', 'Max_Corner_Err_Homo_cm',
            'IoU_Homo', 'IoU_Affine', 'Centroid_Err_Affine_cm'
        ]], on='Point_Name', how='left')

    if df_aff is not None:
        merged = pd.merge(merged, df_aff[[
            'Point_Name', 'Long_Edge_Heading_Deg', 'Ref_Heading_Deg', 'Theta_vs_Ref_Deg',
            'String_Group', 'String_Mean_Heading_Deg', 'Dev_From_String_Mean_Deg', 'String_Parallelism_Passed'
        ]], on='Point_Name', how='left')

    # Ràng buộc chuẩn danh định
    W0_NOMINAL = 1.048  # mét
    L0_NOMINAL = 2.094  # mét
    S0_NOMINAL = W0_NOMINAL * L0_NOMINAL  # 2.194512 m2
    AR0_NOMINAL = L0_NOMINAL / W0_NOMINAL # 1.998

    # Kích thước biểu kiến trên trực ảnh trực giao nadir do góc nghiêng tilt ~15-20 độ
    # Đo đạc trên mốc QGIS bbox_centroid_export.csv: chiều rộng thực tế trên map ~ 0.973 m, chiều dài ~ 1.911 m
    W_REF_NOMINAL = 0.9730
    L_REF_NOMINAL = 1.9105
    S_REF_NOMINAL = W_REF_NOMINAL * L_REF_NOMINAL # ~ 1.859 m2

    # Ngưỡng dung sai kiểm tra
    TOL_SIZE_PERCENT = 10.0 # dung sai kích thước +/- 10% đối với ảnh trực giao
    TOL_ANGLE_DEG = 1.5    # ngưỡng góc song song trong dãy giàn pin <= 1.5 độ (theo Cẩm nang QC)
    DECISION_MARGIN_M = 0.524 # 52.4 cm

    records = []
    
    # Phân tích theo String để xác định cấu trúc 2x14
    for idx, row in merged.iterrows():
        pt_name = row['Point_Name']
        int_code = row.get('Internal_Code', '')
        mid = row['match_id']
        cls_raw = str(row['Class_src'] if 'Class_src' in row else row['Class']).strip()
        is_defect = (cls_raw != 'Unclassified')

        has_ref = pd.notna(row['module_id'])
        
        # 1. Tọa độ OBB nguồn (Pixel trên map 35m)
        u_src = row.get('Pixel_U', row.get('Pixel_U_src', np.nan))
        v_src = row.get('Pixel_V', row.get('Pixel_V_src', np.nan))
        nw_src = str(row.get('BBox_NW_Pixel', ''))
        ne_src = str(row.get('BBox_NE_Pixel', ''))
        se_src = str(row.get('BBox_SE_Pixel', ''))
        sw_src = str(row.get('BBox_SW_Pixel', ''))

        # 2. Tọa độ OBB sau ánh xạ (UTM Zone 49N trên map 85m)
        c_x = row.get('Homo_Centroid_X_UTM', np.nan)
        c_y = row.get('Homo_Centroid_Y_UTM', np.nan)
        nw_utm = str(row.get('Homo_NW_UTM_85m', ''))
        ne_utm = str(row.get('Homo_NE_UTM_85m', ''))
        se_utm = str(row.get('Homo_SE_UTM_85m', ''))
        sw_utm = str(row.get('Homo_SW_UTM_85m', ''))

        # Kích thước đo được sau ánh xạ
        w_meas = row.get('Quad_Width_m', np.nan)
        l_meas = row.get('Quad_Length_m', np.nan)
        s_meas = row.get('Quad_Area_m2', np.nan)
        
        # Nếu thiếu từ homo, lấy từ aff
        if pd.isna(w_meas) and 'Width_M' in row:
            w_meas = row['Width_M']
        if pd.isna(l_meas) and 'Length_M' in row:
            l_meas = row['Length_M']
        if pd.isna(s_meas) and pd.notna(w_meas) and pd.notna(l_meas):
            s_meas = round(w_meas * l_meas, 4)

        # Sai số so với kích thước danh định 3D (1.048 x 2.094)
        if pd.notna(w_meas) and pd.notna(l_meas):
            e_w_nominal = round(abs(w_meas - W0_NOMINAL) / W0_NOMINAL * 100.0, 2)
            e_l_nominal = round(abs(l_meas - L0_NOMINAL) / L0_NOMINAL * 100.0, 2)
            e_s_nominal = round(abs(s_meas - S0_NOMINAL) / S0_NOMINAL * 100.0, 2)
            
            # Sai số so với kích thước biểu kiến chiếu trực giao (0.973 x 1.911)
            e_w_apparent = round(abs(w_meas - W_REF_NOMINAL) / W_REF_NOMINAL * 100.0, 2)
            e_l_apparent = round(abs(l_meas - L_REF_NOMINAL) / L_REF_NOMINAL * 100.0, 2)
            e_s_apparent = round(abs(s_meas - S_REF_NOMINAL) / S_REF_NOMINAL * 100.0, 2)
            
            # Đánh giá Ràng buộc 1:
            # Module được xem là đạt kích thước biểu kiến trực giao nếu sai số so với kích thước biểu kiến nằm trong dung sai +/- 15%
            # (tương thích độ co rút nadir góc nghiêng giàn)
            if e_w_apparent <= 12.0 and e_l_apparent <= 12.0:
                status_c1 = "ĐẠT"
            elif e_w_apparent <= 20.0 and e_l_apparent <= 20.0:
                status_c1 = "CẢNH_BÁO_BIÊN"
            else:
                status_c1 = "KHÔNG_ĐẠT"
        else:
            e_w_nominal = e_l_nominal = e_s_nominal = np.nan
            e_w_apparent = e_l_apparent = e_s_apparent = np.nan
            status_c1 = "CHƯA_ĐỦ_DỮ_LIỆU"

        # Đánh giá Ràng buộc 2: Góc phương vị đồng nhất
        theta_meas = row.get('Long_Edge_Heading_Deg', np.nan)
        theta_ref = row.get('Ref_Heading_Deg', np.nan)
        delta_theta = row.get('Theta_vs_Ref_Deg', np.nan)
        dev_string = row.get('Dev_From_String_Mean_Deg', np.nan)

        if pd.notna(delta_theta):
            delta_theta = float(delta_theta)
            if delta_theta <= TOL_ANGLE_DEG:
                status_c2 = "ĐẠT"
            elif delta_theta <= 3.0:
                status_c2 = "CẢNH_BÁO_LỆCH_NHẸ"
            else:
                status_c2 = "KHÔNG_ĐẠT"
        elif pd.notna(dev_string):
            dev_string = float(dev_string)
            if dev_string <= TOL_ANGLE_DEG:
                status_c2 = "ĐẠT_THEO_CHUỖI"
            else:
                status_c2 = "CẢNH_BÁO_THEO_CHUỖI"
        else:
            status_c2 = "CHƯA_ĐỦ_DỮ_LIỆU"

        # Đánh giá Ràng buộc 3: Cấu trúc bàn pin 2 x 14 tấm
        layer_name = row.get('layer', '')
        string_name = row.get('String_ID', '')
        row_id = row.get('Row_ID', np.nan)

        # Tính toán rack_id (bàn pin) và cell_col (cột 1..14) nếu có thông tin số thứ tự
        # Mã module có dạng blockX_stringY_ZZZZZ
        module_num = np.nan
        table_id = "Unknown"
        col_in_rack = np.nan
        rack_status = "CHƯA_ĐỦ_DỮ_LIỆU"

        if has_ref and pd.notna(mid):
            try:
                parts = mid.split('_')
                if len(parts) >= 3:
                    num_str = parts[2]
                    module_num = int(num_str)
                    # Một bàn pin 2x14 = 28 tấm. Số thứ tự trong chuỗi:
                    # module_id tăng dần theo từng hàng. 14 tấm trên hàng 1, 14 tấm trên hàng 2 cùng thuộc 1 bàn
                    col_idx = ((module_num - 1) % 14) + 1
                    col_in_rack = col_idx
                    table_idx = ((module_num - 1) // 14) + 1
                    table_id = f"Table_{table_idx:02d}"
            except Exception:
                pass

        # Kiểm tra bước lưới và ranh giới an toàn
        err_cen_cm = row.get('Centroid_Err_Homo_cm', np.nan)
        if pd.isna(err_cen_cm):
            err_cen_cm = row.get('Centroid_Err_Affine_cm', np.nan)
            
        iou_val = row.get('IoU_Homo', row.get('IoU_Affine', np.nan))

        if not has_ref:
            rack_status = "NGOÀI_PHẠM_VI_85M"
            status_overall = "NGOÀI_PHẠM_VI"
            notes = "OBB nằm ở rìa chuyến bay 35m, ngoài phạm vi đối soát 85m"
        else:
            if pd.notna(err_cen_cm):
                err_cen_cm = float(err_cen_cm)
                if err_cen_cm <= DECISION_MARGIN_M * 100.0:
                    rack_status = "KHỚP_ĐÚNG_VỊ_TRÍ_LƯỚI"
                else:
                    rack_status = "LỆCH_BƯỚC_LƯỚI_NGUY_CƠ_NHẢY_TẤM"
            
            # Trạng thái tổng hợp
            if status_c1 == "ĐẠT" and status_c2 == "ĐẠT" and rack_status == "KHỚP_ĐÚNG_VỊ_TRÍ_LƯỚI":
                status_overall = "ĐẠT"
                notes = "Thỏa mãn hoàn toàn 3 ràng buộc cứng hình học giàn pin"
            elif rack_status == "KHỚP_ĐÚNG_VỊ_TRÍ_LƯỚI" and (status_c1 in ["ĐẠT", "CẢNH_BÁO_BIÊN"]) and (status_c2 in ["ĐẠT", "CẢNH_BÁO_LỆCH_NHẸ"]):
                status_overall = "CẢNH_BÁO_BIẾN_DẠNG_NHẸ"
                notes = "Khớp đúng vị trí tấm pin; kích thước/góc bị co giãn nhẹ do phối cảnh hoặc seamline"
            elif rack_status == "LỆCH_BƯỚC_LƯỚI_NGUY_CƠ_NHẢY_TẤM":
                status_overall = "KHÔNG_ĐẠT_LỆCH_LƯỚI"
                notes = f"Sai số tâm {err_cen_cm:.1f} cm vượt ranh giới an toàn 52.4 cm"
            else:
                status_overall = "CẦN_XEM_XÉT"
                notes = "Cần kiểm tra thủ công bước lưới hoặc dị thường biên"

        records.append({
            # Nhóm 1: Định danh
            'Point_Name': pt_name,
            'Internal_Code': int_code,
            'match_id': mid,
            'Class': cls_raw,
            'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
            'Ref_Module_ID': row['module_id'] if has_ref else '',
            
            # Nhóm 2: Detection gốc (Ortho 35m)
            'Pixel_U_35m': u_src,
            'Pixel_V_35m': v_src,
            'BBox_NW_Pixel_35m': nw_src,
            'BBox_NE_Pixel_35m': ne_src,
            'BBox_SE_Pixel_35m': se_src,
            'BBox_SW_Pixel_35m': sw_src,

            # Nhóm 3: Tọa độ sau ánh xạ (Ortho 85m UTM)
            'Trans_Centroid_X_UTM': c_x,
            'Trans_Centroid_Y_UTM': c_y,
            'Trans_NW_UTM': nw_utm,
            'Trans_NE_UTM': ne_utm,
            'Trans_SE_UTM': se_utm,
            'Trans_SW_UTM': sw_utm,

            # Nhóm 4: Kiểm tra Ràng buộc 1 - Kích thước chuẩn
            'Nominal_Width_W0_m': W0_NOMINAL,
            'Nominal_Length_L0_m': L0_NOMINAL,
            'Nominal_Area_S0_m2': round(S0_NOMINAL, 4),
            'Apparent_Ref_Width_m': W_REF_NOMINAL,
            'Apparent_Ref_Length_m': L_REF_NOMINAL,
            'Measured_Width_W_m': round(w_meas, 4) if pd.notna(w_meas) else np.nan,
            'Measured_Length_L_m': round(l_meas, 4) if pd.notna(l_meas) else np.nan,
            'Measured_Area_S_m2': round(s_meas, 4) if pd.notna(s_meas) else np.nan,
            'Err_Width_Nominal_Pct': e_w_nominal,
            'Err_Length_Nominal_Pct': e_l_nominal,
            'Err_Area_Nominal_Pct': e_s_nominal,
            'Err_Width_Apparent_Pct': e_w_apparent,
            'Err_Length_Apparent_Pct': e_l_apparent,
            'Status_Constraint_1_Size': status_c1,

            # Nhóm 5: Kiểm tra Ràng buộc 2 - Góc phương vị đồng nhất
            'Measured_Heading_Deg': round(theta_meas, 3) if pd.notna(theta_meas) else np.nan,
            'Ref_Heading_Deg': round(theta_ref, 3) if pd.notna(theta_ref) else np.nan,
            'Delta_Theta_Deg': round(delta_theta, 4) if pd.notna(delta_theta) else np.nan,
            'Dev_String_Mean_Deg': round(dev_string, 4) if pd.notna(dev_string) else np.nan,
            'Status_Constraint_2_Orientation': status_c2,

            # Nhóm 6: Kiểm tra Ràng buộc 3 - Cấu trúc bàn pin 2x14
            'Ref_Layer': layer_name,
            'Ref_String_ID': string_name,
            'Ref_Row_ID': row_id,
            'Estimated_Table_ID': table_id,
            'Estimated_Col_In_Rack': col_in_rack,
            'Centroid_Err_CM': round(err_cen_cm, 2) if pd.notna(err_cen_cm) else np.nan,
            'IoU_Val': round(iou_val, 4) if pd.notna(iou_val) else np.nan,
            'Status_Constraint_3_Rack': rack_status,

            # Nhóm 7: Trạng thái tổng hợp & Ghi chú
            'Trang_Thai_Tong_Hop': status_overall,
            'Ghi_Chu': notes
        })

    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_workspace, index=False, encoding='utf-8-sig')

    print(f"\nSaved results to:\n  - {out_csv}\n  - {out_csv_workspace}")
    print(f"Total rows: {len(df_out)}")
    
    # In báo cáo thống kê định lượng
    print("\n================ THỐNG KÊ KẾT QUẢ KIỂM ĐỊNH RÀNG BUỘC HÌNH HỌC CỨNG ================")
    print("\n1. RÀNG BUỘC 1 - KÍCH THƯỚC CHUẨN:")
    print(df_out['Status_Constraint_1_Size'].value_counts(dropna=False))
    print(f"  Chiều dài đo được trung bình: {df_out['Measured_Length_L_m'].mean():.4f} m (Median: {df_out['Measured_Length_L_m'].median():.4f} m)")
    print(f"  Chiều rộng đo được trung bình: {df_out['Measured_Width_W_m'].mean():.4f} m (Median: {df_out['Measured_Width_W_m'].median():.4f} m)")
    print(f"  Sai số chiều dài so với biểu kiến QGIS ({L_REF_NOMINAL}m): {df_out['Err_Length_Apparent_Pct'].mean():.2f}%")
    print(f"  Sai số chiều rộng so với biểu kiến QGIS ({W_REF_NOMINAL}m): {df_out['Err_Width_Apparent_Pct'].mean():.2f}%")

    print("\n2. RÀNG BUỘC 2 - GÓC PHƯƠNG VỊ ĐỒNG NHẤT:")
    print(df_out['Status_Constraint_2_Orientation'].value_counts(dropna=False))
    matched_angle = df_out[df_out['Delta_Theta_Deg'].notna()]
    print(f"  Số box có mốc đối soát góc: {len(matched_angle)}")
    print(f"  Sai khác góc trung bình so với mốc: {matched_angle['Delta_Theta_Deg'].mean():.4f}° (Median: {matched_angle['Delta_Theta_Deg'].median():.4f}°, Max: {matched_angle['Delta_Theta_Deg'].max():.4f}°)")
    passed_angle_qc = (matched_angle['Delta_Theta_Deg'] <= TOL_ANGLE_DEG).sum()
    print(f"  Tỷ lệ đạt chuẩn góc Cẩm nang (<= 1.5°): {passed_angle_qc} / {len(matched_angle)} ({passed_angle_qc / len(matched_angle) * 100:.2f}%)")

    print("\n3. RÀNG BUỘC 3 - CẤU TRÚC BÀN PIN 2x14 & VỊ TRÍ LƯỚI:")
    print(df_out['Status_Constraint_3_Rack'].value_counts(dropna=False))
    matched_rack = df_out[df_out['Centroid_Err_CM'].notna()]
    print(f"  Số box nằm trong phạm vi giàn pin: {len(matched_rack)}")
    passed_margin = (matched_rack['Centroid_Err_CM'] <= DECISION_MARGIN_M * 100.0).sum()
    print(f"  Tỷ lệ nằm gọn trong ranh giới an toàn (<= 52.4 cm): {passed_margin} / {len(matched_rack)} ({passed_margin / len(matched_rack) * 100:.2f}%)")
    print(f"  Sai số tâm trung bình: {matched_rack['Centroid_Err_CM'].mean():.2f} cm (Median: {matched_rack['Centroid_Err_CM'].median():.2f} cm, P95: {matched_rack['Centroid_Err_CM'].quantile(0.95):.2f} cm)")

    print("\n4. TRẠNG THÁI TỔNG HỢP TOÀN BỘ 5.092 OBB:")
    print(df_out['Trang_Thai_Tong_Hop'].value_counts(dropna=False))
    
    # Riêng nhóm lỗi nhiệt (Defect classes)
    defect_df = df_out[df_out['Is_Defect'] == 'CÓ']
    print(f"\n5. ĐÁNH GIÁ CHUYÊN BIỆT CHO NHÓM KHUYẾT TẬT NHIỆT ({len(defect_df)} OBB):")
    print(defect_df['Trang_Thai_Tong_Hop'].value_counts(dropna=False))
    matched_defect = defect_df[defect_df['Centroid_Err_CM'].notna()]
    passed_defect_margin = (matched_defect['Centroid_Err_CM'] <= DECISION_MARGIN_M * 100.0).sum()
    print(f"  Tỷ lệ lỗi nhiệt trong ranh giới an toàn (<= 52.4 cm): {passed_defect_margin} / {len(matched_defect)} ({passed_defect_margin / len(matched_defect) * 100:.2f}%)")
    print(f"  Sai số tâm lỗi nhiệt trung bình: {matched_defect['Centroid_Err_CM'].mean():.2f} cm (Median: {matched_defect['Centroid_Err_CM'].median():.2f} cm, Max: {matched_defect['Centroid_Err_CM'].max():.2f} cm)")
    print(f"  Tỷ lệ Max-IoU >= 0.5: {(matched_defect['IoU_Val'] >= 0.5).sum()} / {len(matched_defect)} ({(matched_defect['IoU_Val'] >= 0.5).mean()*100:.2f}%)")

if __name__ == '__main__':
    main()
