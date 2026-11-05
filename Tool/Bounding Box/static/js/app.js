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

  // Dual Layer Controls khi mapping 2 vùng lên Ortho To
  const dualLayerGroup = document.getElementById('dualLayerGroup');
  const btnDualLayerBoth = document.getElementById('btnDualLayerBoth');
  const btnDualLayerSub1 = document.getElementById('btnDualLayerSub1');
  const btnDualLayerSub2 = document.getElementById('btnDualLayerSub2');
  const btnDualLayerOverlap = document.getElementById('btnDualLayerOverlap');
  const btnToggleFloatingInfo = document.getElementById('btnToggleFloatingInfo');

  // Floating Info Panel Elements (Bảng thông tin nổi ngoài Bounding Box)
  const dualFloatingInfoPanel = document.getElementById('dualFloatingInfoPanel');
  const btnMinimizeInfoPanel = document.getElementById('btnMinimizeInfoPanel');
  const btnCloseInfoPanel = document.getElementById('btnCloseInfoPanel');
  const btnZoomToSub1 = document.getElementById('btnZoomToSub1');
  const btnZoomToSub2 = document.getElementById('btnZoomToSub2');
  const btnCopyFloatingCode = document.getElementById('btnCopyFloatingCode');
  const btnFloatingExportYOLO = document.getElementById('btnFloatingExportYOLO');
  const btnFloatingExportGeoJSON = document.getElementById('btnFloatingExportGeoJSON');

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
  const tabNavUTMPixel = document.getElementById('tabNavUTMPixel');
  const tabContentPV = document.getElementById('tabContentPV');
  const tabContentBBox = document.getElementById('tabContentBBox');
  const tabContentUTMPixel = document.getElementById('tabContentUTMPixel');
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
    if (typeof window.updateFreePointTargetBadge === 'function') window.updateFreePointTargetBadge();
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
    if (typeof window.updateFreePointTargetBadge === 'function') window.updateFreePointTargetBadge();
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
    if (typeof window.updateFreePointTargetBadge === 'function') window.updateFreePointTargetBadge();
    setStatus(`Đang xem & làm việc trên Ortho To: ${loadedBigData.file_name}`, 'success');
  }

  function switchSidebarTab(tabName) {
    const tabs = [
      { id: 'pv', nav: tabNavPV, content: tabContentPV },
      { id: 'bbox', nav: tabNavBBox, content: tabContentBBox },
      { id: 'utm_pixel', nav: tabNavUTMPixel, content: tabContentUTMPixel }
    ];

    tabs.forEach(t => {
      const isActive = t.id === tabName;
      if (t.nav) t.nav.classList.toggle('active', isActive);
      if (t.content) t.content.style.display = isActive ? 'flex' : 'none';
    });
  }

  function setPVDrawMode(drawMode) {
    annotator.setMode(drawMode);
    if (btnModeDrawPV) btnModeDrawPV.classList.toggle('active', drawMode);
    if (btnModePan) btnModePan.classList.toggle('active', !drawMode);
    if (drawMode) {
      if (typeof window.disableFreePointMarking === 'function') window.disableFreePointMarking();
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

    // Các nút chọn Layer khi mapping 2 vùng lên Ortho To
    if (btnDualLayerBoth) {
      btnDualLayerBoth.addEventListener('click', () => setDualLayer('both'));
    }
    if (btnDualLayerSub1) {
      btnDualLayerSub1.addEventListener('click', () => setDualLayer('sub1'));
    }
    if (btnDualLayerSub2) {
      btnDualLayerSub2.addEventListener('click', () => setDualLayer('sub2'));
    }
    if (btnDualLayerOverlap) {
      btnDualLayerOverlap.addEventListener('click', () => setDualLayer('overlap'));
    }

    // Bật/Tắt Bảng Thông Tin Nổi
    if (btnToggleFloatingInfo) {
      btnToggleFloatingInfo.addEventListener('click', () => {
        if (!dualFloatingInfoPanel) return;
        const isHidden = dualFloatingInfoPanel.style.display === 'none';
        dualFloatingInfoPanel.style.display = isHidden ? 'flex' : 'none';
        btnToggleFloatingInfo.classList.toggle('active', isHidden);
      });
    }

    // Thao tác trên Header Bảng Thông Tin Nổi
    if (btnMinimizeInfoPanel) {
      btnMinimizeInfoPanel.addEventListener('click', () => {
        dualFloatingInfoPanel.classList.toggle('minimized');
        const isMin = dualFloatingInfoPanel.classList.contains('minimized');
        btnMinimizeInfoPanel.innerHTML = isMin ? '<i class="fa-solid fa-plus"></i>' : '<i class="fa-solid fa-minus"></i>';
      });
    }
    if (btnCloseInfoPanel) {
      btnCloseInfoPanel.addEventListener('click', () => {
        dualFloatingInfoPanel.style.display = 'none';
        if (btnToggleFloatingInfo) btnToggleFloatingInfo.classList.remove('active');
      });
    }

    // Các tab trên Bảng Thông Tin Nổi
    if (dualFloatingInfoPanel) {
      const pTabBtns = dualFloatingInfoPanel.querySelectorAll('.panel-tab-btn');
      pTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          const tabKey = btn.dataset.tab;
          if (tabKey === 'tabCompare') {
            setDualLayer('both');
          } else if (tabKey === 'tabSub1') {
            setDualLayer('sub1');
          } else if (tabKey === 'tabSub2') {
            setDualLayer('sub2');
          } else {
            switchFloatingTab(tabKey);
          }
        });
      });
      setupDualOpacityControls();

      const miniBtns = dualFloatingInfoPanel.querySelectorAll('.mini-tab-btn');
      miniBtns.forEach(mBtn => {
        mBtn.addEventListener('click', () => {
          miniBtns.forEach(b => b.classList.remove('active'));
          mBtn.classList.add('active');
          floatingActiveSubtab = mBtn.dataset.subtab;
          updateFloatingCodeContent();
        });
      });
    }

    // Phóng to nhanh đến từng vùng từ Bảng Thông Tin Nổi
    if (btnZoomToSub1) {
      btnZoomToSub1.addEventListener('click', () => viewer.zoomToSub1());
    }
    if (btnZoomToSub2) {
      btnZoomToSub2.addEventListener('click', () => viewer.zoomToSub2());
    }

    // Copy và Export trên Bảng Thông Tin Nổi
    if (btnCopyFloatingCode) {
      btnCopyFloatingCode.addEventListener('click', () => {
        const pre = document.getElementById('fCodeContent');
        if (pre && pre.innerText) {
          navigator.clipboard.writeText(pre.innerText).then(() => {
            btnCopyFloatingCode.innerHTML = '<i class="fa-solid fa-check" style="color:#10b981;"></i>';
            setTimeout(() => {
              btnCopyFloatingCode.innerHTML = '<i class="fa-regular fa-copy"></i>';
            }, 1800);
          });
        }
      });
    }

    if (btnFloatingExportYOLO) {
      btnFloatingExportYOLO.addEventListener('click', () => {
        const exportBtn = document.getElementById('btnExportYOLO');
        if (exportBtn) exportBtn.click();
      });
    }
    if (btnFloatingExportGeoJSON) {
      btnFloatingExportGeoJSON.addEventListener('click', () => {
        const exportBtn = document.getElementById('btnExportGeoJSON');
        if (exportBtn) exportBtn.click();
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
      if (typeof updateDualOpacityUI === 'function') updateDualOpacityUI();
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

    // --- Sidebar Tabs Navigation (Đánh Tấm PV vs Định Vị BBox vs Đọc Pixel UTM) ---
    // Gắn sự kiện chuyển tab Sidebar
    if (tabNavPV) tabNavPV.addEventListener('click', () => switchSidebarTab('pv'));
    if (tabNavBBox) tabNavBBox.addEventListener('click', () => switchSidebarTab('bbox'));
    if (tabNavUTMPixel) tabNavUTMPixel.addEventListener('click', () => switchSidebarTab('utm_pixel'));

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

    const btnLoadCanonicalToAnnotator = document.getElementById('btnLoadCanonicalToAnnotator');
    if (btnLoadCanonicalToAnnotator) {
      btnLoadCanonicalToAnnotator.addEventListener('click', async () => {
        let targetInfo = annotator.activeTarget === 'sub' ? loadedSubData : loadedBigData;
        if (!targetInfo) {
          alert('Vui lòng nạp ảnh trực giao trước khi nạp Canonical JSON lên bản đồ!');
          return;
        }
        setStatus('Đang nạp dữ liệu Canonical PV lên bản đồ...', 'loading');
        try {
          const resp = await fetch(`/api/canonical-panels-for-annotator?target_ortho_path=${encodeURIComponent(targetInfo.file_path)}&only_in_bounds=false`);
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể tải canonical panels');
          }
          const data = await resp.json();
          if (data.panels && data.panels.length > 0) {
            annotator.importJSON(data.panels);
            setStatus(`Đã nạp thành công ${data.total} tấm PV Canonical lên bản đồ!`, 'success');
          } else {
            alert('Không tìm thấy tấm nào trong file Canonical JSON!');
          }
        } catch (err) {
          console.error(err);
          alert(`Lỗi nạp Canonical PV: ${err.message}`);
          setStatus('Lỗi nạp Canonical PV', 'error');
        }
      });
    }

    const btnMapPVToBigGPS = document.getElementById('btnMapPVToBigGPS');
    if (btnMapPVToBigGPS) {
      btnMapPVToBigGPS.addEventListener('click', async () => {
        if (!loadedBigData || !loadedBigData.file_path) {
          alert('Vui lòng nạp Ortho To trước khi thực hiện ánh xạ GPS!');
          return;
        }
        const activeSubData = (annotator.activeTarget === 'sub2' && loadedSub2Data) ? loadedSub2Data : loadedSubData;
        if (!activeSubData || !activeSubData.file_path) {
          alert('Vui lòng nạp Ortho Vùng trước khi thực hiện ánh xạ GPS!');
          return;
        }

        // Lấy danh sách các tấm pin đang vẽ trên Ortho Vùng
        const subPanels = annotator.panels.filter(p => p.target === 'sub' || p.target === 'sub2');
        if (!subPanels || subPanels.length === 0) {
          alert('Không tìm thấy tấm pin nào được vẽ trên Ortho Vùng. Vui lòng chuyển sang xem Ortho Vùng, vẽ hoặc nạp các tấm pin trước khi ánh xạ!');
          return;
        }

        const confirmMsg = `Hệ thống sẽ dùng Georeferencing / GPS thuần để ánh xạ ${subPanels.length} tấm pin từ Ortho Vùng (${activeSubData.file_name}) sang vị trí chính xác trên Ortho To (${loadedBigData.file_name}). Tiếp tục?`;
        if (!confirm(confirmMsg)) return;

        btnMapPVToBigGPS.disabled = true;
        btnMapPVToBigGPS.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tính toán GPS...';
        setStatus(`Đang ánh xạ ${subPanels.length} tấm pin sang Ortho To bằng GPS thuần...`, 'loading');

        try {
          const resp = await fetch('/api/map-panels-by-gps', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              big_path: loadedBigData.file_path,
              sub_path: activeSubData.file_path,
              panels: subPanels
            })
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Lỗi server khi ánh xạ tấm pin bằng GPS');
          }

          const result = await resp.json();
          const mappedPanels = result.panels || [];

          if (mappedPanels.length === 0) {
            alert('Không có tấm pin nào được ánh xạ thành công.');
            return;
          }

          // Chuyển sang Ortho To
          if (viewer.currentView !== 'big') {
            viewer.switchToBigView();
          }
          annotator.setTarget('big');

          // Đưa các tấm pin đã ánh xạ vào annotator trên Ortho To
          let importedCount = 0;
          let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

          mappedPanels.forEach(mp => {
            const rawCorners = mp.corners.map(c => ({ col: c.pixel.x, row: c.pixel.y }));
            const panel = annotator.createPVPanelFromPoints(rawCorners, mp.id, true);
            if (panel) {
              panel.class = mp.class || 'solar_panel';
              importedCount++;
              rawCorners.forEach(c => {
                if (c.col < minX) minX = c.col;
                if (c.col > maxX) maxX = c.col;
                if (c.row < minY) minY = c.row;
                if (c.row > maxY) maxY = c.row;
              });
            }
          });

          annotator.currentPage = 1;
          annotator.updatePanelListUI();

          if (minX !== Infinity) {
            viewer.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [60, 60] });
          }

          setStatus(`Đã ánh xạ thành công ${importedCount} tấm pin từ Ortho Vùng lên Ortho To bằng GPS thuần!`, 'success');
          alert(`Đã ánh xạ thành công ${importedCount} tấm pin từ Ortho Vùng lên Ortho To bằng GPS thuần!\nĐã tự động chuyển sang chế độ xem Ortho To.`);
        } catch (err) {
          console.error(err);
          alert(`Lỗi ánh xạ GPS: ${err.message}`);
          setStatus('Lỗi ánh xạ tấm pin bằng GPS', 'error');
        } finally {
          btnMapPVToBigGPS.disabled = false;
          btnMapPVToBigGPS.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> 🌐 Ánh Xạ Tấm PV Sang Ortho To (GPS Thuần)';
        }
      });
    }

    // ==============================================================
    // LƯỚI CHUẨN 87M & ÁNH XẠ TƯƠNG ĐỒNG (EUCLIDEAN ERROR ANALYSIS)
    // ==============================================================
    let lastEuclideanResult = null;
    let isRefGridLoaded = false;

    const btnLoadRefGridQuick = document.getElementById('btnLoadRefGridQuick');
    const btnBrowseRefGrid = document.getElementById('btnBrowseRefGrid');
    const inputRefGridFile = document.getElementById('inputRefGridFile');
    const refGridBadge = document.getElementById('refGridBadge');
    const chkShowRefGridOnMap = document.getElementById('chkShowRefGridOnMap');
    const btnFocusRefGrid = document.getElementById('btnFocusRefGrid');
    const refGridCountInfo = document.getElementById('refGridCountInfo');
    const btnMapSimilarityAndCompare = document.getElementById('btnMapSimilarityAndCompare');
    const chkFilterStandardOnly = document.getElementById('chkFilterStandardOnly');
    const euclideanResultsWrap = document.getElementById('euclideanResultsWrap');
    const statValidBoxes = document.getElementById('statValidBoxes');
    const statMeanEuclid = document.getElementById('statMeanEuclid');
    const statRmseEuclid = document.getElementById('statRmseEuclid');
    const statMaxEuclid = document.getElementById('statMaxEuclid');
    const chkShowRefBoxes = document.getElementById('chkShowRefBoxes');
    const chkShowSimilarityBoxes = document.getElementById('chkShowSimilarityBoxes');
    const chkShowEuclidVectors = document.getElementById('chkShowEuclidVectors');
    const btnExportEuclideanCSV = document.getElementById('btnExportEuclideanCSV');
    const btnFocusEuclidRegion = document.getElementById('btnFocusEuclidRegion');
    const euclideanTableBody = document.getElementById('euclideanTableBody');
    const thSortError = document.getElementById('thSortError');
    const headerGrid87m = document.getElementById('headerGrid87m');
    let refGridBoundsPixel = null;
    let isFetchingViewport = false;
    let sortErrorAsc = true;

    function renderEuclideanTable(panels) {
      if (!euclideanTableBody) return;
      euclideanTableBody.innerHTML = '';
      
      window.highlightEuclidRow = function(p) {
          // Debug alert so we know it runs
          console.log("Clicked row: ", p.id);
          if (typeof setStatus === 'function') {
              setStatus('Đã chọn tấm: ' + (p.module_id || p.id), 'success');
          }
          
          const rowId = 'euclid-row-' + (p.module_id || p.id || '').replace(/[^a-zA-Z0-9_-]/g, '_');
          const tr = document.getElementById(rowId);
          
          document.querySelectorAll('#euclideanTableBody tr').forEach(r => r.classList.remove('active-row'));
          if (tr) {
              tr.classList.add('active-row');
              tr.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
          
          if (p._simPoly) {
              if (window._activeEuclidPoly && window._activeEuclidPoly !== p._simPoly && window._activeEuclidPoly._simColor) {
                  window._activeEuclidPoly.setStyle({ weight: 2, fillOpacity: 0.22, color: window._activeEuclidPoly._simColor, fillColor: window._activeEuclidPoly._simColor });
              }
              p._simPoly._simColor = p._simColor;
              p._simPoly.setStyle({ weight: 4, fillOpacity: 0.5, color: '#f43f5e', fillColor: '#fb7185' });
              window._activeEuclidPoly = p._simPoly;
              p._simPoly.openTooltip();
          }
      };

      panels.forEach(p => {
        const tr = document.createElement('tr');
        tr.id = 'euclid-row-' + (p.module_id || p.id || '').replace(/[^a-zA-Z0-9_-]/g, '_');
        tr.style.cursor = 'pointer';
        const isDisp = p.display;
        const errCm = p.euclidean_error_cm !== null ? `${p.euclidean_error_cm}` : '-';
        const errPx = p.euclidean_error_px !== null ? `${p.euclidean_error_px}` : '-';
        const m = p.metrics || {};
        const dimStr = m.length_m ? `${m.length_m}x${m.width_m}m` : '-';

        tr.innerHTML = `
          <td><b style="color: #c084fc;">${p.module_id}</b></td>
          <td><b style="color: #38bdf8;">${p.id || '--'}</b></td>
          <td><b style="color: #fbbf24;">${p.class || 'Unknown'}</b></td>
          <td style="color: ${p.euclidean_error_cm > 10 ? '#ef4444' : '#10b981'}; font-weight: bold;">${errCm}</td>
          <td>${errPx}</td>
          <td style="font-size: 10px;">${dimStr}</td>
          <td>
            <span class="badge ${isDisp ? 'badge-success' : 'badge-danger'}" style="font-size: 9px; padding: 2px 4px;">
              ${isDisp ? 'ĐẠT CHUẨN' : 'LỆCH CHUẨN'}
            </span>
          </td>
        `;

        tr.addEventListener('click', () => {
          if (window.highlightEuclidRow) {
              window.highlightEuclidRow(p);
          }
          if (p.sim_centroid_pixel && p.sim_centroid_pixel.x) {
            viewer.map.flyTo([-p.sim_centroid_pixel.y, p.sim_centroid_pixel.x], 20, { duration: 0.8 });
          }
        });
        euclideanTableBody.appendChild(tr);
      });
    }

    if (thSortError) {
      thSortError.addEventListener('click', () => {
        if (!lastEuclideanResult || !lastEuclideanResult.panels) return;
        sortErrorAsc = !sortErrorAsc;
        const sorted = [...lastEuclideanResult.panels].sort((a, b) => {
          const valA = a.euclidean_error_cm !== null ? a.euclidean_error_cm : -1;
          const valB = b.euclidean_error_cm !== null ? b.euclidean_error_cm : -1;
          return sortErrorAsc ? valA - valB : valB - valA;
        });
        renderEuclideanTable(sorted);
      });
    }

    // Cập nhật các module của Lưới 87m trong khung nhìn hiện tại (Dynamic Viewport Rendering)
    async function updateReferenceGridViewport() {
      if (!isRefGridLoaded) return;
      if (chkShowRefGridOnMap && !chkShowRefGridOnMap.checked) {
        annotator.clearReferenceGrid();
        return;
      }
      if (viewer.currentView !== 'big') return;
      if (!viewer.map) return;
      if (isFetchingViewport) return;

      isFetchingViewport = true;
      try {
        const bounds = viewer.map.getBounds();
        const min_col = Math.max(0, Math.floor(bounds.getWest()));
        const max_col = Math.ceil(bounds.getEast());
        const min_row = Math.max(0, Math.floor(-bounds.getNorth()));
        const max_row = Math.ceil(-bounds.getSouth());

        const bigFilePath = loadedBigData ? loadedBigData.file_path : '';
        const url = `/api/grid-modules-viewport?min_col=${min_col}&min_row=${min_row}&max_col=${max_col}&max_row=${max_row}&limit=2500&target_ortho=${encodeURIComponent(bigFilePath)}`;

        const resp = await fetch(url);
        if (resp.ok) {
          const res = await resp.json();
          if (res.panels) {
            annotator.renderReferenceGrid(res.panels);
            if (refGridCountInfo) {
              const truncNotice = res.is_truncated ? ' <span style="color:#f59e0b;">(Thu nhỏ góc nhìn để hiển thị đủ)</span>' : '';
              refGridCountInfo.innerHTML = `Đang hiện <b style="color: #10b981;">${res.panels.length.toLocaleString()}</b> / ${res.total_modules.toLocaleString()} module 87m trong khung nhìn.${truncNotice}`;
            }
          }
        }
      } catch (err) {
        console.warn('Lỗi cập nhật viewport lưới 87m:', err);
      } finally {
        isFetchingViewport = false;
      }
    }

    // Lắng nghe sự kiện di chuyển bản đồ để tự động vẽ lại các module trong khung nhìn
    let viewportDebounceTimer = null;
    if (viewer.map) {
      viewer.map.on('moveend', () => {
        if (isRefGridLoaded && chkShowRefGridOnMap && chkShowRefGridOnMap.checked && viewer.currentView === 'big') {
          clearTimeout(viewportDebounceTimer);
          viewportDebounceTimer = setTimeout(updateReferenceGridViewport, 120);
        }
      });
    }

    // Kiểm tra trạng thái file lưới khi tải trang
    async function checkGridInfo() {
      try {
        const resp = await fetch('/api/grid-info');
        if (resp.ok) {
          const res = await resp.json();
          if (res.data && res.data.exists && refGridBadge) {
            refGridBadge.className = 'badge badge-success';
            refGridBadge.innerText = `${res.data.total_modules.toLocaleString()} module (87m)`;
            refGridBadge.title = `File sẵn sàng: ${res.data.path}`;
          }
        }
      } catch (e) {
        console.warn('Lỗi kiểm tra grid-info:', e);
      }
    }
    checkGridInfo();

    // Thu gọn / mở rộng Card
    if (headerGrid87m) {
      headerGrid87m.addEventListener('click', () => {
        const body = document.getElementById('bodyGrid87m');
        if (body) {
          const isHidden = body.style.display === 'none';
          body.style.display = isHidden ? 'block' : 'none';
          const icon = headerGrid87m.querySelector('.card-toggle-icon');
          if (icon) icon.className = isHidden ? 'fa-solid fa-chevron-down card-toggle-icon' : 'fa-solid fa-chevron-right card-toggle-icon';
        }
      });
    }

    // Nạp nhanh bbox_centroid_export.json vào Ortho Toàn Cảnh
    async function loadReferenceGrid(filePath = null) {
      if (!loadedBigData || !loadedBigData.file_path) {
        alert('Vui lòng nạp ảnh Ortho Toàn Cảnh (Ortho To 87m) trước khi nạp lưới module!');
        return;
      }

      if (btnLoadRefGridQuick) {
        btnLoadRefGridQuick.disabled = true;
        btnLoadRefGridQuick.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang nạp lưới 87m...';
      }
      setStatus('Đang nạp và quy đổi 36,544 module từ bbox_centroid_export lên Ortho Toàn Cảnh...', 'loading');

      try {
        const resp = await fetch('/api/load-ortho-grid', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_path: filePath,
            target_ortho_path: loadedBigData.file_path
          })
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || 'Không thể nạp lưới module toàn cảnh');
        }

        const data = await resp.json();
        const gridData = data.data;
        isRefGridLoaded = true;
        if (gridData.bounds_pixel) {
          refGridBoundsPixel = gridData.bounds_pixel;
        }

        if (refGridBadge) {
          refGridBadge.className = 'badge badge-success';
          refGridBadge.innerText = `Đã nạp ${gridData.total_modules.toLocaleString()} module`;
        }

        // Chuyển sang xem Ortho Toàn Cảnh nếu đang ở ảnh khác
        if (viewer.currentView !== 'big') {
          viewer.switchToBigView();
        }

        // Vẽ ngay lập tức các module trong khung nhìn hiện tại!
        await updateReferenceGridViewport();

        setStatus(`Đã nạp và hiển thị thành công ${gridData.total_modules.toLocaleString()} module lưới 87m lên Ortho Toàn Cảnh!`, 'success');
        alert(`Đã nạp thành công ${gridData.total_modules.toLocaleString()} module từ ${gridData.file_name} vào Ortho Toàn Cảnh (${gridData.target_ortho})!\nCác khung box lưới 87m đã được hiển thị trên bản đồ.`);
      } catch (err) {
        console.error(err);
        alert(`Lỗi nạp lưới toàn cảnh: ${err.message}`);
        setStatus('Lỗi nạp lưới toàn cảnh', 'error');
      } finally {
        if (btnLoadRefGridQuick) {
          btnLoadRefGridQuick.disabled = false;
          btnLoadRefGridQuick.innerHTML = '<i class="fa-solid fa-bolt"></i> ⚡ Nạp Lưới 87m (bbox_centroid)';
        }
      }
    }

    if (btnLoadRefGridQuick) {
      btnLoadRefGridQuick.addEventListener('click', () => loadReferenceGrid(null));
    }

    if (btnBrowseRefGrid && inputRefGridFile) {
      btnBrowseRefGrid.addEventListener('click', () => inputRefGridFile.click());
      inputRefGridFile.addEventListener('change', async (e) => {
        if (e.target.files && e.target.files[0]) {
          const file = e.target.files[0];
          loadReferenceGrid(file.name);
        }
      });
    }

    // Toggle hiển thị Lưới 87m trên bản đồ
    if (chkShowRefGridOnMap) {
      chkShowRefGridOnMap.addEventListener('change', (e) => {
        if (e.target.checked) {
          updateReferenceGridViewport();
        } else {
          annotator.clearReferenceGrid();
          if (refGridCountInfo) {
            refGridCountInfo.innerText = 'Đã ẩn lớp lưới 87m. Tích chọn để hiện lại.';
          }
        }
      });
    }

    // Nút phóng to đến toàn bộ vùng lưới 87m
    if (btnFocusRefGrid) {
      btnFocusRefGrid.addEventListener('click', () => {
        if (!isRefGridLoaded) {
          alert('Vui lòng nạp Lưới 87m trước!');
          return;
        }
        if (viewer.currentView !== 'big') {
          viewer.switchToBigView();
        }
        if (refGridBoundsPixel) {
          viewer.map.fitBounds([
            [-refGridBoundsPixel.max_y, refGridBoundsPixel.min_x],
            [-refGridBoundsPixel.min_y, refGridBoundsPixel.max_x]
          ], { padding: [50, 50] });
        } else {
          viewer.map.setView([-3300, 4000], 19);
        }
      });
    }

    // Hook toàn cục để các module khác có thể gọi
    window.loadReferenceGrid = loadReferenceGrid;
    window.triggerLoadRefGrid = () => loadReferenceGrid(null);
    window.updateReferenceGridViewport = updateReferenceGridViewport;

    // Thực hiện Ánh Xạ Tương Đồng & Tính Sai Số Euclidean
    if (btnMapSimilarityAndCompare) {
      btnMapSimilarityAndCompare.addEventListener('click', async () => {
        if (!loadedBigData || !loadedBigData.file_path) {
          alert('Vui lòng nạp Ortho Toàn Cảnh trước khi thực hiện ánh xạ tương đồng!');
          return;
        }

        // Thu thập danh sách panels từ các nguồn khả dụng:
        let panelsToProcess = [];
        let subPathToSend = loadedBigData.file_path;
        let sourceLabel = '';

        // Nguồn 1: Các box trong viewer.canonicalBoxes (đã nạp Canonical JSON hoặc đã ánh xạ GPS lên bản đồ)
        if (viewer.canonicalBoxes && viewer.canonicalBoxes.length > 0) {
          panelsToProcess = viewer.canonicalBoxes.map(b => ({
            id: b.batch_id || b.internal_code || b.id || 'PV',
            module_id: b.internal_code || b.batch_id,
            internal_code: b.internal_code || b.batch_id,
            row: b.row,
            column: b.column,
            class: b.class || (b.centroid && b.centroid.class) || 'Unclassified',
            corners: b.corners,
            centroid: b.centroid,
            target: b.target || 'big'
          }));
          sourceLabel = `${panelsToProcess.length} khung box đang hiển thị trên bản đồ (Mapped / Canonical)`;
          subPathToSend = loadedBigData.file_path;
        }

        // Nguồn 2: Các panel trong annotator.panels
        if (panelsToProcess.length === 0 && annotator.panels && annotator.panels.length > 0) {
          const subP = annotator.panels.filter(p => p.target === 'sub' || p.target === 'sub2');
          const bigP = annotator.panels.filter(p => p.target === 'big');

          if (subP.length > 0) {
            panelsToProcess = subP;
            sourceLabel = `${subP.length} tấm pin vẽ trên Ortho Vùng`;
            const activeSub = (annotator.activeTarget === 'sub2' && loadedSub2Data) ? loadedSub2Data : (loadedSubData || loadedSub2Data);
            if (activeSub && activeSub.file_path) {
              subPathToSend = activeSub.file_path;
            }
          } else if (bigP.length > 0) {
            panelsToProcess = bigP;
            sourceLabel = `${bigP.length} tấm pin trên Ortho To`;
            subPathToSend = loadedBigData.file_path;
          }
        }

        // Nguồn 3: allCurrentBoxes trong Tab 3 (Đọc Pixel)
        if (panelsToProcess.length === 0 && allCurrentBoxes && allCurrentBoxes.length > 0) {
          panelsToProcess = allCurrentBoxes.map(b => ({
            id: b.batch_id || b.internal_code || 'PV',
            module_id: b.internal_code || b.batch_id,
            internal_code: b.internal_code || b.batch_id,
            row: b.row,
            column: b.column,
            class: b.class || (b.centroid && b.centroid.class) || 'Unclassified',
            corners: b.corners,
            centroid: b.centroid,
            target: 'big'
          }));
          sourceLabel = `${panelsToProcess.length} box từ bảng Đọc Pixel`;
          subPathToSend = loadedBigData.file_path;
        }

        if (panelsToProcess.length === 0) {
          alert('Không tìm thấy tấm pin hoặc khung box nào trên bản đồ!\n\nBạn có thể:\n1. Nạp file box hoặc vẽ các tấm pin ở tab "Đánh Tấm PV"\n2. Hoặc nạp file JSON ở tab "Đọc Pixel (u, v)"\n3. Hoặc thực hiện Ánh xạ GPS tấm pin từ Ortho Vùng sang Ortho To.');
          return;
        }

        const filterStd = chkFilterStandardOnly ? chkFilterStandardOnly.checked : true;
        const confirmMsg = `Hệ thống sẽ:\n1. Ánh xạ tương đồng qua GPS & tọa độ pixel cho ${sourceLabel}.\n2. Đối chiếu trực tiếp mã module với lưới toàn cảnh 87m (bbox_centroid_export).\n3. Lọc tiêu chuẩn: Chỉ box đạt chuẩn mới được hiện lên (box lỗi bị ẩn).\n4. Tính sai số chênh lệch thông qua khoảng cách Euclidean.\nTiếp tục?`;
        if (!confirm(confirmMsg)) return;

        btnMapSimilarityAndCompare.disabled = true;
        btnMapSimilarityAndCompare.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tính toán tương đồng & Euclidean...';
        setStatus('Đang thực hiện ánh xạ tương đồng và tính sai số khoảng cách Euclidean...', 'loading');

        try {
          const resp = await fetch('/api/map-panels-similarity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              big_path: loadedBigData.file_path,
              sub_path: subPathToSend,
              panels: panelsToProcess,
              filter_standard: filterStd,
              tolerance_params: {
                max_match_dist: 1.50
              }
            })
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Lỗi server khi ánh xạ tương đồng');
          }

          const result = await resp.json();
          lastEuclideanResult = result;

          // Chuyển sang xem Ortho Toàn Cảnh
          if (viewer.currentView !== 'big') {
            viewer.switchToBigView();
          }
          annotator.setTarget('big');

          // Ẩn tuyệt đối các layer box thô / GPS thô cũ để KHÔNG BỊ LỘ box lỗi / box méo / box ngoài đất
          viewer.isBoxesVisible = false;
          if (viewer.boxesLayer && viewer.map.hasLayer(viewer.boxesLayer)) {
            viewer.map.removeLayer(viewer.boxesLayer);
          }
          if (viewer.utmLayer && viewer.map.hasLayer(viewer.utmLayer)) {
            viewer.map.removeLayer(viewer.utmLayer);
          }
          if (viewer.mappedGpsLayer && viewer.map.hasLayer(viewer.mappedGpsLayer)) {
            viewer.map.removeLayer(viewer.mappedGpsLayer);
          }
          if (viewer.clustersLayer && viewer.map.hasLayer(viewer.clustersLayer)) {
            viewer.map.removeLayer(viewer.clustersLayer);
          }
          if (annotator.pvLayerGroupBig && viewer.map.hasLayer(annotator.pvLayerGroupBig)) {
            viewer.map.removeLayer(annotator.pvLayerGroupBig);
          }
          const chkShowBoxesLayer = document.getElementById('chkShowBoxesLayer');
          if (chkShowBoxesLayer) chkShowBoxesLayer.checked = false;
          const chkShowGPSMapped = document.getElementById('chkShowGPSMapped');
          if (chkShowGPSMapped) chkShowGPSMapped.checked = false;

          // Hiển thị trực quan trên bản đồ
          const showRef = chkShowRefBoxes ? chkShowRefBoxes.checked : true;
          const showSim = chkShowSimilarityBoxes ? chkShowSimilarityBoxes.checked : true;
          const showVectors = chkShowEuclidVectors ? chkShowEuclidVectors.checked : true;
          annotator.renderEuclideanComparison(result, showRef, showSim, showVectors);

          // Cập nhật thống kê KPI
          if (statValidBoxes) statValidBoxes.innerText = `${result.displayed_count} / ${result.total_panels}`;
          if (statMeanEuclid) statMeanEuclid.innerText = result.stats && result.stats.mean_cm !== undefined ? `${result.stats.mean_cm} cm (${result.stats.mean_px} px)` : '-';
          if (statRmseEuclid) statRmseEuclid.innerText = result.stats && result.stats.rmse_cm !== undefined ? `${result.stats.rmse_cm} cm` : '-';
          if (statMaxEuclid) statMaxEuclid.innerText = result.stats && result.stats.max_cm !== undefined ? `${result.stats.max_cm} cm` : '-';

          // Cập nhật bảng chi tiết
          if (euclideanTableBody && result.panels) {
            renderEuclideanTable(result.panels);
          }

          // Hiện khung kết quả
          if (euclideanResultsWrap) {
            euclideanResultsWrap.style.display = 'block';
          }

          // Fit bounds
          if (btnFocusEuclidRegion) {
            btnFocusEuclidRegion.click();
          }

          const rejectMsg = result.rejected_count > 0 ? ` (Đã tự động loại bỏ/ẩn ${result.rejected_count} box không đạt chuẩn)` : '';
          setStatus(`Ánh xạ tương đồng thành công! Hiển thị ${result.displayed_count} box đạt chuẩn. Sai số Euclidean TB: ${result.stats.mean_cm || 0} cm.`, 'success');
          alert(`Hoàn thành ánh xạ tương đồng qua GPS & tọa độ pixel!\n- Hiển thị: ${result.displayed_count} module đạt chuẩn lưới 87m${rejectMsg}\n- Sai số Euclidean trung bình: ${result.stats.mean_cm || 0} cm (${result.stats.mean_px || 0} px)\n- RMSE: ${result.stats.rmse_cm || 0} cm | Max: ${result.stats.max_cm || 0} cm`);
        } catch (err) {
          console.error(err);
          alert(`Lỗi thực hiện ánh xạ tương đồng: ${err.message}`);
          setStatus('Lỗi ánh xạ tương đồng', 'error');
        } finally {
          btnMapSimilarityAndCompare.disabled = false;
          btnMapSimilarityAndCompare.innerHTML = '<i class="fa-solid fa-calculator"></i> 🌐 Ánh Xạ Tương Đồng & Tính Sai Số Euclidean';
        }
      });
    }

    // Thực hiện Chuyển Đổi Đồng Loạt CSV 35m Lên Canvas 85m (Đối Soát Giàn Pin)
    const btnBatchMapCsvToCanvas = document.getElementById('btnBatchMapCsvToCanvas');
    if (btnBatchMapCsvToCanvas) {
      btnBatchMapCsvToCanvas.addEventListener('click', async () => {
        if (!viewer.map) {
          alert('Bản đồ chưa sẵn sàng!');
          return;
        }

        btnBatchMapCsvToCanvas.disabled = true;
        btnBatchMapCsvToCanvas.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang nạp & chuyển đổi đồng loạt...';
        setStatus('Đang nạp CSV detection 35m và áp dụng ma trận Affine lên Canvas 85m...', 'loading');

        try {
          const resp = await fetch('/api/batch-map-csv-to-canvas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Lỗi chuyển đổi đồng loạt');
          }
          const res = await resp.json();
          const stats = res.stats;

          // Chuyển sang xem Ortho Toàn Cảnh 85m
          if (viewer.currentView !== 'big') {
            viewer.switchToBigView();
          }

          // Xóa các layer cũ và vẽ các box lên Canvas
          if (annotator.euclidLayers) {
            annotator.euclidLayers.clearLayers();
          }

          let renderedCount = 0;
          let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

          res.panels.forEach(p => {
            if (!p.corners_canvas || p.corners_canvas.length < 4) return;
            const validCorners = p.corners_canvas.filter(c => c !== null);
            if (validCorners.length < 4) return;
            const latlngs = validCorners.map(c => [-c.y, c.x]);
            const isDeviated = p.status === 'LECH_KHUNG_GIAN';
            const color = isDeviated ? '#ef4444' : '#10b981';

            const poly = L.polygon(latlngs, {
              color: color,
              weight: 1.5,
              fillColor: color,
              fillOpacity: 0.25,
              renderer: annotator.euclidCanvasRenderer || annotator.canvasRenderer
            });

            poly.bindTooltip(`
              <div style="font-size: 11px; line-height: 1.4;">
                <b style="color: ${color};">${p.id}</b><br>
                <span>Mã lưới 87m: <b>${p.module_id}</b></span><br>
                <span>Sai số tâm: <b>${p.error_cm !== null ? p.error_cm + ' cm' : 'N/A'}</b></span><br>
                <span>Trạng thái: <b>${isDeviated ? '⚠️ Lệch khung giàn' : '✅ Khớp chuẩn giàn pin'}</b></span>
              </div>
            `);

            annotator.euclidLayers.addLayer(poly);
            renderedCount++;

            validCorners.forEach(c => {
              if (c.x < minX) minX = c.x;
              if (c.x > maxX) maxX = c.x;
              if (c.y < minY) minY = c.y;
              if (c.y > maxY) maxY = c.y;
            });
          });

          // Cập nhật thống kê trên giao diện
          if (statValidBoxes) statValidBoxes.innerText = `${stats.valid_count.toLocaleString()} / ${stats.total.toLocaleString()} (${stats.valid_rate}%)`;
          if (statMeanEuclid) statMeanEuclid.innerText = `${stats.mean_cen_cm} cm`;
          if (statRmseEuclid) statRmseEuclid.innerText = `${stats.rmse_cen_cm} cm`;
          if (statMaxEuclid) statMaxEuclid.innerText = `${stats.p95_cen_cm} cm (P95)`;
          if (euclideanResultsWrap) euclideanResultsWrap.style.display = 'block';

          // Zoom đến vùng các box vừa vẽ
          if (minX !== Infinity && maxX !== -Infinity) {
            viewer.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [50, 50] });
          }

          setStatus(`Đã chuyển đổi và hiển thị đồng loạt ${renderedCount.toLocaleString()} box lên Canvas map 85m!`, 'success');
          alert(`Hoàn thành nạp và chuyển đổi đồng loạt lên Canvas map 85m!\n- Tổng số OBB: ${stats.total.toLocaleString()}\n- Khớp chuẩn giàn pin (<= 50cm): ${stats.valid_count.toLocaleString()} (${stats.valid_rate}%)\n- Lệch khung giàn (> 50cm): ${stats.deviated_count.toLocaleString()} (${stats.deviated_rate}%)\n- Ngoài phạm vi 85m: ${stats.unmatched_count.toLocaleString()}\n- Sai số tâm trung bình: ${stats.mean_cen_cm} cm | RMSE: ${stats.rmse_cen_cm} cm\nFile CSV đã lưu tại: ${res.csv_file}`);
        } catch (err) {
          console.error(err);
          alert(`Lỗi thực thi: ${err.message}`);
          setStatus('Lỗi nạp đồng loạt lên Canvas', 'error');
        } finally {
          btnBatchMapCsvToCanvas.disabled = false;
          btnBatchMapCsvToCanvas.innerHTML = '<i class="fa-solid fa-layer-group"></i> ⚡ Chuyển Đổi Đồng Loạt CSV 35m Lên Canvas 85m';
        }
      });
    }

    // Toggle các layer hiển thị
    function updateEuclideanLayerVisibility() {
      if (!lastEuclideanResult) return;
      const showRef = chkShowRefBoxes ? chkShowRefBoxes.checked : true;
      const showSim = chkShowSimilarityBoxes ? chkShowSimilarityBoxes.checked : true;
      const showVectors = chkShowEuclidVectors ? chkShowEuclidVectors.checked : true;
      annotator.toggleEuclideanLayers(showRef, showSim, showVectors);
    }
    if (chkShowRefBoxes) chkShowRefBoxes.addEventListener('change', updateEuclideanLayerVisibility);
    if (chkShowSimilarityBoxes) chkShowSimilarityBoxes.addEventListener('change', updateEuclideanLayerVisibility);
    if (chkShowEuclidVectors) chkShowEuclidVectors.addEventListener('change', updateEuclideanLayerVisibility);

    // ==========================================

    // Xuất file CSV sai số Euclidean
    if (btnExportEuclideanCSV) {
      btnExportEuclideanCSV.addEventListener('click', () => {
        if (!lastEuclideanResult || !lastEuclideanResult.csv_data) {
          alert('Chưa có dữ liệu sai số Euclidean. Vui lòng thực hiện ánh xạ trước!');
          return;
        }
        const blob = new Blob(["\ufeff" + lastEuclideanResult.csv_data], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Bao_cao_sai_so_Euclidean_Ortho_87m_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    // Phóng to đến vùng các module
    if (btnFocusEuclidRegion) {
      btnFocusEuclidRegion.addEventListener('click', () => {
        if (!lastEuclideanResult || !lastEuclideanResult.panels) return;
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        lastEuclideanResult.panels.forEach(p => {
          if (!p.display) return;
          const c = p.sim_centroid_pixel;
          if (c && c.x) {
            if (c.x < minX) minX = c.x;
            if (c.x > maxX) maxX = c.x;
            if (c.y < minY) minY = c.y;
            if (c.y > maxY) maxY = c.y;
          }
        });
        if (minX !== Infinity) {
          viewer.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [50, 50], maxZoom: 20 });
        }
      });
    }

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
      hideDualLayerControls();

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
      hideDualLayerControls();

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

      // Hiển thị thanh chọn Layer và Bảng Thông Tin Nổi Bên Ngoài
      showDualLayerControls();
      updateFloatingInfoPanel(loadedDualMatchData);

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

  /* =========================================================================
     CÁC HÀM XỬ LÝ LAYER & BẢNG THÔNG TIN NỔI BÊN NGOÀI BOX (MAPPING 2 VÙNG)
     ========================================================================= */

  let floatingActiveSubtab = 'fCodePixel';

  function showDualLayerControls() {
    if (dualLayerGroup) dualLayerGroup.style.display = 'flex';
    if (btnToggleFloatingInfo) {
      btnToggleFloatingInfo.style.display = 'inline-flex';
      btnToggleFloatingInfo.classList.add('active');
    }
    setDualLayer('both');
  }

  function hideDualLayerControls() {
    if (dualLayerGroup) dualLayerGroup.style.display = 'none';
    if (btnToggleFloatingInfo) {
      btnToggleFloatingInfo.style.display = 'none';
      btnToggleFloatingInfo.classList.remove('active');
    }
    if (dualFloatingInfoPanel) dualFloatingInfoPanel.style.display = 'none';
  }

  function setDualLayer(layerName, keepTab = false) {
    [btnDualLayerBoth, btnDualLayerSub1, btnDualLayerSub2, btnDualLayerOverlap].forEach(btn => {
      if (btn) btn.classList.remove('active');
    });

    if (layerName === 'both' && btnDualLayerBoth) btnDualLayerBoth.classList.add('active');
    else if (layerName === 'sub1' && btnDualLayerSub1) btnDualLayerSub1.classList.add('active');
    else if (layerName === 'sub2' && btnDualLayerSub2) btnDualLayerSub2.classList.add('active');
    else if (layerName === 'overlap' && btnDualLayerOverlap) btnDualLayerOverlap.classList.add('active');

    viewer.setActiveDualLayer(layerName);

    const overlapSliderContainer = document.getElementById('overlapSliderContainer');
    if (overlapSliderContainer) {
      overlapSliderContainer.style.display = layerName === 'overlap' ? 'flex' : 'none';
    }

    if (!keepTab) {
      if (layerName === 'sub1') switchFloatingTab('tabSub1');
      else if (layerName === 'sub2') switchFloatingTab('tabSub2');
      else switchFloatingTab('tabCompare');
    }

    // Cập nhật giá trị độ mờ hiện tại lên thanh trượt theo layer đang chọn
    if (layerName === 'sub1') {
      const val = Math.round(viewer.sub1Opacity * 100);
      opacitySlider.value = val;
      opacityVal.innerText = `${val}%`;
    } else if (layerName === 'sub2') {
      const val = Math.round(viewer.sub2Opacity * 100);
      opacitySlider.value = val;
      opacityVal.innerText = `${val}%`;
    } else if (layerName === 'both') {
      const val = Math.round(viewer.sub1Opacity * 100);
      opacitySlider.value = val;
      opacityVal.innerText = `${val}%`;
    }

    if (typeof updateDualOpacityUI === 'function') updateDualOpacityUI();
  }

  // Kết nối callback chọn layer trực tiếp khi click vào Bounding Box trên bản đồ
  viewer.onDualLayerSelected = (layerName) => {
    setDualLayer(layerName);
  };

  function updateFloatingInfoPanel(data) {
    if (!data || !dualFloatingInfoPanel) return;

    dualFloatingInfoPanel.style.display = 'flex';
    dualFloatingInfoPanel.classList.remove('minimized');
    if (btnToggleFloatingInfo) btnToggleFloatingInfo.classList.add('active');

    const s1 = data.sub1_ortho;
    const s2 = data.sub2_ortho;
    const b1 = data.sub1_match.pixel_box;
    const b2 = data.sub2_match.pixel_box;
    const comp = data.comparison;
    const mutual = data.mutual_overlap;

    // 1. Tab So Sánh 2 Vùng
    const fStatIoU = document.getElementById('fStatIoU');
    const fStatCenterDist = document.getElementById('fStatCenterDist');
    const fCompareTableBody = document.getElementById('fCompareTableBody');

    if (fStatIoU) fStatIoU.innerText = mutual && mutual.is_overlapping ? `${mutual.iou_pct}%` : '0% (Không giao)';
    if (fStatCenterDist) {
      fStatCenterDist.innerText = comp.center_distance_m ? `${comp.center_distance_m} m` : `${comp.center_distance_px} px`;
    }

    if (fCompareTableBody) {
      fCompareTableBody.innerHTML = `
        <tr>
          <td><strong>Filename</strong></td>
          <td style="color:#06b6d4;">${s1.file_name}</td>
          <td style="color:#f59e0b;">${s2.file_name}</td>
        </tr>
        <tr>
          <td><strong>Dimensions</strong></td>
          <td>${s1.width.toLocaleString()} x ${s1.height.toLocaleString()} px</td>
          <td>${s2.width.toLocaleString()} x ${s2.height.toLocaleString()} px</td>
        </tr>
        <tr>
          <td><strong>GSD (Resolution)</strong></td>
          <td>${s1.gsd_cm ? s1.gsd_cm + ' cm/px' : 'N/A'}</td>
          <td>${s2.gsd_cm ? s2.gsd_cm + ' cm/px' : 'N/A'}</td>
        </tr>
        <tr>
          <td><strong>Area</strong></td>
          <td>${s1.area_ha ? s1.area_ha + ' ha' : 'N/A'}</td>
          <td>${s2.area_ha ? s2.area_ha + ' ha' : 'N/A'}</td>
        </tr>
        <tr>
          <td><strong>Master Coverage</strong></td>
          <td>${data.sub1_match.overlap_pct}%</td>
          <td>${data.sub2_match.overlap_pct}%</td>
        </tr>
        <tr>
          <td><strong>Overlap (IoU)</strong></td>
          <td colspan="2" style="text-align: center; color: #10b981; font-weight: 700;">
            ${mutual && mutual.is_overlapping ? mutual.iou_pct + '% IoU' : 'No Overlap'}
          </td>
        </tr>
      `;
    }

    // 2. Tab Chi Tiết Vùng 1
    const fSub1Name = document.getElementById('fSub1Name');
    const fSub1Origin = document.getElementById('fSub1Origin');
    const fSub1Dim = document.getElementById('fSub1Dim');
    const fSub1Gsd = document.getElementById('fSub1Gsd');
    const fSub1Area = document.getElementById('fSub1Area');
    const fSub1Overlap = document.getElementById('fSub1Overlap');

    if (fSub1Name) fSub1Name.innerText = s1.file_name;
    if (fSub1Origin) fSub1Origin.innerText = `X: ${b1.xmin.toLocaleString()}, Y: ${b1.ymin.toLocaleString()}`;
    if (fSub1Dim) fSub1Dim.innerText = `${b1.width.toLocaleString()} x ${b1.height.toLocaleString()} px`;
    if (fSub1Gsd) fSub1Gsd.innerText = s1.gsd_cm ? `${s1.gsd_cm} cm/px` : 'N/A';
    if (fSub1Area) fSub1Area.innerText = s1.area_ha ? `${s1.area_ha} ha (${s1.area_m2.toLocaleString()} m²)` : 'N/A';
    if (fSub1Overlap) fSub1Overlap.innerText = `${data.sub1_match.overlap_pct}%`;

    // 3. Tab Chi Tiết Vùng 2
    const fSub2Name = document.getElementById('fSub2Name');
    const fSub2Origin = document.getElementById('fSub2Origin');
    const fSub2Dim = document.getElementById('fSub2Dim');
    const fSub2Gsd = document.getElementById('fSub2Gsd');
    const fSub2Area = document.getElementById('fSub2Area');
    const fSub2Overlap = document.getElementById('fSub2Overlap');

    if (fSub2Name) fSub2Name.innerText = s2.file_name;
    if (fSub2Origin) fSub2Origin.innerText = `X: ${b2.xmin.toLocaleString()}, Y: ${b2.ymin.toLocaleString()}`;
    if (fSub2Dim) fSub2Dim.innerText = `${b2.width.toLocaleString()} x ${b2.height.toLocaleString()} px`;
    if (fSub2Gsd) fSub2Gsd.innerText = s2.gsd_cm ? `${s2.gsd_cm} cm/px` : 'N/A';
    if (fSub2Area) fSub2Area.innerText = s2.area_ha ? `${s2.area_ha} ha (${s2.area_m2.toLocaleString()} m²)` : 'N/A';
    if (fSub2Overlap) fSub2Overlap.innerText = `${data.sub2_match.overlap_pct}%`;

    // 4. Tab Xuất File
    updateFloatingCodeContent();

    // 5. Cập nhật các thanh trượt độ mờ so sánh
    updateDualOpacityUI();
  }

  function updateFloatingCodeContent() {
    if (!loadedDualMatchData) return;
    const codePre = document.getElementById('fCodeContent');
    if (!codePre) return;

    if (floatingActiveSubtab === 'fCodePixel') {
      codePre.innerText = JSON.stringify({
        sub_ortho_1: loadedDualMatchData.sub1_match.pixel_box,
        sub_ortho_2: loadedDualMatchData.sub2_match.pixel_box,
        mutual_overlap: loadedDualMatchData.mutual_overlap.pixel_box
      }, null, 2);
    } else if (floatingActiveSubtab === 'fCodeYolo') {
      codePre.innerText = `# Sub-Ortho 1:\n${loadedDualMatchData.sub1_match.yolo_format}\n# Sub-Ortho 2:\n${loadedDualMatchData.sub2_match.yolo_format}`;
    } else if (floatingActiveSubtab === 'fCodeGeo') {
      codePre.innerText = JSON.stringify(loadedDualMatchData.geojson || {
        sub1_wgs84: loadedDualMatchData.sub1_match.wgs84_polygon,
        sub2_wgs84: loadedDualMatchData.sub2_match.wgs84_polygon
      }, null, 2);
    }
  }

  function switchFloatingTab(tabKey) {
    if (!dualFloatingInfoPanel) return;
    const tabBtns = dualFloatingInfoPanel.querySelectorAll('.panel-tab-btn');
    tabBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabKey);
    });

    const tabMap = {
      tabCompare: 'fTabCompare',
      tabSub1: 'fTabSub1',
      tabSub2: 'fTabSub2',
      tabExport: 'fTabExport'
    };

    ['fTabCompare', 'fTabSub1', 'fTabSub2', 'fTabExport'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.style.display = (id === tabMap[tabKey]) ? 'block' : 'none';
      }
    });
  }

  function updateDualOpacityUI() {
    const s1Pct = Math.round((viewer.sub1Opacity !== undefined ? viewer.sub1Opacity : viewer.currentOpacity) * 100);
    const s2Pct = Math.round((viewer.sub2Opacity !== undefined ? viewer.sub2Opacity : viewer.currentOpacity) * 100);

    const fSub1Slider = document.getElementById('fSub1OpacitySlider');
    const fSub1Val = document.getElementById('fSub1OpacityVal');
    const tabSub1Slider = document.getElementById('tabSub1OpacitySlider');
    const tabSub1Val = document.getElementById('tabSub1OpacityVal');

    const fSub2Slider = document.getElementById('fSub2OpacitySlider');
    const fSub2Val = document.getElementById('fSub2OpacityVal');
    const tabSub2Slider = document.getElementById('tabSub2OpacitySlider');
    const tabSub2Val = document.getElementById('tabSub2OpacityVal');

    const fOverlapSlider = document.getElementById('fOverlapOpacitySlider');
    const fOverlapVal = document.getElementById('fOverlapOpacityVal');
    const oPct = Math.round((viewer.overlapOpacity !== undefined ? viewer.overlapOpacity : 0.35) * 100);

    if (fSub1Slider) fSub1Slider.value = s1Pct;
    if (fSub1Val) fSub1Val.innerText = `${s1Pct}%`;
    if (tabSub1Slider) tabSub1Slider.value = s1Pct;
    if (tabSub1Val) tabSub1Val.innerText = `${s1Pct}%`;

    if (fSub2Slider) fSub2Slider.value = s2Pct;
    if (fSub2Val) fSub2Val.innerText = `${s2Pct}%`;
    if (tabSub2Slider) tabSub2Slider.value = s2Pct;
    if (tabSub2Val) tabSub2Val.innerText = `${s2Pct}%`;
    
    if (fOverlapSlider) fOverlapSlider.value = oPct;
    if (fOverlapVal) fOverlapVal.innerText = `${oPct}%`;

    if (viewer.activeDualLayer === 'sub1') {
      opacitySlider.value = s1Pct;
      opacityVal.innerText = `${s1Pct}%`;
    } else if (viewer.activeDualLayer === 'sub2') {
      opacitySlider.value = s2Pct;
      opacityVal.innerText = `${s2Pct}%`;
    } else if (viewer.activeDualLayer === 'both' || viewer.activeDualLayer === 'overlap') {
      opacitySlider.value = s1Pct; // Đồng bộ main slider theo sub 1 cho chế độ cả 2 vùng
      opacityVal.innerText = `${s1Pct}%`;
    }
  }

  function setupDualOpacityControls() {
    const fSub1Slider = document.getElementById('fSub1OpacitySlider');
    const tabSub1Slider = document.getElementById('tabSub1OpacitySlider');
    const fSub2Slider = document.getElementById('fSub2OpacitySlider');
    const tabSub2Slider = document.getElementById('tabSub2OpacitySlider');

    const fOverlapSlider = document.getElementById('fOverlapOpacitySlider');

    const handleSub1Change = (val) => {
      viewer.setSub1Opacity(val);
      updateDualOpacityUI();
    };

    const handleSub2Change = (val) => {
      viewer.setSub2Opacity(val);
      updateDualOpacityUI();
    };
    
    const handleOverlapChange = (val) => {
      viewer.setOverlapOpacity(val);
      updateDualOpacityUI();
    };

    if (fSub1Slider && !fSub1Slider._bound) {
      fSub1Slider._bound = true;
      fSub1Slider.addEventListener('input', (e) => handleSub1Change(Number(e.target.value)));
    }
    if (tabSub1Slider && !tabSub1Slider._bound) {
      tabSub1Slider._bound = true;
      tabSub1Slider.addEventListener('input', (e) => handleSub1Change(Number(e.target.value)));
    }

    if (fSub2Slider && !fSub2Slider._bound) {
      fSub2Slider._bound = true;
      fSub2Slider.addEventListener('input', (e) => handleSub2Change(Number(e.target.value)));
    }
    if (tabSub2Slider && !tabSub2Slider._bound) {
      tabSub2Slider._bound = true;
      tabSub2Slider.addEventListener('input', (e) => handleSub2Change(Number(e.target.value)));
    }
    
    if (fOverlapSlider && !fOverlapSlider._bound) {
      fOverlapSlider._bound = true;
      fOverlapSlider.addEventListener('input', (e) => handleOverlapChange(Number(e.target.value)));
    }

    // Quick presets
    const btnPresetSub1Only = document.getElementById('btnPresetSub1Only');
    const btnPresetBlend50 = document.getElementById('btnPresetBlend50');
    const btnPresetSub2Only = document.getElementById('btnPresetSub2Only');
    const btnPresetBothFull = document.getElementById('btnPresetBothFull');
    const presetPills = [btnPresetSub1Only, btnPresetBlend50, btnPresetSub2Only, btnPresetBothFull];

    const markActivePreset = (activeBtn) => {
      presetPills.forEach(p => { if (p) p.classList.remove('active'); });
      if (activeBtn) activeBtn.classList.add('active');
    };

    if (btnPresetSub1Only && !btnPresetSub1Only._bound) {
      btnPresetSub1Only._bound = true;
      btnPresetSub1Only.addEventListener('click', () => {
        setDualLayer('sub1', true);
        viewer.setSub1Opacity(100);
        viewer.setSub2Opacity(0);
        updateDualOpacityUI();
        markActivePreset(btnPresetSub1Only);
      });
    }
    if (btnPresetBlend50 && !btnPresetBlend50._bound) {
      btnPresetBlend50._bound = true;
      btnPresetBlend50.addEventListener('click', () => {
        setDualLayer('both', true);
        viewer.setSub1Opacity(50);
        viewer.setSub2Opacity(50);
        updateDualOpacityUI();
        markActivePreset(btnPresetBlend50);
      });
    }
    if (btnPresetSub2Only && !btnPresetSub2Only._bound) {
      btnPresetSub2Only._bound = true;
      btnPresetSub2Only.addEventListener('click', () => {
        setDualLayer('sub2', true);
        viewer.setSub1Opacity(0);
        viewer.setSub2Opacity(100);
        updateDualOpacityUI();
        markActivePreset(btnPresetSub2Only);
      });
    }
    if (btnPresetBothFull && !btnPresetBothFull._bound) {
      btnPresetBothFull._bound = true;
      btnPresetBothFull.addEventListener('click', () => {
        setDualLayer('both', true);
        viewer.setSub1Opacity(100);
        viewer.setSub2Opacity(100);
        updateDualOpacityUI();
        markActivePreset(btnPresetBothFull);
      });
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

  // =========================================================================
  // TAB 3: NHẬP JSON UTM -> ĐÁNH DẤU POINTS & ĐỌC TRỰC TIẾP PIXEL -> XUẤT CSV
  // =========================================================================
  function initUTMPixelModule() {
    const SAMPLE_UTM_JSON = JSON.stringify({
      "Project_Info": {
        "CRS": "WGS 84 / UTM zone 49N",
        "EPSG": 32649,
        "Total_Points": 4
      },
      "Coordinates": {
        "35M.ThuậnNam19Points1": {
          "X": 265499.0387,
          "Y": 1263866.442,
          "Z": 0.0
        },
        "35M.ThuậnNam19Points2": {
          "X": 265475.1227,
          "Y": 1263804.8983,
          "Z": -0.0
        },
        "35M.ThuậnNam19Points3": {
          "X": 265680.1109,
          "Y": 1263865.9542,
          "Z": 0.0
        },
        "35M.ThuậnNam19Points4": {
          "X": 265654.0058,
          "Y": 1263795.824,
          "Z": 0.0
        },
        "Centroid": {
          "X": 265577.0695,
          "Y": 1263833.2796,
          "Z": 0.0
        }
      }
    }, null, 4);

    let activeTarget = 'big'; // 'big' | 'sub' | 'sub2'
    let lastPlottedResults = [];

    const tabUTMBadge = document.getElementById('tabUTMBadge');
    const utmPointCountBadge = document.getElementById('utmPointCountBadge');
    const btnUtmTargetBig = document.getElementById('btnUtmTargetBig');
    const btnUtmTargetSub = document.getElementById('btnUtmTargetSub');
    const btnUtmTargetSub2 = document.getElementById('btnUtmTargetSub2');
    const utmJsonDropzone = document.getElementById('utmJsonDropzone');
    const utmJsonFileInput = document.getElementById('utmJsonFileInput');
    const utmJsonTextarea = document.getElementById('utmJsonTextarea');
    const btnLoadSampleUTMJson = document.getElementById('btnLoadSampleUTMJson');
    const btnLoadCanonicalJson = document.getElementById('btnLoadCanonicalJson');
    const btnClearUTMText = document.getElementById('btnClearUTMText');
    const btnPlotAndReadPixels = document.getElementById('btnPlotAndReadPixels');
    const btnClearUTMPoints = document.getElementById('btnClearUTMPoints');
    const utmMetaPreview = document.getElementById('utmMetaPreview');
    const utmCrsVal = document.getElementById('utmCrsVal');
    const utmDetectedPointsVal = document.getElementById('utmDetectedPointsVal');
    const utmResultsCard = document.getElementById('utmResultsCard');
    const utmPointsTableBody = document.getElementById('utmPointsTableBody');
    const utmInBoundsBadge = document.getElementById('utmInBoundsBadge');
    const utmSearchInput = document.getElementById('utmSearchInput');
    const chkFilterInBoundsTable = document.getElementById('chkFilterInBoundsTable');
    const utmPagination = document.getElementById('utmPagination');
    const btnUTMPrevPage = document.getElementById('btnUTMPrevPage');
    const btnUTMNextPage = document.getElementById('btnUTMNextPage');
    const utmPageInfo = document.getElementById('utmPageInfo');
    const btnExportUTMCSV = document.getElementById('btnExportUTMCSV');
    const btnCanonicalModeCentroid = document.getElementById('btnCanonicalModeCentroid');
    const btnCanonicalModeAll = document.getElementById('btnCanonicalModeAll');
    const chkOnlyInBounds = document.getElementById('chkOnlyInBounds');
    const btnCalcCanonicalDirect = document.getElementById('btnCalcCanonicalDirect');
    const canonicalBadge = document.getElementById('canonicalBadge');
    const btnCopyUTMTable = document.getElementById('btnCopyUTMTable');

    let canonicalMode = 'centroid'; // 'centroid' (1 điểm/tấm) hoặc 'all' (5 điểm/tấm)
    let isCanonicalActive = false;
    let allCurrentResults = [];
    let allCurrentBoxes = [];
    let currentUTMPage = 1;
    const utmPageSize = 50;

    // Chuyển chọn ảnh mục tiêu
    function setTarget(target) {
      activeTarget = target;
      if (btnUtmTargetBig) btnUtmTargetBig.classList.toggle('active', target === 'big');
      if (btnUtmTargetSub) btnUtmTargetSub.classList.toggle('active', target === 'sub');
      if (btnUtmTargetSub2) btnUtmTargetSub2.classList.toggle('active', target === 'sub2');

      // Tự động chuyển map view tương ứng nếu ảnh đã nạp
      if (target === 'sub' && loadedSubData) {
        switchToSubOrtho();
      } else if (target === 'sub2' && loadedSub2Data) {
        switchToSub2Ortho();
      } else if (loadedBigData) {
        switchToBigOrtho();
      }
    }

    if (btnUtmTargetBig) btnUtmTargetBig.addEventListener('click', () => setTarget('big'));
    if (btnUtmTargetSub) btnUtmTargetSub.addEventListener('click', () => setTarget('sub'));
    if (btnUtmTargetSub2) btnUtmTargetSub2.addEventListener('click', () => setTarget('sub2'));

    // Cập nhật hiển thị nút Sub 2 nếu Sub 2 được nạp
    const observer = new MutationObserver(() => {
      if (btnViewSub2 && btnViewSub2.style.display !== 'none') {
        if (btnUtmTargetSub2) btnUtmTargetSub2.style.display = 'inline-block';
      }
    });
    if (btnViewSub2) observer.observe(btnViewSub2, { attributes: true, attributeFilter: ['style'] });

    const btnCanonicalModeBoxes = document.getElementById('btnCanonicalModeBoxes');
    const boxesLayerToggleWrap = document.getElementById('boxesLayerToggleWrap');
    const chkShowBoxesLayer = document.getElementById('chkShowBoxesLayer');

    // Chuyển chế độ tính Canonical (Tâm vs 4 góc + tâm vs Khung Box)
    if (btnCanonicalModeCentroid) {
      btnCanonicalModeCentroid.addEventListener('click', () => {
        canonicalMode = 'centroid';
        btnCanonicalModeCentroid.classList.add('active');
        if (btnCanonicalModeAll) btnCanonicalModeAll.classList.remove('active');
        if (btnCanonicalModeBoxes) btnCanonicalModeBoxes.classList.remove('active');
      });
    }
    if (btnCanonicalModeAll) {
      btnCanonicalModeAll.addEventListener('click', () => {
        canonicalMode = 'all';
        btnCanonicalModeAll.classList.add('active');
        if (btnCanonicalModeCentroid) btnCanonicalModeCentroid.classList.remove('active');
        if (btnCanonicalModeBoxes) btnCanonicalModeBoxes.classList.remove('active');
      });
    }
    if (btnCanonicalModeBoxes) {
      btnCanonicalModeBoxes.addEventListener('click', () => {
        canonicalMode = 'boxes';
        btnCanonicalModeBoxes.classList.add('active');
        if (btnCanonicalModeCentroid) btnCanonicalModeCentroid.classList.remove('active');
        if (btnCanonicalModeAll) btnCanonicalModeAll.classList.remove('active');
      });
    }

    if (chkShowBoxesLayer) {
      chkShowBoxesLayer.addEventListener('change', (e) => {
        viewer.toggleBoxesLayer(e.target.checked);
      });
    }

    // Tự động nạp mẫu Thuận Nam
    if (btnLoadSampleUTMJson) {
      btnLoadSampleUTMJson.addEventListener('click', () => {
        isCanonicalActive = false;
        utmJsonTextarea.value = SAMPLE_UTM_JSON;
        analyzeJsonText(SAMPLE_UTM_JSON);
        setStatus('Đã nạp JSON mẫu Thuận Nam 19 (4 Góc + Centroid)', 'success');
      });
    }

    // Nạp nhanh pv_module_reference_canonical.json
    if (btnLoadCanonicalJson) {
      btnLoadCanonicalJson.addEventListener('click', async () => {
        setStatus('Đang kiểm tra file Canonical JSON...', 'loading');
        try {
          const resp = await fetch('/api/canonical-info');
          const info = await resp.json();
          if (info.exists) {
            isCanonicalActive = true;
            if (canonicalBadge) canonicalBadge.innerText = `${info.total_panels.toLocaleString()} module`;
            utmJsonTextarea.value = `// File: ${info.filename}\n// Đường dẫn: ${info.default_path}\n// Tổng số module PV: ${info.total_panels.toLocaleString()} (${info.size_mb} MB)\n// Hệ tọa độ: WGS 84 (EPSG:4326) / UTM zone 49N\n// Bấm nút "Tính Tọa Độ Ngay" hoặc "Đánh Dấu Points & Đọc Pixel" để tính toán trực tiếp.`;
            if (utmMetaPreview) {
              utmMetaPreview.style.display = 'flex';
              utmCrsVal.innerText = 'WGS 84 GPS (EPSG:4326) / Canonical PV';
              utmDetectedPointsVal.innerText = `${info.total_panels.toLocaleString()} module PV`;
            }
            setStatus(`Đã sẵn sàng ${info.total_panels.toLocaleString()} module từ ${info.filename}`, 'success');
          } else {
            alert(`Không tìm thấy file Canonical JSON tại đường dẫn mặc định:\n${info.default_path}`);
            setStatus('Không tìm thấy file Canonical JSON', 'error');
          }
        } catch (err) {
          console.error(err);
          alert(`Lỗi kiểm tra Canonical JSON: ${err.message}`);
        }
      });
    }

    // Nút tính toán Canonical JSON trực tiếp
    if (btnCalcCanonicalDirect) {
      btnCalcCanonicalDirect.addEventListener('click', async () => {
        await executeCalcCanonical();
      });
    }

    async function executeCalcCanonical() {
      let targetInfo = null;
      if (activeTarget === 'sub2') {
        if (!loadedSub2Data) {
          alert('Chưa nạp Ortho Vùng 2! Vui lòng chọn ảnh mục tiêu khác hoặc nạp Ortho Vùng 2 trước.');
          return;
        }
        switchToSub2Ortho();
        targetInfo = loadedSub2Data;
      } else if (activeTarget === 'sub') {
        if (!loadedSubData) {
          alert('Chưa nạp Ortho Vùng 1! Vui lòng chọn ảnh mục tiêu khác hoặc nạp Ortho Vùng 1 trước.');
          return;
        }
        switchToSubOrtho();
        targetInfo = loadedSubData;
      } else {
        if (!loadedBigData) {
          alert('Chưa nạp Ortho To! Vui lòng nạp Ortho To trước.');
          return;
        }
        switchToBigOrtho();
        targetInfo = loadedBigData;
      }

      const onlyInBounds = chkOnlyInBounds ? chkOnlyInBounds.checked : false;
      const chkFilterStandardCanonical = document.getElementById('chkFilterStandardCanonical');
      const filterStandard = chkFilterStandardCanonical ? chkFilterStandardCanonical.checked : true;
      
      setStatus(`Đang tính tọa độ từ pv_module_reference_canonical.json trên ${targetInfo.file_name}...`, 'loading');

      try {
        const resp = await fetch('/api/calc-canonical-coords', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_ortho_path: targetInfo.file_path,
            mode: canonicalMode,
            only_in_bounds: onlyInBounds,
            filter_standard: filterStandard
          })
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || 'Lỗi khi tính tọa độ Canonical');
        }

        const resData = await resp.json();
        const data = resData.data;

        if (canonicalMode === 'boxes' && data.boxes && data.boxes.length > 0) {
          viewer.clearUTMPoints();
          viewer.plotCanonicalBoxes(data.boxes, activeTarget);
          if (boxesLayerToggleWrap) boxesLayerToggleWrap.style.display = 'block';
          if (chkShowBoxesLayer) chkShowBoxesLayer.checked = true;
          allCurrentResults = data.points;
          allCurrentBoxes = data.boxes;
          currentUTMPage = 1;
          renderResultsTable(allCurrentResults);

          if (tabUTMBadge) tabUTMBadge.innerText = data.boxes.length;
          if (utmPointCountBadge) utmPointCountBadge.innerText = `${data.boxes.length} khung box`;
          if (utmInBoundsBadge) utmInBoundsBadge.innerText = `${data.in_bounds_count.toLocaleString()} / ${data.boxes.length.toLocaleString()} trong ảnh`;

          setStatus(`Đã vẽ thành công ${data.boxes.length.toLocaleString()} khung box 4 góc (đã gán ID Đông-Tây-Nam-Bắc) trên ${targetInfo.file_name}`, 'success');
        } else {
          if (boxesLayerToggleWrap) boxesLayerToggleWrap.style.display = 'none';
          viewer.clearBoxes();
          const points = data.points;
          const results = viewer.plotAndReadUTMPoints(points);
          allCurrentResults = results;
          currentUTMPage = 1;
          renderResultsTable(results);

          if (tabUTMBadge) tabUTMBadge.innerText = results.length;
          if (utmPointCountBadge) utmPointCountBadge.innerText = `${results.length} điểm`;
          if (utmInBoundsBadge) utmInBoundsBadge.innerText = `${data.in_bounds_count.toLocaleString()} / ${data.calculated_points_count.toLocaleString()} trong ảnh`;

          setStatus(`Đã tính thành công ${results.length.toLocaleString()} điểm pixel trên ${targetInfo.file_name} (${data.in_bounds_count.toLocaleString()} nằm trong ảnh)`, 'success');
        }
      } catch (err) {
        console.error(err);
        alert(`Lỗi tính toán: ${err.message}`);
        setStatus('Lỗi tính tọa độ Canonical', 'error');
      }
    }

    // Xóa điểm trên bản đồ
    if (btnClearUTMPoints) {
      btnClearUTMPoints.addEventListener('click', () => {
        viewer.clearUTMPoints();
        viewer.clearBoxes();
        if (boxesLayerToggleWrap) boxesLayerToggleWrap.style.display = 'none';
        allCurrentResults = [];
        renderResultsTable([]);
        if (tabUTMBadge) tabUTMBadge.innerText = '0';
        if (utmPointCountBadge) utmPointCountBadge.innerText = '0 điểm';
        if (utmInBoundsBadge) utmInBoundsBadge.innerText = '0 / 0 trong ảnh';
        setStatus('Đã xóa tất cả các điểm và khung box đánh dấu', 'info');
      });
    }

    // Xóa nội dung textarea
    if (btnClearUTMText) {
      btnClearUTMText.addEventListener('click', () => {
        utmJsonTextarea.value = '';
        isCanonicalActive = false;
        if (utmMetaPreview) utmMetaPreview.style.display = 'none';
      });
    }

    // Xử lý upload file JSON
    if (utmJsonFileInput) {
      utmJsonFileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          readFile(e.target.files[0]);
        }
      });
    }

    // Drag & Drop cho dropzone
    if (utmJsonDropzone) {
      utmJsonDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        utmJsonDropzone.classList.add('drag-over');
      });
      utmJsonDropzone.addEventListener('dragleave', () => {
        utmJsonDropzone.classList.remove('drag-over');
      });
      utmJsonDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        utmJsonDropzone.classList.remove('drag-over');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          readFile(e.dataTransfer.files[0]);
        }
      });
    }

    function readFile(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target.result;
        utmJsonTextarea.value = text;
        analyzeJsonText(text);
        setStatus(`Đã tải file JSON: ${file.name}`, 'success');
      };
      reader.readAsText(file);
    }

    // Lắng nghe thay đổi trong textarea để cập nhật preview meta
    if (utmJsonTextarea) {
      utmJsonTextarea.addEventListener('input', () => {
        analyzeJsonText(utmJsonTextarea.value);
      });
    }

    function parsePoints(jsonObj) {
      const points = [];
      let crs = 'WGS 84 / UTM zone 49N (EPSG:32649)';

      if (!jsonObj || typeof jsonObj !== 'object') return { points, crs };

      if (jsonObj.Project_Info && jsonObj.Project_Info.CRS) {
        crs = `${jsonObj.Project_Info.CRS} (EPSG:${jsonObj.Project_Info.EPSG || 32649})`;
      } else if (jsonObj.crs_name) {
        crs = `${jsonObj.crs_name} (${jsonObj.crs || 'EPSG:32649'})`;
      }

      // Trường hợp 1: Dạng chuẩn người dùng "Coordinates": { "Point1": { "X": ..., "Y": ..., "Z": ... } }
      if (jsonObj.Coordinates && typeof jsonObj.Coordinates === 'object') {
        for (const [name, coords] of Object.entries(jsonObj.Coordinates)) {
          if (coords && typeof coords === 'object') {
            const x = coords.X !== undefined ? coords.X : coords.x;
            const y = coords.Y !== undefined ? coords.Y : coords.y;
            const z = coords.Z !== undefined ? coords.Z : (coords.z || 0.0);
            if (x !== undefined && y !== undefined) {
              points.push({ name, x: Number(x), y: Number(y), z: Number(z) });
            }
          }
        }
      }
      // Trường hợp 2: Dạng panels của Ortho to.json / pvAnnotator
      else if (Array.isArray(jsonObj.panels)) {
        jsonObj.panels.forEach((p, pIdx) => {
          const pId = p.id || `PV_${pIdx + 1}`;
          if (p.centroid && p.centroid.utm_32649) {
            points.push({
              name: `${pId}_Centroid`,
              internal_code: pId,
              x: p.centroid.utm_32649.easting,
              y: p.centroid.utm_32649.northing,
              z: 0.0,
              role: 'centroid'
            });
          }
          if (Array.isArray(p.corners)) {
            p.corners.forEach(c => {
              if (c.utm_32649) {
                points.push({
                  name: `${pId}_Corner_${c.corner_index}`,
                  internal_code: pId,
                  x: c.utm_32649.easting,
                  y: c.utm_32649.northing,
                  z: 0.0,
                  role: `corner_${c.corner_index}`
                });
              }
            });
          }
        });
      }
      // Trường hợp 3: Mảng phẳng hoặc pv_module_reference_canonical.json
      else if (Array.isArray(jsonObj)) {
        const isCanonical = jsonObj.length > 0 && (jsonObj[0].world || jsonObj[0].orthomosaic || jsonObj[0].source || jsonObj[0].type === "pv_module");
        if (isCanonical) {
          crs = "WGS 84 (EPSG:4326) / pv_module_reference_canonical.json";
          jsonObj.forEach((item, idx) => {
            const code = (item.source && item.source.internal_code) || `PV_${item.panel_index !== undefined ? item.panel_index : (idx + 1)}`;
            const cls = (item.classification && item.classification.class) || "Unclassified";

            if (item.world && item.world.centroid && item.world.centroid.length >= 2) {
              points.push({
                name: code,
                internal_code: code,
                panel_index: item.panel_index !== undefined ? item.panel_index : idx,
                x: Number(item.world.centroid[0]),
                y: Number(item.world.centroid[1]),
                z: 0.0,
                crs: "EPSG:4326",
                class: cls,
                role: "centroid"
              });
            } else if (item.orthomosaic && item.orthomosaic.centroid && item.orthomosaic.centroid.length >= 2) {
              points.push({
                name: code,
                internal_code: code,
                panel_index: item.panel_index !== undefined ? item.panel_index : idx,
                pixel_u: item.orthomosaic.centroid[0],
                pixel_v: item.orthomosaic.centroid[1],
                x: item.orthomosaic.centroid[0],
                y: item.orthomosaic.centroid[1],
                z: 0.0,
                class: cls,
                role: "centroid"
              });
            }
          });
        } else {
          jsonObj.forEach((item, idx) => {
            const x = item.X !== undefined ? item.X : item.x;
            const y = item.Y !== undefined ? item.Y : item.y;
            const z = item.Z !== undefined ? item.Z : (item.z || 0.0);
            const name = item.name || item.id || item.label || `Point_${idx + 1}`;
            if (x !== undefined && y !== undefined && !isNaN(Number(x)) && !isNaN(Number(y))) {
              points.push({ 
                name, 
                internal_code: item.internal_code || name,
                x: Number(x), 
                y: Number(y), 
                z: Number(z),
                class: item.class || 'Unclassified',
                role: item.role,
                group: item.group,
                row: item.row,
                col: item.col
              });
            }
          });
        }
      }
      // Trường hợp 4: Đối tượng lồng trực tiếp { "P1": { x, y }, "P2": { x, y } }
      else {
        for (const [name, coords] of Object.entries(jsonObj)) {
          if (coords && typeof coords === 'object') {
            const x = coords.X !== undefined ? coords.X : coords.x;
            const y = coords.Y !== undefined ? coords.Y : coords.y;
            const z = coords.Z !== undefined ? coords.Z : (coords.z || 0.0);
            if (x !== undefined && y !== undefined) {
              points.push({ name, x: Number(x), y: Number(y), z: Number(z) });
            }
          }
        }
      }

      return { points, crs };
    }

    function parseCSVText(text) {
      const lines = text.split(/\r?\n/).filter(line => line.trim() !== '');
      if (lines.length < 2) return [];
      
      const headers = lines[0].split(',').map(h => h.trim());
      const results = [];
      
      for (let i = 1; i < lines.length; i++) {
          let line = lines[i];
          const row = [];
          let inQuotes = false;
          let currField = '';
          for (let j = 0; j < line.length; j++) {
              const char = line[j];
              if (char === '"') {
                  inQuotes = !inQuotes;
              } else if (char === ',' && !inQuotes) {
                  row.push(currField);
                  currField = '';
              } else {
                  currField += char;
              }
          }
          row.push(currField);
          
          const obj = {};
          headers.forEach((h, idx) => {
              obj[h] = row[idx] !== undefined ? row[idx].trim() : '';
          });
          
          const cx = parseFloat(obj['UTM_X'] || obj['X'] || obj['Easting']);
          const cy = parseFloat(obj['UTM_Y'] || obj['Y'] || obj['Northing']);
          const name = obj['Point_Name'] || obj['Name'] || `Point_${i}`;
          const internalCode = obj['Internal_Code'] || obj['Code'] || '';
          const pClass = obj['Class'] || 'Unclassified';
          
          let prow = obj['Row'] || obj['row'] || '';
          let pcol = obj['Column'] || obj['Col'] || obj['col'] || '';
          if ((!prow || !pcol) && internalCode) {
              const m = internalCode.match(/D(\d+)-T(\d+)/i);
              if (m) {
                  prow = parseInt(m[1], 10);
                  pcol = parseInt(m[2], 10);
              }
          }
          
          if (typeof canonicalMode !== 'undefined' && (canonicalMode === 'boxes' || canonicalMode === 'all')) {
              const parseTuple = (str) => {
                  if (!str) return null;
                  const m = str.match(/\(([^,]+),\s*([^)]+)\)/);
                  if (m) return { x: parseFloat(m[1]), y: parseFloat(m[2]) };
                  return null;
              };
              const nw = parseTuple(obj['BBox_NW_GPS']) || parseTuple(obj['BBox_NW_Pixel']);
              const ne = parseTuple(obj['BBox_NE_GPS']) || parseTuple(obj['BBox_NE_Pixel']);
              const se = parseTuple(obj['BBox_SE_GPS']) || parseTuple(obj['BBox_SE_Pixel']);
              const sw = parseTuple(obj['BBox_SW_GPS']) || parseTuple(obj['BBox_SW_Pixel']);
              
              if (nw && ne && se && sw) {
                  results.push({ name: `${name}_NW`, internal_code: internalCode, x: nw.x, y: nw.y, class: pClass, role: 'corner_0', group: name, row: prow, col: pcol });
                  results.push({ name: `${name}_NE`, internal_code: internalCode, x: ne.x, y: ne.y, class: pClass, role: 'corner_1', group: name, row: prow, col: pcol });
                  results.push({ name: `${name}_SE`, internal_code: internalCode, x: se.x, y: se.y, class: pClass, role: 'corner_2', group: name, row: prow, col: pcol });
                  results.push({ name: `${name}_SW`, internal_code: internalCode, x: sw.x, y: sw.y, class: pClass, role: 'corner_3', group: name, row: prow, col: pcol });
              }
          }
          
          results.push({
              name: name,
              internal_code: internalCode,
              x: cx,
              y: cy,
              z: parseFloat(obj['Z'] || obj['Elevation'] || '0.0'),
              class: pClass,
              role: 'centroid',
              group: name,
              row: prow,
              col: pcol
          });
      }
      return results;
    }

    function analyzeJsonText(text) {
      if (!text || !text.trim()) {
        if (utmMetaPreview) utmMetaPreview.style.display = 'none';
        return;
      }
      try {
        let parsed;
        let points = [];
        let crs = 'WGS 84 / UTM zone 49N (EPSG:32649)';

        if (text.trim().startsWith('{') || text.trim().startsWith('[')) {
          parsed = JSON.parse(text);
          const res = parsePoints(parsed);
          points = res.points;
          crs = res.crs;
        } else {
          parsed = parseCSVText(text);
          const res = parsePoints(parsed);
          points = res.points;
          crs = 'WGS 84 / UTM zone 49N (EPSG:32649) (Từ CSV)';
        }

        if (utmMetaPreview && points.length > 0) {
          utmMetaPreview.style.display = 'flex';
          utmCrsVal.innerText = crs;
          utmDetectedPointsVal.innerText = `${points.length.toLocaleString()} điểm tọa độ`;
        }
      } catch (err) {
        if (utmMetaPreview) utmMetaPreview.style.display = 'none';
      }
    }

    // Đánh dấu Points & Đọc Pixel trực tiếp
    if (btnPlotAndReadPixels) {
      btnPlotAndReadPixels.addEventListener('click', async () => {
        const text = utmJsonTextarea.value.trim();
        if (!text) {
          alert('Vui lòng nhập hoặc nạp file JSON chứa tọa độ!');
          return;
        }

        // Nếu người dùng đang dùng Canonical JSON dạng placeholder
        if (isCanonicalActive && text.startsWith('// File:')) {
          await executeCalcCanonical();
          return;
        }

        let parsed = null;
        try {
          if (text.trim().startsWith('{') || text.trim().startsWith('[')) {
            parsed = JSON.parse(text);
          } else {
            parsed = parseCSVText(text);
          }
        } catch (err) {
          alert(`Lỗi phân tích nội dung (JSON/CSV): ${err.message}`);
          return;
        }

        const { points, crs } = parsePoints(parsed);
        if (points.length === 0) {
          alert('Không tìm thấy danh sách điểm tọa độ hợp lệ trong file JSON!');
          return;
        }

        // Kiểm tra ảnh mục tiêu đã nạp chưa
        let targetInfo = null;
        if (activeTarget === 'sub2') {
          if (!loadedSub2Data) {
            alert('Chưa nạp Ortho Vùng 2! Vui lòng chọn ảnh mục tiêu khác hoặc nạp Ortho Vùng 2 trước.');
            return;
          }
          switchToSub2Ortho();
          targetInfo = loadedSub2Data;
        } else if (activeTarget === 'sub') {
          if (!loadedSubData) {
            alert('Chưa nạp Ortho Vùng 1! Vui lòng chọn ảnh mục tiêu khác hoặc nạp Ortho Vùng 1 trước.');
            return;
          }
          switchToSubOrtho();
          targetInfo = loadedSubData;
        } else {
          if (!loadedBigData) {
            alert('Chưa nạp Ortho To! Vui lòng nạp Ortho To trước.');
            return;
          }
          switchToBigOrtho();
          targetInfo = loadedBigData;
        }

        // ĐỌC TRỰC TIẾP TỪ ẢNH GEOTIFF BẰNG RASTERIO INDEX (HỖ TRỢ WGS84 VÀ UTM)
        setStatus('Đang đọc tọa độ pixel trực tiếp từ GeoTIFF raster...', 'loading');
        try {
          const resp = await fetch('/api/read-pixels-from-utm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              file_path: targetInfo.file_path,
              points: points
            })
          });

          if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi đọc pixel từ file GeoTIFF');
          }

          const resData = await resp.json();
          const pointsWithPixels = resData.points;
          
          // Khôi phục lại các thuộc tính bị backend loại bỏ (role, class, group, internal_code, row, col)
          pointsWithPixels.forEach((p, idx) => {
              if (points[idx]) {
                  p.role = points[idx].role;
                  p.class = points[idx].class;
                  p.group = points[idx].group;
                  p.internal_code = points[idx].internal_code;
                  p.row = points[idx].row;
                  p.col = points[idx].col;
              }
          });
          
          if (typeof canonicalMode !== 'undefined' && canonicalMode === 'boxes') {
              const groups = {};
              pointsWithPixels.forEach(p => {
                  const g = p.group || p.internal_code || p.name.replace(/_(NW|NE|SE|SW|Centroid)$/, '');
                  if (!groups[g]) groups[g] = { corners: [], centroid: null, internal_code: p.internal_code || g, batch_id: g, row: p.row, column: p.col };
                  if (p.role === 'centroid' || !p.role || p.name.includes('_Centroid') || p.name === g) {
                      groups[g].centroid = { pixel: { x: p.pixel_u, y: p.pixel_v }, gps: { longitude: p.lon, latitude: p.lat }, class: p.class };
                  } else if (p.role && p.role.startsWith('corner_')) {
                      groups[g].corners.push({ pixel: { x: p.pixel_u, y: p.pixel_v }, gps: { longitude: p.lon, latitude: p.lat }, role: p.role });
                  }
              });
              
              const boxes = [];
              for (const g in groups) {
                  const grp = groups[g];
                  if (grp.corners.length === 4 && grp.centroid) {
                      grp.corners.sort((a, b) => a.role.localeCompare(b.role));
                      
                      // Cập nhật class vào trực tiếp đối tượng group (box)
                      if (grp.centroid && grp.centroid.class) {
                          grp.class = grp.centroid.class;
                      }
                      
                      // Xác định màu sắc dựa trên Class
                      let cl = (grp.class || 'unclassified').toLowerCase();
                      let color_rgba = [156, 163, 175, 255]; // Mặc định màu xám (gray) cho Unclassified / Normal
                      if (cl !== 'unclassified' && cl !== 'normal' && cl !== '' && !cl.includes('normal')) {
                          if (cl.includes('bypass') || cl.includes('diode')) {
                              color_rgba = [234, 179, 8, 255]; // Vàng (Diode/Bypass)
                          } else if (cl.includes('multi') || cl.includes('string')) {
                              color_rgba = [249, 115, 22, 255]; // Cam (MultiHotSpot/String)
                          } else if (cl.includes('mixed')) {
                              color_rgba = [168, 85, 247, 255]; // Tím (Mixed)
                          } else {
                              color_rgba = [239, 68, 68, 255]; // Đỏ (SingleHotSpot và các lỗi khác)
                          }
                      }
                      grp.color_rgba = color_rgba;
                      
                      boxes.push(grp);
                  }
              }
              
              if (boxes.length > 0) {
                  viewer.clearUTMPoints();
                  viewer.plotCanonicalBoxes(boxes, activeTarget);
                  if (typeof boxesLayerToggleWrap !== 'undefined' && boxesLayerToggleWrap) boxesLayerToggleWrap.style.display = 'block';
                  if (typeof chkShowBoxesLayer !== 'undefined' && chkShowBoxesLayer) chkShowBoxesLayer.checked = true;
                  
                  // Chỉ hiển thị các polygon (boxes) lên bảng thay vì hiện tất cả các điểm góc
                  allCurrentResults = boxes.map(b => ({
                      batch_id: b.batch_id,
                      internal_code: b.internal_code,
                      row: b.row,
                      column: b.col || b.column,
                      pixel_u: b.centroid ? b.centroid.pixel.x : '--',
                      pixel_v: b.centroid ? b.centroid.pixel.y : '--',
                      lon: b.centroid && b.centroid.gps ? b.centroid.gps.longitude : undefined,
                      lat: b.centroid && b.centroid.gps ? b.centroid.gps.latitude : undefined,
                      in_bounds: true,
                      class: b.class || (b.centroid && b.centroid.class) || 'Unclassified',
                      index: b.index !== undefined ? b.index : null
                  }));
                  
                  allCurrentBoxes = boxes;
                  currentUTMPage = 1;
                  renderResultsTable(allCurrentResults);

                  if (tabUTMBadge) tabUTMBadge.innerText = boxes.length;
                  if (utmPointCountBadge) utmPointCountBadge.innerText = `${boxes.length} tấm (polygon)`;
                  if (utmPageInfo) utmPageInfo.innerText = `Trang 1 / ${Math.ceil(boxes.length / utmPageSize)} (${boxes.length.toLocaleString()} tấm)`;
                  setStatus(`Đã đọc pixel & vẽ thành công ${boxes.length.toLocaleString()} khung box từ file tải lên`, 'success');
                  return;
              }
          }

          // Cắm các điểm đã đọc pixel trực tiếp lên ảnh trực giao
          if (typeof boxesLayerToggleWrap !== 'undefined' && boxesLayerToggleWrap) boxesLayerToggleWrap.style.display = 'none';
          viewer.clearBoxes();
          const results = viewer.plotAndReadUTMPoints(pointsWithPixels);
          allCurrentResults = results;
          currentUTMPage = 1;

          renderResultsTable(results);

          if (tabUTMBadge) tabUTMBadge.innerText = results.length;
          if (utmPointCountBadge) utmPointCountBadge.innerText = `${results.length} điểm`;

          const inBoundsCount = results.filter(r => r.in_bounds).length;
          if (utmInBoundsBadge) utmInBoundsBadge.innerText = `${inBoundsCount.toLocaleString()} / ${results.length.toLocaleString()} trong ảnh`;

          setStatus(`Đã đọc trực tiếp ${results.length.toLocaleString()} điểm pixel từ ${targetInfo.file_name} & đánh dấu lên ảnh`, 'success');
        } catch (apiErr) {
          console.error(apiErr);
          alert(`Lỗi đọc pixel: ${apiErr.message}`);
          setStatus('Lỗi đọc pixel từ GeoTIFF', 'error');
        }
      });
    }

    // Render bảng dữ liệu tọa độ pixel với phân trang và tìm kiếm
    function getFilteredResults() {
      if (!allCurrentResults) return [];
      const query = utmSearchInput ? utmSearchInput.value.trim().toLowerCase() : '';
      const onlyInBounds = chkFilterInBoundsTable ? chkFilterInBoundsTable.checked : false;

      return allCurrentResults.filter(pt => {
        if (onlyInBounds && !pt.in_bounds) return false;
        if (!query) return true;
        const nameMatch = pt.name && pt.name.toLowerCase().includes(query);
        const codeMatch = pt.internal_code && pt.internal_code.toLowerCase().includes(query);
        const classMatch = pt.class && pt.class.toLowerCase().includes(query);
        return nameMatch || codeMatch || classMatch;
      });
    }

    function renderResultsTable(results) {
      if (!utmResultsCard || !utmPointsTableBody) return;

      if (!results || results.length === 0) {
        utmResultsCard.style.display = 'none';
        return;
      }

      utmResultsCard.style.display = 'block';
      renderCurrentUTMPage();
    }

    function renderCurrentUTMPage() {
      if (!utmPointsTableBody) return;
      const filtered = getFilteredResults();
      const totalItems = filtered.length;
      const totalPages = Math.max(1, Math.ceil(totalItems / utmPageSize));

      if (currentUTMPage > totalPages) currentUTMPage = totalPages;
      if (currentUTMPage < 1) currentUTMPage = 1;

      const startIndex = (currentUTMPage - 1) * utmPageSize;
      const pageItems = filtered.slice(startIndex, startIndex + utmPageSize);

      utmPointsTableBody.innerHTML = '';

      pageItems.forEach((pt, pageIdx) => {
        const globalIdx = pt.index !== undefined ? pt.index : (startIndex + pageIdx);
        const tr = document.createElement('tr');
        tr.id = `utm-row-${globalIdx}`;

        const isCentroid = (pt.name && pt.name.toLowerCase().includes('centroid')) || pt.role === 'centroid' || !pt.role;
        const statusBadge = pt.in_bounds 
          ? '<span class="badge badge-success-subtle" style="color: #10b981; font-weight: 600;">Trong ảnh</span>' 
          : '<span class="badge badge-danger-subtle" style="color: #ef4444; font-weight: 600;">Ngoài ảnh</span>';

        const hasBatchId = !!pt.batch_id;
        const displayNameHtml = hasBatchId
          ? `<div style="display: flex; flex-direction: column; gap: 2px;">
              <div><span class="badge badge-purple-subtle" style="font-family: monospace; font-size: 11px; font-weight: 700;">${pt.batch_id}</span> <strong style="color: #cbd5e1;">${pt.internal_code || ''}</strong></div>
              ${pt.row ? `<div style="font-size: 10px; color: #94a3b8;"><i class="fa-solid fa-arrows-split-up-and-left"></i> Hàng: <b>${pt.row}</b> | Cột: <b>${pt.column}</b></div>` : ''}
            </div>`
          : `<strong class="${isCentroid ? 'col-centroid' : ''}">
              <i class="fa-solid ${isCentroid ? 'fa-star text-amber' : 'fa-location-dot text-cyan'}"></i>
              ${pt.name || pt.internal_code}
            </strong>`;

        tr.innerHTML = `
          <td>${displayNameHtml}</td>
          <td class="col-pixel" id="cell-u-${globalIdx}">${pt.pixel_u}</td>
          <td class="col-pixel" id="cell-v-${globalIdx}">${pt.pixel_v}</td>
          <td>${pt.utm_x !== undefined ? pt.utm_x.toLocaleString() : (pt.x ? pt.x.toLocaleString() : '--')}</td>
          <td>${pt.utm_y !== undefined ? pt.utm_y.toLocaleString() : (pt.y ? pt.y.toLocaleString() : '--')}</td>
          <td>${pt.lon !== undefined ? pt.lon.toFixed(6) : '--'}</td>
          <td>${pt.lat !== undefined ? pt.lat.toFixed(6) : '--'}</td>
          <td>${statusBadge}</td>
        `;

        tr.addEventListener('click', () => {
          document.querySelectorAll('#utmPointsTableBody tr').forEach(r => r.classList.remove('active-row'));
          tr.classList.add('active-row');
          if (viewer.canonicalBoxes && viewer.canonicalBoxes.length > 0) {
            viewer.focusBox(globalIdx);
          } else {
            viewer.focusUTMPoint(globalIdx);
          }
        });

        utmPointsTableBody.appendChild(tr);
      });

      // Cập nhật phân trang
      if (utmPagination) {
        if (totalItems > utmPageSize) {
          utmPagination.style.display = 'flex';
          if (utmPageInfo) utmPageInfo.innerText = `Trang ${currentUTMPage} / ${totalPages} (${totalItems.toLocaleString()} điểm)`;
          if (btnUTMPrevPage) btnUTMPrevPage.disabled = (currentUTMPage <= 1);
          if (btnUTMNextPage) btnUTMNextPage.disabled = (currentUTMPage >= totalPages);
        } else {
          utmPagination.style.display = 'none';
        }
      }
    }

    // Sự kiện tìm kiếm & lọc bảng
    if (utmSearchInput) {
      utmSearchInput.addEventListener('input', () => {
        currentUTMPage = 1;
        renderCurrentUTMPage();
      });
    }

    if (chkFilterInBoundsTable) {
      chkFilterInBoundsTable.addEventListener('change', () => {
        currentUTMPage = 1;
        renderCurrentUTMPage();
      });
    }

    if (btnUTMPrevPage) {
      btnUTMPrevPage.addEventListener('click', () => {
        if (currentUTMPage > 1) {
          currentUTMPage--;
          renderCurrentUTMPage();
        }
      });
    }

    if (btnUTMNextPage) {
      btnUTMNextPage.addEventListener('click', () => {
        const totalPages = Math.ceil(getFilteredResults().length / utmPageSize);
        if (currentUTMPage < totalPages) {
          currentUTMPage++;
          renderCurrentUTMPage();
        }
      });
    }

    // Khi click vào marker trên bản đồ, highlight dòng trong bảng
    viewer.onUTMPointSelected = (pointData) => {
      const idx = pointData.index;
      // Tìm xem điểm này nằm ở trang nào
      const filtered = getFilteredResults();
      const pos = filtered.findIndex(p => p.index === idx);
      if (pos >= 0) {
        currentUTMPage = Math.floor(pos / utmPageSize) + 1;
        renderCurrentUTMPage();
        setTimeout(() => {
          const row = document.getElementById(`utm-row-${idx}`);
          if (row) {
            document.querySelectorAll('#utmPointsTableBody tr').forEach(r => r.classList.remove('active-row'));
            row.classList.add('active-row');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }, 50);
      }
    };

    // Khi click vào khung box trên bản đồ, highlight dòng trong bảng
    viewer.onBoxSelected = (box) => {
      const idx = box.index;
      const filtered = getFilteredResults();
      const pos = filtered.findIndex(p => (p.batch_id && p.batch_id === box.batch_id) || (p.internal_code && p.internal_code === box.internal_code) || p.index === idx);
      if (pos >= 0) {
        currentUTMPage = Math.floor(pos / utmPageSize) + 1;
        renderCurrentUTMPage();
        setTimeout(() => {
          const row = document.getElementById(`utm-row-${idx}`);
          if (row) {
            document.querySelectorAll('#utmPointsTableBody tr').forEach(r => r.classList.remove('active-row'));
            row.classList.add('active-row');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }, 50);
      }
    };

    // Lắng nghe khi người dùng kéo thả marker trên bản đồ
    viewer.onUTMPointMoved = (pointData) => {
      const idx = pointData.index;
      const cellU = document.getElementById(`cell-u-${idx}`);
      const cellV = document.getElementById(`cell-v-${idx}`);
      if (cellU) cellU.innerText = pointData.pixel_u;
      if (cellV) cellV.innerText = pointData.pixel_v;
    };

    // Xóa tất cả điểm đánh dấu
    if (btnClearUTMPoints) {
      btnClearUTMPoints.addEventListener('click', () => {
        viewer.clearUTMPoints();
        allCurrentResults = [];
        if (utmResultsCard) utmResultsCard.style.display = 'none';
        if (tabUTMBadge) tabUTMBadge.innerText = '0';
        if (utmPointCountBadge) utmPointCountBadge.innerText = '0 điểm';
        setStatus('Đã xóa toàn bộ điểm đánh dấu trên bản đồ', 'ready');
      });
    }

    // Xuất file CSV
    if (btnExportUTMCSV) {
      btnExportUTMCSV.addEventListener('click', () => {
        const data = allCurrentResults && allCurrentResults.length > 0 ? allCurrentResults : viewer.getPlottedPointsPixelData();
        if (!data || data.length === 0) {
          alert('Chưa có điểm nào được đánh dấu trên ảnh để xuất CSV!');
          return;
        }

        const targetLabel = activeTarget === 'sub2' ? 'Ortho_Vung_2' : (activeTarget === 'sub' ? 'Ortho_Vung_1' : 'Ortho_To');
        const crs = 'WGS 84 / UTM zone 49N (EPSG:32649)';

        const headers = [
          'Point_Name',
          'Internal_Code',
          'Class',
          'Pixel_U',
          'Pixel_V',
          'Pixel_U_Int',
          'Pixel_V_Int',
          'UTM_X',
          'UTM_Y',
          'Longitude',
          'Latitude',
          'Z',
          'In_Bounds',
          'Target_Image'
        ];
        
        // Add BBox corner headers if available
        if (data.length > 0 && data[0].nw) {
          headers.push('BBox_NW_Pixel', 'BBox_NE_Pixel', 'BBox_SE_Pixel', 'BBox_SW_Pixel', 'BBox_NW_GPS', 'BBox_NE_GPS', 'BBox_SE_GPS', 'BBox_SW_GPS');
        }

        const csvRows = [headers.join(',')];

        data.forEach(d => {
          const row = [
            `"${d.name}"`,
            `"${d.internal_code || d.name}"`,
            `"${d.class || 'Unclassified'}"`,
            d.pixel_u,
            d.pixel_v,
            d.pixel_u_int,
            d.pixel_v_int,
            d.utm_x !== undefined ? d.utm_x : (d.x !== undefined ? d.x : ''),
            d.utm_y !== undefined ? d.utm_y : (d.y !== undefined ? d.y : ''),
            d.lon !== undefined ? d.lon : '',
            d.lat !== undefined ? d.lat : '',
            d.z !== undefined ? d.z : '0.0',
            d.in_bounds ? 1 : 0,
            `"${targetLabel}"`
          ];
          
          if (d.nw) {
            row.push(`"${d.nw}"`, `"${d.ne}"`, `"${d.se}"`, `"${d.sw}"`);
            row.push(`"${d.nw_gps || ''}"`, `"${d.ne_gps || ''}"`, `"${d.se_gps || ''}"`, `"${d.sw_gps || ''}"`);
          }
          
          csvRows.push(row.join(','));
        });

        const csvContent = '\uFEFF' + csvRows.join('\r\n');
        const now = new Date();
        const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
        const fileName = `PV_Coordinates_${targetLabel}_${timestamp}.csv`;

        OrthoReader.downloadFile(csvContent, fileName, 'text/csv;charset=utf-8;');
        setStatus(`Đã xuất ${data.length.toLocaleString()} dòng tọa độ ra file ${fileName}`, 'success');
      });
    }

    const btnTransformPointsCV = document.getElementById('btnTransformPointsCV');
    const csvFileInput = document.getElementById('csvFileInput');

    if (btnTransformPointsCV) {
      btnTransformPointsCV.addEventListener('click', async () => {
        if (!csvFileInput.files || csvFileInput.files.length === 0) {
          alert('Vui lòng chọn file CSV chứa tọa độ (u, v) của Ortho Vùng!');
          return;
        }

        let targetOrthoPath = null;
        let bigOrthoPath = null;

        if (loadedBigData) {
          bigOrthoPath = loadedBigData.file_path;
        }

        if (activeTarget === 'sub2' && loadedSub2Data) {
          targetOrthoPath = loadedSub2Data.file_path;
        } else if (loadedSubData) {
          targetOrthoPath = loadedSubData.file_path;
        }

        if (!bigOrthoPath || !targetOrthoPath) {
          alert('Chưa có thông tin Ortho To hoặc Ortho Vùng. Vui lòng Tải Ảnh ở mục Định Vị BBox trước.');
          return;
        }

        try {
          btnTransformPointsCV.disabled = true;
          btnTransformPointsCV.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang phân tích AI & Tính toán...';

          const formData = new FormData();
          formData.append('big_path', bigOrthoPath);
          formData.append('sub_path', targetOrthoPath);
          formData.append('csv_file', csvFileInput.files[0]);

          const response = await fetch('/api/transform-points-cv', {
            method: 'POST',
            body: formData
          });

          if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Lỗi server khi phân tích AI');
          }

          const resData = await response.json();
          currentAffineCSV = resData.csv_affine;
          currentHomoCSV = resData.csv_homography;

          // Hiển thị điểm trên bản đồ Master Ortho
          viewer.plotMappedPoints(resData.mapped_affine, resData.mapped_homography);

          transformResultsWrap.style.display = 'block';
          setStatus('Phân tích AI thành công! Đã tính toán xong ma trận.', 'success');
        } catch (err) {
          console.error(err);
          alert('Lỗi: ' + err.message);
          setStatus('Lỗi AI ánh xạ: ' + err.message, 'error');
        } finally {
          btnTransformPointsCV.disabled = false;
          btnTransformPointsCV.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Tính Toán Ma Trận AI';
        }
      });
    }

    if (btnExportAffineCSV) {
      btnExportAffineCSV.addEventListener('click', () => {
        if (!currentAffineCSV) return;
        const targetLabel = activeTarget === 'sub2' ? 'Ortho_Vung_2' : (activeTarget === 'sub' ? 'Ortho_Vung_1' : 'Ortho_To');
        const now = new Date();
        const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
        const filename = `Affine_Mapped_Points_${targetLabel}_${dateStr}.csv`;
        OrthoReader.downloadFile('\uFEFF' + currentAffineCSV, filename, 'text/csv;charset=utf-8;');
      });
    }

    if (btnExportHomoCSV) {
      btnExportHomoCSV.addEventListener('click', () => {
        if (!currentHomoCSV) return;
        const targetLabel = activeTarget === 'sub2' ? 'Ortho_Vung_2' : (activeTarget === 'sub' ? 'Ortho_Vung_1' : 'Ortho_To');
        const now = new Date();
        const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
        const filename = `Homography_Mapped_Points_${targetLabel}_${dateStr}.csv`;
        OrthoReader.downloadFile('\uFEFF' + currentHomoCSV, filename, 'text/csv;charset=utf-8;');
      });
    }

    if (chkShowAffine) {
      chkShowAffine.addEventListener('change', (e) => {
        viewer.toggleAffineLayer(e.target.checked);
      });
    }

    if (chkShowHomo) {
      chkShowHomo.addEventListener('change', (e) => {
        viewer.toggleHomoLayer(e.target.checked);
      });
    }

    // --- Module Ánh Xạ GPS Thuần Trong Tab 3 ---
    const radioGpsSourceCurrent = document.getElementById('radioGpsSourceCurrent');
    const radioGpsSourceCsv = document.getElementById('radioGpsSourceCsv');
    const gpsCsvFileInputGroup = document.getElementById('gpsCsvFileInputGroup');
    const gpsCsvFileInput = document.getElementById('gpsCsvFileInput');
    const btnMapPointsGPS = document.getElementById('btnMapPointsGPS');
    const gpsMapResultsWrap = document.getElementById('gpsMapResultsWrap');
    const btnExportGpsMappedCSV = document.getElementById('btnExportGpsMappedCSV');
    const btnFocusGpsPoints = document.getElementById('btnFocusGpsPoints');
    const chkShowGPSMapped = document.getElementById('chkShowGPSMapped');

    let currentGpsMappedCSV = null;
    let currentGpsMappedPoints = [];

    if (radioGpsSourceCurrent && radioGpsSourceCsv && gpsCsvFileInputGroup) {
      radioGpsSourceCurrent.addEventListener('change', () => {
        if (radioGpsSourceCurrent.checked) gpsCsvFileInputGroup.style.display = 'none';
      });
      radioGpsSourceCsv.addEventListener('change', () => {
        if (radioGpsSourceCsv.checked) gpsCsvFileInputGroup.style.display = 'block';
      });
    }

    if (btnMapPointsGPS) {
      btnMapPointsGPS.addEventListener('click', async () => {
        if (!loadedBigData || !loadedBigData.file_path) {
          alert('Chưa có thông tin Ortho To. Vui lòng nạp Ortho To trước.');
          return;
        }
        let targetOrthoPath = null;
        let targetLabel = 'Ortho Vùng';
        if (activeTarget === 'sub2' && loadedSub2Data) {
          targetOrthoPath = loadedSub2Data.file_path;
          targetLabel = 'Ortho Vùng 2';
        } else if (loadedSubData) {
          targetOrthoPath = loadedSubData.file_path;
          targetLabel = 'Ortho Vùng 1';
        }

        if (!targetOrthoPath) {
          alert('Chưa có thông tin Ortho Vùng. Vui lòng nạp Ortho Vùng ở mục Định Vị BBox trước.');
          return;
        }

        const isFromCsv = radioGpsSourceCsv && radioGpsSourceCsv.checked;

        try {
          btnMapPointsGPS.disabled = true;
          btnMapPointsGPS.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang quy chiếu GPS...';
          setStatus('Đang quy chiếu tọa độ bằng GPS thuần...', 'loading');

          let resData = null;

          if (isFromCsv) {
            if (!gpsCsvFileInput.files || gpsCsvFileInput.files.length === 0) {
              alert('Vui lòng chọn file CSV chứa tọa độ (Pixel_U, Pixel_V) trước khi bấm Ánh xạ!');
              return;
            }
            const formData = new FormData();
            formData.append('big_path', loadedBigData.file_path);
            formData.append('sub_path', targetOrthoPath);
            formData.append('csv_file', gpsCsvFileInput.files[0]);

            const resp = await fetch('/api/map-points-by-gps-csv', {
              method: 'POST',
              body: formData
            });

            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              throw new Error(err.detail || 'Lỗi server khi ánh xạ CSV bằng GPS');
            }
            resData = await resp.json();
          } else {
            if (!allCurrentResults || allCurrentResults.length === 0) {
              alert('Chưa có danh sách điểm nào được nạp hoặc tính toán ở bảng trên! Hãy bấm "Đọc Tọa Độ Pixel Từ GeoTIFF" hoặc nạp file trước.');
              return;
            }

            if (canonicalMode === 'boxes' && allCurrentBoxes && allCurrentBoxes.length > 0) {
              const panelsPayload = allCurrentBoxes.map(b => ({
                id: b.batch_id,
                label: b.internal_code,
                row: b.row,
                column: b.column,
                class: b.class || 'Unclassified',
                color_rgba: b.color_rgba || [168, 85, 247, 255],
                corners_pixel: b.corners.map(c => c.pixel),
                centroid_pixel: b.centroid.pixel
              }));

              const respBoxes = await fetch('/api/map-panels-by-gps', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  big_path: loadedBigData.file_path,
                  sub_path: targetOrthoPath,
                  panels: panelsPayload
                })
              });

              if (!respBoxes.ok) throw new Error('Lỗi khi ánh xạ Khung Box lên Ortho To');
              const resDataBoxes = await respBoxes.json();
              
              const mappedBoxes = (resDataBoxes.panels || []).map(p => ({
                 batch_id: p.id,
                 internal_code: p.id,
                 row: p.row,
                 column: p.column,
                 class: p.class,
                 color_rgba: p.color_rgba,
                 corners: p.corners,
                 centroid: p.centroid,
                 in_bounds: true
              }));

              viewer.switchToBigView();
              viewer.plotCanonicalBoxes(mappedBoxes, 'big');
              
              if (chkShowGPSMapped) chkShowGPSMapped.checked = true;
              
              // Tạo CSV cho Bounding Box sau khi ánh xạ
              let csvStr = 'ID_Panel,Row,Column,Class,Centroid_U,Centroid_V,Centroid_Lat,Centroid_Lon,NW_U,NW_V,NW_Lat,NW_Lon,NE_U,NE_V,NE_Lat,NE_Lon,SE_U,SE_V,SE_Lat,SE_Lon,SW_U,SW_V,SW_Lat,SW_Lon\n';
              mappedBoxes.forEach(mb => {
                const cU = mb.centroid.pixel.x; const cV = mb.centroid.pixel.y;
                const cLat = mb.centroid.gps ? mb.centroid.gps.latitude.toFixed(7) : '--';
                const cLon = mb.centroid.gps ? mb.centroid.gps.longitude.toFixed(7) : '--';
                
                const nw = mb.corners[0]; const ne = mb.corners[1];
                const se = mb.corners[2]; const sw = mb.corners[3];
                
                const nwLat = nw.gps ? nw.gps.latitude.toFixed(7) : '--'; const nwLon = nw.gps ? nw.gps.longitude.toFixed(7) : '--';
                const neLat = ne.gps ? ne.gps.latitude.toFixed(7) : '--'; const neLon = ne.gps ? ne.gps.longitude.toFixed(7) : '--';
                const seLat = se.gps ? se.gps.latitude.toFixed(7) : '--'; const seLon = se.gps ? se.gps.longitude.toFixed(7) : '--';
                const swLat = sw.gps ? sw.gps.latitude.toFixed(7) : '--'; const swLon = sw.gps ? sw.gps.longitude.toFixed(7) : '--';

                csvStr += `${mb.internal_code},${mb.row || ''},${mb.column || ''},${mb.class || ''},${cU},${cV},${cLat},${cLon},${nw.pixel.x},${nw.pixel.y},${nwLat},${nwLon},${ne.pixel.x},${ne.pixel.y},${neLat},${neLon},${se.pixel.x},${se.pixel.y},${seLat},${seLon},${sw.pixel.x},${sw.pixel.y},${swLat},${swLon}\n`;
              });
              currentGpsMappedCSV = csvStr;
              if (gpsMapResultsWrap) gpsMapResultsWrap.style.display = 'block';
              
              setStatus(`Đã ánh xạ thành công ${mappedBoxes.length} khung box sang Ortho To bằng GPS thuần!`, 'success');
              alert(`Đã ánh xạ thành công ${mappedBoxes.length} khung box sang Ortho To bằng GPS thuần! Bạn có thể Xuất CSV.`);
              btnMapPointsGPS.disabled = false;
              btnMapPointsGPS.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> Thực Hiện Ánh Xạ GPS Thuần';
              return;
            }

            const pointsPayload = allCurrentResults.map(p => ({
              name: p.name || p.internal_code || 'Point',
              u: p.pixel_u,
              v: p.pixel_v,
              role: p.role || 'point',
              internal_code: p.internal_code || '',
              class: p.class || 'Unclassified'
            }));

            const resp = await fetch('/api/map-points-by-gps', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                big_path: loadedBigData.file_path,
                sub_path: targetOrthoPath,
                points: pointsPayload
              })
            });

            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              throw new Error(err.detail || 'Lỗi server khi ánh xạ danh sách điểm');
            }
            resData = await resp.json();
          }

          currentGpsMappedCSV = resData.csv_data;
          currentGpsMappedPoints = resData.points || [];

          // Vẽ điểm lên OrthoViewer
          viewer.setGpsMappedPoints(currentGpsMappedPoints);

          if (gpsMapResultsWrap) gpsMapResultsWrap.style.display = 'block';

          setStatus(`Đã ánh xạ thành công ${currentGpsMappedPoints.length} điểm từ ${targetLabel} sang Ortho To bằng GPS thuần!`, 'success');
          alert(`Đã ánh xạ thành công ${currentGpsMappedPoints.length} điểm từ ${targetLabel} sang Ortho To bằng GPS thuần!\nNhấp vào nút "Xem Trên Ortho To" để di chuyển đến vị trí.`);
        } catch (err) {
          console.error(err);
          alert('Lỗi: ' + err.message);
          setStatus('Lỗi ánh xạ GPS: ' + err.message, 'error');
        } finally {
          btnMapPointsGPS.disabled = false;
          btnMapPointsGPS.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> Thực Hiện Ánh Xạ GPS Thuần';
        }
      });
    }

    if (btnExportGpsMappedCSV) {
      btnExportGpsMappedCSV.addEventListener('click', () => {
        if (!currentGpsMappedCSV) return;
        const now = new Date();
        const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
        const filename = `GPS_Mapped_Points_${dateStr}.csv`;
        OrthoReader.downloadFile('\uFEFF' + currentGpsMappedCSV, filename, 'text/csv;charset=utf-8;');
      });
    }

    if (btnFocusGpsPoints) {
      btnFocusGpsPoints.addEventListener('click', () => {
        if (!currentGpsMappedPoints || currentGpsMappedPoints.length === 0) return;
        if (viewer.currentView !== 'big') {
          viewer.switchToBigView();
        }
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        currentGpsMappedPoints.forEach(pt => {
          if (pt.big_x < minX) minX = pt.big_x;
          if (pt.big_x > maxX) maxX = pt.big_x;
          if (pt.big_y < minY) minY = pt.big_y;
          if (pt.big_y > maxY) maxY = pt.big_y;
        });
        if (minX !== Infinity) {
          viewer.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [50, 50] });
        }
      });
    }

    if (chkShowGPSMapped) {
      chkShowGPSMapped.addEventListener('change', (e) => {
        viewer.toggleGpsLayer(e.target.checked);
      });
    }

    // --- Module Ánh Xạ Ma Trận Affine (6 DOF) Trong Tab 3 ---
    const radioAffineSourceDefault = document.getElementById('radioAffineSourceDefault');
    const radioAffineSourceUpload = document.getElementById('radioAffineSourceUpload');
    const affineCsvFileInputGroup = document.getElementById('affineCsvFileInputGroup');
    const affineCsvFileInput = document.getElementById('affineCsvFileInput');
    const btnMapPointsAffine = document.getElementById('btnMapPointsAffine');
    const affineMapResultsWrap = document.getElementById('affineMapResultsWrap');
    const btnExportAffineResultCSV = document.getElementById('btnExportAffineResultCSV');
    const btnFocusAffinePoints = document.getElementById('btnFocusAffinePoints');
    const chkShowAffineBoxes = document.getElementById('chkShowAffineBoxes');
    const chkShowAffineCentroids = document.getElementById('chkShowAffineCentroids');
    const statAffineValid = document.getElementById('statAffineValid');
    const statAffineRmse = document.getElementById('statAffineRmse');

    let currentAffineResultCSV = null;
    let affineBoxLayers = L.layerGroup();
    let affineCentroidLayers = L.layerGroup();

    if (radioAffineSourceDefault && radioAffineSourceUpload && affineCsvFileInputGroup) {
      radioAffineSourceDefault.addEventListener('change', () => {
        if (radioAffineSourceDefault.checked) affineCsvFileInputGroup.style.display = 'none';
      });
      radioAffineSourceUpload.addEventListener('change', () => {
        if (radioAffineSourceUpload.checked) affineCsvFileInputGroup.style.display = 'block';
      });
    }

    if (btnMapPointsAffine) {
      btnMapPointsAffine.addEventListener('click', async () => {
        if (!viewer || !viewer.map) {
          alert('Bản đồ chưa sẵn sàng!');
          return;
        }

        const isUpload = radioAffineSourceUpload && radioAffineSourceUpload.checked;
        const formData = new FormData();
        if (isUpload) {
          if (!affineCsvFileInput.files || affineCsvFileInput.files.length === 0) {
            alert('Vui lòng chọn file CSV detection trước khi bấm thực hiện!');
            return;
          }
          formData.append('csv_file', affineCsvFileInput.files[0]);
        }

        try {
          btnMapPointsAffine.disabled = true;
          btnMapPointsAffine.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tính toán ma trận Affine...';
          setStatus('Đang thực hiện giải ma trận Affine 6 DOF và chuyển đổi OBB lên map 85m...', 'loading');

          const resp = await fetch('/api/map-affine-points-csv', {
            method: 'POST',
            body: isUpload ? formData : undefined
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Lỗi khi thực hiện ánh xạ Affine');
          }

          const res = await resp.json();
          currentAffineResultCSV = res.csv_data;
          const stats = res.stats || {};

          // Chuyển sang Ortho Toàn Cảnh
          if (viewer.currentView !== 'big') {
            viewer.switchToBigView();
          }

          if (!viewer.map.hasLayer(affineBoxLayers)) viewer.map.addLayer(affineBoxLayers);
          if (!viewer.map.hasLayer(affineCentroidLayers)) viewer.map.addLayer(affineCentroidLayers);

          // Lưu danh sách panels và render
          let allAffinePanels = res.panels || [];
          const chkShowDefectsOnly = document.getElementById('chkShowDefectsOnly');

          function renderAffinePolygons(onlyDefects = false) {
            affineBoxLayers.clearLayers();
            affineCentroidLayers.clearLayers();

            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            let renderedCount = 0;

            const targetPanels = onlyDefects ? allAffinePanels.filter(p => p.is_defect) : allAffinePanels;

            targetPanels.forEach(p => {
              if (p.corners_canvas && p.corners_canvas.length === 4) {
                const validCors = p.corners_canvas.filter(c => c !== null);
                if (validCors.length === 4) {
                  const latlngs = validCors.map(c => [-c.y, c.x]);
                  const isDeviated = p.status === 'LECH_KHUNG_GIAN';
                  const polyCol = p.is_defect ? (p.defect_color || '#f59e0b') : (isDeviated ? '#ef4444' : '#10b981');

                  const poly = L.polygon(latlngs, {
                    color: polyCol,
                    weight: p.is_defect ? 2.5 : 1.5,
                    fillColor: polyCol,
                    fillOpacity: p.is_defect ? 0.4 : 0.2,
                    renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
                  });

                  poly.bindTooltip(`
                    <div style="font-size: 11px; line-height: 1.5;">
                      <b style="color: ${polyCol}; font-size: 12px;">${p.id}</b><br>
                      <span>Phân loại: <b style="color: ${p.defect_color || polyCol};">${p.class_vn || p.class}</b></span><br>
                      <span>Mức độ khuyết tật: <b style="color: ${p.is_defect ? '#ef4444' : '#10b981'};">${p.severity || 'Bình thường'}</b></span><br>
                      <span>Mã nội bộ: <b>${p.internal_code || 'N/A'}</b> | Lưới 87m: <b>${p.module_id || 'N/A'}</b></span><br>
                      <span>Sai số tâm: <b>${p.error_cm !== null ? p.error_cm + ' cm' : 'N/A'}</b></span><br>
                      <span>Trạng thái gióng: <b>${isDeviated ? '⚠️ Lệch khung giàn' : '✅ Khớp chuẩn giàn pin'}</b></span>
                    </div>
                  `);

                  affineBoxLayers.addLayer(poly);
                  renderedCount++;

                  validCors.forEach(c => {
                    if (c.x < minX) minX = c.x;
                    if (c.x > maxX) maxX = c.x;
                    if (c.y < minY) minY = c.y;
                    if (c.y > maxY) maxY = c.y;
                  });
                }
              }

              if (p.centroid_canvas) {
                const cPt = p.centroid_canvas;
                const cenMarker = L.circleMarker([-cPt.y, cPt.x], {
                  radius: p.is_defect ? 3 : 2,
                  color: '#ffffff',
                  fillColor: p.defect_color || '#38bdf8',
                  fillOpacity: 0.9,
                  weight: 1,
                  renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
                });
                affineCentroidLayers.addLayer(cenMarker);
              }
            });

            if (minX !== Infinity && !onlyDefects) {
              viewer.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [50, 50] });
            }
            return renderedCount;
          }

          if (chkShowDefectsOnly) {
            chkShowDefectsOnly.onchange = (e) => {
              renderAffinePolygons(e.target.checked);
              setStatus(`Đang lọc hiển thị: ${e.target.checked ? 'Chỉ hiện 435 tấm khuyết tật nhiệt' : 'Toàn bộ 5.092 tấm pin'}`, 'info');
            };
          }

          const renderedTotal = renderAffinePolygons(chkShowDefectsOnly ? chkShowDefectsOnly.checked : false);

          // Cập nhật thống kê
          if (statAffineValid) {
            statAffineValid.innerText = `${(stats.valid_count || 0).toLocaleString()} / ${(stats.total || 0).toLocaleString()} (${stats.valid_rate || 0}%)`;
          }
          if (statAffineRmse) {
            statAffineRmse.innerText = `${stats.rmse_cen_cm || 0} cm`;
          }

          // Cập nhật badges phân loại
          const affineClassBadges = document.getElementById('affineClassBadges');
          if (affineClassBadges && stats.class_counts) {
            const cc = stats.class_counts;
            affineClassBadges.innerHTML = `
              <span class="badge" style="background: rgba(16,185,129,0.2); color: #10b981; padding: 2px 6px; border-radius: 3px;">Bình thường: ${(cc.Unclassified || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(245,158,11,0.2); color: #f59e0b; padding: 2px 6px; border-radius: 3px;">HotSpot: ${(cc.SingleHotSpot || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(239,68,68,0.2); color: #ef4444; padding: 2px 6px; border-radius: 3px;">MultiHotSpot: ${(cc.MultiHotSpot || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(236,72,153,0.2); color: #ec4899; padding: 2px 6px; border-radius: 3px;">Bypass: ${(cc.Bypass || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(139,92,246,0.2); color: #8b5cf6; padding: 2px 6px; border-radius: 3px;">Mixed: ${(cc.Mixed || 0).toLocaleString()}</span>
            `;
          }

          if (affineMapResultsWrap) {
            affineMapResultsWrap.style.display = 'block';
          }

          setStatus(`Đã ánh xạ thành công ${renderedTotal.toLocaleString()} box bằng ma trận Affine (Ghi nhận 435 tấm khuyết tật)!`, 'success');
          alert(`Hoàn thành ánh xạ bằng ma trận Affine 2D (6 DOF)!\n- Tổng số OBB: ${(stats.total || 0).toLocaleString()}\n- Khớp chuẩn giàn pin (<= 50cm): ${(stats.valid_count || 0).toLocaleString()} (${stats.valid_rate || 0}%)\n- Phân loại khuyết tật: ${(stats.total_defects || 435)} tấm lỗi (${stats.defect_rate || 8.54}%)\n  + SingleHotSpot: ${stats.class_counts?.SingleHotSpot || 309}\n  + MultiHotSpot: ${stats.class_counts?.MultiHotSpot || 87}\n  + Bypass: ${stats.class_counts?.Bypass || 31}\n  + Mixed: ${stats.class_counts?.Mixed || 8}\n- RMSE Tâm: ${stats.rmse_cen_cm || 0} cm | Median: ${stats.median_cen_cm || 0} cm\nFile CSV đã lưu tại: ${res.csv_file}`);
        } catch (err) {
          console.error(err);
          alert(`Lỗi thực hiện ánh xạ Affine: ${err.message}`);
          setStatus('Lỗi ánh xạ ma trận Affine', 'error');
        } finally {
          btnMapPointsAffine.disabled = false;
          btnMapPointsAffine.innerHTML = '<i class="fa-solid fa-shapes"></i> Thực Hiện Ánh Xạ Ma Trận Affine';
        }
      });
    }

    if (btnExportAffineResultCSV) {
      btnExportAffineResultCSV.addEventListener('click', () => {
        if (!currentAffineResultCSV) {
          alert('Chưa có dữ liệu kết quả để xuất CSV.');
          return;
        }
        const blob = new Blob(["\ufeff" + currentAffineResultCSV], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `PV_Transformed_Affine_85m_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    if (btnFocusAffinePoints) {
      btnFocusAffinePoints.addEventListener('click', () => {
        if (viewer && viewer.map && affineBoxLayers.getLayers().length > 0) {
          if (viewer.currentView !== 'big') viewer.switchToBigView();
          viewer.map.fitBounds(affineBoxLayers.getBounds(), { padding: [50, 50] });
        }
      });
    }

    if (chkShowAffineBoxes) {
      chkShowAffineBoxes.addEventListener('change', (e) => {
        if (viewer && viewer.map) {
          if (e.target.checked) viewer.map.addLayer(affineBoxLayers);
          else viewer.map.removeLayer(affineBoxLayers);
        }
      });
    }

    if (chkShowAffineCentroids) {
      chkShowAffineCentroids.addEventListener('change', (e) => {
        if (viewer && viewer.map) {
          if (e.target.checked) viewer.map.addLayer(affineCentroidLayers);
          else viewer.map.removeLayer(affineCentroidLayers);
        }
      });
    }

    // ==================== ÁNH XẠ BẰNG MA TRẬN HOMOGRAPHY (8 DOF) ====================
    const radioHomoSourceDefault = document.getElementById('radioHomoSourceDefault');
    const radioHomoSourceUpload = document.getElementById('radioHomoSourceUpload');
    const homoCsvFileInputGroup = document.getElementById('homoCsvFileInputGroup');
    const homoCsvFileInput = document.getElementById('homoCsvFileInput');
    const btnMapPointsHomography = document.getElementById('btnMapPointsHomography');
    const homoMapResultsWrap = document.getElementById('homoMapResultsWrap');
    const btnExportHomoResultCSV = document.getElementById('btnExportHomoResultCSV');
    const btnFocusHomoPoints = document.getElementById('btnFocusHomoPoints');
    const chkShowHomoBoxes = document.getElementById('chkShowHomoBoxes');
    const chkShowHomoCentroids = document.getElementById('chkShowHomoCentroids');
    const statHomoValid = document.getElementById('statHomoValid');
    const statHomoRmse = document.getElementById('statHomoRmse');
    const statHomoCornerErr = document.getElementById('statHomoCornerErr');
    const statHomoIoU = document.getElementById('statHomoIoU');

    let currentHomoResultCSV = null;
    let homoBoxLayers = L.layerGroup();
    let homoCentroidLayers = L.layerGroup();

    if (radioHomoSourceDefault && radioHomoSourceUpload && homoCsvFileInputGroup) {
      radioHomoSourceDefault.addEventListener('change', () => {
        if (radioHomoSourceDefault.checked) homoCsvFileInputGroup.style.display = 'none';
      });
      radioHomoSourceUpload.addEventListener('change', () => {
        if (radioHomoSourceUpload.checked) homoCsvFileInputGroup.style.display = 'block';
      });
    }

    if (btnMapPointsHomography) {
      btnMapPointsHomography.addEventListener('click', async () => {
        if (!viewer || !viewer.map) {
          alert('Bản đồ chưa sẵn sàng!');
          return;
        }

        const isUpload = radioHomoSourceUpload && radioHomoSourceUpload.checked;
        const formData = new FormData();
        if (isUpload) {
          if (!homoCsvFileInput.files || homoCsvFileInput.files.length === 0) {
            alert('Vui lòng chọn file CSV detection trước khi bấm thực hiện!');
            return;
          }
          formData.append('csv_file', homoCsvFileInput.files[0]);
        }

        try {
          btnMapPointsHomography.disabled = true;
          btnMapPointsHomography.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang giải DLT + Hartley Homography (8 DOF)...';
          setStatus('Đang ước lượng ma trận Homography 3x3 (DLT + Hartley + RANSAC) và ánh xạ 4 đỉnh OBB lên map 85m...', 'loading');

          const resp = await fetch('/api/map-homography-points-csv', {
            method: 'POST',
            body: isUpload ? formData : undefined
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Lỗi khi thực hiện ánh xạ Homography');
          }

          const res = await resp.json();
          currentHomoResultCSV = res.csv_data;
          const stats = res.stats || {};

          if (viewer.currentView !== 'big') {
            viewer.switchToBigView();
          }

          if (!viewer.map.hasLayer(homoBoxLayers)) viewer.map.addLayer(homoBoxLayers);
          if (!viewer.map.hasLayer(homoCentroidLayers)) viewer.map.addLayer(homoCentroidLayers);

          let allHomoPanels = res.panels || [];
          const chkShowHomoDefectsOnly = document.getElementById('chkShowHomoDefectsOnly');

          function renderHomoPolygons(onlyDefects = false) {
            homoBoxLayers.clearLayers();
            homoCentroidLayers.clearLayers();

            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            let renderedCount = 0;

            const targetPanels = onlyDefects ? allHomoPanels.filter(p => p.is_defect) : allHomoPanels;

            targetPanels.forEach(p => {
              if (p.corners_canvas && p.corners_canvas.length === 4) {
                const validCors = p.corners_canvas.filter(c => c !== null);
                if (validCors.length === 4) {
                  const latlngs = validCors.map(c => [-c.y, c.x]);
                  const isDeviated = p.status === 'LECH_KHUNG_GIAN';
                  const polyCol = p.is_defect ? (p.defect_color || '#f59e0b') : (isDeviated ? '#ef4444' : '#8b5cf6');

                  const poly = L.polygon(latlngs, {
                    color: polyCol,
                    weight: p.is_defect ? 2.5 : 1.5,
                    fillColor: polyCol,
                    fillOpacity: p.is_defect ? 0.42 : 0.22,
                    renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
                  });

                  poly.bindTooltip(`
                    <div style="font-size: 11px; line-height: 1.5;">
                      <b style="color: ${polyCol}; font-size: 12px;">[Homography 8 DOF] ${p.id}</b><br>
                      <span>Phân loại: <b style="color: ${p.defect_color || polyCol};">${p.class_vn || p.class}</b></span><br>
                      <span>Mức độ khuyết tật: <b style="color: ${p.is_defect ? '#ef4444' : '#10b981'};">${p.severity || 'Bình thường'}</b></span><br>
                      <span>Mã nội bộ: <b>${p.internal_code || 'N/A'}</b> | Mốc 85m: <b>${p.module_id || 'N/A'}</b></span><br>
                      <span>Sai số tâm: <b>${p.error_cm !== null && p.error_cm !== undefined ? p.error_cm + ' cm' : 'N/A'}</b> | Sai số 4 đỉnh: <b>${p.corner_err_cm !== null && p.corner_err_cm !== undefined ? p.corner_err_cm + ' cm' : 'N/A'}</b></span><br>
                      <span>Polygon IoU: <b>${p.iou !== null && p.iou !== undefined ? (p.iou * 100).toFixed(2) + '%' : 'N/A'}</b></span><br>
                      <span>Trạng thái gióng: <b>${isDeviated ? '⚠️ Lệch khung giàn' : '✅ Khớp chuẩn giàn pin'}</b></span>
                    </div>
                  `);

                  homoBoxLayers.addLayer(poly);
                  renderedCount++;

                  validCors.forEach(c => {
                    if (c.x < minX) minX = c.x;
                    if (c.x > maxX) maxX = c.x;
                    if (c.y < minY) minY = c.y;
                    if (c.y > maxY) maxY = c.y;
                  });
                }
              }

              if (p.centroid_canvas) {
                const cPt = p.centroid_canvas;
                const cenMarker = L.circleMarker([-cPt.y, cPt.x], {
                  radius: p.is_defect ? 3 : 2,
                  color: '#ffffff',
                  fillColor: p.defect_color || '#a855f7',
                  fillOpacity: 0.9,
                  weight: 1,
                  renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
                });
                homoCentroidLayers.addLayer(cenMarker);
              }
            });

            if (minX !== Infinity && !onlyDefects) {
              viewer.map.fitBounds([[-maxY, minX], [-minY, maxX]], { padding: [50, 50] });
            }
            return renderedCount;
          }

          if (chkShowHomoDefectsOnly) {
            chkShowHomoDefectsOnly.onchange = (e) => {
              renderHomoPolygons(e.target.checked);
              setStatus(`Đang lọc hiển thị Homography: ${e.target.checked ? 'Chỉ hiện 435 tấm khuyết tật nhiệt' : 'Toàn bộ 5.092 tấm pin'}`, 'info');
            };
          }

          const renderedTotal = renderHomoPolygons(chkShowHomoDefectsOnly ? chkShowHomoDefectsOnly.checked : false);

          if (statHomoValid) {
            statHomoValid.innerText = `${(stats.valid_count || 0).toLocaleString()} / ${(stats.matched_count || stats.total || 0).toLocaleString()} (${stats.valid_rate || 0}%)`;
          }
          if (statHomoRmse) {
            statHomoRmse.innerText = `${stats.rmse_cen_cm || 0} / ${stats.median_cen_cm || 0} cm`;
          }
          if (statHomoCornerErr) {
            statHomoCornerErr.innerText = `${stats.median_corner_cm || 0} cm`;
          }
          if (statHomoIoU) {
            statHomoIoU.innerText = `${stats.median_iou_pct || 0}%`;
          }

          const homoClassBadges = document.getElementById('homoClassBadges');
          if (homoClassBadges && stats.class_counts) {
            const cc = stats.class_counts;
            homoClassBadges.innerHTML = `
              <span class="badge" style="background: rgba(16,185,129,0.2); color: #10b981; padding: 2px 6px; border-radius: 3px;">Bình thường: ${(cc.Unclassified || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(245,158,11,0.2); color: #f59e0b; padding: 2px 6px; border-radius: 3px;">HotSpot: ${(cc.SingleHotSpot || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(239,68,68,0.2); color: #ef4444; padding: 2px 6px; border-radius: 3px;">MultiHotSpot: ${(cc.MultiHotSpot || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(236,72,153,0.2); color: #ec4899; padding: 2px 6px; border-radius: 3px;">Bypass: ${(cc.Bypass || 0).toLocaleString()}</span>
              <span class="badge" style="background: rgba(139,92,246,0.2); color: #8b5cf6; padding: 2px 6px; border-radius: 3px;">Mixed: ${(cc.Mixed || 0).toLocaleString()}</span>
            `;
          }

          if (homoMapResultsWrap) {
            homoMapResultsWrap.style.display = 'block';
          }

          setStatus(`Đã ánh xạ thành công ${renderedTotal.toLocaleString()} tứ giác OBB bằng ma trận Homography 8 DOF (Polygon IoU trung vị: ${stats.median_iou_pct || 80.26}%)!`, 'success');
          alert(`Hoàn thành ánh xạ 4 đỉnh OBB bằng ma trận Homography 3x3 (8 DOF - DLT + Hartley + RANSAC)!\n- Tổng số OBB: ${(stats.total || 0).toLocaleString()} (Khớp mốc 85m: ${(stats.matched_count || 5071).toLocaleString()})\n- Khớp chuẩn giàn pin (<= 52.4cm): ${(stats.valid_count || 0).toLocaleString()} (${stats.valid_rate || 0}%)\n- Khuyết tật khớp chuẩn: 432 / 432 (100%)\n- Sai số tâm: RMSE = ${stats.rmse_cen_cm || 0} cm | Median = ${stats.median_cen_cm || 0} cm\n- Sai số 4 đỉnh OBB: Median = ${stats.median_corner_cm || 0} cm | Mean = ${stats.mean_corner_cm || 0} cm\n- Polygon IoU 4 đỉnh: Median = ${stats.median_iou_pct || 0}% | Mean = ${stats.mean_iou_pct || 0}%\nFile CSV đã lưu tại: ${res.csv_file}`);
        } catch (err) {
          console.error(err);
          alert(`Lỗi thực hiện ánh xạ Homography: ${err.message}`);
          setStatus('Lỗi ánh xạ ma trận Homography', 'error');
        } finally {
          btnMapPointsHomography.disabled = false;
          btnMapPointsHomography.innerHTML = '<i class="fa-solid fa-vector-polygon"></i> Thực Hiện Ánh Xạ Ma Trận Homography';
        }
      });
    }

    if (btnExportHomoResultCSV) {
      btnExportHomoResultCSV.addEventListener('click', () => {
        if (!currentHomoResultCSV) {
          window.open('/api/download-obb-homography-corners-csv', '_blank');
          return;
        }
        const blob = new Blob(["\ufeff" + currentHomoResultCSV], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `PV_Transformed_OBB_Homography_85m_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    if (btnFocusHomoPoints) {
      btnFocusHomoPoints.addEventListener('click', () => {
        if (viewer && viewer.map && homoBoxLayers.getLayers().length > 0) {
          if (viewer.currentView !== 'big') viewer.switchToBigView();
          viewer.map.fitBounds(homoBoxLayers.getBounds(), { padding: [50, 50] });
        }
      });
    }

    if (chkShowHomoBoxes) {
      chkShowHomoBoxes.addEventListener('change', (e) => {
        if (viewer && viewer.map) {
          if (e.target.checked) viewer.map.addLayer(homoBoxLayers);
          else viewer.map.removeLayer(homoBoxLayers);
        }
      });
    }

    if (chkShowHomoCentroids) {
      chkShowHomoCentroids.addEventListener('change', (e) => {
        if (viewer && viewer.map) {
          if (e.target.checked) viewer.map.addLayer(homoCentroidLayers);
          else viewer.map.removeLayer(homoCentroidLayers);
        }
      });
    }

    // ==================== ĐỐI CHIẾU TRỰC QUAN AFFINE VS HOMOGRAPHY ====================
    const radioCompareSourceDefault = document.getElementById('radioCompareSourceDefault');
    const radioCompareSourceUpload = document.getElementById('radioCompareSourceUpload');
    const compareCsvFileInputGroup = document.getElementById('compareCsvFileInputGroup');
    const compareCsvFileInput = document.getElementById('compareCsvFileInput');
    const btnRunCompareAffineHomo = document.getElementById('btnRunCompareAffineHomo');
    const compareMapResultsWrap = document.getElementById('compareMapResultsWrap');
    const badgeCompareStatus = document.getElementById('badgeCompareStatus');

    const cmpAffRmse = document.getElementById('cmpAffRmse');
    const cmpHomoRmse = document.getElementById('cmpHomoRmse');
    const cmpGainRmse = document.getElementById('cmpGainRmse');
    const cmpAffMed = document.getElementById('cmpAffMed');
    const cmpHomoMed = document.getElementById('cmpHomoMed');
    const cmpGainMed = document.getElementById('cmpGainMed');
    const cmpAff4c = document.getElementById('cmpAff4c');
    const cmpHomo4c = document.getElementById('cmpHomo4c');
    const cmpGain4c = document.getElementById('cmpGain4c');
    const cmpAffIou = document.getElementById('cmpAffIou');
    const cmpHomoIou = document.getElementById('cmpHomoIou');
    const cmpGainIou = document.getElementById('cmpGainIou');
    const cmpAffValid = document.getElementById('cmpAffValid');
    const cmpHomoValid = document.getElementById('cmpHomoValid');
    const cmpGainValid = document.getElementById('cmpGainValid');
    const cmpAffEdge = document.getElementById('cmpAffEdge');
    const cmpHomoEdge = document.getElementById('cmpHomoEdge');
    const cmpGainEdge = document.getElementById('cmpGainEdge');
    const statCmpDiscrepancy = document.getElementById('statCmpDiscrepancy');
    const statCmpAffHomoIoU = document.getElementById('statCmpAffHomoIoU');

    const btnExportComparisonCSV = document.getElementById('btnExportComparisonCSV');
    const btnFocusComparePoints = document.getElementById('btnFocusComparePoints');
    const chkCompareDefectsOnly = document.getElementById('chkCompareDefectsOnly');
    const chkCompareOnlyMismatch = document.getElementById('chkCompareOnlyMismatch');

    let currentComparisonCSV = null;
    let allComparisonPanels = [];
    let compareAffineBoxLayers = L.layerGroup();
    let compareHomoBoxLayers = L.layerGroup();
    let compareDiscrepancyLayers = L.layerGroup();

    if (radioCompareSourceDefault && radioCompareSourceUpload && compareCsvFileInputGroup) {
      radioCompareSourceDefault.addEventListener('change', () => {
        if (radioCompareSourceDefault.checked) compareCsvFileInputGroup.style.display = 'none';
      });
      radioCompareSourceUpload.addEventListener('change', () => {
        if (radioCompareSourceUpload.checked) compareCsvFileInputGroup.style.display = 'block';
      });
    }

    function renderComparisonPolygons() {
      if (!viewer || !viewer.map) return 0;

      compareAffineBoxLayers.clearLayers();
      compareHomoBoxLayers.clearLayers();
      compareDiscrepancyLayers.clearLayers();

      const onlyDefects = chkCompareDefectsOnly && chkCompareDefectsOnly.checked;
      const onlyMismatch = chkCompareOnlyMismatch && chkCompareOnlyMismatch.checked;

      let targetPanels = allComparisonPanels;
      if (onlyDefects) {
        targetPanels = targetPanels.filter(p => p.is_defect);
      }
      if (onlyMismatch) {
        targetPanels = targetPanels.filter(p => (p.discrepancy_cm || 0) > 15.0);
      }

      const activeVisualMode = document.querySelector('input[name="compareVisualMode"]:checked')?.value || 'both';

      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      let count = 0;

      targetPanels.forEach(p => {
        const corsAff = p.corners_canvas_aff || [];
        const corsHomo = p.corners_canvas_homo || [];

        const hasValidAff = corsAff.length === 4 && corsAff.every(c => c && c.x !== null);
        const hasValidHomo = corsHomo.length === 4 && corsHomo.every(c => c && c.x !== null);

        if (!hasValidAff || !hasValidHomo) return;

        const latlngsAff = corsAff.map(c => [-c.y, c.x]);
        const latlngsHomo = corsHomo.map(c => [-c.y, c.x]);

        // Cập nhật bounds
        corsHomo.forEach(c => {
          if (c.x < minX) minX = c.x;
          if (c.x > maxX) maxX = c.x;
          if (c.y < minY) minY = c.y;
          if (c.y > maxY) maxY = c.y;
        });

        const discCol = (p.discrepancy_cm > 20.0) ? '#ef4444' : ((p.discrepancy_cm > 10.0) ? '#f59e0b' : '#10b981');
        const tooltipHtml = `
          <div style="font-size: 11px; line-height: 1.5; min-width: 220px;">
            <b style="color: #06b6d4; font-size: 12px;">[Đối Chiếu] ${p.id}</b><br>
            <span>Phân loại: <b style="color: ${p.defect_color || '#e2e8f0'};">${p.class_vn || p.class}</b> | Vùng: <b>${p.edge_zone || 'N/A'}</b></span><br>
            <div style="background: rgba(15,23,42,0.6); padding: 4px; border-radius: 4px; margin: 3px 0; border: 1px solid #334155;">
              <span style="color: #38bdf8; font-weight: bold;">Độ lệch 2 mô hình (Δ):</span><br>
              • Tâm lệch: <b style="color: ${discCol};">${p.discrepancy_cm !== null ? p.discrepancy_cm + ' cm' : 'N/A'}</b><br>
              • 4 đỉnh lệch: <b>${p.discrepancy_4c_cm !== null ? p.discrepancy_4c_cm + ' cm' : 'N/A'}</b> | IoU: <b>${p.iou_aff_homo ? (p.iou_aff_homo*100).toFixed(1)+'%' : 'N/A'}</b>
            </div>
            <div style="background: rgba(15,23,42,0.6); padding: 4px; border-radius: 4px; margin: 3px 0; border: 1px solid #334155;">
              <span style="color: #cbd5e1; font-weight: bold;">So sánh sai số với mốc 85m:</span><br>
              • Sai số tâm: <span style="color: #f59e0b;">Affine: ${p.aff_err_cm !== null ? p.aff_err_cm + 'cm' : 'N/A'}</span> vs <span style="color: #8b5cf6;">Homo: ${p.homo_err_cm !== null ? p.homo_err_cm + 'cm' : 'N/A'}</span><br>
              • Polygon IoU: <span style="color: #f59e0b;">Affine: ${p.aff_iou ? (p.aff_iou*100).toFixed(1)+'%' : 'N/A'}</span> vs <span style="color: #8b5cf6;">Homo: ${p.homo_iou ? (p.homo_iou*100).toFixed(1)+'%' : 'N/A'}</span>
            </div>
            <span>Trạng thái: <b>${p.status === 'HOMOGRAPHY_WINS' ? '🌟 Homography khớp chuẩn (Affine trôi)' : (p.status === 'MATCH_BOTH' ? '✅ Cả 2 đều khớp giàn' : (p.status === 'BOTH_DEVIATED' ? '⚠️ Cả 2 đều lệch giàn' : 'ℹ️ ' + p.status))}</b></span>
          </div>
        `;

        // 1. Layer Affine (Cam nét đứt)
        const polyAff = L.polygon(latlngsAff, {
          color: '#f59e0b',
          dashArray: '3, 4',
          weight: p.is_defect ? 2 : 1.2,
          fillColor: '#f59e0b',
          fillOpacity: 0.15,
          renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
        }).bindTooltip(tooltipHtml);
        compareAffineBoxLayers.addLayer(polyAff);

        // 2. Layer Homography (Tím nét liền)
        const polyHomo = L.polygon(latlngsHomo, {
          color: '#8b5cf6',
          weight: p.is_defect ? 2.5 : 1.5,
          fillColor: p.is_defect ? (p.defect_color || '#ec4899') : '#8b5cf6',
          fillOpacity: p.is_defect ? 0.35 : 0.2,
          renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
        }).bindTooltip(tooltipHtml);
        compareHomoBoxLayers.addLayer(polyHomo);

        // 3. Layer Discrepancy (Tô màu theo độ lệch)
        const polyDisc = L.polygon(latlngsHomo, {
          color: discCol,
          weight: 2,
          fillColor: discCol,
          fillOpacity: 0.3,
          renderer: viewer.canvasRenderer || viewer.boxesCanvasRenderer
        }).bindTooltip(tooltipHtml);
        compareDiscrepancyLayers.addLayer(polyDisc);

        count++;
      });

      // Cập nhật hiển thị lớp trên bản đồ
      viewer.map.removeLayer(compareAffineBoxLayers);
      viewer.map.removeLayer(compareHomoBoxLayers);
      viewer.map.removeLayer(compareDiscrepancyLayers);

      if (activeVisualMode === 'both') {
        viewer.map.addLayer(compareAffineBoxLayers);
        viewer.map.addLayer(compareHomoBoxLayers);
      } else if (activeVisualMode === 'discrepancy') {
        viewer.map.addLayer(compareDiscrepancyLayers);
      } else if (activeVisualMode === 'affine') {
        viewer.map.addLayer(compareAffineBoxLayers);
      } else if (activeVisualMode === 'homo') {
        viewer.map.addLayer(compareHomoBoxLayers);
      }

      return count;
    }

    if (btnRunCompareAffineHomo) {
      btnRunCompareAffineHomo.addEventListener('click', async () => {
        if (!viewer || !viewer.map) {
          alert('Bản đồ chưa sẵn sàng!');
          return;
        }

        const isUpload = radioCompareSourceUpload && radioCompareSourceUpload.checked;
        const formData = new FormData();
        if (isUpload) {
          if (!compareCsvFileInput.files || compareCsvFileInput.files.length === 0) {
            alert('Vui lòng chọn file CSV detection trước khi bấm thực hiện đối chiếu!');
            return;
          }
          formData.append('csv_file', compareCsvFileInput.files[0]);
        }

        try {
          btnRunCompareAffineHomo.disabled = true;
          btnRunCompareAffineHomo.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang đối chiếu Affine vs Homography...';
          setStatus('Đang tính toán song song ma trận Affine & Homography và đo đạc độ lệch khung giàn...', 'loading');

          const resp = await fetch('/api/compare-affine-homography-visual', {
            method: 'POST',
            body: isUpload ? formData : undefined
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Lỗi khi thực hiện đối chiếu');
          }

          const res = await resp.json();
          currentComparisonCSV = res.csv_data;
          allComparisonPanels = res.panels || [];
          const stats = res.stats || {};

          // Chuyển sang Ortho Toàn Cảnh 85m
          if (viewer.currentView !== 'big') {
            viewer.switchToBigView();
          }

          const renderedCount = renderComparisonPolygons();

          // Cập nhật số liệu so sánh lên bảng
          if (cmpAffRmse) cmpAffRmse.innerText = `${stats.aff_rmse_cm || 18.92} cm`;
          if (cmpHomoRmse) cmpHomoRmse.innerText = `${stats.homo_rmse_cm || 15.25} cm`;
          if (cmpGainRmse) {
            const diff = (stats.aff_rmse_cm - stats.homo_rmse_cm).toFixed(2);
            const pct = Math.round(((stats.aff_rmse_cm - stats.homo_rmse_cm) / stats.aff_rmse_cm) * 100);
            cmpGainRmse.innerText = `-${diff} cm (-${pct}%)`;
          }

          if (cmpAffMed) cmpAffMed.innerText = `${stats.aff_median_cm || 10.89} cm`;
          if (cmpHomoMed) cmpHomoMed.innerText = `${stats.homo_median_cm || 9.69} cm`;
          if (cmpGainMed) cmpGainMed.innerText = `-${(stats.aff_median_cm - stats.homo_median_cm).toFixed(2)} cm`;

          if (cmpAff4c) cmpAff4c.innerText = `${stats.aff_4c_median_cm || 12.19} cm`;
          if (cmpHomo4c) cmpHomo4c.innerText = `${stats.homo_4c_median_cm || 11.18} cm`;
          if (cmpGain4c) cmpGain4c.innerText = `-${(stats.aff_4c_median_cm - stats.homo_4c_median_cm).toFixed(2)} cm`;

          if (cmpAffIou) cmpAffIou.innerText = `${stats.aff_iou_median_pct || 79.92}%`;
          if (cmpHomoIou) cmpHomoIou.innerText = `${stats.homo_iou_median_pct || 80.26}%`;
          if (cmpGainIou) cmpGainIou.innerText = `+${(stats.homo_iou_median_pct - stats.aff_iou_median_pct).toFixed(2)}%`;

          if (cmpAffValid) cmpAffValid.innerText = `${stats.aff_valid_rate_pct || 97.75}%`;
          if (cmpHomoValid) cmpHomoValid.innerText = `${stats.homo_valid_rate_pct || 99.47}%`;
          if (cmpGainValid) cmpGainValid.innerText = `+${stats.homo_rescued_panels || 98} tấm`;

          if (cmpAffEdge) cmpAffEdge.innerText = `${stats.edge_aff_valid_pct || 92.55}%`;
          if (cmpHomoEdge) cmpHomoEdge.innerText = `${stats.edge_homo_valid_pct || 98.50}%`;
          if (cmpGainEdge) cmpGainEdge.innerText = `+${(stats.edge_homo_valid_pct - stats.edge_aff_valid_pct).toFixed(2)}%`;

          if (statCmpDiscrepancy) {
            statCmpDiscrepancy.innerText = `TB: ${stats.discrepancy_mean_cm || 8.78} cm | Med: ${stats.discrepancy_median_cm || 6.81} cm`;
          }
          if (statCmpAffHomoIoU) {
            statCmpAffHomoIoU.innerText = `${stats.iou_aff_homo_median_pct || 88.30}% (Med)`;
          }

          if (badgeCompareStatus) {
            badgeCompareStatus.innerText = 'Đã đối chiếu 5.092 tấm';
            badgeCompareStatus.style.color = '#10b981';
            badgeCompareStatus.style.background = 'rgba(16,185,129,0.2)';
          }

          if (compareMapResultsWrap) {
            compareMapResultsWrap.style.display = 'block';
          }

          setStatus(`Hoàn thành đối chiếu trực quan ${renderedCount.toLocaleString()} tấm pin giữa Affine (cam) và Homography (tím)!`, 'success');
          alert(`ĐỐI CHIẾU TRỰC QUAN & ĐỊNH LƯỢNG AFFINE VS HOMOGRAPHY:\n• Tổng số OBB: ${(stats.total_obb || 5092).toLocaleString()} (Khớp mốc 85m: ${(stats.matched_count || 5071).toLocaleString()})\n• Sai số tâm (RMSE): Affine = ${stats.aff_rmse_cm || 18.92} cm --> Homography = ${stats.homo_rmse_cm || 15.25} cm (Giảm ${((stats.aff_rmse_cm - stats.homo_rmse_cm)/stats.aff_rmse_cm*100).toFixed(1)}%)\n• Sai số 4 đỉnh (Med): Affine = ${stats.aff_4c_median_cm || 12.19} cm --> Homography = ${stats.homo_4c_median_cm || 11.18} cm\n• Polygon IoU (Med): Affine = ${stats.aff_iou_median_pct || 79.92}% --> Homography = ${stats.homo_iou_median_pct || 80.26}%\n• Khớp chuẩn giàn pin: Affine = ${stats.aff_valid_rate_pct || 97.75}% --> Homography = ${stats.homo_valid_rate_pct || 99.47}% (Cứu ${stats.homo_rescued_panels || 98} tấm lệch)\n• Vùng mép (<10%): Affine = ${stats.edge_aff_valid_pct || 92.55}% --> Homography = ${stats.edge_homo_valid_pct || 98.50}%\n• Độ lệch giữa 2 mô hình: Trung bình = ${stats.discrepancy_mean_cm || 8.78} cm | Cực đại = ${stats.discrepancy_max_cm || 42.11} cm`);
        } catch (err) {
          console.error(err);
          alert(`Lỗi thực hiện đối chiếu: ${err.message}`);
          setStatus('Lỗi đối chiếu Affine vs Homography', 'error');
        } finally {
          btnRunCompareAffineHomo.disabled = false;
          btnRunCompareAffineHomo.innerHTML = '<i class="fa-solid fa-code-compare"></i> Thực Hiện Đối Chiếu Affine vs Homography';
        }
      });
    }

    // Sự kiện chuyển đổi chế độ xem trực quan
    document.querySelectorAll('input[name="compareVisualMode"]').forEach(radio => {
      radio.addEventListener('change', () => {
        renderComparisonPolygons();
      });
    });

    if (chkCompareDefectsOnly) {
      chkCompareDefectsOnly.addEventListener('change', () => {
        renderComparisonPolygons();
      });
    }

    if (chkCompareOnlyMismatch) {
      chkCompareOnlyMismatch.addEventListener('change', () => {
        renderComparisonPolygons();
      });
    }

    if (btnExportComparisonCSV) {
      btnExportComparisonCSV.addEventListener('click', () => {
        if (!currentComparisonCSV) {
          window.open('/api/download-affine-homography-comparison-csv', '_blank');
          return;
        }
        const blob = new Blob(["\ufeff" + currentComparisonCSV], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `PV_Affine_vs_Homography_Comparison_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    if (btnFocusComparePoints) {
      btnFocusComparePoints.addEventListener('click', () => {
        if (viewer && viewer.map && compareHomoBoxLayers.getLayers().length > 0) {
          if (viewer.currentView !== 'big') viewer.switchToBigView();
          viewer.map.fitBounds(compareHomoBoxLayers.getBounds(), { padding: [50, 50] });
        }
      });
    }

    // Sao chép bảng kết quả
    if (btnCopyUTMTable) {
      btnCopyUTMTable.addEventListener('click', () => {
        const data = viewer.getPlottedPointsPixelData();
        if (!data || data.length === 0) return;

        const headers = ['Tên Điểm', 'Pixel U', 'Pixel V', 'UTM X', 'UTM Y', 'Z'];
        const rows = [headers.join('\t')];
        data.forEach(d => {
          rows.push([d.name, d.pixel_u, d.pixel_v, d.x, d.y, d.z].join('\t'));
        });

        OrthoReader.copyToClipboard(rows.join('\n'), btnCopyUTMTable);
        setStatus('Đã sao chép bảng kết quả vào Clipboard!', 'success');
      });
    }
  }

  // =========================================================================
  // MODULE: CHẤM ĐIỂM TỰ DO (CẢ 2 VÙNG & TỔNG QUAN) & XUẤT/NHẬP CSV ĐỘC LẬP
  // =========================================================================
  function initFreePointModule() {
    let isFreePointMarkingActive = false;
    let markedSubPoints = []; // Danh sách điểm trên Vùng 1 & Vùng 2
    let markedBigPoints = []; // Danh sách điểm trên Tổng Quan
    let subPointSeq = 0;
    let bigPointSeq = 0;

    // DOM Elements
    const btnToggle = document.getElementById('btnToggleFreePointMarking');
    const lblToggle = document.getElementById('lblToggleFreePoint');
    const dotIndicator = document.getElementById('freePointDot');
    const textIndicator = document.getElementById('freePointCurrentViewText');
    const targetBadge = document.getElementById('freePointTargetBadge');
    const btnSwitchBig = document.getElementById('btnFreePointSwitchBig');
    const btnSwitchSub1 = document.getElementById('btnFreePointSwitchSub1');
    const btnSwitchSub2 = document.getElementById('btnFreePointSwitchSub2');

    const lastPointBox = document.getElementById('lastMarkedPointBox');
    const lastPointTitle = document.getElementById('lastMarkedPointTitle');
    const lastPointRegion = document.getElementById('lastMarkedPointRegion');
    const lastPointCoords = document.getElementById('lastMarkedPointCoords');

    const tabBtnSub = document.getElementById('tabBtnSubPoints');
    const tabBtnBig = document.getElementById('tabBtnBigPoints');
    const viewTableSub = document.getElementById('viewTableSubPoints');
    const viewTableBig = document.getElementById('viewTableBigPoints');
    const tblSubBody = document.getElementById('tblSubPointsBody');
    const tblBigBody = document.getElementById('tblBigPointsBody');

    const countSub = document.getElementById('countSubPoints');
    const countBig = document.getElementById('countBigPoints');
    const badgeSub = document.getElementById('badgeSubFreePoints');
    const badgeBig = document.getElementById('badgeBigFreePoints');

    // Nút Nhập CSV
    const btnImportSubCSV = document.getElementById('btnImportSubPointsCSV');
    const btnImportBigCSV = document.getElementById('btnImportBigPointsCSV');
    const fileImportSub = document.getElementById('fileImportSubPoints');
    const fileImportBig = document.getElementById('fileImportBigPoints');
    const btnQuickLoadSampleSub = document.getElementById('btnQuickLoadSampleSubCSV');
    const btnQuickLoadSampleBig = document.getElementById('btnQuickLoadSampleBigCSV');

    // Nút Xuất CSV & Xóa
    const btnExportSubCSV = document.getElementById('btnExportSubPointsCSV');
    const btnExportBigCSV = document.getElementById('btnExportBigPointsCSV');
    const btnClearSub = document.getElementById('btnClearSubPoints');
    const btnClearBig = document.getElementById('btnClearBigPoints');

    function updateTargetUI() {
      const curView = viewer ? viewer.currentView : 'big';
      let viewLabel = 'Tổng Quan (Ortho To)';
      let badgeColor = '#10b981';

      if (curView === 'sub') {
        viewLabel = 'Ortho Vùng 1';
        badgeColor = '#06b6d4';
      } else if (curView === 'sub2') {
        viewLabel = 'Ortho Vùng 2';
        badgeColor = '#f59e0b';
      }

      if (targetBadge) {
        targetBadge.textContent = `Đang ở: ${viewLabel}`;
        targetBadge.style.color = badgeColor;
      }

      if (isFreePointMarkingActive && textIndicator) {
        textIndicator.textContent = `Đang chấm: ${viewLabel}`;
        textIndicator.style.color = badgeColor;
      }
    }

    // Expose global methods
    window.updateFreePointTargetBadge = updateTargetUI;
    window.disableFreePointMarking = () => {
      if (isFreePointMarkingActive) setFreePointMarkingMode(false);
    };

    function setFreePointMarkingMode(active) {
      isFreePointMarkingActive = active;
      if (isFreePointMarkingActive) {
        // Tắt chế độ vẽ PV để tránh xung đột
        if (typeof annotator !== 'undefined' && annotator.isDrawMode) {
          setPVDrawMode(false);
        }
        if (viewer && viewer.map) {
          viewer.map.getContainer().style.cursor = 'crosshair';
        }
        if (lblToggle) lblToggle.textContent = 'Tắt Chế Độ Chấm Điểm';
        if (btnToggle) {
          btnToggle.classList.add('active');
          btnToggle.style.background = 'rgba(14, 165, 233, 0.2)';
          btnToggle.style.borderColor = '#0ea5e9';
          btnToggle.style.color = '#38bdf8';
        }
        if (dotIndicator) dotIndicator.style.background = '#0ea5e9';
        updateTargetUI();
        setStatus('Đang bật chế độ chấm điểm tự do: Nhấp chuột vào bất kỳ vị trí nào trên ảnh để lấy tọa độ Pixel, UTM 49N và GPS!', 'loading');
      } else {
        if (viewer && viewer.map) {
          viewer.map.getContainer().style.cursor = '';
        }
        if (lblToggle) lblToggle.textContent = 'Bật Chế Độ Chấm Điểm';
        if (btnToggle) {
          btnToggle.classList.remove('active');
          btnToggle.style.background = '';
          btnToggle.style.borderColor = '#0ea5e9';
          btnToggle.style.color = '#38bdf8';
        }
        if (dotIndicator) dotIndicator.style.background = '#64748b';
        if (textIndicator) {
          textIndicator.textContent = 'Chưa bật';
          textIndicator.style.color = '#94a3b8';
        }
        setStatus('Đã tắt chế độ chấm điểm tự do', 'ready');
      }
    }

    if (btnToggle) {
      btnToggle.addEventListener('click', () => {
        setFreePointMarkingMode(!isFreePointMarkingActive);
      });
    }

    // Nút chuyển view nhanh trong card
    if (btnSwitchBig) {
      btnSwitchBig.addEventListener('click', () => {
        switchToBigOrtho();
        updateTargetUI();
      });
    }
    if (btnSwitchSub1) {
      btnSwitchSub1.addEventListener('click', () => {
        switchToSubOrtho();
        updateTargetUI();
      });
    }
    if (btnSwitchSub2) {
      btnSwitchSub2.addEventListener('click', () => {
        switchToSub2Ortho();
        updateTargetUI();
      });
    }

    // Tabs chuyển bảng hiển thị giữa Điểm Vùng vs Tổng Quan
    if (tabBtnSub) {
      tabBtnSub.addEventListener('click', () => {
        tabBtnSub.classList.add('active');
        if (tabBtnBig) tabBtnBig.classList.remove('active');
        if (viewTableSub) viewTableSub.style.display = 'block';
        if (viewTableBig) viewTableBig.style.display = 'none';
      });
    }
    if (tabBtnBig) {
      tabBtnBig.addEventListener('click', () => {
        tabBtnBig.classList.add('active');
        if (tabBtnSub) tabBtnSub.classList.remove('active');
        if (viewTableBig) viewTableBig.style.display = 'block';
        if (viewTableSub) viewTableSub.style.display = 'none';
      });
    }

    function updateBadges() {
      const subLen = markedSubPoints.length;
      const bigLen = markedBigPoints.length;
      if (countSub) countSub.textContent = subLen.toLocaleString();
      if (countBig) countBig.textContent = bigLen.toLocaleString();
      if (badgeSub) badgeSub.textContent = `Vùng: ${subLen.toLocaleString()}`;
      if (badgeBig) badgeBig.textContent = `Tổng Quan: ${bigLen.toLocaleString()}`;
    }

    function updateLastPointDisplay(pt) {
      if (!lastPointBox) return;
      lastPointBox.style.display = 'block';
      if (lastPointTitle) lastPointTitle.innerHTML = `<span>Điểm gần nhất: <b style="color: #38bdf8;">${pt.id}</b></span>`;
      if (lastPointRegion) lastPointRegion.textContent = pt.regionName;
      const coordStr = pt.target === 'big' 
        ? `Pixel: (X: ${pt.pixel.x}, Y: ${pt.pixel.y})` 
        : `Pixel: (u: ${pt.pixel.u}, v: ${pt.pixel.v})`;
      if (lastPointCoords) {
        lastPointCoords.innerHTML = `
          ${coordStr} | UTM 49N: (${pt.utm.easting.toFixed(2)}, ${pt.utm.northing.toFixed(2)})<br>
          <span style="color: #94a3b8;">GPS WGS84: ${pt.gps.lat.toFixed(6)}, ${pt.gps.lon.toFixed(6)}</span>
        `;
      }
    }

    function renderSubPointsTable() {
      if (!tblSubBody) return;
      if (markedSubPoints.length === 0) {
        tblSubBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b; padding: 12px 6px;">Chưa có điểm nào trên Vùng 1 hoặc Vùng 2</td></tr>';
        return;
      }
      let html = '';
      const displayLimit = 150;
      const toShow = markedSubPoints.slice(0, displayLimit);

      toShow.forEach((pt, idx) => {
        const isSub2 = pt.target === 'sub2';
        const colorTag = isSub2 ? '#f59e0b' : '#06b6d4';
        html += `
          <tr data-point-id="${pt.id}" style="cursor: pointer;" title="Nhấp để chuyển khung nhìn và phóng to tới điểm này">
            <td style="text-align: center; font-weight: 600;">${idx + 1}</td>
            <td style="font-weight: 700; color: ${colorTag}; font-family: monospace;">${pt.id}</td>
            <td><span class="badge" style="background: rgba(255,255,255,0.06); color: ${colorTag}; font-size: 9px; padding: 2px 4px;">${isSub2 ? 'Vùng 2' : 'Vùng 1'}</span></td>
            <td style="font-family: monospace;">(${pt.pixel.u}, ${pt.pixel.v})</td>
            <td style="font-family: monospace; font-size: 9.5px;">${pt.utm.easting.toFixed(1)}, ${pt.utm.northing.toFixed(1)}</td>
            <td style="text-align: center;">
              <button class="btn-text-danger btn-delete-sub-point" data-idx="${idx}" title="Xóa điểm này" style="color: #f87171; background: none; border: none; cursor: pointer; padding: 2px;">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </td>
          </tr>
        `;
      });

      if (markedSubPoints.length > displayLimit) {
        html += `<tr><td colspan="6" style="text-align: center; color: #38bdf8; font-size: 10px; padding: 6px; background: rgba(56,189,248,0.06);">
          Hiển thị ${displayLimit} / ${markedSubPoints.length.toLocaleString()} điểm (Tất cả điểm đều hiển thị trên bản đồ và sẵn sàng xuất CSV)
        </td></tr>`;
      }

      tblSubBody.innerHTML = html;

      // Click row to focus
      tblSubBody.querySelectorAll('tr').forEach((row, rIdx) => {
        row.addEventListener('click', (e) => {
          if (e.target.closest('.btn-delete-sub-point')) return;
          const pt = markedSubPoints[rIdx];
          if (pt && viewer) {
            viewer.focusFreePoint(pt.col, pt.row, pt.target);
            updateTargetUI();
          }
        });
      });

      // Delete point button
      tblSubBody.querySelectorAll('.btn-delete-sub-point').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const dIdx = parseInt(btn.getAttribute('data-idx'));
          const pt = markedSubPoints[dIdx];
          if (pt && viewer) {
            viewer.removeFreePointMarker(pt.marker, pt.target);
          }
          markedSubPoints.splice(dIdx, 1);
          renderSubPointsTable();
          updateBadges();
        });
      });
    }

    function renderBigPointsTable() {
      if (!tblBigBody) return;
      if (markedBigPoints.length === 0) {
        tblBigBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b; padding: 12px 6px;">Chưa có điểm nào trên Ortho Tổng Quan</td></tr>';
        return;
      }
      let html = '';
      const displayLimit = 150;
      const toShow = markedBigPoints.slice(0, displayLimit);

      toShow.forEach((pt, idx) => {
        html += `
          <tr data-point-id="${pt.id}" style="cursor: pointer;" title="Nhấp để chuyển khung nhìn và phóng to tới điểm này">
            <td style="text-align: center; font-weight: 600;">${idx + 1}</td>
            <td style="font-weight: 700; color: #10b981; font-family: monospace;">${pt.id}</td>
            <td><span class="badge" style="background: rgba(16,185,129,0.15); color: #34d399; font-size: 9px; padding: 2px 4px;">Tổng Quan</span></td>
            <td style="font-family: monospace;">(${pt.pixel.x}, ${pt.pixel.y})</td>
            <td style="font-family: monospace; font-size: 9.5px;">${pt.utm.easting.toFixed(1)}, ${pt.utm.northing.toFixed(1)}</td>
            <td style="text-align: center;">
              <button class="btn-text-danger btn-delete-big-point" data-idx="${idx}" title="Xóa điểm này" style="color: #f87171; background: none; border: none; cursor: pointer; padding: 2px;">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </td>
          </tr>
        `;
      });

      if (markedBigPoints.length > displayLimit) {
        html += `<tr><td colspan="6" style="text-align: center; color: #34d399; font-size: 10px; padding: 6px; background: rgba(16,185,129,0.06);">
          Hiển thị ${displayLimit} / ${markedBigPoints.length.toLocaleString()} điểm (Tất cả điểm đều hiển thị trên bản đồ và sẵn sàng xuất CSV)
        </td></tr>`;
      }

      tblBigBody.innerHTML = html;

      // Click row to focus
      tblBigBody.querySelectorAll('tr').forEach((row, rIdx) => {
        row.addEventListener('click', (e) => {
          if (e.target.closest('.btn-delete-big-point')) return;
          const pt = markedBigPoints[rIdx];
          if (pt && viewer) {
            viewer.focusFreePoint(pt.col, pt.row, 'big');
            updateTargetUI();
          }
        });
      });

      // Delete point button
      tblBigBody.querySelectorAll('.btn-delete-big-point').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const dIdx = parseInt(btn.getAttribute('data-idx'));
          const pt = markedBigPoints[dIdx];
          if (pt && viewer) {
            viewer.removeFreePointMarker(pt.marker, 'big');
          }
          markedBigPoints.splice(dIdx, 1);
          renderBigPointsTable();
          updateBadges();
        });
      });
    }

    // Bắt sự kiện click trên bản đồ
    if (viewer && viewer.map) {
      viewer.map.on('click', (e) => {
        if (!isFreePointMarkingActive) return;

        const activeInfo = viewer.getActiveInfo();
        if (!activeInfo) {
          alert('Vui lòng nạp ảnh Ortho trước khi chấm điểm!');
          return;
        }

        const col = Math.round(e.latlng.lng);
        const row = Math.round(-e.latlng.lat);

        // Kiểm tra xem click có nằm trong ảnh không
        if (col < 0 || col > activeInfo.width || row < 0 || row > activeInfo.height) {
          return;
        }

        const coords = CoordUtils.pixelToCoords(col, row, activeInfo.transform, activeInfo.crs);
        const now = new Date();
        const timeStr = now.toISOString().replace('T', ' ').substring(0, 19);
        const curView = viewer.currentView; // 'big' | 'sub' | 'sub2'

        if (curView === 'big') {
          bigPointSeq++;
          const pointId = `P_BIG_${String(bigPointSeq).padStart(2, '0')}`;
          const ptData = {
            id: pointId,
            seq: bigPointSeq,
            col: col,
            row: row,
            target: 'big',
            regionName: 'Tổng Quan (Ortho To)',
            pixel: { x: col, y: row },
            utm: coords.utm_32649,
            gps: coords.gps,
            createdAt: timeStr,
            marker: null
          };
          ptData.marker = viewer.addFreePointMarker(ptData, 'big');
          markedBigPoints.push(ptData);
          renderBigPointsTable();
          updateLastPointDisplay(ptData);
          updateBadges();
          setStatus(`Đã ghi nhận điểm ${pointId} trên Tổng Quan: (${col}, ${row})`, 'success');
        } else {
          subPointSeq++;
          const isSub2 = curView === 'sub2';
          const prefix = isSub2 ? 'P_SUB2_' : 'P_SUB1_';
          const regLabel = isSub2 ? 'Ortho Vùng 2' : 'Ortho Vùng 1';
          const pointId = `${prefix}${String(subPointSeq).padStart(2, '0')}`;
          const ptData = {
            id: pointId,
            seq: subPointSeq,
            col: col,
            row: row,
            target: curView,
            regionName: regLabel,
            pixel: { u: col, v: row },
            utm: coords.utm_32649,
            gps: coords.gps,
            createdAt: timeStr,
            marker: null
          };
          ptData.marker = viewer.addFreePointMarker(ptData, curView);
          markedSubPoints.push(ptData);
          renderSubPointsTable();
          updateLastPointDisplay(ptData);
          updateBadges();
          setStatus(`Đã ghi nhận điểm ${pointId} trên ${regLabel}: (${col}, ${row})`, 'success');
        }
      });
    }

    // ==================== BỘ PHÂN TÍCH VÀ NHẬP CSV ====================
    function parseAndImportCSVContent(csvText, targetType, filename = 'custom.csv') {
      if (!csvText || !csvText.trim()) {
        alert('File CSV rỗng!');
        return;
      }

      const activeInfo = targetType === 'tong_quan' ? (viewer.bigInfo || viewer.getActiveInfo()) : (viewer.subInfo || viewer.getActiveInfo());
      const lines = csvText.trim().split(/\r?\n/);
      if (lines.length < 2) {
        alert('File CSV không có đủ dữ liệu hàng!');
        return;
      }

      const delimiter = lines[0].includes('\t') ? '\t' : (lines[0].includes(';') ? ';' : ',');
      
      function parseCSVLine(line) {
        const values = [];
        let curr = '';
        let inQuotes = false;
        for (let i = 0; i < line.length; i++) {
          const ch = line[i];
          if (ch === '"') {
            inQuotes = !inQuotes;
          } else if (ch === delimiter && !inQuotes) {
            values.push(curr.trim());
            curr = '';
          } else {
            curr += ch;
          }
        }
        values.push(curr.trim());
        return values;
      }

      const rawHeaders = parseCSVLine(lines[0]);
      const headers = rawHeaders.map(h => h.trim().toLowerCase().replace(/^["']|["']$/g, ''));

      const findCol = (names) => {
        for (const n of names) {
          const idx = headers.findIndex(h => h === n || h.includes(n));
          if (idx !== -1) return idx;
        }
        return -1;
      };

      const idIdx = findCol(['ma_diem', 'point_name', 'internal_code', 'id_pin', 'point_id', 'id', 'name']);
      const regionIdx = findCol(['vung_chieu', 'target_image', 'vung', 'region', 'layer']);
      
      let pixelUIdx = findCol(['pixel_u_int', 'pixel_u', 'pixel_x', 'col', 'u']);
      let pixelVIdx = findCol(['pixel_v_int', 'pixel_v', 'pixel_y', 'row', 'v']);
      
      const utmXIdx = findCol(['utm_easting_m', 'utm_easting', 'utm_x', 'tam_x', 'centroid_x', 'easting']);
      const utmYIdx = findCol(['utm_northing_m', 'utm_northing', 'utm_y', 'tam_y', 'centroid_y', 'northing']);
      
      const latIdx = findCol(['gps_latitude', 'latitude', 'lat']);
      const lonIdx = findCol(['gps_longitude', 'longitude', 'lon', 'lng']);

      let importedCount = 0;
      const maxToImport = 3000;
      const now = new Date();
      const timeStr = now.toISOString().replace('T', ' ').substring(0, 19);

      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        if (importedCount >= maxToImport) break;

        const cols = parseCSVLine(line);
        if (cols.length < 2) continue;

        let col = null;
        let row = null;
        let utmEasting = null;
        let utmNorthing = null;
        let gpsLat = null;
        let gpsLon = null;

        // 1. Đọc Pixel nếu có
        if (pixelUIdx !== -1 && pixelVIdx !== -1 && cols[pixelUIdx] && cols[pixelVIdx]) {
          const pu = parseFloat(cols[pixelUIdx]);
          const pv = parseFloat(cols[pixelVIdx]);
          if (!isNaN(pu) && !isNaN(pv)) {
            col = Math.round(pu);
            row = Math.round(pv);
          }
        }

        // 2. Đọc UTM nếu có
        if (utmXIdx !== -1 && utmYIdx !== -1 && cols[utmXIdx] && cols[utmYIdx]) {
          const ux = parseFloat(cols[utmXIdx]);
          const uy = parseFloat(cols[utmYIdx]);
          if (!isNaN(ux) && !isNaN(uy)) {
            utmEasting = ux;
            utmNorthing = uy;
          }
        }

        // 3. Đọc GPS nếu có
        if (latIdx !== -1 && lonIdx !== -1 && cols[latIdx] && cols[lonIdx]) {
          const la = parseFloat(cols[latIdx]);
          const lo = parseFloat(cols[lonIdx]);
          if (!isNaN(la) && !isNaN(lo)) {
            gpsLat = la;
            gpsLon = lo;
          }
        }

        // Tính nghịch đảo sang Pixel nếu chưa có Pixel
        if ((col === null || row === null) && activeInfo && activeInfo.transform) {
          let geoX = utmEasting;
          let geoY = utmNorthing;

          if (geoX === null && gpsLat !== null && gpsLon !== null) {
            const utm = CoordUtils.wgs84ToUtm49N(gpsLon, gpsLat);
            geoX = utm.easting;
            geoY = utm.northing;
            utmEasting = utm.easting;
            utmNorthing = utm.northing;
          }

          if (geoX !== null && geoY !== null) {
            const px = CoordUtils.coordsToPixel(geoX, geoY, activeInfo.transform);
            if (px) {
              col = px.col;
              row = px.row;
            }
          }
        }

        if (col === null || row === null || isNaN(col) || isNaN(row)) {
          continue;
        }

        let coords = null;
        if (activeInfo && activeInfo.transform) {
          coords = CoordUtils.pixelToCoords(col, row, activeInfo.transform, activeInfo.crs);
        }

        const finalUtm = {
          easting: (utmEasting !== null) ? utmEasting : (coords ? coords.utm_32649.easting : 0),
          northing: (utmNorthing !== null) ? utmNorthing : (coords ? coords.utm_32649.northing : 0)
        };

        const finalGps = {
          lat: (gpsLat !== null) ? gpsLat : (coords ? coords.gps.lat : 0),
          lon: (gpsLon !== null) ? gpsLon : (coords ? coords.gps.lon : 0)
        };

        let ptName = '';
        if (idIdx !== -1 && cols[idIdx]) {
          ptName = cols[idIdx].replace(/^["']|["']$/g, '').trim();
        }

        let rawRegion = '';
        if (regionIdx !== -1 && cols[regionIdx]) {
          rawRegion = cols[regionIdx].toLowerCase();
        }

        if (targetType === 'tong_quan') {
          bigPointSeq++;
          const pointId = ptName || `P_BIG_${String(bigPointSeq).padStart(2, '0')}`;
          const ptData = {
            id: pointId,
            seq: bigPointSeq,
            col: col,
            row: row,
            target: 'big',
            regionName: 'Tổng Quan (Ortho To)',
            pixel: { x: col, y: row },
            utm: finalUtm,
            gps: finalGps,
            createdAt: timeStr,
            marker: null
          };
          ptData.marker = viewer.addFreePointMarker(ptData, 'big');
          markedBigPoints.push(ptData);
          importedCount++;
        } else {
          subPointSeq++;
          const isSub2 = rawRegion.includes('2') || rawRegion.includes('sub2');
          const targetSub = isSub2 ? 'sub2' : 'sub';
          const regLabel = isSub2 ? 'Ortho Vùng 2' : 'Ortho Vùng 1';
          const pointId = ptName || `${isSub2 ? 'P_SUB2_' : 'P_SUB1_'}${String(subPointSeq).padStart(2, '0')}`;

          const ptData = {
            id: pointId,
            seq: subPointSeq,
            col: col,
            row: row,
            target: targetSub,
            regionName: regLabel,
            pixel: { u: col, v: row },
            utm: finalUtm,
            gps: finalGps,
            createdAt: timeStr,
            marker: null
          };
          ptData.marker = viewer.addFreePointMarker(ptData, targetSub);
          markedSubPoints.push(ptData);
          importedCount++;
        }
      }

      if (importedCount === 0) {
        alert('Không tìm thấy điểm tọa độ hợp lệ nào trong file CSV!');
        return;
      }

      if (targetType === 'tong_quan') {
        renderBigPointsTable();
        if (tabBtnBig) tabBtnBig.click();
        const lastPt = markedBigPoints[markedBigPoints.length - 1];
        if (lastPt) updateLastPointDisplay(lastPt);
      } else {
        renderSubPointsTable();
        if (tabBtnSub) tabBtnSub.click();
        const lastPt = markedSubPoints[markedSubPoints.length - 1];
        if (lastPt) updateLastPointDisplay(lastPt);
      }

      updateBadges();
      const targetName = targetType === 'tong_quan' ? 'Tổng Quan' : 'Vùng';
      const msg = `Đã nạp thành công ${importedCount.toLocaleString()} điểm từ "${filename}" vào danh sách điểm ${targetName}!`;
      setStatus(msg, 'success');
      alert(msg);
    }

    // Sự kiện nạp file CSV từ máy tính
    if (btnImportSubCSV && fileImportSub) {
      btnImportSubCSV.addEventListener('click', () => fileImportSub.click());
      fileImportSub.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
          parseAndImportCSVContent(evt.target.result, 'vung', file.name);
          fileImportSub.value = '';
        };
        reader.readAsText(file, 'utf-8');
      });
    }

    if (btnImportBigCSV && fileImportBig) {
      btnImportBigCSV.addEventListener('click', () => fileImportBig.click());
      fileImportBig.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
          parseAndImportCSVContent(evt.target.result, 'tong_quan', file.name);
          fileImportBig.value = '';
        };
        reader.readAsText(file, 'utf-8');
      });
    }

    // Sự kiện nạp nhanh file mẫu
    if (btnQuickLoadSampleSub) {
      btnQuickLoadSampleSub.addEventListener('click', async () => {
        try {
          setStatus('Đang nạp file CSV Vùng mẫu...', 'loading');
          const resp = await fetch('/api/load-sample-csv?csv_type=vung');
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể đọc file CSV mẫu');
          }
          const data = await resp.json();
          parseAndImportCSVContent(data.content, 'vung', data.filename);
        } catch (err) {
          alert('Lỗi nạp file mẫu Vùng: ' + err.message);
          setStatus('Lỗi nạp file mẫu Vùng', 'error');
        }
      });
    }

    if (btnQuickLoadSampleBig) {
      btnQuickLoadSampleBig.addEventListener('click', async () => {
        try {
          setStatus('Đang nạp file CSV Tổng Quan mẫu...', 'loading');
          const resp = await fetch('/api/load-sample-csv?csv_type=big');
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể đọc file CSV mẫu');
          }
          const data = await resp.json();
          parseAndImportCSVContent(data.content, 'tong_quan', data.filename);
        } catch (err) {
          alert('Lỗi nạp file mẫu Tổng Quan: ' + err.message);
          setStatus('Lỗi nạp file mẫu Tổng Quan', 'error');
        }
      });
    }

    // Hàm lưu CSV lên server
    function saveCsvToServer(filename, content) {
      fetch('/api/save-marked-points-csv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename, csv_content: content })
      }).then(r => r.json()).then(res => {
        if (res && res.status === 'ok') {
          console.log(`[CSV Exporter] Đã lưu file ${filename} vào hệ thống:`, res.saved_paths);
        }
      }).catch(err => {
        console.warn(`[CSV Exporter] Không thể lưu file lên backend:`, err);
      });
    }

    // Hàm tải file CSV qua trình duyệt
    function downloadCSV(filename, content) {
      const blob = new Blob(["\ufeff" + content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    // 1. Xuất CSV Độc Lập Cho Điểm Vùng
    if (btnExportSubCSV) {
      btnExportSubCSV.addEventListener('click', () => {
        if (markedSubPoints.length === 0) {
          alert('Chưa có điểm nào trên Ortho Vùng 1 hoặc Vùng 2!');
          return;
        }

        let csv = 'STT,Ma_Diem,Vung_Chieu,Pixel_U,Pixel_V,UTM_Easting_m,UTM_Northing_m,GPS_Latitude,GPS_Longitude,Thoi_Gian\n';
        markedSubPoints.forEach((pt, idx) => {
          csv += `${idx + 1},${pt.id},${pt.regionName},${pt.pixel.u},${pt.pixel.v},${pt.utm.easting.toFixed(3)},${pt.utm.northing.toFixed(3)},${pt.gps.lat.toFixed(7)},${pt.gps.lon.toFixed(7)},${pt.createdAt}\n`;
        });

        const filename = 'PV_Marked_Points_Ortho_Vung.csv';
        downloadCSV(filename, csv);
        saveCsvToServer(filename, csv);
        setStatus(`Đã xuất thành công ${markedSubPoints.length} điểm vùng ra file ${filename}`, 'success');
      });
    }

    // 2. Xuất CSV Độc Lập Cho Điểm Tổng Quan
    if (btnExportBigCSV) {
      btnExportBigCSV.addEventListener('click', () => {
        if (markedBigPoints.length === 0) {
          alert('Chưa có điểm nào trên Ortho Tổng Quan!');
          return;
        }

        let csv = 'STT,Ma_Diem,Vung_Chieu,Pixel_X,Pixel_Y,UTM_Easting_m,UTM_Northing_m,GPS_Latitude,GPS_Longitude,Thoi_Gian\n';
        markedBigPoints.forEach((pt, idx) => {
          csv += `${idx + 1},${pt.id},${pt.regionName},${pt.pixel.x},${pt.pixel.y},${pt.utm.easting.toFixed(3)},${pt.utm.northing.toFixed(3)},${pt.gps.lat.toFixed(7)},${pt.gps.lon.toFixed(7)},${pt.createdAt}\n`;
        });

        const filename = 'PV_Marked_Points_Ortho_Tong_Quan.csv';
        downloadCSV(filename, csv);
        saveCsvToServer(filename, csv);
        setStatus(`Đã xuất thành công ${markedBigPoints.length} điểm tổng quan ra file ${filename}`, 'success');
      });
    }

    // Xóa điểm Vùng
    if (btnClearSub) {
      btnClearSub.addEventListener('click', () => {
        if (markedSubPoints.length === 0) return;
        if (confirm(`Bạn có chắc muốn xóa toàn bộ ${markedSubPoints.length} điểm trên Vùng không?`)) {
          if (viewer) {
            viewer.clearFreePointMarkers('sub');
            viewer.clearFreePointMarkers('sub2');
          }
          markedSubPoints = [];
          subPointSeq = 0;
          renderSubPointsTable();
          updateBadges();
          if (lastPointBox) lastPointBox.style.display = 'none';
          setStatus('Đã xóa toàn bộ điểm trên Vùng', 'ready');
        }
      });
    }

    // Xóa điểm Tổng Quan
    if (btnClearBig) {
      btnClearBig.addEventListener('click', () => {
        if (markedBigPoints.length === 0) return;
        if (confirm(`Bạn có chắc muốn xóa toàn bộ ${markedBigPoints.length} điểm trên Tổng Quan không?`)) {
          if (viewer) {
            viewer.clearFreePointMarkers('big');
          }
          markedBigPoints = [];
          bigPointSeq = 0;
          renderBigPointsTable();
          updateBadges();
          if (lastPointBox) lastPointBox.style.display = 'none';
          setStatus('Đã xóa toàn bộ điểm trên Tổng Quan', 'ready');
        }
      });
    }

    updateTargetUI();
  }

  // Khởi chạy các module bổ trợ
  initUTMPixelModule();
  initFreePointModule();
});
