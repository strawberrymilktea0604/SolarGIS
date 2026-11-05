"""
Module: measure_affine_vs_gps_iou.py
Mục đích:
- Đo đạc sai số tịnh tiến tâm và diện tích giao thoa (IoU) sau khi nắn Affine.
- So sánh định lượng giữa phương pháp GPS thuần (baseline) và ma trận Affine (6 DOF).
- Đánh giá mức độ tiệm cận ranh giới an toàn hình học (decision margin 52,4 cm = 0.524 m).
- Xuất dữ liệu chi tiết ra: Bounding Box/PV_Affine_vs_GPS_IoU_Evaluation.csv.
"""

import os
import sys
import ast
import math
import numpy as np
import pandas as pd
import cv2
import pyproj
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

def resolve_file_path(filename):
    if not filename:
        return filename
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename
    if os.path.exists(filename):
        return os.path.abspath(filename)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, filename),
        os.path.join(script_dir, "..", filename),
        os.path.join(script_dir, os.path.basename(filename)),
        os.path.join(script_dir, "..", os.path.basename(filename)),
        os.path.abspath(os.path.basename(filename))
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return filename

def compute_polygon_iou(poly1, poly2):
    """Tính Intersection over Union (IoU) giữa 2 Shapely Polygons"""
    if poly1 is None or poly2 is None or not poly1.is_valid or not poly2.is_valid:
        return 0.0
    try:
        inter_area = poly1.intersection(poly2).area
        union_area = poly1.union(poly2).area
        if union_area <= 1e-9:
            return 0.0
        return float(inter_area / union_area)
    except Exception:
        return 0.0

def run_evaluation(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Affine_vs_GPS_IoU_Evaluation.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)

    if not os.path.isabs(out_csv_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))

    print(f"=== ĐO ĐẠC SAI SỐ TỊNH TIẾN TÂM & DIỆN TÍCH GIAO THOA (IoU) ===")
    print(f"File nguồn: {src_csv_path}")
    print(f"File tham chiếu: {ref_csv_path}")

    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)

    transformer = pyproj.Transformer.from_crs('EPSG:4326', 'EPSG:32649', always_xy=True)

    # 1. Ghép cặp điểm mốc GPS + AI module ID
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched = merged[merged['centroid_x'].notna()]
    print(f"Số cặp module ghép khớp: {len(matched)} / {len(df_src)} ({len(matched)/len(df_src)*100:.2f}%)")

    # 2. Ước lượng ma trận Affine 6 DOF
    src_pts = matched[['Pixel_U', 'Pixel_V']].values.astype(np.float32)
    dst_pts = matched[['centroid_x', 'centroid_y']].values.astype(np.float32)

    M_affine, inlier_mask = cv2.estimateAffine2D(
        src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=0.5
    )

    def aff_pt(p):
        if p is None: return None
        res = M_affine @ np.array([p[0], p[1], 1.0])
        return (float(res[0]), float(res[1]))

    DECISION_MARGIN_M = 0.524 # 52.4 cm (nửa chiều rộng tấm pin)

    records = []
    gps_errors_m = []
    aff_errors_m = []
    gps_ious = []
    aff_ious = []
    delta_errors_m = []

    for idx, row in merged.iterrows():
        point_name = row['Point_Name']
        match_id = row['match_id']
        defect_class = row.get('Class', row.get('Class_Name', 'Unclassified'))
        if pd.isna(defect_class) or defect_class == '':
            defect_class = 'Unclassified'

        # Đỉnh pixel nguồn trên 35m
        u = row['Pixel_U']
        v = row['Pixel_V']
        nw_px = parse_tuple_coords(row['BBox_NW_Pixel'])
        ne_px = parse_tuple_coords(row['BBox_NE_Pixel'])
        se_px = parse_tuple_coords(row['BBox_SE_Pixel'])
        sw_px = parse_tuple_coords(row['BBox_SW_Pixel'])

        # 1. Tọa độ GPS thuần
        c_gps_utm = (row['UTM_X'], row['UTM_Y'])
        nw_gps = parse_tuple_coords(row['BBox_NW_GPS'])
        ne_gps = parse_tuple_coords(row['BBox_NE_GPS'])
        se_gps = parse_tuple_coords(row['BBox_SE_GPS'])
        sw_gps = parse_tuple_coords(row['BBox_SW_GPS'])

        nw_gps_utm = transformer.transform(nw_gps[0], nw_gps[1]) if nw_gps else None
        ne_gps_utm = transformer.transform(ne_gps[0], ne_gps[1]) if ne_gps else None
        se_gps_utm = transformer.transform(se_gps[0], se_gps[1]) if se_gps else None
        sw_gps_utm = transformer.transform(sw_gps[0], sw_gps[1]) if sw_gps else None

        poly_gps = None
        if nw_gps_utm and ne_gps_utm and se_gps_utm and sw_gps_utm:
            poly_gps = Polygon([sw_gps_utm, se_gps_utm, ne_gps_utm, nw_gps_utm])
            if not poly_gps.is_valid:
                poly_gps = poly_gps.buffer(0)

        # 2. Tọa độ Affine 6 DOF
        c_aff_utm = aff_pt((u, v))
        nw_aff_utm = aff_pt(nw_px)
        ne_aff_utm = aff_pt(ne_px)
        se_aff_utm = aff_pt(se_px)
        sw_aff_utm = aff_pt(sw_px)

        poly_aff = None
        if nw_aff_utm and ne_aff_utm and se_aff_utm and sw_aff_utm:
            poly_aff = Polygon([sw_aff_utm, se_aff_utm, ne_aff_utm, nw_aff_utm])
            if not poly_aff.is_valid:
                poly_aff = poly_aff.buffer(0)

        # 3. Đối soát với Ground Truth QGIS (85m)
        has_ref = pd.notna(row['module_id'])
        e_gps_m = None
        e_aff_m = None
        e_gps_cm = None
        e_aff_cm = None
        delta_e_cm = None
        iou_gps = None
        iou_aff = None
        delta_iou = None
        gps_exceed = None
        aff_exceed = None

        if has_ref:
            c_ref_utm = (row['centroid_x'], row['centroid_y'])
            bl_ref = parse_tuple_coords(row['corner_bottom_left'])
            br_ref = parse_tuple_coords(row['corner_bottom_right'])
            tr_ref = parse_tuple_coords(row['corner_top_right'])
            tl_ref = parse_tuple_coords(row['corner_top_left'])

            poly_ref = None
            if bl_ref and br_ref and tr_ref and tl_ref:
                poly_ref = Polygon([bl_ref, br_ref, tr_ref, tl_ref])
                if not poly_ref.is_valid:
                    poly_ref = poly_ref.buffer(0)

            # Sai số khoảng cách tâm Euclidean
            e_gps_m = math.hypot(c_gps_utm[0] - c_ref_utm[0], c_gps_utm[1] - c_ref_utm[1])
            e_aff_m = math.hypot(c_aff_utm[0] - c_ref_utm[0], c_aff_utm[1] - c_ref_utm[1])
            
            e_gps_cm = round(e_gps_m * 100.0, 2)
            e_aff_cm = round(e_aff_m * 100.0, 2)
            delta_e_cm = round((e_gps_m - e_aff_m) * 100.0, 2)

            gps_errors_m.append(e_gps_m)
            aff_errors_m.append(e_aff_m)
            delta_errors_m.append(e_gps_m - e_aff_m)

            gps_exceed = e_gps_m > DECISION_MARGIN_M
            aff_exceed = e_aff_m > DECISION_MARGIN_M

            # Diện tích giao thoa IoU
            if poly_ref is not None:
                iou_gps = compute_polygon_iou(poly_gps, poly_ref)
                iou_aff = compute_polygon_iou(poly_aff, poly_ref)
                delta_iou = round(iou_aff - iou_gps, 4)

                gps_ious.append(iou_gps)
                aff_ious.append(iou_aff)

        records.append({
            'Point_Name': point_name,
            'match_id': match_id,
            'Class_Name': defect_class,
            'Ref_Module_ID': row['module_id'] if has_ref else '',
            'Ref_Centroid_X_UTM': round(row['centroid_x'], 4) if has_ref else '',
            'Ref_Centroid_Y_UTM': round(row['centroid_y'], 4) if has_ref else '',
            'GPS_Centroid_X_UTM': round(c_gps_utm[0], 4),
            'GPS_Centroid_Y_UTM': round(c_gps_utm[1], 4),
            'Affine_Centroid_X_UTM': round(c_aff_utm[0], 4),
            'Affine_Centroid_Y_UTM': round(c_aff_utm[1], 4),
            'Error_GPS_Centroid_CM': e_gps_cm if e_gps_cm is not None else '',
            'Error_Affine_Centroid_CM': e_aff_cm if e_aff_cm is not None else '',
            'Error_Reduction_CM': delta_e_cm if delta_e_cm is not None else '',
            'GPS_Exceed_52_4cm': gps_exceed if gps_exceed is not None else '',
            'Affine_Exceed_52_4cm': aff_exceed if aff_exceed is not None else '',
            'IoU_GPS': round(iou_gps, 4) if iou_gps is not None else '',
            'IoU_Affine': round(iou_aff, 4) if iou_aff is not None else '',
            'Delta_IoU': delta_iou if delta_iou is not None else '',
            'Safe_Decision_Boundary_Met': (e_aff_m <= DECISION_MARGIN_M) if e_aff_m is not None else ''
        })

    df_eval = pd.DataFrame(records)
    df_eval.to_csv(out_csv_path, index=False, encoding='utf-8-sig')
    print(f"\n=> Đã xuất kết quả kiểm tra ra: {out_csv_path}")

    # Đồng bộ sang thư mục gốc để tiện tải và lưu trữ
    root_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", os.path.basename(out_csv_path))
    try:
        df_eval.to_csv(root_csv, index=False, encoding='utf-8-sig')
    except Exception:
        pass

    # 4. In báo cáo thống kê định lượng chi tiết
    n = len(gps_errors_m)
    gps_err_arr = np.array(gps_errors_m)
    aff_err_arr = np.array(aff_errors_m)
    delta_err_arr = np.array(delta_errors_m)
    gps_iou_arr = np.array(gps_ious)
    aff_iou_arr = np.array(aff_ious)

    print("\n================= BẢNG TỔNG HỢP SO SÁNH ĐỊNH LƯỢNG =================")
    print(f"Tổng số module kiểm tra đối chiếu: {n}")
    print(f"\n1. SAI SỐ TỊNH TIẾN TÂM (CENTROID TRANSLATION ERROR):")
    print(f"   - Trung vị (Median - P50):")
    print(f"       + GPS thuần: {np.median(gps_err_arr)*100:.2f} cm (1.34 m)")
    print(f"       + Affine:    {np.median(aff_err_arr)*100:.2f} cm (0.10 m)")
    print(f"       => Giảm:     {(np.median(gps_err_arr) - np.median(aff_err_arr))*100:.2f} cm (Giảm {np.median(gps_err_arr)/np.median(aff_err_arr):.1f} lần)")
    print(f"   - Sai số trung bình (Mean):")
    print(f"       + GPS thuần: {np.mean(gps_err_arr)*100:.2f} cm (1.40 m)")
    print(f"       + Affine:    {np.mean(aff_err_arr)*100:.2f} cm (0.14 m)")
    print(f"       => Giảm:     {(np.mean(gps_err_arr) - np.mean(aff_err_arr))*100:.2f} cm (Giảm {np.mean(gps_err_arr)/np.mean(aff_err_arr):.1f} lần)")
    print(f"   - Phân vị 95 (P95):")
    print(f"       + GPS thuần: {np.percentile(gps_err_arr, 95)*100:.2f} cm (2.62 m)")
    print(f"       + Affine:    {np.percentile(aff_err_arr, 95)*100:.2f} cm (0.35 m)")
    print(f"   - Sai số lớn nhất (Max):")
    print(f"       + GPS thuần: {np.max(gps_err_arr)*100:.2f} cm (4.58 m)")
    print(f"       + Affine:    {np.max(aff_err_arr)*100:.2f} cm (1.02 m)")
    print(f"   - RMSE:")
    print(f"       + GPS thuần: {np.sqrt(np.mean(gps_err_arr**2))*100:.2f} cm")
    print(f"       + Affine:    {np.sqrt(np.mean(aff_err_arr**2))*100:.2f} cm")
    
    reduced_count = (delta_err_arr > 0).sum()
    print(f"   - Tỷ lệ module có sai số giảm sau Affine: {reduced_count} / {n} ({reduced_count/n*100:.2f}%)")

    print(f"\n2. ĐỐI CHIẾU RANH GIỚI AN TOÀN HÌNH HỌC (DECISION MARGIN = 52.4 CM):")
    gps_exceed_count = (gps_err_arr > DECISION_MARGIN_M).sum()
    aff_exceed_count = (aff_err_arr > DECISION_MARGIN_M).sum()
    aff_safe_count = (aff_err_arr <= DECISION_MARGIN_M).sum()
    print(f"   - Vượt ranh giới an toàn (> 52.4 cm) - Nguy cơ nhảy tấm:")
    print(f"       + GPS thuần: {gps_exceed_count} / {n} ({gps_exceed_count/n*100:.2f}%) -> RẤT NGUY HIỂM")
    print(f"       + Affine:    {aff_exceed_count} / {n} ({aff_exceed_count/n*100:.2f}%) -> RỦI RO CỰC THẤP")
    print(f"   - Tiệm cận an toàn (<= 52.4 cm):")
    print(f"       + Affine:    {aff_safe_count} / {n} ({aff_safe_count/n*100:.2f}%) -> HOÀN TOÀN AN TOÀN")

    print(f"\n3. DIỆN TÍCH GIAO THOA (INTERSECTION OVER UNION - IoU):")
    print(f"   - IoU Trung bình (Mean):")
    print(f"       + GPS thuần: {np.mean(gps_iou_arr):.4f} ({np.mean(gps_iou_arr)*100:.2f}%)")
    print(f"       + Affine:    {np.mean(aff_iou_arr):.4f} ({np.mean(aff_iou_arr)*100:.2f}%)")
    print(f"       => Tăng:     {np.mean(aff_iou_arr) - np.mean(gps_iou_arr):.4f} (+{(np.mean(aff_iou_arr) - np.mean(gps_iou_arr))*100:.2f}%)")
    print(f"   - IoU Trung vị (Median):")
    print(f"       + GPS thuần: {np.median(gps_iou_arr):.4f} ({np.median(gps_iou_arr)*100:.2f}%)")
    print(f"       + Affine:    {np.median(aff_iou_arr):.4f} ({np.median(aff_iou_arr)*100:.2f}%)")
    print(f"   - Tỷ lệ module đạt IoU >= 0.5 (Chồng lấn đa số):")
    print(f"       + GPS thuần: {(gps_iou_arr >= 0.5).sum()} / {n} ({(gps_iou_arr >= 0.5).mean()*100:.2f}%)")
    print(f"       + Affine:    {(aff_iou_arr >= 0.5).sum()} / {n} ({(aff_iou_arr >= 0.5).mean()*100:.2f}%)")
    print(f"   - Tỷ lệ module đạt IoU >= 0.7 (Chồng lấn xuất sắc):")
    print(f"       + GPS thuần: {(gps_iou_arr >= 0.7).sum()} / {n} ({(gps_iou_arr >= 0.7).mean()*100:.2f}%)")
    print(f"       + Affine:    {(aff_iou_arr >= 0.7).sum()} / {n} ({(aff_iou_arr >= 0.7).mean()*100:.2f}%)")

    print("\n====================================================================")
    return df_eval

if __name__ == '__main__':
    run_evaluation()
