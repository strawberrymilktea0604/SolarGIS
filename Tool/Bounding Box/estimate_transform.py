import pandas as pd
import numpy as np
import ast
from sklearn.model_selection import train_test_split
import math

def parse_pixel(p_str):
    if pd.isna(p_str): return None
    try:
        return ast.literal_eval(p_str)
    except:
        return None

def compute_affine_least_squares(src_pts, dst_pts):
    # src_pts: Nx2, dst_pts: Nx2
    # Equation: [x_s y_s 1 0 0 0] [a] = [x_t]
    #           [0 0 0 x_s y_s 1] [b] = [y_t]
    #                             [c]
    #                             [d]
    #                             [e]
    #                             [f]
    A = []
    B = []
    for (xs, ys), (xt, yt) in zip(src_pts, dst_pts):
        A.append([xs, ys, 1, 0, 0, 0])
        A.append([0, 0, 0, xs, ys, 1])
        B.append(xt)
        B.append(yt)
    A = np.array(A)
    B = np.array(B)
    # Solve A * X = B
    X, res, rank, s = np.linalg.lstsq(A, B, rcond=None)
    M = np.array([
        [X[0], X[1], X[2]],
        [X[3], X[4], X[5]],
        [0, 0, 1]
    ])
    return M

def ransac_affine(src_pts, dst_pts, threshold=1.0, max_iters=1000):
    best_inliers = []
    best_M = None
    n_pts = len(src_pts)
    if n_pts < 3:
        return None, []
    
    for _ in range(max_iters):
        # random sample 3 points
        idx = np.random.choice(n_pts, 3, replace=False)
        src_sample = src_pts[idx]
        dst_sample = dst_pts[idx]
        
        M = compute_affine_least_squares(src_sample, dst_sample)
        
        # calculate errors
        src_homo = np.hstack([src_pts, np.ones((n_pts, 1))]).T
        dst_pred = (M @ src_homo).T[:, :2]
        errors = np.linalg.norm(dst_pred - dst_pts, axis=1)
        
        inliers = np.where(errors < threshold)[0]
        if len(inliers) > len(best_inliers):
            best_inliers = inliers
            best_M = M
            
    # Recompute with all inliers
    if len(best_inliers) >= 3:
        best_M = compute_affine_least_squares(src_pts[best_inliers], dst_pts[best_inliers])
        
    return best_M, best_inliers

def main():
    # 1. Read files
    df_src = pd.read_csv('PV_Coordinates_Ortho_Vung_1_20260929_0018.csv')
    df_tgt = pd.read_csv('bbox_centroid_export.csv')
    
    # 2. Match points
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: x.split(' ')[0] if isinstance(x, str) else '')
    merged = pd.merge(df_src, df_tgt, left_on='match_id', right_on='module_id')
    
    # We will map Source Pixel -> Target UTM
    src_pts = merged[['Pixel_U', 'Pixel_V']].values
    dst_pts = merged[['centroid_x', 'centroid_y']].values
    
    # 3. Split into Control Points and Check Points
    src_train, src_test, dst_train, dst_test, idx_train, idx_test = train_test_split(
        src_pts, dst_pts, merged.index, test_size=0.2, random_state=42)
    
    # 4. RANSAC + Least Squares
    threshold_m = 0.5 # 0.5 meters threshold for inliers
    M, inliers = ransac_affine(src_train, dst_train, threshold=threshold_m, max_iters=2000)
    
    # 5. Evaluate on Check Points (Independent Check Points)
    src_test_homo = np.hstack([src_test, np.ones((len(src_test), 1))]).T
    dst_test_pred = (M @ src_test_homo).T[:, :2]
    test_errors = np.linalg.norm(dst_test_pred - dst_test, axis=1)
    rmse = np.sqrt(np.mean(test_errors**2))
    
    print(f"Total matched pairs: {len(merged)}")
    print(f"Control Points: {len(src_train)} (Inliers: {len(inliers)})")
    print(f"Check Points: {len(src_test)}")
    print(f"RMSE on Check Points: {rmse:.3f} meters")
    
    # 6. Apply to OBBs
    def apply_transform(pixel_str):
        pt = parse_pixel(pixel_str)
        if pt is None: return None
        pt_homo = np.array([pt[0], pt[1], 1.0])
        res = M @ pt_homo
        return (round(res[0], 3), round(res[1], 3))

    df_src['Mapped_NW_UTM'] = df_src['BBox_NW_Pixel'].apply(apply_transform)
    df_src['Mapped_NE_UTM'] = df_src['BBox_NE_Pixel'].apply(apply_transform)
    df_src['Mapped_SE_UTM'] = df_src['BBox_SE_Pixel'].apply(apply_transform)
    df_src['Mapped_SW_UTM'] = df_src['BBox_SW_Pixel'].apply(apply_transform)
    
    # Add predicted centroid to evaluate per-point in the output
    def apply_transform_pt(u, v):
        res = M @ np.array([u, v, 1.0])
        return res[0], res[1]
    
    pred_centroids = [apply_transform_pt(u, v) for u, v in zip(df_src['Pixel_U'], df_src['Pixel_V'])]
    df_src['Mapped_Centroid_X'] = [p[0] for p in pred_centroids]
    df_src['Mapped_Centroid_Y'] = [p[1] for p in pred_centroids]
    
    df_src.to_csv('mapped_obb_results.csv', index=False)
    print("Saved results to Bounding Box/mapped_obb_results.csv")

if __name__ == '__main__':
    main()
