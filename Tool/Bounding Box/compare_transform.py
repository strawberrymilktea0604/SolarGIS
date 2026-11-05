import pandas as pd
import numpy as np
import cv2
import ast
from sklearn.model_selection import train_test_split

def main():
    df_src = pd.read_csv('PV_Coordinates_Ortho_Vung_1_20260929_0018.csv')
    df_tgt = pd.read_csv('bbox_centroid_export.csv')
    
    df_src['match_id'] = df_src['Point_Name'].apply(lambda x: x.split(' ')[0] if isinstance(x, str) else '')
    merged = pd.merge(df_src, df_tgt, left_on='match_id', right_on='module_id')
    
    src_pts = merged[['Pixel_U', 'Pixel_V']].values.astype(np.float32)
    dst_pts = merged[['centroid_x', 'centroid_y']].values.astype(np.float32)
    
    src_train, src_test, dst_train, dst_test = train_test_split(
        src_pts, dst_pts, test_size=0.2, random_state=42)
    
    M_affine, mask_affine = cv2.estimateAffine2D(src_train, dst_train, method=cv2.RANSAC, ransacReprojThreshold=1.0)
    
    M_homo, mask_homo = cv2.findHomography(src_train, dst_train, cv2.RANSAC, 1.0)
    
    src_test_homo = np.hstack([src_test, np.ones((len(src_test), 1))]).T
    dst_pred_affine = (M_affine @ src_test_homo).T[:, :2]
    errors_affine = np.linalg.norm(dst_pred_affine - dst_test, axis=1)
    
    dst_pred_homo_homo = (M_homo @ src_test_homo).T
    dst_pred_homo = dst_pred_homo_homo[:, :2] / dst_pred_homo_homo[:, 2:]
    errors_homo = np.linalg.norm(dst_pred_homo - dst_test, axis=1)
    
    def print_metrics(name, errors, mask):
        print(f"--- {name} ---")
        print(f"Inliers: {np.sum(mask)}")
        print(f"Mean Error: {np.mean(errors):.4f} m")
        print(f"RMSE: {np.sqrt(np.mean(errors**2)):.4f} m")
        print(f"Median Error: {np.median(errors):.4f} m")
        print(f"P95 Error: {np.percentile(errors, 95):.4f} m")
        print(f"Max Error: {np.max(errors):.4f} m")
        print()
        
    print(f"Total pairs: {len(merged)}")
    print(f"Train: {len(src_train)}")
    print(f"Test: {len(src_test)}")
    print()
    
    print_metrics("Affine", errors_affine, mask_affine)
    print_metrics("Homography", errors_homo, mask_homo)

if __name__ == '__main__':
    main()
