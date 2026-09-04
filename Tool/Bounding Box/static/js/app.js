/**
 * app.js - Trình điều khiển chính cho ứng dụng OrthoScope BBox
 * Quy trình:
 * 1. Nạp/Upload Ortho To -> Hiển thị xem trước ngay lập tức trên bản đồ.
 * 2. Nạp/Upload Ortho Vùng -> Hiển thị xem trước (thumbnail) và siêu dữ liệu trong bảng.
 * 3. Nhấn "Xác Định Vị Trí" -> Tính toán và vẽ khung Bounding Box lên Ortho To.
 */

document.addEventListener('DOMContentLoaded', () => {
  const viewer = new OrthoViewer('orthoMap');
  const annotator = new PVAnnotator(viewer);
  
  // Dữ liệu trạng thái
  let loadedBigData = null;
  let loadedSubData = null;
  let loadedMatchData = null;
  let currentBigPath = '';
  let currentSubPath = '';

  // Đường dẫn mẫu sẵn có trên máy
  const SAMPLE_BIG = 'C:\\Users\\minhk\\Downloads\\Kho làm việc riêng\\Ghép 2.1\\ortho.tif';
  const SAMPLE_SUB = 'C:\\Users\\minhk\\Downloads\\Kho làm việc riêng\\Ghép 2.1\\thermal_ortho.tif';

  // DOM Elements
  const bigPathInput = document.getElementById('bigPathInput');
  const subPathInput = document.getElementById('subPathInput');
  const bigFileInput = document.getElementById('bigFileInput');
  const subFileInput = document.getElementById('subFileInput');
  const btnLoadBig = document.getElementById('btnLoadBig');
  const btnLoadSub = document.getElementById('btnLoadSub');
  const btnMatchRegion = document.getElementById('btnMatchRegion');
  const btnQuickSample = document.getElementById('btnQuickSample');
  const btnPlaceholderQuick = document.getElementById('btnPlaceholderQuick');
  const btnScanFiles = document.getElementById('btnScanFiles');
  const globalStatus = document.getElementById('globalStatus');
  const actionHint = document.getElementById('actionHint');

  const opacitySlider = document.getElementById('opacitySlider');
  const opacityVal = document.getElementById('opacityVal');
  const btnToggleBBox = document.getElementById('btnToggleBBox');
  const btnToggleOverlay = document.getElementById('btnToggleOverlay');
  const btnZoomFit = document.getElementById('btnZoomFit');
  const btnZoomRegion = document.getElementById('btnZoomRegion');
  const btnSplitView = document.getElementById('btnSplitView');

  // Khởi tạo các sự kiện
  initEventListeners();

  function initEventListeners() {
    // Nút dùng file mẫu
    if (btnQuickSample) btnQuickSample.addEventListener('click', loadSampleFiles);
    if (btnPlaceholderQuick) btnPlaceholderQuick.addEventListener('click', loadSampleFiles);

    // 1. Nạp Ortho To (Đường dẫn hoặc nút bấm)
    btnLoadBig.addEventListener('click', () => {
      const path = bigPathInput.value.trim();
      if (bigFileInput.files && bigFileInput.files[0]) {
        uploadAndLoadBig(bigFileInput.files[0]);
      } else if (path) {
        loadBigByPath(path);
      } else {
        alert('Vui lòng nhập đường dẫn hoặc chọn file Ortho To');
      }
    });

    // Tự động upload & xem trước ngay khi chọn file Ortho To
    bigFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadAndLoadBig(e.target.files[0]);
      }
    });

    // Cho phép ấn Enter ở ô đường dẫn Ortho To
    bigPathInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        btnLoadBig.click();
      }
    });

    // 2. Nạp Ortho Vùng (Đường dẫn hoặc nút bấm)
    btnLoadSub.addEventListener('click', () => {
      const path = subPathInput.value.trim();
      if (subFileInput.files && subFileInput.files[0]) {
        uploadAndLoadSub(subFileInput.files[0]);
      } else if (path) {
        loadSubByPath(path);
      } else {
        alert('Vui lòng nhập đường dẫn hoặc chọn file Ortho Vùng');
      }
    });

    // Tự động upload & xem trước ngay khi chọn file Ortho Vùng
    subFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        uploadAndLoadSub(e.target.files[0]);
      }
    });

    // Cho phép ấn Enter ở ô đường dẫn Ortho Vùng
    subPathInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        btnLoadSub.click();
      }
    });

    // 3. Nút Xác Định Vị Trí Vùng (Chỉ tính Bounding Box khi người dùng bấm nút này)
    btnMatchRegion.addEventListener('click', () => {
      const bigP = currentBigPath || bigPathInput.value.trim();
      const subP = currentSubPath || subPathInput.value.trim();
      const subFile = subFileInput.files ? subFileInput.files[0] : null;

      if (!bigP) {
        alert('Vui lòng nạp và xem trước Ortho To trước!');
        return;
      }
      if (!subP && !subFile) {
        alert('Vui lòng nạp Ortho Vùng nhỏ trước khi xác định vị trí!');
        return;
      }

      executeMatch(bigP, subP, subFile);
    });

    // Xóa nhanh input
    document.getElementById('btnClearBigPath').addEventListener('click', () => {
      bigPathInput.value = '';
    });
    document.getElementById('btnClearSubPath').addEventListener('click', () => {
      subPathInput.value = '';
    });

    // Chế độ lớp phủ trong Results Card (Hiện cả ảnh con / Chỉ hiện BBox)
    const btnModeBoth = document.getElementById('btnModeBoth');
    const btnModeOnlyBBox = document.getElementById('btnModeOnlyBBox');

    function setOverlayMode(showOverlay) {
      if (showOverlay) {
        if (btnModeBoth) btnModeBoth.classList.add('active');
        if (btnModeOnlyBBox) btnModeOnlyBBox.classList.remove('active');
        btnToggleOverlay.classList.add('active');
        btnToggleOverlay.innerHTML = '<i class="fa-solid fa-image"></i> Lớp Phủ Vùng (Bật)';
        viewer.setSubOverlayVisible(true);
        if (opacitySlider.value === '0') {
          opacitySlider.value = '85';
          opacityVal.innerText = '85%';
          viewer.setOverlayOpacity(85);
        }
      } else {
        if (btnModeBoth) btnModeBoth.classList.remove('active');
        if (btnModeOnlyBBox) btnModeOnlyBBox.classList.add('active');
        btnToggleOverlay.classList.remove('active');
        btnToggleOverlay.innerHTML = '<i class="fa-solid fa-eye-slash"></i> Lớp Phủ Vùng (Tắt)';
        viewer.setSubOverlayVisible(false);
      }
    }

    if (btnModeBoth) btnModeBoth.addEventListener('click', () => setOverlayMode(true));
    if (btnModeOnlyBBox) btnModeOnlyBBox.addEventListener('click', () => setOverlayMode(false));

    // Toolbar slider & toggles
    opacitySlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value);
      opacityVal.innerText = `${val}%`;
      viewer.setOverlayOpacity(val);
      if (val === 0) {
        setOverlayMode(false);
      } else {
        if (btnModeBoth) btnModeBoth.classList.add('active');
        if (btnModeOnlyBBox) btnModeOnlyBBox.classList.remove('active');
        btnToggleOverlay.classList.add('active');
        btnToggleOverlay.innerHTML = '<i class="fa-solid fa-image"></i> Lớp Phủ Vùng (Bật)';
        viewer.setSubOverlayVisible(true);
      }
    });

    let bboxActive = true;
    btnToggleBBox.addEventListener('click', () => {
      bboxActive = !bboxActive;
      btnToggleBBox.classList.toggle('active', bboxActive);
      viewer.toggleBBox(bboxActive);
    });

    btnToggleOverlay.addEventListener('click', () => {
      const isCurrentlyActive = btnToggleOverlay.classList.contains('active');
      setOverlayMode(!isCurrentlyActive);
    });

    // Bật/tắt chế độ siêu nét HD khi zoom
    const btnToggleHD = document.getElementById('btnToggleHD');
    let hdActive = true;
    if (btnToggleHD) {
      btnToggleHD.addEventListener('click', () => {
        hdActive = !hdActive;
        btnToggleHD.classList.toggle('active', hdActive);
        viewer.toggleHD(hdActive);
      });
    }

    btnZoomFit.addEventListener('click', () => viewer.zoomFit());
    btnZoomRegion.addEventListener('click', () => viewer.zoomToRegion());

    // Tab chuyển định dạng BBox
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
        btn.classList.add('active');
        const targetId = btn.getAttribute('data-tab');
        document.getElementById(targetId).style.display = 'block';
      });
    });

    // Nút copy clipboard
    document.querySelectorAll('.copy-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-target');
        const codeEl = document.getElementById(targetId);
        if (codeEl) {
          OrthoReader.copyToClipboard(codeEl.innerText, btn);
        }
      });
    });

    // Xuất file YOLO
    document.getElementById('btnExportYOLO').addEventListener('click', () => {
      if (loadedMatchData && loadedMatchData.yolo_format) {
        const name = (loadedMatchData.sub_ortho.file_name || 'bbox').replace(/\.[^/.]+$/, "") + ".txt";
        OrthoReader.downloadFile(loadedMatchData.yolo_format, name);
      }
    });

    // Xuất GeoJSON
    document.getElementById('btnExportGeoJSON').addEventListener('click', () => {
      if (loadedMatchData && loadedMatchData.geojson) {
        const name = (loadedMatchData.sub_ortho.file_name || 'region').replace(/\.[^/.]+$/, "") + ".geojson";
        OrthoReader.downloadFile(JSON.stringify(loadedMatchData.geojson, null, 2), name, 'application/geo+json');
      }
    });

    // Cắt trích xuất GeoTIFF
    document.getElementById('btnCropGeoTIFF').addEventListener('click', () => {
      if (loadedMatchData && currentBigPath) {
        const box = loadedMatchData.pixel_box;
        const url = `/api/crop-download?big_path=${encodeURIComponent(currentBigPath)}&xmin=${box.xmin}&ymin=${box.ymin}&width=${box.width}&height=${box.height}&format=GTiff`;
        window.open(url, '_blank');
      }
    });

    // Quét file máy
    btnScanFiles.addEventListener('click', openFilesModal);
    document.getElementById('btnCloseModal').addEventListener('click', () => {
      document.getElementById('filesModal').style.display = 'none';
    });

    // So sánh song song
    btnSplitView.addEventListener('click', openSplitModal);
    document.getElementById('btnCloseSplitModal').addEventListener('click', () => {
      document.getElementById('splitModal').style.display = 'none';
    });

    // --- PV Annotator Event Listeners (Đánh dấu tấm pin PV) ---
    const btnModePan = document.getElementById('btnModePan');
    const btnModeDrawPV = document.getElementById('btnModeDrawPV');
    const btnStartDrawPV = document.getElementById('btnStartDrawPV');
    const btnUndoPV = document.getElementById('btnUndoPV');
    const btnExportPVJSON = document.getElementById('btnExportPVJSON');
    const btnImportPVJSON = document.getElementById('btnImportPVJSON');
    const fileImportPV = document.getElementById('fileImportPV');
    const btnClearAllPV = document.getElementById('btnClearAllPV');

    // Chế độ con: Dập 1-Click vs Chấm 4 góc
    const btnSubModeStamp = document.getElementById('btnSubModeStamp');
    const btnSubModeManual = document.getElementById('btnSubModeManual');

    // Cấu hình khuôn mẫu
    const stampWidthInput = document.getElementById('stampWidthInput');
    const stampHeightInput = document.getElementById('stampHeightInput');
    const btnDecW = document.getElementById('btnDecW');
    const btnIncW = document.getElementById('btnIncW');
    const btnDecH = document.getElementById('btnDecH');
    const btnIncH = document.getElementById('btnIncH');

    const btnOrientHorizontal = document.getElementById('btnOrientHorizontal');
    const btnOrientVertical = document.getElementById('btnOrientVertical');
    const btnSwapWH = document.getElementById('btnSwapWH');

    const stampAngleSlider = document.getElementById('stampAngleSlider');
    const btnResetAngle = document.getElementById('btnResetAngle');

    const btnPickStampSize = document.getElementById('btnPickStampSize');
    const btnScaleDown = document.getElementById('btnScaleDown');
    const btnScaleUp = document.getElementById('btnScaleUp');

    // Toolbar controls
    const tbBtnSwapOrient = document.getElementById('tbBtnSwapOrient');
    const tbBtnDecSize = document.getElementById('tbBtnDecSize');
    const tbBtnIncSize = document.getElementById('tbBtnIncSize');

    // --- Sidebar Tabs Navigation (Đánh Tấm PV vs Định Vị BBox) ---
    const tabNavPV = document.getElementById('tabNavPV');
    const tabNavBBox = document.getElementById('tabNavBBox');
    const tabContentPV = document.getElementById('tabContentPV');
    const tabContentBBox = document.getElementById('tabContentBBox');

    function switchSidebarTab(tabName) {
      if (tabName === 'pv') {
        if (tabNavPV) tabNavPV.classList.add('active');
        if (tabNavBBox) tabNavBBox.classList.remove('active');
        if (tabContentPV) tabContentPV.style.display = 'flex';
        if (tabContentBBox) tabContentBBox.style.display = 'none';
      } else {
        if (tabNavBBox) tabNavBBox.classList.add('active');
        if (tabNavPV) tabNavPV.classList.remove('active');
        if (tabContentBBox) tabContentBBox.style.display = 'flex';
        if (tabContentPV) tabContentPV.style.display = 'none';
      }
    }

    if (tabNavPV) tabNavPV.addEventListener('click', () => switchSidebarTab('pv'));
    if (tabNavBBox) tabNavBBox.addEventListener('click', () => switchSidebarTab('bbox'));

    // Collapsible Card Headers (Click header để thu gọn / mở rộng)
    document.querySelectorAll('.card-collapsible-header').forEach(header => {
      header.addEventListener('click', (e) => {
        if (e.target.closest('button') || e.target.closest('.badge') || e.target.closest('input')) return;
        const card = header.closest('.card');
        if (card) {
          card.classList.toggle('collapsed');
        }
      });
    });

    function setPVDrawMode(drawMode) {
      annotator.setMode(drawMode);
      if (btnModeDrawPV) btnModeDrawPV.classList.toggle('active', drawMode);
      if (btnModePan) btnModePan.classList.toggle('active', !drawMode);
      if (drawMode) {
        switchSidebarTab('pv'); // Tự động mở tab PV khi bắt đầu đánh
        if (annotator.subMode === 'stamp') {
          setStatus(`Chế độ Dập 1-Click: Click chuột để đặt ngay tấm PV ${annotator.stampConfig.width}x${annotator.stampConfig.height}px`, 'loading');
        } else {
          setStatus('Chế độ đánh dấu tấm PV: Click lần lượt 4 góc trên ảnh Ortho To', 'loading');
        }
      } else {
        setStatus('Chế độ di chuyển bản đồ (Pan/Zoom)', 'ready');
      }
    }

    if (btnModePan) btnModePan.addEventListener('click', () => setPVDrawMode(false));
    if (btnModeDrawPV) btnModeDrawPV.addEventListener('click', () => {
      const isDrawing = btnModeDrawPV.classList.contains('active');
      setPVDrawMode(!isDrawing);
    });
    if (btnStartDrawPV) btnStartDrawPV.addEventListener('click', () => setPVDrawMode(!annotator.isDrawMode));
    if (btnUndoPV) btnUndoPV.addEventListener('click', () => annotator.undo());

    // Chuyển chế độ 1-Click vs Manual 4-Point
    if (btnSubModeStamp) btnSubModeStamp.addEventListener('click', (e) => {
      e.preventDefault();
      annotator.setSubMode('stamp');
    });
    if (btnSubModeManual) btnSubModeManual.addEventListener('click', (e) => {
      e.preventDefault();
      annotator.setSubMode('manual');
    });

    annotator.onSubModeChange = (mode) => {
      if (annotator.isDrawMode) {
        if (mode === 'stamp') {
          setStatus(`Chế độ Dập 1-Click: Click chuột để đặt ngay tấm PV ${annotator.stampConfig.width}x${annotator.stampConfig.height}px`, 'loading');
        } else {
          setStatus('Chế độ đánh dấu tấm PV: Click lần lượt 4 góc trên ảnh Ortho To', 'loading');
        }
      }
    };

    // Cập nhật Width & Height từ ô input
    if (stampWidthInput) {
      stampWidthInput.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        if (val > 0) {
          annotator.stampConfig.width = val;
          annotator.stampConfig.orientation = (annotator.stampConfig.width >= annotator.stampConfig.height) ? 'horizontal' : 'vertical';
          annotator.syncStampConfigToUI();
        }
      });
    }
    if (stampHeightInput) {
      stampHeightInput.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        if (val > 0) {
          annotator.stampConfig.height = val;
          annotator.stampConfig.orientation = (annotator.stampConfig.width >= annotator.stampConfig.height) ? 'horizontal' : 'vertical';
          annotator.syncStampConfigToUI();
        }
      });
    }

    // Tăng giảm nhanh +-5px
    if (btnDecW) btnDecW.addEventListener('click', () => annotator.adjustDimensions(-5, 0));
    if (btnIncW) btnIncW.addEventListener('click', () => annotator.adjustDimensions(5, 0));
    if (btnDecH) btnDecH.addEventListener('click', () => annotator.adjustDimensions(0, -5));
    if (btnIncH) btnIncH.addEventListener('click', () => annotator.adjustDimensions(0, 5));

    // Chọn hướng Ngang / Dọc
    if (btnOrientHorizontal) btnOrientHorizontal.addEventListener('click', () => annotator.setOrientation('horizontal'));
    if (btnOrientVertical) btnOrientVertical.addEventListener('click', () => annotator.setOrientation('vertical'));
    if (btnSwapWH) btnSwapWH.addEventListener('click', () => annotator.toggleOrientation());

    // Toolbar Stamp buttons
    if (tbBtnSwapOrient) tbBtnSwapOrient.addEventListener('click', () => annotator.toggleOrientation());
    if (tbBtnDecSize) tbBtnDecSize.addEventListener('click', () => annotator.scaleStamp(0.9));
    if (tbBtnIncSize) tbBtnIncSize.addEventListener('click', () => annotator.scaleStamp(1.1));

    // Góc xoay
    if (stampAngleSlider) {
      stampAngleSlider.addEventListener('input', (e) => annotator.setAngle(e.target.value));
    }
    if (btnResetAngle) {
      btnResetAngle.addEventListener('click', () => annotator.setAngle(0));
    }

    // Phóng to / thu nhỏ khuôn mẫu 10%
    if (btnScaleDown) btnScaleDown.addEventListener('click', () => annotator.scaleStamp(0.9));
    if (btnScaleUp) btnScaleUp.addEventListener('click', () => annotator.scaleStamp(1.1));

    // Hút mẫu kích thước từ tấm pin đã có
    if (btnPickStampSize) {
      btnPickStampSize.addEventListener('click', () => {
        if (annotator.panels.length === 0) {
          alert('Chưa có tấm PV nào trên bản đồ để lấy mẫu. Vui lòng vẽ ít nhất 1 tấm trước!');
          return;
        }
        const lastPanel = annotator.panels[annotator.panels.length - 1];
        annotator.pickSizeFromPanel(lastPanel.id);
      });
    }

    if (btnExportPVJSON) btnExportPVJSON.addEventListener('click', () => annotator.exportJSON());

    if (btnImportPVJSON && fileImportPV) {
      btnImportPVJSON.addEventListener('click', () => fileImportPV.click());
      fileImportPV.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          const file = e.target.files[0];
          const reader = new FileReader();
          reader.onload = (event) => {
            annotator.importJSON(event.target.result);
            fileImportPV.value = '';
          };
          reader.readAsText(file);
        }
      });
    }

    if (btnClearAllPV) {
      btnClearAllPV.addEventListener('click', () => {
        if (confirm('Bạn có chắc chắn muốn xóa tất cả các tấm PV đã đánh dấu?')) {
          annotator.clearAll();
        }
      });
    }
  }

  function setStatus(text, type = 'ready') {
    const txt = globalStatus.querySelector('.status-text');
    const dot = globalStatus.querySelector('.status-dot');
    txt.innerText = text;
    if (type === 'loading') {
      dot.style.backgroundColor = '#f59e0b';
    } else if (type === 'success') {
      dot.style.backgroundColor = '#10b981';
    } else {
      dot.style.backgroundColor = '#06b6d4';
    }
  }

  function checkReadiness() {
    if (loadedBigData && (loadedSubData || currentSubPath)) {
      btnMatchRegion.classList.add('ready-pulse');
      actionHint.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Đã sẵn sàng cả 2 ảnh! Nhấn nút trên để xác định Bounding Box.';
    } else {
      btnMatchRegion.classList.remove('ready-pulse');
      actionHint.innerHTML = '<i class="fa-solid fa-circle-info"></i> Sau khi nạp Ortho To và Ortho Vùng, nhấn nút trên để định vị Bounding Box.';
    }
  }

  // --- BƯỚC 1: XỬ LÝ NẠP & XEM TRƯỚC ORTHO TO ---
  async function loadBigByPath(filePath) {
    setStatus('Đang phân tích Ortho To...', 'loading');
    btnLoadBig.disabled = true;
    btnLoadBig.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang đọc file...';

    const formData = new FormData();
    formData.append('file_path', filePath);

    try {
      const res = await fetch('/api/load-ortho', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể đọc Ortho To');

      currentBigPath = filePath;
      loadedBigData = data.data;
      bigPathInput.value = filePath;

      // Xóa BBox cũ nếu có
      viewer.clearBoundingBox();
      document.getElementById('resultCard').style.display = 'none';

      updateBigMetaUI(loadedBigData);
      const previewUrl = `/api/preview-image?filename=${loadedBigData.preview_filename}`;
      
      // Hiển thị ngay lập tức ảnh to lên bản đồ để xem trước
      viewer.loadBigOrtho(loadedBigData, previewUrl);

      setStatus('Đã nạp Ortho To (Đang xem trước trên bản đồ)', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadBig.disabled = false;
      btnLoadBig.innerHTML = '<i class="fa-solid fa-mountain-sun"></i> Nạp & Xem Trước Ortho To';
    }
  }

  async function uploadAndLoadBig(fileObj) {
    setStatus('Đang tải lên & phân tích Ortho To...', 'loading');
    btnLoadBig.disabled = true;
    btnLoadBig.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang tải lên...';
    bigPathInput.value = `[File Upload] ${fileObj.name}`;

    const formData = new FormData();
    formData.append('file', fileObj);

    try {
      const res = await fetch('/api/load-ortho', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi tải file lên');

      currentBigPath = data.data.file_path;
      loadedBigData = data.data;

      // Xóa BBox cũ nếu có
      viewer.clearBoundingBox();
      document.getElementById('resultCard').style.display = 'none';

      updateBigMetaUI(loadedBigData);
      const previewUrl = `/api/preview-image?filename=${loadedBigData.preview_filename}`;
      
      // Hiển thị ngay lập tức ảnh to lên bản đồ
      viewer.loadBigOrtho(loadedBigData, previewUrl);

      setStatus('Đã tải lên Ortho To (Đang xem trước trên bản đồ)', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadBig.disabled = false;
      btnLoadBig.innerHTML = '<i class="fa-solid fa-mountain-sun"></i> Nạp & Xem Trước Ortho To';
    }
  }

  // --- BƯỚC 2: XỬ LÝ NẠP & XEM TRƯỚC ORTHO VÙNG NHỎ ---
  async function loadSubByPath(filePath) {
    setStatus('Đang đọc Ortho Vùng...', 'loading');
    btnLoadSub.disabled = true;
    btnLoadSub.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang đọc file...';

    const formData = new FormData();
    formData.append('file_path', filePath);

    try {
      const res = await fetch('/api/load-ortho', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể đọc Ortho Vùng');

      currentSubPath = filePath;
      loadedSubData = data.data;
      subPathInput.value = filePath;

      // Cập nhật thông tin và thumbnail xem trước của Ortho Vùng
      updateSubMetaUI(loadedSubData);

      setStatus('Đã nạp Ortho Vùng. Nhấn "Xác Định Vị Trí" để định vị!', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadSub.disabled = false;
      btnLoadSub.innerHTML = '<i class="fa-solid fa-eye"></i> Nạp & Xem Trước Ortho Vùng';
    }
  }

  async function uploadAndLoadSub(fileObj) {
    setStatus('Đang tải lên & đọc Ortho Vùng...', 'loading');
    btnLoadSub.disabled = true;
    btnLoadSub.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang tải lên...';
    subPathInput.value = `[File Upload] ${fileObj.name}`;

    const formData = new FormData();
    formData.append('file', fileObj);

    try {
      const res = await fetch('/api/load-ortho', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi tải file Ortho Vùng lên');

      currentSubPath = data.data.file_path;
      loadedSubData = data.data;

      // Cập nhật thông tin và thumbnail xem trước của Ortho Vùng
      updateSubMetaUI(loadedSubData);

      setStatus('Đã nạp Ortho Vùng. Nhấn "Xác Định Vị Trí" để định vị!', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadSub.disabled = false;
      btnLoadSub.innerHTML = '<i class="fa-solid fa-eye"></i> Nạp & Xem Trước Ortho Vùng';
    }
  }

  // --- BƯỚC 3: XÁC ĐỊNH VỊ TRÍ & VẼ BOUNDING BOX ---
  async function executeMatch(bigPath, subPath, subFile) {
    setStatus('Đang tính toán Bounding Box...', 'loading');
    btnMatchRegion.disabled = true;
    btnMatchRegion.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang xác định vị trí...';

    const formData = new FormData();
    formData.append('big_path', bigPath);
    if (subFile && !currentSubPath) {
      formData.append('sub_file', subFile);
    } else {
      formData.append('sub_path', subPath || currentSubPath);
    }

    try {
      const res = await fetch('/api/match-region', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi xác định vùng');

      loadedMatchData = data.data;
      currentSubPath = subPath || loadedMatchData.sub_ortho.file_path;

      // Cập nhật giao diện kết quả
      updateSubMetaUI(loadedMatchData.sub_ortho);
      updateResultsUI(loadedMatchData);

      // Bây giờ mới vẽ Bounding Box và xếp lớp phủ lên Ortho To
      const subPreviewUrl = `/api/preview-image?filename=${loadedMatchData.sub_ortho.preview_filename}`;
      viewer.displayBoundingBox(loadedMatchData, subPreviewUrl);

      // Tự động zoom nhẹ đến vị trí Bounding Box
      viewer.zoomToRegion();

      setStatus('Đã xác định vị trí Bounding Box thành công!', 'success');
      btnMatchRegion.classList.remove('ready-pulse');
      actionHint.innerHTML = '<i class="fa-solid fa-check-double" style="color:#10b981;"></i> Đã định vị thành công Bounding Box!';
    } catch (err) {
      alert(`Lỗi xác định vùng: ${err.message}`);
      setStatus('Lỗi xử lý', 'ready');
    } finally {
      btnMatchRegion.disabled = false;
      btnMatchRegion.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Xác Định Vị Trí Trên Ortho To';
    }
  }

  function updateBigMetaUI(info) {
    document.getElementById('bigBadge').innerText = info.file_name;
    document.getElementById('bigBadge').className = 'badge badge-success';
    document.getElementById('bigMetaBox').style.display = 'flex';

    document.getElementById('bigDimVal').innerText = `${info.width.toLocaleString()} x ${info.height.toLocaleString()} px`;
    document.getElementById('bigCrsVal').innerText = info.crs || 'Không có CRS';
    document.getElementById('bigGsdVal').innerText = info.gsd_cm ? `${info.gsd_cm} cm/px` : 'N/A';
    document.getElementById('bigAreaVal').innerText = info.area_ha ? `${info.area_ha.toLocaleString()} ha (${info.area_m2.toLocaleString()} m²)` : 'N/A';
    document.getElementById('bigSizeVal').innerText = `${info.file_size_mb} MB`;
  }

  function updateSubMetaUI(info) {
    document.getElementById('subBadge').innerText = info.file_name;
    document.getElementById('subBadge').className = 'badge badge-success';
    document.getElementById('subMetaBox').style.display = 'flex';

    // Hiển thị thumbnail xem trước
    if (info.preview_filename) {
      const subThumbWrapper = document.getElementById('subThumbWrapper');
      const subThumbnail = document.getElementById('subThumbnail');
      subThumbWrapper.style.display = 'block';
      subThumbnail.src = `/api/preview-image?filename=${info.preview_filename}`;
    }

    document.getElementById('subDimVal').innerText = `${info.width.toLocaleString()} x ${info.height.toLocaleString()} px`;
    document.getElementById('subCrsVal').innerText = info.crs || 'Không có CRS';
    document.getElementById('subGsdVal').innerText = info.gsd_cm ? `${info.gsd_cm} cm/px` : 'N/A';
    document.getElementById('subAreaVal').innerText = info.area_ha ? `${info.area_ha.toLocaleString()} ha (${info.area_m2.toLocaleString()} m²)` : 'N/A';
  }

  function updateResultsUI(data) {
    const card = document.getElementById('resultCard');
    card.style.display = 'block';

    // Badge Overlap
    const badge = document.getElementById('overlapBadge');
    badge.innerText = `${data.overlap_pct}% Trùng khớp (${data.method})`;

    // Metrics
    const box = data.pixel_box;
    document.getElementById('pixelBoxVal').innerText = `X: ${box.xmin.toLocaleString()}, Y: ${box.ymin.toLocaleString()}`;
    document.getElementById('pixelDimVal').innerText = `W: ${box.width.toLocaleString()} px, H: ${box.height.toLocaleString()} px`;

    if (data.gsd_ratio) {
      document.getElementById('gsdRatioVal').innerText = `1 : ${data.gsd_ratio}`;
    } else {
      document.getElementById('gsdRatioVal').innerText = 'Tương đương';
    }

    // Tabs content
    document.getElementById('codePixel').innerText = OrthoReader.formatPixelJSON(data.pixel_box);
    document.getElementById('codeNorm').innerText = OrthoReader.formatNormJSON(data.norm_box);
    document.getElementById('codeYOLO').innerText = data.yolo_format;
    
    if (data.wgs84_polygon) {
      document.getElementById('codeGeo').innerText = JSON.stringify({
        wgs84_corners: data.wgs84_polygon,
        geo_box: data.geo_box
      }, null, 2);
    } else {
      document.getElementById('codeGeo').innerText = 'Không có thông tin WGS84';
    }
  }

  async function loadSampleFiles() {
    // Nạp xem trước Ortho To trước
    bigPathInput.value = SAMPLE_BIG;
    await loadBigByPath(SAMPLE_BIG);

    // Nạp xem trước Ortho Vùng
    subPathInput.value = SAMPLE_SUB;
    await loadSubByPath(SAMPLE_SUB);

    // Báo cho người dùng biết đã nạp xong 2 file và mời bấm nút xác định
    setStatus('Đã nạp xong 2 file mẫu. Hãy bấm "Xác Định Vị Trí Trên Ortho To"!', 'success');
  }

  async function openFilesModal() {
    const modal = document.getElementById('filesModal');
    const container = document.getElementById('quickFilesContainer');
    modal.style.display = 'flex';
    container.innerHTML = '<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Đang tìm kiếm file trong hệ thống...</div>';

    try {
      const res = await fetch('/api/quick-files');
      const data = await res.json();
      container.innerHTML = '';

      if (!data.files || data.files.length === 0) {
        container.innerHTML = '<p class="text-muted">Không tìm thấy file GeoTIFF trong thư mục quét.</p>';
        return;
      }

      data.files.forEach(f => {
        const item = document.createElement('div');
        item.className = 'file-item';
        item.innerHTML = `
          <div class="file-info">
            <span class="file-name">${f.name}</span>
            <span class="file-meta">Dung lượng: ${f.size_mb} MB | Thư mục: ${f.dir}</span>
          </div>
          <div class="file-actions">
            <button class="btn btn-secondary btn-sm select-big-btn">Chọn làm Ortho To</button>
            <button class="btn btn-outline btn-sm select-sub-btn">Chọn làm Vùng</button>
          </div>
        `;

        item.querySelector('.select-big-btn').addEventListener('click', () => {
          bigPathInput.value = f.path;
          modal.style.display = 'none';
          loadBigByPath(f.path);
        });

        item.querySelector('.select-sub-btn').addEventListener('click', () => {
          subPathInput.value = f.path;
          modal.style.display = 'none';
          loadSubByPath(f.path);
        });

        container.appendChild(item);
      });
    } catch (e) {
      container.innerHTML = `<p class="text-danger">Lỗi quét file: ${e.message}</p>`;
    }
  }

  function openSplitModal() {
    if (!loadedMatchData) {
      alert('Vui lòng xác định vị trí Bounding Box trước khi mở so sánh!');
      return;
    }
    const modal = document.getElementById('splitModal');
    modal.style.display = 'flex';

    const bigCropImg = document.getElementById('splitBigCrop');
    const subImg = document.getElementById('splitSubImg');

    const box = loadedMatchData.pixel_box;
    bigCropImg.src = `/api/crop-download?big_path=${encodeURIComponent(currentBigPath)}&xmin=${box.xmin}&ymin=${box.ymin}&width=${box.width}&height=${box.height}&format=PNG`;
    subImg.src = `/api/preview-image?filename=${loadedMatchData.sub_ortho.preview_filename}`;
  }
});
