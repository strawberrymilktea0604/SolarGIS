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
    this.sub2Overlay = null;
    this.bboxLayer = null;
    this.bboxLayer2 = null;
    this.interBboxLayer = null;
    this.bigInfo = null;
    this.subInfo = null;
    this.sub2Info = null;
    this.matchData = null;
    this.dualMatchData = null;
    this.isBBoxVisible = true;
    this.isOverlayVisible = true;
    this.isHDEnabled = true;
    this.currentOpacity = 0.85;
    this.hdDebounceTimer = null;
    this.hdRequestId = 0;
    this.currentView = 'big'; // 'big' | 'sub' | 'sub2'
    this.subStandaloneOverlay = null;

    this.utmPointsLayer = null;
    this.plottedUTMMarkers = [];
    this.utmPolygonLine = null;
    this.onUTMPointMoved = null;

    this.initMap();
  }

  initMap() {
    this.map = L.map(this.containerId, {
      crs: L.CRS.Simple,
      preferCanvas: true,
      minZoom: -5,
      maxZoom: 6,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      attributionControl: false,
    });

    this.utmPointsLayer = L.layerGroup().addTo(this.map);

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
      if (this.isHDEnabled && this.getActiveInfo()) {
        clearTimeout(this.hdDebounceTimer);
        this.hdDebounceTimer = setTimeout(() => {
          this.refreshHDViewport();
        }, 200);
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
    this.currentView = 'big';

    this.map.fitBounds(bounds);
  }

  getActiveInfo() {
    if (this.currentView === 'sub2' && this.sub2Info) return this.sub2Info;
    if (this.currentView === 'sub' && this.subInfo) return this.subInfo;
    return this.bigInfo;
  }

  loadSubOrthoStandalone(subInfo, previewUrl) {
    this.subInfo = subInfo;

    const ph = document.getElementById('viewerPlaceholder');
    if (ph) ph.style.display = 'none';

    if (this.subStandaloneOverlay) {
      this.map.removeLayer(this.subStandaloneOverlay);
      this.subStandaloneOverlay = null;
    }
    if (this.bigOverlay) this.map.removeLayer(this.bigOverlay);
    this.clearBoundingBox();
    if (this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    }

    const H = subInfo.height;
    const W = subInfo.width;
    const bounds = [[-H, 0], [0, W]];
    this.subStandaloneOverlay = L.imageOverlay(previewUrl, bounds).addTo(this.map);
    this.currentView = 'sub';
    this.map.fitBounds(bounds);
  }

  loadSub2OrthoStandalone(sub2Info, previewUrl) {
    this.sub2Info = sub2Info;

    const ph = document.getElementById('viewerPlaceholder');
    if (ph) ph.style.display = 'none';

    if (this.subStandaloneOverlay) {
      this.map.removeLayer(this.subStandaloneOverlay);
      this.subStandaloneOverlay = null;
    }
    if (this.bigOverlay) this.map.removeLayer(this.bigOverlay);
    this.clearBoundingBox();
    if (this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    }

    const H = sub2Info.height;
    const W = sub2Info.width;
    const bounds = [[-H, 0], [0, W]];
    this.subStandaloneOverlay = L.imageOverlay(previewUrl, bounds).addTo(this.map);
    this.currentView = 'sub2';
    this.map.fitBounds(bounds);
  }

  switchToBigView() {
    if (!this.bigInfo) return;
    this.hdRequestId++;
    if (this.subStandaloneOverlay) {
      this.map.removeLayer(this.subStandaloneOverlay);
      this.subStandaloneOverlay = null;
    }
    if (this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    }
    if (this.bigOverlay && !this.map.hasLayer(this.bigOverlay)) {
      this.bigOverlay.addTo(this.map);
    }
    if (this.bboxLayer && this.isBBoxVisible && !this.map.hasLayer(this.bboxLayer)) {
      this.bboxLayer.addTo(this.map);
    }
    if (this.bboxLayer2 && this.isBBoxVisible && !this.map.hasLayer(this.bboxLayer2)) {
      this.bboxLayer2.addTo(this.map);
    }
    if (this.interBboxLayer && this.isBBoxVisible && !this.map.hasLayer(this.interBboxLayer)) {
      this.interBboxLayer.addTo(this.map);
    }
    if (this.subOverlay && this.isOverlayVisible && !this.map.hasLayer(this.subOverlay)) {
      this.subOverlay.addTo(this.map);
    }
    if (this.sub2Overlay && this.isOverlayVisible && !this.map.hasLayer(this.sub2Overlay)) {
      this.sub2Overlay.addTo(this.map);
    }
    this.currentView = 'big';
    const bounds = [[-this.bigInfo.height, 0], [0, this.bigInfo.width]];
    this.map.fitBounds(bounds);
  }

  switchToSubView() {
    if (!this.subInfo) return;
    this.hdRequestId++;
    if (this.bigOverlay) this.map.removeLayer(this.bigOverlay);
    if (this.bboxLayer) this.map.removeLayer(this.bboxLayer);
    if (this.bboxLayer2) this.map.removeLayer(this.bboxLayer2);
    if (this.interBboxLayer) this.map.removeLayer(this.interBboxLayer);
    if (this.subOverlay) this.map.removeLayer(this.subOverlay);
    if (this.sub2Overlay) this.map.removeLayer(this.sub2Overlay);
    if (this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    }

    const H = this.subInfo.height;
    const W = this.subInfo.width;
    const bounds = [[-H, 0], [0, W]];

    if (this.subStandaloneOverlay) {
      this.map.removeLayer(this.subStandaloneOverlay);
      this.subStandaloneOverlay = null;
    }
    const previewUrl = `/api/preview-image?filename=${this.subInfo.preview_filename}`;
    this.subStandaloneOverlay = L.imageOverlay(previewUrl, bounds).addTo(this.map);

    this.currentView = 'sub';
    this.map.fitBounds(bounds);
  }

  switchToSub2View() {
    if (!this.sub2Info) return;
    this.hdRequestId++;
    if (this.bigOverlay) this.map.removeLayer(this.bigOverlay);
    if (this.bboxLayer) this.map.removeLayer(this.bboxLayer);
    if (this.bboxLayer2) this.map.removeLayer(this.bboxLayer2);
    if (this.interBboxLayer) this.map.removeLayer(this.interBboxLayer);
    if (this.subOverlay) this.map.removeLayer(this.subOverlay);
    if (this.sub2Overlay) this.map.removeLayer(this.sub2Overlay);
    if (this.hdOverlay) {
      this.map.removeLayer(this.hdOverlay);
      this.hdOverlay = null;
    }

    const H = this.sub2Info.height;
    const W = this.sub2Info.width;
    const bounds = [[-H, 0], [0, W]];

    if (this.subStandaloneOverlay) {
      this.map.removeLayer(this.subStandaloneOverlay);
      this.subStandaloneOverlay = null;
    }
    const previewUrl = `/api/preview-image?filename=${this.sub2Info.preview_filename}`;
    this.subStandaloneOverlay = L.imageOverlay(previewUrl, bounds).addTo(this.map);

    this.currentView = 'sub2';
    this.map.fitBounds(bounds);
  }

  displayBoundingBox(matchData, subPreviewUrl) {
    this.matchData = matchData;
    this.dualMatchData = null;
    this.subInfo = matchData.sub_ortho;

    const box = matchData.pixel_box;
    const bounds = [
      [-box.ymax, box.xmin],
      [-box.ymin, box.xmax]
    ];

    // Xóa layer cũ
    this.clearBoundingBox();

    // 1. Lớp phủ ảnh vùng con với Opacity có thể điều chỉnh
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

    // Gắn tooltip hiển thị kích thước và tọa độ bằng tiếng Anh
    const labelContent = `
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #06b6d4;">🎯 Sub-Ortho Bounding Box:</strong><br>
        Pixels: ${box.width.toLocaleString()} x ${box.height.toLocaleString()} px<br>
        Origin: (${box.xmin.toLocaleString()}, ${box.ymin.toLocaleString()})<br>
        Overlap: ${matchData.overlap_pct}%
      </div>
    `;
    this.bboxLayer.bindTooltip(labelContent, {
      permanent: true,
      direction: 'top',
      className: 'bbox-label',
      offset: [0, -10]
    });
  }

  displayTwoSubsOnBig(dualData, sub1PreviewUrl, sub2PreviewUrl) {
    this.dualMatchData = dualData;
    this.matchData = null;
    this.subInfo = dualData.sub1_ortho;
    this.sub2Info = dualData.sub2_ortho;

    this.clearBoundingBox();

    const box1 = dualData.sub1_match.pixel_box;
    const bounds1 = [
      [-box1.ymax, box1.xmin],
      [-box1.ymin, box1.xmax]
    ];

    const box2 = dualData.sub2_match.pixel_box;
    const bounds2 = [
      [-box2.ymax, box2.xmin],
      [-box2.ymin, box2.xmax]
    ];

    // 1. Overlays
    if (sub1PreviewUrl) {
      this.subOverlay = L.imageOverlay(sub1PreviewUrl, bounds1, {
        opacity: this.currentOpacity,
        interactive: false
      });
      if (this.isOverlayVisible) this.subOverlay.addTo(this.map);
    }

    if (sub2PreviewUrl) {
      this.sub2Overlay = L.imageOverlay(sub2PreviewUrl, bounds2, {
        opacity: this.currentOpacity,
        interactive: false
      });
      if (this.isOverlayVisible) this.sub2Overlay.addTo(this.map);
    }

    // 2. Neon Bounding Box 1 (Cyan)
    this.bboxLayer = L.rectangle(bounds1, {
      color: '#06b6d4',
      weight: 3,
      fillColor: '#06b6d4',
      fillOpacity: 0.1,
      className: 'neon-bbox'
    });
    if (this.isBBoxVisible) this.bboxLayer.addTo(this.map);

    this.bboxLayer.bindTooltip(`
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #06b6d4;">🔵 Sub-Ortho 1:</strong><br>
        ${dualData.sub1_ortho.file_name}<br>
        Size: ${box1.width.toLocaleString()} x ${box1.height.toLocaleString()} px<br>
        Origin: (${box1.xmin.toLocaleString()}, ${box1.ymin.toLocaleString()})
      </div>
    `, { permanent: true, direction: 'top', className: 'bbox-label', offset: [0, -10] });

    // 3. Neon Bounding Box 2 (Amber)
    this.bboxLayer2 = L.rectangle(bounds2, {
      color: '#f59e0b',
      weight: 3,
      fillColor: '#f59e0b',
      fillOpacity: 0.1,
      className: 'neon-bbox-amber'
    });
    if (this.isBBoxVisible) this.bboxLayer2.addTo(this.map);

    this.bboxLayer2.bindTooltip(`
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #f59e0b;">🟠 Sub-Ortho 2:</strong><br>
        ${dualData.sub2_ortho.file_name}<br>
        Size: ${box2.width.toLocaleString()} x ${box2.height.toLocaleString()} px<br>
        Origin: (${box2.xmin.toLocaleString()}, ${box2.ymin.toLocaleString()})
      </div>
    `, { permanent: true, direction: 'bottom', className: 'bbox-label', offset: [0, 10] });

    // 4. Mutual Overlap Box (nếu có giao nhau)
    if (dualData.mutual_overlap && dualData.mutual_overlap.is_overlapping) {
      const ibox = dualData.mutual_overlap.pixel_box;
      const ibounds = [
        [-ibox.ymax, ibox.xmin],
        [-ibox.ymin, ibox.xmax]
      ];
      this.interBboxLayer = L.rectangle(ibounds, {
        color: '#10b981',
        weight: 2,
        dashArray: '5, 5',
        fillColor: '#10b981',
        fillOpacity: 0.25,
        className: 'neon-bbox-green'
      });
      if (this.isBBoxVisible) this.interBboxLayer.addTo(this.map);

      this.interBboxLayer.bindTooltip(`
        <div style="font-family: var(--font-mono); font-size: 11px;">
          <strong style="color: #10b981;">🟢 Mutual Overlap: ${dualData.mutual_overlap.iou_pct}%</strong><br>
          Size: ${ibox.width.toLocaleString()} x ${ibox.height.toLocaleString()} px
        </div>
      `, { permanent: false, direction: 'center', className: 'bbox-label' });
    }

    // Tự động fit để bao trọn cả 2 Bounding Box
    const combinedBounds = L.latLngBounds(bounds1).extend(bounds2);
    this.map.fitBounds(combinedBounds, { padding: [50, 50] });
  }

  displayTwoSubMatch(matchData, sub1PreviewUrl, sub2PreviewUrl) {
    this.matchData = matchData;
    this.dualMatchData = null;
    this.subInfo = matchData.sub1_ortho;
    this.sub2Info = matchData.sub2_ortho;

    // Hiển thị Sub 1 làm canvas nền
    this.loadSubOrthoStandalone(matchData.sub1_ortho, sub1PreviewUrl);

    // Nếu có vị trí của Sub 2 trên Sub 1
    if (matchData.sub2_on_sub1_pixel_box) {
      const box2 = matchData.sub2_on_sub1_pixel_box;
      const bounds2 = [
        [-box2.ymax, box2.xmin],
        [-box2.ymin, box2.xmax]
      ];

      if (sub2PreviewUrl) {
        this.sub2Overlay = L.imageOverlay(sub2PreviewUrl, bounds2, {
          opacity: this.currentOpacity,
          interactive: false
        });
        if (this.isOverlayVisible) this.sub2Overlay.addTo(this.map);
      }

      this.bboxLayer2 = L.rectangle(bounds2, {
        color: '#f59e0b',
        weight: 3,
        fillColor: '#f59e0b',
        fillOpacity: 0.15,
        className: 'neon-bbox-amber'
      });
      if (this.isBBoxVisible) this.bboxLayer2.addTo(this.map);

      this.bboxLayer2.bindTooltip(`
        <div style="font-family: var(--font-mono); font-size: 11px;">
          <strong style="color: #f59e0b;">🟠 Sub-Ortho 2 Alignment:</strong><br>
          Overlap: ${matchData.overlap_pct}%<br>
          Center Distance: ${matchData.center_distance_m ? matchData.center_distance_m + ' m' : 'N/A'}<br>
          Relative Box: (${box2.xmin}, ${box2.ymin}) ${box2.width}x${box2.height}px
        </div>
      `, { permanent: true, direction: 'top', className: 'bbox-label', offset: [0, -10] });

      const s1Bounds = [[-matchData.sub1_ortho.height, 0], [0, matchData.sub1_ortho.width]];
      const fullBounds = L.latLngBounds(s1Bounds).extend(bounds2);
      this.map.fitBounds(fullBounds, { padding: [40, 40] });
    }
  }

  /**
   * Tự động nạp ảnh độ nét cao (100% full-resolution) cho vùng viewport hiện tại
   */
  async refreshHDViewport() {
    const activeInfo = this.getActiveInfo();
    if (!activeInfo || !activeInfo.file_path || !this.isHDEnabled) return;

    const requestedView = this.currentView;
    const reqId = ++this.hdRequestId;

    // Nếu ảnh có kích thước nhỏ (<= 2048px), ảnh preview đã là 1:1, không cần crop HD đè lên
    if (activeInfo.width <= 2048 && activeInfo.height <= 2048) {
      if (this.hdOverlay) {
        this.map.removeLayer(this.hdOverlay);
        this.hdOverlay = null;
      }
      return;
    }

    const bounds = this.map.getBounds();
    const colMin = Math.max(0, Math.floor(bounds.getWest()));
    const colMax = Math.min(activeInfo.width, Math.ceil(bounds.getEast()));
    const rowMin = Math.max(0, Math.floor(-bounds.getNorth()));
    const rowMax = Math.min(activeInfo.height, Math.ceil(-bounds.getSouth()));

    const winW = colMax - colMin;
    const winH = rowMax - rowMin;

    if (winW < 30 || winH < 30) return;

    // Nếu khung nhìn chiếm gần như toàn bộ ảnh (đang zoom xa ngắm toàn cảnh)
    if (winW >= activeInfo.width * 0.95 && winH >= activeInfo.height * 0.95) {
      if (this.hdOverlay) {
        this.map.removeLayer(this.hdOverlay);
        this.hdOverlay = null;
      }
      return;
    }

    try {
      const url = `/api/viewport-crop?file_path=${encodeURIComponent(activeInfo.file_path)}&col_off=${colMin}&row_off=${rowMin}&width=${winW}&height=${winH}&max_dim=2560`;
      
      // Tải trước ảnh để chuyển layer mượt mà không bị nhấp nháy
      const tempImg = new Image();
      tempImg.onload = () => {
        // Đảm bảo không đè ảnh nếu người dùng đã chuyển view hoặc có request mới hơn
        if (this.currentView !== requestedView || this.hdRequestId !== reqId) return;

        const patchBounds = [[-rowMax, colMin], [-rowMin, colMax]];
        if (this.hdOverlay) {
          this.map.removeLayer(this.hdOverlay);
        }
        this.hdOverlay = L.imageOverlay(url, patchBounds, { 
          zIndex: 10, 
          interactive: false,
          className: 'hd-viewport-overlay'
        }).addTo(this.map);
        if (this.hdOverlay.bringToFront) {
          this.hdOverlay.bringToFront();
        }
      };
      tempImg.onerror = (e) => {
        console.warn('Lỗi tải HD viewport crop:', e);
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
    if (this.sub2Overlay) {
      this.sub2Overlay.setOpacity(this.currentOpacity);
    }
  }

  /**
   * Bật hoặc Ẩn ảnh con (Chỉ giữ lại khung Bounding Box)
   */
  setSubOverlayVisible(visible) {
    this.isOverlayVisible = visible;
    [this.subOverlay, this.sub2Overlay].forEach(overlay => {
      if (overlay) {
        if (visible) {
          if (!this.map.hasLayer(overlay)) this.map.addLayer(overlay);
        } else {
          if (this.map.hasLayer(overlay)) this.map.removeLayer(overlay);
        }
      }
    });
  }

  clearBoundingBox() {
    if (this.subOverlay) {
      this.map.removeLayer(this.subOverlay);
      this.subOverlay = null;
    }
    if (this.sub2Overlay) {
      this.map.removeLayer(this.sub2Overlay);
      this.sub2Overlay = null;
    }
    if (this.bboxLayer) {
      this.map.removeLayer(this.bboxLayer);
      this.bboxLayer = null;
    }
    if (this.bboxLayer2) {
      this.map.removeLayer(this.bboxLayer2);
      this.bboxLayer2 = null;
    }
    if (this.interBboxLayer) {
      this.map.removeLayer(this.interBboxLayer);
      this.interBboxLayer = null;
    }
    this.matchData = null;
    this.dualMatchData = null;
  }

  toggleBBox(visible) {
    this.isBBoxVisible = visible;
    [this.bboxLayer, this.bboxLayer2, this.interBboxLayer].forEach(layer => {
      if (layer) {
        if (visible) {
          if (!this.map.hasLayer(layer)) this.map.addLayer(layer);
        } else {
          if (this.map.hasLayer(layer)) this.map.removeLayer(layer);
        }
      }
    });
  }

  zoomFit() {
    const activeInfo = this.getActiveInfo();
    if (activeInfo) {
      const H = activeInfo.height;
      const W = activeInfo.width;
      this.map.fitBounds([[-H, 0], [0, W]]);
    }
  }

  zoomToRegion() {
    if (this.dualMatchData) {
      const box1 = this.dualMatchData.sub1_match.pixel_box;
      const box2 = this.dualMatchData.sub2_match.pixel_box;
      const bounds1 = [[-box1.ymax, box1.xmin], [-box1.ymin, box1.xmax]];
      const bounds2 = [[-box2.ymax, box2.xmin], [-box2.ymin, box2.xmax]];
      const combined = L.latLngBounds(bounds1).extend(bounds2);
      this.map.fitBounds(combined, { padding: [40, 40] });
      setTimeout(() => { this.refreshHDViewport(); }, 400);
    } else if (this.matchData && this.matchData.pixel_box) {
      const box = this.matchData.pixel_box;
      const bounds = [
        [-box.ymax, box.xmin],
        [-box.ymin, box.xmax]
      ];
      this.map.fitBounds(bounds, { padding: [40, 40] });
      setTimeout(() => {
        this.refreshHDViewport();
      }, 400);
    }
  }

  handleMouseMove(e) {
    const col = Math.round(e.latlng.lng);
    const row = Math.round(-e.latlng.lat);

    const hudPixel = document.getElementById('hudPixel');
    const hudUTM = document.getElementById('hudUTM');
    const hudGeo = document.getElementById('hudGeo');

    const activeInfo = this.getActiveInfo();

    if (activeInfo) {
      if (col >= 0 && col <= activeInfo.width && row >= 0 && row <= activeInfo.height) {
        const viewLabel = this.currentView === 'sub2' ? ' [Ortho Vùng 2]' : (this.currentView === 'sub' ? ' [Ortho Vùng 1]' : ' [Ortho To]');
        if (hudPixel) hudPixel.innerText = `X: ${col.toLocaleString()}, Y: ${row.toLocaleString()}${viewLabel}`;

        // Tính tọa độ đầy đủ (UTM 49N + GPS) thông qua CoordUtils
        if (typeof CoordUtils !== 'undefined' && activeInfo.transform && activeInfo.transform.length >= 6) {
          const coords = CoordUtils.pixelToCoords(col, row, activeInfo.transform, activeInfo.crs);
          if (hudUTM) {
            hudUTM.innerText = `E: ${coords.utm_32649.easting.toLocaleString()} m, N: ${coords.utm_32649.northing.toLocaleString()} m`;
          }
          if (hudGeo) {
            hudGeo.innerText = `${coords.gps.formatted || (coords.gps.lat.toFixed(6) + '°, ' + coords.gps.lon.toFixed(6) + '°')}`;
          }
        } else if (activeInfo.transform && activeInfo.transform.length >= 6) {
          const t = activeInfo.transform;
          const geoX = t[2] + t[0] * col + t[1] * row;
          const geoY = t[5] + t[3] * col + t[4] * row;
          if (hudGeo) hudGeo.innerText = `X: ${geoX.toFixed(2)}, Y: ${geoY.toFixed(2)}`;
        }
      } else {
        if (hudPixel) hudPixel.innerText = `X: --, Y: --`;
        if (hudUTM) hudUTM.innerText = `Ngoài ảnh`;
        if (hudGeo) hudGeo.innerText = `Ngoài phạm vi ảnh`;
      }
    }
  }

  /**
   * Đánh dấu các points đã được đọc trực tiếp từ ảnh GeoTIFF lên bản đồ
   * (Các tọa độ pixel Col, Row được đọc từ GeoTIFF rasterio index)
   * @param {Array<{ name: string, x: number, y: number, z?: number, pixel_u: number, pixel_v: number, in_bounds?: boolean }>} pointsList
   */
  plotAndReadUTMPoints(pointsList) {
    this.clearUTMPoints();
    if (!pointsList || pointsList.length === 0) return [];

    const activeInfo = this.getActiveInfo();
    const results = [];
    const latlngs = [];

    pointsList.forEach((pt, index) => {
      const col = pt.pixel_u !== undefined ? pt.pixel_u : pt.col;
      const row = pt.pixel_v !== undefined ? pt.pixel_v : pt.row;

      // Đánh dấu marker lên ảnh trực giao: lng = col, lat = -row
      const lat = -row;
      const lng = col;
      const latlng = L.latLng(lat, lng);
      latlngs.push(latlng);

      // Phân loại: Điểm góc hay Điểm tâm Centroid
      const isCentroid = pt.name && pt.name.toLowerCase().includes('centroid');
      const markerColor = isCentroid ? '#f59e0b' : '#06b6d4';
      const markerIconHtml = `
        <div class="utm-point-marker ${isCentroid ? 'centroid-marker' : ''}" style="--marker-color: ${markerColor}">
          <span class="utm-marker-pin">
            <i class="fa-solid ${isCentroid ? 'fa-star' : 'fa-location-dot'}"></i>
          </span>
          <span class="utm-marker-badge">${pt.name || `P${index + 1}`}</span>
        </div>
      `;

      const customIcon = L.divIcon({
        className: 'custom-utm-point-icon',
        html: markerIconHtml,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
        popupAnchor: [0, -18]
      });

      const marker = L.marker(latlng, {
        icon: customIcon,
        draggable: true,
        zIndexOffset: isCentroid ? 1000 : 500
      });

      // BƯỚC ĐỌC TRỰC TIẾP: Đọc pixel (u, v) từ chính vị trí marker cắm trên ảnh
      const readMarkerPixels = () => {
        const pos = marker.getLatLng();
        const u_exact = parseFloat(pos.lng.toFixed(2));
        const v_exact = parseFloat((-pos.lat).toFixed(2));
        const u_int = Math.round(pos.lng);
        const v_int = Math.round(-pos.lat);
        let inBounds = true;
        if (activeInfo) {
          inBounds = (u_int >= 0 && u_int <= activeInfo.width && v_int >= 0 && v_int <= activeInfo.height);
        }
        return { u_exact, v_exact, u_int, v_int, inBounds };
      };

      const pxData = readMarkerPixels();

      marker._pointData = {
        name: pt.name || `Point_${index + 1}`,
        x: pt.x,
        y: pt.y,
        z: pt.z !== undefined ? pt.z : 0.0,
        pixel_u: pxData.u_exact,
        pixel_v: pxData.v_exact,
        pixel_u_int: pxData.u_int,
        pixel_v_int: pxData.v_int,
        in_bounds: pxData.inBounds,
        index: index
      };

      const updatePopup = () => {
        const d = marker._pointData;
        marker.bindPopup(`
          <div class="utm-popup">
            <div class="utm-popup-title">
              <i class="fa-solid ${isCentroid ? 'fa-star text-amber' : 'fa-location-dot text-cyan'}"></i>
              <strong>${d.name}</strong>
            </div>
            <div class="utm-popup-body">
              <div class="popup-row highlight">
                <span>Tọa độ Pixel (u, v):</span>
                <strong>(${d.pixel_u}, ${d.pixel_v})</strong>
              </div>
              <div class="popup-row">
                <span>Pixel nguyên (Col, Row):</span>
                <span>(${d.pixel_u_int}, ${d.pixel_v_int})</span>
              </div>
              <div class="popup-row">
                <span>Tọa độ UTM X:</span>
                <span>${d.x ? d.x.toLocaleString() : '--'} m</span>
              </div>
              <div class="popup-row">
                <span>Tọa độ UTM Y:</span>
                <span>${d.y ? d.y.toLocaleString() : '--'} m</span>
              </div>
              <div class="popup-row">
                <span>Cao độ Z:</span>
                <span>${d.z !== undefined ? d.z : '--'} m</span>
              </div>
              <div class="popup-row">
                <span>Trạng thái:</span>
                <span class="${d.in_bounds ? 'text-success' : 'text-danger'}">${d.in_bounds ? 'Trong ảnh' : 'Ngoài ảnh'}</span>
              </div>
            </div>
          </div>
        `);
      };
      updatePopup();

      // Kéo thả marker: Đọc trực tiếp tọa độ mới từ vị trí marker
      marker.on('drag', () => {
        const curPx = readMarkerPixels();
        marker._pointData.pixel_u = curPx.u_exact;
        marker._pointData.pixel_v = curPx.v_exact;
        marker._pointData.pixel_u_int = curPx.u_int;
        marker._pointData.pixel_v_int = curPx.v_int;
        marker._pointData.in_bounds = curPx.inBounds;
        updatePopup();
        if (typeof this.onUTMPointMoved === 'function') {
          this.onUTMPointMoved(marker._pointData);
        }
      });

      marker.on('dragend', () => {
        if (typeof this.onUTMPointMoved === 'function') {
          this.onUTMPointMoved(marker._pointData, true);
        }
      });

      this.utmPointsLayer.addLayer(marker);
      this.plottedUTMMarkers.push(marker);
      results.push(marker._pointData);
    });

    // Vẽ đường bao quanh các góc nếu có các góc
    const cornerMarkers = this.plottedUTMMarkers.filter(m => !m._pointData.name.toLowerCase().includes('centroid'));
    if (cornerMarkers.length >= 3) {
      const cornerCoords = cornerMarkers.map(m => m.getLatLng());
      cornerCoords.push(cornerCoords[0]);
      this.utmPolygonLine = L.polyline(cornerCoords, {
        color: '#06b6d4',
        weight: 2,
        dashArray: '5, 5',
        opacity: 0.8
      }).addTo(this.utmPointsLayer);
    }

    // Tự động căn khung nhìn bao quát các điểm
    if (latlngs.length > 0) {
      const groupBounds = L.latLngBounds(latlngs);
      this.map.fitBounds(groupBounds, { padding: [60, 60], maxZoom: 4 });
    }

    return results;
  }

  clearUTMPoints() {
    if (this.utmPointsLayer) {
      this.utmPointsLayer.clearLayers();
    }
    this.plottedUTMMarkers = [];
    this.utmPolygonLine = null;
  }

  getPlottedPointsPixelData() {
    return this.plottedUTMMarkers.map(m => m._pointData);
  }

  focusUTMPoint(index) {
    const marker = this.plottedUTMMarkers[index];
    if (marker) {
      this.map.panTo(marker.getLatLng(), { animate: true });
      marker.openPopup();
    }
  }
}

window.OrthoViewer = OrthoViewer;
