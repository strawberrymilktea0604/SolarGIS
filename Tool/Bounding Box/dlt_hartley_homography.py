"""
Module: dlt_hartley_homography.py
Mục đích:
- Lập trình thuật toán Biến đổi Tuyến tính Trực tiếp (DLT - Direct Linear Transformation)
  để ước lượng ma trận Homography 3x3 (8 bậc tự do) kết hợp chuẩn hóa tọa độ Hartley (Hartley Normalization).
- Sử dụng dữ liệu ghép cặp từ GPS + AI Module ID giữa:
  + File nguồn (detection OBB ortho vùng 35m): PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (5.092 OBB)
  + File tham chiếu (mốc chuẩn QGIS toàn cảnh 85m): bbox_centroid_export.csv (36.544 module)
- Kiểm chứng số học: So sánh điều kiện số (Condition Number kappa(A)) và sai số tái chiếu giữa
  DLT thuần (không chuẩn hóa) và DLT có chuẩn hóa tọa độ Hartley.
- Kết hợp RANSAC để loại bỏ ngoại lai (outliers), tách biệt tập Control Points (70%) và
  Independent Check Points (30%) theo đúng quy định của Cẩm nang kỹ thuật.
- Áp dụng ma trận Homography 3x3 đã tối ưu lên tọa độ 4 đỉnh OBB (NW, NE, SE, SW) và tâm Centroid
  của toàn bộ 5.092 box, quy đổi sang cả hệ tọa độ phẳng UTM Zone 49N (EPSG:32649) và hệ Pixel Ortho 85m.
- Đo đạc sai số tái chiếu tâm, sai số 4 đỉnh, chỉ số chồng lấn hình học (IoU), đối chiếu ngưỡng an toàn
  d_margin = 52,4 cm và xuất ra file CSV: Bounding Box/PV_Homography_DLT_Hartley_Evaluation.csv.
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

# Thông số GeoTIFF của Orthomosaic toàn cảnh 85m (SonarPanelOrthoGeoTIFF.tif)
ORIGIN_X_85M = 265363.45795877185
ORIGIN_Y_85M = 1263901.907597885
RES_M_85M = 0.03  # 3 cm/pixel
DECISION_MARGIN_M = 0.524  # 52.4 cm (nửa chiều rộng module 1.048m)
SEED = 42
FIT_RATIO = 0.70


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
        os.path.abspath(os.path.basename(filename)),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return filename


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


def utm_to_px_85m(x, y):
    """Chuyển đổi tọa độ phẳng UTM (EPSG:32649) sang tọa độ Pixel trên Ortho toàn cảnh 85m"""
    if x is None or y is None:
        return None
    col = (x - ORIGIN_X_85M) / RES_M_85M
    row = (ORIGIN_Y_85M - y) / RES_M_85M
    return (float(col), float(row))


def compute_polygon_iou(poly1, poly2):
    if poly1 is None or poly2 is None:
        return 0.0
    try:
        if not poly1.is_valid:
            poly1 = poly1.buffer(0)
        if not poly2.is_valid:
            poly2 = poly2.buffer(0)
        inter = poly1.intersection(poly2).area
        union = poly1.union(poly2).area
        return float(inter / union) if union > 1e-9 else 0.0
    except Exception:
        return 0.0


# ==============================================================================
# 1. CHUẨN HÓA TỌA ĐỘ HARTLEY (HARTLEY ISOTROPIC NORMALIZATION)
# ==============================================================================
def hartley_normalize(pts):
    """
    Chuẩn hóa đẳng hướng Hartley cho tập điểm 2D (N x 2):
    1. Tính tâm trọng tâm (cx, cy) của tập điểm.
    2. Dịch gốc tọa độ về tâm trọng tâm.
    3. Tính khoảng cách trung bình d_mean từ các điểm đến tâm.
    4. Co giãn sao cho khoảng cách trung bình đến gốc tọa độ bằng sqrt(2).
    5. Trả về: (pts_normalized, T, T_inv)
    """
    pts = np.asarray(pts, dtype=np.float64)
    centroid = np.mean(pts, axis=0)
    shifted = pts - centroid
    dists = np.hypot(shifted[:, 0], shifted[:, 1])
    mean_dist = np.mean(dists)

    if mean_dist < 1e-12:
        scale = 1.0
    else:
        scale = math.sqrt(2.0) / mean_dist

    cx, cy = centroid[0], centroid[1]
    T = np.array([
        [scale, 0.0,   -scale * cx],
        [0.0,   scale, -scale * cy],
        [0.0,   0.0,   1.0]
    ], dtype=np.float64)

    T_inv = np.array([
        [1.0 / scale, 0.0,         cx],
        [0.0,         1.0 / scale, cy],
        [0.0,         0.0,         1.0]
    ], dtype=np.float64)

    pts_norm = shifted * scale
    return pts_norm, T, T_inv


# ==============================================================================
# 2. THUẬT TOÁN DLT (DIRECT LINEAR TRANSFORMATION) + SVD
# ==============================================================================
def build_dlt_matrix(src_pts, dst_pts):
    """
    Xây dựng ma trận hệ số A kích thước (2N x 9) từ N cặp điểm tương ứng (x, y) -> (x', y'):
    Mỗi cặp điểm sinh ra 2 hàng độc lập tuyến tính:
      [-x, -y, -1,  0,  0,  0, x'*x, x'*y, x']
      [ 0,  0,  0, -x, -y, -1, y'*x, y'*y, y']
    """
    src_pts = np.asarray(src_pts, dtype=np.float64)
    dst_pts = np.asarray(dst_pts, dtype=np.float64)
    N = len(src_pts)
    A = np.zeros((2 * N, 9), dtype=np.float64)

    x = src_pts[:, 0]
    y = src_pts[:, 1]
    xp = dst_pts[:, 0]
    yp = dst_pts[:, 1]

    A[0::2, 0] = -x
    A[0::2, 1] = -y
    A[0::2, 2] = -1.0
    A[0::2, 6] = xp * x
    A[0::2, 7] = xp * y
    A[0::2, 8] = xp

    A[1::2, 3] = -x
    A[1::2, 4] = -y
    A[1::2, 5] = -1.0
    A[1::2, 6] = yp * x
    A[1::2, 7] = yp * y
    A[1::2, 8] = yp

    return A


def solve_homography_dlt(src_pts, dst_pts, use_hartley=True, compute_cond=False):
    """
    Giải ma trận Homography H (3x3, 8 bậc tự do) bằng DLT + Phân rã SVD:
    - Nếu use_hartley=True: chuẩn hóa Hartley cho nguồn (Ts) và đích (Tt),
      giải A_n * h_n = 0 bằng SVD, sau đó khôi phục H = Tt^{-1} @ H_n @ Ts.
    - Chuẩn hóa H[2, 2] = 1 để cố định 8 bậc tự do.
    """
    src_pts = np.asarray(src_pts, dtype=np.float64)
    dst_pts = np.asarray(dst_pts, dtype=np.float64)
    if len(src_pts) < 4:
        raise ValueError("Cần tối thiểu 4 cặp điểm để ước lượng Homography 8 bậc tự do.")

    if use_hartley:
        src_norm, Ts, _ = hartley_normalize(src_pts)
        dst_norm, Tt, Tt_inv = hartley_normalize(dst_pts)
        A = build_dlt_matrix(src_norm, dst_norm)
    else:
        A = build_dlt_matrix(src_pts, dst_pts)

    # Phân rã SVD: A = U * S * Vt
    _, S, Vt = np.linalg.svd(A, full_matrices=False)
    h = Vt[-1, :]  # Vector riêng ứng với giá trị kỳ dị nhỏ nhất sigma_9
    H_est = h.reshape(3, 3)

    if use_hartley:
        H = Tt_inv @ H_est @ Ts
    else:
        H = H_est

    # Cố định bậc tự do tỷ lệ: chia cho h_33
    if abs(H[2, 2]) > 1e-15:
        H = H / H[2, 2]

    info = {}
    if compute_cond:
        cond_num = float(S[0] / S[-1]) if S[-1] > 1e-30 else float('inf')
        info['singular_values'] = S
        info['condition_number'] = cond_num

    return H, info


def is_non_collinear_4pts(pts, eps=1e-3):
    """Kiểm tra 4 điểm không có 3 điểm nào thẳng hàng (tránh suy biến ma trận)"""
    for i in range(4):
        p1 = pts[i]
        p2 = pts[(i + 1) % 4]
        p3 = pts[(i + 2) % 4]
        area2 = abs((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0]))
        if area2 < eps:
            return False
    return True


def is_homography_valid(H, src_pts_sample=None):
    """Kiểm tra tính hợp lệ của ma trận Homography (không suy biến, mẫu số w' không đổi dấu/tiệm cận 0)"""
    if H is None or not np.all(np.isfinite(H)):
        return False
    det = np.linalg.det(H)
    if abs(det) < 1e-12 or abs(H[2, 2]) < 1e-12:
        return False
    if src_pts_sample is not None:
        w = H[2, 0] * src_pts_sample[:, 0] + H[2, 1] * src_pts_sample[:, 1] + H[2, 2]
        if np.any(np.abs(w) < 1e-6) or not (np.all(w > 0) or np.all(w < 0)):
            return False
    return True


def project_points_homography(pts, H, eps=1e-9):
    """
    Ánh xạ tập điểm 2D (N x 2) hoặc 1 điểm (x, y) qua ma trận Homography H (3x3):
      x' = (h11*x + h12*y + h13) / (h31*x + h32*y + h33)
      y' = (h21*x + h22*y + h23) / (h31*x + h32*y + h33)
    """
    pts_arr = np.asarray(pts, dtype=np.float64)
    single = (pts_arr.ndim == 1)
    if single:
        pts_arr = pts_arr.reshape(1, 2)

    ones = np.ones((len(pts_arr), 1), dtype=np.float64)
    pts_homo = np.hstack([pts_arr, ones])  # N x 3
    transformed = pts_homo @ H.T  # N x 3
    w = transformed[:, 2:3]
    # Tránh chia cho mẫu số quá gần 0
    w = np.where(np.abs(w) < eps, np.sign(w + 1e-15) * eps, w)
    out = transformed[:, :2] / w

    if single:
        return (float(out[0, 0]), float(out[0, 1]))
    return out


# ==============================================================================
# 3. KẾT HỢP RANSAC + DLT CHUẨN HÓA HARTLEY
# ==============================================================================
def ransac_dlt_homography(src_pts, dst_pts, threshold=0.5, max_iters=2000, seed=42):
    """
    Ước lượng Homography bền vững bằng RANSAC kết hợp DLT + Chuẩn hóa Hartley:
    1. Lấy mẫu ngẫu nhiên 4 cặp điểm không thẳng hàng.
    2. Giải H thử nghiệm bằng DLT + Hartley trên 4 điểm.
    3. Tính sai số tái chiếu e_i trên toàn bộ tập điểm và đếm số inliers (e_i < threshold).
    4. Sau khi tìm được tập inliers lớn nhất, ước lượng lại (refit) ma trận H cuối cùng
       bằng DLT + Hartley trên toàn bộ tập inliers.
    """
    src_pts = np.asarray(src_pts, dtype=np.float64)
    dst_pts = np.asarray(dst_pts, dtype=np.float64)
    N = len(src_pts)
    rng = np.random.default_rng(seed)

    best_inliers = np.zeros(N, dtype=bool)
    best_count = 0
    best_H = None

    for _ in range(max_iters):
        idx = rng.choice(N, size=4, replace=False)
        s_sample = src_pts[idx]
        d_sample = dst_pts[idx]

        if not is_non_collinear_4pts(s_sample):
            continue

        try:
            H_cand, _ = solve_homography_dlt(s_sample, d_sample, use_hartley=True)
        except Exception:
            continue

        if not is_homography_valid(H_cand, src_pts):
            continue

        pred = project_points_homography(src_pts, H_cand)
        errors = np.hypot(pred[:, 0] - dst_pts[:, 0], pred[:, 1] - dst_pts[:, 1])
        inliers = errors < threshold
        count = int(np.sum(inliers))

        if count > best_count:
            best_count = count
            best_inliers = inliers
            best_H = H_cand

    # Refit bằng DLT + Hartley trên tập inliers và tinh chỉnh tập inliers (Iterative Refit)
    if best_count >= 4:
        for _ in range(3):
            best_H, info = solve_homography_dlt(
                src_pts[best_inliers], dst_pts[best_inliers], use_hartley=True, compute_cond=True
            )
            pred = project_points_homography(src_pts, best_H)
            errors = np.hypot(pred[:, 0] - dst_pts[:, 0], pred[:, 1] - dst_pts[:, 1])
            new_inliers = errors < threshold
            if int(np.sum(new_inliers)) >= best_count:
                best_inliers = new_inliers
                best_count = int(np.sum(new_inliers))
        best_H, info = solve_homography_dlt(
            src_pts[best_inliers], dst_pts[best_inliers], use_hartley=True, compute_cond=True
        )
    else:
        best_H, info = solve_homography_dlt(src_pts, dst_pts, use_hartley=True, compute_cond=True)
        best_inliers = np.ones(N, dtype=bool)

    return best_H, best_inliers, info


def compute_metrics(errors_m):
    arr = np.asarray(errors_m, dtype=np.float64)
    return {
        'count': len(arr),
        'mean_cm': round(float(np.mean(arr) * 100.0), 2),
        'median_cm': round(float(np.median(arr) * 100.0), 2),
        'rmse_cm': round(float(np.sqrt(np.mean(arr ** 2)) * 100.0), 2),
        'p95_cm': round(float(np.percentile(arr, 95) * 100.0), 2),
        'min_cm': round(float(np.min(arr) * 100.0), 2),
        'max_cm': round(float(np.max(arr) * 100.0), 2),
        'safe_count': int(np.sum(arr <= DECISION_MARGIN_M)),
        'safe_pct': round(float(np.mean(arr <= DECISION_MARGIN_M) * 100.0), 2),
        'exceed_count': int(np.sum(arr > DECISION_MARGIN_M)),
        'exceed_pct': round(float(np.mean(arr > DECISION_MARGIN_M) * 100.0), 2),
    }


def run_dlt_hartley_pipeline(
    src_csv_path='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
    ref_csv_path='bbox_centroid_export.csv',
    out_csv_path='PV_Homography_DLT_Hartley_Evaluation.csv'
):
    src_csv_path = resolve_file_path(src_csv_path)
    ref_csv_path = resolve_file_path(ref_csv_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(out_csv_path):
        out_csv_path = os.path.join(script_dir, os.path.basename(out_csv_path))

    print("================================================================================")
    print(" LẬP TRÌNH THUẬT TOÁN DLT CHO HOMOGRAPHY (8 DOF) CÓ CHUẨN HÓA TỌA ĐỘ HARTLEY")
    print("================================================================================")
    print(f"1. File CSV detection nguồn (35m): {src_csv_path}")
    print(f"2. File CSV tham chiếu chuẩn (85m): {ref_csv_path}")

    df_src = pd.read_csv(src_csv_path)
    df_ref = pd.read_csv(ref_csv_path)

    # Ghép cặp bằng GPS + AI Module ID (Point_Name <-> module_id)
    df_src['match_id'] = df_src['Point_Name'].apply(
        lambda x: str(x).split(' ')[0].strip() if pd.notna(x) else ''
    )
    df_ref['match_id'] = df_ref['module_id'].apply(
        lambda x: str(x).strip() if pd.notna(x) else ''
    )

    merged = pd.merge(df_src, df_ref, on='match_id', how='left', suffixes=('_src', '_ref'))
    matched_mask = merged['centroid_x'].notna()
    matched = merged[matched_mask].copy().reset_index(drop=True)
    print(f"3. Kết quả ghép cặp GPS + AI Matching: {len(matched)} / {len(df_src)} cặp điểm tương ứng ({len(matched)/len(df_src)*100:.2f}%)")

    # Tọa độ nguồn (Pixel 35m) và Tọa độ đích (UTM 85m & Pixel 85m)
    src_pts_all = matched[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst_utm_all = matched[['centroid_x', 'centroid_y']].values.astype(np.float64)
    dst_px85_all = np.array([utm_to_px_85m(x, y) for x, y in dst_utm_all], dtype=np.float64)

    # Chia tập điểm: 70% Control Points (3.549 điểm ước lượng) / 30% Independent Check Points (1.522 điểm kiểm tra độc lập)
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(matched))
    n_fit = int(len(matched) * FIT_RATIO)
    is_fit_matched = np.zeros(len(matched), dtype=bool)
    is_fit_matched[perm[:n_fit]] = True

    src_fit, dst_fit = src_pts_all[is_fit_matched], dst_utm_all[is_fit_matched]
    src_chk, dst_chk = src_pts_all[~is_fit_matched], dst_utm_all[~is_fit_matched]

    print(f"4. Phân tách tập dữ liệu (Seed={SEED}):")
    print(f"   - Tập Control Points (Ước lượng): {len(src_fit)} cặp điểm (70%)")
    print(f"   - Tập Independent Check Points (Kiểm định độc lập): {len(src_chk)} cặp điểm (30%)")

    # --------------------------------------------------------------------------
    # SO SÁNH SỐ HỌC: DLT KHÔNG CHUẨN HÓA vs DLT CÓ CHUẨN HÓA HARTLEY
    # --------------------------------------------------------------------------
    _, Ts_demo, _ = hartley_normalize(src_fit)
    _, Tt_demo, _ = hartley_normalize(dst_fit)
    print("\n5. Ma trận chuẩn hóa tọa độ Hartley trên tập Control Points:")
    print("   - Ma trận chuẩn hóa nguồn Ts (Pixel 35m -> Chuẩn hóa):")
    print(np.array2string(Ts_demo, precision=6, suppress_small=False))
    print("   - Ma trận chuẩn hóa đích Tt (UTM 85m -> Chuẩn hóa):")
    print(np.array2string(Tt_demo, precision=6, suppress_small=False))

    # Bước RANSAC + DLT Hartley trên tập Control Points
    H_utm, inlier_mask_fit, info_hartley = ransac_dlt_homography(
        src_fit, dst_fit, threshold=0.5, max_iters=2000, seed=SEED
    )
    inliers_count = int(np.sum(inlier_mask_fit))

    # So sánh trực tiếp trên cùng tập Inliers giữa DLT không chuẩn hóa và DLT có chuẩn hóa Hartley
    H_raw_inliers, info_raw = solve_homography_dlt(
        src_fit[inlier_mask_fit], dst_fit[inlier_mask_fit], use_hartley=False, compute_cond=True
    )
    pred_chk_raw = project_points_homography(src_chk, H_raw_inliers)
    err_chk_raw = np.hypot(pred_chk_raw[:, 0] - dst_chk[:, 0], pred_chk_raw[:, 1] - dst_chk[:, 1])

    pred_chk_hartley = project_points_homography(src_chk, H_utm)
    err_chk_hartley = np.hypot(pred_chk_hartley[:, 0] - dst_chk[:, 0], pred_chk_hartley[:, 1] - dst_chk[:, 1])

    print("\n6. Đánh giá hiệu quả ổn định số học của chuẩn hóa Hartley (trên tập Inliers):")
    print(f"   - Số điểm Inliers (RANSAC threshold < 0.5m): {inliers_count} / {len(src_fit)} ({inliers_count/len(src_fit)*100:.2f}%)")
    print(f"   - Điều kiện số kappa(A) KHÔNG chuẩn hóa Hartley: {info_raw['condition_number']:.3e}")
    print(f"   - Điều kiện số kappa(A) CÓ chuẩn hóa Hartley:    {info_hartley['condition_number']:.4f}")
    print(f"   - Cải thiện điều kiện số: Giảm {info_raw['condition_number']/info_hartley['condition_number']:.2e} lần!")
    print(f"   - Sai số RMSE trên Check Points (DLT thuần không chuẩn hóa): {np.sqrt(np.mean(err_chk_raw**2))*100:.2f} cm (Median: {np.median(err_chk_raw)*100:.2f} cm)")
    print(f"   - Sai số RMSE trên Check Points (DLT + Chuẩn hóa Hartley):   {np.sqrt(np.mean(err_chk_hartley**2))*100:.2f} cm (Median: {np.median(err_chk_hartley)*100:.2f} cm)")

    # Ước lượng thêm ma trận Homography ánh xạ trực tiếp từ Pixel 35m -> Pixel 85m (Canvas)
    H_px85, _ = solve_homography_dlt(
        src_fit[inlier_mask_fit], dst_px85_all[is_fit_matched][inlier_mask_fit], use_hartley=True
    )

    print("\n7. Ma trận Homography H (3x3, 8 DOF) khôi phục về hệ tọa độ gốc:")
    print("   a) Hệ Pixel 35m -> Hệ UTM 85m (EPSG:32649):")
    for row_vals in H_utm:
        print(f"      [{row_vals[0]:16.8e}, {row_vals[1]:16.8e}, {row_vals[2]:16.8e}]")
    print("   b) Hệ Pixel 35m -> Hệ Pixel Ortho toàn cảnh 85m:")
    for row_vals in H_px85:
        print(f"      [{row_vals[0]:16.8e}, {row_vals[1]:16.8e}, {row_vals[2]:16.8e}]")

    # Ước lượng Affine (6 DOF) trên cùng tập Control Points để đối sánh khách quan
    M_affine, _ = cv2.estimateAffine2D(
        src_fit.astype(np.float32), dst_fit.astype(np.float32),
        method=cv2.RANSAC, ransacReprojThreshold=0.5
    )

    def project_affine(pt):
        if pt is None:
            return None
        v = np.array([pt[0], pt[1], 1.0], dtype=np.float64)
        r = M_affine @ v
        return (float(r[0]), float(r[1]))

    # --------------------------------------------------------------------------
    # ÁP DỤNG MA TRẬN HOMOGRAPHY LÊN TOÀN BỘ 5.092 OBB TRONG CSV DETECTION
    # --------------------------------------------------------------------------
    transformer_wgs_to_utm = pyproj.Transformer.from_crs('EPSG:4326', 'EPSG:32649', always_xy=True)

    # Map merged index -> role (CONTROL_FIT_70 / CHECK_INDEPENDENT_30)
    matched_indices = merged.index[matched_mask].to_numpy()
    role_by_idx = {}
    inlier_by_idx = {}
    fit_sub_idx = 0
    for pos, m_idx in enumerate(matched_indices):
        if is_fit_matched[pos]:
            role_by_idx[m_idx] = 'CONTROL_FIT_70'
            inlier_by_idx[m_idx] = bool(inlier_mask_fit[fit_sub_idx])
            fit_sub_idx += 1
        else:
            role_by_idx[m_idx] = 'CHECK_INDEPENDENT_30'
            inlier_by_idx[m_idx] = True

    umin, umax = src_pts_all[:, 0].min(), src_pts_all[:, 0].max()
    vmin, vmax = src_pts_all[:, 1].min(), src_pts_all[:, 1].max()

    records = []
    err_gps_all, err_aff_all, err_homo_all = [], [], []
    err_gps_chk, err_aff_chk, err_homo_chk = [], [], []
    err_homo_fit, err_homo_inliers = [], []
    cor_err_aff_all, cor_err_homo_all = [], []
    cor_err_aff_chk, cor_err_homo_chk = [], []
    iou_gps_all, iou_aff_all, iou_homo_all = [], [], []
    iou_gps_chk, iou_aff_chk, iou_homo_chk = [], [], []

    for idx, row in merged.iterrows():
        point_name = row['Point_Name']
        match_id = row['match_id']
        cls_name = str(row.get('Class', 'Unclassified')).strip() if pd.notna(row.get('Class')) else 'Unclassified'

        u = float(row['Pixel_U'])
        v = float(row['Pixel_V'])
        nw_px = parse_tuple_coords(row['BBox_NW_Pixel'])
        ne_px = parse_tuple_coords(row['BBox_NE_Pixel'])
        se_px = parse_tuple_coords(row['BBox_SE_Pixel'])
        sw_px = parse_tuple_coords(row['BBox_SW_Pixel'])

        # Phân vùng không gian trên ortho nguồn
        nx = (u - umin) / max(1.0, (umax - umin))
        ny = (v - vmin) / max(1.0, (vmax - vmin))
        d_edge = min(nx, 1.0 - nx, ny, 1.0 - ny)
        if d_edge < 0.10:
            zone_str = '3_Mep (<10%)'
        elif d_edge < 0.25:
            zone_str = '2_Trung_gian (10-25%)'
        else:
            zone_str = '1_Trung_tam (>=25%)'

        # 1. Ánh xạ bằng Homography DLT + Hartley (sang UTM 85m & Pixel 85m)
        c_homo_utm = project_points_homography((u, v), H_utm)
        nw_homo_utm = project_points_homography(nw_px, H_utm) if nw_px else None
        ne_homo_utm = project_points_homography(ne_px, H_utm) if ne_px else None
        se_homo_utm = project_points_homography(se_px, H_utm) if se_px else None
        sw_homo_utm = project_points_homography(sw_px, H_utm) if sw_px else None

        c_homo_px85 = utm_to_px_85m(c_homo_utm[0], c_homo_utm[1])
        nw_homo_px85 = utm_to_px_85m(nw_homo_utm[0], nw_homo_utm[1]) if nw_homo_utm else None
        ne_homo_px85 = utm_to_px_85m(ne_homo_utm[0], ne_homo_utm[1]) if ne_homo_utm else None
        se_homo_px85 = utm_to_px_85m(se_homo_utm[0], se_homo_utm[1]) if se_homo_utm else None
        sw_homo_px85 = utm_to_px_85m(sw_homo_utm[0], sw_homo_utm[1]) if sw_homo_utm else None

        # 2. Ánh xạ bằng Affine 6 DOF (để đối chứng)
        c_aff_utm = project_affine((u, v))
        nw_aff_utm = project_affine(nw_px)
        ne_aff_utm = project_affine(ne_px)
        se_aff_utm = project_affine(se_px)
        sw_aff_utm = project_affine(sw_px)

        # 3. Tọa độ GPS thuần (Baseline)
        c_gps_utm = (float(row['UTM_X']), float(row['UTM_Y']))

        # 4. Đo đạc sai số với mốc chuẩn QGIS (bbox_centroid_export.csv)
        has_ref = pd.notna(row['module_id'])
        role_str = role_by_idx.get(idx, 'UNMATCHED_NO_REF')
        is_inlier_val = inlier_by_idx.get(idx, '')

        e_gps_cm = e_aff_cm = e_homo_cm = None
        mean_cor_aff_cm = mean_cor_homo_cm = None
        iou_gps = iou_aff = iou_homo = None
        dx_homo_cm = dy_homo_cm = None
        status_str = 'NGOAI_PHAM_VI_85M'

        if has_ref:
            ref_c_utm = (float(row['centroid_x']), float(row['centroid_y']))
            ref_tl = parse_tuple_coords(row['corner_top_left'])
            ref_tr = parse_tuple_coords(row['corner_top_right'])
            ref_br = parse_tuple_coords(row['corner_bottom_right'])
            ref_bl = parse_tuple_coords(row['corner_bottom_left'])

            # Sai số tái chiếu tâm (m & cm)
            e_gps_m = math.hypot(c_gps_utm[0] - ref_c_utm[0], c_gps_utm[1] - ref_c_utm[1])
            e_aff_m = math.hypot(c_aff_utm[0] - ref_c_utm[0], c_aff_utm[1] - ref_c_utm[1])
            e_homo_m = math.hypot(c_homo_utm[0] - ref_c_utm[0], c_homo_utm[1] - ref_c_utm[1])

            e_gps_cm = round(e_gps_m * 100.0, 2)
            e_aff_cm = round(e_aff_m * 100.0, 2)
            e_homo_cm = round(e_homo_m * 100.0, 2)
            dx_homo_cm = round((c_homo_utm[0] - ref_c_utm[0]) * 100.0, 2)
            dy_homo_cm = round((c_homo_utm[1] - ref_c_utm[1]) * 100.0, 2)

            err_gps_all.append(e_gps_m)
            err_aff_all.append(e_aff_m)
            err_homo_all.append(e_homo_m)

            if role_str == 'CHECK_INDEPENDENT_30':
                err_gps_chk.append(e_gps_m)
                err_aff_chk.append(e_aff_m)
                err_homo_chk.append(e_homo_m)
            elif role_str == 'CONTROL_FIT_70':
                err_homo_fit.append(e_homo_m)
                if is_inlier_val:
                    err_homo_inliers.append(e_homo_m)

            # Sai số 4 đỉnh OBB (NW<->TL, NE<->TR, SE<->BR, SW<->BL)
            if all([nw_homo_utm, ne_homo_utm, se_homo_utm, sw_homo_utm, ref_tl, ref_tr, ref_br, ref_bl]):
                c_errs_homo = [
                    math.hypot(nw_homo_utm[0] - ref_tl[0], nw_homo_utm[1] - ref_tl[1]),
                    math.hypot(ne_homo_utm[0] - ref_tr[0], ne_homo_utm[1] - ref_tr[1]),
                    math.hypot(se_homo_utm[0] - ref_br[0], se_homo_utm[1] - ref_br[1]),
                    math.hypot(sw_homo_utm[0] - ref_bl[0], sw_homo_utm[1] - ref_bl[1]),
                ]
                c_errs_aff = [
                    math.hypot(nw_aff_utm[0] - ref_tl[0], nw_aff_utm[1] - ref_tl[1]),
                    math.hypot(ne_aff_utm[0] - ref_tr[0], ne_aff_utm[1] - ref_tr[1]),
                    math.hypot(se_aff_utm[0] - ref_br[0], se_aff_utm[1] - ref_br[1]),
                    math.hypot(sw_aff_utm[0] - ref_bl[0], sw_aff_utm[1] - ref_bl[1]),
                ]
                mean_cor_homo_cm = round(float(np.mean(c_errs_homo) * 100.0), 2)
                mean_cor_aff_cm = round(float(np.mean(c_errs_aff) * 100.0), 2)
                cor_err_homo_all.append(mean_cor_homo_cm)
                cor_err_aff_all.append(mean_cor_aff_cm)
                if role_str == 'CHECK_INDEPENDENT_30':
                    cor_err_homo_chk.append(mean_cor_homo_cm)
                    cor_err_aff_chk.append(mean_cor_aff_cm)

                # Tính IoU đa giác 4 đỉnh
                poly_ref = Polygon([ref_bl, ref_br, ref_tr, ref_tl])
                poly_homo = Polygon([sw_homo_utm, se_homo_utm, ne_homo_utm, nw_homo_utm])
                poly_aff = Polygon([sw_aff_utm, se_aff_utm, ne_aff_utm, nw_aff_utm])

                nw_gps = parse_tuple_coords(row['BBox_NW_GPS'])
                ne_gps = parse_tuple_coords(row['BBox_NE_GPS'])
                se_gps = parse_tuple_coords(row['BBox_SE_GPS'])
                sw_gps = parse_tuple_coords(row['BBox_SW_GPS'])
                if all([nw_gps, ne_gps, se_gps, sw_gps]):
                    poly_gps = Polygon([
                        transformer_wgs_to_utm.transform(*sw_gps),
                        transformer_wgs_to_utm.transform(*se_gps),
                        transformer_wgs_to_utm.transform(*ne_gps),
                        transformer_wgs_to_utm.transform(*nw_gps),
                    ])
                    iou_gps = round(compute_polygon_iou(poly_gps, poly_ref), 4)
                    iou_gps_all.append(iou_gps)
                    if role_str == 'CHECK_INDEPENDENT_30':
                        iou_gps_chk.append(iou_gps)

                iou_aff = round(compute_polygon_iou(poly_aff, poly_ref), 4)
                iou_homo = round(compute_polygon_iou(poly_homo, poly_ref), 4)
                iou_aff_all.append(iou_aff)
                iou_homo_all.append(iou_homo)
                if role_str == 'CHECK_INDEPENDENT_30':
                    iou_aff_chk.append(iou_aff)
                    iou_homo_chk.append(iou_homo)

            status_str = 'AN_TOAN_TRONG_MARGIN' if e_homo_m <= DECISION_MARGIN_M else 'VUOT_MARGIN_52_4CM'

        records.append({
            'Point_Name': point_name,
            'match_id': match_id,
            'Class': cls_name,
            'Data_Split_Role': role_str,
            'RANSAC_Inlier': is_inlier_val,
            'Zone': zone_str,
            'Pixel_U_35m': u,
            'Pixel_V_35m': v,
            'Homo_Centroid_X_UTM': round(c_homo_utm[0], 4),
            'Homo_Centroid_Y_UTM': round(c_homo_utm[1], 4),
            'Homo_Centroid_Col_85m_Px': round(c_homo_px85[0], 2),
            'Homo_Centroid_Row_85m_Px': round(c_homo_px85[1], 2),
            'Homo_NW_UTM': f"({nw_homo_utm[0]:.3f}, {nw_homo_utm[1]:.3f})" if nw_homo_utm else '',
            'Homo_NE_UTM': f"({ne_homo_utm[0]:.3f}, {ne_homo_utm[1]:.3f})" if ne_homo_utm else '',
            'Homo_SE_UTM': f"({se_homo_utm[0]:.3f}, {se_homo_utm[1]:.3f})" if se_homo_utm else '',
            'Homo_SW_UTM': f"({sw_homo_utm[0]:.3f}, {sw_homo_utm[1]:.3f})" if sw_homo_utm else '',
            'Homo_NW_85m_Px': f"({nw_homo_px85[0]:.2f}, {nw_homo_px85[1]:.2f})" if nw_homo_px85 else '',
            'Homo_NE_85m_Px': f"({ne_homo_px85[0]:.2f}, {ne_homo_px85[1]:.2f})" if ne_homo_px85 else '',
            'Homo_SE_85m_Px': f"({se_homo_px85[0]:.2f}, {se_homo_px85[1]:.2f})" if se_homo_px85 else '',
            'Homo_SW_85m_Px': f"({sw_homo_px85[0]:.2f}, {sw_homo_px85[1]:.2f})" if sw_homo_px85 else '',
            'Ref_Module_ID': row['module_id'] if has_ref else '',
            'Ref_Centroid_X_UTM': round(float(row['centroid_x']), 4) if has_ref else '',
            'Ref_Centroid_Y_UTM': round(float(row['centroid_y']), 4) if has_ref else '',
            'Homo_dX_cm': dx_homo_cm if dx_homo_cm is not None else '',
            'Homo_dY_cm': dy_homo_cm if dy_homo_cm is not None else '',
            'Error_GPS_Centroid_cm': e_gps_cm if e_gps_cm is not None else '',
            'Error_Affine_Centroid_cm': e_aff_cm if e_aff_cm is not None else '',
            'Error_Homo_Centroid_cm': e_homo_cm if e_homo_cm is not None else '',
            'Mean_Corner_Err_Affine_cm': mean_cor_aff_cm if mean_cor_aff_cm is not None else '',
            'Mean_Corner_Err_Homo_cm': mean_cor_homo_cm if mean_cor_homo_cm is not None else '',
            'IoU_GPS': iou_gps if iou_gps is not None else '',
            'IoU_Affine': iou_aff if iou_aff is not None else '',
            'IoU_Homo': iou_homo if iou_homo is not None else '',
            'Homo_Exceed_52_4cm': (e_homo_cm > 52.4) if e_homo_cm is not None else '',
            'Trang_Thai_Doi_Soat': status_str,
        })

    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv_path, index=False, encoding='utf-8-sig')
    root_copy = os.path.join(script_dir, "..", os.path.basename(out_csv_path))
    try:
        df_out.to_csv(root_copy, index=False, encoding='utf-8-sig')
    except Exception:
        pass

    # In tổng hợp kết quả
    m_gps_all = compute_metrics(err_gps_all)
    m_aff_all = compute_metrics(err_aff_all)
    m_homo_all = compute_metrics(err_homo_all)

    m_gps_chk = compute_metrics(err_gps_chk)
    m_aff_chk = compute_metrics(err_aff_chk)
    m_homo_chk = compute_metrics(err_homo_chk)
    m_homo_fit = compute_metrics(err_homo_fit)
    m_homo_inl = compute_metrics(err_homo_inliers)

    print("\n8. KẾT QUẢ KIỂM TRA SAI SỐ TÁI CHIẾU TRÊN CÁC TẬP ĐIỂM (HOMOGRAPHY DLT + HARTLEY):")
    print(f"   - Tập Inliers ({m_homo_inl['count']} điểm):         Median = {m_homo_inl['median_cm']} cm | Mean = {m_homo_inl['mean_cm']} cm | RMSE = {m_homo_inl['rmse_cm']} cm | P95 = {m_homo_inl['p95_cm']} cm")
    print(f"   - Tập Control Fit 70% ({m_homo_fit['count']} điểm): Median = {m_homo_fit['median_cm']} cm | Mean = {m_homo_fit['mean_cm']} cm | RMSE = {m_homo_fit['rmse_cm']} cm | P95 = {m_homo_fit['p95_cm']} cm")
    print(f"   - Tập Check độc lập 30% ({m_homo_chk['count']} điểm): Median = {m_homo_chk['median_cm']} cm | Mean = {m_homo_chk['mean_cm']} cm | RMSE = {m_homo_chk['rmse_cm']} cm | P95 = {m_homo_chk['p95_cm']} cm")
    print(f"   - Toàn bộ 5.071 cặp khớp ({m_homo_all['count']} điểm): Median = {m_homo_all['median_cm']} cm | Mean = {m_homo_all['mean_cm']} cm | RMSE = {m_homo_all['rmse_cm']} cm | P95 = {m_homo_all['p95_cm']} cm")

    print("\n9. BẢNG ĐỐI SÁNH 3 PHƯƠNG PHÁP TRÊN TẬP KIỂM TRA ĐỘC LẬP (1.522 CHECK POINTS):")
    print(f"   - GPS thuần (Baseline):        Median = {m_gps_chk['median_cm']} cm | Mean = {m_gps_chk['mean_cm']} cm | RMSE = {m_gps_chk['rmse_cm']} cm | P95 = {m_gps_chk['p95_cm']} cm | Vượt 52.4cm = {m_gps_chk['exceed_pct']}% | IoU Mean = {np.mean(iou_gps_chk)*100:.2f}% (Median {np.median(iou_gps_chk)*100:.2f}%)")
    print(f"   - Affine (6 DOF):              Median = {m_aff_chk['median_cm']} cm | Mean = {m_aff_chk['mean_cm']} cm | RMSE = {m_aff_chk['rmse_cm']} cm | P95 = {m_aff_chk['p95_cm']} cm | Vượt 52.4cm = {m_aff_chk['exceed_pct']}% | IoU Mean = {np.mean(iou_aff_chk)*100:.2f}% (Median {np.median(iou_aff_chk)*100:.2f}%)")
    print(f"   - Homography DLT+Hartley (8DOF): Median = {m_homo_chk['median_cm']} cm | Mean = {m_homo_chk['mean_cm']} cm | RMSE = {m_homo_chk['rmse_cm']} cm | P95 = {m_homo_chk['p95_cm']} cm | Vượt 52.4cm = {m_homo_chk['exceed_pct']}% | IoU Mean = {np.mean(iou_homo_chk)*100:.2f}% (Median {np.median(iou_homo_chk)*100:.2f}%)")

    print("\n10. BẢNG ĐỐI SÁNH 3 PHƯƠNG PHÁP TRÊN TOÀN BỘ 5.071 MODULE THAM CHIẾU:")
    print(f"   - GPS thuần (Baseline):        Median = {m_gps_all['median_cm']} cm | Mean = {m_gps_all['mean_cm']} cm | RMSE = {m_gps_all['rmse_cm']} cm | P95 = {m_gps_all['p95_cm']} cm | Vượt 52.4cm = {m_gps_all['exceed_pct']}% ({m_gps_all['exceed_count']} box) | IoU Mean = {np.mean(iou_gps_all)*100:.2f}% (Median {np.median(iou_gps_all)*100:.2f}%)")
    print(f"   - Affine (6 DOF):              Median = {m_aff_all['median_cm']} cm | Mean = {m_aff_all['mean_cm']} cm | RMSE = {m_aff_all['rmse_cm']} cm | P95 = {m_aff_all['p95_cm']} cm | Vượt 52.4cm = {m_aff_all['exceed_pct']}% ({m_aff_all['exceed_count']} box) | IoU Mean = {np.mean(iou_aff_all)*100:.2f}% (Median {np.median(iou_aff_all)*100:.2f}%)")
    print(f"   - Homography DLT+Hartley (8DOF): Median = {m_homo_all['median_cm']} cm | Mean = {m_homo_all['mean_cm']} cm | RMSE = {m_homo_all['rmse_cm']} cm | P95 = {m_homo_all['p95_cm']} cm | Vượt 52.4cm = {m_homo_all['exceed_pct']}% ({m_homo_all['exceed_count']} box) | IoU Mean = {np.mean(iou_homo_all)*100:.2f}% (Median {np.median(iou_homo_all)*100:.2f}%)")
    print(f"   - Sai số trung bình 4 đỉnh OBB (Mean Corner Error - Toàn tập): Affine = {np.mean(cor_err_aff_all):.2f} cm (Median {np.median(cor_err_aff_all):.2f} cm) | Homography = {np.mean(cor_err_homo_all):.2f} cm (Median {np.median(cor_err_homo_all):.2f} cm)")
    print(f"   - Tỷ lệ IoU >= 0.5 (Toàn tập): GPS = {(np.array(iou_gps_all)>=0.5).mean()*100:.2f}% | Affine = {(np.array(iou_aff_all)>=0.5).mean()*100:.2f}% | Homography = {(np.array(iou_homo_all)>=0.5).mean()*100:.2f}%")
    print(f"   - Tỷ lệ IoU >= 0.7 (Toàn tập): GPS = {(np.array(iou_gps_all)>=0.7).mean()*100:.2f}% | Affine = {(np.array(iou_aff_all)>=0.7).mean()*100:.2f}% | Homography = {(np.array(iou_homo_all)>=0.7).mean()*100:.2f}%")

    print(f"\n=> Đã xuất file CSV kết quả nghiệm thu: {out_csv_path}")
    return df_out, H_utm, H_px85


if __name__ == '__main__':
    run_dlt_hartley_pipeline()
