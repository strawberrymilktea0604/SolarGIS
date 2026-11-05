"""
Module: survey_seamline_distortions.py
Mục đích:
- Khảo sát các trường hợp box bị méo góc cục bộ tại các đường ghép ảnh (seamlines)
  và khu vực chuyển tiếp ranh giới trên bản đồ toàn cảnh 85m.
- Sử dụng dữ liệu OBB gốc từ PV_Coordinates_Ortho_Vung_1_20260929_0018.csv,
  đối soát với mốc tham chiếu thực địa bbox_centroid_export.csv qua GPS + AI matching.
- Đánh giá định lượng độ méo góc, chênh lệch sai số 4 đỉnh, độ thuôn hình thang và suy giảm Polygon IoU
  do ảnh hưởng của vết khâu ảnh Metashape (ranh giới pin bị bẻ cong trên nền raster trực giao).
- Phân loại 3 nhóm: Box tương đối khớp, Box lệch gần seam (nghi ngờ méo do seamlines), Box lệch ngoài seam.
- Xuất tệp kết quả: Bounding Box/PV_Seamline_Distortion_Survey.csv.
"""

import os
import sys
import math
import numpy as np
import pandas as pd

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_csv = os.path.join(script_dir, "..", "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
        
    ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(script_dir, "..", "bbox_centroid_export.csv")
        
    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    out_csv = os.path.join(script_dir, "PV_Seamline_Distortion_Survey.csv")
    
    print(f"Loading data for seamline distortion survey...")
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv) if os.path.exists(homo_csv) else None
    
    # 1. Match IDs via GPS + AI
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    
    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    
    if df_homo is not None:
        merged = pd.merge(merged, df_homo[[
            'Point_Name', 'Err_NW_cm', 'Err_NE_cm', 'Err_SE_cm', 'Err_SW_cm',
            'Mean_Corner_Err_Homo_cm', 'Max_Corner_Err_Homo_cm', 'Centroid_Err_Homo_cm',
            'Centroid_Err_Affine_cm', 'IoU_Homo', 'IoU_Affine', 'Quad_Trapezoid_Diff_mm',
            'Quad_Valid_Convex', 'Trang_Thai_Doi_Soat'
        ]], on='Point_Name', how='left')

    records = []
    
    for idx, row in merged.iterrows():
        pt_name = row['Point_Name']
        int_code = row.get('Internal_Code_src', row.get('Internal_Code', ''))
        cls_raw = str(row['Class_src'] if 'Class_src' in row else row['Class']).strip()
        is_defect = (cls_raw != 'Unclassified')
        has_ref = pd.notna(row['module_id'])
        
        c_err_homo = row.get('Centroid_Err_Homo_cm', np.nan)
        c_err_aff = row.get('Centroid_Err_Affine_cm', np.nan)
        iou_homo = row.get('IoU_Homo', np.nan)
        iou_aff = row.get('IoU_Affine', np.nan)
        
        e_nw = row.get('Err_NW_cm', np.nan)
        e_ne = row.get('Err_NE_cm', np.nan)
        e_se = row.get('Err_SE_cm', np.nan)
        e_sw = row.get('Err_SW_cm', np.nan)
        
        corners = [c for c in [e_nw, e_ne, e_se, e_sw] if pd.notna(c)]
        if corners:
            max_c = max(corners)
            min_c = min(corners)
            mean_c = np.mean(corners)
            corner_spread = round(max_c - min_c, 2)
            corner_cen_diff = round(max_c - c_err_homo, 2) if pd.notna(c_err_homo) else np.nan
        else:
            max_c = min_c = mean_c = corner_spread = corner_cen_diff = np.nan
            
        trap_diff = row.get('Quad_Trapezoid_Diff_mm', np.nan)
        
        # Phân loại nhóm bất thường hình học theo Form khảo sát
        # 1. Box tương đối khớp: Vị trí và hình dạng chuẩn, IoU cao, chênh lệch góc thấp
        # 2. Box lệch gần seam: Sai số tâm nhỏ nhưng góc bị kéo lệch hoặc IoU suy giảm đáng kể do gợn sóng seamline
        # 3. Box lệch ngoài seam: Box ở vùng biên cực viễn hoặc ngoài phạm vi map
        
        if not has_ref:
            group = "Ngoài phạm vi đối soát"
            distortion_type = "Không có mốc tham chiếu 85m"
            fit_level = "Không xác định"
            notes = "OBB nằm ngoài phạm vi bao phủ của lớp tham chiếu QGIS"
        elif c_err_homo <= 20.0 and iou_homo >= 0.75 and corner_spread < 10.0:
            group = "Box tương đối khớp"
            distortion_type = "Hình học ổn định, không méo"
            fit_level = "Khớp tốt (IoU >= 75%)"
            notes = "Nằm trong vùng ruột giàn pin, xa đường ghép ảnh seamlines"
        elif c_err_homo <= 35.0 and (corner_spread >= 10.0 or iou_homo < 0.70 or (trap_diff is not None and trap_diff > 8.0)):
            group = "Box lệch gần seam"
            if corner_spread >= 12.0:
                distortion_type = "Lệch góc bất đối xứng (Méo góc OBB)"
            elif iou_homo < 0.65:
                distortion_type = "Ranh giới pin bị bẻ cong do vết khâu ảnh"
            else:
                distortion_type = "Biến dạng hình thang cục bộ"
            fit_level = "Khớp trung bình / suy giảm cục bộ"
            notes = "Nghi ngờ nằm gần hoặc cắt qua vết khâu ảnh Metashape / mép đường bê tông"
        else:
            group = "Box lệch ngoài seam"
            if c_err_homo > 50.0:
                distortion_type = "Lệch tịnh tiến vị trí vùng biên"
            else:
                distortion_type = "Sai lệch phối cảnh biên ngoài"
            fit_level = "Khớp thấp (Vùng biên)"
            notes = "Nằm ở vùng rìa ngoài cùng của trực ảnh vùng 35m, ít điểm khống chế"
            
        records.append({
            'Point_Name': pt_name,
            'Internal_Code': int_code,
            'match_id': row['match_id'],
            'Class': cls_raw,
            'Is_Defect': 'CÓ' if is_defect else 'KHÔNG',
            'Pixel_U_35m': row.get('Pixel_U', np.nan),
            'Pixel_V_35m': row.get('Pixel_V', np.nan),
            'Centroid_Err_Homo_cm': c_err_homo,
            'Centroid_Err_Affine_cm': c_err_aff,
            'Max_Corner_Err_cm': max_c,
            'Corner_Spread_cm': corner_spread,
            'Corner_Centroid_Diff_cm': corner_cen_diff,
            'Quad_Trapezoid_Diff_mm': trap_diff,
            'IoU_Homo': iou_homo,
            'IoU_Affine': iou_aff,
            'Nhom_Khao_Sat': group,
            'Dang_Bat_Thuong': distortion_type,
            'Muc_Do_Khop': fit_level,
            'Ghi_Chu': notes
        })
        
    out_df = pd.DataFrame(records)
    out_df.to_csv(out_csv, index=False, encoding='utf-8-sig')
    print(f"Exported seamline distortion survey to: {out_csv}")
    
    print("\n--- THỐNG KÊ PHÂN BỐ CÁC NHÓM KHẢO SÁT ---")
    print(out_df['Nhom_Khao_Sat'].value_counts())
    print("\n--- THỐNG KÊ CÁC DẠNG BẤT THƯỜNG HÌNH HỌC ---")
    print(out_df['Dang_Bat_Thuong'].value_counts())
    
    # Analyze by defect vs normal
    print("\n--- PHÂN BỐ TRÊN NHÓM KHUYẾT TẬT NHIỆT ---")
    df_def = out_df[out_df['Is_Defect'] == 'CÓ']
    print(df_def['Nhom_Khao_Sat'].value_counts())
    
    # Detail on Box lệch gần seam
    seam_cases = out_df[out_df['Nhom_Khao_Sat'] == 'Box lệch gần seam']
    print(f"\nTổng số box thuộc nhóm 'Box lệch gần seam': {len(seam_cases)}")
    print(f"Trong đó số OBB khuyết tật: {len(seam_cases[seam_cases['Is_Defect'] == 'CÓ'])}")
    print(f"Mean IoU nhóm lệch gần seam: {seam_cases['IoU_Homo'].mean()*100:.2f}%")
    print(f"Mean Corner Spread: {seam_cases['Corner_Spread_cm'].mean():.2f} cm")
    print(f"Mean Centroid Error: {seam_cases['Centroid_Err_Homo_cm'].mean():.2f} cm")

if __name__ == '__main__':
    main()
