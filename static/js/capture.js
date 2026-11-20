// Face Sample Capture Handler
let videoStream = null;
const videoEl = document.getElementById('webcamVideo');
const canvasEl = document.getElementById('webcamCanvas');
const captureBtn = document.getElementById('btnCapture');
const startCamBtn = document.getElementById('btnStartCam');
const autoCaptureBtn = document.getElementById('btnAutoCapture');
const sampleGrid = document.getElementById('sampleGrid');
const sampleCountBadge = document.getElementById('sampleCount');
const statusMsg = document.getElementById('statusMessage');

let isAutoCapturing = false;

// Start Browser Webcam
async function startWebcam() {
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
    });
    videoEl.srcObject = videoStream;
    videoEl.style.display = 'block';
    if (startCamBtn) startCamBtn.style.display = 'none';
    if (captureBtn) captureBtn.disabled = false;
    if (autoCaptureBtn) autoCaptureBtn.disabled = false;
    showStatus('Webcam active. Stand clearly in front of the camera.', 'info');
  } catch (err) {
    console.error('Camera access error:', err);
    showStatus('Unable to access browser camera: ' + err.message + '. You can still upload photo files below.', 'warning');
  }
}

// Capture frame and send to backend
async function captureAndSendSample(studentId) {
  if (!videoStream) {
    showStatus('Please start the webcam first.', 'warning');
    return false;
  }

  const ctx = canvasEl.getContext('2d');
  canvasEl.width = videoEl.videoWidth || 640;
  canvasEl.height = videoEl.videoHeight || 480;
  ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);

  const dataUrl = canvasEl.toDataURL('image/jpeg', 0.9);
  showStatus('Detecting face and saving sample...', 'info');

  try {
    const res = await fetch(`/api/students/${studentId}/save_sample`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_data: dataUrl })
    });
    const result = await res.json();

    if (result.success) {
      showStatus(result.message, 'success');
      if (sampleCountBadge) sampleCountBadge.textContent = result.total_samples;
      
      // Prepend newly captured thumbnail
      if (sampleGrid && result.sample_url) {
        const thumb = document.createElement('img');
        thumb.src = result.sample_url + '?t=' + Date.now();
        thumb.className = 'sample-thumb animate__animated animate__zoomIn';
        thumb.title = `Sample #${result.total_samples}`;
        sampleGrid.prepend(thumb);
      }
      return true;
    } else {
      showStatus(result.error || 'Failed to capture sample.', 'danger');
      return false;
    }
  } catch (e) {
    showStatus('Network error while saving sample: ' + e.message, 'danger');
    return false;
  }
}

// Auto-capture 5 samples sequentially
async function autoCaptureSequence(studentId, count = 5) {
  if (isAutoCapturing) return;
  isAutoCapturing = true;
  autoCaptureBtn.disabled = true;
  captureBtn.disabled = true;

  let captured = 0;
  for (let i = 1; i <= count; i++) {
    showStatus(`Auto-capturing sample ${i} of ${count}... Slightly move or tilt head.`, 'info');
    const ok = await captureAndSendSample(studentId);
    if (ok) captured++;
    await new Promise(r => setTimeout(r, 1200));
  }

  showStatus(`Auto-capture completed! Successfully captured ${captured} samples. Remember to Train Model.`, 'success');
  isAutoCapturing = false;
  autoCaptureBtn.disabled = false;
  captureBtn.disabled = false;
}

function showStatus(msg, type) {
  if (!statusMsg) return;
  statusMsg.className = `alert alert-${type} py-2 mb-3`;
  statusMsg.textContent = msg;
  statusMsg.style.display = 'block';
}

if (startCamBtn) {
  startCamBtn.addEventListener('click', startWebcam);
}
