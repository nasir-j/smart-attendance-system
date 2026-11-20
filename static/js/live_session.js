// Live Session Attendance Handler
let pollInterval = null;
let clientScanInterval = null;
let clientStream = null;

function initLiveSession(sessionId, isSessionOpen) {
  const badgePresent = document.getElementById('countPresent');
  const badgeAbsent = document.getElementById('countAbsent');
  const badgeTotal = document.getElementById('countTotal');
  const badgePct = document.getElementById('countPct');
  const tableBody = document.getElementById('attendanceTableBody');
  const recentFeed = document.getElementById('recentFeed');

  let knownPresentIds = new Set();
  // Initialize known present IDs from existing table rows
  document.querySelectorAll('[data-student-id]').forEach(el => {
    const sid = parseInt(el.getAttribute('data-student-id'));
    const status = el.getAttribute('data-status');
    if (status === 'PRESENT') knownPresentIds.add(sid);
  });

  async function pollStatus() {
    try {
      const res = await fetch(`/api/sessions/${sessionId}/live_status`);
      if (!res.ok) return;
      const data = await res.json();

      if (badgePresent) badgePresent.textContent = data.present_count;
      if (badgeAbsent) badgeAbsent.textContent = data.absent_count;
      if (badgeTotal) badgeTotal.textContent = data.total_enrolled;
      if (badgePct) badgePct.textContent = data.percentage + '%';

      // Update progress bar if present
      const pBar = document.getElementById('liveProgressBar');
      if (pBar) {
        pBar.style.width = data.percentage + '%';
      }

      // Check for newly marked students
      data.records.forEach(r => {
        if (r.status === 'PRESENT' && !knownPresentIds.has(r.student_id)) {
          knownPresentIds.add(r.student_id);
          addPresentRow(r);
          addRecentNotification(r);
        }
      });

      // If session closed, stop polling
      if (data.status === 'CLOSED') {
        clearInterval(pollInterval);
        const alertBox = document.getElementById('sessionStatusAlert');
        if (alertBox) {
          alertBox.className = 'alert alert-secondary';
          alertBox.innerHTML = '<i class="bi bi-lock-fill me-2"></i> This attendance session is now <strong>CLOSED</strong>.';
        }
      }
    } catch (err) {
      console.warn('Status poll error:', err);
    }
  }

  function addPresentRow(r) {
    if (!tableBody) return;
    const tr = document.createElement('tr');
    tr.className = 'table-success animate__animated animate__fadeInDown';
    tr.setAttribute('data-student-id', r.student_id);
    tr.setAttribute('data-status', 'PRESENT');
    tr.innerHTML = `
      <td><strong>${r.roll_no}</strong></td>
      <td>${r.student_name}</td>
      <td><span class="badge-present"><i class="bi bi-check-circle-fill me-1"></i> PRESENT</span></td>
      <td><small class="text-muted">${r.marked_at || 'Just now'}</small></td>
      <td><span class="badge bg-secondary">${r.confidence ? r.confidence + '%' : 'N/A'}</span></td>
    `;
    tableBody.prepend(tr);
  }

  function addRecentNotification(r) {
    if (!recentFeed) return;
    const item = document.createElement('div');
    item.className = 'p-2 mb-2 bg-success bg-opacity-10 border border-success border-opacity-25 rounded animate__animated animate__bounceIn';
    item.innerHTML = `
      <div class="d-flex justify-content-between align-items-center">
        <div>
          <strong class="text-success"><i class="bi bi-person-check-fill me-1"></i> ${r.student_name}</strong>
          <span class="text-muted ms-2">(${r.roll_no})</span>
        </div>
        <small class="badge bg-success">${r.confidence ? r.confidence + '%' : 'Marked'}</small>
      </div>
    `;
    recentFeed.prepend(item);
    // Keep max 5 recent notifications
    while (recentFeed.children.length > 5) {
      recentFeed.removeChild(recentFeed.lastChild);
    }
  }

  if (isSessionOpen) {
    // Poll every 2 seconds
    pollInterval = setInterval(pollStatus, 2000);
  }
}

// Client-side Browser Webcam Scanner
async function startClientCameraScan(sessionId) {
  const clientVideo = document.getElementById('clientScanVideo');
  const clientCanvas = document.getElementById('clientScanCanvas');
  const btnStart = document.getElementById('btnStartClientScan');
  const btnStop = document.getElementById('btnStopClientScan');
  const statusBox = document.getElementById('clientScanStatus');

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('Webcam API is not supported in this browser.');
    return;
  }

  try {
    clientStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' }
    });
    clientVideo.srcObject = clientStream;
    clientVideo.style.display = 'block';
    btnStart.style.display = 'none';
    btnStop.style.display = 'inline-block';

    if (statusBox) {
      statusBox.textContent = 'Browser scanner active. Point camera at students...';
      statusBox.className = 'text-success small fw-bold';
    }

    // Capture & post frame every 1.5 seconds
    clientScanInterval = setInterval(async () => {
      const ctx = clientCanvas.getContext('2d');
      clientCanvas.width = clientVideo.videoWidth || 640;
      clientCanvas.height = clientVideo.videoHeight || 480;
      ctx.drawImage(clientVideo, 0, 0, clientCanvas.width, clientCanvas.height);
      const dataUrl = clientCanvas.toDataURL('image/jpeg', 0.85);

      try {
        const res = await fetch(`/api/sessions/${sessionId}/scan_frame`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_data: dataUrl })
        });
        const result = await res.json();
        if (result.success && result.newly_marked && result.newly_marked.length > 0) {
          const names = result.newly_marked.map(m => m.name).join(', ');
          if (statusBox) statusBox.textContent = `Marked: ${names}!`;
        }
      } catch (err) {
        console.warn('Scan frame post error:', err);
      }
    }, 1500);

  } catch (err) {
    alert('Unable to access client webcam: ' + err.message);
  }
}

function stopClientCameraScan() {
  const clientVideo = document.getElementById('clientScanVideo');
  const btnStart = document.getElementById('btnStartClientScan');
  const btnStop = document.getElementById('btnStopClientScan');
  const statusBox = document.getElementById('clientScanStatus');

  if (clientScanInterval) clearInterval(clientScanInterval);
  if (clientStream) {
    clientStream.getTracks().forEach(t => t.stop());
    clientStream = null;
  }
  if (clientVideo) clientVideo.style.display = 'none';
  if (btnStart) btnStart.style.display = 'inline-block';
  if (btnStop) btnStop.style.display = 'none';
  if (statusBox) statusBox.textContent = 'Scanner stopped.';
}
