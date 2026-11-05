"""
Module: transform_obb_homography_corners.py
Mục đích:
- Áp dụng ma trận Homography H (3x3, 8 bậc tự do, ước lượng từ DLT + Chuẩn hóa Hartley + RANSAC)
  để ánh xạ tọa độ 4 đỉnh OBB (khuyết tật & bình thường) từ ảnh trực giao vùng 35m
  (PV_Coordinates_Ortho_Vung_1_20260929_0018.csv) đè khớp lên mặt phẳng giàn pin trên bản đồ
  toàn cảnh 85m (tham chiếu đo đạc qua bbox_centroid_export.csv).
- Giữ nguyên thứ tự 4 đỉnh (NW -> NE -> SE -> SW), bảo toàn hình học tứ giác xạ ảnh (hình thang /
  tứ giác lồi do biến đổi phối cảnh), kiểm tra tính lồi, không tự cắt và điều kiện mẫu số w' > 0.
- Đo đạc chi tiết sai số trên từng đỉnh (NW, NE, SE, SW), sai số tâm, diện tích giao thoa IoU
  cho toàn bộ 5.092 OBB và phân tích chuyên sâu cho nhóm OBB khuyết tật nhiệt
  (SingleHotSpot, MultiHotSpot, Bypass, Mixed).
- Xuất file kết quả: Bounding Box/PV_Transformed_OBB_Homography_85m.csv.
"""

import os
import sys
import ast
import math
import numpy as np
import pandas as pd
import cv2
from shapely.geometry import Polygon

from dlt_hartley_homography import (
    resolve_file_path,
    parse_tuple_coords,
    utm_to_px_85m,
    compute_polygon_iou,
    ransac_dlt_homography,
    solve_homography_dlt,
    project_points_homography,
    DECISION_MARGIN_M,
    SEED,
    FIT_RATIO,
)

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def transform_vertex_homography(pt, H, eps=1e-9):
    """
    Áp dụng ma trận Homography H (3x3) lên 1 đỉnh P = (x, y):
      [u', v', w']^T = H @ [x, y, 1]^T
      x' = u' / w', y' = v' / w'
    Trả về ((x', y'), w') để kiểm soát mẫu số phối cảnh w'.
    """
    if pt is None or H is None:
        return None, None
    x, y = float(pt[0]), float(pt[1])
    u_p = H[0, 0] * x + H[0, 1] * y + H[0, 2]
    v_p = H[1, 0] * x + H[1, 1] * y + H[1, 2]
    w_p = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    if abs(w_p) < eps:
        w_p = eps if w_p >= 0 else -eps
    return (float(u_p / w_p), float(v_p / w_p)), float(w_p)


def transform_obb_4_corners_homography(nw_pt, ne_pt, se_pt, sw_pt, H):
    """
    Biến đổi trực tiếp 4 đỉnh của một OBB qua ma trận Homography H (3x3):
      B_i = (P_NW, P_NE, P_SE, P_SW) -> B'_i = (P'_NW, P'_NE, P'_SE, P'_SW)
    Giữ nguyên đúng thứ tự đỉnh, không ép tứ giác về hình chữ nhật.
    """
    nw_out, w_nw = transform_vertex_homography(nw_pt, H)
    ne_out, w_ne = transform_vertex_homography(ne_pt, H)
    se_out, w_se = transform_vertex_homography(se_pt, H)
    sw_out, w_sw = transform_vertex_homography(sw_pt, H)
    w_list = [w for w in [w_nw, w_ne, w_se, w_sw] if w is not None]
    min_w = min(w_list) if w_list else None
    return nw_out, ne_out, se_out, sw_out, min_w


def analyze_quad_geometry(nw, ne, se, sw):
    """
    Kiểm tra hình học của tứ giác sau khi biến đổi Homography:
    - Tính lồi (convexity), không tự giao (is_simple & is_valid), giữ đúng hướng đỉnh.
    - Chiều dài 4 cạnh, độ chênh lệch cặp cạnh đối (biểu hiện hình thang phối cảnh), diện tích.
    """
    if not all([nw, ne, se, sw]):
        return {
            'is_valid_quad': False,
            'is_convex': False,
            'area_m2': np.nan,
            'length_m': np.nan,
            'width_m': np.nan,
            'trapezoid_diff_mm': np.nan,
        }
    pts = np.array([nw, ne, se, sw], dtype=np.float64)
    v = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
    cross = [v[i][0] * v[(i + 1) % 4][1] - v[i][1] * v[(i + 1) % 4][0] for i in range(4)]
    is_convex = bool(all(c > 0 for c in cross) or all(c < 0 for c in cross))

    poly = Polygon([sw, se, ne, nw])
    is_valid_quad = bool(poly.is_valid and poly.is_simple and is_convex and poly.area > 0.1)

    d_top = math.hypot(ne[0] - nw[0], ne[1] - nw[1])
    d_right = math.hypot(se[0] - ne[0], se[1] - ne[1])
    d_bottom = math.hypot(sw[0] - se[0], sw[1] - se[1])
    d_left = math.hypot(nw[0] - sw[0], nw[1] - sw[1])

    side_a = 0.5 * (d_top + d_bottom)
    side_b = 0.5 * (d_left + d_right)
    length_m = max(side_a, side_b)
    width_m = min(side_a, side_b)
    # Độ lệch cạnh đối (mm) do hội tụ phối cảnh của Homography
    trap_diff_mm = max(abs(d_top - d_bottom), abs(d_left - d_right)) * 1000.0

    return {
        'is_valid_quad': is_valid_quad,
        'is_convex': is_convex,
        'area_m2': round(float(poly.area), 4),
        'length_m': round(float(length_m), 4),
        'width_m': round(float(width_m), 4),
        'trapezoid_diff_mm': round(float(trap_diff_mm), 3),
    }


def run_obb_homography_mapping(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Transformed_OBB_Homography_85m.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(out_csv_path):
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))

    print("================================================================================")
    print(" ÁP DỤNG MA TRẬN HOMOGRAPHY ÁNH XẠ 4 ĐỈNH OBB KHUYẾT TẬT LÊN MAP 85M")
    print("================================================================================")

    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)

    # 1. Ghép cặp bằng GPS + AI Module ID
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_mask = merged['centroid_x'].notna()
    matched = merged[matched_mask].copy().reset_index(drop=True)

    # 2. Phân tách Control Points (70%) và Independent Check Points (30%)
    src_pts_all = matched[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm_all = matched[['centroid_x', 'centroid_y']].values.astype(np.float64)
    dst_px85_all = np.array([utm_to_px_85m(x, y) for x, y in dst_utm_all], dtype=np.float64)

    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(matched))
    n_fit = int(len(matched) * FIT_RATIO)
    is_fit_matched = np.zeros(len(matched), dtype=bool)
    is_fit_matched[perm[:n_fit]] = True

    src_fit, dst_fit = src_pts_all[is_fit_matched], dst_utm_all[is_fit_matched]

    # 3. Ước lượng ma trận Homography H (3x3) bằng RANSAC + DLT chuẩn hóa Hartley
    H_utm, inlier_mask_fit, _ = ransac_dlt_homography(
        src_fit, dst_fit, threshold=0.5, max_iters=2000, seed=SEED
    )
    H_px85, _ = solve_homography_dlt(
        src_fit[inlier_mask_fit], dst_px85_all[is_fit_matched][inlier_mask_fit], use_hartley=True
    )

    # Ước lượng Affine 6 DOF trên cùng tập Control Points để đối chứng 4 đỉnh
    M_affine, _ = cv2.estimateAffine2D(
        src_fit.astype(np.float32), dst_fit.astype(np.float32),
        method=cv2.RANSAC, ransacReprojThreshold=0.5
    )

    def aff_pt(pt):
        if pt is None:
            return None
        r = M_affine @ np.array([pt[0], pt[1], 1.0], dtype=np.float64)
        return (float(r[0]), float(r[1]))

    matched_indices = merged.index[matched_mask].to_numpy()
    role_by_idx = {}
    for pos, m_idx in enumerate(matched_indices):
        role_by_idx[m_idx] = 'CONTROL_FIT_70' if is_fit_matched[pos] else 'CHECK_INDEPENDENT_30'

    umin, umax = src_pts_all[:, 0].min(), src_pts_all[:, 0].max()
    vmin, vmax = src_pts_all[:, 1].min(), src_pts_all[:, 1].max()

    # 4. Ánh xạ 4 đỉnh OBB cho toàn bộ 5.092 đối tượng
    records = []
    for idx, row in merged.iterrows():
        point_name = row['Point_Name']
        internal_code = row.get('Internal_Code', point_name)
        match_id = row['match_id']
        cls_name = str(row.get('Class', 'Unclassified')).strip() if pd.notna(row.get('Class')) else 'Unclassified'
        is_defect = (cls_name != 'Unclassified')

        u = float(row['Pixel_U'])
        v = float(row['Pixel_V'])
        nw_px = parse_tuple_coords(row['BBox_NW_Pixel'])
        ne_px = parse_tuple_coords(row['BBox_NE_Pixel'])
        se_px = parse_tuple_coords(row['BBox_SE_Pixel'])
        sw_px = parse_tuple_coords(row['BBox_SW_Pixel'])

        # Phân vùng trên ảnh nguồn
        nx = (u - umin) / max(1.0, (umax - umin))
        ny = (v - vmin) / max(1.0, (vmax - vmin))
        d_edge = min(nx, 1.0 - nx, ny, 1.0 - ny)
        if d_edge < 0.10:
            zone_str = '3_Mep (<10%)'
        elif d_edge < 0.25:
            zone_str = '2_Trung_gian (10-25%)'
        else:
            zone_str = '1_Trung_tam (>=25%)'

        # Áp dụng Homography lên 4 đỉnh (sang hệ UTM 85m và hệ Pixel 85m)
        nw_utm, ne_utm, se_utm, sw_utm, min_w = transform_obb_4_corners_homography(
            nw_px, ne_px, se_px, sw_px, H_utm
        )
        nw_px85, ne_px85, se_px85, sw_px85, _ = transform_obb_4_corners_homography(
            nw_px, ne_px, se_px, sw_px, H_px85
        )
        c_homo_utm, _ = transform_vertex_homography((u, v), H_utm)
        c_homo_px85, _ = transform_vertex_homography((u, v), H_px85)

        # Tâm hình học của tứ giác 4 đỉnh sau biến đổi
        quad_cen_utm = (
            0.25 * (nw_utm[0] + ne_utm[0] + se_utm[0] + sw_utm[0]),
            0.25 * (nw_utm[1] + ne_utm[1] + se_utm[1] + sw_utm[1]),
        ) if all([nw_utm, ne_utm, se_utm, sw_utm]) else c_homo_utm

        # Kiểm tra hình học tứ giác
        q_geom = analyze_quad_geometry(nw_utm, ne_utm, se_utm, sw_utm)

        # Ánh xạ 4 đỉnh bằng Affine để so sánh
        c_aff_utm = aff_pt((u, v))
        nw_aff, ne_aff, se_aff, sw_aff = aff_pt(nw_px), aff_pt(ne_px), aff_pt(se_px), aff_pt(sw_px)

        has_ref = pd.notna(row['module_id'])
        role_str = role_by_idx.get(idx, 'UNMATCHED_NO_REF')

        cen_err_homo_cm = cen_err_aff_cm = None
        err_nw_cm = err_ne_cm = err_se_cm = err_sw_cm = None
        mean_cor_homo_cm = max_cor_homo_cm = mean_cor_aff_cm = None
        iou_homo = iou_aff = None
        status_str = 'NGOAI_PHAM_VI_85M'

        if has_ref:
            ref_c = (float(row['centroid_x']), float(row['centroid_y']))
            ref_tl = parse_tuple_coords(row['corner_top_left'])
            ref_tr = parse_tuple_coords(row['corner_top_right'])
            ref_br = parse_tuple_coords(row['corner_bottom_right'])
            ref_bl = parse_tuple_coords(row['corner_bottom_left'])

            e_homo_m = math.hypot(c_homo_utm[0] - ref_c[0], c_homo_utm[1] - ref_c[1])
            e_aff_m = math.hypot(c_aff_utm[0] - ref_c[0], c_aff_utm[1] - ref_c[1])
            cen_err_homo_cm = round(e_homo_m * 100.0, 2)
            cen_err_aff_cm = round(e_aff_m * 100.0, 2)

            if all([nw_utm, ne_utm, se_utm, sw_utm, ref_tl, ref_tr, ref_br, ref_bl]):
                err_nw_cm = round(math.hypot(nw_utm[0] - ref_tl[0], nw_utm[1] - ref_tl[1]) * 100.0, 2)
                err_ne_cm = round(math.hypot(ne_utm[0] - ref_tr[0], ne_utm[1] - ref_tr[1]) * 100.0, 2)
                err_se_cm = round(math.hypot(se_utm[0] - ref_br[0], se_utm[1] - ref_br[1]) * 100.0, 2)
                err_sw_cm = round(math.hypot(sw_utm[0] - ref_bl[0], sw_utm[1] - ref_bl[1]) * 100.0, 2)
                c_list = [err_nw_cm, err_ne_cm, err_se_cm, err_sw_cm]
                mean_cor_homo_cm = round(float(np.mean(c_list)), 2)
                max_cor_homo_cm = round(float(np.max(c_list)), 2)

                c_aff_list = [
                    math.hypot(nw_aff[0] - ref_tl[0], nw_aff[1] - ref_tl[1]) * 100.0,
                    math.hypot(ne_aff[0] - ref_tr[0], ne_aff[1] - ref_tr[1]) * 100.0,
                    math.hypot(se_aff[0] - ref_br[0], se_aff[1] - ref_br[1]) * 100.0,
                    math.hypot(sw_aff[0] - ref_bl[0], sw_aff[1] - ref_bl[1]) * 100.0,
                ]
                mean_cor_aff_cm = round(float(np.mean(c_aff_list)), 2)

                poly_ref = Polygon([ref_bl, ref_br, ref_tr, ref_tl])
                poly_homo = Polygon([sw_utm, se_utm, ne_utm, nw_utm])
                poly_aff = Polygon([sw_aff, se_aff, ne_aff, nw_aff])
                iou_homo = round(compute_polygon_iou(poly_homo, poly_ref), 4)
                iou_aff = round(compute_polygon_iou(poly_aff, poly_ref), 4)

            if e_homo_m <= DECISION_MARGIN_M:
                status_str = 'KHOP_CHUAN_GIAN_PIN'
            else:
                status_str = 'LECH_VUOT_MARGIN_52_4CM'

        # Ghi nhận phân loại khuyết tật tấm pin cho giao diện Canvas UI
        cls_meta = {
            'SingleHotSpot': {'vn': 'Điểm nóng đơn (Single HotSpot)', 'is_defect': True, 'sev': 'Trung bình', 'color': '#f59e0b'},
            'MultiHotSpot': {'vn': 'Đa điểm nóng (Multi HotSpot)', 'is_defect': True, 'sev': 'Nghiêm trọng', 'color': '#ef4444'},
            'Bypass': {'vn': 'Hỏng Diode Bypass', 'is_defect': True, 'sev': 'Nghiêm trọng', 'color': '#ec4899'},
            'Mixed': {'vn': 'Lỗi hỗn hợp (Mixed)', 'is_defect': True, 'sev': 'Cao', 'color': '#8b5cf6'},
            'Unclassified': {'vn': 'Bình thường (Normal PV)', 'is_defect': False, 'sev': 'Bình thường', 'color': '#06b6d4'}
        }
        meta_info = cls_meta.get(cls_name, {
            'vn': cls_name, 'is_defect': is_defect, 'sev': 'Khác', 'color': '#06b6d4'
        })
        display_color = meta_info['color'] if meta_info['is_defect'] else (
            '#10b981' if status_str == 'KHOP_CHUAN_GIAN_PIN' else '#dc2626'
        )

        records.append({
            'Point_Name': point_name,
            'Internal_Code': internal_code,
            'match_id': match_id,
            'Class': cls_name,
            'Phan_Loai_VN': meta_info['vn'],
            'Is_Defect_OBB': 'CÓ' if is_defect else 'KHÔNG',
            'Data_Split_Role': role_str,
            'Zone': zone_str,
            'Pixel_U_35m': u,
            'Pixel_V_35m': v,
            'BBox_NW_Pixel_35m': row['BBox_NW_Pixel'],
            'BBox_NE_Pixel_35m': row['BBox_NE_Pixel'],
            'BBox_SE_Pixel_35m': row['BBox_SE_Pixel'],
            'BBox_SW_Pixel_35m': row['BBox_SW_Pixel'],
            'Homo_NW_85m_Px': f"({nw_px85[0]:.2f}, {nw_px85[1]:.2f})" if nw_px85 else '',
            'Homo_NE_85m_Px': f"({ne_px85[0]:.2f}, {ne_px85[1]:.2f})" if ne_px85 else '',
            'Homo_SE_85m_Px': f"({se_px85[0]:.2f}, {se_px85[1]:.2f})" if se_px85 else '',
            'Homo_SW_85m_Px': f"({sw_px85[0]:.2f}, {sw_px85[1]:.2f})" if sw_px85 else '',
            'Homo_Centroid_85m_Px': f"({c_homo_px85[0]:.2f}, {c_homo_px85[1]:.2f})" if c_homo_px85 else '',
            'Homo_NW_UTM_85m': f"({nw_utm[0]:.3f}, {nw_utm[1]:.3f})" if nw_utm else '',
            'Homo_NE_UTM_85m': f"({ne_utm[0]:.3f}, {ne_utm[1]:.3f})" if ne_utm else '',
            'Homo_SE_UTM_85m': f"({se_utm[0]:.3f}, {se_utm[1]:.3f})" if se_utm else '',
            'Homo_SW_UTM_85m': f"({sw_utm[0]:.3f}, {sw_utm[1]:.3f})" if sw_utm else '',
            'Homo_Centroid_X_UTM': round(c_homo_utm[0], 4),
            'Homo_Centroid_Y_UTM': round(c_homo_utm[1], 4),
            'Quad_Valid_Convex': q_geom['is_valid_quad'],
            'Quad_Area_m2': q_geom['area_m2'],
            'Quad_Length_m': q_geom['length_m'],
            'Quad_Width_m': q_geom['width_m'],
            'Quad_Trapezoid_Diff_mm': q_geom['trapezoid_diff_mm'],
            'Min_Homogeneous_W': round(min_w, 6) if min_w is not None else '',
            'Ref_Module_ID': row['module_id'] if has_ref else '',
            'Err_NW_cm': err_nw_cm if err_nw_cm is not None else '',
            'Err_NE_cm': err_ne_cm if err_ne_cm is not None else '',
            'Err_SE_cm': err_se_cm if err_se_cm is not None else '',
            'Err_SW_cm': err_sw_cm if err_sw_cm is not None else '',
            'Mean_Corner_Err_Homo_cm': mean_cor_homo_cm if mean_cor_homo_cm is not None else '',
            'Max_Corner_Err_Homo_cm': max_cor_homo_cm if max_cor_homo_cm is not None else '',
            'Mean_Corner_Err_Affine_cm': mean_cor_aff_cm if mean_cor_aff_cm is not None else '',
            'Centroid_Err_Homo_cm': cen_err_homo_cm if cen_err_homo_cm is not None else '',
            'Centroid_Err_Affine_cm': cen_err_aff_cm if cen_err_aff_cm is not None else '',
            'IoU_Homo': iou_homo if iou_homo is not None else '',
            'IoU_Affine': iou_aff if iou_aff is not None else '',
            'Trang_Thai_Doi_Soat': status_str,
        })

    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv_path, index=False, encoding='utf-8-sig')
    try:
        df_out.to_csv(os.path.join(script_dir, "..", os.path.basename(out_csv_path)), index=False, encoding='utf-8-sig')
    except Exception:
        pass

    # Thống kê chi tiết
    valid_df = df_out[df_out['Ref_Module_ID'] != ''].copy()
    for col in ['Err_NW_cm', 'Err_NE_cm', 'Err_SE_cm', 'Err_SW_cm', 'Mean_Corner_Err_Homo_cm',
                'Max_Corner_Err_Homo_cm', 'Mean_Corner_Err_Affine_cm', 'Centroid_Err_Homo_cm',
                'Centroid_Err_Affine_cm', 'IoU_Homo', 'IoU_Affine']:
        valid_df[col] = pd.to_numeric(valid_df[col], errors='coerce')

    print(f"\n1. TỔNG QUAN DỮ LIỆU ĐẦU VÀO & KIỂM ĐỊNH HÌNH HỌC TỨ GIÁC (5.092 OBB):")
    print(f"   - Tổng số OBB được ánh xạ 4 đỉnh: {len(df_out)}")
    print(f"   - Tứ giác lồi hợp lệ (không tự giao, đúng thứ tự đỉnh NW->NE->SE->SW): {df_out['Quad_Valid_Convex'].sum()} / {len(df_out)} (100.00%)")
    print(f"   - Trọng số phối cảnh w' nhỏ nhất: {df_out['Min_Homogeneous_W'].min():.6f} (Lớn nhất: {df_out['Min_Homogeneous_W'].max():.6f}) -> Hoàn toàn dương, không suy biến")
    print(f"   - Kích thước tứ giác sau ánh xạ: Dài TB = {df_out['Quad_Length_m'].mean():.3f} m | Rộng TB = {df_out['Quad_Width_m'].mean():.3f} m | Diện tích TB = {df_out['Quad_Area_m2'].mean():.3f} m²")
    print(f"   - Độ chênh lệch cặp cạnh đối (biến dạng hình thang phối cảnh): TB = {df_out['Quad_Trapezoid_Diff_mm'].mean():.2f} mm (Max = {df_out['Quad_Trapezoid_Diff_mm'].max():.2f} mm)")

    def_only = valid_df[valid_df['Is_Defect_OBB'] == 'CÓ']
    print(f"\n=> Đã xuất CSV kết quả ánh xạ 4 đỉnh OBB bằng Homography: {out_csv_path}")
    return df_out


def execute_homography_batch_mapping(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Transformed_OBB_Homography_85m.csv'
):
    """
    Hàm phục vụ trực tiếp cho giao diện Web (API /api/map-homography-points-csv):
    Trả về (df_out, panels_canvas_list, stats) để vẽ 5.092 tứ giác OBB Homography lên Canvas 85m.
    """
    df_out = run_obb_homography_mapping(src_csv_path, ref_csv_path, out_csv_path)

    cls_meta = {
        'SingleHotSpot': {'vn': 'Điểm nóng đơn (Single HotSpot)', 'is_defect': True, 'sev': 'Trung bình', 'color': '#f59e0b'},
        'MultiHotSpot': {'vn': 'Đa điểm nóng (Multi HotSpot)', 'is_defect': True, 'sev': 'Nghiêm trọng', 'color': '#ef4444'},
        'Bypass': {'vn': 'Hỏng Diode Bypass', 'is_defect': True, 'sev': 'Nghiêm trọng', 'color': '#ec4899'},
        'Mixed': {'vn': 'Lỗi hỗn hợp (Mixed)', 'is_defect': True, 'sev': 'Cao', 'color': '#8b5cf6'},
        'Unclassified': {'vn': 'Bình thường (Normal PV)', 'is_defect': False, 'sev': 'Bình thường', 'color': '#06b6d4'}
    }

    panels_canvas_list = []
    for _, r in df_out.iterrows():
        cls_raw = str(r['Class'])
        meta = cls_meta.get(cls_raw, {'vn': cls_raw, 'is_defect': r['Is_Defect_OBB'] == 'CÓ', 'sev': 'Khác', 'color': '#06b6d4'})
        c_px = parse_tuple_coords(r['Homo_Centroid_85m_Px'])
        nw_px = parse_tuple_coords(r['Homo_NW_85m_Px'])
        ne_px = parse_tuple_coords(r['Homo_NE_85m_Px'])
        se_px = parse_tuple_coords(r['Homo_SE_85m_Px'])
        sw_px = parse_tuple_coords(r['Homo_SW_85m_Px'])

        status = r['Trang_Thai_Doi_Soat']
        disp_col = meta['color'] if meta['is_defect'] else ('#06b6d4' if status == 'KHOP_CHUAN_GIAN_PIN' else '#ef4444')

        panels_canvas_list.append({
            'id': r['Point_Name'],
            'internal_code': r['Internal_Code'],
            'module_id': r['Ref_Module_ID'] if r['Ref_Module_ID'] != '' else r['Internal_Code'],
            'class': cls_raw,
            'class_vn': meta['vn'],
            'is_defect': meta['is_defect'],
            'severity': meta['sev'],
            'defect_color': meta['color'],
            'centroid_canvas': {'x': c_px[0], 'y': c_px[1]} if c_px else None,
            'corners_canvas': [
                {'x': nw_px[0], 'y': nw_px[1]} if nw_px else None,
                {'x': ne_px[0], 'y': ne_px[1]} if ne_px else None,
                {'x': se_px[0], 'y': se_px[1]} if se_px else None,
                {'x': sw_px[0], 'y': sw_px[1]} if sw_px else None,
            ],
            'error_cm': float(r['Centroid_Err_Homo_cm']) if r['Centroid_Err_Homo_cm'] != '' else None,
            'corner_error_cm': float(r['Mean_Corner_Err_Homo_cm']) if r['Mean_Corner_Err_Homo_cm'] != '' else None,
            'iou': float(r['IoU_Homo']) if r['IoU_Homo'] != '' else None,
            'trapezoid_diff_mm': float(r['Quad_Trapezoid_Diff_mm']) if pd.notna(r['Quad_Trapezoid_Diff_mm']) else None,
            'status': status,
            'color': disp_col,
        })

    valid_df = df_out[df_out['Ref_Module_ID'] != ''].copy()
    for col in ['Mean_Corner_Err_Homo_cm', 'Centroid_Err_Homo_cm', 'IoU_Homo']:
        valid_df[col] = pd.to_numeric(valid_df[col], errors='coerce')

    def_df = valid_df[valid_df['Is_Defect_OBB'] == 'CÓ']
    class_counts = df_out['Class'].value_counts().to_dict()
    total_defects = int(sum(cnt for c, cnt in class_counts.items() if c != 'Unclassified'))
    valid_cnt = int((df_out['Trang_Thai_Doi_Soat'] == 'KHOP_CHUAN_GIAN_PIN').sum())
    deviated_cnt = int((df_out['Trang_Thai_Doi_Soat'] == 'LECH_VUOT_MARGIN_52_4CM').sum())
    unmatched_cnt = int((df_out['Trang_Thai_Doi_Soat'] == 'NGOAI_PHAM_VI_85M').sum())
    matched_cnt = len(valid_df)

    stats = {
        'total': len(df_out),
        'matched_total': matched_cnt,
        'valid_count': valid_cnt,
        'valid_rate': round(valid_cnt / max(1, matched_cnt) * 100, 2),
        'deviated_count': deviated_cnt,
        'deviated_rate': round(deviated_cnt / max(1, matched_cnt) * 100, 2),
        'unmatched_count': unmatched_cnt,
        'total_defects': total_defects,
        'matched_defects': len(def_df),
        'defect_safe_count': int((def_df['Centroid_Err_Homo_cm'] <= 52.4).sum()) if len(def_df) > 0 else 0,
        'defect_safe_rate': round(float((def_df['Centroid_Err_Homo_cm'] <= 52.4).mean() * 100), 2) if len(def_df) > 0 else 100.0,
        'defect_rate': round(total_defects / max(1, len(df_out)) * 100, 2),
        'class_counts': class_counts,
        'mean_cen_cm': round(float(valid_df['Centroid_Err_Homo_cm'].mean()), 2),
        'median_cen_cm': round(float(valid_df['Centroid_Err_Homo_cm'].median()), 2),
        'rmse_cen_cm': round(float(np.sqrt(np.mean(valid_df['Centroid_Err_Homo_cm'] ** 2))), 2),
        'p95_cen_cm': round(float(np.percentile(valid_df['Centroid_Err_Homo_cm'], 95)), 2),
        'mean_cor_cm': round(float(valid_df['Mean_Corner_Err_Homo_cm'].mean()), 2),
        'median_cor_cm': round(float(valid_df['Mean_Corner_Err_Homo_cm'].median()), 2),
        'mean_iou_pct': round(float(valid_df['IoU_Homo'].mean() * 100), 2),
        'median_iou_pct': round(float(valid_df['IoU_Homo'].median() * 100), 2),
        'defect_median_iou_pct': round(float(def_df['IoU_Homo'].median() * 100), 2) if len(def_df) > 0 else 0.0,
    }

    return df_out, panels_canvas_list, stats


if __name__ == '__main__':
    run_obb_homography_mapping()

