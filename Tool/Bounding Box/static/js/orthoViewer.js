/**
 * orthoViewer.js - Module quản lý hiển thị bản đồ Leaflet, zoom, pan,
 * vẽ Bounding Box phát sáng, thanh trượt opacity và chế độ HD Viewport siêu nét
 */
class OrthoViewer {
  constructor(mapContainerId) {
    this.containerId = mapContainerId;
    this.map = null;
    this.bigOverlay = null;
    this.hdOverlay = null;
    this.subOverlay = null;
    this.bboxLayer = null;
    this.bigInfo = null;
    this.subInfo = null;
    this.matchData = null;
    this.isBBoxVisible = true;
    this.isOverlayVisible = true;
    this.isHDEnabled = true;
    this.currentOpacity = 0.85;
    this.hdDebounceTimer = null;

    this.initMap();
  }

  initMap() {
    this.map = L.map(this.containerId, {
      crs: L.CRS.Simple,
      minZoom: -5,
      maxZoom: 6,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      attributionControl: false,
    });

    // Bắt sự kiện di chuyển chuột để cập nhật HUD tọa độ
    this.map.on('mousemove', (e) => {
      this.handleMouseMove(e);
    });

    this.map.on('zoomend', () => {
      const zoom = this.map.getZoom();
      const zoomPct = Math.round(Math.pow(2, zoom) * 100);
      const zoomEl = document.getElementById('hudZoom');
      if (zoomEl) zoomEl.innerText = `${zoomPct}%`;
    });

    // Tự động làm nét siêu cao (HD auto-refinement) khi người dùng zoom sâu vào khu vực
    this.map.on('moveend', () => {
      if (this.isHDEnabled && this.bigInfo) {
        clearTimeout(this.hdDebounceTimer);
        this.hdDebounceTimer = setTimeout(() => {
          this.refreshHDViewport();
        }, 350);
      }
    });
  }

  loadBigOrtho(bigInfo, previewUrl) {
    this.bigInfo = bigInfo;

    // Ẩn placeholder
    const ph = document.getElementById('viewerPlaceholder');
    if (ph) ph.style.display = 'none';

    // Xóa overlay cũ nếu có
    if (this.bigOverlay) this.map.removeLayer(this.bigOverlay);
    if (this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    }
    this.clearBoundingBox();

    const H = bigInfo.height;
    const W = bigInfo.width;

    // Tọa độ CRS.Simple: góc trên-trái là [0, 0], góc dưới-phải là [-H, W]
    const bounds = [[-H, 0], [0, W]];
    this.bigOverlay = L.imageOverlay(previewUrl, bounds).addTo(this.map);

    this.map.fitBounds(bounds);
  }

  displayBoundingBox(matchData, subPreviewUrl) {
    this.matchData = matchData;
    this.subInfo = matchData.sub_ortho;

    const box = matchData.pixel_box;
    // Bounding Box trong hệ tọa độ Simple:
    // Top-left: [-box.ymin, box.xmin]
    // Bottom-right: [-box.ymax, box.xmax]
    const bounds = [
      [-box.ymax, box.xmin],
      [-box.ymin, box.xmax]
    ];

    // Xóa layer cũ
    if (this.bboxLayer) this.map.removeLayer(this.bboxLayer);
    if (this.subOverlay) this.map.removeLayer(this.subOverlay);

    // 1. Lớp phủ ảnh vùng con với Opacity có thể điều chỉnh (nếu đang bật hiển thị ảnh con)
    if (subPreviewUrl) {
      this.subOverlay = L.imageOverlay(subPreviewUrl, bounds, {
        opacity: this.currentOpacity,
        interactive: false
      });
      if (this.isOverlayVisible) {
        this.subOverlay.addTo(this.map);
      }
    }

    // 2. Vẽ khung chữ nhật Bounding Box với hiệu ứng Neon
    this.bboxLayer = L.rectangle(bounds, {
      color: '#06b6d4',
      weight: 3,
      fillColor: '#06b6d4',
      fillOpacity: 0.1,
      className: 'neon-bbox'
    });
    if (this.isBBoxVisible) {
      this.bboxLayer.addTo(this.map);
    }

    // Gắn tooltip hiển thị kích thước và tọa độ
    const labelContent = `
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #06b6d4;">🎯 Bounding Box Vùng:</strong><br>
        Pixel: ${box.width.toLocaleString()} x ${box.height.toLocaleString()} px<br>
        Tọa độ: (${box.xmin.toLocaleString()}, ${box.ymin.toLocaleString()})<br>
        Độ trùng khớp: ${matchData.overlap_pct}%
      </div>
    `;
    this.bboxLayer.bindTooltip(labelContent, {
      permanent: true,
      direction: 'top',
      className: 'bbox-label',
      offset: [0, -10]
    });
  }

  /**
   * Tự động nạp ảnh độ nét cao (100% full-resolution) cho vùng viewport hiện tại
   */
  async refreshHDViewport() {
    if (!this.bigInfo || !this.bigInfo.file_path) return;

    const zoom = this.map.getZoom();
    // Chỉ nạp HD khi người dùng phóng to (zoom >= -0.5)
    if (zoom < -0.5) {
      if (this.hdOverlay) {
        this.map.removeLayer(this.hdOverlay);
        this.hdOverlay = null;
      }
      return;
    }

    const bounds = this.map.getBounds();
    const colMin = Math.max(0, Math.floor(bounds.getWest()));
    const colMax = Math.min(this.bigInfo.width, Math.ceil(bounds.getEast()));
    const rowMin = Math.max(0, Math.floor(-bounds.getNorth()));
    const rowMax = Math.min(this.bigInfo.height, Math.ceil(-bounds.getSouth()));

    const winW = colMax - colMin;
    const winH = rowMax - rowMin;

    if (winW < 50 || winH < 50) return;
    // Nếu khung nhìn chiếm hầu như toàn bộ ảnh thì ảnh overview 4K đã đủ nét
    if (winW >= this.bigInfo.width * 0.95 && winH >= this.bigInfo.height * 0.95) return;

    try {
      const url = `/api/viewport-crop?file_path=${encodeURIComponent(this.bigInfo.file_path)}&col_off=${colMin}&row_off=${rowMin}&width=${winW}&height=${winH}&max_dim=2560`;
      
      // Tải trước ảnh để chuyển layer mượt mà không bị nhấp nháy
      const tempImg = new Image();
      tempImg.onload = () => {
        const patchBounds = [[-rowMax, colMin], [-rowMin, colMax]];
        if (this.hdOverlay) {
          this.map.removeLayer(this.hdOverlay);
        }
        this.hdOverlay = L.imageOverlay(url, patchBounds, { zIndex: 10, interactive: false }).addTo(this.map);
      };
      tempImg.src = url;
    } catch (e) {
      console.error('Lỗi nạp HD viewport:', e);
    }
  }

  toggleHD(enabled) {
    this.isHDEnabled = enabled;
    if (!enabled && this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    } else if (enabled) {
      this.refreshHDViewport();
    }
  }

  setOverlayOpacity(val) {
    this.currentOpacity = val / 100;
    if (this.subOverlay) {
      this.subOverlay.setOpacity(this.currentOpacity);
    }
  }

  /**
   * Bật hoặc Ẩn ảnh con (Chỉ giữ lại khung Bounding Box)
   */
  setSubOverlayVisible(visible) {
    this.isOverlayVisible = visible;
    if (this.subOverlay) {
      if (visible) {
        if (!this.map.hasLayer(this.subOverlay)) {
          this.map.addLayer(this.subOverlay);
        }
      } else {
        if (this.map.hasLayer(this.subOverlay)) {
          this.map.removeLayer(this.subOverlay);
        }
      }
    }
  }

  clearBoundingBox() {
    if (this.subOverlay) {
      this.map.removeLayer(this.subOverlay);
      this.subOverlay = null;
    }
    if (this.bboxLayer) {
      this.map.removeLayer(this.bboxLayer);
      this.bboxLayer = null;
    }
    this.matchData = null;
  }

  toggleBBox(visible) {
    this.isBBoxVisible = visible;
    if (this.bboxLayer) {
      if (visible) {
        this.map.addLayer(this.bboxLayer);
      } else {
        this.map.removeLayer(this.bboxLayer);
      }
    }
  }

  zoomFit() {
    if (this.bigInfo && this.bigOverlay) {
      const H = this.bigInfo.height;
      const W = this.bigInfo.width;
      this.map.fitBounds([[-H, 0], [0, W]]);
    }
  }

  zoomToRegion() {
    if (this.matchData && this.matchData.pixel_box) {
      const box = this.matchData.pixel_box;
      const bounds = [
        [-box.ymax, box.xmin],
        [-box.ymin, box.xmax]
      ];
      this.map.fitBounds(bounds, { padding: [40, 40] });
      // Kích hoạt ngay HD refinement cho vùng Bounding Box
      setTimeout(() => {
        this.refreshHDViewport();
      }, 400);
    }
  }

  handleMouseMove(e) {
    const col = Math.round(e.latlng.lng);
    const row = Math.round(-e.latlng.lat);

    const hudPixel = document.getElementById('hudPixel');
    const hudGeo = document.getElementById('hudGeo');

    if (this.bigInfo) {
      if (col >= 0 && col <= this.bigInfo.width && row >= 0 && row <= this.bigInfo.height) {
        hudPixel.innerText = `X: ${col.toLocaleString()}, Y: ${row.toLocaleString()}`;

        // Tính tọa độ địa lý nếu có transform
        if (this.bigInfo.transform && this.bigInfo.transform.length >= 6) {
          const t = this.bigInfo.transform;
          const geoX = t[2] + t[0] * col + t[1] * row;
          const geoY = t[5] + t[3] * col + t[4] * row;

          if (this.bigInfo.crs && this.bigInfo.crs.includes('4326')) {
            hudGeo.innerText = `Lat: ${geoY.toFixed(6)}°, Lon: ${geoX.toFixed(6)}°`;
          } else {
            hudGeo.innerText = `E: ${geoX.toFixed(2)}, N: ${geoY.toFixed(2)}`;
          }
        }
      } else {
        hudPixel.innerText = `X: --, Y: --`;
        hudGeo.innerText = `Ngoài phạm vi ảnh`;
      }
    }
  }
}

window.OrthoViewer = OrthoViewer;
