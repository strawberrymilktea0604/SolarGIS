/**
 * pvAnnotator.js - Module đánh dấu Bounding Box tấm PV (4 điểm góc + 1 centroid)
 * - Chế độ Đóng Dấu Nhanh 1-Click (PV Stamp Tool): Dập ngay 4 góc + centroid theo khuôn mẫu
 * - Tùy chỉnh kích thước hình dạng to/nhỏ (W, H, +/- 10%), hướng Ngang / Dọc, góc xoay nghiêng
 * - Hỗ trợ "Hút mẫu từ tấm có sẵn" (Pick sample size from existing panel)
 * - Tự động tính toán điểm tâm centroid: X_c = (X1+X2+X3+X4)/4, Y_c = (Y1+Y2+Y3+Y4)/4
 * - Lưu trữ và bảo toàn cả tọa độ Pixel (X, Y) và tọa độ địa lý (Lat, Lon / UTM) của 4 góc + centroid
 * - Kiến trúc Hiệu năng cao (High Performance Architecture):
 *   + Sử dụng Leaflet Canvas Renderer vẽ vector trực tiếp trên GPU -> Chịu tải hàng chục nghìn tấm pin mượt mà
 *   + Cơ chế Single Active Editor: Chỉ hiển thị 4 góc kéo và tâm kéo trên đúng tấm pin đang chọn -> Giảm DOM Marker từ 5.000 xuống tối đa 5 marker
 *   + Sidebar phân trang 30 tấm/trang + Tìm kiếm ID tức thì + Event Delegation
 *   + Tự động Reset ID về 1 khi xóa hết và đồng bộ ID kế tiếp chuẩn xác khi nạp file JSON
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
    this.nextPanelId = 1;

    // Quản lý tấm pin đang được chọn để chỉnh sửa (Active Selected Panel)
    this.selectedPanelId = null;
    this.activeHandles = null; // { centroidMarker, cornerMarkers }

    // Bản vẽ Canvas riêng biệt để tối ưu tối đa hiệu năng render hàng nghìn tấm
    this.canvasRenderer = L.canvas({ padding: 0.5 });

    // Các điểm tạm thời khi vẽ thủ công [P1, P2, P3]
    this.currentDraftPoints = [];
    this.draftMarkers = [];
    this.draftLines = null;

    // Layer preview Ghost Box mờ mờ khi di chuột
    this.ghostLayer = null;
    this.ghostCenterMarker = null;

    // Layer group chứa tất cả các annotation PV
    this.pvLayerGroup = L.layerGroup().addTo(this.map);

    // Trạng thái phân trang và tìm kiếm trong Sidebar
    this.currentPage = 1;
    this.pageSize = 30;
    this.searchQuery = '';

    this.initEvents();
    this.initListEvents();
  }

  initEvents() {
    // 1. Click trên bản đồ
    this.map.on('click', (e) => {
      if (!this.isDrawMode) {
        // Khi không ở chế độ vẽ: click ra ngoài bản đồ sẽ bỏ chọn tấm pin
        this.deselectPanel();
        return;
      }
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
    // - Esc: Hủy vẽ / Bỏ chọn / Tắt chế độ đánh dấu
    // - Ctrl+Z: Undo tấm vừa đánh
    // - Delete / Backspace: Xóa tấm pin đang chọn
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
        } else if (this.isDrawMode) {
          this.setMode(false);
        } else if (this.selectedPanelId) {
          this.deselectPanel();
        }
      } else if (e.ctrlKey && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault();
        this.undo();
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && this.selectedPanelId && !this.isDrawMode) {
        e.preventDefault();
        this.deletePanel(this.selectedPanelId);
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

  /**
   * Khởi tạo sự kiện cho danh sách Sidebar (Ủy quyền sự kiện - Event Delegation)
   */
  initListEvents() {
    const listContainer = document.getElementById('pvListContainer');
    if (listContainer) {
      listContainer.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (btn) {
          e.stopPropagation();
          const action = btn.dataset.action;
          const id = btn.dataset.id;
          if (action === 'pick') this.pickSizeFromPanel(id);
          else if (action === 'scale-down') this.scalePanel(id, 0.9);
          else if (action === 'scale-up') this.scalePanel(id, 1.1);
          else if (action === 'focus') this.focusPanel(id);
          else if (action === 'delete') this.deletePanel(id);
          return;
        }

        // Bấm vào thân card sẽ chọn tấm pin trên bản đồ
        const card = e.target.closest('.pv-item-card');
        if (card && card.dataset.panelId) {
          this.selectPanel(card.dataset.panelId, true);
        }
      });
    }

    // Nút phân trang Prev / Next
    const btnPrev = document.getElementById('btnPVPrevPage');
    if (btnPrev) {
      btnPrev.addEventListener('click', () => {
        if (this.currentPage > 1) {
          this.currentPage--;
          this.updatePanelListUI();
        }
      });
    }

    const btnNext = document.getElementById('btnPVNextPage');
    if (btnNext) {
      btnNext.addEventListener('click', () => {
        const filtered = this.getFilteredPanels();
        const totalPages = Math.max(1, Math.ceil(filtered.length / this.pageSize));
        if (this.currentPage < totalPages) {
          this.currentPage++;
          this.updatePanelListUI();
        }
      });
    }

    // Ô tìm kiếm nhanh theo mã tấm pin
    const searchInput = document.getElementById('pvSearchInput');
    const btnClearSearch = document.getElementById('btnClearPVSearch');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.trim();
        if (btnClearSearch) {
          btnClearSearch.style.display = this.searchQuery ? 'block' : 'none';
        }
        this.currentPage = 1;
        this.updatePanelListUI();
      });
    }

    if (btnClearSearch) {
      btnClearSearch.addEventListener('click', () => {
        if (searchInput) searchInput.value = '';
        this.searchQuery = '';
        btnClearSearch.style.display = 'none';
        this.currentPage = 1;
        this.updatePanelListUI();
      });
    }
  }

  setMode(drawMode) {
    this.isDrawMode = drawMode;
    const container = document.getElementById(this.viewer.containerId);
    const guideEl = document.getElementById('drawGuideBadge');

    if (drawMode) {
      this.deselectPanel();
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

  toggleOrientation() {
    const temp = this.stampConfig.width;
    this.stampConfig.width = this.stampConfig.height;
    this.stampConfig.height = temp;
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

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

  scaleStamp(factor) {
    this.stampConfig.width = Math.max(5, Math.round(this.stampConfig.width * factor));
    this.stampConfig.height = Math.max(5, Math.round(this.stampConfig.height * factor));
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  adjustDimensions(deltaW, deltaH) {
    this.stampConfig.width = Math.max(5, this.stampConfig.width + deltaW);
    this.stampConfig.height = Math.max(5, this.stampConfig.height + deltaH);
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  setAngle(deg) {
    this.stampConfig.angleDeg = parseInt(deg) || 0;
    this.syncStampConfigToUI();
  }

  pickSizeFromPanel(panelId) {
    const panel = this.panels.find(p => p.id === panelId);
    if (!panel || !panel.corners_pixel || panel.corners_pixel.length < 4) return;
    const pts = panel.corners_pixel;

    const dxW = pts[1].x - pts[0].x;
    const dyW = pts[1].y - pts[0].y;
    const w = Math.round(Math.hypot(dxW, dyW));

    const dxH = pts[2].x - pts[1].x;
    const dyH = pts[2].y - pts[1].y;
    const h = Math.round(Math.hypot(dxH, dyH));

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

  scalePanel(id, factor) {
    const p = this.panels.find(x => x.id === id);
    if (!p) return;
    const cX = p.centroid_pixel.x;
    const cY = p.centroid_pixel.y;

    p.corners_pixel.forEach((cp, idx) => {
      const newX = Math.round(cX + (cp.x - cX) * factor);
      const newY = Math.round(cY + (cp.y - cY) * factor);
      cp.x = newX;
      cp.y = newY;
      p.corners_geo[idx] = this.pixelToGeo(newX, newY);
    });

    if (p.polygon) {
      p.polygon.setLatLngs(p.corners_pixel.map(pt => [-pt.y, pt.x]));
    }

    if (this.selectedPanelId === id) {
      this.attachActiveHandles(p);
    }
    this.updateSinglePanelCardUI(p);
  }

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
   * Sinh mã ID tiếp theo một cách chuẩn xác:
   * - Nếu danh sách đang trống: luôn bắt đầu từ PV_001
   * - Nếu đã có tấm: tìm số lớn nhất hiện có và tăng thêm 1
   */
  getNextAvailableId() {
    if (this.panels.length === 0) {
      this.nextPanelId = 1;
      return 'PV_001';
    }
    let maxNum = 0;
    for (const p of this.panels) {
      const match = String(p.id).match(/(\d+)$/);
      if (match) {
        const num = parseInt(match[1], 10);
        if (!isNaN(num) && num > maxNum) {
          maxNum = num;
        }
      }
    }
    this.nextPanelId = maxNum + 1;
    return `PV_${String(this.nextPanelId).padStart(3, '0')}`;
  }

  /**
   * Tính toán và tạo mới tấm PV từ 4 góc
   * Bảo toàn chính xác 4 góc pixel, 4 góc geo, và tự động tính toán centroid
   * Hỗ trợ cờ skipUIRefresh để nạp hàng nghìn tấm cực nhanh không bị giật lag
   */
  createPVPanelFromPoints(points, customId = null, skipUIRefresh = false) {
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

    let panelId = customId;
    if (!panelId) {
      panelId = this.getNextAvailableId();
    } else {
      // Nếu có customId, cập nhật nextPanelId nếu số này lớn hơn
      const match = String(customId).match(/(\d+)$/);
      if (match) {
        const num = parseInt(match[1], 10);
        if (!isNaN(num) && num >= this.nextPanelId) {
          this.nextPanelId = num + 1;
        }
      }
    }

    const panelData = {
      id: panelId,
      label: "solar_panel",
      corners_pixel: cornersPixel,
      centroid_pixel: centroidPixel,
      corners_geo: cornersGeo,
      centroid_geo: centroidGeo
    };

    // 3. Render Polygon siêu nhẹ lên Canvas
    this.renderPanelPolygon(panelData);

    this.panels.push(panelData);

    if (!skipUIRefresh) {
      this.selectPanel(panelData.id, false);
      this.updatePanelListUI();
    }
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
   * Render Polygon và Centroid Dot trực tiếp bằng Leaflet Canvas Renderer (0 DOM Element)
   */
  renderPanelPolygon(panelData) {
    const latlngs = panelData.corners_pixel.map(p => [-p.y, p.x]);
    const centroidLatLng = [-panelData.centroid_pixel.y, panelData.centroid_pixel.x];

    // Đa giác viền tấm PV
    const polygon = L.polygon(latlngs, {
      color: '#f59e0b',
      weight: 2,
      fillColor: '#f59e0b',
      fillOpacity: 0.22,
      className: 'pv-panel-polygon',
      renderer: this.canvasRenderer
    }).addTo(this.pvLayerGroup);

    polygon.bindTooltip(`<b>${panelData.id}</b>`, {
      permanent: false,
      direction: 'center',
      className: 'pv-id-tooltip'
    });

    // Bắt sự kiện click vào polygon để kích hoạt chế độ chọn/sửa
    polygon.on('click', (e) => {
      L.DomEvent.stopPropagation(e);
      if (!this.isDrawMode) {
        this.selectPanel(panelData.id);
      }
    });

    // Điểm tâm Centroid dạng chấm Canvas nhẹ nhàng
    const centroidDot = L.circleMarker(centroidLatLng, {
      radius: 2.5,
      color: '#ef4444',
      fillColor: '#ef4444',
      fillOpacity: 0.85,
      weight: 1,
      renderer: this.canvasRenderer
    }).addTo(this.pvLayerGroup);

    centroidDot.on('click', (e) => {
      L.DomEvent.stopPropagation(e);
      if (!this.isDrawMode) {
        this.selectPanel(panelData.id);
      }
    });

    panelData.polygon = polygon;
    panelData.centroidDot = centroidDot;
  }

  /**
   * Chọn một tấm PV để chỉnh sửa:
   * - Hiển thị 4 góc kéo và tâm kéo TRÊN ĐÚNG TẤM NÀY (Single Active Editor)
   * - Highlight viền màu xanh Cyan nổi bật
   */
  selectPanel(panelId, shouldPan = false) {
    if (this.selectedPanelId === panelId) {
      if (shouldPan) this.focusPanel(panelId);
      return;
    }

    this.deselectPanel();

    const p = this.panels.find(x => x.id === panelId);
    if (!p) return;

    this.selectedPanelId = panelId;

    // Highlight polygon đang chọn
    if (p.polygon) {
      p.polygon.setStyle({
        color: '#06b6d4',
        weight: 3,
        fillColor: '#06b6d4',
        fillOpacity: 0.35
      });
    }

    // Gắn bộ 5 điểm kéo điều khiển vào tấm này
    this.attachActiveHandles(p);

    // Đồng bộ card đang active trong sidebar
    this.highlightSidebarCard(panelId);

    if (shouldPan) {
      this.focusPanel(panelId);
    }
  }

  /**
   * Bỏ chọn tấm pin hiện tại, ẩn bộ điểm kéo và trả về màu vàng tiêu chuẩn
   */
  deselectPanel() {
    if (this.selectedPanelId) {
      const prev = this.panels.find(x => x.id === this.selectedPanelId);
      if (prev && prev.polygon) {
        prev.polygon.setStyle({
          color: '#f59e0b',
          weight: 2,
          fillColor: '#f59e0b',
          fillOpacity: 0.22
        });
      }
      this.removeActiveHandles();
      this.selectedPanelId = null;
      document.querySelectorAll('.pv-item-card.active-selected').forEach(el => el.classList.remove('active-selected'));
    }
  }

  /**
   * Gắn bộ điều khiển kéo thả (4 góc + 1 tâm) cho tấm pin đang chọn
   */
  attachActiveHandles(panelData) {
    this.removeActiveHandles();

    const centroidLatLng = [-panelData.centroid_pixel.y, panelData.centroid_pixel.x];

    // 1. Điểm tâm Centroid Draggable
    const centroidIcon = L.divIcon({
      className: 'centroid-div-icon',
      html: `<div class="centroid-marker active" title="Kéo để di chuyển cả tấm ${panelData.id}">⌖</div>`,
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    });

    const centroidMarker = L.marker(centroidLatLng, {
      icon: centroidIcon,
      draggable: true,
      zIndexOffset: 1000
    }).addTo(this.pvLayerGroup);

    // 2. 4 Điểm góc kéo Draggable
    const cornerMarkers = panelData.corners_pixel.map((cp, idx) => {
      const cornerIcon = L.divIcon({
        className: 'corner-div-icon',
        html: `<div class="corner-handle" title="Góc ${cp.index}: X=${cp.x}, Y=${cp.y}">${cp.index}</div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
      });

      const m = L.marker([-cp.y, cp.x], {
        icon: cornerIcon,
        draggable: true,
        zIndexOffset: 1000
      }).addTo(this.pvLayerGroup);

      // Kéo góc để vi chỉnh tọa độ
      m.on('drag', () => {
        const newCol = Math.round(m.getLatLng().lng);
        const newRow = Math.round(-m.getLatLng().lat);
        panelData.corners_pixel[idx].x = newCol;
        panelData.corners_pixel[idx].y = newRow;
        panelData.corners_geo[idx] = this.pixelToGeo(newCol, newRow);

        // Cập nhật lại polygon
        const updatedLatLngs = panelData.corners_pixel.map(pt => [-pt.y, pt.x]);
        if (panelData.polygon) panelData.polygon.setLatLngs(updatedLatLngs);

        // Tự động tính toán lại Centroid
        const cX = Math.round((panelData.corners_pixel[0].x + panelData.corners_pixel[1].x + panelData.corners_pixel[2].x + panelData.corners_pixel[3].x) / 4);
        const cY = Math.round((panelData.corners_pixel[0].y + panelData.corners_pixel[1].y + panelData.corners_pixel[2].y + panelData.corners_pixel[3].y) / 4);
        panelData.centroid_pixel = { x: cX, y: cY };
        panelData.centroid_geo = this.pixelToGeo(cX, cY);

        centroidMarker.setLatLng([-cY, cX]);
        if (panelData.centroidDot) panelData.centroidDot.setLatLng([-cY, cX]);
      });

      m.on('dragend', () => {
        this.updateSinglePanelCardUI(panelData);
      });

      return m;
    });

    // Kéo Centroid -> Di chuyển cả tấm pin
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

      const updatedLatLngs = panelData.corners_pixel.map(pt => [-pt.y, pt.x]);
      if (panelData.polygon) panelData.polygon.setLatLngs(updatedLatLngs);

      const cX = Math.round(curPos.lng);
      const cY = Math.round(-curPos.lat);
      panelData.centroid_pixel = { x: cX, y: cY };
      panelData.centroid_geo = this.pixelToGeo(cX, cY);
      if (panelData.centroidDot) panelData.centroidDot.setLatLng([-cY, cX]);
    });

    centroidMarker.on('dragend', () => {
      this.updateSinglePanelCardUI(panelData);
    });

    this.activeHandles = { centroidMarker, cornerMarkers };
  }

  removeActiveHandles() {
    if (this.activeHandles) {
      if (this.activeHandles.centroidMarker) {
        this.pvLayerGroup.removeLayer(this.activeHandles.centroidMarker);
      }
      if (this.activeHandles.cornerMarkers) {
        this.activeHandles.cornerMarkers.forEach(m => this.pvLayerGroup.removeLayer(m));
      }
      this.activeHandles = null;
    }
  }

  /**
   * Xóa một tấm pin cụ thể
   */
  deletePanel(id) {
    const idx = this.panels.findIndex(p => p.id === id);
    if (idx !== -1) {
      const p = this.panels[idx];
      if (this.selectedPanelId === id) {
        this.deselectPanel();
      }
      if (p.polygon) {
        this.pvLayerGroup.removeLayer(p.polygon);
      }
      if (p.centroidDot) {
        this.pvLayerGroup.removeLayer(p.centroidDot);
      }
      this.panels.splice(idx, 1);

      // Nếu xóa hết sạch, reset ID về 1
      if (this.panels.length === 0) {
        this.nextPanelId = 1;
      }

      // Điều chỉnh phân trang nếu cần
      const filtered = this.getFilteredPanels();
      const totalPages = Math.max(1, Math.ceil(filtered.length / this.pageSize));
      if (this.currentPage > totalPages) {
        this.currentPage = totalPages;
      }

      this.updatePanelListUI();
    }
  }

  /**
   * Xóa toàn bộ tất cả tấm PV trên bản đồ:
   * - Thu dọn toàn bộ layer trong 1 thao tác duy nhất
   * - RESET BỘ ĐẾM ID VỀ 1
   * - Làm sạch thanh tìm kiếm và reset trang về 1
   */
  clearAll() {
    this.deselectPanel();
    this.pvLayerGroup.clearLayers();
    this.panels = [];
    this.nextPanelId = 1; // RESET VỀ 1 CHUẨN XÁC

    this.searchQuery = '';
    this.currentPage = 1;

    const searchInput = document.getElementById('pvSearchInput');
    if (searchInput) searchInput.value = '';
    const btnClearSearch = document.getElementById('btnClearPVSearch');
    if (btnClearSearch) btnClearSearch.style.display = 'none';

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
      this.map.fitBounds(bounds, { padding: [80, 80], maxZoom: 3 });
      this.selectPanel(id, false);
      if (p.polygon) {
        p.polygon.openTooltip();
      }
    }
  }

  getFilteredPanels() {
    if (!this.searchQuery) return this.panels;
    const q = this.searchQuery.toLowerCase();
    return this.panels.filter(p => String(p.id).toLowerCase().includes(q));
  }

  /**
   * Cập nhật thông tin nhanh cho 1 card đơn lẻ mà không render lại toàn bộ DOM Sidebar
   */
  updateSinglePanelCardUI(panelData) {
    const card = document.getElementById(`card_${panelData.id}`);
    if (!card) return;

    const pts = panelData.corners_pixel;
    const wEst = Math.round(Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
    const hEst = Math.round(Math.hypot(pts[2].x - pts[1].x, pts[2].y - pts[1].y));

    const dimEl = card.querySelector('.pv-dim-tag');
    if (dimEl) dimEl.innerText = `${wEst}x${hEst}px`;

    const cEl = card.querySelector('.pv-centroid-val');
    if (cEl) cEl.innerText = `⌖ (${panelData.centroid_pixel.x}, ${panelData.centroid_pixel.y})`;

    let geoText = '';
    if (panelData.centroid_geo.lat !== undefined) {
      geoText = `Lat: ${panelData.centroid_geo.lat.toFixed(6)}, Lon: ${panelData.centroid_geo.lon.toFixed(6)}`;
    } else if (panelData.centroid_geo.northing !== undefined) {
      geoText = `E: ${panelData.centroid_geo.easting}, N: ${panelData.centroid_geo.northing}`;
    } else {
      geoText = `(${panelData.centroid_pixel.x}, ${panelData.centroid_pixel.y})`;
    }
    const geoEl = card.querySelector('.geo-val-text');
    if (geoEl) geoEl.innerText = geoText;

    const cornersEl = card.querySelector('.corners-val-text');
    if (cornersEl) {
      cornersEl.innerText = `1: (${pts[0].x}, ${pts[0].y}) | 2: (${pts[1].x}, ${pts[1].y}) | 3: (${pts[2].x}, ${pts[2].y}) | 4: (${pts[3].x}, ${pts[3].y})`;
    }
  }

  /**
   * Highlight và cuộn tới card trong danh sách Sidebar
   */
  highlightSidebarCard(panelId) {
    document.querySelectorAll('.pv-item-card.active-selected').forEach(el => el.classList.remove('active-selected'));

    const existingCard = document.getElementById(`card_${panelId}`);
    if (existingCard) {
      existingCard.classList.add('active-selected');
      if (typeof existingCard.scrollIntoView === 'function') {
        existingCard.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    } else {
      // Nếu card nằm ở trang khác, chuyển trang tới trang chứa card đó
      const filtered = this.getFilteredPanels();
      const idx = filtered.findIndex(p => p.id === panelId);
      if (idx !== -1) {
        this.currentPage = Math.floor(idx / this.pageSize) + 1;
        this.updatePanelListUI();
        const newCard = document.getElementById(`card_${panelId}`);
        if (newCard) {
          newCard.classList.add('active-selected');
          if (typeof newCard.scrollIntoView === 'function') {
            newCard.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          }
        }
      }
    }
  }

  /**
   * Cập nhật danh sách tấm PV ra Sidebar với phân trang siêu mượt
   */
  updatePanelListUI() {
    const countBadge = document.getElementById('pvCountBadge');
    if (countBadge) countBadge.innerText = `${this.panels.length} tấm`;

    const tabPVBadge = document.getElementById('tabPVBadge');
    if (tabPVBadge) tabPVBadge.innerText = this.panels.length;

    const btnClearAll = document.getElementById('btnClearAllPV');
    if (btnClearAll) {
      btnClearAll.style.display = this.panels.length > 0 ? 'block' : 'none';
    }

    const searchBox = document.getElementById('pvSearchBox');
    if (searchBox) {
      searchBox.style.display = this.panels.length > 0 ? 'block' : 'none';
    }

    const listContainer = document.getElementById('pvListContainer');
    if (!listContainer) return;

    if (this.panels.length === 0) {
      listContainer.innerHTML = '<div class="empty-hint"><i class="fa-regular fa-clone"></i> Chưa có tấm PV nào. Bấm <b>"Bật Đánh Tấm PV"</b> ở trên rồi click vào ảnh để dập tấm pin.</div>';
      const pagination = document.getElementById('pvPagination');
      if (pagination) pagination.style.display = 'none';
      return;
    }

    const filtered = this.getFilteredPanels();
    const totalFiltered = filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalFiltered / this.pageSize));

    if (this.currentPage > totalPages) {
      this.currentPage = totalPages;
    }
    if (this.currentPage < 1) {
      this.currentPage = 1;
    }

    const startIndex = (this.currentPage - 1) * this.pageSize;
    const endIndex = Math.min(startIndex + this.pageSize, totalFiltered);
    const pageItems = filtered.slice(startIndex, endIndex);

    // Cập nhật thanh phân trang
    const pagination = document.getElementById('pvPagination');
    const pageInfo = document.getElementById('pvPageInfo');
    const btnPrev = document.getElementById('btnPVPrevPage');
    const btnNext = document.getElementById('btnPVNextPage');

    if (pagination) {
      pagination.style.display = (totalPages > 1 || this.searchQuery) ? 'flex' : 'none';
    }
    if (pageInfo) {
      pageInfo.innerText = `Trang ${this.currentPage}/${totalPages} (${totalFiltered} tấm)`;
    }
    if (btnPrev) btnPrev.disabled = this.currentPage <= 1;
    if (btnNext) btnNext.disabled = this.currentPage >= totalPages;

    if (pageItems.length === 0) {
      listContainer.innerHTML = '<div class="empty-hint"><i class="fa-solid fa-filter-circle-xmark"></i> Không tìm thấy tấm PV nào với từ khóa này.</div>';
      return;
    }

    // Render HTML các card của trang hiện tại
    let html = '';
    pageItems.forEach(p => {
      const isSelected = p.id === this.selectedPanelId;
      const pts = p.corners_pixel;
      const wEst = Math.round(Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
      const hEst = Math.round(Math.hypot(pts[2].x - pts[1].x, pts[2].y - pts[1].y));

      const geoText = p.centroid_geo.lat 
        ? `Lat: ${p.centroid_geo.lat.toFixed(6)}, Lon: ${p.centroid_geo.lon.toFixed(6)}`
        : `E: ${p.centroid_geo.easting || p.centroid_pixel.x}, N: ${p.centroid_geo.northing || p.centroid_pixel.y}`;

      html += `
        <div class="pv-item-card ${isSelected ? 'active-selected' : ''}" data-panel-id="${p.id}" id="card_${p.id}">
          <div class="pv-item-header">
            <div class="pv-item-title">
              <span class="pv-id-tag">${p.id}</span>
              <span class="pv-dim-tag">${wEst}x${hEst}px</span>
              <span class="pv-centroid-val">⌖ (${p.centroid_pixel.x}, ${p.centroid_pixel.y})</span>
            </div>
            <div class="pv-item-actions">
              <button class="btn-icon pick-btn" data-action="pick" data-id="${p.id}" title="Lấy kích thước tấm này làm khuôn mẫu"><i class="fa-solid fa-eye-dropper"></i></button>
              <button class="btn-icon scale-down-btn" data-action="scale-down" data-id="${p.id}" title="Thu nhỏ 10%"><i class="fa-solid fa-compress"></i></button>
              <button class="btn-icon scale-up-btn" data-action="scale-up" data-id="${p.id}" title="Phóng to 10%"><i class="fa-solid fa-expand"></i></button>
              <button class="btn-icon focus-btn" data-action="focus" data-id="${p.id}" title="Phóng to & Chỉnh sửa"><i class="fa-solid fa-crosshairs"></i></button>
              <button class="btn-icon delete-btn text-danger" data-action="delete" data-id="${p.id}" title="Xóa tấm này"><i class="fa-solid fa-trash-can"></i></button>
            </div>
          </div>
          <div class="pv-item-meta">
            <div class="meta-row">
              <span>Tọa độ địa lý tâm:</span>
              <span class="val geo-val-text">${geoText}</span>
            </div>
            <div class="meta-row corners-preview">
              <span>4 Góc:</span>
              <span class="val corners-val-text">1: (${pts[0].x}, ${pts[0].y}) | 2: (${pts[1].x}, ${pts[1].y}) | 3: (${pts[2].x}, ${pts[2].y}) | 4: (${pts[3].x}, ${pts[3].y})</span>
            </div>
          </div>
        </div>
      `;
    });

    listContainer.innerHTML = html;
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
   * Tối ưu hóa Gom nhóm (Batch processing) nạp hàng nghìn tấm trong tích tắc
   */
  importJSON(jsonString) {
    try {
      const data = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
      if (!data.panels || !Array.isArray(data.panels)) {
        throw new Error('Định dạng JSON không hợp lệ. Cần có trường "panels" là mảng.');
      }

      let importedCount = 0;
      // Nạp hàng loạt với cờ skipUIRefresh = true để không bị đơ trình duyệt
      data.panels.forEach(p => {
        if (p.corners_pixel && p.corners_pixel.length === 4) {
          const points = p.corners_pixel.map(c => ({
            col: c.x,
            row: c.y
          }));
          this.createPVPanelFromPoints(points, p.id, true);
          importedCount++;
        }
      });

      // Cập nhật giao diện đúng 1 lần duy nhất sau khi hoàn tất toàn bộ
      this.currentPage = 1;
      this.updatePanelListUI();
      alert(`Đã nạp thành công ${importedCount} tấm PV lên bản đồ!`);

      // Tự động fit bounds một lượt nhanh chóng
      if (this.panels.length > 0) {
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        this.panels.forEach(p => {
          p.corners_pixel.forEach(pt => {
            if (pt.x < minX) minX = pt.x;
            if (pt.x > maxX) maxX = pt.x;
            if (pt.y < minY) minY = pt.y;
            if (pt.y > maxY) maxY = pt.y;
          });
        });
        if (minX !== Infinity) {
          this.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [40, 40] });
        }
      }
    } catch (err) {
      alert(`Lỗi khi nhập JSON: ${err.message}`);
    }
  }
}

window.PVAnnotator = PVAnnotator;
