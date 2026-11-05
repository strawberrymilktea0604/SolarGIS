"""
Module: interpolate_panel_gaps.py
Thư mục: Bounding Box
Mục đích:
- Khai thác tính tuần hoàn không gian của bước lưới (Panel Spacing s0) để phát hiện
  và tự động nội suy các vị trí module PV bị AI bỏ sót do lóa sáng, tương phản kém
  hoặc đường ghép ảnh trên orthomosaic toàn cảnh 85m.
- Sử dụng dữ liệu OBB gốc từ PV_Coordinates_Ortho_Vung_1_20260929_0018.csv,
  ánh xạ sang không gian trắc địa 85m bằng mô hình Homography DLT Hartley.
- Đối chiếu, kiểm chứng sai số với mốc trắc địa tham chiếu bbox_centroid_export.csv
  thông qua cơ chế ghép cặp định danh GPS + AI.
- Xuất tệp kết quả CSV chuẩn hóa:
  PV_Interpolated_Gaps_Evaluation.csv (giữ nguyên detection gốc và bổ sung các vị trí ứng viên).
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
    if not os.path.exists(homo_csv):
        homo_csv = os.path.join(root_dir, "PV_Transformed_OBB_Homography_85m.csv")
        
    out_csv_bbox = os.path.join(script_dir, "PV_Interpolated_Gaps_Evaluation.csv")
    out_csv_root = os.path.join(root_dir, "PV_Interpolated_Gaps_Evaluation.csv")
    
    print("=== BẮT ĐẦU THUẬT TOÁN NỘI SUY KHOẢNG TRỐNG (INTERPOLATION) TRÊN DẢI PIN ===")
    print(f"1. Nạp CSV detection nguồn: {src_csv}")
    print(f"2. Nạp CSV mốc tham chiếu trắc địa: {ref_csv}")
    
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv)
    
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    df_homo['match_id'] = df_homo['match_id'].astype(str)
    
    # Ghép thông tin hàng/cột từ mốc tham chiếu
    merged = pd.merge(df_homo, df_ref[['match_id', 'String_ID', 'Row_ID', 'centroid_x', 'centroid_y']], on='match_id', how='left')
    valid = merged[merged['String_ID'].notna()].copy()
    print(f"Số lượng detection có thông tin cấu trúc hàng: {len(valid)} / {len(df_src)}")
    
    # Mốc tham chiếu chưa được phát hiện
    detected_ids = set(df_src['match_id'])
    undetected_ref = df_ref[~df_ref['match_id'].isin(detected_ids)].copy().reset_index(drop=True)
    print(f"Số lượng mốc trắc địa tham chiếu chưa có detection: {len(undetected_ref)}")
    
    ref_tree = cKDTree(undetected_ref[['centroid_x', 'centroid_y']].values)
    
    # Tham số thuật toán
    EPS_S = 0.35       # Sai lệch bước lưới tối đa (m)
    EPS_PERP = 0.40    # Sai lệch vuông góc tối đa (m)
    K_MAX = 4          # Số vị trí khuyết tối đa trong 1 khoảng
    STD_WIDTH = 1.956  # Chiều dài chuẩn module (m)
    STD_HEIGHT = 0.992 # Chiều rộng chuẩn module (m)
    
    all_records = []
    
    # 1. Thêm toàn bộ detection gốc vào bảng kết quả
    for idx, row in df_homo.iterrows():
        p_name = row['Point_Name']
        cx = row.get('Homo_Centroid_X_UTM', np.nan)
        cy = row.get('Homo_Centroid_Y_UTM', np.nan)
        cls_raw = row.get('Class', 'Unclassified')
        is_def = (cls_raw != 'Unclassified')
        
        all_records.append({
            'record_type': 'detection',
            'candidate_id': p_name,
            'source_left_id': np.nan,
            'source_right_id': np.nan,
            'candidate_cx': cx,
            'candidate_cy': cy,
            'estimated_theta': 0.0,
            'estimated_width': row.get('Quad_Length_m', STD_WIDTH),
            'estimated_height': row.get('Quad_Width_m', STD_HEIGHT),
            'gap_slots': 0,
            'interpolation_status': 'original_detection',
            'validation_note': f"Detection thực tế từ AI ({cls_raw}); IoU={row.get('IoU_Homo', 0)*100:.1f}%",
            'distance_to_ref_cm': row.get('Centroid_Err_Homo_cm', np.nan),
            'String_ID': row.get('Zone', ''),
            'Row_ID': np.nan
        })
        
    candidate_records = []
    gap_intervals_count = 0
    spacings_before = []
    spacings_after = []
    
    # 2. Xử lý từng hàng pin (String_ID, Row_ID)
    cand_counter = 1
    for (s_id, r_id), grp in valid.groupby(['String_ID', 'Row_ID']):
        if len(grp) < 2:
            continue
            
        grp_sorted = grp.sort_values('Homo_Centroid_X_UTM').reset_index(drop=True)
        coords = grp_sorted[['Homo_Centroid_X_UTM', 'Homo_Centroid_Y_UTM']].values
        n_pts = len(coords)
        
        diffs = np.diff(coords, axis=0)
        dist_vec = np.linalg.norm(diffs, axis=1)
        spacings_before.extend(dist_vec.tolist())
        
        # Bước lưới tham chiếu của hàng
        normal_spacings = dist_vec[(dist_vec >= 1.70) & (dist_vec <= 2.15)]
        s0 = float(np.median(normal_spacings)) if len(normal_spacings) > 0 else 1.904
        
        row_points_with_interp = []
        for i in range(n_pts):
            row_points_with_interp.append(coords[i])
            if i < n_pts - 1:
                p_a = coords[i]
                p_b = coords[i+1]
                p_a_id = grp_sorted.loc[i, 'Point_Name']
                p_b_id = grp_sorted.loc[i+1, 'Point_Name']
                
                D = dist_vec[i]
                k_hat = int(round(D / s0)) - 1
                
                if 1 <= k_hat <= K_MAX:
                    gap_intervals_count += 1
                    expected_D = (k_hat + 1) * s0
                    dev_s = abs(D - expected_D)
                    dev_perp = abs(p_b[1] - p_a[1])
                    
                    if dev_s <= EPS_S and dev_perp <= EPS_PERP:
                        # Hướng vector hàng pin
                        dx = p_b[0] - p_a[0]
                        dy = p_b[1] - p_a[1]
                        theta_deg = round(math.degrees(math.atan2(dy, dx)), 3)
                        
                        for j in range(1, k_hat + 1):
                            p_cand = p_a + (j / (k_hat + 1)) * (p_b - p_a)
                            row_points_with_interp.append(p_cand)
                            
                            # Đối soát mốc trắc địa QGIS
                            dist, nearest_idx = ref_tree.query(p_cand)
                            nearest_ref = undetected_ref.iloc[nearest_idx]
                            err_cm = round(dist * 100.0, 2)
                            
                            cand_id = f"INTERP_{s_id}_R{int(r_id)}_{cand_counter:04d}"
                            cand_counter += 1
                            
                            if err_cm <= 25.0:
                                status = "confirmed"
                                note = f"Khớp chính xác module thực tế {nearest_ref['match_id']} (sai số {err_cm:.1f} cm <= 25cm)"
                            elif err_cm <= 52.4:
                                status = "ambiguous"
                                note = f"Nằm trong Decision Margin (sai số {err_cm:.1f} cm <= 52.4cm); khớp module {nearest_ref['match_id']}"
                            else:
                                status = "candidate"
                                note = f"Ứng viên ngoài ngưỡng an toàn (sai số {err_cm:.1f} cm); cần kiểm tra ảnh raster"
                                
                            rec = {
                                'record_type': 'interpolated_candidate',
                                'candidate_id': cand_id,
                                'source_left_id': p_a_id,
                                'source_right_id': p_b_id,
                                'candidate_cx': round(p_cand[0], 4),
                                'candidate_cy': round(p_cand[1], 4),
                                'estimated_theta': theta_deg,
                                'estimated_width': STD_WIDTH,
                                'estimated_height': STD_HEIGHT,
                                'gap_slots': k_hat,
                                'interpolation_status': status,
                                'validation_note': note,
                                'distance_to_ref_cm': err_cm,
                                'String_ID': s_id,
                                'Row_ID': r_id
                            }
                            candidate_records.append(rec)
                            all_records.append(rec)
                            
        # Tính bước lưới sau khi nội suy trên hàng
        row_pts_arr = np.array(row_points_with_interp)
        row_pts_arr = row_pts_arr[np.argsort(row_pts_arr[:, 0])]
        diffs_after = np.diff(row_pts_arr, axis=0)
        dist_after = np.linalg.norm(diffs_after, axis=1)
        spacings_after.extend(dist_after.tolist())
        
    df_out = pd.DataFrame(all_records)
    df_cand = pd.DataFrame(candidate_records)
    
    # Xuất file CSV
    df_out.to_csv(out_csv_bbox, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_root, index=False, encoding='utf-8-sig')
    print(f"\n Xuất báo cáo CSV nội suy thành công tại:")
    print(f"  + {out_csv_bbox}")
    print(f"  + {out_csv_root}")
    
    # Thống kê kết quả
    N_input = len(df_src)
    G_gaps = gap_intervals_count
    K_candidates = len(df_cand)
    N_confirmed = len(df_cand[df_cand['interpolation_status'] == 'confirmed'])
    N_ambiguous = len(df_cand[df_cand['interpolation_status'] == 'ambiguous'])
    N_unconfirmed = len(df_cand[df_cand['interpolation_status'] == 'candidate'])
    
    P_confirmed = (N_confirmed / K_candidates) * 100.0 if K_candidates > 0 else 0
    P_decision_margin = ((N_confirmed + N_ambiguous) / K_candidates) * 100.0 if K_candidates > 0 else 0
    
    s_before_mean = np.mean(spacings_before)
    s_before_std = np.std(spacings_before)
    s_before_cv = (s_before_std / s_before_mean) * 100.0
    
    s_after_mean = np.mean(spacings_after)
    s_after_std = np.std(spacings_after)
    s_after_cv = (s_after_std / s_after_mean) * 100.0
    
    print("\n--- KẾT QUẢ ĐỊNH LƯỢNG THUẬT TOÁN NỘI SUY ---")
    print(f"1. Số detection đầu vào (N): {N_input}")
    print(f"2. Số khoảng trống phát hiện (G): {G_gaps}")
    print(f"3. Tổng số vị trí ứng viên nội suy (K): {K_candidates}")
    print(f"4. Số ứng viên khớp chính xác module thực tế (<= 25cm): {N_confirmed} ({P_confirmed:.2f}%)")
    print(f"5. Số ứng viên trong Decision Margin (<= 52.4cm): {N_confirmed + N_ambiguous} ({P_decision_margin:.2f}%)")
    print(f"6. Số ứng viên ngoài ngưỡng cần kiểm tra: {N_unconfirmed}")
    print(f"7. Sai số khoảng cách tâm ứng viên so với mốc trắc địa:")
    print(f"   - Mean: {df_cand['distance_to_ref_cm'].mean():.2f} cm")
    print(f"   - Median: {df_cand['distance_to_ref_cm'].median():.2f} cm")
    print(f"   - Min: {df_cand['distance_to_ref_cm'].min():.2f} cm | Max: {df_cand['distance_to_ref_cm'].max():.2f} cm")
    print(f"8. Bước lưới trước khi nội suy: Mean={s_before_mean:.3f}m, Std={s_before_std:.3f}m, CV={s_before_cv:.2f}%")
    print(f"9. Bước lưới sau khi nội suy:   Mean={s_after_mean:.3f}m, Std={s_after_std:.3f}m, CV={s_after_cv:.2f}%")

if __name__ == '__main__':
    main()
