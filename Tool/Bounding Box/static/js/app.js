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
  let loadedSub2Data = null;
  let loadedMatchData = null;
  let loadedDualMatchData = null;
  let currentBigPath = '';
  let currentSubPath = '';
  let currentSub2Path = '';
  let matchMode = 'single'; // 'single' | 'two_subs' | 'two_subs_on_big'

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

  // Sub-Ortho 2 DOM Elements
  const btnToggleSub2 = document.getElementById('btnToggleSub2');
  const sub2CardSection = document.getElementById('sub2CardSection');
  const btnCloseSub2 = document.getElementById('btnCloseSub2');
  const sub2PathInput = document.getElementById('sub2PathInput');
  const sub2FileInput = document.getElementById('sub2FileInput');
  const btnLoadSub2 = document.getElementById('btnLoadSub2');
  const btnClearSub2Path = document.getElementById('btnClearSub2Path');
  const btnOpenSub2View = document.getElementById('btnOpenSub2View');
  const btnMatchTwoSubs = document.getElementById('btnMatchTwoSubs');
  const btnMatchTwoSubsOnBig = document.getElementById('btnMatchTwoSubsOnBig');
  const btnViewSub2 = document.getElementById('btnViewSub2');

  const opacitySlider = document.getElementById('opacitySlider');
  const opacityVal = document.getElementById('opacityVal');
  const btnToggleBBox = document.getElementById('btnToggleBBox');
  const btnToggleOverlay = document.getElementById('btnToggleOverlay');
  const btnZoomFit = document.getElementById('btnZoomFit');
  const btnZoomRegion = document.getElementById('btnZoomRegion');
  const btnSplitView = document.getElementById('btnSplitView');

  // Điều hướng & Chuyển đổi giữa Ortho To, Ortho Vùng 1 và Ortho Vùng 2
  const btnViewBig = document.getElementById('btnViewBig');
  const btnViewSub = document.getElementById('btnViewSub');
  const btnTargetBig = document.getElementById('btnTargetBig');
  const btnTargetSub = document.getElementById('btnTargetSub');
  const btnOpenSubView = document.getElementById('btnOpenSubView');
  const tabNavPV = document.getElementById('tabNavPV');
  const tabNavBBox = document.getElementById('tabNavBBox');
  const tabContentPV = document.getElementById('tabContentPV');
  const tabContentBBox = document.getElementById('tabContentBBox');
  const btnModePan = document.getElementById('btnModePan');
  const btnModeDrawPV = document.getElementById('btnModeDrawPV');
  const btnStartDrawPV = document.getElementById('btnStartDrawPV');
  const btnUndoPV = document.getElementById('btnUndoPV');

  function enableSubOrthoFeatures(subData) {
    viewer.subInfo = subData;
    if (btnViewSub) {
      btnViewSub.disabled = false;
      btnViewSub.title = `Xem ảnh Ortho Vùng 1: ${subData.file_name}`;
    }
    if (btnTargetSub) {
      btnTargetSub.disabled = false;
      btnTargetSub.title = `Làm việc trên Ortho Vùng 1: ${subData.file_name}`;
    }
    checkReadiness();
  }

  function enableSub2OrthoFeatures(sub2Data) {
    viewer.sub2Info = sub2Data;
    if (btnViewSub2) {
      btnViewSub2.style.display = 'inline-flex';
      btnViewSub2.disabled = false;
      btnViewSub2.title = `Xem ảnh Ortho Vùng 2: ${sub2Data.file_name}`;
    }
    checkReadiness();
  }

  function switchToSubOrtho() {
    if (!loadedSubData) {
      alert('Vui lòng nạp Ortho Vùng 1 trước!');
      return;
    }
    viewer.switchToSubView();
    annotator.setTarget('sub');
    if (btnViewBig) btnViewBig.classList.remove('active');
    if (btnViewSub2) btnViewSub2.classList.remove('active');
    if (btnViewSub) btnViewSub.classList.add('active');
    if (btnTargetBig) btnTargetBig.classList.remove('active');
    if (btnTargetSub) btnTargetSub.classList.add('active');
    setStatus(`Đang xem & làm việc trên Ortho Vùng 1: ${loadedSubData.file_name}`, 'success');
  }

  function switchToSub2Ortho() {
    if (!loadedSub2Data) {
      alert('Vui lòng nạp Ortho Vùng 2 trước!');
      return;
    }
    viewer.switchToSub2View();
    if (btnViewBig) btnViewBig.classList.remove('active');
    if (btnViewSub) btnViewSub.classList.remove('active');
    if (btnViewSub2) btnViewSub2.classList.add('active');
    setStatus(`Đang xem Ortho Vùng 2: ${loadedSub2Data.file_name}`, 'success');
  }

  function switchToBigOrtho() {
    if (!loadedBigData) {
      alert('Vui lòng nạp Ortho To trước!');
      return;
    }
    viewer.switchToBigView();
    annotator.setTarget('big');
    if (btnViewBig) btnViewBig.classList.add('active');
    if (btnViewSub) btnViewSub.classList.remove('active');
    if (btnViewSub2) btnViewSub2.classList.remove('active');
    if (btnTargetBig) btnTargetBig.classList.add('active');
    if (btnTargetSub) btnTargetSub.classList.remove('active');
    setStatus(`Đang xem & làm việc trên Ortho To: ${loadedBigData.file_name}`, 'success');
  }

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

  function setPVDrawMode(drawMode) {
    annotator.setMode(drawMode);
    if (btnModeDrawPV) btnModeDrawPV.classList.toggle('active', drawMode);
    if (btnModePan) btnModePan.classList.toggle('active', !drawMode);
    if (drawMode) {
      switchSidebarTab('pv');
      if (annotator.subMode === 'stamp') {
        setStatus(`Chế độ Dập Khuôn: Click chuột để đặt tấm PV ${annotator.stampConfig.width}x${annotator.stampConfig.height}px`, 'loading');
      } else {
        setStatus('Chế độ Chấm 4 Góc PV: Click lần lượt 4 góc trên ảnh để tự tính tâm centroid', 'loading');
      }
    } else {
      setStatus('Chế độ di chuyển bản đồ (Pan/Zoom)', 'ready');
    }
  }

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

    // 2b. Tùy chọn Thêm Ortho 2
    if (btnToggleSub2) {
      btnToggleSub2.addEventListener('click', () => {
        if (!sub2CardSection) return;
        const isHidden = sub2CardSection.style.display === 'none';
        sub2CardSection.style.display = isHidden ? 'block' : 'none';
        if (isHidden) {
          sub2CardSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    }

    if (btnCloseSub2) {
      btnCloseSub2.addEventListener('click', () => {
        if (sub2CardSection) sub2CardSection.style.display = 'none';
      });
    }

    if (btnLoadSub2) {
      btnLoadSub2.addEventListener('click', () => {
        const path = sub2PathInput.value.trim();
        if (sub2FileInput.files && sub2FileInput.files[0]) {
          uploadAndLoadSub2(sub2FileInput.files[0]);
        } else if (path) {
          loadSub2ByPath(path);
        } else {
          alert('Vui lòng nhập đường dẫn hoặc chọn file Ortho Vùng 2');
        }
      });
    }

    if (sub2FileInput) {
      sub2FileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          uploadAndLoadSub2(e.target.files[0]);
        }
      });
    }

    if (sub2PathInput) {
      sub2PathInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          btnLoadSub2.click();
        }
      });
    }

    if (btnClearSub2Path) {
      btnClearSub2Path.addEventListener('click', () => {
        sub2PathInput.value = '';
      });
    }

    // Nút Xác Định Vị Trí 2 Ortho Vùng
    if (btnMatchTwoSubs) {
      btnMatchTwoSubs.addEventListener('click', () => {
        executeMatchTwoSubs();
      });
    }

    // Nút Xác Định Vị Trí 2 Ortho trên Ortho To
    if (btnMatchTwoSubsOnBig) {
      btnMatchTwoSubsOnBig.addEventListener('click', () => {
        executeMatchTwoSubsOnBig();
      });
    }

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
        const contentEl = document.getElementById(targetId);
        if (contentEl) contentEl.style.display = 'block';
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
      if (loadedDualMatchData) {
        const yolo1 = loadedDualMatchData.sub1_match.yolo_format;
        const yolo2 = loadedDualMatchData.sub2_match.yolo_format;
        const combinedYOLO = `# Sub-Ortho 1: ${loadedDualMatchData.sub1_ortho.file_name}\n${yolo1}\n# Sub-Ortho 2: ${loadedDualMatchData.sub2_ortho.file_name}\n${yolo2}`;
        OrthoReader.downloadFile(combinedYOLO, "dual_sub_bboxes_yolo.txt");
      } else if (loadedMatchData && loadedMatchData.yolo_format) {
        const name = (loadedMatchData.sub_ortho ? loadedMatchData.sub_ortho.file_name : 'bbox').replace(/\.[^/.]+$/, "") + ".txt";
        OrthoReader.downloadFile(loadedMatchData.yolo_format, name);
      }
    });

    // Xuất GeoJSON
    document.getElementById('btnExportGeoJSON').addEventListener('click', () => {
      if (loadedDualMatchData && loadedDualMatchData.geojson) {
        OrthoReader.downloadFile(JSON.stringify(loadedDualMatchData.geojson, null, 2), "dual_sub_bboxes.geojson", 'application/geo+json');
      } else if (loadedMatchData && loadedMatchData.geojson) {
        const name = (loadedMatchData.sub_ortho ? loadedMatchData.sub_ortho.file_name : 'region').replace(/\.[^/.]+$/, "") + ".geojson";
        OrthoReader.downloadFile(JSON.stringify(loadedMatchData.geojson, null, 2), name, 'application/geo+json');
      }
    });

    // Cắt trích xuất GeoTIFF
    document.getElementById('btnCropGeoTIFF').addEventListener('click', () => {
      if (currentBigPath) {
        let box = null;
        if (loadedDualMatchData) {
          box = loadedDualMatchData.sub1_match.pixel_box;
        } else if (loadedMatchData && loadedMatchData.pixel_box) {
          box = loadedMatchData.pixel_box;
        }
        if (box) {
          const url = `/api/crop-download?big_path=${encodeURIComponent(currentBigPath)}&xmin=${box.xmin}&ymin=${box.ymin}&width=${box.width}&height=${box.height}&format=GTiff`;
          window.open(url, '_blank');
        }
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
    // Gắn sự kiện chuyển tab Sidebar
    if (tabNavPV) tabNavPV.addEventListener('click', () => switchSidebarTab('pv'));
    if (tabNavBBox) tabNavBBox.addEventListener('click', () => switchSidebarTab('bbox'));

    // Gắn sự kiện chuyển đổi Ortho To / Ortho Vùng
    if (btnViewBig) btnViewBig.addEventListener('click', switchToBigOrtho);
    if (btnViewSub) btnViewSub.addEventListener('click', switchToSubOrtho);
    if (btnViewSub2) btnViewSub2.addEventListener('click', switchToSub2Ortho);
    if (btnTargetBig) btnTargetBig.addEventListener('click', switchToBigOrtho);
    if (btnTargetSub) btnTargetSub.addEventListener('click', switchToSubOrtho);
    if (btnOpenSubView) {
      btnOpenSubView.addEventListener('click', () => {
        switchToSubOrtho();
        switchSidebarTab('pv');
        setPVDrawMode(true);
      });
    }
    if (btnOpenSub2View) {
      btnOpenSub2View.addEventListener('click', () => {
        switchToSub2Ortho();
        switchSidebarTab('pv');
        setPVDrawMode(true);
      });
    }

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

    if (btnModePan) btnModePan.addEventListener('click', () => setPVDrawMode(false));
    if (btnModeDrawPV) btnModeDrawPV.addEventListener('click', () => {
      const isDrawing = btnModeDrawPV.classList.contains('active');
      setPVDrawMode(!isDrawing);
    });
    if (btnStartDrawPV) btnStartDrawPV.addEventListener('click', () => setPVDrawMode(!annotator.isDrawMode));
    if (btnUndoPV) btnUndoPV.addEventListener('click', () => annotator.undo());

    // Chuyển chế độ: Chấm 4 góc vs Dải pin vs Dập khuôn
    const btnSubModeStrip = document.getElementById('btnSubModeStrip');
    if (btnSubModeStrip) btnSubModeStrip.addEventListener('click', (e) => {
      e.preventDefault();
      annotator.setSubMode('strip');
    });
    if (btnSubModeStamp) btnSubModeStamp.addEventListener('click', (e) => {
      e.preventDefault();
      annotator.setSubMode('stamp');
    });
    if (btnSubModeManual) btnSubModeManual.addEventListener('click', (e) => {
      e.preventDefault();
      annotator.setSubMode('manual');
    });

    const btnToggleChain = document.getElementById('btnToggleChain');
    if (btnToggleChain) btnToggleChain.addEventListener('click', (e) => {
      e.preventDefault();
      annotator.toggleAutoChain();
    });

    annotator.onSubModeChange = (mode) => {
      if (annotator.isDrawMode) {
        if (mode === 'stamp') {
          setStatus(`Chế độ Dập Khuôn: Click chuột để đặt tấm PV ${annotator.stampConfig.width}x${annotator.stampConfig.height}px`, 'loading');
        } else if (mode === 'strip') {
          setStatus('Chế độ Dải Pin: Chấm các điểm hàng trên, ấn Space sang hàng dưới, ấn Enter để hợp lực tạo toàn bộ dải pin', 'loading');
        } else {
          setStatus('Chế độ Chấm 4 Góc PV: Click 4 góc tự tính tâm, hoặc chấm 2 góc để tự bắt tấm liền kề', 'loading');
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
          alert('Chưa có bộ điểm nào trên bản đồ để lấy mẫu.');
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
        if (confirm('Bạn có chắc chắn muốn xóa tất cả các bộ điểm đã đánh dấu?')) {
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
    const hasBig = !!loadedBigData;
    const hasSub1 = !!(loadedSubData || currentSubPath);
    const hasSub2 = !!(loadedSub2Data || currentSub2Path);

    // 1 Sub + Big (Định vị 1 Sub)
    if (hasBig && hasSub1) {
      btnMatchRegion.classList.add('ready-pulse');
    } else {
      btnMatchRegion.classList.remove('ready-pulse');
    }

    // 2 Subs (So sánh 2 Ortho Vùng)
    if (hasSub1 && hasSub2) {
      if (btnMatchTwoSubs) {
        btnMatchTwoSubs.style.display = 'block';
        btnMatchTwoSubs.classList.add('ready-pulse');
      }
    } else {
      if (btnMatchTwoSubs) {
        btnMatchTwoSubs.style.display = 'none';
        btnMatchTwoSubs.classList.remove('ready-pulse');
      }
    }

    // 2 Subs + Big (Định vị 2 Sub trên Ortho To)
    if (hasBig && hasSub1 && hasSub2) {
      if (btnMatchTwoSubsOnBig) {
        btnMatchTwoSubsOnBig.style.display = 'block';
        btnMatchTwoSubsOnBig.classList.add('ready-pulse');
      }
      actionHint.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Đã nạp đủ cả 3 ảnh (Ortho To, Vùng 1, Vùng 2)! Sẵn sàng xác định 2 Ortho trên Ortho To.';
    } else if (hasSub1 && hasSub2) {
      if (btnMatchTwoSubsOnBig) btnMatchTwoSubsOnBig.style.display = 'none';
      actionHint.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Đã nạp 2 Ortho vùng! Bạn có thể bấm "Xác định vị trí 2 Ortho vùng" để so sánh.';
    } else if (hasBig && hasSub1) {
      if (btnMatchTwoSubsOnBig) btnMatchTwoSubsOnBig.style.display = 'none';
      actionHint.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Đã sẵn sàng Ortho To và Ortho Vùng 1! Nhấn nút để định vị Bounding Box.';
    } else {
      if (btnMatchTwoSubsOnBig) btnMatchTwoSubsOnBig.style.display = 'none';
      actionHint.innerHTML = '<i class="fa-solid fa-circle-info"></i> Sau khi nạp ảnh, các nút chức năng định vị sẽ tự động kích hoạt.';
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
      enableSubOrthoFeatures(loadedSubData);

      setStatus('Đã nạp Ortho Vùng. Có thể bấm "Xem & Đánh Dấu Trên Ortho Vùng" hoặc "Xác Định Vị Trí"!', 'success');
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
      enableSubOrthoFeatures(loadedSubData);

      setStatus('Đã nạp Ortho Vùng. Có thể bấm "Xem & Đánh Dấu Trên Ortho Vùng" hoặc "Xác Định Vị Trí"!', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadSub.disabled = false;
      btnLoadSub.innerHTML = '<i class="fa-solid fa-eye"></i> Nạp & Xem Trước Ortho Vùng';
    }
  }

  // --- BƯỚC 2b: XỬ LÝ NẠP & XEM TRƯỚC ORTHO VÙNG 2 ---
  async function loadSub2ByPath(filePath) {
    setStatus('Đang đọc Ortho Vùng 2...', 'loading');
    btnLoadSub2.disabled = true;
    btnLoadSub2.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang đọc file...';

    const formData = new FormData();
    formData.append('file_path', filePath);

    try {
      const res = await fetch('/api/load-ortho', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể đọc Ortho Vùng 2');

      currentSub2Path = filePath;
      loadedSub2Data = data.data;
      sub2PathInput.value = filePath;

      updateSub2MetaUI(loadedSub2Data);
      enableSub2OrthoFeatures(loadedSub2Data);

      setStatus('Đã nạp Ortho Vùng 2 thành công!', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadSub2.disabled = false;
      btnLoadSub2.innerHTML = '<i class="fa-solid fa-eye"></i> Nạp & Xem Trước Ortho Vùng 2';
    }
  }

  async function uploadAndLoadSub2(fileObj) {
    setStatus('Đang tải lên & đọc Ortho Vùng 2...', 'loading');
    btnLoadSub2.disabled = true;
    btnLoadSub2.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang tải lên...';
    sub2PathInput.value = `[File Upload] ${fileObj.name}`;

    const formData = new FormData();
    formData.append('file', fileObj);

    try {
      const res = await fetch('/api/load-ortho', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi tải file Ortho Vùng 2 lên');

      currentSub2Path = data.data.file_path;
      loadedSub2Data = data.data;

      updateSub2MetaUI(loadedSub2Data);
      enableSub2OrthoFeatures(loadedSub2Data);

      setStatus('Đã nạp Ortho Vùng 2 thành công!', 'success');
      checkReadiness();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      setStatus('Lỗi tải file', 'ready');
    } finally {
      btnLoadSub2.disabled = false;
      btnLoadSub2.innerHTML = '<i class="fa-solid fa-eye"></i> Nạp & Xem Trước Ortho Vùng 2';
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
      loadedDualMatchData = null;
      matchMode = 'single';
      currentSubPath = subPath || loadedMatchData.sub_ortho.file_path;

      // Cập nhật giao diện kết quả (English)
      updateSubMetaUI(loadedMatchData.sub_ortho);
      updateResultsUI(loadedMatchData, 'single');
      loadedSubData = loadedMatchData.sub_ortho;
      enableSubOrthoFeatures(loadedSubData);

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
      btnMatchRegion.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Xác Định Vị Trí Bounding Box';
    }
  }

  async function executeMatchTwoSubs() {
    const s1P = currentSubPath || subPathInput.value.trim();
    const s2P = currentSub2Path || sub2PathInput.value.trim();
    const s1File = subFileInput.files ? subFileInput.files[0] : null;
    const s2File = sub2FileInput.files ? sub2FileInput.files[0] : null;

    if (!s1P && !s1File) {
      alert('Vui lòng nạp Ortho Vùng 1 trước!');
      return;
    }
    if (!s2P && !s2File) {
      alert('Vui lòng nạp Ortho Vùng 2 trước!');
      return;
    }

    setStatus('Đang tính toán so sánh & vị trí tương quan giữa 2 Ortho vùng...', 'loading');
    btnMatchTwoSubs.disabled = true;
    btnMatchTwoSubs.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang so sánh...';

    const formData = new FormData();
    if (s1File && !currentSubPath) formData.append('sub1_file', s1File);
    else formData.append('sub1_path', s1P || currentSubPath);

    if (s2File && !currentSub2Path) formData.append('sub2_file', s2File);
    else formData.append('sub2_path', s2P || currentSub2Path);

    try {
      const res = await fetch('/api/match-two-subs', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi so sánh 2 Ortho vùng');

      loadedMatchData = data.data;
      loadedDualMatchData = null;
      matchMode = 'two_subs';

      // Cập nhật kết quả Tiếng Anh
      updateResultsUI(loadedMatchData, 'two_subs');

      // Vẽ lên viewer: canvas là Sub 1, Bbox là Sub 2
      const s1Url = `/api/preview-image?filename=${loadedMatchData.sub1_ortho.preview_filename}`;
      const s2Url = `/api/preview-image?filename=${loadedMatchData.sub2_ortho.preview_filename}`;
      viewer.displayTwoSubMatch(loadedMatchData, s1Url, s2Url);

      setStatus('Đã xác định vị trí tương quan & so sánh 2 Ortho vùng thành công!', 'success');
      actionHint.innerHTML = '<i class="fa-solid fa-check-double" style="color:#10b981;"></i> Đã so sánh & định vị 2 Ortho vùng!';
    } catch (err) {
      alert(`Lỗi so sánh: ${err.message}`);
      setStatus('Lỗi xử lý', 'ready');
    } finally {
      btnMatchTwoSubs.disabled = false;
      btnMatchTwoSubs.innerHTML = '<i class="fa-solid fa-object-ungroup"></i> Xác định vị trí 2 Ortho vùng';
    }
  }

  async function executeMatchTwoSubsOnBig() {
    const bigP = currentBigPath || bigPathInput.value.trim();
    const s1P = currentSubPath || subPathInput.value.trim();
    const s2P = currentSub2Path || sub2PathInput.value.trim();
    const s1File = subFileInput.files ? subFileInput.files[0] : null;
    const s2File = sub2FileInput.files ? sub2FileInput.files[0] : null;

    if (!bigP) {
      alert('Vui lòng nạp Ortho To trước!');
      return;
    }
    if (!s1P && !s1File) {
      alert('Vui lòng nạp Ortho Vùng 1 trước!');
      return;
    }
    if (!s2P && !s2File) {
      alert('Vui lòng nạp Ortho Vùng 2 trước!');
      return;
    }

    setStatus('Đang xác định vị trí 2 Ortho trên Ortho To...', 'loading');
    btnMatchTwoSubsOnBig.disabled = true;
    btnMatchTwoSubsOnBig.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Đang xác định vị trí...';

    const formData = new FormData();
    formData.append('big_path', bigP);
    if (s1File && !currentSubPath) formData.append('sub1_file', s1File);
    else formData.append('sub1_path', s1P || currentSubPath);

    if (s2File && !currentSub2Path) formData.append('sub2_file', s2File);
    else formData.append('sub2_path', s2P || currentSub2Path);

    try {
      const res = await fetch('/api/match-two-subs-on-big', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Lỗi khi định vị 2 Ortho trên Ortho To');

      loadedDualMatchData = data.data;
      matchMode = 'two_subs_on_big';

      // Cập nhật kết quả Tiếng Anh
      updateResultsUI(loadedDualMatchData, 'two_subs_on_big');

      // Vẽ cả 2 Bounding Box lên Ortho To
      const s1Url = `/api/preview-image?filename=${loadedDualMatchData.sub1_ortho.preview_filename}`;
      const s2Url = `/api/preview-image?filename=${loadedDualMatchData.sub2_ortho.preview_filename}`;
      viewer.displayTwoSubsOnBig(loadedDualMatchData, s1Url, s2Url);

      setStatus('Đã xác định vị trí 2 Ortho trên Ortho To thành công!', 'success');
      btnMatchTwoSubsOnBig.classList.remove('ready-pulse');
      actionHint.innerHTML = '<i class="fa-solid fa-check-double" style="color:#10b981;"></i> Đã định vị thành công 2 Ortho trên Ortho To!';
    } catch (err) {
      alert(`Lỗi xác định vị trí: ${err.message}`);
      setStatus('Lỗi xử lý', 'ready');
    } finally {
      btnMatchTwoSubsOnBig.disabled = false;
      btnMatchTwoSubsOnBig.innerHTML = '<i class="fa-solid fa-layer-group"></i> Xác định vị trí 2 Ortho trên Ortho To';
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

  function updateSub2MetaUI(info) {
    document.getElementById('sub2Badge').innerText = info.file_name;
    document.getElementById('sub2Badge').className = 'badge badge-success';
    document.getElementById('sub2MetaBox').style.display = 'flex';

    if (info.preview_filename) {
      const sub2ThumbWrapper = document.getElementById('sub2ThumbWrapper');
      const sub2Thumbnail = document.getElementById('sub2Thumbnail');
      sub2ThumbWrapper.style.display = 'block';
      sub2Thumbnail.src = `/api/preview-image?filename=${info.preview_filename}`;
    }

    document.getElementById('sub2DimVal').innerText = `${info.width.toLocaleString()} x ${info.height.toLocaleString()} px`;
    document.getElementById('sub2CrsVal').innerText = info.crs || 'Không có CRS';
    document.getElementById('sub2GsdVal').innerText = info.gsd_cm ? `${info.gsd_cm} cm/px` : 'N/A';
    document.getElementById('sub2AreaVal').innerText = info.area_ha ? `${info.area_ha.toLocaleString()} ha (${info.area_m2.toLocaleString()} m²)` : 'N/A';
  }

  function updateResultsUI(data, mode = 'single') {
    const card = document.getElementById('resultCard');
    card.style.display = 'block';

    const cardTitle = document.getElementById('resultCardTitle');
    const badge = document.getElementById('overlapBadge');
    const dualPanel = document.getElementById('dualComparePanel');
    const tableBody = document.getElementById('dualCompareTableBody');

    const mTitle1 = document.getElementById('metricTitle1');
    const mTitle2 = document.getElementById('metricTitle2');
    const mSub2 = document.getElementById('metricSub2');
    const pixelBoxVal = document.getElementById('pixelBoxVal');
    const pixelDimVal = document.getElementById('pixelDimVal');
    const gsdRatioVal = document.getElementById('gsdRatioVal');

    if (mode === 'two_subs_on_big') {
      if (cardTitle) cardTitle.innerText = "Dual Sub-Ortho Master Alignment Results";
      const b1 = data.sub1_match.pixel_box;
      const b2 = data.sub2_match.pixel_box;

      badge.innerText = `Sub 1: ${data.sub1_match.overlap_pct}% | Sub 2: ${data.sub2_match.overlap_pct}% Overlap`;
      badge.className = 'badge badge-success';

      if (mTitle1) mTitle1.innerText = "Dual Sub-Ortho Origins (Pixel)";
      if (pixelBoxVal) pixelBoxVal.innerText = `S1: (${b1.xmin.toLocaleString()}, ${b1.ymin.toLocaleString()}) | S2: (${b2.xmin.toLocaleString()}, ${b2.ymin.toLocaleString()})`;
      if (pixelDimVal) pixelDimVal.innerText = `S1: ${b1.width.toLocaleString()}x${b1.height.toLocaleString()} px | S2: ${b2.width.toLocaleString()}x${b2.height.toLocaleString()} px`;

      if (mTitle2) mTitle2.innerText = "Mutual Overlap & Separation";
      if (gsdRatioVal) gsdRatioVal.innerText = `Mutual IoU: ${data.mutual_overlap.iou_pct}%`;
      if (mSub2) mSub2.innerText = `Center Distance: ${data.comparison.center_distance_m ? data.comparison.center_distance_m + ' m' : data.comparison.center_distance_px + ' px'}`;

      // Render Comparative Specs Table in English
      if (dualPanel) dualPanel.style.display = 'block';
      if (tableBody) {
        const s1 = data.sub1_ortho;
        const s2 = data.sub2_ortho;
        const comp = data.comparison;
        tableBody.innerHTML = `
          <tr>
            <td><strong>Image Filename</strong></td>
            <td style="color: #06b6d4;">${s1.file_name}</td>
            <td style="color: #f59e0b;">${s2.file_name}</td>
            <td>Master: ${data.big_ortho.file_name}</td>
          </tr>
          <tr>
            <td><strong>Dimensions (W x H)</strong></td>
            <td>${s1.width.toLocaleString()} x ${s1.height.toLocaleString()} px</td>
            <td>${s2.width.toLocaleString()} x ${s2.height.toLocaleString()} px</td>
            <td>Diff: ${(s2.width - s1.width)} x ${(s2.height - s1.height)} px</td>
          </tr>
          <tr>
            <td><strong>Ground Resolution (GSD)</strong></td>
            <td>${s1.gsd_cm ? s1.gsd_cm + ' cm/px' : 'N/A'}</td>
            <td>${s2.gsd_cm ? s2.gsd_cm + ' cm/px' : 'N/A'}</td>
            <td>${comp.gsd_cm.ratio ? 'Ratio: 1 : ' + comp.gsd_cm.ratio : 'Equivalent'}</td>
          </tr>
          <tr>
            <td><strong>Surface Area Coverage</strong></td>
            <td>${s1.area_ha ? s1.area_ha + ' ha (' + s1.area_m2.toLocaleString() + ' m²)' : 'N/A'}</td>
            <td>${s2.area_ha ? s2.area_ha + ' ha (' + s2.area_m2.toLocaleString() + ' m²)' : 'N/A'}</td>
            <td>${comp.area_m2.area_diff_m2 ? 'Diff: ' + (comp.area_m2.area_diff_m2 / 10000).toFixed(3) + ' ha' : 'N/A'}</td>
          </tr>
          <tr>
            <td><strong>Spatial Overlap on Master</strong></td>
            <td>${data.sub1_match.overlap_pct}% coverage</td>
            <td>${data.sub2_match.overlap_pct}% coverage</td>
            <td>Mutual IoU: <strong>${data.mutual_overlap.iou_pct}%</strong></td>
          </tr>
          <tr>
            <td><strong>Center-to-Center Distance</strong></td>
            <td colspan="2" style="text-align: center;">${data.comparison.center_distance_px.toLocaleString()} px on master</td>
            <td><strong>${data.comparison.center_distance_m ? data.comparison.center_distance_m + ' m' : 'N/A'}</strong></td>
          </tr>
        `;
      }

      // Code blocks
      document.getElementById('codePixel').innerText = JSON.stringify({
        sub_ortho_1: data.sub1_match.pixel_box,
        sub_ortho_2: data.sub2_match.pixel_box,
        mutual_intersection: data.mutual_overlap.pixel_box
      }, null, 2);

      document.getElementById('codeNorm').innerText = JSON.stringify({
        sub_ortho_1: data.sub1_match.norm_box,
        sub_ortho_2: data.sub2_match.norm_box
      }, null, 2);

      document.getElementById('codeYOLO').innerText = `# Sub-Ortho 1:\n${data.sub1_match.yolo_format}\n# Sub-Ortho 2:\n${data.sub2_match.yolo_format}`;

      document.getElementById('codeGeo').innerText = JSON.stringify(data.geojson || {
        sub1_wgs84: data.sub1_match.wgs84_polygon,
        sub2_wgs84: data.sub2_match.wgs84_polygon
      }, null, 2);

    } else if (mode === 'two_subs') {
      if (cardTitle) cardTitle.innerText = "Sub-Ortho Relative Alignment Results";
      badge.innerText = `${data.overlap_pct}% Mutual Overlap (${data.method || 'Geospatial'})`;
      badge.className = data.is_overlapping ? 'badge badge-success' : 'badge badge-warning';

      const box = data.sub2_on_sub1_pixel_box || { xmin: 0, ymin: 0, width: 0, height: 0 };
      if (mTitle1) mTitle1.innerText = "Relative Placement on Sub 1 (Pixel)";
      if (pixelBoxVal) pixelBoxVal.innerText = `X: ${box.xmin.toLocaleString()}, Y: ${box.ymin.toLocaleString()}`;
      if (pixelDimVal) pixelDimVal.innerText = `W: ${box.width.toLocaleString()} px, H: ${box.height.toLocaleString()} px`;

      if (mTitle2) mTitle2.innerText = "Physical Center Distance";
      if (gsdRatioVal) gsdRatioVal.innerText = data.center_distance_m ? `${data.center_distance_m} m` : 'N/A';
      if (mSub2) mSub2.innerText = `Overlap Area: ${data.overlap_m2.toLocaleString()} m² (${data.overlap_pct}%)`;

      // Render Comparative Specs Table in English
      if (dualPanel) dualPanel.style.display = 'block';
      if (tableBody) {
        const s1 = data.sub1_ortho;
        const s2 = data.sub2_ortho;
        const comp = data.comparison;
        tableBody.innerHTML = `
          <tr>
            <td><strong>Image Filename</strong></td>
            <td style="color: #06b6d4;">${s1.file_name}</td>
            <td style="color: #f59e0b;">${s2.file_name}</td>
            <td>-</td>
          </tr>
          <tr>
            <td><strong>Dimensions (W x H)</strong></td>
            <td>${s1.width.toLocaleString()} x ${s1.height.toLocaleString()} px</td>
            <td>${s2.width.toLocaleString()} x ${s2.height.toLocaleString()} px</td>
            <td>Diff: ${(s2.width - s1.width)} x ${(s2.height - s1.height)} px</td>
          </tr>
          <tr>
            <td><strong>Ground Resolution (GSD)</strong></td>
            <td>${s1.gsd_cm ? s1.gsd_cm + ' cm/px' : 'N/A'}</td>
            <td>${s2.gsd_cm ? s2.gsd_cm + ' cm/px' : 'N/A'}</td>
            <td>${comp.gsd_cm.ratio ? 'Ratio: 1 : ' + comp.gsd_cm.ratio : 'Equivalent'}</td>
          </tr>
          <tr>
            <td><strong>Surface Area Coverage</strong></td>
            <td>${s1.area_ha ? s1.area_ha + ' ha (' + s1.area_m2.toLocaleString() + ' m²)' : 'N/A'}</td>
            <td>${s2.area_ha ? s2.area_ha + ' ha (' + s2.area_m2.toLocaleString() + ' m²)' : 'N/A'}</td>
            <td>${comp.area_m2.area_diff_m2 ? 'Diff: ' + (comp.area_m2.area_diff_m2 / 10000).toFixed(3) + ' ha' : 'N/A'}</td>
          </tr>
          <tr>
            <td><strong>Coordinate Reference System (CRS)</strong></td>
            <td>${s1.crs || 'None'}</td>
            <td>${s2.crs || 'None'}</td>
            <td>${comp.crs.is_matching ? '<span style="color:#10b981;">Matching CRS</span>' : '<span style="color:#f59e0b;">Re-projected</span>'}</td>
          </tr>
          <tr>
            <td><strong>Mutual Overlap</strong></td>
            <td>${data.overlap_pct}% of Sub 1</td>
            <td>Overlap Area: ${data.overlap_m2.toLocaleString()} m²</td>
            <td><strong>${data.is_overlapping ? 'Overlapping' : 'Non-overlapping'}</strong></td>
          </tr>
          <tr>
            <td><strong>Center-to-Center Distance</strong></td>
            <td colspan="2" style="text-align: center;">Ground geodesic distance</td>
            <td><strong>${data.center_distance_m ? data.center_distance_m + ' m' : 'N/A'}</strong></td>
          </tr>
        `;
      }

      // Code blocks
      document.getElementById('codePixel').innerText = JSON.stringify({
        sub2_on_sub1_pixel_box: data.sub2_on_sub1_pixel_box,
        sub2_on_sub1_polygon: data.sub2_on_sub1_polygon
      }, null, 2);

      document.getElementById('codeNorm').innerText = JSON.stringify(data.comparison, null, 2);
      document.getElementById('codeYOLO').innerText = `# Sub-Ortho 2 on Sub 1 canvas:\n# Overlap: ${data.overlap_pct}%\n# Center Distance: ${data.center_distance_m}m`;
      document.getElementById('codeGeo').innerText = JSON.stringify({
        sub1_wgs84: data.sub1_ortho.wgs84_bounds,
        sub2_wgs84: data.sub2_ortho.wgs84_bounds,
        center_distance_m: data.center_distance_m
      }, null, 2);

    } else {
      // Single sub on Big (Original mode)
      if (cardTitle) cardTitle.innerText = "Bounding Box Results";
      badge.innerText = `${data.overlap_pct}% Overlap (${data.method || 'Geospatial CRS'})`;
      badge.className = 'badge badge-success';

      if (dualPanel) dualPanel.style.display = 'none';

      const box = data.pixel_box;
      if (mTitle1) mTitle1.innerText = "Origin Coordinates (Pixel)";
      if (pixelBoxVal) pixelBoxVal.innerText = `X: ${box.xmin.toLocaleString()}, Y: ${box.ymin.toLocaleString()}`;
      if (pixelDimVal) pixelDimVal.innerText = `W: ${box.width.toLocaleString()} px, H: ${box.height.toLocaleString()} px`;

      if (mTitle2) mTitle2.innerText = "GSD Resolution Ratio";
      if (data.gsd_ratio) {
        if (gsdRatioVal) gsdRatioVal.innerText = `1 : ${data.gsd_ratio}`;
      } else {
        if (gsdRatioVal) gsdRatioVal.innerText = 'Equivalent (1 : 1)';
      }
      if (mSub2) mSub2.innerText = "Master / Sub ground resolution";

      document.getElementById('codePixel').innerText = OrthoReader.formatPixelJSON(data.pixel_box);
      document.getElementById('codeNorm').innerText = OrthoReader.formatNormJSON(data.norm_box);
      document.getElementById('codeYOLO').innerText = data.yolo_format;

      if (data.wgs84_polygon) {
        document.getElementById('codeGeo').innerText = JSON.stringify({
          wgs84_corners: data.wgs84_polygon,
          geo_box: data.geo_box
        }, null, 2);
      } else {
        document.getElementById('codeGeo').innerText = 'No WGS84 coordinates available';
      }
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
            <button class="btn btn-outline btn-sm select-sub-btn">Chọn làm Vùng 1</button>
            <button class="btn btn-warning btn-sm select-sub2-btn">Chọn làm Vùng 2</button>
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

        item.querySelector('.select-sub2-btn').addEventListener('click', () => {
          sub2PathInput.value = f.path;
          if (sub2CardSection) sub2CardSection.style.display = 'block';
          modal.style.display = 'none';
          loadSub2ByPath(f.path);
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
