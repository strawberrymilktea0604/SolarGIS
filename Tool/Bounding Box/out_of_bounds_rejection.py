"""
Module: out_of_bounds_rejection.py
Thư mục: Bounding Box
Mục đích:
- Thiết lập cơ chế tự động gạt bỏ các hộp bao rác (Out-of-bounds Rejection)
  sau khi ánh xạ từ trực ảnh vùng (35m) sang trực ảnh toàn cảnh (85m).
- Hiện thực hóa khái niệm "lực đẩy đồ thị vô hạn" (Infinite Graph Repulsion Force)
  dưới dạng ràng buộc đào thải cứng (Hard Rejection Constraint, E_out = +inf)
  để tự động loại bỏ các box rác lơ lửng ngoài hành lang do cỏ dại, bóng đổ hoặc trôi biên.
- Kiểm tra hai cấp độ ràng buộc:
    1. Ràng buộc hành lang không gian C: Tỷ lệ diện tích giao rho_i = Area(B_i cap C) / Area(B_i).
    2. Ràng buộc cấu trúc lưới: Khoảng cách tới mốc lưới gần nhất d_i^grid = min_j ||p_i - g_j||_2
       so với ngưỡng Decision Margin d_max = 0.524m.
- Dữ liệu đầu vào:
    + Detection nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
    + Mốc trắc địa tham chiếu: bbox_centroid_export.csv (36.544 module GIS QGIS)
    + Tọa độ sau ánh xạ Homography: PV_Transformed_OBB_Homography_85m.csv
- Xuất tệp kết quả CSV chuẩn hóa:
  PV_Out_of_Bounds_Rejection_Evaluation.csv (bảo toàn toàn bộ detection gốc và bổ sung trạng thái duyệt).
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
    
    src_csv = os.path.join(root_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
    if not os.path.exists(src_csv):
        src_csv = os.path.join(script_dir, "PV_Coordinates_Ortho_Vung_1_20260929_0018.csv")
        
    ref_csv = os.path.join(root_dir, "bbox_centroid_export.csv")
    if not os.path.exists(ref_csv):
        ref_csv = os.path.join(script_dir, "bbox_centroid_export.csv")
        
    homo_csv = os.path.join(script_dir, "PV_Transformed_OBB_Homography_85m.csv")
    if not os.path.exists(homo_csv):
        homo_csv = os.path.join(root_dir, "PV_Transformed_OBB_Homography_85m.csv")
        
    out_csv_bbox = os.path.join(script_dir, "PV_Out_of_Bounds_Rejection_Evaluation.csv")
    out_csv_root = os.path.join(root_dir, "PV_Out_of_Bounds_Rejection_Evaluation.csv")
    
    print("=== BẮT ĐẦU CƠ CHẾ GẠT BỎ HỘP BAO RÁC (OUT-OF-BOUNDS REJECTION) ===")
    print(f"1. Nạp CSV detection nguồn: {src_csv}")
    print(f"2. Nạp CSV mốc tham chiếu trắc địa: {ref_csv}")
    
    df_src = pd.read_csv(src_csv)
    df_ref = pd.read_csv(ref_csv)
    df_homo = pd.read_csv(homo_csv)
    
    # Chuẩn hóa match_id
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: str(x).split(' ')[0].split('(')[0].replace('Pblock2', 'block2').strip() if pd.notna(x) else '')
    df_ref['match_id'] = df_ref['module_id'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    df_homo['match_id'] = df_homo['match_id'].astype(str)
    
    # Thiết lập cây KD-Tree mốc trắc địa tham chiếu toàn cảnh 85m
    ref_coords = df_ref[['centroid_x', 'centroid_y']].values
    ref_tree = cKDTree(ref_coords)
    
    # Xây dựng hành lang giàn pin C:
    # Lấy phạm vi giàn pin của Block 2 (các chuỗi từ string6 đến string21) từ mốc QGIS
    strings_block2 = [f"string{i}" for i in range(6, 22)]
    ref_b2 = df_ref[df_ref['String_ID'].isin(strings_block2)].copy()
    
    # Tạo hành lang bằng hợp các bounding box của từng bàn pin / hàng pin có đệm biên an toàn (buffer 0.35m)
    # Để tính toán nhanh và chuẩn xác:
    row_boxes = []
    for (s_id, r_id), grp in ref_b2.groupby(['String_ID', 'Row_ID']):
        b_geom = box(grp['min_x'].min(), grp['min_y'].min(), grp['max_x'].max(), grp['max_y'].max()).buffer(0.35)
        row_boxes.append(b_geom)
    corridor_C = unary_union(row_boxes)
    print("Đã thiết lập hành lang giàn pin hợp lệ C thành công.")
    
    D_MAX = 0.524       # Ngưỡng Decision Margin (m)
    TAU_C = 0.60        # Ngưỡng tỷ lệ diện tích nằm trong hành lang tối thiểu
    
    records = []
    
    for idx, row in df_homo.iterrows():
        p_name = row['Point_Name']
        cx = row['Homo_Centroid_X_UTM']
        cy = row['Homo_Centroid_Y_UTM']
        cls_raw = row.get('Class', 'Unclassified')
        is_defect = (cls_raw != 'Unclassified')
        
        # 4 đỉnh sau ánh xạ
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
            
        # Tính khoảng cách tới mốc lưới gần nhất
        grid_dist, nearest_idx = ref_tree.query([cx, cy])
        grid_dist = round(float(grid_dist), 4)
        nearest_mod_id = df_ref.iloc[nearest_idx]['module_id']
        
        # Xác định trạng thái hành lang (corridor_status)
        if rho_i >= 0.85:
            corridor_status = "inside"
        elif rho_i >= TAU_C:
            corridor_status = "uncertain"
        else:
            corridor_status = "outside"
            
        # Xác định trạng thái lưới (grid_status)
        if grid_dist <= 0.25:
            grid_status = "consistent"
        elif grid_dist <= D_MAX:
            grid_status = "consistent"  # Vẫn nằm trong Decision Margin
        else:
            grid_status = "mismatch"
            
        # Cơ chế lực đẩy đồ thị vô hạn (Hard Rejection Constraint):
        # 1. Box nằm ngoài hành lang giàn pin (rho_i < TAU_C) HOẶC khoảng cách lưới vượt xa d_max (grid_dist > D_MAX)
        #    vào vị trí rìa ngoài không có cấu trúc module => gán REJECTED (E_out = +inf)
        # 2. Box có dấu hiệu lệch nhẹ hoặc vùng seamline (0.35m < dist <= D_MAX hoặc uncertain) => NEEDS_REVIEW
        # 3. Box khuyết tật nhiệt: ưu tiên bảo vệ, chuyển sang NEEDS_REVIEW nếu có nghi ngờ, không từ chối tự động mù quáng
        # 4. Box chuẩn => ACCEPTED (E_out = 0)
        
        c_err_cm = row.get('Centroid_Err_Homo_cm', grid_dist * 100.0)
        zone = str(row.get('Zone', ''))
        
        if grid_dist > D_MAX:
            if is_defect:
                rejection_status = "needs_review"
                rejection_reason = f"Box khuyết tật lệch xa lưới ({grid_dist*100:.1f} cm > 52.4 cm); giữ lại để đối soát ảnh nhiệt"
                review_note = "Cần kiểm tra lớp ảnh nhiệt FLIR xem có điểm phát nóng thực tế tại vị trí này không"
            else:
                rejection_status = "rejected"
                rejection_reason = f"Lực đẩy vô hạn: Box rác vi phạm ràng buộc lưới (grid_dist={grid_dist*100:.1f} cm > 52.4 cm)"
                review_note = f"Hộp bao ngoại lai lơ lửng ngoài hàng pin (nghi ngờ cỏ dại/bóng đổ rìa dốc); loại khỏi đồ thị"
        elif corridor_status == "outside":
            if is_defect:
                rejection_status = "needs_review"
                rejection_reason = f"Box khuyết tật nằm ngoài hành lang (rho={rho_i*100:.1f}%); cần đối soát trực quan"
                review_note = "Xem xét trực quan ảnh nền trước khi quyết định loại bỏ"
            else:
                rejection_status = "rejected"
                rejection_reason = f"Lực đẩy vô hạn: Box nằm ngoài hành lang giàn pin (rho={rho_i*100:.1f}% < 60.0%)"
                review_note = "Ngoại lai lọt ra rãnh thoát nước hoặc mép đường nội bộ; gạt bỏ khỏi danh sách detection"
        elif (0.35 < grid_dist <= D_MAX) or (corridor_status == "uncertain"):
            rejection_status = "needs_review"
            rejection_reason = f"Cảnh báo lệch lưới/biên hành lang (dist={grid_dist*100:.1f} cm, rho={rho_i*100:.1f}%)"
            review_note = "Nằm gần seamline hoặc đầu hồi bàn pin; đề xuất giữ lại để nắn chỉnh bằng Grid Regularization"
        else:
            rejection_status = "accepted"
            rejection_reason = "Thỏa mãn hoàn hảo ràng buộc hành lang và cấu trúc lưới giàn pin (E_out = 0)"
            review_note = f"Hợp lệ: Khớp module chuẩn {nearest_mod_id} (sai số {grid_dist*100:.1f} cm, IoU={row.get('IoU_Homo', 0)*100:.1f}%)"
            
        records.append({
            'detection_id': p_name,
            'mapped_cx': round(cx, 4),
            'mapped_cy': round(cy, 4),
            'corridor_overlap_ratio': rho_i,
            'nearest_grid_distance': grid_dist,
            'corridor_status': corridor_status,
            'grid_status': grid_status,
            'rejection_status': rejection_status,
            'rejection_reason': rejection_reason,
            'review_note': review_note,
            # Các trường kỹ thuật đối soát
            'class_label': cls_raw,
            'is_defect': 'CÓ' if is_defect else 'KHÔNG',
            'zone': zone,
            'nearest_ref_id': nearest_mod_id
        })
        
    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv_bbox, index=False, encoding='utf-8-sig')
    df_out.to_csv(out_csv_root, index=False, encoding='utf-8-sig')
    print(f"\n Xuất báo cáo CSV gạt bỏ hộp bao rác thành công tại:")
    print(f"  + {out_csv_bbox}")
    print(f"  + {out_csv_root}")
    
    # Thống kê kết quả
    N_total = len(df_out)
    N_accepted = (df_out['rejection_status'] == 'accepted').sum()
    N_rejected = (df_out['rejection_status'] == 'rejected').sum()
    N_review = (df_out['rejection_status'] == 'needs_review').sum()
    R_rejected = (N_rejected / N_total) * 100.0
    
    print("\n--- KẾT QUẢ ĐỊNH LƯỢNG CƠ CHẾ GẠT BỎ HỘP BAO RÁC ---")
    print(f"Tổng số detection đầu vào (N): {N_total}")
    print(f"Số box được chấp nhận giữ lại (N_accepted): {N_accepted} ({N_accepted/N_total*100:.2f}%)")
    print(f"Số box bị từ chối / loại bỏ (N_rejected): {N_rejected} ({R_rejected:.2f}%)")
    print(f"Số box chuyển kiểm tra thủ công (N_review): {N_review} ({N_review/N_total*100:.2f}%)")
    print(f"Tỷ lệ từ chối (R_rejected): {R_rejected:.2f}%")
    
    print("\n--- THỐNG KÊ THEO CORRIDOR STATUS ---")
    print(df_out['corridor_status'].value_counts())
    
    print("\n--- THỐNG KÊ THEO GRID STATUS ---")
    print(df_out['grid_status'].value_counts())
    
    print("\n--- KIỂM TRA ĐỐI SOÁT TRÊN LỚP KHUYẾT TẬT NHIỆT (435 OBB) ---")
    df_def = df_out[df_out['is_defect'] == 'CÓ']
    print(df_def['rejection_status'].value_counts())

if __name__ == '__main__':
    main()
