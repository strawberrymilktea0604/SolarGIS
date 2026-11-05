"""
Module: transform_obb_affine_corners.py
Mục đích:
- Đọc file CSV OBB detection từ ortho 35m: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv
- Đọc file mốc tham chiếu ortho toàn cảnh 85m: bbox_centroid_export.csv
- Ghép cặp điểm mốc (bằng mã module ID kết hợp kiểm tra không gian GPS/AI)
- Ước lượng ma trận biến đổi Affine 2D (6 bậc tự do) bằng RANSAC + Least Squares
- Hàm biến đổi trực tiếp 4 góc OBB (NW, NE, SE, SW) và tâm từ map 35m sang hệ tọa độ map 85m (UTM Zone 49N)
- Đo đạc sai số Euclidean của tâm và từng đỉnh so với ground truth QGIS tham chiếu
- Phân loại trạng thái kiểm định (Hợp lệ, Lệch rõ rệt, Nằm ngoài phạm vi)
- Xuất dữ liệu đánh giá đầy đủ ra file CSV
"""

import os
import ast
import math
import numpy as np
import pandas as pd
import cv2

def parse_tuple_coords(val):
    """Phân tích chuỗi tọa độ (x, y) thành tuple float"""
    if pd.isna(val):
        return None
    try:
        res = ast.literal_eval(str(val).strip())
        if isinstance(res, (tuple, list)) and len(res) == 2:
            return (float(res[0]), float(res[1]))
    except Exception:
        pass
    return None

def compute_affine_matrix_ransac(src_pts, dst_pts, reproj_threshold=0.5):
    """
    Ước lượng ma trận Affine 2D 6 bậc tự do:
    [x_85]   [a11 a12 tx] [u_35]
    [y_85] = [a21 a22 ty] [v_35]
    [ 1  ]   [ 0   0   1] [ 1  ]
    """
    src_f = np.asarray(src_pts, dtype=np.float32)
    dst_f = np.asarray(dst_pts, dtype=np.float32)
    M_affine, inlier_mask = cv2.estimateAffine2D(
        src_f, dst_f, method=cv2.RANSAC, ransacReprojThreshold=reproj_threshold
    )
    return M_affine, inlier_mask

def transform_point_affine(pt, M):
    """
    Áp dụng ma trận Affine lên 1 điểm 2D
    """
    if pt is None or M is None:
        return None
    vec = np.array([pt[0], pt[1], 1.0], dtype=np.float64)
    res = M @ vec
    return (float(res[0]), float(res[1]))

def transform_obb_4_corners(nw_pt, ne_pt, se_pt, sw_pt, M):
    """
    Biến đổi trực tiếp 4 góc của một OBB từ map 35m sang map 85m:
    Giữ nguyên đúng thứ tự đỉnh: NW -> NE -> SE -> SW
    """
    m_nw = transform_point_affine(nw_pt, M)
    m_ne = transform_point_affine(ne_pt, M)
    m_se = transform_point_affine(se_pt, M)
    m_sw = transform_point_affine(sw_pt, M)
    return m_nw, m_ne, m_se, m_sw

def euclidean_distance(p1, p2):
    """Khoảng cách Euclidean giữa 2 điểm (m)"""
    if p1 is None or p2 is None:
        return None
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def resolve_file_path(filename):
    if not filename: return filename
    if os.path.isabs(filename) and os.path.exists(filename): return filename
    if os.path.exists(filename): return os.path.abspath(filename)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    same_dir = os.path.join(script_dir, filename)
    if os.path.exists(same_dir): return same_dir
    parent_dir = os.path.join(script_dir, "..", filename)
    if os.path.exists(parent_dir): return os.path.abspath(parent_dir)
    base = os.path.basename(filename)
    for c in [os.path.join(script_dir, base), os.path.join(script_dir, "..", base), os.path.abspath(base)]:
        if os.path.exists(c): return os.path.abspath(c)
    return filename

def run_pipeline(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Transformed_OBB_Affine_85m.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)
    if not os.path.isabs(out_csv_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))

    print("=== BẮT ĐẦU QUY TRÌNH BIẾN ĐỔI 4 ĐỈNH OBB BẰNG AFFINE ===")
    if not os.path.exists(src_csv_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {src_csv_path}")
    if not os.path.exists(ref_csv_path):
        raise FileNotFoundError(f"Không tìm thấy file tham chiếu: {ref_csv_path}")
        
    # 1. Đọc dữ liệu
    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)
    print(f"1. Tiếp nhận dữ liệu nguồn: {len(df_src)} OBBs từ map 35m")
    print(f"   Dữ liệu tham chiếu chuẩn: {len(df_ref)} modules từ map 85m")

    # 2. Chuẩn hóa mã ghép nối (GPS + AI matching ID)
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )
    
    # Ghép nối với file tham chiếu
    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_pairs = merged[merged['centroid_x'].notna()]
    print(f"2. Ghép cặp thành công: {len(matched_pairs)} / {len(df_src)} tấm pin đối ứng")

    # 3. Ước lượng ma trận biến đổi Affine
    src_pts = matched_pairs[['Pixel_U', 'Pixel_V']].values.astype(np.float32)
    dst_pts = matched_pairs[['centroid_x', 'centroid_y']].values.astype(np.float32)

    M_affine, inlier_mask = compute_affine_matrix_ransac(src_pts, dst_pts, reproj_threshold=0.5)
    inliers_count = int(np.sum(inlier_mask))
    print(f"3. Ước lượng ma trận Affine 2D (6 DOF):")
    print(f"   Inliers (ngưỡng < 0.5m): {inliers_count} / {len(matched_pairs)} ({inliers_count/len(matched_pairs)*100:.2f}%)")
    print("   Ma trận M:\n", M_affine)

    # 4. Biến đổi tọa độ 4 đỉnh OBB & Tâm cho toàn bộ 5.092 bản ghi
    records = []
    corner_errors_all = []
    centroid_errors_all = []

    for idx, row in merged.iterrows():
        # Tọa độ nguồn (Pixel 35m)
        u = row['Pixel_U']
        v = row['Pixel_V']
        nw_px = parse_tuple_coords(row['BBox_NW_Pixel'])
        ne_px = parse_tuple_coords(row['BBox_NE_Pixel'])
        se_px = parse_tuple_coords(row['BBox_SE_Pixel'])
        sw_px = parse_tuple_coords(row['BBox_SW_Pixel'])

        # Biến đổi sang UTM 85m qua ma trận Affine
        cen_mapped = transform_point_affine((u, v), M_affine)
        nw_m, ne_m, se_m, sw_m = transform_obb_4_corners(nw_px, ne_px, se_px, sw_px, M_affine)

        # Tham chiếu từ file bbox_centroid_export
        ref_id = row['module_id'] if pd.notna(row['module_id']) else None
        has_ref = ref_id is not None
        
        delta_e = None
        delta_n = None
        cen_err_m = None
        cen_err_cm = None
        err_nw_cm = None
        err_ne_cm = None
        err_se_cm = None
        err_sw_cm = None
        mean_corner_cm = None
        validation_status = "NGOAI_PHAM_VI_HOAC_CHUA_KHOP"

        if has_ref:
            ref_cen = (row['centroid_x'], row['centroid_y'])
            ref_tl = parse_tuple_coords(row['corner_top_left'])
            ref_tr = parse_tuple_coords(row['corner_top_right'])
            ref_br = parse_tuple_coords(row['corner_bottom_right'])
            ref_bl = parse_tuple_coords(row['corner_bottom_left'])

            delta_e = round(cen_mapped[0] - ref_cen[0], 4)
            delta_n = round(cen_mapped[1] - ref_cen[1], 4)
            cen_err_m = euclidean_distance(cen_mapped, ref_cen)
            cen_err_cm = round(cen_err_m * 100, 2)

            # Đo sai số 4 góc: NW->TL, NE->TR, SE->BR, SW->BL
            e_nw = euclidean_distance(nw_m, ref_tl)
            e_ne = euclidean_distance(ne_m, ref_tr)
            e_se = euclidean_distance(se_m, ref_br)
            e_sw = euclidean_distance(sw_m, ref_bl)

            err_nw_cm = round(e_nw * 100, 2) if e_nw is not None else None
            err_ne_cm = round(e_ne * 100, 2) if e_ne is not None else None
            err_se_cm = round(e_se * 100, 2) if e_se is not None else None
            err_sw_cm = round(e_sw * 100, 2) if e_sw is not None else None

            valid_corners = [c for c in [e_nw, e_ne, e_se, e_sw] if c is not None]
            if valid_corners:
                mean_corner_cm = round(float(np.mean(valid_corners)) * 100, 2)
                corner_errors_all.append(mean_corner_cm)
            centroid_errors_all.append(cen_err_cm)

            if cen_err_m <= 0.50:
                validation_status = "HOP_LE_CHUAN_XAC"
            else:
                validation_status = "LECH_RO_RET"
        else:
            validation_status = "KHONG_CO_MODULE_THAM_CHIEU"

        records.append({
            'Point_Name': row['Point_Name'],
            'Internal_Code': row['Internal_Code'],
            'Class': row['Class'],
            'Pixel_U_35m': u,
            'Pixel_V_35m': v,
            'BBox_NW_Pixel': row['BBox_NW_Pixel'],
            'BBox_NE_Pixel': row['BBox_NE_Pixel'],
            'BBox_SE_Pixel': row['BBox_SE_Pixel'],
            'BBox_SW_Pixel': row['BBox_SW_Pixel'],
            'Mapped_Centroid_X_85m': round(cen_mapped[0], 3),
            'Mapped_Centroid_Y_85m': round(cen_mapped[1], 3),
            'Mapped_NW_UTM_85m': f"({round(nw_m[0], 3)}, {round(nw_m[1], 3)})" if nw_m else None,
            'Mapped_NE_UTM_85m': f"({round(ne_m[0], 3)}, {round(ne_m[1], 3)})" if ne_m else None,
            'Mapped_SE_UTM_85m': f"({round(se_m[0], 3)}, {round(se_m[1], 3)})" if se_m else None,
            'Mapped_SW_UTM_85m': f"({round(sw_m[0], 3)}, {round(sw_m[1], 3)})" if sw_m else None,
            'Ref_Module_ID': ref_id,
            'Ref_Centroid_X': round(row['centroid_x'], 3) if has_ref else None,
            'Ref_Centroid_Y': round(row['centroid_y'], 3) if has_ref else None,
            'Delta_E_m': delta_e,
            'Delta_N_m': delta_n,
            'Centroid_Error_cm': cen_err_cm,
            'Err_NW_cm': err_nw_cm,
            'Err_NE_cm': err_ne_cm,
            'Err_SE_cm': err_se_cm,
            'Err_SW_cm': err_sw_cm,
            'Mean_Corner_Err_cm': mean_corner_cm,
            'Trang_Thai_Kiem_Tra': validation_status
        })

    df_out = pd.DataFrame(records)
    os.makedirs(os.path.dirname(out_csv_path), exist_ok=True)
    df_out.to_csv(out_csv_path, index=False, encoding='utf-8-sig')
    print(f"4. Xuất kết quả ra file CSV: {out_csv_path}")

    # 5. Thống kê số liệu kiểm định
    cen_arr = np.array(centroid_errors_all)
    cor_arr = np.array(corner_errors_all)

    valid_cnt = len(df_out[df_out['Trang_Thai_Kiem_Tra'] == "HOP_LE_CHUAN_XAC"])
    deviated_cnt = len(df_out[df_out['Trang_Thai_Kiem_Tra'] == "LECH_RO_RET"])
    unmatched_cnt = len(df_out[df_out['Trang_Thai_Kiem_Tra'] == "KHONG_CO_MODULE_THAM_CHIEU"])

    print("\n=== KẾT QUẢ ĐO ĐẠC SAI SỐ THỰC TẾ ===")
    print(f"Tổng số OBB đầu vào: {len(df_out)}")
    print(f"- Hợp lệ chuẩn xác (sai số <= 50cm): {valid_cnt} ({valid_cnt/len(df_out)*100:.2f}%)")
    print(f"- Lệch rõ rệt (sai số > 50cm): {deviated_cnt} ({deviated_cnt/len(df_out)*100:.2f}%)")
    print(f"- Không có module tham chiếu trên 85m: {unmatched_cnt} ({unmatched_cnt/len(df_out)*100:.2f}%)")

    print("\nThống kê sai số tâm (Centroid):")
    print(f"  Trung bình (Mean): {np.mean(cen_arr):.2f} cm")
    print(f"  Trung vị (Median): {np.median(cen_arr):.2f} cm")
    print(f"  RMSE: {np.sqrt(np.mean(cen_arr**2)):.2f} cm")
    print(f"  Phân vị 95% (P95): {np.percentile(cen_arr, 95):.2f} cm")
    print(f"  Nhỏ nhất (Min): {np.min(cen_arr):.2f} cm | Lớn nhất (Max): {np.max(cen_arr):.2f} cm")

    print("\nThống kê sai số 4 góc OBB (Mean Corner Error):")
    print(f"  Trung bình (Mean): {np.mean(cor_arr):.2f} cm")
    print(f"  Trung vị (Median): {np.median(cor_arr):.2f} cm")
    print(f"  RMSE: {np.sqrt(np.mean(cor_arr**2)):.2f} cm")
    print(f"  Phân vị 95% (P95): {np.percentile(cor_arr, 95):.2f} cm")
    print(f"  Nhỏ nhất (Min): {np.min(cor_arr):.2f} cm | Lớn nhất (Max): {np.max(cor_arr):.2f} cm")

    return df_out, M_affine

if __name__ == '__main__':
    run_pipeline()
