"""
Module: evaluate_defect_decision_margin.py
Mục đích:
- Đánh giá tỷ lệ khống chế sai số trong Decision Margin (d_min ≈ 52.4 cm) cho toàn bộ 5.092 OBB,
  đặc biệt tập trung vào nhóm OBB khuyết tật nhiệt (SingleHotSpot, MultiHotSpot, Bypass, Mixed).
- Ánh xạ từ file detection PV_Coordinates_Ortho_Vung_1_20260929_0018.csv sang bản đồ toàn cảnh 85m.
- Sử dụng mốc tham chiếu thực địa từ bbox_centroid_export.csv làm ground truth.
- Sử dụng ghép cặp GPS + AI (Point_Name -> module_id) để đối soát.
- So sánh chi tiết 3 phương pháp: GPS thuần (Baseline), Affine (6 DOF) và Homography (8 DOF).
- Kiểm tra nguy cơ Panel Aliasing (gán nhầm sang tấm pin lân cận) dựa trên decision margin và IoU >= 0.5.
- Xuất file kết quả chuẩn: Bounding Box/PV_Defect_Decision_Margin_Evaluation.csv.
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

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_csv = os.path.join(script_dir, "..", "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
        
    ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(script_dir, "..", "bbox_centroid_export.csv")
        
    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    
    out_csv = os.path.join(script_dir, "PV_Defect_Decision_Margin_Evaluation.csv")
    
    print(f"Loading data...")
    print(f"Source: {src_csv}")
    print(f"Reference: {ref_csv}")
    print(f"Homography Precalculated: {homo_csv}")
    
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None

    # GPS + AI matching ID
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    
    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    
    # Merge with precomputed Homography & Affine metrics if available
    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Centroid_Err_Homo_cm', 'Centroid_Err_Affine_cm',
            'IoU_Homo', 'IoU_Affine', 'Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM',
            'Quad_Valid_Convex', 'Trang_Thai_Doi_Soat'
        ]], on='Point_Name', how='left')
    
    D_MARGIN_CM = 52.4
    
    records = []
    
    cls_meta = {
        'SingleHotSpot': {'vn': 'Điểm nóng đơn (Single HotSpot)', 'is_defect': True, 'sev': 'Trung bình'},
        'MultiHotSpot': {'vn': 'Đa điểm nóng (Multi HotSpot)', 'is_defect': True, 'sev': 'Nghiêm trọng'},
        'Bypass': {'vn': 'Hỏng Diode Bypass', 'is_defect': True, 'sev': 'Nghiêm trọng'},
        'Mixed': {'vn': 'Lỗi hỗn hợp (Mixed)', 'is_defect': True, 'sev': 'Cao'},
        'Unclassified': {'vn': 'Bình thường (Normal PV)', 'is_defect': False, 'sev': 'Bình thường'}
    }
    
    for idx, row in merged.iterrows():
        pt_name = row['Point_Name']
        int_code = row.get('Internal_Code_src', row.get('Internal_Code', ''))
        cls_raw = str(row['Class_src'] if 'Class_src' in row else row['Class']).strip()
        meta = cls_meta.get(cls_raw, {'vn': cls_raw, 'is_defect': cls_raw != 'Unclassified', 'sev': 'Khác'})
        is_defect = meta['is_defect']
        
        has_ref = pd.notna(row['module_id'])
        ref_x = float(row['centroid_x']) if has_ref else np.nan
        ref_y = float(row['centroid_y']) if has_ref else np.nan
        
        # 1. GPS Thuan
        gps_x = float(row['UTM_X']) if pd.notna(row['UTM_X']) else np.nan
        gps_y = float(row['UTM_Y']) if pd.notna(row['UTM_Y']) else np.nan
        if has_ref and not np.isnan(gps_x):
            err_gps_m = math.hypot(gps_x - ref_x, gps_y - ref_y)
            err_gps_cm = round(err_gps_m * 100.0, 2)
            in_margin_gps = "ĐẠT" if err_gps_cm <= D_MARGIN_CM else "VƯỢT_NGƯỠNG"
        else:
            err_gps_cm = np.nan
            in_margin_gps = "CHƯA_XÁC_ĐỊNH"
            
        # 2. Affine
        err_aff_cm = row.get('Centroid_Err_Affine_cm', np.nan)
        if pd.notna(err_aff_cm):
            err_aff_cm = round(float(err_aff_cm), 2)
            in_margin_aff = "ĐẠT" if err_aff_cm <= D_MARGIN_CM else "VƯỢT_NGƯỠNG"
        else:
            in_margin_aff = "CHƯA_XÁC_ĐỊNH"
        iou_aff = round(float(row.get('IoU_Affine', np.nan)), 4) if pd.notna(row.get('IoU_Affine', np.nan)) else np.nan
        
        # 3. Homography
        err_homo_cm = row.get('Centroid_Err_Homo_cm', np.nan)
        if pd.notna(err_homo_cm):
            err_homo_cm = round(float(err_homo_cm), 2)
            in_margin_homo = "ĐẠT" if err_homo_cm <= D_MARGIN_CM else "VƯỢT_NGƯỠNG"
        else:
            in_margin_homo = "CHƯA_XÁC_ĐỊNH"
        iou_homo = round(float(row.get('IoU_Homo', np.nan)), 4) if pd.notna(row.get('IoU_Homo', np.nan)) else np.nan
        
        homo_x = row.get('Homo_Centroid_X_UTM', np.nan)
        homo_y = row.get('Homo_Centroid_Y_UTM', np.nan)
        
        # Improvement
        if pd.notna(err_aff_cm) and pd.notna(err_homo_cm):
            impr_cm = round(err_aff_cm - err_homo_cm, 2)
        else:
            impr_cm = np.nan
            
        # Association status & Aliasing risk
        if not has_ref:
            assoc_status = "NGOAI_PHAM_VI_85M"
            aliasing_risk = "KHÔNG_XÁC_ĐỊNH"
        elif pd.notna(err_homo_cm):
            if err_homo_cm <= D_MARGIN_CM and (pd.isna(iou_homo) or iou_homo >= 0.5):
                assoc_status = "CHÍNH_XÁC_TOP1"
                aliasing_risk = "AN_TOÀN_TUYỆT_ĐỐI"
            elif err_homo_cm <= D_MARGIN_CM:
                assoc_status = "ĐẠT_MARGIN_IOU_THẤP"
                aliasing_risk = "CẦN_KIỂM_TRA_RẢNH"
            else:
                assoc_status = "VƯỢT_MARGIN"
                aliasing_risk = "NGUY_CƠ_NHẢY_TẤM"
        else:
            assoc_status = "CHƯA_RÕ"
            aliasing_risk = "CHƯA_RÕ"
            
        records.append({
            'Point_Name': pt_name,
            'Internal_Code': int_code,
            'match_id': row['match_id'],
            'Class': cls_raw,
            'Phan_Loai_VN': meta['vn'],
            'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
            'Muc_Do_Khuyet_Tat': meta['sev'],
            'Pixel_U_35m': row.get('Pixel_U', row.get('Pixel_U_src', np.nan)),
            'Pixel_V_35m': row.get('Pixel_V', row.get('Pixel_V_src', np.nan)),
            'Target_Ref_X_UTM': ref_x,
            'Target_Ref_Y_UTM': ref_y,
            'GPS_X_UTM': gps_x,
            'GPS_Y_UTM': gps_y,
            'GPS_Centroid_Err_cm': err_gps_cm,
            'GPS_In_Margin_52cm': in_margin_gps,
            'Affine_Centroid_Err_cm': err_aff_cm,
            'Affine_In_Margin_52cm': in_margin_aff,
            'Affine_IoU': iou_aff,
            'Homo_Centroid_X_UTM': homo_x,
            'Homo_Centroid_Y_UTM': homo_y,
            'Homo_Centroid_Err_cm': err_homo_cm,
            'Homo_In_Margin_52cm': in_margin_homo,
            'Homo_IoU': iou_homo,
            'Homo_Improvement_vs_Affine_cm': impr_cm,
            'Trang_Thai_Association': assoc_status,
            'Nguy_Co_Panel_Aliasing': aliasing_risk
        })
        
    out_df = pd.DataFrame(records)
    out_df.to_csv(out_csv, index=False, encoding='utf-8-sig')
    print(f"Exported successfully to: {out_csv}")
    
    # Summary on DEFECTS
    df_def = out_df[out_df['Is_Defect'] == 'CÓ']
    df_def_valid = df_def[df_def['Homo_Centroid_Err_cm'].notna()]
    print("\n=======================================================")
    print(f" TỔNG HỢP ĐỐI SOÁT DECISION MARGIN CHO NHÓM KHUYẾT TẬT")
    print("=======================================================")
    print(f"Tổng số OBB khuyết tật đầu vào: {len(df_def)}")
    print(f"Số OBB khuyết tật có tham chiếu hợp lệ (QGIS): {len(df_def_valid)}")
    print(f"Số OBB khuyết tật ngoài vùng tham chiếu: {len(df_def) - len(df_def_valid)}")
    
    for model, col, in_col in [
        ('GPS thuần', 'GPS_Centroid_Err_cm', 'GPS_In_Margin_52cm'),
        ('Affine 2D', 'Affine_Centroid_Err_cm', 'Affine_In_Margin_52cm'),
        ('Homography', 'Homo_Centroid_Err_cm', 'Homo_In_Margin_52cm')
    ]:
        valid_series = df_def_valid[col]
        in_m = (df_def_valid[in_col] == 'ĐẠT').sum()
        over_m = (df_def_valid[in_col] == 'VƯỢT_NGƯỠNG').sum()
        pct = in_m / len(df_def_valid) * 100.0
        print(f"\n[{model}]")
        print(f"  - Số ca trong margin (<= 52.4 cm): {in_m}/{len(df_def_valid)} ({pct:.2f}%)")
        print(f"  - Số ca vượt margin (> 52.4 cm):   {over_m}/{len(df_def_valid)} ({100-pct:.2f}%)")
        print(f"  - Sai số trung bình (Mean):        {valid_series.mean():.2f} cm")
        print(f"  - Sai số trung vị (Median):        {valid_series.median():.2f} cm")
        print(f"  - Sai số cực đại (Max Error):      {valid_series.max():.2f} cm")

    # Association Status count on Defects
    print("\n--- Trạng thái liên kết định danh (Association Status) nhóm Khuyết tật: ---")
    print(df_def['Trang_Thai_Association'].value_counts())
    print("\n--- Đánh giá nguy cơ Panel Aliasing nhóm Khuyết tật: ---")
    print(df_def['Nguy_Co_Panel_Aliasing'].value_counts())

if __name__ == '__main__':
    main()
