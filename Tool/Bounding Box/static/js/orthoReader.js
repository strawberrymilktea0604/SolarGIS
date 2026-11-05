/**
 * orthoReader.js - Quản lý định dạng dữ liệu, xuất file và sao chép tọa độ
 */
const OrthoReader = {
  /**
   * Tạo chuỗi JSON định dạng chi tiết tọa độ BBox
   */
  formatPixelJSON(pixelBox) {
    return JSON.stringify({
      xmin: pixelBox.xmin,
      ymin: pixelBox.ymin,
      xmax: pixelBox.xmax,
      ymax: pixelBox.ymax,
      width: pixelBox.width,
      height: pixelBox.height,
      center_x: pixelBox.center_x,
      center_y: pixelBox.center_y
    }, null, 2);
  },

  /**
   * Định dạng chuẩn hóa (0.0 -> 1.0)
   */
  formatNormJSON(normBox) {
    return JSON.stringify({
      norm_xmin: normBox.xmin,
      norm_ymin: normBox.ymin,
      norm_xmax: normBox.xmax,
      norm_ymax: normBox.ymax,
      norm_width: normBox.width,
      norm_height: normBox.height,
      norm_center_x: normBox.center_x,
      norm_center_y: normBox.center_y
    }, null, 2);
  },

  /**
   * Định dạng GeoJSON
   */
  formatGeoJSON(geojsonData) {
    return JSON.stringify(geojsonData, null, 2);
  },

  /**
   * Kích hoạt tải về file văn bản (YOLO txt, GeoJSON, v.v.)
   */
  downloadFile(content, fileName, contentType = 'text/plain') {
    const blob = new Blob([content], { type: contentType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  /**
   * Sao chép nội dung vào Clipboard kèm hiệu ứng trực quan
   */
  copyToClipboard(text, btnElement) {
    navigator.clipboard.writeText(text).then(() => {
      const originalHTML = btnElement.innerHTML;
      btnElement.innerHTML = '<i class="fa-solid fa-check" style="color:#10b981;"></i> Đã chép';
      setTimeout(() => {
        btnElement.innerHTML = originalHTML;
      }, 1800);
    }).catch(err => {
      console.error('Không thể chép vào clipboard:', err);
    });
  }
};

window.OrthoReader = OrthoReader;
