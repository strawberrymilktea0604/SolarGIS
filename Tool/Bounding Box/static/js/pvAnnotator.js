/**
 * pvAnnotator.js - Module đánh dấu Bounding Box tấm PV (4 điểm góc + 1 centroid)
 * - Chế độ Đóng Dấu Nhanh 1-Click (PV Stamp Tool): Dập ngay 4 góc + centroid theo khuôn mẫu
 * - Tùy chỉnh kích thước hình dạng to/nhỏ (W, H, +/- 10%), hướng Ngang / Dọc, góc xoay nghiêng
 * - Hỗ trợ "Hút mẫu từ tấm có sẵn" (Pick sample size from existing panel)
 * - Tự động tính toán điểm tâm centroid: X_c = (X1+X2+X3+X4)/4, Y_c = (Y1+Y2+Y3+Y4)/4
 * - Lưu trữ và bảo toàn cả tọa độ Pixel (X, Y) và tọa độ địa lý (Lat, Lon / UTM) của 4 góc + centroid
 * - Hỗ trợ kéo di chuyển vi chỉnh 4 góc và centroid độc lập
 * - Xuất file JSON và Nhập lại JSON tương thích 100%
 */
class PVAnnotator {
  constructor(orthoViewer) {
    this.viewer = orthoViewer;
    this.map = orthoViewer.map;
    this.isDrawMode = false;
    this.subMode = 'stamp'; // 'stamp' (1-click dập khuôn) hoặc 'manual' (chấm 4 điểm thủ công)

    // Cấu hình khuôn mẫu tấm PV
    this.stampConfig = {
      width: 60,                // Chiều rộng pixel
      height: 30,               // Chiều cao pixel
      orientation: 'horizontal',// 'horizontal' (Ngang) | 'vertical' (Dọc)
      angleDeg: 0               // Góc xoay (-90 đến +90 hoặc 0-360)
    };

    this.panels = []; // Danh sách các tấm PV đã đánh dấu
    this.currentDraftPoints = []; // Các điểm tạm thời khi vẽ thủ công [P1, P2, P3]
    this.draftMarkers = [];
    this.draftLines = null;
    this.nextPanelId = 1;

    // Layer preview Ghost Box mờ mờ khi di chuột
    this.ghostLayer = null;
    this.ghostCenterMarker = null;

    // Layer group chứa tất cả các annotation PV
    this.pvLayerGroup = L.layerGroup().addTo(this.map);

    this.initEvents();
  }

  initEvents() {
    // 1. Click trên bản đồ
    this.map.on('click', (e) => {
      if (!this.isDrawMode) return;
      if (!this.viewer.bigInfo) {
        alert('Vui lòng nạp Ortho To trước khi đánh dấu tấm PV!');
        this.setMode(false);
        return;
      }

      if (this.subMode === 'stamp') {
        this.stampPanelAt(e.latlng);
      } else {
        this.handleManualClick(e);
      }
    });

    // 2. Di chuột trên bản đồ để vẽ Ghost Box xem trước vị trí
    this.map.on('mousemove', (e) => {
      if (!this.isDrawMode || this.subMode !== 'stamp' || !this.viewer.bigInfo) {
        this.hideGhostPreview();
        return;
      }
      this.updateGhostPreview(e.latlng);
    });

    this.map.on('mouseout', () => {
      this.hideGhostPreview();
    });

    // 3. Phím tắt tiện lợi:
    // - Esc: Hủy vẽ / Tắt chế độ đánh dấu
    // - Ctrl+Z: Undo tấm vừa đánh
    // - R: Đổi hướng Ngang <-> Dọc (hoặc xoay)
    // - [ và ]: Thu nhỏ / Phóng to kích thước khuôn mẫu
    document.addEventListener('keydown', (e) => {
      // Bỏ qua nếu người dùng đang nhập text trong ô input
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
        return;
      }

      if (e.key === 'Tab') {
        e.preventDefault();
        this.setSubMode(this.subMode === 'stamp' ? 'manual' : 'stamp');
      } else if (e.key === 'Escape') {
        if (this.subMode === 'manual' && this.currentDraftPoints.length > 0) {
          this.cancelDraft();
        } else {
          this.setMode(false);
        }
      } else if (e.ctrlKey && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault();
        this.undo();
      } else if (e.key === 'r' || e.key === 'R') {
        if (this.isDrawMode) {
          e.preventDefault();
          this.toggleOrientation();
        }
      } else if (e.key === '[' || e.key === '{') {
        if (this.isDrawMode) {
          e.preventDefault();
          this.scaleStamp(0.9); // Giảm 10%
        }
      } else if (e.key === ']' || e.key === '}') {
        if (this.isDrawMode) {
          e.preventDefault();
          this.scaleStamp(1.1); // Tăng 10%
        }
      }
    });
  }

  setMode(drawMode) {
    this.isDrawMode = drawMode;
    const container = document.getElementById(this.viewer.containerId);
    const guideEl = document.getElementById('drawGuideBadge');

    if (drawMode) {
      if (container) container.style.cursor = 'crosshair';
      this.updateGuideText();
      if (guideEl) {
        guideEl.style.display = 'flex';
      }
      this.syncStampConfigToUI();
    } else {
      if (container) container.style.cursor = '';
      if (guideEl) guideEl.style.display = 'none';
      this.hideGhostPreview();
      this.cancelDraft();
    }
    this.updateStartButtonUI();
  }

  setSubMode(subMode) {
    this.subMode = subMode;
    const btnStamp = document.getElementById('btnSubModeStamp');
    const btnManual = document.getElementById('btnSubModeManual');
    const stampBox = document.getElementById('stampControlsBox');

    if (btnStamp) btnStamp.classList.toggle('active', subMode === 'stamp');
    if (btnManual) btnManual.classList.toggle('active', subMode === 'manual');
    if (stampBox) stampBox.style.display = subMode === 'stamp' ? 'block' : 'none';

    if (subMode !== 'stamp') {
      this.hideGhostPreview();
    }
    this.cancelDraft();
    this.updateGuideText();
    this.updateStartButtonUI();
    if (this.onSubModeChange) {
      this.onSubModeChange(subMode);
    }
  }

  updateStartButtonUI() {
    const btnStart = document.getElementById('btnStartDrawPV');
    if (!btnStart) return;
    if (this.isDrawMode) {
      btnStart.innerHTML = `<i class="fa-solid fa-stop"></i> Đang ${this.subMode === 'stamp' ? 'Dập 1-Click' : 'Chấm 4 Góc'} (Bấm để Dừng)`;
      btnStart.className = 'btn btn-action btn-block active-drawing';
    } else {
      btnStart.innerHTML = this.subMode === 'stamp' 
        ? `<i class="fa-solid fa-stamp"></i> Bật Đánh Tấm PV (1-Click)`
        : `<i class="fa-solid fa-draw-polygon"></i> Bật Chấm 4 Góc`;
      btnStart.className = 'btn btn-warning btn-block';
    }
  }

  updateGuideText() {
    const guideEl = document.getElementById('drawGuideBadge');
    if (!guideEl) return;

    if (this.subMode === 'stamp') {
      const orientText = this.stampConfig.orientation === 'horizontal' ? 'Ngang' : 'Dọc';
      guideEl.innerHTML = `<i class="fa-solid fa-stamp"></i> <b>Chế độ Dập 1-Click:</b> Click chuột để đặt ngay tấm PV <b>${this.stampConfig.width}x${this.stampConfig.height}px (${orientText})</b> | Phím <b>[R]</b> đảo hướng | <b>Esc</b> thoát`;
    } else {
      const count = this.currentDraftPoints.length;
      if (count === 0) {
        guideEl.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Click điểm <b>Góc 1/4</b> của tấm PV (Esc để hủy)';
      } else if (count === 1) {
        guideEl.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Click điểm <b>Góc 2/4</b>...';
      } else if (count === 2) {
        guideEl.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Click điểm <b>Góc 3/4</b>...';
      } else if (count === 3) {
        guideEl.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Click điểm <b>Góc 4/4</b> để hoàn thành tấm pin';
      }
    }
  }

  /**
   * Tính toán tọa độ 4 góc của khuôn mẫu xoay quanh tâm (centerCol, centerRow)
   */
  calculateStampCorners(centerCol, centerRow) {
    const w = this.stampConfig.width;
    const h = this.stampConfig.height;
    const rad = (this.stampConfig.angleDeg * Math.PI) / 180;
    const cosA = Math.cos(rad);
    const sinA = Math.sin(rad);

    const halfW = w / 2;
    const halfH = h / 2;

    // Thứ tự 4 góc theo chiều kim đồng hồ từ Top-Left:
    // 1: Top-Left (-halfW, -halfH)
    // 2: Top-Right (halfW, -halfH)
    // 3: Bottom-Right (halfW, halfH)
    // 4: Bottom-Left (-halfW, halfH)
    const offsets = [
      { dx: -halfW, dy: -halfH },
      { dx: halfW, dy: -halfH },
      { dx: halfW, dy: halfH },
      { dx: -halfW, dy: halfH }
    ];

    return offsets.map(off => {
      const rx = off.dx * cosA - off.dy * sinA;
      const ry = off.dx * sinA + off.dy * cosA;
      const col = Math.round(centerCol + rx);
      const row = Math.round(centerRow + ry);
      return {
        col,
        row,
        latlng: L.latLng(-row, col)
      };
    });
  }

  /**
   * Đóng dấu (Stamp) 1-Click tại vị trí click chuột
   */
  stampPanelAt(latlng) {
    if (!this.viewer.bigInfo) return;
    const centerCol = Math.round(latlng.lng);
    const centerRow = Math.round(-latlng.lat);

    // Kiểm tra phạm vi ảnh
    if (centerCol < 0 || centerCol > this.viewer.bigInfo.width || centerRow < 0 || centerRow > this.viewer.bigInfo.height) {
      return;
    }

    const points = this.calculateStampCorners(centerCol, centerRow);
    this.createPVPanelFromPoints(points);
  }

  /**
   * Cập nhật hình chữ nhật xem trước (Ghost Box) khi di chuột
   */
  updateGhostPreview(latlng) {
    if (!this.viewer.bigInfo) return;
    const centerCol = Math.round(latlng.lng);
    const centerRow = Math.round(-latlng.lat);

    if (centerCol < 0 || centerCol > this.viewer.bigInfo.width || centerRow < 0 || centerRow > this.viewer.bigInfo.height) {
      this.hideGhostPreview();
      return;
    }

    const points = this.calculateStampCorners(centerCol, centerRow);
    const latlngs = points.map(p => p.latlng);

    if (!this.ghostLayer) {
      this.ghostLayer = L.polygon(latlngs, {
        color: '#f59e0b',
        weight: 2,
        dashArray: '5, 5',
        fillColor: '#f59e0b',
        fillOpacity: 0.3,
        interactive: false,
        className: 'pv-ghost-preview'
      }).addTo(this.pvLayerGroup);
    } else {
      this.ghostLayer.setLatLngs(latlngs);
      this.ghostLayer.setStyle({ opacity: 1, fillOpacity: 0.3 });
    }

    if (!this.ghostCenterMarker) {
      this.ghostCenterMarker = L.circleMarker(latlng, {
        radius: 3,
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 1,
        weight: 1,
        interactive: false
      }).addTo(this.pvLayerGroup);
    } else {
      this.ghostCenterMarker.setLatLng(latlng);
      this.ghostCenterMarker.setStyle({ opacity: 1, fillOpacity: 1 });
    }
  }

  hideGhostPreview() {
    if (this.ghostLayer) {
      this.ghostLayer.setStyle({ opacity: 0, fillOpacity: 0 });
    }
    if (this.ghostCenterMarker) {
      this.ghostCenterMarker.setStyle({ opacity: 0, fillOpacity: 0 });
    }
  }

  /**
   * Chế độ vẽ chấm 4 góc thủ công
   */
  handleManualClick(e) {
    const col = Math.round(e.latlng.lng);
    const row = Math.round(-e.latlng.lat);

    if (col < 0 || col > this.viewer.bigInfo.width || row < 0 || row > this.viewer.bigInfo.height) {
      return;
    }

    const pt = { col, row, latlng: e.latlng };
    this.currentDraftPoints.push(pt);

    const cornerIndex = this.currentDraftPoints.length;
    const marker = L.circleMarker(e.latlng, {
      radius: 5,
      color: '#f59e0b',
      fillColor: '#f59e0b',
      fillOpacity: 1,
      weight: 2
    }).addTo(this.pvLayerGroup);

    marker.bindTooltip(`${cornerIndex}`, { permanent: true, direction: 'top', className: 'draft-corner-badge' });
    this.draftMarkers.push(marker);

    if (this.currentDraftPoints.length > 1) {
      const latlngs = this.currentDraftPoints.map(p => p.latlng);
      if (this.draftLines) {
        this.draftLines.setLatLngs(latlngs);
      } else {
        this.draftLines = L.polyline(latlngs, { color: '#f59e0b', weight: 2, dashArray: '4, 4' }).addTo(this.pvLayerGroup);
      }
    }

    this.updateGuideText();

    if (this.currentDraftPoints.length === 4) {
      this.createPVPanelFromPoints(this.currentDraftPoints);
      this.cleanupDraftMarkers();
      this.currentDraftPoints = [];
      this.updateGuideText();
    }
  }

  cleanupDraftMarkers() {
    this.draftMarkers.forEach(m => this.pvLayerGroup.removeLayer(m));
    this.draftMarkers = [];
    if (this.draftLines) {
      this.pvLayerGroup.removeLayer(this.draftLines);
      this.draftLines = null;
    }
  }

  cancelDraft() {
    this.cleanupDraftMarkers();
    this.currentDraftPoints = [];
    this.updateGuideText();
  }

  /**
   * Đảo hướng Ngang <-> Dọc (hoán đổi W <-> H)
   */
  toggleOrientation() {
    const temp = this.stampConfig.width;
    this.stampConfig.width = this.stampConfig.height;
    this.stampConfig.height = temp;
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  /**
   * Đặt hướng rõ ràng
   */
  setOrientation(type) {
    if (type === 'horizontal') {
      if (this.stampConfig.width < this.stampConfig.height) {
        this.toggleOrientation();
      } else {
        this.stampConfig.orientation = 'horizontal';
        this.syncStampConfigToUI();
      }
    } else if (type === 'vertical') {
      if (this.stampConfig.width > this.stampConfig.height) {
        this.toggleOrientation();
      } else {
        this.stampConfig.orientation = 'vertical';
        this.syncStampConfigToUI();
      }
    }
  }

  /**
   * Phóng to / thu nhỏ tỷ lệ khuôn mẫu
   */
  scaleStamp(factor) {
    this.stampConfig.width = Math.max(5, Math.round(this.stampConfig.width * factor));
    this.stampConfig.height = Math.max(5, Math.round(this.stampConfig.height * factor));
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  /**
   * Tăng giảm W hoặc H theo pixel
   */
  adjustDimensions(deltaW, deltaH) {
    this.stampConfig.width = Math.max(5, this.stampConfig.width + deltaW);
    this.stampConfig.height = Math.max(5, this.stampConfig.height + deltaH);
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  /**
   * Đặt góc xoay nghiêng
   */
  setAngle(deg) {
    this.stampConfig.angleDeg = parseInt(deg) || 0;
    this.syncStampConfigToUI();
  }

  /**
   * Lấy mẫu kích thước từ một tấm PV đã có trên bản đồ
   */
  pickSizeFromPanel(panelId) {
    const panel = this.panels.find(p => p.id === panelId);
    if (!panel || !panel.corners_pixel || panel.corners_pixel.length < 4) return;
    const pts = panel.corners_pixel;

    // Chiều dài cạnh 1 -> 2 (Width)
    const dxW = pts[1].x - pts[0].x;
    const dyW = pts[1].y - pts[0].y;
    const w = Math.round(Math.hypot(dxW, dyW));

    // Chiều dài cạnh 2 -> 3 (Height)
    const dxH = pts[2].x - pts[1].x;
    const dyH = pts[2].y - pts[1].y;
    const h = Math.round(Math.hypot(dxH, dyH));

    // Góc nghiêng theo cạnh W
    let angleDeg = Math.round((Math.atan2(dyW, dxW) * 180) / Math.PI);
    if (angleDeg > 90) angleDeg -= 180;
    if (angleDeg < -90) angleDeg += 180;

    this.stampConfig.width = Math.max(5, w);
    this.stampConfig.height = Math.max(5, h);
    this.stampConfig.angleDeg = angleDeg;
    this.stampConfig.orientation = (w >= h) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();

    alert(`Đã lấy mẫu kích thước từ tấm ${panel.id}:\n- Rộng (W): ${w} px\n- Cao (H): ${h} px\n- Góc nghiêng: ${angleDeg}°\n- Hướng: ${this.stampConfig.orientation === 'horizontal' ? 'Ngang' : 'Dọc'}`);
  }

  /**
   * Phóng to / thu nhỏ một tấm PV đã có xung quanh tâm Centroid của nó
   */
  scalePanel(panelId, factor) {
    const p = this.panels.find(x => x.id === panelId);
    if (!p) return;
    const cX = p.centroid_pixel.x;
    const cY = p.centroid_pixel.y;

    p.corners_pixel.forEach((cp, idx) => {
      const newX = Math.round(cX + (cp.x - cX) * factor);
      const newY = Math.round(cY + (cp.y - cY) * factor);
      cp.x = newX;
      cp.y = newY;
      p.corners_geo[idx] = this.pixelToGeo(newX, newY);
      if (p.layers && p.layers.cornerMarkers[idx]) {
        p.layers.cornerMarkers[idx].setLatLng([-newY, newX]);
      }
    });

    if (p.layers && p.layers.polygon) {
      p.layers.polygon.setLatLngs(p.corners_pixel.map(pt => [-pt.y, pt.x]));
    }
    this.updatePanelListUI();
  }

  /**
   * Đồng bộ các giá trị cấu hình ra giao diện DOM
   */
  syncStampConfigToUI() {
    const wInput = document.getElementById('stampWidthInput');
    const hInput = document.getElementById('stampHeightInput');
    const badge = document.getElementById('orientationBadge');
    const btnH = document.getElementById('btnOrientHorizontal');
    const btnV = document.getElementById('btnOrientVertical');
    const angleSlider = document.getElementById('stampAngleSlider');
    const angleVal = document.getElementById('stampAngleVal');
    const tbLabel = document.getElementById('tbOrientLabel');

    if (wInput && document.activeElement !== wInput) wInput.value = this.stampConfig.width;
    if (hInput && document.activeElement !== hInput) hInput.value = this.stampConfig.height;

    const isH = this.stampConfig.orientation === 'horizontal';
    if (badge) {
      badge.innerText = isH ? 'Ngang' : 'Dọc';
    }
    if (btnH) btnH.classList.toggle('active', isH);
    if (btnV) btnV.classList.toggle('active', !isH);

    if (angleSlider && document.activeElement !== angleSlider) angleSlider.value = this.stampConfig.angleDeg;
    if (angleVal) angleVal.innerText = `${this.stampConfig.angleDeg}°`;

    if (tbLabel) {
      tbLabel.innerText = `${isH ? 'Ngang' : 'Dọc'} (${this.stampConfig.width}x${this.stampConfig.height})`;
    }

    this.updateGuideText();
  }

  /**
   * Tính toán và tạo mới tấm PV từ 4 góc
   * Bảo toàn chính xác 4 góc pixel, 4 góc geo, và tự động tính toán centroid
   */
  createPVPanelFromPoints(points, customId = null) {
    const cornersPixel = points.map((p, idx) => ({
      index: idx + 1,
      x: p.col,
      y: p.row
    }));

    // 1. Tính Centroid (Tâm hình chữ nhật/đa giác 4 điểm)
    const centroidX = Math.round((cornersPixel[0].x + cornersPixel[1].x + cornersPixel[2].x + cornersPixel[3].x) / 4);
    const centroidY = Math.round((cornersPixel[0].y + cornersPixel[1].y + cornersPixel[2].y + cornersPixel[3].y) / 4);
    const centroidPixel = { x: centroidX, y: centroidY };

    // 2. Chuyển đổi tọa độ địa lý cho 4 góc và centroid nếu có transform
    const cornersGeo = cornersPixel.map(cp => this.pixelToGeo(cp.x, cp.y));
    const centroidGeo = this.pixelToGeo(centroidX, centroidY);

    const panelId = customId || `PV_${String(this.nextPanelId++).padStart(3, '0')}`;

    const panelData = {
      id: panelId,
      label: "solar_panel",
      corners_pixel: cornersPixel,
      centroid_pixel: centroidPixel,
      corners_geo: cornersGeo,
      centroid_geo: centroidGeo
    };

    // 3. Render lên bản đồ Leaflet
    const layers = this.renderPanelLayers(panelData);
    panelData.layers = layers;

    this.panels.push(panelData);
    this.updatePanelListUI();
    return panelData;
  }

  pixelToGeo(col, row) {
    if (!this.viewer.bigInfo || !this.viewer.bigInfo.transform) {
      return { x: col, y: row };
    }
    const t = this.viewer.bigInfo.transform;
    const geoX = t[2] + t[0] * col + t[1] * row;
    const geoY = t[5] + t[3] * col + t[4] * row;

    if (this.viewer.bigInfo.crs && this.viewer.bigInfo.crs.includes('4326')) {
      return {
        lon: Number(geoX.toFixed(7)),
        lat: Number(geoY.toFixed(7))
      };
    }
    return {
      easting: Number(geoX.toFixed(2)),
      northing: Number(geoY.toFixed(2))
    };
  }

  /**
   * Vẽ đa giác viền tấm pin, 4 điểm góc kéo rê và điểm centroid phát sáng
   */
  renderPanelLayers(panelData) {
    const latlngs = panelData.corners_pixel.map(p => [-p.y, p.x]);
    const centroidLatLng = [-panelData.centroid_pixel.y, panelData.centroid_pixel.x];

    // 1. Đa giác viền tấm PV
    const polygon = L.polygon(latlngs, {
      color: '#f59e0b',
      weight: 2,
      fillColor: '#f59e0b',
      fillOpacity: 0.22,
      className: 'pv-panel-polygon'
    }).addTo(this.pvLayerGroup);

    polygon.bindTooltip(`<b>${panelData.id}</b>`, {
      permanent: false,
      direction: 'center',
      className: 'pv-id-tooltip'
    });

    // 2. Điểm tâm Centroid (Ký hiệu Target ⌖ nổi bật)
    const centroidIcon = L.divIcon({
      className: 'centroid-div-icon',
      html: `<div class="centroid-marker" title="Centroid (${panelData.id}): X=${panelData.centroid_pixel.x}, Y=${panelData.centroid_pixel.y}">⌖</div>`,
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    });

    const centroidMarker = L.marker(centroidLatLng, {
      icon: centroidIcon,
      draggable: true
    }).addTo(this.pvLayerGroup);

    // 3. Bốn điểm góc (Draggable góc 1, 2, 3, 4)
    const cornerMarkers = panelData.corners_pixel.map((cp, idx) => {
      const cornerIcon = L.divIcon({
        className: 'corner-div-icon',
        html: `<div class="corner-handle" title="Góc ${cp.index}: X=${cp.x}, Y=${cp.y}">${cp.index}</div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
      });

      const m = L.marker([-cp.y, cp.x], {
        icon: cornerIcon,
        draggable: true
      }).addTo(this.pvLayerGroup);

      // Kéo góc để vi chỉnh tọa độ
      m.on('drag', () => {
        const newCol = Math.round(m.getLatLng().lng);
        const newRow = Math.round(-m.getLatLng().lat);
        panelData.corners_pixel[idx].x = newCol;
        panelData.corners_pixel[idx].y = newRow;
        panelData.corners_geo[idx] = this.pixelToGeo(newCol, newRow);

        // Cập nhật lại polygon
        const updatedLatLngs = panelData.corners_pixel.map(p => [-p.y, p.x]);
        polygon.setLatLngs(updatedLatLngs);

        // Tự động tính toán lại Centroid
        const cX = Math.round((panelData.corners_pixel[0].x + panelData.corners_pixel[1].x + panelData.corners_pixel[2].x + panelData.corners_pixel[3].x) / 4);
        const cY = Math.round((panelData.corners_pixel[0].y + panelData.corners_pixel[1].y + panelData.corners_pixel[2].y + panelData.corners_pixel[3].y) / 4);
        panelData.centroid_pixel = { x: cX, y: cY };
        panelData.centroid_geo = this.pixelToGeo(cX, cY);

        centroidMarker.setLatLng([-cY, cX]);
      });

      m.on('dragend', () => {
        this.updatePanelListUI();
      });

      return m;
    });

    // Khi kéo Centroid -> Di chuyển cả tấm pin!
    let prevCentroidPos = centroidLatLng;
    centroidMarker.on('dragstart', () => {
      prevCentroidPos = centroidMarker.getLatLng();
    });

    centroidMarker.on('drag', () => {
      const curPos = centroidMarker.getLatLng();
      const dLng = curPos.lng - prevCentroidPos.lng;
      const dLat = curPos.lat - prevCentroidPos.lat;
      prevCentroidPos = curPos;

      panelData.corners_pixel.forEach((cp, i) => {
        cp.x = Math.round(cp.x + dLng);
        cp.y = Math.round(cp.y - dLat);
        panelData.corners_geo[i] = this.pixelToGeo(cp.x, cp.y);
        cornerMarkers[i].setLatLng([-cp.y, cp.x]);
      });

      const updatedLatLngs = panelData.corners_pixel.map(p => [-p.y, p.x]);
      polygon.setLatLngs(updatedLatLngs);

      const cX = Math.round(curPos.lng);
      const cY = Math.round(-curPos.lat);
      panelData.centroid_pixel = { x: cX, y: cY };
      panelData.centroid_geo = this.pixelToGeo(cX, cY);
    });

    centroidMarker.on('dragend', () => {
      this.updatePanelListUI();
    });

    return {
      polygon,
      centroidMarker,
      cornerMarkers
    };
  }

  deletePanel(id) {
    const idx = this.panels.findIndex(p => p.id === id);
    if (idx !== -1) {
      const p = this.panels[idx];
      if (p.layers) {
        this.pvLayerGroup.removeLayer(p.layers.polygon);
        this.pvLayerGroup.removeLayer(p.layers.centroidMarker);
        p.layers.cornerMarkers.forEach(m => this.pvLayerGroup.removeLayer(m));
      }
      this.panels.splice(idx, 1);
      this.updatePanelListUI();
    }
  }

  clearAll() {
    this.panels.forEach(p => {
      if (p.layers) {
        this.pvLayerGroup.removeLayer(p.layers.polygon);
        this.pvLayerGroup.removeLayer(p.layers.centroidMarker);
        p.layers.cornerMarkers.forEach(m => this.pvLayerGroup.removeLayer(m));
      }
    });
    this.panels = [];
    this.cancelDraft();
    this.updatePanelListUI();
  }

  undo() {
    if (this.subMode === 'manual' && this.currentDraftPoints.length > 0) {
      this.currentDraftPoints.pop();
      const lastMarker = this.draftMarkers.pop();
      if (lastMarker) this.pvLayerGroup.removeLayer(lastMarker);
      if (this.draftLines) {
        if (this.currentDraftPoints.length > 1) {
          this.draftLines.setLatLngs(this.currentDraftPoints.map(p => p.latlng));
        } else {
          this.pvLayerGroup.removeLayer(this.draftLines);
          this.draftLines = null;
        }
      }
      this.updateGuideText();
    } else if (this.panels.length > 0) {
      const lastPanel = this.panels[this.panels.length - 1];
      this.deletePanel(lastPanel.id);
    }
  }

  focusPanel(id) {
    const p = this.panels.find(x => x.id === id);
    if (p) {
      const latlngs = p.corners_pixel.map(pt => [-pt.y, pt.x]);
      const bounds = L.latLngBounds(latlngs);
      this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 4 });
      if (p.layers && p.layers.polygon) {
        p.layers.polygon.openTooltip();
      }
    }
  }

  /**
   * Cập nhật danh sách tấm PV ra Sidebar
   */
  updatePanelListUI() {
    const countBadge = document.getElementById('pvCountBadge');
    if (countBadge) countBadge.innerText = `${this.panels.length} tấm`;

    const tabPVBadge = document.getElementById('tabPVBadge');
    if (tabPVBadge) tabPVBadge.innerText = this.panels.length;

    const listContainer = document.getElementById('pvListContainer');
    if (!listContainer) return;

    const btnClearAll = document.getElementById('btnClearAllPV');
    if (btnClearAll) {
      btnClearAll.style.display = this.panels.length > 0 ? 'block' : 'none';
    }

    if (this.panels.length === 0) {
      listContainer.innerHTML = '<div class="empty-hint"><i class="fa-regular fa-clone"></i> Chưa có tấm PV nào. Bấm <b>"Đánh tấm mới"</b> để dập 1-click hoặc chấm 4 góc trên ảnh Ortho To.</div>';
      return;
    }

    listContainer.innerHTML = '';
    this.panels.forEach(p => {
      const item = document.createElement('div');
      item.className = 'pv-item-card';

      // Tính kích thước xấp xỉ của tấm PV này
      const pts = p.corners_pixel;
      const wEst = Math.round(Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
      const hEst = Math.round(Math.hypot(pts[2].x - pts[1].x, pts[2].y - pts[1].y));
      
      const geoText = p.centroid_geo.lat 
        ? `Lat: ${p.centroid_geo.lat.toFixed(6)}, Lon: ${p.centroid_geo.lon.toFixed(6)}`
        : `E: ${p.centroid_geo.easting || p.centroid_pixel.x}, N: ${p.centroid_geo.northing || p.centroid_pixel.y}`;

      item.innerHTML = `
        <div class="pv-item-header">
          <div class="pv-item-title">
            <span class="pv-id-tag">${p.id}</span>
            <span class="pv-dim-tag">${wEst}x${hEst}px</span>
            <span class="pv-centroid-val">⌖ (${p.centroid_pixel.x}, ${p.centroid_pixel.y})</span>
          </div>
          <div class="pv-item-actions">
            <button class="btn-icon pick-btn" title="Lấy kích thước tấm này làm khuôn mẫu"><i class="fa-solid fa-eye-dropper"></i></button>
            <button class="btn-icon scale-down-btn" title="Thu nhỏ 10%"><i class="fa-solid fa-compress"></i></button>
            <button class="btn-icon scale-up-btn" title="Phóng to 10%"><i class="fa-solid fa-expand"></i></button>
            <button class="btn-icon focus-btn" title="Phóng to đến tấm này"><i class="fa-solid fa-crosshairs"></i></button>
            <button class="btn-icon delete-btn" title="Xóa tấm này"><i class="fa-solid fa-trash-can"></i></button>
          </div>
        </div>
        <div class="pv-item-meta">
          <div class="meta-row">
            <span>Tọa độ địa lý tâm:</span>
            <span class="val">${geoText}</span>
          </div>
          <div class="meta-row corners-preview">
            <span>4 Góc:</span>
            <span class="val">1: (${p.corners_pixel[0].x}, ${p.corners_pixel[0].y}) | 2: (${p.corners_pixel[1].x}, ${p.corners_pixel[1].y}) | 3: (${p.corners_pixel[2].x}, ${p.corners_pixel[2].y}) | 4: (${p.corners_pixel[3].x}, ${p.corners_pixel[3].y})</span>
          </div>
        </div>
      `;

      item.querySelector('.pick-btn').addEventListener('click', () => this.pickSizeFromPanel(p.id));
      item.querySelector('.scale-down-btn').addEventListener('click', () => this.scalePanel(p.id, 0.9));
      item.querySelector('.scale-up-btn').addEventListener('click', () => this.scalePanel(p.id, 1.1));
      item.querySelector('.focus-btn').addEventListener('click', () => this.focusPanel(p.id));
      item.querySelector('.delete-btn').addEventListener('click', () => this.deletePanel(p.id));

      listContainer.appendChild(item);
    });
  }

  /**
   * Xuất danh sách tấm PV ra file JSON
   */
  exportJSON() {
    if (this.panels.length === 0) {
      alert('Chưa có tấm PV nào để xuất!');
      return;
    }

    const exportData = {
      version: "1.0",
      project: "Solar PV Panel Annotations",
      generated_at: new Date().toISOString(),
      ortho_file: this.viewer.bigInfo ? this.viewer.bigInfo.file_name : "unknown",
      dimensions: this.viewer.bigInfo ? { width: this.viewer.bigInfo.width, height: this.viewer.bigInfo.height } : null,
      crs: this.viewer.bigInfo ? this.viewer.bigInfo.crs : null,
      total_panels: this.panels.length,
      panels: this.panels.map(p => ({
        id: p.id,
        label: p.label,
        centroid_pixel: p.centroid_pixel,
        corners_pixel: p.corners_pixel.map(c => ({ index: c.index, x: c.x, y: c.y })),
        centroid_geo: p.centroid_geo,
        corners_geo: p.corners_geo
      }))
    };

    const jsonStr = JSON.stringify(exportData, null, 2);
    const fileName = `pv_annotations_${(this.viewer.bigInfo ? this.viewer.bigInfo.file_name : 'ortho').replace(/\.[^/.]+$/, "")}.json`;
    
    OrthoReader.downloadFile(jsonStr, fileName, 'application/json');
  }

  /**
   * Nhập lại danh sách tấm PV từ file JSON
   */
  importJSON(jsonString) {
    try {
      const data = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
      if (!data.panels || !Array.isArray(data.panels)) {
        throw new Error('Định dạng JSON không hợp lệ. Cần có trường "panels" là mảng.');
      }

      let importedCount = 0;
      data.panels.forEach(p => {
        if (p.corners_pixel && p.corners_pixel.length === 4) {
          const points = p.corners_pixel.map(c => ({
            col: c.x,
            row: c.y
          }));
          this.createPVPanelFromPoints(points, p.id);
          importedCount++;
        }
      });

      this.updatePanelListUI();
      alert(`Đã nạp thành công ${importedCount} tấm PV lên bản đồ!`);

      // Tự động fit bounds nếu có tấm pin
      if (this.panels.length > 0) {
        const allLatLngs = [];
        this.panels.forEach(p => {
          p.corners_pixel.forEach(pt => allLatLngs.push([-pt.y, pt.x]));
        });
        this.map.fitBounds(L.latLngBounds(allLatLngs), { padding: [40, 40] });
      }
    } catch (err) {
      alert(`Lỗi khi nhập JSON: ${err.message}`);
    }
  }
}

window.PVAnnotator = PVAnnotator;
