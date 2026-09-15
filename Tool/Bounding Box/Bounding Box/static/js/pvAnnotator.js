/**
 * pvAnnotator.js - Module Đánh Dấu Tấm PV (Chấm 4 Góc Tự Tính Tâm Centroid & Dập Khuôn)
 * Hỗ trợ ĐẦY ĐỦ trên CẢ Ortho To và Ortho Vùng
 * - Cơ chế Chấm 4 Góc: Click lần lượt 4 góc của tấm pin PV, hệ thống tự động tính toán
 *   tọa độ điểm tâm Centroid ở giữa (Pixel, WGS 84 / UTM zone 49N EPSG:32649, và GPS WGS84 EPSG:4326).
 * - Cả 4 góc và tâm Centroid đều được hiển thị trực quan và lưu trữ đầy đủ vào JSON.
 * - Cơ chế Dập Khuôn PV (1-click Stamp) với cấu hình kích thước WxH, hướng và góc xoay.
 * - Bộ vi chỉnh Active Editor: Kéo tâm để di chuyển toàn bộ tấm pin, kéo góc để tinh chỉnh và tự động cập nhật lại tâm.
 * - Độc lập layer group cho từng ảnh mục tiêu (Ortho To / Ortho Vùng).
 * - Xuất và Nhập JSON tương thích 100% cho từng ảnh mục tiêu.
 */
class PVAnnotator {
  constructor(orthoViewer) {
    this.viewer = orthoViewer;
    this.map = orthoViewer.map;
    this.isDrawMode = false;
    this.subMode = 'manual'; // 'manual' (Chấm góc tự tính tâm), 'strip' (Dải pin hàng trên - dưới), 'stamp' (Khuôn mẫu PV)
    this.activeTarget = 'big'; // 'big' (Ortho To) hoặc 'sub' (Ortho Vùng)
    this.isAutoChainEnabled = false; // Tự động hoàn tất khi có 2 điểm khớp với cạnh tấm liền kề

    // Cấu hình khuôn mẫu nếu dùng dập nhanh PV
    this.stampConfig = {
      width: 60,
      height: 30,
      orientation: 'horizontal',
      angleDeg: 0
    };

    this.panels = []; // Danh sách toàn bộ các annotation PV
    this.nextPanelId = 1;

    // Quản lý tấm PV đang được chọn để chỉnh sửa
    this.selectedPanelId = null;
    this.activeHandles = null; // { centroidMarker, handleMarkers }

    // Canvas Renderer tối ưu hiệu năng
    this.canvasRenderer = L.canvas({ padding: 0.5 });

    // Các góc tạm thời khi đang chấm [Góc 1, Góc 2, Góc 3, Góc 4]
    this.currentDraftPoints = [];
    this.draftMarkers = [];
    this.draftLines = null;

    // Quản lý Chế độ Chấm Dải Pin (Hàng Trên - Hàng Dưới)
    this.stripStep = 'top'; // 'top' hoặc 'bottom'
    this.stripPointsTop = [];
    this.stripPointsBot = [];
    this.stripMarkersTop = [];
    this.stripMarkersBot = [];
    this.stripLineTop = null;
    this.stripLineBot = null;

    // Layer preview Ghost Box khi dùng stamp
    this.ghostLayer = null;
    this.ghostCenterMarker = null;

    // Hai Layer Group riêng biệt cho Ortho To và Ortho Vùng
    this.pvLayerGroupBig = L.layerGroup().addTo(this.map);
    this.pvLayerGroupSub = L.layerGroup();

    // Trạng thái phân trang và tìm kiếm trong Sidebar
    this.currentPage = 1;
    this.pageSize = 20;
    this.searchQuery = '';

    this.initEvents();
    this.initListEvents();
  }

  getActiveLayerGroup() {
    return this.activeTarget === 'sub' ? this.pvLayerGroupSub : this.pvLayerGroupBig;
  }

  getActiveInfo() {
    return this.activeTarget === 'sub' ? this.viewer.subInfo : this.viewer.bigInfo;
  }

  setTarget(target) {
    if (this.activeTarget === target) return;
    this.deselectPanel();
    this.cancelDraft();
    this.activeTarget = target;

    // Chuyển đổi layer group trên bản đồ
    if (target === 'sub') {
      if (this.map.hasLayer(this.pvLayerGroupBig)) this.map.removeLayer(this.pvLayerGroupBig);
      if (!this.map.hasLayer(this.pvLayerGroupSub)) this.map.addLayer(this.pvLayerGroupSub);
    } else {
      if (this.map.hasLayer(this.pvLayerGroupSub)) this.map.removeLayer(this.pvLayerGroupSub);
      if (!this.map.hasLayer(this.pvLayerGroupBig)) this.map.addLayer(this.pvLayerGroupBig);
    }

    // Đồng bộ nút chọn ảnh mục tiêu
    const btnBig = document.getElementById('btnTargetBig');
    const btnSub = document.getElementById('btnTargetSub');
    if (btnBig) btnBig.classList.toggle('active', target === 'big');
    if (btnSub) btnSub.classList.toggle('active', target === 'sub');

    this.currentPage = 1;
    this.updatePanelListUI();
    this.updateGuideText();
    this.updateStartButtonUI();
  }

  initEvents() {
    // 1. Click trên bản đồ
    this.map.on('click', (e) => {
      if (!this.isDrawMode) {
        this.deselectPanel();
        return;
      }
      const activeInfo = this.getActiveInfo();
      if (!activeInfo) {
        alert(this.activeTarget === 'sub' ? 'Vui lòng nạp Ortho Vùng trước khi đánh dấu!' : 'Vui lòng nạp Ortho To trước khi đánh dấu!');
        this.setMode(false);
        return;
      }

      if (this.subMode === 'stamp') {
        this.stampPanelAt(e.latlng);
      } else if (this.subMode === 'strip') {
        this.handleStripClick(e);
      } else {
        this.handleManualClick(e);
      }
    });

    // 1.1 Click đúp trên bản đồ để hoàn tất sớm nếu đã chấm >= 2 góc
    this.map.on('dblclick', (e) => {
      if (this.isDrawMode && this.subMode === 'manual' && this.currentDraftPoints.length >= 2) {
        L.DomEvent.stopPropagation(e);
        this.finishDraft();
      }
    });

    // Bắt sự kiện click vào các nút hành động trên floating guide badge
    const guideEl = document.getElementById('drawGuideBadge');
    if (guideEl) {
      guideEl.addEventListener('click', (e) => {
        const btnAction = e.target.closest('[data-guide-action]');
        if (!btnAction) return;
        e.stopPropagation();
        const action = btnAction.dataset.guideAction;
        if (action === 'switch-row') {
          this.toggleStripStep();
        } else if (action === 'synthesize-strip') {
          this.synthesizeStripPanels();
        } else if (action === 'finish-draft') {
          this.finishDraft();
        } else if (action === 'toggle-chain') {
          this.toggleAutoChain();
        }
      });
    }

    // 2. Di chuột trên bản đồ để vẽ Ghost Box (nếu ở chế độ stamp)
    this.map.on('mousemove', (e) => {
      if (!this.isDrawMode || this.subMode !== 'stamp' || !this.getActiveInfo()) {
        this.hideGhostPreview();
        return;
      }
      this.updateGhostPreview(e.latlng);
    });

    this.map.on('mouseout', () => {
      this.hideGhostPreview();
    });

    // 3. Phím tắt tiện lợi:
    // - Esc: Hủy lượt chấm dở / Bỏ chọn / Tắt chế độ chấm
    // - Ctrl+Z: Undo điểm vừa chấm hoặc tấm vừa tạo
    // - Delete / Backspace: Xóa tấm đang chọn
    // - Tab: Chuyển đổi giữa Chấm góc, Dải pin và Dập khuôn PV
    // - Space: Đổi hàng trên / dưới khi đang ở chế độ Dải pin
    // - Enter: Hoàn tất dải pin hoặc hoàn tất tấm PV từ 2 góc
    // - R: Đảo chiều tấm khuôn (Ngang / Dọc)
    // - [ / ]: Thu nhỏ / Phóng to khuôn mẫu 10%
    document.addEventListener('keydown', (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
        return;
      }

      if (e.key === 'Tab') {
        e.preventDefault();
        const modes = ['manual', 'strip', 'stamp'];
        const nextIdx = (modes.indexOf(this.subMode) + 1) % modes.length;
        this.setSubMode(modes[nextIdx]);
      } else if (e.key === ' ' || e.code === 'Space') {
        if (this.isDrawMode && this.subMode === 'strip') {
          e.preventDefault();
          this.toggleStripStep();
        }
      } else if (e.key === 'Escape') {
        if (this.subMode === 'manual' && this.currentDraftPoints.length > 0) {
          this.cancelDraft();
        } else if (this.subMode === 'strip' && (this.stripPointsTop.length > 0 || this.stripPointsBot.length > 0)) {
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
      } else if (e.key === 'Enter') {
        if (this.isDrawMode) {
          if (this.subMode === 'strip') {
            e.preventDefault();
            this.synthesizeStripPanels();
          } else if (this.subMode === 'manual' && this.currentDraftPoints.length >= 2) {
            e.preventDefault();
            this.finishDraft();
          }
        }
      } else if (e.key === 'r' || e.key === 'R') {
        if (this.isDrawMode && this.subMode === 'stamp') {
          e.preventDefault();
          this.toggleOrientation();
        }
      } else if (e.key === '[' || e.key === '{') {
        if (this.isDrawMode && this.subMode === 'stamp') {
          e.preventDefault();
          this.scaleStamp(0.9);
        }
      } else if (e.key === ']' || e.key === '}') {
        if (this.isDrawMode && this.subMode === 'stamp') {
          e.preventDefault();
          this.scaleStamp(1.1);
        }
      }
    });
  }

  initListEvents() {
    const listContainer = document.getElementById('pvListContainer');
    if (listContainer) {
      listContainer.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (btn) {
          e.stopPropagation();
          const action = btn.dataset.action;
          const id = btn.dataset.id;
          if (action === 'copy') this.copyCoordinates(id, btn);
          else if (action === 'focus') this.focusPanel(id);
          else if (action === 'delete') this.deletePanel(id);
          else if (action === 'pick') this.pickSizeFromPanel(id);
          else if (action === 'scale-down') this.scalePanel(id, 0.9);
          else if (action === 'scale-up') this.scalePanel(id, 1.1);
          return;
        }

        const card = e.target.closest('.pv-item-card');
        if (card && card.dataset.panelId) {
          this.selectPanel(card.dataset.panelId, true);
        }
      });
    }

    // Phân trang
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

    // Ô tìm kiếm nhanh
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
      if (container) {
        container.style.cursor = 'crosshair';
        container.classList.add('drawing-active');
      }
      this.updateGuideText();
      if (guideEl) {
        guideEl.style.display = 'flex';
      }
      this.syncStampConfigToUI();
    } else {
      if (container) {
        container.style.cursor = '';
        container.classList.remove('drawing-active');
      }
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
    const btnStrip = document.getElementById('btnSubModeStrip');
    const stampBox = document.getElementById('stampControlsBox');
    const tbStampGroup = document.getElementById('tbStampGroup');

    if (btnStamp) btnStamp.classList.toggle('active', subMode === 'stamp');
    if (btnManual) btnManual.classList.toggle('active', subMode === 'manual');
    if (btnStrip) btnStrip.classList.toggle('active', subMode === 'strip');
    if (stampBox) stampBox.style.display = subMode === 'stamp' ? 'block' : 'none';
    if (tbStampGroup) tbStampGroup.style.display = subMode === 'stamp' ? 'flex' : 'none';

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

  toggleAutoChain(enabled) {
    this.isAutoChainEnabled = enabled ?? !this.isAutoChainEnabled;
    const btn = document.getElementById('btnToggleChain');
    if (btn) {
      btn.classList.toggle('active', this.isAutoChainEnabled);
      btn.title = this.isAutoChainEnabled ? 'Đang BẬT chế độ Nối 2 Click' : 'Đang TẮT chế độ Nối 2 Click';
    }
    this.updateGuideText();
  }

  updateStartButtonUI() {
    const btnStart = document.getElementById('btnStartDrawPV');
    if (!btnStart) return;
    const targetLabel = this.activeTarget === 'sub' ? ' (Ortho Vùng)' : '';
    if (this.isDrawMode) {
      let modeText = 'Chấm 4 Góc PV';
      if (this.subMode === 'stamp') modeText = 'Dập Khuôn PV';
      else if (this.subMode === 'strip') modeText = 'Chấm Dải Pin';
      btnStart.innerHTML = `<i class="fa-solid fa-stop"></i> Đang ${modeText}${targetLabel} (Bấm để Dừng)`;
      btnStart.className = 'btn btn-action btn-block active-drawing';
    } else {
      let modeText = 'Bật Chấm 4 Góc PV';
      if (this.subMode === 'stamp') modeText = 'Bật Dập Khuôn PV';
      else if (this.subMode === 'strip') modeText = 'Bật Chấm Dải Pin';
      btnStart.innerHTML = `<i class="fa-solid fa-draw-polygon"></i> ${modeText}${targetLabel}`;
      btnStart.className = 'btn btn-warning btn-block';
    }
  }

  updateGuideText() {
    const guideEl = document.getElementById('drawGuideBadge');
    if (!guideEl) return;

    const targetLabel = this.activeTarget === 'sub' ? ' [Ortho Vùng]' : ' [Ortho To]';

    if (this.subMode === 'stamp') {
      const orientText = this.stampConfig.orientation === 'horizontal' ? 'Ngang' : 'Dọc';
      guideEl.innerHTML = `<i class="fa-solid fa-stamp"></i> <b>Dập Khuôn PV${targetLabel}:</b> Click để đặt tấm PV <b>${this.stampConfig.width}x${this.stampConfig.height}px (${orientText})</b> | <b>Esc</b> thoát`;
    } else if (this.subMode === 'strip') {
      if (this.stripStep === 'top') {
        guideEl.innerHTML = `<i class="fa-solid fa-arrow-up-long" style="color:#06b6d4;"></i> <b>Chấm HÀNG TRÊN:</b> Đã có <b>${this.stripPointsTop.length} điểm</b>. <button class="badge-mini-btn" data-guide-action="switch-row">Sang Hàng Dưới [Space]</button> | Esc hủy`;
      } else {
        guideEl.innerHTML = `<i class="fa-solid fa-arrow-down-long" style="color:#10b981;"></i> <b>Chấm HÀNG DƯỚI:</b> Đã có <b>${this.stripPointsBot.length} điểm</b>. <button class="badge-mini-btn primary" data-guide-action="synthesize-strip">✨ Hợp Lực Dải Pin [Enter]</button> <button class="badge-mini-btn" data-guide-action="switch-row">[Space] Đổi hàng</button>`;
      }
    } else {
      const count = this.currentDraftPoints.length;
      const chainStatus = this.isAutoChainEnabled 
        ? `<button class="badge-mini-btn active" data-guide-action="toggle-chain" title="Đang BẬT tự nối 2 click"><i class="fa-solid fa-link"></i> Nối 2 Click: BẬT</button>`
        : `<button class="badge-mini-btn" data-guide-action="toggle-chain" title="Click để BẬT tự nối 2 click"><i class="fa-solid fa-link"></i> Nối 2 Click: TẮT</button>`;

      if (count === 0) {
        guideEl.innerHTML = `<i class="fa-solid fa-crosshairs"></i> Click <b>Góc 1</b> trên ảnh${targetLabel} (tự hút góc gần) ${chainStatus} | Esc hủy`;
      } else if (count === 1) {
        guideEl.innerHTML = `<i class="fa-solid fa-crosshairs"></i> Click <b>Góc 2</b>${targetLabel}... ${chainStatus}`;
      } else if (count === 2) {
        const match = this.findAdjacentMatchingEdge(this.currentDraftPoints[0], this.currentDraftPoints[1]);
        if (match) {
          guideEl.innerHTML = `<i class="fa-solid fa-link" style="color:#10b981;"></i> <b>Khớp cạnh [${match.panel.id}]!</b> <button class="badge-mini-btn primary" data-guide-action="finish-draft">✨ Tạo ngay tấm PV [Enter]</button> hoặc click tiếp góc 3`;
        } else {
          guideEl.innerHTML = `<i class="fa-solid fa-crosshairs"></i> Click <b>Góc 3</b> (hoặc ấn <b>Enter</b> tạo từ 2 góc đối diện)`;
        }
      } else if (count === 3) {
        guideEl.innerHTML = `<i class="fa-solid fa-crosshairs"></i> Click <b>Góc 4</b> để hoàn tất (hoặc ấn <b>Enter</b> tự suy ra góc 4)`;
      }
    }
  }

  /**
   * Tìm điểm góc của tấm pin liền kề gần nhất để tự động hút điểm (Snapping)
   */
  findSnapPoint(latlng, pixelRadius = 14) {
    const activePanels = this.panels.filter(p => (p.target || 'big') === this.activeTarget);
    let nearest = null;
    let minDist = Infinity;
    const clickPt = this.map.latLngToContainerPoint(latlng);

    for (const p of activePanels) {
      const corners = p.corners || p.corners_pixel;
      if (!corners) continue;
      for (const c of corners) {
        const px = c.pixel ? c.pixel.x : c.x;
        const py = c.pixel ? c.pixel.y : c.y;
        const cLatLng = L.latLng(-py, px);
        const cPt = this.map.latLngToContainerPoint(cLatLng);
        const dist = clickPt.distanceTo(cPt);
        if (dist <= pixelRadius && dist < minDist) {
          minDist = dist;
          nearest = { col: px, row: py, latlng: cLatLng, snapped: true };
        }
      }
    }
    return nearest;
  }

  /**
   * Hợp lực và sắp xếp 4 góc theo chiều kim đồng hồ quanh trọng tâm (Đông Tây Nam Bắc).
   * Bỏ hoàn toàn ràng buộc người dùng phải bấm 1-2-3-4 theo chu vi.
   */
  sortCornersClockwise(points) {
    const pts = points.map(p => ({
      col: Math.round(p.col ?? p.x),
      row: Math.round(p.row ?? p.y),
      raw: p
    }));
    const cx = pts.reduce((sum, p) => sum + p.col, 0) / pts.length;
    const cy = pts.reduce((sum, p) => sum + p.row, 0) / pts.length;

    pts.forEach(p => {
      p.angle = Math.atan2(p.row - cy, p.col - cx);
    });
    pts.sort((a, b) => a.angle - b.angle);

    // Tìm góc Tây Bắc (Top-Left, col + row nhỏ nhất) đưa lên index 0
    let minSum = Infinity;
    let tlIdx = 0;
    pts.forEach((p, idx) => {
      const sum = p.col + p.row;
      if (sum < minSum) {
        minSum = sum;
        tlIdx = idx;
      }
    });

    const ordered = [];
    for (let i = 0; i < pts.length; i++) {
      ordered.push(pts[(tlIdx + i) % pts.length]);
    }
    return ordered;
  }

  /**
   * Tìm cạnh của tấm pin đã có phù hợp nhất để tự động bắt cặp với 2 điểm mới chấm
   */
  findAdjacentMatchingEdge(p1, p2) {
    const activePanels = this.panels.filter(p => (p.target || 'big') === this.activeTarget);
    if (!activePanels.length) return null;

    const vNew = { x: p2.col - p1.col, y: p2.row - p1.row };
    const lenNew = Math.hypot(vNew.x, vNew.y);
    if (lenNew < 5) return null;

    let bestMatch = null;
    let minDiffScore = Infinity;

    for (const panel of activePanels) {
      const corners = panel.corners_pixel || panel.corners?.map(c => c.pixel || c);
      if (!corners || corners.length < 4) continue;

      for (let i = 0; i < 4; i++) {
        const eA = corners[i];
        const eB = corners[(i + 1) % 4];
        const vEdge = { x: eB.x - eA.x, y: eB.y - eA.y };
        const lenEdge = Math.hypot(vEdge.x, vEdge.y);
        if (lenEdge < 5) continue;

        const lenDiffRatio = Math.abs(lenNew - lenEdge) / Math.max(lenNew, lenEdge);
        if (lenDiffRatio > 0.40) continue;

        const dot = (vNew.x * vEdge.x + vNew.y * vEdge.y) / (lenNew * lenEdge);
        if (Math.abs(dot) < 0.80) continue;

        const originA = dot > 0 ? eA : eB;
        const originB = dot > 0 ? eB : eA;
        const d1 = { x: p1.col - originA.x, y: p1.row - originA.y };
        const d2 = { x: p2.col - originB.x, y: p2.row - originB.y };

        const perpDist = Math.abs(d1.x * vEdge.y - d1.y * vEdge.x) / lenEdge;
        if (perpDist < 5 || perpDist > lenEdge * 3.8) continue;

        const proj1 = (d1.x * vEdge.x + d1.y * vEdge.y) / lenEdge;
        const proj2 = (d2.x * vEdge.x + d2.y * vEdge.y) / lenEdge;
        if (Math.abs(proj1) > lenEdge * 0.6 || Math.abs(proj2) > lenEdge * 0.6) continue;

        const score = lenDiffRatio * 50 + (1 - Math.abs(dot)) * 100 + Math.abs(proj1) * 0.5 + Math.abs(proj2) * 0.5 + perpDist * 0.2;

        if (score < minDiffScore) {
          minDiffScore = score;
          const candidate = [
            { col: originA.x, row: originA.y },
            { col: originB.x, row: originB.y },
            { col: p2.col, row: p2.row },
            { col: p1.col, row: p1.row }
          ];
          bestMatch = { panel, edge: [originA, originB], corners: candidate, perpDist, score };
        }
      }
    }
    return bestMatch;
  }

  /**
   * Chế độ chấm góc thủ công trên ảnh mục tiêu hiện tại (Ortho To hoặc Ortho Vùng).
   * Hỗ trợ tự động hút điểm (Snapping), tự tính tâm centroid.
   */
  handleManualClick(e) {
    const activeInfo = this.getActiveInfo();
    if (!activeInfo) return;

    // Kiểm tra hút điểm vào góc của tấm liền kề đã có (bán kính 14px màn hình)
    const snap = this.findSnapPoint(e.latlng, 14);
    const col = snap ? snap.col : Math.round(e.latlng.lng);
    const row = snap ? snap.row : Math.round(-e.latlng.lat);
    const clickLatLng = snap ? snap.latlng : e.latlng;

    if (col < 0 || col > activeInfo.width || row < 0 || row > activeInfo.height) {
      return;
    }

    const pt = { col, row, latlng: clickLatLng };
    this.currentDraftPoints.push(pt);

    const cornerIndex = this.currentDraftPoints.length;
    const targetGroup = this.getActiveLayerGroup();

    const marker = L.circleMarker(clickLatLng, {
      radius: 6,
      color: this.activeTarget === 'sub' ? '#10b981' : '#f59e0b',
      fillColor: snap ? '#ffffff' : (this.activeTarget === 'sub' ? '#10b981' : '#f59e0b'),
      fillOpacity: 1,
      weight: 2
    }).addTo(targetGroup);

    marker.bindTooltip(`Góc ${cornerIndex}${snap ? ' 🧲 (Khớp góc)' : ''}`, { permanent: true, direction: 'top', className: 'draft-corner-badge' });
    this.draftMarkers.push(marker);

    // Khi đã có 2 điểm: Kiểm tra tự động bắt cạnh tấm liền kề
    if (this.currentDraftPoints.length === 2) {
      const match = this.findAdjacentMatchingEdge(this.currentDraftPoints[0], this.currentDraftPoints[1]);
      if (match) {
        // Nếu bật chế độ Nối Nhanh 2 Điểm (Auto-Chain): tự hoàn tất ngay không cần chờ click thêm
        if (this.isAutoChainEnabled) {
          this.createPVPanelFromPoints(match.corners);
          this.cleanupDraftMarkers();
          this.currentDraftPoints = [];
          this.updateGuideText();
          return;
        }

        // Vẽ gợi ý khung nối tiếp với tấm liền kề
        const latlngs = [
          match.corners[0],
          match.corners[1],
          match.corners[2],
          match.corners[3],
          match.corners[0]
        ].map(c => L.latLng(-c.row, c.col));
        if (this.draftLines) {
          this.draftLines.setLatLngs(latlngs);
        } else {
          this.draftLines = L.polyline(latlngs, {
            color: '#10b981',
            weight: 2,
            dashArray: '4, 4'
          }).addTo(targetGroup);
        }
      } else {
        const latlngs = this.currentDraftPoints.map(p => p.latlng);
        if (this.draftLines) {
          this.draftLines.setLatLngs(latlngs);
        } else {
          this.draftLines = L.polyline(latlngs, {
            color: this.activeTarget === 'sub' ? '#10b981' : '#f59e0b',
            weight: 2,
            dashArray: '4, 4'
          }).addTo(targetGroup);
        }
      }
    } else if (this.currentDraftPoints.length > 2) {
      const latlngs = this.currentDraftPoints.map(p => p.latlng);
      if (this.draftLines) {
        this.draftLines.setLatLngs(latlngs);
      } else {
        this.draftLines = L.polyline(latlngs, {
          color: this.activeTarget === 'sub' ? '#10b981' : '#f59e0b',
          weight: 2,
          dashArray: '4, 4'
        }).addTo(targetGroup);
      }
    }

    this.updateGuideText();

    // Khi đã click đủ 4 góc -> Tự động hoàn tất tấm PV & tính toán điểm tâm centroid
    if (this.currentDraftPoints.length === 4) {
      this.finishDraft();
    }
  }

  /**
   * Chấm điểm góc theo dải pin (Hàng Trên - Hàng Dưới)
   */
  handleStripClick(e) {
    const activeInfo = this.getActiveInfo();
    if (!activeInfo) return;

    const snap = this.findSnapPoint(e.latlng, 14);
    const col = snap ? snap.col : Math.round(e.latlng.lng);
    const row = snap ? snap.row : Math.round(-e.latlng.lat);
    const clickLatLng = snap ? snap.latlng : e.latlng;

    if (col < 0 || col > activeInfo.width || row < 0 || row > activeInfo.height) return;

    const pt = { col, row, latlng: clickLatLng };
    const targetGroup = this.getActiveLayerGroup();

    if (this.stripStep === 'top') {
      this.stripPointsTop.push(pt);
      const idx = this.stripPointsTop.length;
      const marker = L.circleMarker(clickLatLng, {
        radius: 6,
        color: '#06b6d4',
        fillColor: '#ffffff',
        fillOpacity: 1,
        weight: 2
      }).addTo(targetGroup);
      marker.bindTooltip(`T${idx}`, { permanent: true, direction: 'top', className: 'draft-corner-badge' });
      this.stripMarkersTop.push(marker);

      if (this.stripPointsTop.length > 1) {
        const latlngs = this.stripPointsTop.map(p => p.latlng);
        if (this.stripLineTop) {
          this.stripLineTop.setLatLngs(latlngs);
        } else {
          this.stripLineTop = L.polyline(latlngs, { color: '#06b6d4', weight: 2, dashArray: '5, 5' }).addTo(targetGroup);
        }
      }
    } else {
      this.stripPointsBot.push(pt);
      const idx = this.stripPointsBot.length;
      const marker = L.circleMarker(clickLatLng, {
        radius: 6,
        color: '#10b981',
        fillColor: '#ffffff',
        fillOpacity: 1,
        weight: 2
      }).addTo(targetGroup);
      marker.bindTooltip(`B${idx}`, { permanent: true, direction: 'bottom', className: 'draft-corner-badge' });
      this.stripMarkersBot.push(marker);

      if (this.stripPointsBot.length > 1) {
        const latlngs = this.stripPointsBot.map(p => p.latlng);
        if (this.stripLineBot) {
          this.stripLineBot.setLatLngs(latlngs);
        } else {
          this.stripLineBot = L.polyline(latlngs, { color: '#10b981', weight: 2, dashArray: '5, 5' }).addTo(targetGroup);
        }
      }
    }

    this.updateGuideText();
  }

  toggleStripStep() {
    this.stripStep = this.stripStep === 'top' ? 'bottom' : 'top';
    this.updateGuideText();
  }

  /**
   * Hợp lực các điểm hàng trên & hàng dưới thành toàn bộ dải tấm pin PV
   */
  synthesizeStripPanels() {
    if (this.stripPointsTop.length < 2) {
      if (typeof alert !== 'undefined') alert('Vui lòng chấm ít nhất 2 điểm ở Hàng Trên của dải pin!');
      return;
    }
    if (this.stripPointsBot.length < 2) {
      if (typeof alert !== 'undefined') alert('Vui lòng chấm ít nhất 2 điểm ở Hàng Dưới (hoặc 2 điểm đầu-cuối của dải pin)!');
      return;
    }

    // 1. Sắp xếp các điểm hàng trên dọc theo dải pin (từ Tây sang Đông / x tăng dần)
    const sortedTop = [...this.stripPointsTop].sort((a, b) => (a.col + a.row) - (b.col + b.row));
    // 2. Sắp xếp các điểm hàng dưới dọc theo dải pin
    const sortedBot = [...this.stripPointsBot].sort((a, b) => (a.col + a.row) - (b.col + b.row));

    let createdCount = 0;

    // Trường hợp 1: Số điểm hàng trên = Số điểm hàng dưới
    if (sortedTop.length === sortedBot.length) {
      for (let i = 0; i < sortedTop.length - 1; i++) {
        const rawCorners = [
          sortedTop[i],
          sortedTop[i + 1],
          sortedBot[i + 1],
          sortedBot[i]
        ];
        this.createPVPanelFromPoints(rawCorners, null, true);
        createdCount++;
      }
    } else {
      // Trường hợp 2: Hàng trên có N điểm, hàng dưới có 2 điểm đầu-cuối -> Tự động nội suy các điểm tương ứng
      const bStart = sortedBot[0];
      const bEnd = sortedBot[sortedBot.length - 1];
      const tStart = sortedTop[0];
      const tEnd = sortedTop[sortedTop.length - 1];
      const totalDistTop = Math.hypot(tEnd.col - tStart.col, tEnd.row - tStart.row);

      const interpBot = [];
      for (let i = 0; i < sortedTop.length; i++) {
        const curDist = Math.hypot(sortedTop[i].col - tStart.col, sortedTop[i].row - tStart.row);
        const ratio = totalDistTop > 0 ? curDist / totalDistTop : (i / (sortedTop.length - 1));
        interpBot.push({
          col: Math.round(bStart.col + (bEnd.col - bStart.col) * ratio),
          row: Math.round(bStart.row + (bEnd.row - bStart.row) * ratio)
        });
      }

      for (let i = 0; i < sortedTop.length - 1; i++) {
        const rawCorners = [
          sortedTop[i],
          sortedTop[i + 1],
          interpBot[i + 1],
          interpBot[i]
        ];
        this.createPVPanelFromPoints(rawCorners, null, true);
        createdCount++;
      }
    }

    this.cleanupStripDraft();
    this.updatePanelListUI();
    this.updateGuideText();
    if (typeof alert !== 'undefined') alert(`Đã hợp lực tạo thành công ${createdCount} tấm PV kèm tâm Centroid trên dải pin!`);
  }

  cleanupStripDraft() {
    const targetGroup = this.getActiveLayerGroup();
    this.stripMarkersTop.forEach(m => targetGroup.removeLayer(m));
    this.stripMarkersBot.forEach(m => targetGroup.removeLayer(m));
    this.stripMarkersTop = [];
    this.stripMarkersBot = [];
    this.stripPointsTop = [];
    this.stripPointsBot = [];
    if (this.stripLineTop) {
      targetGroup.removeLayer(this.stripLineTop);
      this.stripLineTop = null;
    }
    if (this.stripLineBot) {
      targetGroup.removeLayer(this.stripLineBot);
      this.stripLineBot = null;
    }
    this.stripStep = 'top';
  }

  /**
   * Hoàn thành tấm PV từ các góc đã chấm:
   * - 2 góc: Tự tìm cạnh nối của tấm liền kề, hoặc tạo hình chữ nhật từ 2 góc đối diện
   * - 3 góc: Tự suy ra góc 4 theo vector hình bình hành/chữ nhật xoay (P4 = P1 + P3 - P2)
   * - 4 góc: Hợp lực và sắp xếp 4 góc Đông Tây Nam Bắc, tạo hình và tính tâm
   */
  finishDraft() {
    const pts = this.currentDraftPoints;
    if (pts.length === 2) {
      // Kiểm tra có cạnh của tấm liền kề nào khớp không
      const match = this.findAdjacentMatchingEdge(pts[0], pts[1]);
      if (match) {
        this.createPVPanelFromPoints(match.corners);
      } else {
        const p1 = pts[0];
        const p2 = pts[1];
        const minX = Math.min(p1.col, p2.col);
        const maxX = Math.max(p1.col, p2.col);
        const minY = Math.min(p1.row, p2.row);
        const maxY = Math.max(p1.row, p2.row);

        const corners = [
          { col: minX, row: minY },
          { col: maxX, row: minY },
          { col: maxX, row: maxY },
          { col: minX, row: maxY }
        ];
        this.createPVPanelFromPoints(corners);
      }
      this.cleanupDraftMarkers();
      this.currentDraftPoints = [];
      this.updateGuideText();
    } else if (pts.length === 3) {
      const p1 = pts[0];
      const p2 = pts[1];
      const p3 = pts[2];
      const x4 = p1.col + p3.col - p2.col;
      const y4 = p1.row + p3.row - p2.row;
      const corners = [
        { col: p1.col, row: p1.row },
        { col: p2.col, row: p2.row },
        { col: p3.col, row: p3.row },
        { col: x4, row: y4 }
      ];
      this.createPVPanelFromPoints(corners);
      this.cleanupDraftMarkers();
      this.currentDraftPoints = [];
      this.updateGuideText();
    } else if (pts.length >= 4) {
      this.createPVPanelFromPoints(pts.slice(0, 4));
      this.cleanupDraftMarkers();
      this.currentDraftPoints = [];
      this.updateGuideText();
    }
  }

  cleanupDraftMarkers() {
    const targetGroup = this.getActiveLayerGroup();
    this.draftMarkers.forEach(m => targetGroup.removeLayer(m));
    this.draftMarkers = [];
    if (this.draftLines) {
      targetGroup.removeLayer(this.draftLines);
      this.draftLines = null;
    }
  }

  cancelDraft() {
    this.cleanupDraftMarkers();
    this.cleanupStripDraft();
    this.currentDraftPoints = [];
    this.updateGuideText();
  }

  /**
   * Tạo tấm PV từ 4 góc và TỰ ĐỘNG TÍNH TOÁN TÂM CENTROID Ở GIỮA
   * Tính toán đầy đủ Pixel, UTM zone 49N (EPSG:32649) và GPS WGS84 (EPSG:4326) cho cả 4 góc và tâm centroid.
   */
  createPVPanelFromPoints(points, customId = null, skipUIRefresh = false) {
    const activeInfo = this.getActiveInfo();
    const rawCorners = points.slice(0, 4);
    if (rawCorners.length < 4) return null;

    // Tự động sắp xếp 4 góc theo chiều kim đồng hồ quanh trọng tâm (Đông Tây Nam Bắc)
    // Loại bỏ hoàn toàn ràng buộc người dùng phải bấm 1-2-3-4 theo chu vi
    const orderedCorners = this.sortCornersClockwise(rawCorners);

    const cornersPixel = orderedCorners.map((p, idx) => ({
      corner_index: idx + 1,
      x: Math.round(p.col),
      y: Math.round(p.row)
    }));

    // Tự động tính toán điểm tâm Centroid ở giữa: Xc = sum(Xi)/4, Yc = sum(Yi)/4
    const centroidX = Math.round((cornersPixel[0].x + cornersPixel[1].x + cornersPixel[2].x + cornersPixel[3].x) / 4);
    const centroidY = Math.round((cornersPixel[0].y + cornersPixel[1].y + cornersPixel[2].y + cornersPixel[3].y) / 4);

    // Tính tọa độ UTM 49N và GPS cho 4 góc
    const cornersData = cornersPixel.map(cp => {
      const coords = CoordUtils.pixelToCoords(
        cp.x,
        cp.y,
        activeInfo ? activeInfo.transform : null,
        activeInfo ? activeInfo.crs : null
      );
      return {
        corner_index: cp.corner_index,
        pixel: { x: cp.x, y: cp.y },
        utm_32649: coords.utm_32649,
        gps: coords.gps
      };
    });

    // Tính tọa độ UTM 49N và GPS cho tâm Centroid
    const centroidCoords = CoordUtils.pixelToCoords(
      centroidX,
      centroidY,
      activeInfo ? activeInfo.transform : null,
      activeInfo ? activeInfo.crs : null
    );

    const centroidData = {
      pixel: { x: centroidX, y: centroidY },
      utm_32649: centroidCoords.utm_32649,
      gps: centroidCoords.gps
    };

    // Mảng 5 điểm hoàn chỉnh: 4 góc + 1 tâm centroid (điểm thứ 5)
    const allPoints = [
      ...cornersData.map(c => ({
        point_index: c.corner_index,
        role: "corner",
        pixel: c.pixel,
        utm_32649: c.utm_32649,
        gps: c.gps
      })),
      {
        point_index: 5,
        role: "centroid",
        pixel: centroidData.pixel,
        utm_32649: centroidData.utm_32649,
        gps: centroidData.gps
      }
    ];

    let panelId = customId;
    if (!panelId) {
      panelId = this.getNextPanelId();
    } else {
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
      type: "pv_panel",
      target: this.activeTarget, // 'big' hoặc 'sub'
      label: "solar_panel",
      corners: cornersData,
      centroid: centroidData,
      all_points: allPoints,
      // Tương thích ngược:
      corners_pixel: cornersPixel.map(cp => ({ index: cp.corner_index, x: cp.x, y: cp.y })),
      centroid_pixel: { x: centroidX, y: centroidY },
      corners_geo: cornersData.map(c => c.gps),
      centroid_geo: centroidData.gps
    };

    this.renderPVPanel(panelData);
    this.panels.push(panelData);

    if (!skipUIRefresh) {
      this.selectPanel(panelData.id, false);
      this.updatePanelListUI();
    }
    return panelData;
  }

  getNextPanelId() {
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
    const prefix = this.activeTarget === 'sub' ? 'PV_SUB' : 'PV';
    return `${prefix}_${String(this.nextPanelId).padStart(3, '0')}`;
  }

  /**
   * Render trực quan tấm PV:
   * 1. Đa giác 4 góc khép kín
   * 2. Chấm tâm Centroid nổi bật ở giữa
   * 3. 4 điểm đánh dấu góc
   */
  renderPVPanel(panelData) {
    const targetGroup = panelData.target === 'sub' ? this.pvLayerGroupSub : this.pvLayerGroupBig;
    const isSub = panelData.target === 'sub';
    const strokeColor = isSub ? '#10b981' : '#f59e0b';
    const fillColor = isSub ? '#10b981' : '#f59e0b';

    // 1. Đa giác viền 4 góc
    const latlngs = panelData.corners.map(c => [-c.pixel.y, c.pixel.x]);
    const polygon = L.polygon(latlngs, {
      color: strokeColor,
      weight: 2,
      fillColor: fillColor,
      fillOpacity: 0.22,
      className: 'pv-panel-polygon',
      renderer: this.canvasRenderer
    }).addTo(targetGroup);

    polygon.bindTooltip(`<b>${panelData.id}</b> (${isSub ? 'Ortho Vùng' : 'Ortho To'})`, {
      permanent: false,
      direction: 'center',
      className: 'pv-id-tooltip'
    });

    polygon.on('click', (e) => {
      if (!this.isDrawMode) {
        L.DomEvent.stopPropagation(e);
        this.selectPanel(panelData.id);
      }
    });

    // 2. Chấm tâm Centroid (nổi bật, rõ nét ở tâm tấm PV)
    const cLatlng = [-panelData.centroid.pixel.y, panelData.centroid.pixel.x];
    const centroidDot = L.circleMarker(cLatlng, {
      radius: 5,
      color: '#ffffff',
      fillColor: isSub ? '#059669' : '#ef4444',
      fillOpacity: 0.95,
      weight: 2,
      className: 'pv-centroid-dot',
      renderer: this.canvasRenderer
    }).addTo(targetGroup);

    const cUtm = panelData.centroid.utm_32649;
    const cGps = panelData.centroid.gps;
    centroidDot.bindTooltip(`
      <div style="font-family: monospace; font-size: 11px;">
        <b>${panelData.id} (Tâm Centroid)</b><br>
        Pixel: (${panelData.centroid.pixel.x}, ${panelData.centroid.pixel.y})<br>
        UTM 49N: E=${Math.round(cUtm.easting).toLocaleString()} m, N=${Math.round(cUtm.northing).toLocaleString()} m<br>
        GPS: ${cGps.formatted || (cGps.lat.toFixed(6) + '°, ' + cGps.lon.toFixed(6) + '°')}
      </div>
    `, {
      direction: 'top',
      className: 'pv-id-tooltip'
    });

    centroidDot.on('click', (e) => {
      if (!this.isDrawMode) {
        L.DomEvent.stopPropagation(e);
        this.selectPanel(panelData.id);
      }
    });

    // 3. Chấm 4 góc nhỏ để định vị
    const cornerDots = panelData.corners.map(c => {
      const dot = L.circleMarker([-c.pixel.y, c.pixel.x], {
        radius: 3.5,
        color: isSub ? '#34d399' : '#fbbf24',
        fillColor: isSub ? '#065f46' : '#92400e',
        fillOpacity: 0.85,
        weight: 1.5,
        renderer: this.canvasRenderer
      }).addTo(targetGroup);

      dot.bindTooltip(`Góc ${c.corner_index}: (${c.pixel.x}, ${c.pixel.y})`, {
        direction: 'top',
        className: 'pv-id-tooltip'
      });

      dot.on('click', (e) => {
        if (!this.isDrawMode) {
          L.DomEvent.stopPropagation(e);
          this.selectPanel(panelData.id);
        }
      });

      return dot;
    });

    panelData.polygon = polygon;
    panelData.centroidDot = centroidDot;
    panelData.cornerDots = cornerDots;
  }

  /**
   * Chọn tấm PV để hiển thị bộ vi chỉnh (Active Editor)
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

    if (p.polygon) {
      const highlightColor = p.target === 'sub' ? '#34d399' : '#38bdf8';
      p.polygon.setStyle({
        color: highlightColor,
        weight: 3,
        fillColor: highlightColor,
        fillOpacity: 0.35
      });
    }

    this.attachActiveHandles(p);
    this.highlightSidebarCard(panelId);

    if (shouldPan) {
      this.focusPanel(panelId);
    }
  }

  deselectPanel() {
    if (this.selectedPanelId) {
      const prev = this.panels.find(x => x.id === this.selectedPanelId);
      if (prev && prev.polygon) {
        const isSub = prev.target === 'sub';
        prev.polygon.setStyle({
          color: isSub ? '#10b981' : '#f59e0b',
          weight: 2,
          fillColor: isSub ? '#10b981' : '#f59e0b',
          fillOpacity: 0.22
        });
      }
      this.removeActiveHandles();
      this.selectedPanelId = null;
      document.querySelectorAll('.pv-item-card.active-selected').forEach(el => el.classList.remove('active-selected'));
    }
  }

  /**
   * Gắn các chốt kéo vi chỉnh:
   * - 1 chốt kéo ở tâm Centroid: Kéo để tịnh tiến toàn bộ tấm pin
   * - 4 chốt kéo ở 4 góc: Kéo để chỉnh góc -> TỰ ĐỘNG tính lại tâm Centroid
   */
  attachActiveHandles(panelData) {
    this.removeActiveHandles();
    const targetGroup = panelData.target === 'sub' ? this.pvLayerGroupSub : this.pvLayerGroupBig;
    const activeInfo = panelData.target === 'sub' ? this.viewer.subInfo : this.viewer.bigInfo;

    this.attachActiveHandlesPV(panelData, targetGroup, activeInfo);
  }

  attachActiveHandlesPV(panelData, targetGroup, activeInfo) {
    const cX = panelData.centroid ? panelData.centroid.pixel.x : panelData.centroid_pixel.x;
    const cY = panelData.centroid ? panelData.centroid.pixel.y : panelData.centroid_pixel.y;

    // 1. Chốt kéo tâm Centroid (kéo để di chuyển toàn bộ tấm pin)
    const centroidIcon = L.divIcon({
      className: 'centroid-div-icon',
      html: `<div class="centroid-marker active" title="Tâm Centroid (${panelData.id}) - Kéo để di chuyển cả tấm">⌖</div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11]
    });

    const centroidMarker = L.marker([-cY, cX], {
      icon: centroidIcon,
      draggable: true,
      zIndexOffset: 1500
    }).addTo(targetGroup);

    centroidMarker.on('drag', () => {
      const newCol = Math.round(centroidMarker.getLatLng().lng);
      const newRow = Math.round(-centroidMarker.getLatLng().lat);
      const currentCenterX = panelData.centroid ? panelData.centroid.pixel.x : panelData.centroid_pixel.x;
      const currentCenterY = panelData.centroid ? panelData.centroid.pixel.y : panelData.centroid_pixel.y;
      const dx = newCol - currentCenterX;
      const dy = newRow - currentCenterY;

      if (dx === 0 && dy === 0) return;

      // Cập nhật tọa độ tâm Centroid
      if (panelData.centroid) {
        panelData.centroid.pixel.x = newCol;
        panelData.centroid.pixel.y = newRow;
      }
      panelData.centroid_pixel = { x: newCol, y: newRow };

      const cCoords = CoordUtils.pixelToCoords(newCol, newRow, activeInfo?.transform, activeInfo?.crs);
      if (panelData.centroid) {
        panelData.centroid.utm_32649 = cCoords.utm_32649;
        panelData.centroid.gps = cCoords.gps;
      }
      panelData.centroid_geo = cCoords.gps;

      // Tịnh tiến cả 4 góc
      panelData.corners.forEach((c, idx) => {
        c.pixel.x += dx;
        c.pixel.y += dy;
        if (panelData.corners_pixel && panelData.corners_pixel[idx]) {
          panelData.corners_pixel[idx].x = c.pixel.x;
          panelData.corners_pixel[idx].y = c.pixel.y;
        }
        const cUpdated = CoordUtils.pixelToCoords(c.pixel.x, c.pixel.y, activeInfo?.transform, activeInfo?.crs);
        c.utm_32649 = cUpdated.utm_32649;
        c.gps = cUpdated.gps;
        if (panelData.corners_geo && panelData.corners_geo[idx]) {
          panelData.corners_geo[idx] = cUpdated.gps;
        }

        // Di chuyển chốt kéo góc
        if (cornerMarkers[idx]) {
          cornerMarkers[idx].setLatLng([-c.pixel.y, c.pixel.x]);
        }
        // Di chuyển chấm góc cố định
        if (panelData.cornerDots && panelData.cornerDots[idx]) {
          panelData.cornerDots[idx].setLatLng([-c.pixel.y, c.pixel.x]);
        }
      });

      if (panelData.centroidDot) {
        panelData.centroidDot.setLatLng([-newRow, newCol]);
      }

      if (panelData.polygon) {
        panelData.polygon.setLatLngs(panelData.corners.map(c => [-c.pixel.y, c.pixel.x]));
      }

      this.updateSingleCardCoords(panelData.id);
    });

    centroidMarker.on('dragend', () => {
      this.updateSingleCardCoords(panelData.id);
    });

    // 2. 4 chốt kéo ở 4 góc (kéo góc nào -> hình dạng thay đổi -> tự động tính lại tâm centroid)
    const cornerMarkers = panelData.corners.map((c, idx) => {
      const cornerIcon = L.divIcon({
        className: 'corner-div-icon',
        html: `<div class="corner-handle" title="Góc ${c.corner_index} - Kéo để vi chỉnh">${c.corner_index}</div>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9]
      });

      const m = L.marker([-c.pixel.y, c.pixel.x], {
        icon: cornerIcon,
        draggable: true,
        zIndexOffset: 1200
      }).addTo(targetGroup);

      m.on('drag', () => {
        const newCol = Math.round(m.getLatLng().lng);
        const newRow = Math.round(-m.getLatLng().lat);

        c.pixel.x = newCol;
        c.pixel.y = newRow;
        if (panelData.corners_pixel && panelData.corners_pixel[idx]) {
          panelData.corners_pixel[idx].x = newCol;
          panelData.corners_pixel[idx].y = newRow;
        }

        const updated = CoordUtils.pixelToCoords(newCol, newRow, activeInfo?.transform, activeInfo?.crs);
        c.utm_32649 = updated.utm_32649;
        c.gps = updated.gps;
        if (panelData.corners_geo && panelData.corners_geo[idx]) {
          panelData.corners_geo[idx] = updated.gps;
        }

        if (panelData.cornerDots && panelData.cornerDots[idx]) {
          panelData.cornerDots[idx].setLatLng([-newRow, newCol]);
        }

        // TỰ ĐỘNG TÍNH LẠI TÂM CENTROID TỪ 4 GÓC
        const autoCenterX = Math.round(panelData.corners.reduce((s, pt) => s + pt.pixel.x, 0) / 4);
        const autoCenterY = Math.round(panelData.corners.reduce((s, pt) => s + pt.pixel.y, 0) / 4);

        if (panelData.centroid) {
          panelData.centroid.pixel.x = autoCenterX;
          panelData.centroid.pixel.y = autoCenterY;
        }
        panelData.centroid_pixel = { x: autoCenterX, y: autoCenterY };

        const cCentroid = CoordUtils.pixelToCoords(autoCenterX, autoCenterY, activeInfo?.transform, activeInfo?.crs);
        if (panelData.centroid) {
          panelData.centroid.utm_32649 = cCentroid.utm_32649;
          panelData.centroid.gps = cCentroid.gps;
        }
        panelData.centroid_geo = cCentroid.gps;

        // Di chuyển chốt kéo tâm và chấm tâm
        centroidMarker.setLatLng([-autoCenterY, autoCenterX]);
        if (panelData.centroidDot) {
          panelData.centroidDot.setLatLng([-autoCenterY, autoCenterX]);
        }

        if (panelData.polygon) {
          panelData.polygon.setLatLngs(panelData.corners.map(pt => [-pt.pixel.y, pt.pixel.x]));
        }

        this.updateSingleCardCoords(panelData.id);
      });

      m.on('dragend', () => {
        this.updateSingleCardCoords(panelData.id);
      });

      return m;
    });

    this.activeHandles = { centroidMarker, handleMarkers: cornerMarkers, targetGroup };
  }

  removeActiveHandles() {
    if (this.activeHandles) {
      const group = this.activeHandles.targetGroup || this.getActiveLayerGroup();
      if (this.activeHandles.centroidMarker) {
        group.removeLayer(this.activeHandles.centroidMarker);
      }
      if (this.activeHandles.handleMarkers) {
        this.activeHandles.handleMarkers.forEach(m => group.removeLayer(m));
      }
      this.activeHandles = null;
    }
  }

  highlightSidebarCard(panelId) {
    document.querySelectorAll('.pv-item-card.active-selected').forEach(el => el.classList.remove('active-selected'));
    const card = document.getElementById(`card_${panelId}`);
    if (card) {
      card.classList.add('active-selected');
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  /**
   * Cập nhật thời gian thực tọa độ hiển thị trên card khi kéo thả
   */
  updateSingleCardCoords(id) {
    const p = this.panels.find(x => x.id === id);
    if (!p) return;
    const card = document.getElementById(`card_${id}`);
    if (!card) return;

    // Cập nhật kích thước
    const dimTag = card.querySelector('.pv-dim-tag');
    if (dimTag && p.corners) {
      const pts = p.corners.map(c => c.pixel);
      const wEst = Math.round(Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
      const hEst = Math.round(Math.hypot(pts[2].x - pts[1].x, pts[2].y - pts[1].y));
      dimTag.innerText = `${wEst}x${hEst}px`;
    }

    // Cập nhật khối Centroid
    const centroidLines = card.querySelectorAll('.centroid-coords-details .coord-line');
    if (centroidLines && centroidLines.length >= 3 && p.centroid) {
      centroidLines[0].innerHTML = `<span class="coord-tag">Pixel:</span> (${p.centroid.pixel.x}, ${p.centroid.pixel.y})`;
      centroidLines[1].innerHTML = `<span class="coord-tag">UTM 49N:</span> E=${Math.round(p.centroid.utm_32649.easting).toLocaleString()} m, N=${Math.round(p.centroid.utm_32649.northing).toLocaleString()} m`;
      centroidLines[2].innerHTML = `<span class="coord-tag">GPS:</span> ${p.centroid.gps.formatted || (p.centroid.gps.lat.toFixed(7) + '°, ' + p.centroid.gps.lon.toFixed(7) + '°')}`;
    }

    // Cập nhật 4 góc
    const cornerRows = card.querySelectorAll('.corner-row');
    if (p.corners && cornerRows) {
      p.corners.forEach((c, idx) => {
        if (cornerRows[idx]) {
          const lines = cornerRows[idx].querySelectorAll('.coord-line');
          if (lines[0]) lines[0].innerHTML = `<span class="coord-tag">Pixel:</span> (${c.pixel.x}, ${c.pixel.y})`;
          if (lines[1]) lines[1].innerHTML = `<span class="coord-tag">UTM 49N:</span> E=${Math.round(c.utm_32649.easting).toLocaleString()} m, N=${Math.round(c.utm_32649.northing).toLocaleString()} m`;
          if (lines[2]) lines[2].innerHTML = `<span class="coord-tag">GPS:</span> ${c.gps.formatted || (c.gps.lat.toFixed(7) + '°, ' + c.gps.lon.toFixed(7) + '°')}`;
        }
      });
    }
  }

  /**
   * Cập nhật toàn bộ Sidebar UI (Phân trang, Danh sách, Thống kê) cho ảnh mục tiêu hiện tại
   */
  updatePanelListUI() {
    const countBadge = document.getElementById('pvCountBadge');
    const tabBadge = document.getElementById('tabPVBadge');
    const listContainer = document.getElementById('pvListContainer');
    const btnClear = document.getElementById('btnClearAllPV');
    const searchBox = document.getElementById('pvSearchBox');

    const filtered = this.getFilteredPanels();
    const total = filtered.length;
    const targetLabel = this.activeTarget === 'sub' ? 'Vùng' : 'To';

    if (countBadge) countBadge.innerText = `${total} tấm (${targetLabel})`;
    if (tabBadge) tabBadge.innerText = total;

    if (btnClear) btnClear.style.display = total > 0 ? 'inline-flex' : 'none';
    if (searchBox) searchBox.style.display = total > 0 ? 'block' : 'none';

    if (!listContainer) return;

    if (total === 0) {
      listContainer.innerHTML = `
        <div class="empty-hint">
          <i class="fa-solid fa-solar-panel"></i>
          Chưa có tấm PV nào trên <b>${this.activeTarget === 'sub' ? 'Ortho Vùng' : 'Ortho To'}</b>.<br>
          Bấm <b>Bật Chấm 4 Góc PV</b> hoặc <b>Dập Khuôn PV</b> để bắt đầu.
        </div>
      `;
      const pagination = document.getElementById('pvPagination');
      if (pagination) pagination.style.display = 'none';
      return;
    }

    const totalPages = Math.max(1, Math.ceil(total / this.pageSize));

    if (this.currentPage > totalPages) this.currentPage = totalPages;
    if (this.currentPage < 1) this.currentPage = 1;

    const startIndex = (this.currentPage - 1) * this.pageSize;
    const endIndex = Math.min(startIndex + this.pageSize, total);
    const pageItems = filtered.slice(startIndex, endIndex);

    const pagination = document.getElementById('pvPagination');
    const pageInfo = document.getElementById('pvPageInfo');
    const btnPrev = document.getElementById('btnPVPrevPage');
    const btnNext = document.getElementById('btnPVNextPage');

    if (pagination) pagination.style.display = (totalPages > 1 || this.searchQuery) ? 'flex' : 'none';
    if (pageInfo) pageInfo.innerText = `Trang ${this.currentPage}/${totalPages} (${total} tấm - ${targetLabel})`;
    if (btnPrev) btnPrev.disabled = this.currentPage <= 1;
    if (btnNext) btnNext.disabled = this.currentPage >= totalPages;

    if (pageItems.length === 0) {
      listContainer.innerHTML = '<div class="empty-hint"><i class="fa-solid fa-filter-circle-xmark"></i> Không tìm thấy tấm PV nào với từ khóa này.</div>';
      return;
    }

    let html = '';
    pageItems.forEach(p => {
      const isSelected = p.id === this.selectedPanelId;
      const targetBadge = `<span class="pv-target-badge ${p.target === 'sub' ? 'sub' : 'big'}">${p.target === 'sub' ? 'Ortho Vùng' : 'Ortho To'}</span>`;

      // Ước tính kích thước W x H px
      const pts = p.corners ? p.corners.map(c => c.pixel) : (p.corners_pixel || []);
      let wEst = 0, hEst = 0;
      if (pts.length >= 4) {
        wEst = Math.round(Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
        hEst = Math.round(Math.hypot(pts[2].x - pts[1].x, pts[2].y - pts[1].y));
      }

      const cData = p.centroid;
      const cUtm = cData?.utm_32649;
      const cGps = cData?.gps || p.centroid_geo;
      const cPixel = cData?.pixel || p.centroid_pixel || { x: 0, y: 0 };

      html += `
        <div class="pv-item-card ${isSelected ? 'active-selected' : ''}" data-panel-id="${p.id}" id="card_${p.id}">
          <div class="pv-item-header">
            <div class="pv-item-title">
              <span class="pv-id-tag"><i class="fa-solid fa-solar-panel"></i> ${p.id}</span>
              <span class="pv-dim-tag">${wEst}x${hEst}px</span>
              ${targetBadge}
            </div>
            <div class="pv-item-actions">
              <button class="btn-icon copy-btn" data-action="copy" data-id="${p.id}" title="Sao chép JSON tọa độ tấm này"><i class="fa-solid fa-copy"></i></button>
              <button class="btn-icon focus-btn" data-action="focus" data-id="${p.id}" title="Phóng to & Chỉnh sửa"><i class="fa-solid fa-crosshairs"></i></button>
              <button class="btn-icon delete-btn text-danger" data-action="delete" data-id="${p.id}" title="Xóa tấm PV này"><i class="fa-solid fa-trash-can"></i></button>
            </div>
          </div>
          
          <div class="pv-item-meta pv-panel-meta">
            <!-- 1. KHỐI TÂM CENTROID (TỰ TÍNH) -->
            <div class="centroid-section-card">
              <div class="centroid-section-header">
                <span class="centroid-title-badge"><i class="fa-solid fa-bullseye"></i> Tâm Centroid (Tự tính)</span>
              </div>
              <div class="centroid-coords-details">
                <div class="coord-line"><span class="coord-tag">Pixel:</span> (${cPixel.x}, ${cPixel.y})</div>
                <div class="coord-line"><span class="coord-tag">UTM 49N:</span> ${cUtm ? `E=${Math.round(cUtm.easting).toLocaleString()} m, N=${Math.round(cUtm.northing).toLocaleString()} m` : 'N/A'}</div>
                <div class="coord-line"><span class="coord-tag">GPS:</span> ${cGps ? (cGps.formatted || (cGps.lat.toFixed(7) + '°, ' + cGps.lon.toFixed(7) + '°')) : 'N/A'}</div>
              </div>
            </div>

            <!-- 2. KHỐI 4 GÓC -->
            <div class="corners-section-card">
              <div class="corners-section-title"><i class="fa-solid fa-vector-square"></i> 4 Góc Tấm PV:</div>
              ${p.corners ? p.corners.map(c => `
                <div class="point-row corner-row">
                  <span class="point-num-badge corner-badge">${c.corner_index}</span>
                  <div class="point-coords-details">
                    <div class="coord-line"><span class="coord-tag">Pixel:</span> (${c.pixel.x}, ${c.pixel.y})</div>
                    <div class="coord-line"><span class="coord-tag">UTM 49N:</span> E=${Math.round(c.utm_32649.easting).toLocaleString()} m, N=${Math.round(c.utm_32649.northing).toLocaleString()} m</div>
                    <div class="coord-line"><span class="coord-tag">GPS:</span> ${c.gps.formatted || (c.gps.lat.toFixed(7) + '°, ' + c.gps.lon.toFixed(7) + '°')}</div>
                  </div>
                </div>
              `).join('') : ''}
            </div>
          </div>
        </div>
      `;
    });

    listContainer.innerHTML = html;
  }

  focusPanel(id) {
    const p = this.panels.find(x => x.id === id);
    if (!p) return;

    let latlngs;
    if (p.corners && p.corners.length > 0) {
      latlngs = p.corners.map(c => [-c.pixel.y, c.pixel.x]);
    } else if (p.corners_pixel) {
      latlngs = p.corners_pixel.map(pt => [-pt.y, pt.x]);
    }

    if (latlngs) {
      const bounds = L.latLngBounds(latlngs);
      this.map.fitBounds(bounds, { padding: [80, 80], maxZoom: 4 });
      this.selectPanel(id, false);
      if (p.polygon) {
        p.polygon.openTooltip();
      }
    }
  }

  deletePanel(id) {
    const idx = this.panels.findIndex(p => p.id === id);
    if (idx !== -1) {
      const p = this.panels[idx];
      const targetGroup = p.target === 'sub' ? this.pvLayerGroupSub : this.pvLayerGroupBig;
      if (p.polygon) targetGroup.removeLayer(p.polygon);
      if (p.centroidDot) targetGroup.removeLayer(p.centroidDot);
      if (p.cornerDots) {
        p.cornerDots.forEach(m => targetGroup.removeLayer(m));
      }
      if (p.pointMarkers) {
        p.pointMarkers.forEach(m => targetGroup.removeLayer(m));
      }
      if (this.selectedPanelId === id) {
        this.deselectPanel();
      }
      this.panels.splice(idx, 1);
      this.updatePanelListUI();
    }
  }

  clearAll() {
    this.deselectPanel();
    const targetGroup = this.getActiveLayerGroup();
    targetGroup.clearLayers();
    this.panels = this.panels.filter(p => (p.target || 'big') !== this.activeTarget);
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
      const targetGroup = this.getActiveLayerGroup();
      if (lastMarker) targetGroup.removeLayer(lastMarker);
      if (this.draftLines) {
        if (this.currentDraftPoints.length > 1) {
          this.draftLines.setLatLngs(this.currentDraftPoints.map(p => p.latlng));
        } else {
          targetGroup.removeLayer(this.draftLines);
          this.draftLines = null;
        }
      }
      this.updateGuideText();
    } else {
      const activePanels = this.panels.filter(p => (p.target || 'big') === this.activeTarget);
      if (activePanels.length > 0) {
        const lastItem = activePanels[activePanels.length - 1];
        this.deletePanel(lastItem.id);
      }
    }
  }

  getFilteredPanels() {
    let list = this.panels.filter(p => (p.target || 'big') === this.activeTarget);
    if (!this.searchQuery) return list;
    const q = this.searchQuery.toLowerCase();
    return list.filter(p => String(p.id).toLowerCase().includes(q));
  }

  copyCoordinates(id, btnElement) {
    const p = this.panels.find(x => x.id === id);
    if (!p) return;

    const copyData = {
      id: p.id,
      label: p.label || "solar_panel",
      target: p.target,
      crs: "EPSG:32649",
      crs_name: "WGS 84 / UTM zone 49N",
      gps_crs: "EPSG:4326 (WGS 84)",
      centroid: {
        pixel: p.centroid ? p.centroid.pixel : p.centroid_pixel,
        utm_32649: p.centroid ? p.centroid.utm_32649 : null,
        gps: p.centroid ? p.centroid.gps : p.centroid_geo
      },
      corners: p.corners ? p.corners.map(c => ({
        corner_index: c.corner_index,
        pixel: c.pixel,
        utm_32649: c.utm_32649,
        gps: c.gps
      })) : p.corners_pixel,
      all_points: p.all_points || (p.corners && p.centroid ? [
        ...p.corners.map(c => ({ point_index: c.corner_index, role: "corner", pixel: c.pixel, utm_32649: c.utm_32649, gps: c.gps })),
        { point_index: 5, role: "centroid", pixel: p.centroid.pixel, utm_32649: p.centroid.utm_32649, gps: p.centroid.gps }
      ] : []),
      corners_pixel: p.corners_pixel,
      centroid_pixel: p.centroid_pixel
    };

    OrthoReader.copyToClipboard(JSON.stringify(copyData, null, 2), btnElement);
  }

  /**
   * Xuất danh sách các tấm PV (bao gồm cả 4 góc và tâm Centroid) ra file JSON
   */
  exportJSON() {
    const activePanels = this.panels.filter(p => (p.target || 'big') === this.activeTarget);
    const targetName = this.activeTarget === 'sub' ? 'Ortho Vùng' : 'Ortho To';
    if (activePanels.length === 0) {
      alert(`Chưa có tấm PV nào trên ${targetName} để xuất!`);
      return;
    }

    const activeInfo = this.getActiveInfo();
    const exportData = {
      version: "2.1",
      project: "PV Panel Annotations with Centroid",
      target_type: this.activeTarget === 'sub' ? "ortho_vung" : "ortho_to",
      generated_at: new Date().toISOString(),
      crs: activeInfo && activeInfo.crs ? activeInfo.crs : "EPSG:32649",
      crs_name: "WGS 84 / UTM zone 49N",
      gps_crs: "EPSG:4326 (WGS 84)",
      ortho_file: activeInfo ? activeInfo.file_name : "unknown",
      dimensions: activeInfo ? { width: activeInfo.width, height: activeInfo.height } : null,
      total_panels: activePanels.length,
      panels: activePanels.map(p => ({
        id: p.id,
        label: p.label || "solar_panel",
        target: p.target,
        centroid: {
          pixel: p.centroid ? p.centroid.pixel : p.centroid_pixel,
          utm_32649: p.centroid && p.centroid.utm_32649 ? {
            easting: p.centroid.utm_32649.easting,
            northing: p.centroid.utm_32649.northing,
            unit: "meter",
            crs: "EPSG:32649"
          } : null,
          gps: p.centroid && p.centroid.gps ? {
            latitude: p.centroid.gps.lat ?? p.centroid.gps.latitude,
            longitude: p.centroid.gps.lon ?? p.centroid.gps.longitude,
            formatted: p.centroid.gps.formatted,
            crs: "EPSG:4326"
          } : (p.centroid_geo ? {
            latitude: p.centroid_geo.lat,
            longitude: p.centroid_geo.lon,
            crs: "EPSG:4326"
          } : null)
        },
        corners: p.corners ? p.corners.map(c => ({
          corner_index: c.corner_index,
          pixel: c.pixel,
          utm_32649: {
            easting: c.utm_32649.easting,
            northing: c.utm_32649.northing,
            unit: "meter",
            crs: "EPSG:32649"
          },
          gps: {
            latitude: c.gps.lat ?? c.gps.latitude,
            longitude: c.gps.lon ?? c.gps.longitude,
            formatted: c.gps.formatted,
            crs: "EPSG:4326"
          }
        })) : (p.corners_pixel ? p.corners_pixel.map(cp => ({
          corner_index: cp.index,
          pixel: { x: cp.x, y: cp.y }
        })) : []),
        all_points: p.all_points || (p.corners && p.centroid ? [
          ...p.corners.map(c => ({ point_index: c.corner_index, role: "corner", pixel: c.pixel, utm_32649: c.utm_32649, gps: c.gps })),
          { point_index: 5, role: "centroid", pixel: p.centroid.pixel, utm_32649: p.centroid.utm_32649, gps: p.centroid.gps }
        ] : []),
        // Trường tương thích ngược:
        corners_pixel: p.corners_pixel,
        centroid_pixel: p.centroid_pixel,
        corners_geo: p.corners_geo,
        centroid_geo: p.centroid_geo
      }))
    };

    const jsonStr = JSON.stringify(exportData, null, 2);
    const orthoBaseName = (activeInfo ? activeInfo.file_name : this.activeTarget).replace(/\.[^/.]+$/, "");
    const fileName = `pv_panels_${this.activeTarget}_${orthoBaseName}_with_centroid_EPSG32649.json`;

    OrthoReader.downloadFile(jsonStr, fileName, 'application/json');
  }

  /**
   * Nhập lại danh sách các tấm PV từ file JSON vào ảnh mục tiêu hiện tại
   */
  importJSON(jsonString) {
    try {
      const data = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
      const list = data.panels || data.point_sets || data.items;

      if (!list || !Array.isArray(list)) {
        throw new Error('Định dạng JSON không hợp lệ. Cần có trường "panels", "point_sets" hoặc "items" là mảng.');
      }

      let importedCount = 0;
      list.forEach(item => {
        let rawCorners = null;
        if (item.corners && Array.isArray(item.corners) && item.corners.length === 4) {
          rawCorners = item.corners.map(c => ({ col: c.pixel ? c.pixel.x : c.x, row: c.pixel ? c.pixel.y : c.y }));
        } else if (item.corners_pixel && Array.isArray(item.corners_pixel) && item.corners_pixel.length === 4) {
          rawCorners = item.corners_pixel.map(c => ({ col: c.x, row: c.y }));
        } else if (item.points && Array.isArray(item.points) && item.points.length >= 4) {
          rawCorners = item.points.slice(0, 4).map(p => ({ col: p.pixel ? p.pixel.x : p.x, row: p.pixel ? p.pixel.y : p.y }));
        } else if (item.all_points && Array.isArray(item.all_points) && item.all_points.length >= 4) {
          rawCorners = item.all_points.slice(0, 4).map(p => ({ col: p.pixel ? p.pixel.x : p.x, row: p.pixel ? p.pixel.y : p.y }));
        }

        if (rawCorners && rawCorners.length === 4) {
          this.createPVPanelFromPoints(rawCorners, item.id, true);
          importedCount++;
        }
      });

      this.currentPage = 1;
      this.updatePanelListUI();
      const targetName = this.activeTarget === 'sub' ? 'Ortho Vùng' : 'Ortho To';
      alert(`Đã nạp thành công ${importedCount} tấm PV lên ${targetName}!`);

      const activePanels = this.panels.filter(p => (p.target || 'big') === this.activeTarget);
      if (activePanels.length > 0) {
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        activePanels.forEach(p => {
          const pts = p.corners ? p.corners.map(c => c.pixel) : (p.corners_pixel || []);
          pts.forEach(pt => {
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

  // --- Các hàm hỗ trợ chế độ dập khuôn mẫu (Stamp) trên ảnh mục tiêu ---
  stampPanelAt(latlng) {
    const centerCol = Math.round(latlng.lng);
    const centerRow = Math.round(-latlng.lat);
    const points = this.calculateStampCorners(centerCol, centerRow);
    this.createPVPanelFromPoints(points);
  }

  calculateStampCorners(centerCol, centerRow) {
    const halfW = this.stampConfig.width / 2;
    const halfH = this.stampConfig.height / 2;
    const rad = (this.stampConfig.angleDeg * Math.PI) / 180;
    const cosA = Math.cos(rad);
    const sinA = Math.sin(rad);

    const relCorners = [
      { dx: -halfW, dy: -halfH },
      { dx: halfW, dy: -halfH },
      { dx: halfW, dy: halfH },
      { dx: -halfW, dy: halfH }
    ];

    return relCorners.map(c => {
      const rx = c.dx * cosA - c.dy * sinA;
      const ry = c.dx * sinA + c.dy * cosA;
      const col = Math.round(centerCol + rx);
      const row = Math.round(centerRow + ry);
      return { col, row, latlng: L.latLng(-row, col) };
    });
  }

  updateGhostPreview(latlng) {
    const centerCol = Math.round(latlng.lng);
    const centerRow = Math.round(-latlng.lat);
    const corners = this.calculateStampCorners(centerCol, centerRow);
    const latlngs = corners.map(p => p.latlng);
    const targetGroup = this.getActiveLayerGroup();

    if (!this.ghostLayer) {
      this.ghostLayer = L.polygon(latlngs, {
        color: this.activeTarget === 'sub' ? '#10b981' : '#f59e0b',
        weight: 1.5,
        dashArray: '3, 3',
        fillColor: this.activeTarget === 'sub' ? '#10b981' : '#f59e0b',
        fillOpacity: 0.25,
        interactive: false
      }).addTo(targetGroup);
    } else {
      this.ghostLayer.setLatLngs(latlngs);
      this.ghostLayer.setStyle({ opacity: 1, fillOpacity: 0.25 });
    }
  }

  hideGhostPreview() {
    if (this.ghostLayer) {
      this.ghostLayer.setStyle({ opacity: 0, fillOpacity: 0 });
    }
  }

  syncStampConfigToUI() {
    const wInput = document.getElementById('stampWidthInput');
    const hInput = document.getElementById('stampHeightInput');
    if (wInput) wInput.value = this.stampConfig.width;
    if (hInput) hInput.value = this.stampConfig.height;

    const badge = document.getElementById('orientationBadge');
    if (badge) {
      badge.innerText = this.stampConfig.orientation === 'horizontal' ? 'Ngang' : 'Dọc';
    }
    const btnH = document.getElementById('btnOrientHorizontal');
    const btnV = document.getElementById('btnOrientVertical');
    if (btnH) btnH.classList.toggle('active', this.stampConfig.orientation === 'horizontal');
    if (btnV) btnV.classList.toggle('active', this.stampConfig.orientation === 'vertical');
  }

  toggleOrientation() {
    const temp = this.stampConfig.width;
    this.stampConfig.width = this.stampConfig.height;
    this.stampConfig.height = temp;
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  setOrientation(orientation) {
    if (this.stampConfig.orientation === orientation) return;
    const isHoriz = orientation === 'horizontal';
    const maxDim = Math.max(this.stampConfig.width, this.stampConfig.height);
    const minDim = Math.min(this.stampConfig.width, this.stampConfig.height);
    this.stampConfig.width = isHoriz ? maxDim : minDim;
    this.stampConfig.height = isHoriz ? minDim : maxDim;
    this.stampConfig.orientation = orientation;
    this.syncStampConfigToUI();
  }

  adjustDimensions(dw, dh) {
    this.stampConfig.width = Math.max(5, this.stampConfig.width + dw);
    this.stampConfig.height = Math.max(5, this.stampConfig.height + dh);
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  setAngle(deg) {
    this.stampConfig.angleDeg = parseFloat(deg) || 0;
    const angleVal = document.getElementById('stampAngleVal');
    if (angleVal) angleVal.innerText = `${this.stampConfig.angleDeg}°`;
  }

  scaleStamp(factor) {
    this.stampConfig.width = Math.max(5, Math.round(this.stampConfig.width * factor));
    this.stampConfig.height = Math.max(5, Math.round(this.stampConfig.height * factor));
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }

  scalePanel(id, factor) {
    const p = this.panels.find(x => x.id === id);
    if (!p || !p.corners || p.corners.length < 4) return;
    const cX = p.centroid.pixel.x;
    const cY = p.centroid.pixel.y;
    const activeInfo = this.getActiveInfo();

    p.corners.forEach((c, idx) => {
      c.pixel.x = Math.round(cX + (c.pixel.x - cX) * factor);
      c.pixel.y = Math.round(cY + (c.pixel.y - cY) * factor);
      if (p.corners_pixel && p.corners_pixel[idx]) {
        p.corners_pixel[idx].x = c.pixel.x;
        p.corners_pixel[idx].y = c.pixel.y;
      }
      const updated = CoordUtils.pixelToCoords(c.pixel.x, c.pixel.y, activeInfo?.transform, activeInfo?.crs);
      c.utm_32649 = updated.utm_32649;
      c.gps = updated.gps;
    });

    if (p.polygon) {
      p.polygon.setLatLngs(p.corners.map(c => [-c.pixel.y, c.pixel.x]));
    }
    if (p.cornerDots) {
      p.corners.forEach((c, idx) => {
        if (p.cornerDots[idx]) p.cornerDots[idx].setLatLng([-c.pixel.y, c.pixel.x]);
      });
    }
    this.updateSingleCardCoords(id);
    if (this.selectedPanelId === id) {
      this.attachActiveHandles(p);
    }
  }

  pickSizeFromPanel(id) {
    const p = this.panels.find(x => x.id === id);
    if (!p || !p.corners || p.corners.length < 4) return;
    const pts = p.corners.map(c => c.pixel);
    const w = Math.round(Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y));
    const h = Math.round(Math.hypot(pts[2].x - pts[1].x, pts[2].y - pts[1].y));
    this.stampConfig.width = Math.max(5, w);
    this.stampConfig.height = Math.max(5, h);
    this.stampConfig.orientation = (this.stampConfig.width >= this.stampConfig.height) ? 'horizontal' : 'vertical';
    this.syncStampConfigToUI();
  }
}

window.PVAnnotator = PVAnnotator;
