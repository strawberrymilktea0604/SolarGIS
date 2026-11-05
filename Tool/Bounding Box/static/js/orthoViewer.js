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
    this.sub1Opacity = 0.85;
    this.sub2Opacity = 0.85;
    this.activeDualLayer = 'both'; // 'both' | 'sub1' | 'sub2' | 'overlap'
    this.onDualLayerSelected = null;
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

    // Tạo các map pane chuyên biệt để kiểm soát tuyệt đối thứ tự xếp chồng (layer stacking)
    // Giúp HD Viewport không bao giờ che mất ảnh con, và Vùng 1 / Vùng 2 luôn hiển thị đúng thứ tự
    this.map.createPane('bgPane'); // Nền Ortho To (zIndex 200)
    this.map.getPane('bgPane').style.zIndex = '200';

    this.map.createPane('hdPane'); // Lớp HD zoom crop (zIndex 250, luôn nằm DƯỚI ảnh con)
    this.map.getPane('hdPane').style.zIndex = '250';

    this.map.createPane('sub1Pane'); // Ảnh Ortho Vùng 1 (zIndex 310)
    this.map.getPane('sub1Pane').style.zIndex = '310';

    this.map.createPane('sub2Pane'); // Ảnh Ortho Vùng 2 (zIndex 320)
    this.map.getPane('sub2Pane').style.zIndex = '320';

    this.map.createPane('bboxPane'); // Khung viền Bounding Box (zIndex 400, luôn nổi trên cùng)
    this.map.getPane('bboxPane').style.zIndex = '400';

    this.canvasRenderer = L.canvas({ padding: 0.5 });
    this.map.createPane('boxesPane'); // Khung Box đa giác 4 góc (zIndex 460, luôn trên ảnh nền)
    this.map.getPane('boxesPane').style.zIndex = '460';
    this.boxesCanvasRenderer = L.canvas({ padding: 0.5, pane: 'boxesPane' });
    this.boxesLayer = L.layerGroup();
    this.isBoxesVisible = true;
    this.boxesTarget = null;
    this.utmPointsLayer = L.layerGroup().addTo(this.map);

    // Lớp hiển thị các điểm chấm tự do (Ortho To vs Ortho Vùng 1 vs Ortho Vùng 2)
    this.map.createPane('freePointsPane');
    this.map.getPane('freePointsPane').style.zIndex = '480';
    this.freePointsLayerBig = L.layerGroup().addTo(this.map);
    this.freePointsLayerSub = L.layerGroup();
    this.freePointsLayerSub2 = L.layerGroup();

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
    this.bigOverlay = L.imageOverlay(previewUrl, bounds, { pane: 'bgPane' }).addTo(this.map);
    this.currentView = 'big';
    this.updateFreePointsVisibility();

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
    this.updateFreePointsVisibility();
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
    this.updateFreePointsVisibility();
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
    if (this.utmPointsLayer && this.map.hasLayer(this.utmPointsLayer)) {
      this.map.removeLayer(this.utmPointsLayer);
    }
    if (this.mappedAffineLayer && this.isAffineVisible !== false && !this.map.hasLayer(this.mappedAffineLayer)) {
      this.mappedAffineLayer.addTo(this.map);
    }
    if (this.mappedHomoLayer && this.isHomoVisible !== false && !this.map.hasLayer(this.mappedHomoLayer)) {
      this.mappedHomoLayer.addTo(this.map);
    }
    if (this.mappedGpsLayer && this.isGpsVisible !== false && !this.map.hasLayer(this.mappedGpsLayer)) {
      this.mappedGpsLayer.addTo(this.map);
    }
    if (this.boxesLayer) {
      if (this.isBoxesVisible !== false && (this.boxesTarget === 'big' || !this.boxesTarget)) {
        if (!this.map.hasLayer(this.boxesLayer)) this.boxesLayer.addTo(this.map);
      } else if (this.boxesTarget && this.boxesTarget !== 'big') {
        if (this.map.hasLayer(this.boxesLayer)) this.map.removeLayer(this.boxesLayer);
      }
    }
    this.currentView = 'big';
    this.updateFreePointsVisibility();
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

    if (this.utmPointsLayer && !this.map.hasLayer(this.utmPointsLayer)) {
      this.utmPointsLayer.addTo(this.map);
    }
    if (this.mappedAffineLayer && this.map.hasLayer(this.mappedAffineLayer)) {
      this.map.removeLayer(this.mappedAffineLayer);
    }
    if (this.mappedHomoLayer && this.map.hasLayer(this.mappedHomoLayer)) {
      this.map.removeLayer(this.mappedHomoLayer);
    }
    if (this.mappedGpsLayer && this.map.hasLayer(this.mappedGpsLayer)) {
      this.map.removeLayer(this.mappedGpsLayer);
    }
    if (this.boxesLayer) {
      if (this.isBoxesVisible !== false && (this.boxesTarget === 'sub' || !this.boxesTarget)) {
        if (!this.map.hasLayer(this.boxesLayer)) this.boxesLayer.addTo(this.map);
      } else if (this.boxesTarget && this.boxesTarget !== 'sub') {
        if (this.map.hasLayer(this.boxesLayer)) this.map.removeLayer(this.boxesLayer);
      }
    }

    this.currentView = 'sub';
    this.updateFreePointsVisibility();
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

    if (this.utmPointsLayer && !this.map.hasLayer(this.utmPointsLayer)) {
      this.utmPointsLayer.addTo(this.map);
    }
    if (this.mappedAffineLayer && this.map.hasLayer(this.mappedAffineLayer)) {
      this.map.removeLayer(this.mappedAffineLayer);
    }
    if (this.mappedHomoLayer && this.map.hasLayer(this.mappedHomoLayer)) {
      this.map.removeLayer(this.mappedHomoLayer);
    }
    if (this.mappedGpsLayer && this.map.hasLayer(this.mappedGpsLayer)) {
      this.map.removeLayer(this.mappedGpsLayer);
    }
    if (this.boxesLayer) {
      if (this.isBoxesVisible !== false && (this.boxesTarget === 'sub2' || !this.boxesTarget)) {
        if (!this.map.hasLayer(this.boxesLayer)) this.boxesLayer.addTo(this.map);
      } else if (this.boxesTarget && this.boxesTarget !== 'sub2') {
        if (this.map.hasLayer(this.boxesLayer)) this.map.removeLayer(this.boxesLayer);
      }
    }

    this.currentView = 'sub2';
    this.updateFreePointsVisibility();
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
        pane: 'sub1Pane',
        opacity: this.currentOpacity,
        interactive: false
      });
      if (this.isOverlayVisible) {
        this.subOverlay.addTo(this.map);
      }
    }

    // 2. Vẽ khung chữ nhật Bounding Box với hiệu ứng Neon
    this.bboxLayer = L.rectangle(bounds, {
      pane: 'bboxPane',
      color: '#06b6d4',
      weight: 3,
      fillColor: '#06b6d4',
      fillOpacity: 0.1,
      className: 'neon-bbox'
    });
    if (this.isBBoxVisible) {
      this.bboxLayer.addTo(this.map);
    }

    // Gắn tooltip hiển thị kích thước và tọa độ (chỉ hiện khi rê chuột để không che ảnh)
    const labelContent = `
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #06b6d4;">🎯 Sub-Ortho Bounding Box:</strong><br>
        Pixels: ${box.width.toLocaleString()} x ${box.height.toLocaleString()} px<br>
        Origin: (${box.xmin.toLocaleString()}, ${box.ymin.toLocaleString()})<br>
        Overlap: ${matchData.overlap_pct}%
      </div>
    `;
    this.bboxLayer.bindTooltip(labelContent, {
      permanent: false,
      direction: 'top',
      className: 'bbox-label-hover',
      offset: [0, -10]
    });
  }

  displayTwoSubsOnBig(dualData, sub1PreviewUrl, sub2PreviewUrl) {
    this.dualMatchData = dualData;
    this.matchData = null;
    this.subInfo = dualData.sub1_ortho;
    this.sub2Info = dualData.sub2_ortho;
    this.activeDualLayer = 'both';
    this.sub1Opacity = this.currentOpacity;
    this.sub2Opacity = this.currentOpacity;

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

    // 1. Overlays (đưa vào sub1Pane và sub2Pane để luôn nổi trên nền HD viewport)
    if (sub1PreviewUrl) {
      this.subOverlay = L.imageOverlay(sub1PreviewUrl, bounds1, {
        pane: 'sub1Pane',
        opacity: this.sub1Opacity,
        interactive: false
      });
      if (this.isOverlayVisible) this.subOverlay.addTo(this.map);
    }

    if (sub2PreviewUrl) {
      this.sub2Overlay = L.imageOverlay(sub2PreviewUrl, bounds2, {
        pane: 'sub2Pane',
        opacity: this.sub2Opacity,
        interactive: false
      });
      if (this.isOverlayVisible) this.sub2Overlay.addTo(this.map);
    }

    // 2. Neon Bounding Box 1 (Cyan - đưa vào bboxPane)
    this.bboxLayer = L.rectangle(bounds1, {
      pane: 'bboxPane',
      color: '#06b6d4',
      weight: 3,
      fillColor: '#06b6d4',
      fillOpacity: 0.1,
      className: 'neon-bbox'
    });
    if (this.isBBoxVisible) this.bboxLayer.addTo(this.map);

    // Tooltip chỉ hiện khi hover
    this.bboxLayer.bindTooltip(`
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #06b6d4;">🔵 Sub-Ortho 1:</strong> ${dualData.sub1_ortho.file_name}<br>
        Size: ${box1.width.toLocaleString()} x ${box1.height.toLocaleString()} px
      </div>
    `, { permanent: false, direction: 'top', className: 'bbox-label-hover', offset: [0, -10] });

    this.bboxLayer.on('click', (e) => {
      L.DomEvent.stopPropagation(e);
      if (this.onDualLayerSelected) this.onDualLayerSelected('sub1');
      else this.setActiveDualLayer('sub1');
    });

    // 3. Neon Bounding Box 2 (Amber - đưa vào bboxPane)
    this.bboxLayer2 = L.rectangle(bounds2, {
      pane: 'bboxPane',
      color: '#f59e0b',
      weight: 3,
      fillColor: '#f59e0b',
      fillOpacity: 0.1,
      className: 'neon-bbox-amber'
    });
    if (this.isBBoxVisible) this.bboxLayer2.addTo(this.map);

    this.bboxLayer2.bindTooltip(`
      <div style="font-family: var(--font-mono); font-size: 11px;">
        <strong style="color: #f59e0b;">🟠 Sub-Ortho 2:</strong> ${dualData.sub2_ortho.file_name}<br>
        Size: ${box2.width.toLocaleString()} x ${box2.height.toLocaleString()} px
      </div>
    `, { permanent: false, direction: 'bottom', className: 'bbox-label-hover', offset: [0, 10] });

    this.bboxLayer2.on('click', (e) => {
      L.DomEvent.stopPropagation(e);
      if (this.onDualLayerSelected) this.onDualLayerSelected('sub2');
      else this.setActiveDualLayer('sub2');
    });

    // 4. Mutual Overlap Box (nếu có giao nhau - đưa vào bboxPane)
    if (dualData.mutual_overlap && dualData.mutual_overlap.is_overlapping) {
      const ibox = dualData.mutual_overlap.pixel_box;
      const ibounds = [
        [-ibox.ymax, ibox.xmin],
        [-ibox.ymin, ibox.xmax]
      ];
      this.interBboxLayer = L.rectangle(ibounds, {
        pane: 'bboxPane',
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
          <strong style="color: #10b981;">🟢 Vùng Giao Nhau (Overlap): ${dualData.mutual_overlap.iou_pct}%</strong><br>
          Size: ${ibox.width.toLocaleString()} x ${ibox.height.toLocaleString()} px
        </div>
      `, { permanent: false, direction: 'center', className: 'bbox-label-hover' });

      this.interBboxLayer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        if (this.onDualLayerSelected) this.onDualLayerSelected('overlap');
        else this.setActiveDualLayer('overlap');
      });
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
      `, { permanent: false, direction: 'top', className: 'bbox-label-hover', offset: [0, -10] });

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
        // Gắn vào hdPane (zIndex 250) để luôn nằm DƯỚI ảnh con (zIndex 310, 320, 350)
        this.hdOverlay = L.imageOverlay(url, patchBounds, { 
          pane: 'hdPane', 
          interactive: false,
          className: 'hd-viewport-overlay'
        }).addTo(this.map);
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
    const opacity = val / 100;
    this.currentOpacity = opacity;

    if (this.dualMatchData) {
      if (this.activeDualLayer === 'sub1') {
        this.setSub1Opacity(val);
      } else if (this.activeDualLayer === 'sub2') {
        this.setSub2Opacity(val);
      } else {
        this.setSub1Opacity(val);
        this.setSub2Opacity(val);
      }
    } else {
      if (this.subOverlay) {
        this.subOverlay.setOpacity(opacity);
      }
      if (this.sub2Overlay) {
        this.sub2Overlay.setOpacity(opacity);
      }
    }
  }

  setSub1Opacity(val) {
    this.sub1Opacity = val / 100;
    if (this.subOverlay) {
      if (this.sub1Opacity > 0 && this.isOverlayVisible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'sub1')) {
        if (!this.map.hasLayer(this.subOverlay)) this.map.addLayer(this.subOverlay);
      }
      this.subOverlay.setOpacity(this.sub1Opacity);
    }
    if (this.bboxLayer) {
      this.bboxLayer.setStyle({
        opacity: this.sub1Opacity,
        fillOpacity: this.sub1Opacity * 0.18
      });
    }
  }

  setSub2Opacity(val) {
    this.sub2Opacity = val / 100;
    if (this.sub2Overlay) {
      if (this.sub2Opacity > 0 && this.isOverlayVisible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'sub2')) {
        if (!this.map.hasLayer(this.sub2Overlay)) this.map.addLayer(this.sub2Overlay);
      }
      this.sub2Overlay.setOpacity(this.sub2Opacity);
    }
    if (this.bboxLayer2) {
      this.bboxLayer2.setStyle({
        opacity: this.sub2Opacity,
        fillOpacity: this.sub2Opacity * 0.18
      });
    }
  }

  /**
   * Chọn hiển thị Layer khi mapping 2 vùng lên Ortho To:
   * 'both' | 'sub1' | 'sub2' | 'overlap'
   * Tự động đẩy z-index của pane tương ứng lên 350 để ưu tiên tuyệt đối lên trên cùng
   */
  setActiveDualLayer(layerName) {
    this.activeDualLayer = layerName;

    if (!this.dualMatchData) return;

    const sub1Pane = this.map.getPane('sub1Pane');
    const sub2Pane = this.map.getPane('sub2Pane');

    if (layerName === 'both') {
      // Đặt lại thứ tự z-index mặc định cho 2 pane
      if (sub1Pane) sub1Pane.style.zIndex = '310';
      if (sub2Pane) sub2Pane.style.zIndex = '320';

      // Khôi phục độ mờ nếu một trong 2 vùng đang bị tắt về 0 hoặc đang ở 100% (solo mode)
      if (this.sub1Opacity <= 0.05 || this.sub1Opacity >= 0.99) this.sub1Opacity = 0.85;
      if (this.sub2Opacity <= 0.05 || this.sub2Opacity >= 0.99) this.sub2Opacity = 0.85;

      // Hiển thị cả 2
      if (this.subOverlay) {
        if (this.isOverlayVisible && !this.map.hasLayer(this.subOverlay)) this.map.addLayer(this.subOverlay);
        this.subOverlay.setOpacity(this.sub1Opacity);
      }
      if (this.sub2Overlay) {
        if (this.isOverlayVisible && !this.map.hasLayer(this.sub2Overlay)) this.map.addLayer(this.sub2Overlay);
        this.sub2Overlay.setOpacity(this.sub2Opacity);
      }
      if (this.bboxLayer) {
        if (this.isBBoxVisible && !this.map.hasLayer(this.bboxLayer)) this.map.addLayer(this.bboxLayer);
        this.bboxLayer.setStyle({ color: '#06b6d4', opacity: 1, fillOpacity: 0.1, weight: 3 });
      }
      if (this.bboxLayer2) {
        if (this.isBBoxVisible && !this.map.hasLayer(this.bboxLayer2)) this.map.addLayer(this.bboxLayer2);
        this.bboxLayer2.setStyle({ color: '#f59e0b', opacity: 1, fillOpacity: 0.1, weight: 3 });
      }
      if (this.interBboxLayer) {
        if (this.isBBoxVisible && !this.map.hasLayer(this.interBboxLayer)) this.map.addLayer(this.interBboxLayer);
        this.interBboxLayer.setStyle({ color: '#10b981', opacity: 1, fillOpacity: 0.25, weight: 2 });
      }
    } else if (layerName === 'sub1') {
      // ƯU TIÊN HIỆN HẲN VÙNG 1 (Solo Layer 1)
      if (sub1Pane) sub1Pane.style.zIndex = '350';
      if (sub2Pane) sub2Pane.style.zIndex = '310';

      this.sub1Opacity = 1.0; // Ưu tiên hiện hẳn lên rõ nhất
      this.sub2Opacity = 0.0;

      if (this.subOverlay) {
        if (this.isOverlayVisible && !this.map.hasLayer(this.subOverlay)) this.map.addLayer(this.subOverlay);
        this.subOverlay.setOpacity(this.sub1Opacity);
      }
      // Xóa triệt để các vùng còn lại
      if (this.sub2Overlay) {
        this.map.removeLayer(this.sub2Overlay);
      }
      if (this.bboxLayer) {
        if (this.isBBoxVisible && !this.map.hasLayer(this.bboxLayer)) this.map.addLayer(this.bboxLayer);
        this.bboxLayer.setStyle({ color: '#06b6d4', opacity: 1, fillOpacity: 0.18, weight: 4 });
      }
      if (this.bboxLayer2) {
        this.map.removeLayer(this.bboxLayer2);
      }
      if (this.interBboxLayer) {
        this.map.removeLayer(this.interBboxLayer);
      }
    } else if (layerName === 'sub2') {
      // ƯU TIÊN HIỆN HẲN VÙNG 2 (Solo Layer 2)
      if (sub2Pane) sub2Pane.style.zIndex = '350';
      if (sub1Pane) sub1Pane.style.zIndex = '310';

      this.sub2Opacity = 1.0; // Ưu tiên hiện hẳn lên rõ nhất
      this.sub1Opacity = 0.0;

      if (this.sub2Overlay) {
        if (this.isOverlayVisible && !this.map.hasLayer(this.sub2Overlay)) this.map.addLayer(this.sub2Overlay);
        this.sub2Overlay.setOpacity(this.sub2Opacity);
      }
      // Xóa triệt để các vùng còn lại
      if (this.subOverlay) {
        this.map.removeLayer(this.subOverlay);
      }
      if (this.bboxLayer2) {
        if (this.isBBoxVisible && !this.map.hasLayer(this.bboxLayer2)) this.map.addLayer(this.bboxLayer2);
        this.bboxLayer2.setStyle({ color: '#f59e0b', opacity: 1, fillOpacity: 0.18, weight: 4 });
      }
      
      if (this.bboxLayer && this.map.hasLayer(this.bboxLayer)) {
        this.map.removeLayer(this.bboxLayer);
      }
      if (this.interBboxLayer && this.map.hasLayer(this.interBboxLayer)) {
        this.map.removeLayer(this.interBboxLayer);
      }
    } else if (layerName === 'overlap') {
      if (sub1Pane) sub1Pane.style.zIndex = '310';
      if (sub2Pane) sub2Pane.style.zIndex = '320';

      // Tập trung vào Vùng Giao Nhau, xóa triệt để các vùng còn lại
      if (this.subOverlay) this.map.removeLayer(this.subOverlay);
      if (this.sub2Overlay) this.map.removeLayer(this.sub2Overlay);
      if (this.bboxLayer) this.map.removeLayer(this.bboxLayer);
      if (this.bboxLayer2) this.map.removeLayer(this.bboxLayer2);
      
      if (this.overlapOpacity === undefined) this.overlapOpacity = 0.35;

      if (this.interBboxLayer) {
        if (!this.map.hasLayer(this.interBboxLayer)) this.map.addLayer(this.interBboxLayer);
        this.interBboxLayer.setStyle({ color: '#10b981', opacity: 1, fillOpacity: this.overlapOpacity, weight: 3 });
        this.zoomToOverlap();
      }
    }
  }

  setOverlapOpacity(val) {
    this.overlapOpacity = val / 100;
    if (this.interBboxLayer && this.map.hasLayer(this.interBboxLayer)) {
      this.interBboxLayer.setStyle({
        opacity: this.overlapOpacity > 0 ? 1 : 0,
        fillOpacity: this.overlapOpacity
      });
    }
  }

  zoomToSub1() {
    if (this.dualMatchData && this.dualMatchData.sub1_match) {
      const box1 = this.dualMatchData.sub1_match.pixel_box;
      const bounds1 = [[-box1.ymax, box1.xmin], [-box1.ymin, box1.xmax]];
      this.map.fitBounds(bounds1, { padding: [40, 40] });
      setTimeout(() => { this.refreshHDViewport(); }, 400);
    }
  }

  zoomToSub2() {
    if (this.dualMatchData && this.dualMatchData.sub2_match) {
      const box2 = this.dualMatchData.sub2_match.pixel_box;
      const bounds2 = [[-box2.ymax, box2.xmin], [-box2.ymin, box2.xmax]];
      this.map.fitBounds(bounds2, { padding: [40, 40] });
      setTimeout(() => { this.refreshHDViewport(); }, 400);
    }
  }

  zoomToOverlap() {
    if (this.dualMatchData && this.dualMatchData.mutual_overlap && this.dualMatchData.mutual_overlap.pixel_box) {
      const ibox = this.dualMatchData.mutual_overlap.pixel_box;
      const ibounds = [[-ibox.ymax, ibox.xmin], [-ibox.ymin, ibox.xmax]];
      this.map.fitBounds(ibounds, { padding: [40, 40] });
      setTimeout(() => { this.refreshHDViewport(); }, 400);
    }
  }

  /**
   * Bật hoặc Ẩn ảnh con (Chỉ giữ lại khung Bounding Box)
   */
  setSubOverlayVisible(visible) {
    this.isOverlayVisible = visible;
    
    if (this.subOverlay) {
      if (visible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'sub1')) {
        if (!this.map.hasLayer(this.subOverlay)) this.map.addLayer(this.subOverlay);
      } else {
        if (this.map.hasLayer(this.subOverlay)) this.map.removeLayer(this.subOverlay);
      }
    }

    if (this.sub2Overlay) {
      if (visible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'sub2')) {
        if (!this.map.hasLayer(this.sub2Overlay)) this.map.addLayer(this.sub2Overlay);
      } else {
        if (this.map.hasLayer(this.sub2Overlay)) this.map.removeLayer(this.sub2Overlay);
      }
    }
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
    if (this.dualMatchData) {
      if (this.bboxLayer) {
        if (visible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'sub1')) {
          if (!this.map.hasLayer(this.bboxLayer)) this.map.addLayer(this.bboxLayer);
        } else {
          if (this.map.hasLayer(this.bboxLayer)) this.map.removeLayer(this.bboxLayer);
        }
      }
      if (this.bboxLayer2) {
        if (visible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'sub2')) {
          if (!this.map.hasLayer(this.bboxLayer2)) this.map.addLayer(this.bboxLayer2);
        } else {
          if (this.map.hasLayer(this.bboxLayer2)) this.map.removeLayer(this.bboxLayer2);
        }
      }
      if (this.interBboxLayer) {
        if (visible && (this.activeDualLayer === 'both' || this.activeDualLayer === 'overlap')) {
          if (!this.map.hasLayer(this.interBboxLayer)) this.map.addLayer(this.interBboxLayer);
        } else {
          if (this.map.hasLayer(this.interBboxLayer)) this.map.removeLayer(this.interBboxLayer);
        }
      }
    } else {
      if (this.bboxLayer) {
        if (visible) {
          if (!this.map.hasLayer(this.bboxLayer)) this.map.addLayer(this.bboxLayer);
        } else {
          if (this.map.hasLayer(this.bboxLayer)) this.map.removeLayer(this.bboxLayer);
        }
      }
    }
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
    const isLargeDataset = pointsList.length > 150;

    pointsList.forEach((pt, index) => {
      const col = pt.pixel_u !== undefined ? pt.pixel_u : pt.col;
      const row = pt.pixel_v !== undefined ? pt.pixel_v : pt.row;

      const lat = -row;
      const lng = col;
      const latlng = L.latLng(lat, lng);
      latlngs.push(latlng);

      const isCentroid = (pt.name && pt.name.toLowerCase().includes('centroid')) || pt.role === 'centroid' || !pt.role;
      const inBounds = pt.in_bounds !== undefined ? pt.in_bounds : (activeInfo ? (col >= 0 && col <= activeInfo.width && row >= 0 && row <= activeInfo.height) : true);
      const markerColor = isCentroid ? '#f59e0b' : '#06b6d4';

      if (isLargeDataset) {
        // Chế độ tối ưu hóa hiệu năng cao cho Canonical PV (1,780 - 32,000 điểm)
        const marker = L.circleMarker(latlng, {
          radius: isCentroid ? 5 : 3.5,
          color: inBounds ? '#ffffff' : '#ef4444',
          fillColor: inBounds ? markerColor : '#64748b',
          fillOpacity: inBounds ? 0.9 : 0.45,
          weight: 1.5,
          renderer: this.canvasRenderer
        });

        marker._pointData = {
          name: pt.name || pt.internal_code || `Point_${index + 1}`,
          internal_code: pt.internal_code || pt.name,
          x: pt.x,
          y: pt.y,
          utm_x: pt.utm_x !== undefined ? pt.utm_x : pt.x,
          utm_y: pt.utm_y !== undefined ? pt.utm_y : pt.y,
          lon: pt.lon,
          lat: pt.lat,
          z: pt.z !== undefined ? pt.z : 0.0,
          pixel_u: col,
          pixel_v: row,
          pixel_u_int: col,
          pixel_v_int: row,
          in_bounds: inBounds,
          class: pt.class || 'Unclassified',
          role: pt.role || 'point',
          index: index
        };

        marker.bindTooltip(`
          <div style="font-size: 11px; padding: 2px 4px;">
            <strong style="color: ${markerColor}">${marker._pointData.name}</strong><br/>
            <span>Pixel: (${col}, ${row})</span><br/>
            <span>UTM: (${marker._pointData.utm_x || '--'}, ${marker._pointData.utm_y || '--'})</span><br/>
            <span style="color: ${inBounds ? '#10b981' : '#ef4444'}">${inBounds ? 'Trong ảnh' : 'Ngoài ảnh'}</span>
          </div>
        `, { direction: 'top', className: 'utm-point-tooltip', sticky: false });

        marker.on('click', () => {
          if (typeof this.onUTMPointSelected === 'function') {
            this.onUTMPointSelected(marker._pointData);
          }
        });

        this.utmPointsLayer.addLayer(marker);
        this.plottedUTMMarkers.push(marker);
        results.push(marker._pointData);
      } else {
        // Chế độ DOM Marker tương tác kéo thả (< 150 điểm)
        let markerIconHtml = '';
        if (isCentroid) {
          markerIconHtml = `
            <div class="utm-point-marker centroid-marker" style="--marker-color: ${markerColor}; display: flex; flex-direction: column; align-items: center; justify-content: center; transform: translateY(12px);">
              <div style="width: 18px; height: 18px; background-color: ${markerColor}; border: 2px solid white; border-radius: 50%; box-shadow: 0 0 6px rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; color: white; font-size: 10px;">
                <i class="fa-solid fa-star"></i>
              </div>
              <span class="utm-marker-badge" style="margin-top: 6px;">${pt.name || `P${index + 1}`}</span>
            </div>
          `;
        } else {
          markerIconHtml = `
            <div class="utm-point-marker" style="--marker-color: ${markerColor}; display: flex; flex-direction: column; align-items: center; justify-content: center; transform: translateY(12px);">
              <div style="width: 14px; height: 14px; background-color: ${markerColor}; border: 2px solid white; border-radius: 50%; box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>
              <span class="utm-marker-badge" style="margin-top: 6px;">${pt.name || `P${index + 1}`}</span>
            </div>
          `;
        }

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
          internal_code: pt.internal_code || pt.name,
          x: pt.x,
          y: pt.y,
          utm_x: pt.utm_x !== undefined ? pt.utm_x : pt.x,
          utm_y: pt.utm_y !== undefined ? pt.utm_y : pt.y,
          lon: pt.lon,
          lat: pt.lat,
          z: pt.z !== undefined ? pt.z : 0.0,
          pixel_u: pxData.u_exact,
          pixel_v: pxData.v_exact,
          pixel_u_int: pxData.u_int,
          pixel_v_int: pxData.v_int,
          in_bounds: pxData.inBounds,
          class: pt.class || 'Unclassified',
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
                  <span>${d.utm_x ? d.utm_x.toLocaleString() : (d.x ? d.x.toLocaleString() : '--')} m</span>
                </div>
                <div class="popup-row">
                  <span>Tọa độ UTM Y:</span>
                  <span>${d.utm_y ? d.utm_y.toLocaleString() : (d.y ? d.y.toLocaleString() : '--')} m</span>
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
      }
    });

    // Tự động căn khung nhìn bao quát các điểm (lọc các điểm inBounds trước nếu có)
    const inBoundsLatLngs = results.filter(r => r.in_bounds).map(r => L.latLng(-r.pixel_v, r.pixel_u));
    const targetBounds = inBoundsLatLngs.length > 0 ? inBoundsLatLngs : latlngs;
    if (targetBounds.length > 0) {
      const groupBounds = L.latLngBounds(targetBounds);
      this.map.fitBounds(groupBounds, { padding: [60, 60], maxZoom: 4 });
    }

    return results;
  }

  clearUTMPoints() {
    if (this.utmPointsLayer) {
      this.utmPointsLayer.clearLayers();
    }
    this.plottedUTMMarkers = [];
  }

  getPlottedPointsPixelData() {
    return this.plottedUTMMarkers.map(m => m._pointData);
  }

  focusUTMPoint(index) {
    const marker = this.plottedUTMMarkers[index];
    if (marker) {
      this.map.panTo(marker.getLatLng(), { animate: true });
      if (typeof marker.openPopup === 'function') {
        marker.openPopup();
      } else if (typeof marker.openTooltip === 'function') {
        marker.openTooltip();
      }
    }
  }

  plotMappedPoints(affinePts, homoPts) {
    if (!this.mappedAffineLayer) {
      this.mappedAffineLayer = L.layerGroup();
      this.isAffineVisible = true;
    }
    if (!this.mappedHomoLayer) {
      this.mappedHomoLayer = L.layerGroup();
      this.isHomoVisible = true;
    }
    this.mappedAffineLayer.clearLayers();
    this.mappedHomoLayer.clearLayers();

    if (this.currentView === 'big') {
      if (this.isAffineVisible && !this.map.hasLayer(this.mappedAffineLayer)) this.mappedAffineLayer.addTo(this.map);
      if (this.isHomoVisible && !this.map.hasLayer(this.mappedHomoLayer)) this.mappedHomoLayer.addTo(this.map);
    }

    // Plot Affine points (Red Triangles)
    if (affinePts && affinePts.length > 0) {
      affinePts.forEach(pt => {
        const latlng = L.latLng(-pt.y, pt.x);
        const iconHtml = `
          <div style="color: #ef4444; text-shadow: 0 0 3px #000; font-size: 16px; text-align: center;">
            <i class="fa-solid fa-play fa-rotate-270"></i>
            <div style="font-size: 10px; background: rgba(0,0,0,0.6); color: white; border-radius: 3px; padding: 1px 3px; margin-top: 2px;">${pt.name} (A)</div>
          </div>
        `;
        const icon = L.divIcon({ html: iconHtml, className: '', iconSize: [40, 40], iconAnchor: [20, 20] });
        L.marker(latlng, { icon }).addTo(this.mappedAffineLayer)
          .bindTooltip(`<b>${pt.name} (Affine)</b><br>X: ${pt.x}<br>Y: ${pt.y}`);
      });
    }

    // Plot Homography points (Blue Squares)
    if (homoPts && homoPts.length > 0) {
      homoPts.forEach(pt => {
        const latlng = L.latLng(-pt.y, pt.x);
        const iconHtml = `
          <div style="color: #3b82f6; text-shadow: 0 0 3px #000; font-size: 16px; text-align: center;">
            <i class="fa-solid fa-square"></i>
            <div style="font-size: 10px; background: rgba(0,0,0,0.6); color: white; border-radius: 3px; padding: 1px 3px; margin-top: 2px;">${pt.name} (H)</div>
          </div>
        `;
        const icon = L.divIcon({ html: iconHtml, className: '', iconSize: [40, 40], iconAnchor: [20, 20] });
        L.marker(latlng, { icon }).addTo(this.mappedHomoLayer)
          .bindTooltip(`<b>${pt.name} (Homography)</b><br>X: ${pt.x}<br>Y: ${pt.y}`);
      });
    }
  }

  toggleAffineLayer(visible) {
    this.isAffineVisible = visible;
    if (this.currentView !== 'big' || !this.mappedAffineLayer) return;
    if (visible && !this.map.hasLayer(this.mappedAffineLayer)) {
      this.mappedAffineLayer.addTo(this.map);
    } else if (!visible && this.map.hasLayer(this.mappedAffineLayer)) {
      this.map.removeLayer(this.mappedAffineLayer);
    }
  }

  toggleHomoLayer(visible) {
    this.isHomoVisible = visible;
    if (this.currentView !== 'big' || !this.mappedHomoLayer) return;
    if (visible && !this.map.hasLayer(this.mappedHomoLayer)) {
      this.mappedHomoLayer.addTo(this.map);
    } else if (!visible && this.map.hasLayer(this.mappedHomoLayer)) {
      this.map.removeLayer(this.mappedHomoLayer);
    }
  }

  setGpsMappedPoints(points) {
    if (!this.mappedGpsLayer) {
      this.mappedGpsLayer = L.layerGroup();
      this.isGpsVisible = true;
    }
    this.mappedGpsLayer.clearLayers();

    if (this.currentView === 'big' && this.isGpsVisible !== false) {
      if (!this.map.hasLayer(this.mappedGpsLayer)) this.mappedGpsLayer.addTo(this.map);
    }

    if (points && points.length > 0) {
      points.forEach(pt => {
        const latlng = L.latLng(-pt.big_y, pt.big_x);
        const iconHtml = `
          <div style="color: #10b981; text-shadow: 0 0 3px #000; font-size: 16px; text-align: center;">
            <i class="fa-solid fa-crosshairs"></i>
            <div style="font-size: 10px; background: rgba(0,0,0,0.75); color: #10b981; border: 1px solid #10b981; border-radius: 3px; padding: 1px 4px; margin-top: 2px; white-space: nowrap; font-weight: bold;">${pt.name}</div>
          </div>
        `;
        const icon = L.divIcon({ html: iconHtml, className: '', iconSize: [60, 40], iconAnchor: [30, 20] });
        L.marker(latlng, { icon }).addTo(this.mappedGpsLayer)
          .bindTooltip(`<b>${pt.name} (GPS Thuần)</b><br>Big: (${pt.big_x}, ${pt.big_y})<br>Sub: (${pt.sub_u}, ${pt.sub_v})<br>UTM: ${pt.utm_x}, ${pt.utm_y}`);
      });
    }
  }

  toggleGpsLayer(visible) {
    this.isGpsVisible = visible;
    if (this.currentView !== 'big' || !this.mappedGpsLayer) return;
    if (visible && !this.map.hasLayer(this.mappedGpsLayer)) {
      this.mappedGpsLayer.addTo(this.map);
    } else if (!visible && this.map.hasLayer(this.mappedGpsLayer)) {
      this.map.removeLayer(this.mappedGpsLayer);
    }
  }

  // --- Khung Box (Đa giác 4 góc cho từng Panel nạp Canonical JSON) ---
  plotCanonicalBoxes(boxes, target = null) {
    this.boxesTarget = target || this.currentView;
    this.canonicalBoxes = boxes || [];
    if (!this.boxesLayer) {
      this.boxesLayer = L.layerGroup();
      this.isBoxesVisible = true;
    }
    this.boxesLayer.clearLayers();
    this._activeBoxPoly = null;

    if (this.isBoxesVisible !== false) {
      if (!this.map.hasLayer(this.boxesLayer)) this.boxesLayer.addTo(this.map);
    }

    if (!boxes || boxes.length === 0) return;

    boxes.forEach((b, idx) => {
      const latlngs = b.corners.map(c => [-c.pixel.y, c.pixel.x]);
      
      let strokeColor = '#a855f7'; // Mặc định màu tím
      let fillColor = '#c084fc';
      let fillOp = 0.22;

      if (b.color_rgba && Array.isArray(b.color_rgba) && b.color_rgba.length >= 3) {
        const [r, g, b_val] = b.color_rgba;
        strokeColor = `rgb(${r}, ${g}, ${b_val})`;
        fillColor = `rgb(${r}, ${g}, ${b_val})`;
        // Giữ fillOpacity cố định để dễ nhìn xuyên thấu, hoặc dùng b.color_rgba[3] nếu muốn
        fillOp = 0.35; 
      }

      const poly = L.polygon(latlngs, {
        color: strokeColor,
        weight: 2,
        fillColor: fillColor,
        fillOpacity: fillOp,
        className: 'pv-box-frame',
        pane: 'boxesPane',
        renderer: this.boxesCanvasRenderer
      }).addTo(this.boxesLayer);

      b._polygon = poly;
      b.index = idx;
      
      poly._originalStyle = {
        color: strokeColor,
        weight: 2,
        fillColor: fillColor,
        fillOpacity: fillOp
      };

      poly.bindTooltip(() => {
        const getLat = (pt) => pt.gps ? pt.gps.latitude.toFixed(6) : (pt.lat !== undefined ? pt.lat.toFixed(6) : '--');
        const getLon = (pt) => pt.gps ? pt.gps.longitude.toFixed(6) : (pt.lon !== undefined ? pt.lon.toFixed(6) : '--');

        return `
        <div style="font-family: monospace; font-size: 11px; line-height: 1.45;">
          <b style="color: #c084fc; font-size: 12px;">📦 ${b.batch_id}</b> <span style="color: #94a3b8;">(${b.internal_code})</span><br>
          <b>Hàng:</b> ${b.row || '--'} | <b>Cột:</b> ${b.column || '--'}<br>
          <b>Tâm (u, v):</b> (${b.centroid.pixel.x}, ${b.centroid.pixel.y}) <br>
          <b>Tâm (GPS):</b> (${getLat(b.centroid)}, ${getLon(b.centroid)})<br>
          <span style="color: #38bdf8;">1. Tây Bắc (NW):</span> (${b.corners[0].pixel.x}, ${b.corners[0].pixel.y})<br>
          <span style="color: #64748b;">↳ GPS: ${getLat(b.corners[0])}, ${getLon(b.corners[0])}</span><br>
          <span style="color: #38bdf8;">2. Đông Bắc (NE):</span> (${b.corners[1].pixel.x}, ${b.corners[1].pixel.y})<br>
          <span style="color: #64748b;">↳ GPS: ${getLat(b.corners[1])}, ${getLon(b.corners[1])}</span><br>
          <span style="color: #38bdf8;">3. Đông Nam (SE):</span> (${b.corners[2].pixel.x}, ${b.corners[2].pixel.y})<br>
          <span style="color: #64748b;">↳ GPS: ${getLat(b.corners[2])}, ${getLon(b.corners[2])}</span><br>
          <span style="color: #38bdf8;">4. Tây Nam (SW):</span> (${b.corners[3].pixel.x}, ${b.corners[3].pixel.y})<br>
          <span style="color: #64748b;">↳ GPS: ${getLat(b.corners[3])}, ${getLon(b.corners[3])}</span>
        </div>
        `;
      }, {
        direction: 'top',
        sticky: false,
        className: 'utm-point-tooltip'
      });

      const onSelect = (e) => {
        if (e) L.DomEvent.stopPropagation(e);
        this.focusBox(idx);
        if (typeof this.onBoxSelected === 'function') {
          this.onBoxSelected(b);
        }
      };

      poly.on('click', onSelect);
    });

    // Tự động căn khung nhìn bao quát các khung box
    const inBoundsBoxes = boxes.filter(b => b.in_bounds);
    const targetBoxes = inBoundsBoxes.length > 0 ? inBoundsBoxes : boxes;
    if (targetBoxes.length > 0) {
      const allLatLngs = [];
      targetBoxes.forEach(b => {
        b.corners.forEach(c => allLatLngs.push(L.latLng(-c.pixel.y, c.pixel.x)));
      });
      if (allLatLngs.length > 0) {
        this.map.fitBounds(L.latLngBounds(allLatLngs), { padding: [50, 50], maxZoom: 4 });
      }
    }
  }

  toggleBoxesLayer(visible) {
    this.isBoxesVisible = visible;
    if (!this.boxesLayer) return;
    if (visible && !this.map.hasLayer(this.boxesLayer)) {
      this.boxesLayer.addTo(this.map);
    } else if (!visible && this.map.hasLayer(this.boxesLayer)) {
      this.map.removeLayer(this.boxesLayer);
    }
  }

  focusBox(idx) {
    const b = this.canonicalBoxes[idx];
    if (!b) return;
    if (this.boxesTarget && this.currentView !== this.boxesTarget) {
      if (this.boxesTarget === 'big') this.switchToBigView();
      else if (this.boxesTarget === 'sub2') this.switchToSub2View();
      else this.switchToSubView();
    }
    const c = b.centroid.pixel;
    this.map.setView([-c.y, c.x], Math.max(this.map.getZoom(), 3));

    if (this._activeBoxPoly && this._activeBoxPoly !== b._polygon) {
      if (this._activeBoxPoly._originalStyle) {
        this._activeBoxPoly.setStyle(this._activeBoxPoly._originalStyle);
      } else {
        this._activeBoxPoly.setStyle({ color: '#a855f7', weight: 2, fillColor: '#c084fc', fillOpacity: 0.22 });
      }
    }
    if (b._polygon) {
      b._polygon.setStyle({ color: '#f43f5e', weight: 4, fillColor: '#fb7185', fillOpacity: 0.45 });
      this._activeBoxPoly = b._polygon;
    }
  }

  clearBoxes() {
    if (this.boxesLayer) this.boxesLayer.clearLayers();
    this.canonicalBoxes = [];
    this._activeBoxPoly = null;
  }

  /**
   * Cập nhật hiển thị lớp điểm tự do tương ứng với chế độ xem hiện tại
   */
  updateFreePointsVisibility() {
    if (!this.freePointsLayerBig) return;
    if (this.currentView === 'big') {
      if (!this.map.hasLayer(this.freePointsLayerBig)) this.freePointsLayerBig.addTo(this.map);
      if (this.map.hasLayer(this.freePointsLayerSub)) this.map.removeLayer(this.freePointsLayerSub);
      if (this.map.hasLayer(this.freePointsLayerSub2)) this.map.removeLayer(this.freePointsLayerSub2);
    } else if (this.currentView === 'sub') {
      if (!this.map.hasLayer(this.freePointsLayerSub)) this.freePointsLayerSub.addTo(this.map);
      if (this.map.hasLayer(this.freePointsLayerBig)) this.map.removeLayer(this.freePointsLayerBig);
      if (this.map.hasLayer(this.freePointsLayerSub2)) this.map.removeLayer(this.freePointsLayerSub2);
    } else if (this.currentView === 'sub2') {
      if (!this.map.hasLayer(this.freePointsLayerSub2)) this.freePointsLayerSub2.addTo(this.map);
      if (this.map.hasLayer(this.freePointsLayerBig)) this.map.removeLayer(this.freePointsLayerBig);
      if (this.map.hasLayer(this.freePointsLayerSub)) this.map.removeLayer(this.freePointsLayerSub);
    }
  }

  /**
   * Thêm 1 điểm chấm tự do lên bản đồ
   * @param {Object} pt - Dữ liệu điểm { id, col, row, pixel, utm, gps, ... }
   * @param {string} viewType - 'big' | 'sub' | 'sub2'
   * @returns {L.CircleMarker} Leaflet marker đã tạo
   */
  addFreePointMarker(pt, viewType = 'big') {
    const isBig = viewType === 'big';
    const isSub2 = viewType === 'sub2';
    const color = isBig ? '#10b981' : (isSub2 ? '#f59e0b' : '#06b6d4');
    const regionLabel = isBig ? 'Tổng Quan (Ortho To)' : (isSub2 ? 'Ortho Vùng 2' : 'Ortho Vùng 1');
    const coordName = isBig ? `X: ${pt.pixel.x}, Y: ${pt.pixel.y}` : `u: ${pt.pixel.u}, v: ${pt.pixel.v}`;

    const marker = L.circleMarker([-pt.row, pt.col], {
      pane: 'freePointsPane',
      radius: 7,
      color: '#ffffff',
      weight: 2,
      fillColor: color,
      fillOpacity: 0.9,
    });

    const tooltipContent = `
      <div style="font-family: monospace; font-size: 11px; line-height: 1.45;">
        <b style="color: ${color}; font-size: 12px;">📍 ${pt.id}</b> <span style="color: #94a3b8;">(${regionLabel})</span><br>
        <b>Pixel:</b> (${coordName})<br>
        <b>UTM 49N:</b> E ${pt.utm.easting.toFixed(2)}, N ${pt.utm.northing.toFixed(2)}<br>
        <b>GPS:</b> ${pt.gps.lat.toFixed(6)}, ${pt.gps.lon.toFixed(6)}
      </div>
    `;

    marker.bindTooltip(tooltipContent, {
      permanent: false,
      direction: 'top',
      offset: [0, -8],
      className: 'utm-point-tooltip'
    });

    const targetLayer = isBig ? this.freePointsLayerBig : (isSub2 ? this.freePointsLayerSub2 : this.freePointsLayerSub);
    if (targetLayer) {
      targetLayer.addLayer(marker);
    }
    return marker;
  }

  /**
   * Xóa 1 điểm marker khỏi bản đồ
   */
  removeFreePointMarker(marker, viewType = 'big') {
    const isBig = viewType === 'big';
    const isSub2 = viewType === 'sub2';
    const targetLayer = isBig ? this.freePointsLayerBig : (isSub2 ? this.freePointsLayerSub2 : this.freePointsLayerSub);
    if (targetLayer && marker) {
      targetLayer.removeLayer(marker);
    }
  }

  /**
   * Xóa toàn bộ điểm marker tự do
   */
  clearFreePointMarkers(viewType = 'all') {
    if (viewType === 'big' || viewType === 'all') {
      if (this.freePointsLayerBig) this.freePointsLayerBig.clearLayers();
    }
    if (viewType === 'sub' || viewType === 'all') {
      if (this.freePointsLayerSub) this.freePointsLayerSub.clearLayers();
    }
    if (viewType === 'sub2' || viewType === 'all') {
      if (this.freePointsLayerSub2) this.freePointsLayerSub2.clearLayers();
    }
  }

  /**
   * Tập trung khung nhìn vào 1 điểm tự do
   */
  focusFreePoint(col, row, viewType = 'big') {
    if (viewType === 'big' && this.currentView !== 'big') {
      this.switchToBigView();
    } else if (viewType === 'sub' && this.currentView !== 'sub') {
      this.switchToSubView();
    } else if (viewType === 'sub2' && this.currentView !== 'sub2') {
      this.switchToSub2View();
    }
    this.map.setView([-row, col], Math.max(this.map.getZoom(), 4));
  }
}

window.OrthoViewer = OrthoViewer;


