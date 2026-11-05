#!/usr/bin/env python3
"""
Chọn ĐÚNG ảnh drone để chiếu, và khử trùng lặp giữa các ảnh chồng lấn.

Giải quyết 3 vấn đề:

  (1) Không phải camera nào trong cameras.xml cũng dùng được: camera chưa align thì
      KHÔNG có thẻ <transform> và cũng không đóng góp vào orthophoto -> phải lọc bỏ.

  (2) Một điểm dưới đất nằm trong nhiều ảnh. Ảnh ĐÚNG để chiếu là ảnh mà điểm đó
      GẦN TÂM ẢNH NHẤT (góc off-nadir nhỏ nhất) -> xê dịch do độ cao tấm pin nhỏ nhất.
      Đây cũng là tiêu chí Metashape dùng khi ghép mosaic, nên khớp với ortho.

  (3) Cùng một lỗi bị phát hiện lại ở các ảnh chồng lấn -> gộp theo ngưỡng IoU
      trên toạ độ ORTHO (mặc định 0.3), giữ lần quan sát có góc off-nadir nhỏ nhất.

Cách dùng:
  # Thống kê ảnh đã align / chưa align trong XML
  python ma/camera_select.py --xml cameras_v6.xml --list

  # Tìm ảnh tốt nhất để chiếu một điểm thực địa
  python ma/camera_select.py --xml cameras_v6.xml --lon 108.8514744 --lat 11.4246698 --alt 46.5 --top 5

  # Tính ô "sở hữu" của mỗi ảnh theo độ chồng phủ bay
  python ma/camera_select.py --xml cameras_v6.xml --overlap 0.30
"""

import argparse
import sys
import xml.etree.ElementTree as ET

import numpy as np


# ============================================================================
# 1. ĐỌC XML ĐẦY ĐỦ (sensor / component / camera) — KHÔNG hard-code id
# ============================================================================
def load_project(xml_path):
    """
    Đọc toàn bộ cameras XML của Metashape.

    Trả về:
        sensors    : {sensor_id: dict intrinsics}
        components : {component_id: dict chunk transform}
        cameras    : {label: dict camera (chỉ gồm ảnh ĐÃ ALIGN)}
        skipped    : [label,...] các ảnh chưa align / bị tắt
    """
    root = ET.parse(xml_path).getroot()
    chunk = root.find(".//chunk")
    if chunk is None:
        raise ValueError("Không tìm thấy <chunk> trong XML")

    # --- sensors ---
    sensors = {}
    for s in chunk.findall(".//sensor"):
        res = s.find("resolution")
        calib = s.find("calibration[@class='adjusted']")
        if calib is None:
            calib = s.find("calibration")
        if res is None or calib is None:
            continue

        def g(tag, default=0.0):
            e = calib.find(tag)
            return float(e.text) if e is not None else default

        sensors[s.get("id")] = {
            "id": s.get("id"),
            "label": s.get("label", ""),
            "width": int(res.get("width")),
            "height": int(res.get("height")),
            "f": g("f"), "cx": g("cx"), "cy": g("cy"),
            "k1": g("k1"), "k2": g("k2"), "k3": g("k3"),
            "p1": g("p1"), "p2": g("p2"),
        }

    # --- components (chunk transform: chunk coords -> ECEF) ---
    components = {}
    for c in chunk.findall(".//component"):
        t = c.find("transform")
        if t is None:
            continue
        rot = t.find("rotation")
        tra = t.find("translation")
        sca = t.find("scale")
        if rot is None or tra is None:
            continue
        components[c.get("id")] = {
            "id": c.get("id"),
            "rotation": np.array(list(map(float, rot.text.split()))).reshape(3, 3),
            "translation": np.array(list(map(float, tra.text.split()))),
            "scale": float(sca.text) if sca is not None else 1.0,
        }

    # --- cameras: CHỈ giữ ảnh đã align (có <transform>) ---
    cameras, skipped = {}, []
    for cam in chunk.findall(".//camera"):
        label = cam.get("label")
        if label is None:
            continue
        if cam.get("enabled") == "false":
            skipped.append((label, "bị tắt (enabled=false)"))
            continue
        tr = cam.find("transform")
        if tr is None or not (tr.text or "").strip():
            skipped.append((label, "chưa align (không có <transform>)"))
            continue

        M = np.array(list(map(float, tr.text.split()))).reshape(4, 4)
        sid = cam.get("sensor_id") or (next(iter(sensors)) if sensors else None)
        cid = cam.get("component_id")
        if cid not in components:
            cid = next(iter(components)) if components else None

        cameras[label] = {
            "label": label,
            "id": cam.get("id"),
            "transform": M,
            "sensor_id": sid,
            "component_id": cid,
        }

    if not components:
        raise ValueError("XML không có component nào kèm <transform> — không quy được về ECEF")

    print(f"[INFO] Sensors   : {len(sensors)}  -> {[s['id'] + ':' + s['label'] for s in sensors.values()]}")
    print(f"[INFO] Components: {len(components)} -> id {list(components)}")
    print(f"[INFO] Camera đã align: {len(cameras)} | bỏ qua: {len(skipped)}")
    return sensors, components, cameras, skipped


# ============================================================================
# 2. CHIẾU NGƯỢC: điểm thực địa -> pixel trên một ảnh cụ thể
# ============================================================================
def wgs84_to_ecef(lon, lat, alt):
    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
    return np.array(tf.transform(lon, lat, alt))


def ecef_to_pixel(P_ecef, cam, sensor, comp):
    """
    Chiếu một điểm ECEF vào ảnh -> pixel (u, v) trên ẢNH ĐÃ UNDISTORT.

    Ngược lại đúng với pixel_to_ray_ecef_undistorted() trong project_box_to_ortho.py.
    Trả về (u, v, theta_deg, r_norm) hoặc None nếu điểm ở SAU lưng camera.
        theta_deg : góc off-nadir của tia (càng nhỏ càng tốt)
        r_norm    : bán kính chuẩn hoá so với nửa đường chéo ảnh (0 = tâm ảnh)
    """
    R, T, S = comp["rotation"], comp["translation"], comp["scale"]
    P_chunk = R.T @ (P_ecef - T) / S

    # Nghịch đảo ma trận 4x4 -> không phụ thuộc việc transform có kèm scale hay không
    Minv = np.linalg.inv(cam["transform"])
    P_cam = (Minv @ np.append(P_chunk, 1.0))[:3]

    if P_cam[2] <= 0:
        return None  # điểm nằm sau lưng camera

    x, y = P_cam[0] / P_cam[2], P_cam[1] / P_cam[2]
    w, h = sensor["width"], sensor["height"]
    u = sensor["f"] * x + w / 2.0 + sensor["cx"]
    v = sensor["f"] * y + h / 2.0 + sensor["cy"]

    theta = np.degrees(np.arctan(np.hypot(x, y)))
    r_norm = np.hypot(u - w / 2.0, v - h / 2.0) / (0.5 * np.hypot(w, h))
    return u, v, theta, r_norm


# ============================================================================
# 3. Ô "SỞ HỮU" CỦA MỖI ẢNH THEO ĐỘ CHỒNG PHỦ BAY
# ============================================================================
def unique_tile(width, height, overlap_side, overlap_fwd=None):
    """
    Vùng trung tâm mà một ảnh chịu trách nhiệm, để cùng một lỗi không bị đếm 2 lần.

        overlap 0.80 -> ô  20% x 20% khung
        overlap 0.30 -> ô  70% x 70% khung

    Trả về (x1, y1, x2, y2) theo pixel ảnh.
    """
    if overlap_fwd is None:
        overlap_fwd = overlap_side
    tw = (1.0 - overlap_side) * width
    th = (1.0 - overlap_fwd) * height
    return ((width - tw) / 2.0, (height - th) / 2.0,
            (width + tw) / 2.0, (height + th) / 2.0)


def in_tile(u, v, tile):
    x1, y1, x2, y2 = tile
    return x1 <= u <= x2 and y1 <= v <= y2


# ============================================================================
# 4. CHỌN ẢNH TỐT NHẤT
# ============================================================================
def select_best_camera(lon, lat, alt, sensors, components, cameras,
                       margin_ratio=0.02, tile_overlap=None, top=5):
    """
    Xếp hạng các ảnh có thể chiếu một điểm thực địa.

    Tiêu chí xếp hạng: góc off-nadir nhỏ nhất (điểm càng gần tâm ảnh càng tốt),
    vì sai số bù relief tỉ lệ thuận với tan(theta).

    tile_overlap : nếu đặt (vd 0.30), chỉ giữ ảnh mà điểm rơi vào Ô SỞ HỮU của ảnh đó.
    """
    P = wgs84_to_ecef(lon, lat, alt)
    hits = []

    for cam in cameras.values():
        sensor = sensors.get(cam["sensor_id"])
        comp = components.get(cam["component_id"])
        if sensor is None or comp is None:
            continue

        res = ecef_to_pixel(P, cam, sensor, comp)
        if res is None:
            continue
        u, v, theta, r_norm = res

        w, h = sensor["width"], sensor["height"]
        mx, my = margin_ratio * w, margin_ratio * h
        if not (mx <= u <= w - mx and my <= v <= h - my):
            continue  # rơi ra ngoài khung (hoặc quá sát mép)

        if tile_overlap is not None:
            if not in_tile(u, v, unique_tile(w, h, tile_overlap)):
                continue

        hits.append({"label": cam["label"], "u": u, "v": v,
                     "theta": theta, "r_norm": r_norm,
                     "sensor_id": cam["sensor_id"]})

    hits.sort(key=lambda d: d["theta"])
    return hits[:top]


# ============================================================================
# 5. GỘP BOX TRÙNG GIỮA CÁC ẢNH (NMS liên ảnh trên toạ độ ORTHO)
# ============================================================================
def quad_iou(q1, q2):
    """IoU của 2 tứ giác lồi (Nx2 float32) trên mặt phẳng ortho."""
    import cv2
    a1 = cv2.contourArea(np.asarray(q1, np.float32))
    a2 = cv2.contourArea(np.asarray(q2, np.float32))
    if a1 <= 0 or a2 <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(np.asarray(q1, np.float32),
                                         np.asarray(q2, np.float32))
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def merge_detections(dets, iou_thr=0.30):
    """
    Gộp các lần phát hiện cùng một lỗi từ nhiều ảnh chồng lấn.

    dets: list dict, mỗi phần tử tối thiểu có
        {"quad": [[c,r] x4] trên ortho, "theta": góc off-nadir, "conf": độ tin cậy, ...}

    Quy tắc: IoU >= iou_thr => cùng một lỗi. Đại diện cụm = quan sát có THETA NHỎ NHẤT
    (chiếu chính xác nhất), conf = max của cụm.
    """
    order = sorted(range(len(dets)), key=lambda i: dets[i].get("theta", 999))
    used = [False] * len(dets)
    merged = []

    for i in order:
        if used[i]:
            continue
        used[i] = True
        cluster = [dets[i]]
        for j in order:
            if used[j] or j == i:
                continue
            if quad_iou(dets[i]["quad"], dets[j]["quad"]) >= iou_thr:
                used[j] = True
                cluster.append(dets[j])

        rep = dict(dets[i])
        rep["n_views"] = len(cluster)
        rep["conf"] = max(d.get("conf", 0.0) for d in cluster)
        rep["source_images"] = [d.get("image") for d in cluster]
        merged.append(rep)

    return merged


# ============================================================================
# MAIN
# ============================================================================
def main():
    ap = argparse.ArgumentParser(description="Chọn ảnh đúng để chiếu + tính ô sở hữu")
    ap.add_argument("--xml", required=True, help="cameras XML của Metashape")
    ap.add_argument("--list", action="store_true", help="Liệt kê ảnh đã align / bị loại")
    ap.add_argument("--lon", type=float, help="Kinh độ điểm cần chiếu")
    ap.add_argument("--lat", type=float, help="Vĩ độ điểm cần chiếu")
    ap.add_argument("--alt", type=float, help="Cao độ điểm (lấy từ DSM)")
    ap.add_argument("--top", type=int, default=5, help="Số ảnh tốt nhất hiển thị")
    ap.add_argument("--overlap", type=float, default=None,
                    help="Độ chồng phủ bay (vd 0.30) -> tính ô sở hữu, và lọc theo ô đó")
    args = ap.parse_args()

    sensors, components, cameras, skipped = load_project(args.xml)

    if args.list:
        print("\n--- ẢNH BỊ LOẠI (không dùng để chiếu được) ---")
        if not skipped:
            print("  (không có — toàn bộ ảnh đều đã align)")
        for label, why in skipped:
            print(f"  {label:40s} {why}")

    if args.overlap is not None:
        print(f"\n--- Ô SỞ HỮU CỦA MỖI ẢNH (overlap = {args.overlap:.0%}) ---")
        for s in sensors.values():
            x1, y1, x2, y2 = unique_tile(s["width"], s["height"], args.overlap)
            print(f"  sensor {s['id']} ({s['width']}x{s['height']}): "
                  f"({x1:.0f}, {y1:.0f}) -> ({x2:.0f}, {y2:.0f})  "
                  f"= {(x2 - x1) / s['width']:.0%} x {(y2 - y1) / s['height']:.0%} khung")

    if args.lon is not None and args.lat is not None:
        if args.alt is None:
            sys.exit("[ERROR] Cần --alt (cao độ điểm, lấy từ DSM)")
        hits = select_best_camera(args.lon, args.lat, args.alt,
                                  sensors, components, cameras,
                                  tile_overlap=args.overlap, top=args.top)
        print(f"\n--- ẢNH CHIẾU ĐƯỢC ĐIỂM ({args.lon:.8f}, {args.lat:.8f}, {args.alt:.2f}m) ---")
        if not hits:
            print("  KHÔNG có ảnh nào phủ điểm này"
                  + (" trong ô sở hữu của nó (thử bỏ --overlap)" if args.overlap else ""))
        for i, d in enumerate(hits):
            mark = "  <== NÊN DÙNG" if i == 0 else ""
            print(f"  {i + 1}. {d['label']:38s} pixel=({d['u']:7.1f},{d['v']:7.1f}) "
                  f"off-nadir={d['theta']:5.2f}°  r={d['r_norm']:.2f}{mark}")


if __name__ == "__main__":
    main()
