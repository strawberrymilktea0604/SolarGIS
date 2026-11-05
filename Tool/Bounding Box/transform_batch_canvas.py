"""
Module: transform_batch_canvas.py
Mục đích:
- Thực thi chuyển đổi đồng loạt 5.092 OBB tấm pin từ CSV detection trên ortho vùng 35m (PV_Coordinates_Ortho_Vung_1_20260929_0018.csv)
  sang hệ tọa độ và pixel Canvas của orthophoto toàn cảnh 85m (SonarPanelOrthoGeoTIFF.tif).
- Sử dụng mốc tham chiếu thực tế từ QGIS (bbox_centroid_export.csv) để đo đạc sai số định vị (Euclidean Error).
- Gióng lớp và phân loại trực quan cho giao diện Canvas (Khớp chuẩn giàn pin vs Lệch khung giàn vs Ngoài phạm vi).
- Xuất file kết quả hoàn chỉnh: Bounding Box/PV_Batch_Transformed_Canvas_85m.csv.
"""

import os
import ast
import math
import numpy as np
import pandas as pd
import cv2

# Thông số hệ quy chiếu & GeoTIFF của map toàn cảnh 85m (SonarPanelOrthoGeoTIFF.tif)
ORIGIN_X = 265363.45795877185
ORIGIN_Y = 1263901.907597885
RES_M = 0.03 # 3 cm/pixel

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

def utm_to_canvas_px(x, y):
    """Quy đổi tọa độ UTM (EPSG:32649) sang tọa độ Pixel Canvas của map 85m"""
    if x is None or y is None:
        return None
    col = (x - ORIGIN_X) / RES_M
    row = (ORIGIN_Y - y) / RES_M
    return {'x': round(float(col), 2), 'y': round(float(row), 2)}

def euclidean_dist(p1, p2):
    if p1 is None or p2 is None:
        return None
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def resolve_file_path(filename):
    if not filename:
        return filename
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename
    # 1. Check relative to current working dir
    if os.path.exists(filename):
        return os.path.abspath(filename)
    # 2. Check in same dir as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    same_dir_path = os.path.join(script_dir, filename)
    if os.path.exists(same_dir_path):
        return same_dir_path
    # 3. Check in parent dir of this script
    parent_dir_path = os.path.join(script_dir, "..", filename)
    if os.path.exists(parent_dir_path):
        return os.path.abspath(parent_dir_path)
    # 4. Strip directory and check base filename
    base_name = os.path.basename(filename)
    for candidate in [
        os.path.join(script_dir, base_name),
        os.path.join(script_dir, "..", base_name),
        os.path.abspath(base_name)
    ]:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return filename

def execute_batch_mapping(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Batch_Transformed_Canvas_85m.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)

    if not os.path.isabs(out_csv_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))

    print(f"=== THỰC THI CHUYỂN ĐỔI ĐỒNG LOẠT OBB LÊN CANVAS MAP 85M ===")
    print(f"File nguồn: {src_csv_path}")
    print(f"File tham chiếu: {ref_csv_path}")

    if not os.path.exists(src_csv_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn detection: {src_csv_path}")
    if not os.path.exists(ref_csv_path):
        raise FileNotFoundError(f"Không tìm thấy file mốc tham chiếu: {ref_csv_path}")

    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)

    # 1. Ghép cặp điểm mốc tự động (GPS + AI matching ID)
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_pairs = merged[merged['centroid_x'].notna()]

    # 2. Ước lượng ma trận Affine 2D (6 DOF) từ các điểm mốc
    src_pts = matched_pairs[['Pixel_U', 'Pixel_V']].values.astype(np.float32)
    dst_pts = matched_pairs[['centroid_x', 'centroid_y']].values.astype(np.float32)

    M_affine, inlier_mask = cv2.estimateAffine2D(
        src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=0.5
    )

    # 3. Chuyển đổi đồng loạt toàn bộ 5.092 OBB
    records = []
    panels_canvas_list = []
    
    valid_count = 0
    deviated_count = 0
    unmatched_count = 0

    centroid_errors_cm = []
    corner_errors_cm = []

    for idx, row in merged.iterrows():
        u = row['Pixel_U']
        v = row['Pixel_V']
        nw_px_src = parse_tuple_coords(row['BBox_NW_Pixel'])
        ne_px_src = parse_tuple_coords(row['BBox_NE_Pixel'])
        se_px_src = parse_tuple_coords(row['BBox_SE_Pixel'])
        sw_px_src = parse_tuple_coords(row['BBox_SW_Pixel'])

        # Biến đổi sang UTM qua ma trận Affine
        def aff_pt(p):
            if p is None: return None
            res = M_affine @ np.array([p[0], p[1], 1.0])
            return (float(res[0]), float(res[1]))

        c_utm = aff_pt((u, v))
        nw_utm = aff_pt(nw_px_src)
        ne_utm = aff_pt(ne_px_src)
        se_utm = aff_pt(se_px_src)
        sw_utm = aff_pt(sw_px_src)

        # Chuyển tiếp sang Pixel Canvas của Ortho toàn cảnh 85m
        c_canv = utm_to_canvas_px(c_utm[0], c_utm[1])
        nw_canv = utm_to_canvas_px(nw_utm[0], nw_utm[1]) if nw_utm else None
        ne_canv = utm_to_canvas_px(ne_utm[0], ne_utm[1]) if ne_utm else None
        se_canv = utm_to_canvas_px(se_utm[0], se_utm[1]) if se_utm else None
        sw_canv = utm_to_canvas_px(sw_utm[0], sw_utm[1]) if sw_utm else None

        # Đối soát với ground truth từ bbox_centroid_export
        has_ref = pd.notna(row['module_id'])
        ref_id = row['module_id'] if has_ref else None
        
        cen_err_m = None
        cen_err_cm = None
        mean_cor_cm = None
        status = "NGOAI_PHAM_VI_HOAC_CHUA_KHOP"
        color = "#94a3b8" # Xám

        ref_c_canv = None
        ref_nw_canv = None
        ref_ne_canv = None
        ref_se_canv = None
        ref_sw_canv = None

        if has_ref:
            ref_cen_utm = (row['centroid_x'], row['centroid_y'])
            ref_tl_utm = parse_tuple_coords(row['corner_top_left'])
            ref_tr_utm = parse_tuple_coords(row['corner_top_right'])
            ref_br_utm = parse_tuple_coords(row['corner_bottom_right'])
            ref_bl_utm = parse_tuple_coords(row['corner_bottom_left'])

            # Pixel Canvas chuẩn của mốc
            ref_c_canv = utm_to_canvas_px(ref_cen_utm[0], ref_cen_utm[1])
            ref_nw_canv = utm_to_canvas_px(ref_tl_utm[0], ref_tl_utm[1]) if ref_tl_utm else None
            ref_ne_canv = utm_to_canvas_px(ref_tr_utm[0], ref_tr_utm[1]) if ref_tr_utm else None
            ref_se_canv = utm_to_canvas_px(ref_br_utm[0], ref_br_utm[1]) if ref_br_utm else None
            ref_sw_canv = utm_to_canvas_px(ref_bl_utm[0], ref_bl_utm[1]) if ref_bl_utm else None

            # Sai số khoảng cách Euclidean
            cen_err_m = euclidean_dist(c_utm, ref_cen_utm)
            cen_err_cm = round(cen_err_m * 100, 2)
            centroid_errors_cm.append(cen_err_cm)

            e_nw = euclidean_dist(nw_utm, ref_tl_utm)
            e_ne = euclidean_dist(ne_utm, ref_tr_utm)
            e_se = euclidean_dist(se_utm, ref_br_utm)
            e_sw = euclidean_dist(sw_utm, ref_bl_utm)
            valid_cors = [e for e in [e_nw, e_ne, e_se, e_sw] if e is not None]
            if valid_cors:
                mean_cor_cm = round(float(np.mean(valid_cors)) * 100, 2)
                corner_errors_cm.append(mean_cor_cm)

            # Phân loại đối soát giàn pin
            if cen_err_m <= 0.50:
                status = "KHOP_CHUAN_GIAN_PIN"
                valid_count += 1
            else:
                status = "LECH_KHUNG_GIAN"
                deviated_count += 1
        else:
            status = "NGOAI_PHAM_VI_85M"
            unmatched_count += 1

        # Ghi nhận phân loại khuyết tật tấm pin
        cls_raw = str(row['Class']).strip() if pd.notna(row['Class']) else 'Unclassified'
        cls_meta = {
            'SingleHotSpot': {'vn': 'Điểm nóng đơn (Single HotSpot)', 'is_defect': True, 'sev': 'Trung bình', 'color': '#f59e0b'},
            'MultiHotSpot': {'vn': 'Đa điểm nóng (Multi HotSpot)', 'is_defect': True, 'sev': 'Nghiêm trọng', 'color': '#ef4444'},
            'Bypass': {'vn': 'Hỏng Diode Bypass', 'is_defect': True, 'sev': 'Nghiêm trọng', 'color': '#ec4899'},
            'Mixed': {'vn': 'Lỗi hỗn hợp (Mixed)', 'is_defect': True, 'sev': 'Cao', 'color': '#8b5cf6'},
            'Unclassified': {'vn': 'Bình thường (Normal PV)', 'is_defect': False, 'sev': 'Bình thường', 'color': '#10b981'}
        }
        meta_info = cls_meta.get(cls_raw, {
            'vn': cls_raw, 'is_defect': False if cls_raw.lower() == 'unclassified' else True, 'sev': 'Khác', 'color': '#06b6d4'
        })

        # Màu trực quan trên Canvas: Nếu tấm có lỗi nhiệt, ưu tiên tô màu lỗi nhiệt để nhìn thấy ngay!
        if meta_info['is_defect']:
            display_color = meta_info['color']
        else:
            display_color = '#10b981' if status == "KHOP_CHUAN_GIAN_PIN" else '#dc2626'

        records.append({
            'Point_Name': row['Point_Name'],
            'Internal_Code': row['Internal_Code'],
            'Class': cls_raw,
            'Phan_Loai_VN': meta_info['vn'],
            'Co_Khuyet_Tat': 'CÓ' if meta_info['is_defect'] else 'KHÔNG',
            'Muc_Do_Khuyet_Tat': meta_info['sev'],
            'Pixel_U_35m': u,
            'Pixel_V_35m': v,
            'Canvas_Centroid_X_85m': c_canv['x'],
            'Canvas_Centroid_Y_85m': c_canv['y'],
            'Canvas_NW_X_85m': nw_canv['x'] if nw_canv else None,
            'Canvas_NW_Y_85m': nw_canv['y'] if nw_canv else None,
            'Canvas_NE_X_85m': ne_canv['x'] if ne_canv else None,
            'Canvas_NE_Y_85m': ne_canv['y'] if ne_canv else None,
            'Canvas_SE_X_85m': se_canv['x'] if se_canv else None,
            'Canvas_SE_Y_85m': se_canv['y'] if se_canv else None,
            'Canvas_SW_X_85m': sw_canv['x'] if sw_canv else None,
            'Canvas_SW_Y_85m': sw_canv['y'] if sw_canv else None,
            'Ref_Module_ID': ref_id,
            'Ref_Canvas_Centroid_X': ref_c_canv['x'] if ref_c_canv else None,
            'Ref_Canvas_Centroid_Y': ref_c_canv['y'] if ref_c_canv else None,
            'Delta_Canvas_X_px': round(c_canv['x'] - ref_c_canv['x'], 2) if ref_c_canv else None,
            'Delta_Canvas_Y_px': round(c_canv['y'] - ref_c_canv['y'], 2) if ref_c_canv else None,
            'Centroid_Error_cm': cen_err_cm,
            'Mean_Corner_Error_cm': mean_cor_cm,
            'Trang_Thai_Doi_Soat': status
        })

        # Cấu trúc cho Canvas UI
        panels_canvas_list.append({
            'id': row['Point_Name'],
            'internal_code': row['Internal_Code'],
            'module_id': ref_id or row['Internal_Code'],
            'class': cls_raw,
            'class_vn': meta_info['vn'],
            'is_defect': meta_info['is_defect'],
            'severity': meta_info['sev'],
            'defect_color': meta_info['color'],
            'centroid_canvas': c_canv,
            'corners_canvas': [nw_canv, ne_canv, se_canv, sw_canv],
            'ref_centroid_canvas': ref_c_canv,
            'ref_corners_canvas': [ref_nw_canv, ref_ne_canv, ref_se_canv, ref_sw_canv] if ref_c_canv else None,
            'error_cm': cen_err_cm,
            'corner_error_cm': mean_cor_cm,
            'status': status,
            'color': display_color
        })

    df_out = pd.DataFrame(records)
    os.makedirs(os.path.dirname(out_csv_path), exist_ok=True)
    df_out.to_csv(out_csv_path, index=False, encoding='utf-8-sig')
    print(f"Đã xuất kết quả kiểm tra đồng loạt ra: {out_csv_path}")

    # Thống kê phân loại khuyết tật
    class_counts = df_out['Class'].value_counts().to_dict()
    total_defects = int(sum(count for c, count in class_counts.items() if c != 'Unclassified'))

    stats = {
        'total': len(df_out),
        'valid_count': valid_count,
        'valid_rate': round(valid_count / len(df_out) * 100, 2),
        'deviated_count': deviated_count,
        'deviated_rate': round(deviated_count / len(df_out) * 100, 2),
        'unmatched_count': unmatched_count,
        'unmatched_rate': round(unmatched_count / len(df_out) * 100, 2),
        'total_defects': total_defects,
        'defect_rate': round(total_defects / len(df_out) * 100, 2),
        'class_counts': class_counts,
        'unmatched_rate': round(unmatched_count / len(df_out) * 100, 2),
        'mean_cen_cm': round(float(np.mean(centroid_errors_cm)), 2),
        'median_cen_cm': round(float(np.median(centroid_errors_cm)), 2),
        'rmse_cen_cm': round(float(np.sqrt(np.mean(np.array(centroid_errors_cm)**2))), 2),
        'p95_cen_cm': round(float(np.percentile(centroid_errors_cm, 95)), 2),
        'mean_cor_cm': round(float(np.mean(corner_errors_cm)), 2),
        'median_cor_cm': round(float(np.median(corner_errors_cm)), 2),
        'rmse_cor_cm': round(float(np.sqrt(np.mean(np.array(corner_errors_cm)**2))), 2),
        'p95_cor_cm': round(float(np.percentile(corner_errors_cm, 95)), 2)
    }

    print("\n=== THỐNG KÊ KẾT QUẢ ĐỐI SOÁT GIÀN PIN TRÊN CANVAS 85M ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return df_out, panels_canvas_list, stats

if __name__ == '__main__':
    execute_batch_mapping()
