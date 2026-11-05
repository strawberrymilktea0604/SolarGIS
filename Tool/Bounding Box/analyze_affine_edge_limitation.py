"""
Module: analyze_affine_edge_limitation.py
Mục đích:
- Ghi nhận hạn chế của mô hình Affine tại các vùng gần mép ortho vùng (bay thấp 35m).
- Nguồn: PV_Coordinates_Ortho_Vung_1_20260929_0018.csv (OBB đã detect, KHÔNG detect lại).
- Mốc đo: bbox_centroid_export.csv (module QGIS trên ortho toàn cảnh 85m).
- Quy trình:
  1. Ghép cặp GPS + AI module ID (Point_Name <-> module_id).
  2. Tách 70% điểm ước lượng (fit) / 30% điểm kiểm tra độc lập (check) - seed cố định.
  3. Ước lượng Affine (6 DOF) và Homography (8 DOF) bằng RANSAC trên CÙNG tập fit.
  4. Phân vùng theo vị trí pixel trên ortho nguồn: Trung tâm / Trung gian / Mép.
  5. Thống kê sai số tâm, IoU, tỷ lệ vượt margin 52,4 cm, vector lệch trung bình theo vùng và lưới 4x4.
- Xuất: PV_Affine_Edge_Limitation_Evaluation.csv (từng box) và PV_Affine_Edge_Zone_Summary.csv (tổng hợp).
"""

import os
import sys
import ast
import numpy as np
import pandas as pd
import cv2
from shapely.geometry import Polygon

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

MARGIN_M = 0.524
SEED = 42
FIT_RATIO = 0.7


def resolve_file_path(filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for c in [filename, os.path.join(script_dir, filename), os.path.join(script_dir, "..", filename)]:
        if os.path.exists(c):
            return os.path.abspath(c)
    return filename


def parse_t(val):
    try:
        r = ast.literal_eval(str(val).strip())
        return (float(r[0]), float(r[1]))
    except Exception:
        return None


def iou(p1, p2):
    try:
        if not p1.is_valid:
            p1 = p1.buffer(0)
        if not p2.is_valid:
            p2 = p2.buffer(0)
        u = p1.union(p2).area
        return float(p1.intersection(p2).area / u) if u > 1e-9 else 0.0
    except Exception:
        return 0.0


def zone_of(d_edge):
    if d_edge < 0.10:
        return '3_Mep (<10%)'
    if d_edge < 0.25:
        return '2_Trung_gian (10-25%)'
    return '1_Trung_tam (>=25%)'


def stats(arr_m):
    a = np.asarray(arr_m, dtype=float)
    if len(a) == 0:
        return dict(n=0, median_cm=np.nan, mean_cm=np.nan, p95_cm=np.nan, max_cm=np.nan, rmse_cm=np.nan, exceed_pct=np.nan)
    return dict(
        n=len(a),
        median_cm=round(np.median(a) * 100, 2),
        mean_cm=round(np.mean(a) * 100, 2),
        p95_cm=round(np.percentile(a, 95) * 100, 2),
        max_cm=round(np.max(a) * 100, 2),
        rmse_cm=round(np.sqrt(np.mean(a ** 2)) * 100, 2),
        exceed_pct=round((a > MARGIN_M).mean() * 100, 2),
    )


def run_evaluation(src_csv='PV_Coordinates_Ortho_Vung_1_20260929_0018.csv',
                   ref_csv='bbox_centroid_export.csv',
                   out_csv='PV_Affine_Edge_Limitation_Evaluation.csv',
                   out_summary='PV_Affine_Edge_Zone_Summary.csv'):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    df_src = pd.read_csv(resolve_file_path(src_csv))
    df_ref = pd.read_csv(resolve_file_path(ref_csv))

    df_src['match_id'] = df_src['Point_Name'].astype(str).str.split(' ').str[0].str.strip()
    df_ref['match_id'] = df_ref['module_id'].astype(str).str.strip()
    m = pd.merge(df_src, df_ref, on='match_id', how='inner').reset_index(drop=True)
    print(f"Cặp module khớp ID: {len(m)} / {len(df_src)}")

    # --- Chuẩn hóa tọa độ để Homography ổn định số học ---
    src = m[['Pixel_U', 'Pixel_V']].values.astype(np.float64)
    dst = m[['centroid_x', 'centroid_y']].values.astype(np.float64)
    s_off = src.mean(axis=0)
    d_off = dst.mean(axis=0)
    src_n = (src - s_off).astype(np.float32)
    dst_n = (dst - d_off).astype(np.float32)

    # --- Tách fit / check độc lập ---
    rng = np.random.default_rng(SEED)
    idx = rng.permutation(len(m))
    n_fit = int(len(m) * FIT_RATIO)
    is_fit = np.zeros(len(m), dtype=bool)
    is_fit[idx[:n_fit]] = True

    A, _ = cv2.estimateAffine2D(src_n[is_fit], dst_n[is_fit], method=cv2.RANSAC, ransacReprojThreshold=0.5)
    H, _ = cv2.findHomography(src_n[is_fit], dst_n[is_fit], cv2.RANSAC, 0.5)
    print("Affine (chuẩn hóa):\n", A)
    print("Homography (chuẩn hóa):\n", H)

    def f_aff(p):
        q = np.array([p[0] - s_off[0], p[1] - s_off[1], 1.0])
        r = A @ q
        return (r[0] + d_off[0], r[1] + d_off[1])

    def f_hom(p):
        q = np.array([p[0] - s_off[0], p[1] - s_off[1], 1.0])
        r = H @ q
        return (r[0] / r[2] + d_off[0], r[1] / r[2] + d_off[1])

    umin, umax = src[:, 0].min(), src[:, 0].max()
    vmin, vmax = src[:, 1].min(), src[:, 1].max()
    print(f"Phạm vi pixel ortho nguồn: U [{umin:.0f}, {umax:.0f}], V [{vmin:.0f}, {vmax:.0f}]")

    rows = []
    for i, r in m.iterrows():
        u, v = r['Pixel_U'], r['Pixel_V']
        nx = (u - umin) / (umax - umin)
        ny = (v - vmin) / (vmax - vmin)
        d_edge = min(nx, 1 - nx, ny, 1 - ny)
        r_norm = np.hypot(nx - 0.5, ny - 0.5) / np.hypot(0.5, 0.5)
        side = min([('Trai(W)', nx), ('Phai(E)', 1 - nx), ('Tren(N)', ny), ('Duoi(S)', 1 - ny)], key=lambda t: t[1])[0]

        ref_c = (r['centroid_x'], r['centroid_y'])
        ca, ch = f_aff((u, v)), f_hom((u, v))
        ea = np.hypot(ca[0] - ref_c[0], ca[1] - ref_c[1])
        eh = np.hypot(ch[0] - ref_c[0], ch[1] - ref_c[1])

        corners_px = [parse_t(r[c]) for c in ['BBox_SW_Pixel', 'BBox_SE_Pixel', 'BBox_NE_Pixel', 'BBox_NW_Pixel']]
        corners_ref = [parse_t(r[c]) for c in ['corner_bottom_left', 'corner_bottom_right', 'corner_top_right', 'corner_top_left']]
        iou_a = iou_h = np.nan
        if all(corners_px) and all(corners_ref):
            pref = Polygon(corners_ref)
            iou_a = iou(Polygon([f_aff(p) for p in corners_px]), pref)
            iou_h = iou(Polygon([f_hom(p) for p in corners_px]), pref)

        cls = r.get('Class', 'Unclassified')
        rows.append({
            'Point_Name': r['Point_Name'], 'match_id': r['match_id'],
            'Class': cls if pd.notna(cls) else 'Unclassified',
            'Pixel_U': u, 'Pixel_V': v,
            'Norm_X': round(nx, 4), 'Norm_Y': round(ny, 4),
            'Dist_To_Edge_Norm': round(d_edge, 4), 'Radial_Norm': round(r_norm, 4),
            'Nearest_Edge': side, 'Zone': zone_of(d_edge),
            'Grid_Cell': f"R{min(int(ny * 4), 3) + 1}C{min(int(nx * 4), 3) + 1}",
            'Point_Role': 'FIT' if is_fit[i] else 'CHECK_DOC_LAP',
            'Ref_X': round(ref_c[0], 4), 'Ref_Y': round(ref_c[1], 4),
            'Affine_X': round(ca[0], 4), 'Affine_Y': round(ca[1], 4),
            'Affine_dX_cm': round((ca[0] - ref_c[0]) * 100, 2), 'Affine_dY_cm': round((ca[1] - ref_c[1]) * 100, 2),
            'Affine_Err_cm': round(ea * 100, 2),
            'Homo_X': round(ch[0], 4), 'Homo_Y': round(ch[1], 4),
            'Homo_Err_cm': round(eh * 100, 2),
            'Delta_Err_Affine_minus_Homo_cm': round((ea - eh) * 100, 2),
            'IoU_Affine': round(iou_a, 4), 'IoU_Homo': round(iou_h, 4),
            'Affine_Exceed_52_4cm': ea > MARGIN_M, 'Homo_Exceed_52_4cm': eh > MARGIN_M,
        })

    df = pd.DataFrame(rows)
    out_path = os.path.join(script_dir, out_csv)
    df.to_csv(out_path, index=False, encoding='utf-8-sig')

    # --- Tổng hợp theo vùng (chỉ điểm kiểm tra độc lập + toàn bộ) ---
    summary = []
    for scope, d_scope in [('CHECK_DOC_LAP', df[df.Point_Role == 'CHECK_DOC_LAP']), ('TOAN_BO', df)]:
        for key_col in ['Zone', 'Nearest_Edge', 'Grid_Cell']:
            for k, g in d_scope.groupby(key_col):
                sa = stats(g.Affine_Err_cm / 100)
                sh = stats(g.Homo_Err_cm / 100)
                summary.append({
                    'Scope': scope, 'Group_By': key_col, 'Group': k, 'N': sa['n'],
                    'Affine_Median_cm': sa['median_cm'], 'Affine_Mean_cm': sa['mean_cm'], 'Affine_P95_cm': sa['p95_cm'],
                    'Affine_Max_cm': sa['max_cm'], 'Affine_RMSE_cm': sa['rmse_cm'], 'Affine_Exceed_pct': sa['exceed_pct'],
                    'Affine_Mean_dX_cm': round(g.Affine_dX_cm.mean(), 2), 'Affine_Mean_dY_cm': round(g.Affine_dY_cm.mean(), 2),
                    'Affine_IoU_Mean': round(g.IoU_Affine.mean(), 4),
                    'Homo_Median_cm': sh['median_cm'], 'Homo_Mean_cm': sh['mean_cm'], 'Homo_P95_cm': sh['p95_cm'],
                    'Homo_RMSE_cm': sh['rmse_cm'], 'Homo_Exceed_pct': sh['exceed_pct'],
                    'Homo_IoU_Mean': round(g.IoU_Homo.mean(), 4),
                })
    df_sum = pd.DataFrame(summary)
    sum_path = os.path.join(script_dir, out_summary)
    df_sum.to_csv(sum_path, index=False, encoding='utf-8-sig')
    for p, d in [(out_csv, df), (out_summary, df_sum)]:
        try:
            d.to_csv(os.path.join(script_dir, '..', p), index=False, encoding='utf-8-sig')
        except Exception:
            pass

    # --- In kết quả ---
    chk = df[df.Point_Role == 'CHECK_DOC_LAP']
    print(f"\nFit: {is_fit.sum()} | Check độc lập: {len(chk)}")
    pd.set_option('display.width', 250)
    pd.set_option('display.max_columns', 30)
    cols = ['Group', 'N', 'Affine_Median_cm', 'Affine_Mean_cm', 'Affine_P95_cm', 'Affine_Max_cm', 'Affine_RMSE_cm',
            'Affine_Exceed_pct', 'Affine_Mean_dX_cm', 'Affine_Mean_dY_cm', 'Affine_IoU_Mean',
            'Homo_Median_cm', 'Homo_P95_cm', 'Homo_RMSE_cm', 'Homo_Exceed_pct', 'Homo_IoU_Mean']
    for gb in ['Zone', 'Nearest_Edge', 'Grid_Cell']:
        print(f"\n=== CHECK_DOC_LAP theo {gb} ===")
        print(df_sum[(df_sum.Scope == 'CHECK_DOC_LAP') & (df_sum.Group_By == gb)][cols].to_string(index=False))
    print("\n=== TOAN_BO theo Zone ===")
    print(df_sum[(df_sum.Scope == 'TOAN_BO') & (df_sum.Group_By == 'Zone')][cols].to_string(index=False))

    sa_all, sh_all = stats(chk.Affine_Err_cm / 100), stats(chk.Homo_Err_cm / 100)
    print("\n=== TỔNG CHECK độc lập ===")
    print("Affine:", sa_all, "IoU", round(chk.IoU_Affine.mean(), 4))
    print("Homo:  ", sh_all, "IoU", round(chk.IoU_Homo.mean(), 4))
    rho = pd.Series(chk.Radial_Norm).corr(pd.Series(chk.Affine_Err_cm), method='spearman')
    rho_e = pd.Series(chk.Dist_To_Edge_Norm).corr(pd.Series(chk.Affine_Err_cm), method='spearman')
    print(f"Spearman(Radial, Err_Affine) = {rho:.3f} | Spearman(Dist_to_edge, Err_Affine) = {rho_e:.3f}")
    print(f"Homography tốt hơn Affine ở {(chk.Delta_Err_Affine_minus_Homo_cm > 0).mean()*100:.2f}% điểm check")
    big = df[df.Affine_Err_cm > 52.4]
    print(f"\nBox Affine vượt 52,4cm: {len(big)} | phân bố vùng:\n{big.Zone.value_counts().to_string()}\n{big.Nearest_Edge.value_counts().to_string()}")
    print(f"\n=> {out_path}\n=> {sum_path}")
    return df, df_sum


if __name__ == '__main__':
    run_evaluation()
