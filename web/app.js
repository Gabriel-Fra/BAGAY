/* BAGAY demo UI — Professional Institutional Theme.
   No build step and no CDN dependencies on purpose: runs locally offline on any laptop or network.
*/

const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
  if (!res.ok) throw Object.assign(new Error(data.detail || res.statusText), { data, status: res.status });
  return data;
};

const el = (html) => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  if (t.content.childElementCount === 1) return t.content.firstElementChild;
  const wrap = document.createElement('section');
  wrap.append(t.content);
  return wrap;
};
const esc = (s) => String(s ?? '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
const peso = (n) => 'PHP ' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
const day = (s) => (s ? String(s).slice(0, 10) : '—');
const pill = (v) => `<span class="pill ${esc(String(v || '').toLowerCase())}">${esc(String(v || '').replace(/_/g, ' ').toLowerCase())}</span>`;
const short = (h) => (h ? String(h).slice(0, 12) + '…' : '—');

const state = { view: 'dashboard', asset: null, busy: false, user: null, q: '' };

const OFFICIAL_VIEWS = [
  ['dashboard', 'Dashboard'], ['assets', 'Assets'], ['queue', 'Work queue'],
  ['insights', 'Insights'], ['integrity', 'Integrity'],
];
const RESIDENT_VIEWS = [['report', 'Mag-ulat · Report'], ['my', 'Aking mga ulat · My reports']];

function toast(msg, ms = 4500) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = el(`<div class="toast"><span>${esc(msg)}</span></div>`);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function openLightbox(src) {
  document.querySelectorAll('.lightbox-backdrop').forEach(b => b.remove());
  const box = el(`<div class="lightbox-backdrop">
    <div class="lightbox-content">
      <button class="lightbox-close" type="button">Close ✕</button>
      <img src="${esc(src)}" alt="Enlarged photo">
    </div>
  </div>`);
  box.onclick = (e) => {
    if (e.target === box || e.target.classList.contains('lightbox-close')) {
      box.remove();
    }
  };
  document.body.appendChild(box);
}

document.addEventListener('click', (e) => {
  const target = e.target;
  if (target && target.tagName === 'IMG' && (target.classList.contains('ticket-photo') || target.closest('.ticket-img-box'))) {
    openLightbox(target.src);
  }
});

function renderChrome() {
  const nav = document.getElementById('nav');
  const who = document.getElementById('who');
  nav.innerHTML = ''; who.innerHTML = '';
  if (!state.user) return;
  const views = state.user.role === 'PUBLIC' ? RESIDENT_VIEWS : OFFICIAL_VIEWS;
  views.forEach(([id, label]) => {
    const b = el(`<button aria-current="${state.view === id}">${label}</button>`);
    b.onclick = () => go(id);
    nav.appendChild(b);
  });
  const initial = (state.user.displayName || state.user.username || '?').trim()[0].toUpperCase();
  const chip = el(`<div class="user-chip">
    <span class="user-avatar">${esc(initial)}</span>
    <div class="user-details">
      <span class="user-name">${esc(state.user.displayName)}</span>
      <span class="role-tag">${esc(state.user.role.replace(/_/g, ' '))}</span>
    </div>
    <button class="btn-logout" title="Sign out">Log out</button>
  </div>`);
  chip.querySelector('.btn-logout').onclick = async () => {
    await api('/api/auth/logout', { method: 'POST' });
    closeStream();
    state.user = null;
    go('login');
  };
  who.appendChild(chip);
}

async function go(view, asset) {
  state.view = view;
  if (asset !== undefined) state.asset = asset;
  document.body.classList.toggle('on-login', view === 'login'); 
  renderChrome();
  const main = document.getElementById('app');
  main.innerHTML = '<p class="note">Loading…</p>';
  try {
    await (RENDER[view] || dashboard)(main);
  } catch (e) {
    if (e.status === 401) { state.user = null; return go('login'); }
    main.innerHTML = `<div class="bad-box">${esc(e.data && e.data.detail ? e.data.detail : e.message)}</div>`;
  }
  
}

/* ------------------------------------------------------------------ auth */
async function loginView(main) {
  main.innerHTML = '';
  let role = 'PUBLIC';
  let mode = 'login';
  const wrap = el(`<div class="auth-wrap"><div class="auth-card">
    <div class="fil">Republika ng Pilipinas · Barangay Registry</div>
    <h1>Barangay Halimbawa</h1>
    <p class="note" style="margin:0 0 16px">Sign in to continue. Residents can report damaged infrastructure; authorized officials access the full registry and audit tools.</p>
    <div class="role-pick">
      <button data-role="PUBLIC" aria-pressed="true">
        <b>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
          Resident
        </b>
        <span>Mamamayan · File reports</span>
      </button>
      <button data-role="OFFICIAL" aria-pressed="false">
        <b>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line><line x1="15" y1="3" x2="15" y2="21"></line></svg>
          Official
        </b>
        <span>Opisyal · Secretary / Field</span>
      </button>
    </div>
    <form id="form"></form>
    <div class="auth-switch" id="switch"></div>
    <div class="demo-accounts" id="demo"></div>
  </div></div>`);
  main.append(wrap);

  const form = wrap.querySelector('#form');
  const switchEl = wrap.querySelector('#switch');
  const demoEl = wrap.querySelector('#demo');

  function renderForm() {
    wrap.querySelectorAll('.role-pick button').forEach(b =>
      b.setAttribute('aria-pressed', b.dataset.role === role || (role === 'OFFICIAL' && b.dataset.role === 'OFFICIAL') ? 'true' : 'false'));

    if (role === 'PUBLIC' && mode === 'register') {
      form.innerHTML = `
        <div class="field"><label>Buong pangalan · Full name</label><input id="displayName" placeholder="Juan Dela Cruz" required></div>
        <div class="field"><label>Purok</label>
          <select id="purok"><option>Purok 1</option><option>Purok 2</option><option>Purok 3</option>
            <option>Purok 4</option><option>Purok 5</option></select></div>
        <div class="field"><label>Username</label><input id="username" placeholder="juandelacruz" required></div>
        <div class="field"><label>Password (8+ characters)</label><input id="password" type="password" required></div>
        <button class="act gold" style="width:100%;justify-content:center" id="submit">Gumawa ng account · Create account</button>`;
      switchEl.innerHTML = '';
      const sw = el('<button class="linklike">May account na? Mag-sign in</button>');
      sw.onclick = () => { mode = 'login'; renderForm(); };
      switchEl.appendChild(sw);
    } else {
      form.innerHTML = `
        <div class="field"><label>Username</label><input id="username" placeholder="username" required></div>
        <div class="field"><label>Password</label><input id="password" type="password" required></div>
        <button class="act ${role === 'PUBLIC' ? 'gold' : 'solid'}" style="width:100%;justify-content:center" id="submit">Sign in</button>`;
      switchEl.innerHTML = '';
      if (role === 'PUBLIC') {
        const sw = el('<button class="linklike">Bagong residente? Magparehistro · New here? Register</button>');
        sw.onclick = () => { mode = 'register'; renderForm(); };
        switchEl.appendChild(sw);
      }
    }
    demoEl.innerHTML = role === 'PUBLIC'
      ? 'Demo login: <span class="mono">resident / Barangay2026!</span>'
      : ['Demo logins:', '<span class="mono">secretary / Barangay2026!</span>',
         '<span class="mono">fieldworker / Barangay2026!</span>',
         '<span class="mono">kapitana / Barangay2026!</span>'].join(' · ');

    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const btn = form.querySelector('#submit');
      btn.disabled = true; btn.textContent = 'Please wait…';
      try {
        const username = form.querySelector('#username').value.trim();
        const password = form.querySelector('#password').value;
        let r;
        if (mode === 'register') {
          r = await api('/api/auth/register', { method: 'POST', body: {
            username, password, displayName: form.querySelector('#displayName').value,
            purok: form.querySelector('#purok').value } });
        } else {
          r = await api('/api/auth/login', { method: 'POST', body: { username, password } });
        }
        state.user = r.user;
        openStream();
        toast(`Welcome, ${r.user.displayName}!`);
        go(r.user.role === 'PUBLIC' ? 'report' : 'dashboard');
      } catch (e) {
        toast(e.data && e.data.detail ? e.data.detail : e.message);
        btn.disabled = false; btn.textContent = mode === 'register' ? 'Gumawa ng account · Create account' : 'Sign in';
      }
    };
  }
  wrap.querySelectorAll('.role-pick button').forEach(b => b.onclick = () => { role = b.dataset.role; mode = 'login'; renderForm(); });
  renderForm();
}

/* ------------------------------------------------------------------ live feed */
let es = null;
function openStream() {
  closeStream();
  try {
    es = new EventSource('/api/stream');
    es.onmessage = (ev) => {
      let d; try { d = JSON.parse(ev.data); } catch { return; }
      if (!d || !d.kind) return;
      const who = d.actorName || 'Someone';
      if (d.kind === 'report') toast(`${who} (${d.purok || 'resident'}) filed a report with photo`);
      else toast(`${who} recorded ${d.eventType.replace(/([A-Z])/g, ' $1').trim().toLowerCase()}`);
      if (['dashboard', 'queue', 'my'].includes(state.view)) go(state.view);
    };
  } catch { /* SSE unsupported */ }
}
function closeStream() { if (es) { es.close(); es = null; } }

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.15);
  } catch (_) {}
}

function mountScanner(onDetected, onClose) {
  let stream = null;
  let timer = null;
  let active = true;
  let facingMode = 'environment';
  let isScanning = false;

  const box = el(`<div class="scanner-card" id="scannerWidget">
    <div class="row spread" style="margin-bottom:10px">
      <div>
        <b style="font-size:14px">QR Code Scanner · Gamitin ang Camera</b>
        <div class="note">Point camera at asset QR code tag or select an image</div>
      </div>
      <button class="act" id="closeScannerBtn" type="button" style="font-size:12px;padding:4px 10px">Close ✕</button>
    </div>
    <div class="scanner-viewport">
      <video id="scanVideo" playsinline autoplay muted></video>
      <div class="scanner-overlay">
        <div class="scanner-reticle">
          <div class="scanner-laser"></div>
        </div>
      </div>
      <div class="scanner-status" id="scanStatus">Initializing camera…</div>
    </div>
    <div class="row spread" style="margin-top:10px">
      <label class="act" style="cursor:pointer;font-size:12.5px" title="Choose or snap photo of QR tag">
        Upload / Snap photo of QR
        <input type="file" accept="image/*" id="scanFileInput" style="display:none">
      </label>
      <button class="act" id="switchCameraBtn" type="button" style="font-size:12.5px">Switch camera</button>
    </div>
  </div>`);

  const video = box.querySelector('#scanVideo');
  const status = box.querySelector('#scanStatus');
  const fileInput = box.querySelector('#scanFileInput');
  const switchBtn = box.querySelector('#switchCameraBtn');
  const closeBtn = box.querySelector('#closeScannerBtn');

  function cleanup() {
    active = false;
    if (timer) clearInterval(timer);
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
  }

  function handleSuccess(assetId) {
    if (!active) return;
    cleanup();
    playBeep();
    box.remove();
    toast(`QR code detected: ${assetId}`);
    onDetected(assetId);
  }

  closeBtn.onclick = () => {
    cleanup();
    box.remove();
    if (onClose) onClose();
  };

  fileInput.onchange = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    status.textContent = 'Scanning uploaded image…';
    const reader = new FileReader();
    reader.onload = async () => {
      const dataUrl = reader.result;
      // 1. Try on-device jsQR first
      try {
        const img = new Image();
        img.onload = async () => {
          const offscreen = document.createElement('canvas');
          const offctx = offscreen.getContext('2d', { willReadFrequently: true });
          offscreen.width = img.naturalWidth || img.width;
          offscreen.height = img.naturalHeight || img.height;
          offctx.drawImage(img, 0, 0);

          if (window.jsQR) {
            const idata = offctx.getImageData(0, 0, offscreen.width, offscreen.height);
            const qrRes = window.jsQR(idata.data, offscreen.width, offscreen.height, {
              inversionAttempts: 'attemptBoth'
            });
            if (qrRes && qrRes.data) {
              const match = qrRes.data.match(/(BGY-[A-Za-z0-9-]+)/i);
              const aid = match ? match[1].toUpperCase() : qrRes.data.trim().toUpperCase();
              if (aid) {
                handleSuccess(aid);
                return;
              }
            }
          }

          // 2. Try native BarcodeDetector on the image canvas
          if ('BarcodeDetector' in window) {
            try {
              const bd = new window.BarcodeDetector({ formats: ['qr_code'] });
              const codes = await bd.detect(offscreen);
              if (codes && codes.length > 0) {
                const val = codes[0].rawValue || '';
                const match = val.match(/(BGY-[A-Za-z0-9-]+)/i);
                const aid = match ? match[1].toUpperCase() : val.trim().toUpperCase();
                if (aid) {
                  handleSuccess(aid);
                  return;
                }
              }
            } catch (_) {}
          }

          // 3. Fallback to server-side multi-pass ArUco OpenCV detector
          try {
            const res = await api('/api/qr/decode', { method: 'POST', body: { dataUrl } });
            if (res && res.found && res.asset_id) {
              handleSuccess(res.asset_id);
              return;
            }
          } catch (_) {}

          status.textContent = 'No QR code found in photo. Please try a clearer angle.';
          toast('No QR code detected in that image. Try a clearer angle.');
        };
        img.src = dataUrl;
      } catch (err) {
        status.textContent = 'Error processing photo.';
        toast('QR decode error: ' + err.message);
      }
    };
    reader.readAsDataURL(file);
  };

  async function startCamera() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    status.textContent = 'Opening camera…';
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera API unavailable in this browser');
      }
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facingMode }, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      if (!active) {
        stream.getTracks().forEach(t => t.stop());
        return;
      }
      video.srcObject = stream;
      await video.play().catch(() => {});
      status.textContent = 'Scanning… Point camera at QR tag';
      startScanLoop();
    } catch (err) {
      status.textContent = 'Camera not available. You can upload/take a photo below.';
    }
  }

  switchBtn.onclick = () => {
    facingMode = facingMode === 'environment' ? 'user' : 'environment';
    startCamera();
  };

  function startScanLoop() {
    if (timer) clearInterval(timer);
    let barcodeDetector = null;
    if ('BarcodeDetector' in window) {
      try {
        barcodeDetector = new window.BarcodeDetector({ formats: ['qr_code'] });
      } catch (_) {}
    }

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    let frameCount = 0;

    timer = setInterval(async () => {
      if (!active || isScanning || video.readyState < 2) return;
      isScanning = true;
      frameCount++;

      try {
        const w = video.videoWidth || 640;
        const h = video.videoHeight || 480;
        if (!w || !h) return;

        canvas.width = w;
        canvas.height = h;
        ctx.drawImage(video, 0, 0, w, h);

        // Pass 1: jsQR (Instant client-side detection)
        if (window.jsQR) {
          const imgData = ctx.getImageData(0, 0, w, h);
          const code = window.jsQR(imgData.data, w, h, { inversionAttempts: 'attemptBoth' });
          if (code && code.data) {
            const match = code.data.match(/(BGY-[A-Za-z0-9-]+)/i);
            const aid = match ? match[1].toUpperCase() : code.data.trim().toUpperCase();
            if (aid) {
              handleSuccess(aid);
              return;
            }
          }
        }

        // Pass 2: Hardware-accelerated BarcodeDetector
        if (barcodeDetector) {
          const codes = await barcodeDetector.detect(canvas).catch(() => []);
          if (codes && codes.length > 0) {
            const val = codes[0].rawValue || '';
            const match = val.match(/(BGY-[A-Za-z0-9-]+)/i);
            const aid = match ? match[1].toUpperCase() : val.trim().toUpperCase();
            if (aid) {
              handleSuccess(aid);
              return;
            }
          }
        }

        // Pass 3: Periodic server fallback only if client detectors are missing or after persistent failure
        const hasClientDetector = !!(window.jsQR || barcodeDetector);
        if ((!hasClientDetector && frameCount % 6 === 0) || (frameCount % 25 === 0)) {
          const thumb = document.createElement('canvas');
          const maxDim = 480;
          const s = Math.min(1, maxDim / Math.max(w, h));
          thumb.width = Math.round(w * s);
          thumb.height = Math.round(h * s);
          thumb.getContext('2d').drawImage(canvas, 0, 0, thumb.width, thumb.height);
          const dataUrl = thumb.toDataURL('image/jpeg', 0.70);
          const res = await api('/api/qr/decode', { method: 'POST', body: { dataUrl } }).catch(() => null);
          if (res && res.found && res.asset_id) {
            handleSuccess(res.asset_id);
            return;
          }
        }
      } catch (_) {
        // continue scanning
      } finally {
        isScanning = false;
      }
    }, 100);
  }

  startCamera();
  return { el: box, cleanup };
}

/* ------------------------------------------------------------------ camera capture */
function mountCapture(hostSelector, label) {
  const box = el(`<div class="capture">
    <div class="row spread" style="margin-bottom:10px"><b>${esc(label)}</b><span class="note">optional</span></div>
    <div class="capture-frame" id="frame"><span class="placeholder">Walang larawan pa · No photo yet<br>Tap the button below to use your camera or upload</span></div>
    <div class="shutter-row">
      <input type="file" accept="image/*" capture="environment" id="file" style="display:none">
      <button class="shutter" id="shutterBtn" type="button" aria-label="Take photo"></button>
      <button class="retake" id="retakeBtn" type="button" style="display:none">Retake · Kunin ulit</button>
    </div>
  </div>`);
  const frame = box.querySelector('#frame');
  const fileInput = box.querySelector('#file');
  const shutterBtn = box.querySelector('#shutterBtn');
  const retakeBtn = box.querySelector('#retakeBtn');
  let attachment = null;
  let uploading = false;

  shutterBtn.onclick = () => fileInput.click();
  retakeBtn.onclick = () => {
    attachment = null;
    fileInput.value = '';
    frame.innerHTML = '<span class="placeholder">Walang larawan pa · No photo yet<br>Tap the button below to use your camera or upload</span>';
    retakeBtn.style.display = 'none';
  };

  fileInput.onchange = () => {
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        // Redraw through canvas: strips EXIF (GPS, device id) automatically
        const maxSide = 1400;
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.84);
        frame.innerHTML = '';
        frame.appendChild(el(`<img src="${dataUrl}" alt="captured photo">`));
        retakeBtn.style.display = '';
        uploading = true;
        api('/api/photos', { method: 'POST', body: { dataUrl } })
          .then(r => { attachment = r; uploading = false; })
          .catch(e => { uploading = false; toast('Photo upload failed: ' + e.message); });
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  };

  return { el: box, getAttachment: () => (uploading ? undefined : attachment) };
}

/* ------------------------------------------------------------------ resident: report */
async function reportView(main) {
  main.innerHTML = '';
  const hero = el(`<div class="res-hero">
    <div class="fil">Republika ng Pilipinas · Barangay Halimbawa</div>
    <h1>Mag-ulat ng Sirang Pasilidad · Report an Issue</h1>
    <p>Select an asset by scanning its physical QR tag or choosing from the registry below. A photo helps the barangay prioritize maintenance crews.</p>
  </div>`);
  main.append(hero);

  const qrSection = el(`<div class="card" id="qrContainer" style="display:none;background:var(--bg-muted);border:1px solid var(--border-strong)">
    <div class="row spread" style="margin-bottom:8px">
      <b>3 Sample QR Code Tags (Scan with phone or click to select)</b>
      <button class="act" id="closeQrs" style="font-size:12px;padding:4px 10px">Hide</button>
    </div>
    <div class="qr-strip">
      <div class="qr-card" data-aid="BGY-1380600000-SL-00001" style="cursor:pointer">
        <img src="/static/qr/qr_streetlight.png" alt="Streetlight QR">
        <b>Streetlight (SL-00001)</b>
        <span>Purok 1 · Damaged Fixture</span>
        <button class="act solid" style="margin-top:8px;font-size:12px;width:100%;justify-content:center">Select Asset</button>
      </div>
      <div class="qr-card" data-aid="BGY-1380600000-DR-00047" style="cursor:pointer">
        <img src="/static/qr/qr_drainage.png" alt="Drainage QR">
        <b>Drainage Canal (DR-00047)</b>
        <span>Purok 3 · Clogged Canal</span>
        <button class="act solid" style="margin-top:8px;font-size:12px;width:100%;justify-content:center">Select Asset</button>
      </div>
      <div class="qr-card" data-aid="BGY-1380600000-FB-00076" style="cursor:pointer">
        <img src="/static/qr/qr_footbridge.png" alt="Footbridge QR">
        <b>Footbridge (FB-00076)</b>
        <span>Purok 2 · Broken Planks</span>
        <button class="act solid" style="margin-top:8px;font-size:12px;width:100%;justify-content:center">Select Asset</button>
      </div>
    </div>
  </div>`);
  main.append(qrSection);

  const picker = el(`<div class="card row">
    <input id="aid" placeholder="Asset ID, e.g. BGY-1380600000-SL-00001" value="${esc(state.asset || '')}" style="flex:1;min-width:220px">
    <button class="act solid" id="scanBtn" title="Scan physical QR code tag with camera">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:2px"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
      Scan QR
    </button>
    <button class="act" id="open">Buksan · Open</button>
    <button class="act" id="sample">Random sample</button>
    <button class="act gold" id="toggleQrs">Sample QR Codes</button>
  </div>`);
  main.append(picker);

  const detailArea = el('<div id="reportDetailArea"></div>');
  main.append(detailArea);

  let activeScanner = null;
  let loadingAsset = false;

  async function loadAssetDetail(aid) {
    if (!aid || loadingAsset) return;
    loadingAsset = true;
    state.asset = aid;
    picker.querySelector('#aid').value = aid;

    if (activeScanner) {
      activeScanner.cleanup();
      activeScanner.el.remove();
      activeScanner = null;
    }
    qrSection.style.display = 'none';
    picker.querySelectorAll('button, input').forEach(b => b.disabled = true);

    detailArea.innerHTML = '';
    detailArea.append(el(`<div class="loading-screen" id="assetLoadingCard">
      <div class="spinner"></div>
      <h3>Na-scan ang QR Code · Loading Asset Record</h3>
      <p>Kinukuha ang rekord ng pasilidad mula sa opisyal na rehistro…<br>Fetching municipal registry status and maintenance history…</p>
      <div class="loading-asset-tag">
        <span class="live-dot" style="background:var(--ph-blue);box-shadow:none"></span>
        ${esc(aid)}
      </div>
    </div>`));

    try {
      const d = await api(`/public/assets/${encodeURIComponent(aid)}`);
      renderAssetForm(d);
    } catch (e) {
      detailArea.innerHTML = `<div class="bad-box">Could not find asset "${esc(aid)}". Please check the ID and try again.</div>`;
    } finally {
      loadingAsset = false;
      picker.querySelectorAll('button, input').forEach(b => b.disabled = false);
    }
  }

  function renderAssetForm(d) {
    detailArea.innerHTML = '';
    const a = d.asset;
    const card = el(`<div class="card">
      <div class="row spread"><b>${esc(a.name)}</b>${pill(a.status)}</div>
      <p class="note" style="margin:2px 0 10px">${esc(a.asset_id)} · ${esc(a.purok || '')} · condition ${esc(a.condition || '—')}</p>
      <div class="tl">${d.timeline.slice(0, 5).map(t => `<div class="e"><b>${esc(t.summary_fil)}</b>
        <small>${esc(t.summary_en)}</small><small>${day(t.occurred_at)} · ${pill(t.trust_level)}</small></div>`).join('') || '<p class="note">No public history yet.</p>'}</div>
    </div>`);
    detailArea.append(card);

    const cap = mountCapture(null, 'Kunan ng larawan · Take or upload photo');
    const form = el(`<div class="card">
      <div class="row spread" style="margin-bottom:8px"><b>Iulat ang problema · Describe the problem</b></div>
      <div class="row" style="margin-bottom:10px">
        <select id="kind" style="flex:1">
          <option value="NOT_WORKING">Hindi gumagana · Not working</option>
          <option value="DAMAGED">Sira · Damaged</option>
          <option value="CLOGGED">Barado · Clogged</option>
          <option value="UNSAFE">Delikado · Unsafe</option>
          <option value="MISSING">Nawawala · Missing</option>
        </select>
      </div>
      <textarea id="desc" rows="3" style="width:100%" placeholder="Optional details (e.g. location notes, hazard)..."></textarea>
    </div>`);
    detailArea.append(form);
    detailArea.append(cap.el);

    const submitBar = el(`<div class="card row spread">
      <span class="note">Filed as a resident claim — an officer confirms it before repairs are scheduled.</span>
      <button class="act gold" id="submit">Isumite ang Ulat · Submit report</button></div>`);
    detailArea.append(submitBar);

    submitBar.querySelector('#submit').onclick = async () => {
      const btn = submitBar.querySelector('#submit');
      const attachment = cap.getAttachment();
      if (attachment === undefined) { toast('Still uploading the photo — one moment.'); return; }
      btn.disabled = true; btn.textContent = 'Sending…';
      try {
        const r = await api(`/public/assets/${encodeURIComponent(state.asset)}/reports`, { method: 'POST', body: {
          issueCategory: form.querySelector('#kind').value,
          description: form.querySelector('#desc').value,
          attachments: attachment ? [attachment] : [],
        } });
        toast(`Report filed as event #${r.globalPosition}. Track it under "My reports".`);
        go('my');
      } catch (e) {
        toast(e.data && e.data.detail ? e.data.detail : e.message);
        btn.disabled = false; btn.textContent = 'Isumite ang Ulat · Submit report';
      }
    };
  }

  picker.querySelector('#scanBtn').onclick = () => {
    if (loadingAsset) return;
    if (activeScanner) {
      activeScanner.cleanup();
      activeScanner.el.remove();
      activeScanner = null;
      return;
    }
    activeScanner = mountScanner((aid) => {
      loadAssetDetail(aid);
    }, () => {
      activeScanner = null;
    });
    picker.before(activeScanner.el);
  };

  picker.querySelector('#toggleQrs').onclick = () => {
    qrSection.style.display = qrSection.style.display === 'none' ? 'block' : 'none';
  };
  qrSection.querySelector('#closeQrs').onclick = () => {
    qrSection.style.display = 'none';
  };
  qrSection.querySelectorAll('.qr-card').forEach(card => {
    card.onclick = () => loadAssetDetail(card.dataset.aid);
  });

  picker.querySelector('#open').onclick = () => {
    const v = picker.querySelector('#aid').value.trim();
    if (v) loadAssetDetail(v);
  };
  picker.querySelector('#aid').onkeydown = (e) => {
    if (e.key === 'Enter') {
      const v = picker.querySelector('#aid').value.trim();
      if (v) loadAssetDetail(v);
    }
  };
  picker.querySelector('#sample').onclick = async () => {
    if (loadingAsset) return;
    try {
      const s = await api('/public/sample-asset');
      if (s.assetId) loadAssetDetail(s.assetId); else toast('No sample asset available yet.');
    } catch (e) {
      toast('Could not fetch sample asset: ' + e.message);
    }
  };

  if (state.asset) {
    loadAssetDetail(state.asset);
  } else {
    detailArea.innerHTML = '<div class="empty">Enter an asset ID above, or click "Scan QR" / "Sample QR Codes" to inspect or report an asset.</div>';
  }
}

async function myReportsView(main) {
  const d = await api('/api/my/reports');
  main.innerHTML = '';
  main.append(el(`<div class="res-hero"><div class="fil">Aking mga ulat</div>
    <h1>My reports</h1><p>Every report you have filed and its current status in the barangay work queue.</p></div>`));
  if (!d.reports.length) {
    main.append(el('<div class="empty">You have not filed a report yet. Use "Mag-ulat · Report" to send one.</div>'));
    return;
  }
  const statusLabel = {
    NEW: 'Naghihintay ng pagsusuri · Awaiting triage',
    ACCEPTED: 'Tinanggap · Accepted, work order opened',
    REJECTED: 'Hindi kasama · Not accepted',
    DUPLICATE: 'Kaparehong ulat na naisumite · Duplicate of an earlier report'
  };
  const list = el('<div class="tickets"></div>');
  d.reports.forEach(r => list.append(el(`<div class="ticket">
    <div class="tt"><b>${esc(r.asset_name || r.asset_id)}</b>${pill(r.status)}</div>
    <div class="meta">${esc(r.category.replace(/_/g, ' ').toLowerCase())} · ${day(r.reported_at)}</div>
    ${r.photo_ref ? `<div class="ticket-img-box"><img src="${esc(r.photo_ref)}" class="ticket-photo" alt="report photo"></div>` : ''}
    ${r.description ? `<p class="note" style="margin:0 0 8px">${esc(r.description)}</p>` : ''}
    <p class="note" style="margin-top:auto;font-weight:600">${esc(statusLabel[r.status] || r.status)}</p>
  </div>`)));
  main.append(list);
}

/* ------------------------------------------------------------------ official: dashboard */
async function dashboard(main) {
  const o = await api('/api/overview');
  main.innerHTML = '';
  main.append(el(`<h1>Barangay Halimbawa <span class="live-dot" title="Live"></span></h1>`));
  main.append(el(`<p class="lead">Every number below is derived from the immutable event log. Delete the read models and they rebuild identically from day one.</p>`));
  main.append(el(`<div class="kpis">
    <div class="kpi"><b>${o.assets}</b><span>assets registered</span></div>
    <div class="kpi warn"><b>${o.needs_attention}</b><span>need attention</span></div>
    <div class="kpi"><b>${o.under_repair}</b><span>under repair</span></div>
    <div class="kpi crit"><b>${o.p1_open}</b><span>P1 safety orders open</span></div>
    <div class="kpi"><b>${o.new_reports}</b><span>resident reports to triage</span></div>
    <div class="kpi ok"><b>${o.log.events}</b><span>events in the log</span></div>
  </div>`));
  main.append(el(`<div class="card">
    <div class="row spread"><b>Log head</b><span class="mono">${esc(o.log.head_hash)}</span></div>
    <div class="row spread"><span class="note">Latest checkpoint</span>
      <span class="note">#${o.latest_checkpoint ? o.latest_checkpoint.position : '—'} ·
      ${o.latest_checkpoint ? day(o.latest_checkpoint.created_at) : ''} ·
      anchored by ${o.witnesses} external witnesses</span></div>
    <div class="row spread"><span class="note">Lifetime repair spend</span><b>${peso(o.repair_cost)}</b></div>
  </div>`));

  const log = await api('/api/log?limit=8');
  const rows = log.events.map(e => `<tr><td class="mono">#${e.global_position}</td>
    <td>${esc(e.event_type)}</td><td>${esc(e.stream_id)}</td>
    <td>${pill(e.trust_level)}</td><td>${day(e.occurred_at)}</td>
    <td class="mono">${short(e.event_hash)}</td></tr>`).join('');
  main.append(el(`<h2>Newest events in the chain</h2><div class="card tw"><table>
    <thead><tr><th>#</th><th>Event</th><th>Stream</th><th>Trust</th><th>Occurred</th><th>Hash</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`));
}

/* ------------------------------------------------------------------ assets */
async function assets(main) {
  if (state.asset) return assetDetail(main, state.asset);
  const q = state.q || '';
  const data = await api(`/api/assets?limit=200&q=${encodeURIComponent(q)}`);
  main.innerHTML = '';
  main.append(el(`<h1>Asset registry</h1>`));
  const search = el(`<div class="card row"><input id="q" placeholder="Search name, purok, ID..." value="${esc(q)}" style="min-width:260px">
    <button class="act solid" id="find">Search</button>
    <button class="act" id="scanAssetQr" title="Scan Asset QR Code Tag">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:2px"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
      Scan QR
    </button>
    <span class="note">${data.assets.length} registered assets shown</span></div>`);
  main.append(search);

  let activeAssetScanner = null;
  search.querySelector('#scanAssetQr').onclick = () => {
    if (activeAssetScanner) {
      activeAssetScanner.cleanup();
      activeAssetScanner.el.remove();
      activeAssetScanner = null;
      return;
    }
    activeAssetScanner = mountScanner((aid) => {
      activeAssetScanner = null;
      search.querySelectorAll('button, input').forEach(b => b.disabled = true);
      search.after(el(`<div class="loading-screen" style="margin-top:12px">
        <div class="spinner"></div>
        <h3>Na-scan ang QR Code · Loading Asset Record</h3>
        <p>Kinukuha ang rekord ng pasilidad mula sa rehistro…<br>Fetching asset details and maintenance history…</p>
        <div class="loading-asset-tag">
          <span class="live-dot" style="background:var(--ph-blue);box-shadow:none"></span>
          ${esc(aid)}
        </div>
      </div>`));
      go('assets', aid);
    }, () => {
      activeAssetScanner = null;
    });
    search.before(activeAssetScanner.el);
  };

  search.querySelector('#find').onclick = () => { state.q = search.querySelector('#q').value; go('assets', null); };
  search.querySelector('#q').onkeydown = (e) => { if (e.key === 'Enter') search.querySelector('#find').click(); };

  const rows = data.assets.map(a => `<tr data-id="${esc(a.asset_id)}" style="cursor:pointer">
    <td><b>${esc(a.name)}</b><br><span class="mono">${esc(a.asset_id)}</span></td>
    <td>${pill(a.status)}</td><td>${esc(a.condition || '—')}</td>
    <td>${esc(a.purok || '')}</td><td>${day(a.last_inspected_at)}</td>
    <td>${peso(a.lifetime_repair_cost)}</td><td>${a.failure_episodes}</td></tr>`).join('');
  const tbl = el(`<div class="card tw"><table>
    <thead><tr><th>Asset</th><th>Status</th><th>Condition</th><th>Purok</th><th>Last inspected</th>
    <th>Repair spend</th><th>Episodes</th></tr></thead><tbody>${rows}</tbody></table></div>`);
  tbl.querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => go('assets', tr.dataset.id));
  main.append(tbl);
}

async function assetDetail(main, id) {
  const d = await api(`/api/assets/${encodeURIComponent(id)}`);
  const a = d.asset;
  main.innerHTML = '';
  const back = el('<button class="act">← Back to all assets</button>');
  back.onclick = () => go('assets', null);
  const bar = el('<div class="row" style="margin-bottom:12px"></div>');
  bar.append(back);
  main.append(bar);

  const latestPhoto = d.timeline.find(t => t.photo_ref)?.photo_ref;

  const headerCard = el(`<div class="card">
    <div style="display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap">
      ${latestPhoto ? `<div style="width:160px;height:120px;border-radius:8px;overflow:hidden;border:1px solid var(--border);flex-shrink:0">
        <img src="${esc(latestPhoto)}" style="width:100%;height:100%;object-fit:cover" alt="Asset photo">
      </div>` : ''}
      <div style="flex:1;min-width:240px">
        <div class="row spread">
          <h1 style="margin:0">${esc(a.name)}</h1>
          ${pill(a.status)}
        </div>
        <p class="note" style="margin:4px 0 10px"><span class="mono">${esc(a.asset_id)}</span> · ${esc(a.purok || '')} · acquired ${day(a.acquired_on)} for ${peso(a.acquisition_cost)}</p>
      </div>
    </div>
  </div>`);
  main.append(headerCard);

  main.append(el(`<div class="kpis">
    <div class="kpi"><b style="font-size:16px">${esc(a.status.replace(/_/g, ' '))}</b><span>status</span></div>
    <div class="kpi"><b style="font-size:16px">${esc(a.condition || '—')}</b><span>condition</span></div>
    <div class="kpi"><b>${a.failure_episodes}</b><span>failure episodes</span></div>
    <div class="kpi"><b style="font-size:18px">${peso(a.lifetime_repair_cost)}</b><span>repair spend</span></div>
    <div class="kpi"><b>${a.stream_version}</b><span>events on this stream</span></div>
  </div>`));

  const canInspect = ['FIELD_WORKER', 'SECRETARY'].includes(state.user.role);
  const canDamage = ['FIELD_WORKER', 'SECRETARY', 'KAGAWAD'].includes(state.user.role);
  const canWorkOrder = ['SECRETARY', 'KAGAWAD', 'PUNONG_BARANGAY'].includes(state.user.role);
  const options = [];
  if (canInspect) options.push('<option value="InspectionRecorded">Inspection</option>');
  if (canDamage) options.push('<option value="DamageRecorded">Damage</option>');
  if (canWorkOrder) options.push('<option value="WorkOrderOpened">Open work order</option>');

  if (options.length) {
    const cap = mountCapture(null, 'Attach a photo (optional)');
    const act = el(`<div class="card">
      <div class="row spread"><b>Record field event</b><span class="note">signed by ${esc(state.user.displayName)} (${esc(state.user.role.replace(/_/g, ' '))})</span></div>
      <div class="row" style="margin-top:8px">
        <select id="ev">${options.join('')}</select>
        <select id="cond"><option>GOOD</option><option>FAIR</option><option selected>POOR</option><option>UNSAFE</option></select>
        <button class="act solid" id="send">Record</button>
      </div></div>`);
    act.appendChild(cap.el);
    act.querySelector('#send').onclick = async () => {
      const type = act.querySelector('#ev').value;
      const cond = act.querySelector('#cond').value;
      const attachment = cap.getAttachment();
      if (attachment === undefined) { toast('Still uploading the photo — one moment.'); return; }
      const body = { assetId: id, payload: {}, attachments: attachment ? [attachment] : [] };
      if (type === 'InspectionRecorded') body.payload = { condition: cond, findings: 'Recorded from field inspection' };
      if (type === 'DamageRecorded') body.payload = { severity: cond === 'UNSAFE' ? 'MAJOR' : 'MINOR', service_disrupted: cond === 'UNSAFE' };
      if (type === 'WorkOrderOpened') body.payload = { work_order_id: crypto.randomUUID(), priority: cond === 'UNSAFE' ? 'P1' : 'P3' };
      try {
        const r = await api(`/api/commands/${type}`, { method: 'POST', body });
        toast(`Appended #${r.globalPosition} · ${r.eventHash.slice(0, 12)}…`);
        go('assets', id);
      } catch (e) { toast(e.data && e.data.detail ? e.data.detail : e.message); }
    };
    main.append(act);
  }

  const tl = d.timeline.map(t => `<div class="e"><b>${esc(t.summary_en)}</b>
    <small>${esc(t.summary_fil)}</small>
    <small>${day(t.occurred_at)} · ${esc(t.actor_role.replace(/_/g, ' ').toLowerCase())} ·
      ${pill(t.trust_level)} · <span class="mono">#${t.global_position} ${short(t.event_hash)}</span></small>
    ${t.photo_ref ? `<div style="max-width:240px;height:140px;border-radius:6px;overflow:hidden;border:1px solid var(--border);margin-top:6px"><img src="${esc(t.photo_ref)}" style="width:100%;height:100%;object-fit:cover" alt="Event photo"></div>` : ''}
    </div>`).join('');
  main.append(el(`<h2>Audit history (${d.timeline.length} events)</h2>
    <div class="card"><div class="tl">${tl}</div></div>`));

  const positions = d.timeline.map(t => t.global_position);
  const mid = positions[Math.floor(positions.length / 2)] || 1;
  const tt = el(`<div class="card"><div class="row spread"><b>State as of a past point</b>
    <span class="note">rebuilt on demand by replaying this asset's stream</span></div>
    <div class="row" style="margin-top:8px"><input id="pos" type="number" value="${mid}" style="width:120px">
      <button class="act" id="rewind">Rebuild</button><span id="out" class="note"></span></div></div>`);
  tt.querySelector('#rewind').onclick = async () => {
    const pos = tt.querySelector('#pos').value;
    const r = await api(`/api/assets/${encodeURIComponent(id)}?as_of=${pos}`);
    const s = r.as_of.state;
    tt.querySelector('#out').innerHTML = `at #${pos}: ${pill(s.status || 'unknown')} condition ${esc(s.condition || '—')}, repair spend ${peso(s.lifetime_repair_cost)}, ${s.version} events so far`;
  };
  main.append(tt);
}

/* ------------------------------------------------------------------ queue (ticket board) */
async function queue(main) {
  const d = await api('/api/queue');
  main.innerHTML = '';
  main.append(el('<h1>Work queue <span class="live-dot" title="Live"></span></h1><p class="lead">Resident reports are claims until an officer triages them. Accepting one opens a work order. Tickets submitted from resident phones appear here automatically.</p>'));

  const canTriage = state.user.role === 'SECRETARY';
  const canRepair = state.user.role === 'FIELD_WORKER';

  // 1. Resident Reports (Inbox)
  const t1 = el(`<h2>Resident reports awaiting triage (${d.issues.length})</h2><div class="tickets"></div>`);
  const box1 = t1.querySelector('.tickets');
  if (!d.issues.length) box1.appendChild(el('<div class="empty">No resident reports awaiting triage.</div>'));
  d.issues.forEach(i => {
    const card = el(`<div class="ticket">
      <div class="tt"><b>${esc(i.name || i.asset_id)}</b><span class="note">${day(i.reported_at)}</span></div>
      <div class="meta">${esc((i.category || '').replace(/_/g, ' ').toLowerCase())} · <span class="mono">${esc(i.asset_id)}</span></div>
      ${i.photo_ref ? `<div class="ticket-img-box"><img src="${esc(i.photo_ref)}" class="ticket-photo" alt="Report photo"></div>` : ''}
      ${i.description ? `<p class="note" style="margin:0 0 10px">${esc(i.description)}</p>` : ''}
      <div class="stub-actions">${canTriage
        ? `<button class="act solid" data-accept="${esc(i.issue_id)}" data-asset="${esc(i.asset_id)}">Accept &amp; open order</button>
           <button class="act danger" data-reject="${esc(i.issue_id)}" data-asset="${esc(i.asset_id)}">Reject</button>`
        : '<span class="note">Only the secretary can triage incoming reports.</span>'}</div>
    </div>`);
    card.querySelectorAll('button[data-accept],button[data-reject]').forEach(b => b.onclick = async () => {
      const accept = b.hasAttribute('data-accept');
      const issueId = b.dataset.accept || b.dataset.reject;
      try {
        if (accept) {
          await api('/api/commands/IssueTriaged', { method: 'POST', body: {
            assetId: b.dataset.asset, payload: { issue_id: issueId, decision: 'ACCEPTED' } } });
          await api('/api/commands/WorkOrderOpened', { method: 'POST', body: {
            assetId: b.dataset.asset, payload: { work_order_id: crypto.randomUUID(), priority: 'P2', source_issue_id: issueId } } });
          toast('Report accepted; work order opened with photo for field crew');
        } else {
          await api('/api/commands/IssueTriaged', { method: 'POST', body: {
            assetId: b.dataset.asset, payload: { issue_id: issueId, decision: 'REJECTED' } } });
          toast('Report rejected');
        }
        go('queue');
      } catch (err) { toast(err.message); }
    });
    box1.appendChild(card);
  });
  main.append(t1);

  // 2. Open Work Orders (Field Crew)
  const t2 = el(`<h2>Open work orders (${d.work_orders.length})</h2><div class="tickets"></div>`);
  const box2 = t2.querySelector('.tickets');
  if (!d.work_orders.length) box2.appendChild(el('<div class="empty">No work orders currently open.</div>'));
  d.work_orders.forEach(w => {
    const card = el(`<div class="ticket ${w.priority === 'P1' ? 'p1' : ''}">
      <div class="tt"><b>${esc(w.name || w.asset_id)}</b>${pill(w.priority)}</div>
      <div class="meta">${pill(w.status)} · opened ${day(w.opened_at)} · due ${day(w.due_on)}</div>
      ${w.photo_ref ? `<div class="ticket-img-box"><img src="${esc(w.photo_ref)}" class="ticket-photo" alt="Work order photo"></div>` : ''}
      <div class="stub-actions">${canRepair
        ? (w.status === 'OPEN'
            ? `<button class="act solid" data-start="${esc(w.work_order_id)}" data-asset="${esc(w.asset_id)}">Start repair</button>`
            : `<button class="act gold" data-done="${esc(w.work_order_id)}" data-asset="${esc(w.asset_id)}">Complete repair</button>`)
        : '<span class="note">Only the field worker can start/complete repairs.</span>'}</div>
    </div>`);
    card.querySelectorAll('button[data-start],button[data-done]').forEach(b => b.onclick = async () => {
      const start = b.hasAttribute('data-start');
      const wo = b.dataset.start || b.dataset.done;
      const type = start ? 'RepairStarted' : 'RepairCompleted';
      const payload = start ? { work_order_id: wo } : { work_order_id: wo, actual_cost: 3200, resulting_condition: 'GOOD' };
      try {
        await api(`/api/commands/${type}`, { method: 'POST', body: { assetId: b.dataset.asset, payload } });
        toast(start ? 'Repair started by field worker' : 'Repair completed, PHP 3,200 recorded');
        go('queue');
      } catch (e) { toast(e.data && e.data.detail ? e.data.detail : e.message); }
    });
    box2.appendChild(card);
  });
  main.append(t2);
}

/* ------------------------------------------------------------------ insights */
async function insights(main) {
  const d = await api('/api/insights');
  main.innerHTML = '';
  main.append(el('<h1>Insights &amp; Disaster Metrics</h1><p class="lead">Derived directly from the event log. The hazard view satisfies UN SDG indicator 11.5.3: tracking damage to public critical infrastructure and disruptions to basic services.</p>'));

  d.hazards.forEach(h => {
    const cats = h.by_category.map(c => `${esc(c.category)} (${c.n})`).join(' · ') || 'none';
    main.append(el(`<div class="card">
      <div class="row spread"><b>${esc(h.name)}</b><span class="note">${day(h.started_on)} to ${day(h.ended_on)}</span></div>
      <div class="kpis" style="margin:12px 0 0">
        <div class="kpi"><b>${h.damaged}</b><span>assets damaged</span></div>
        <div class="kpi warn"><b>${h.disrupted}</b><span>service disrupted</span></div>
        <div class="kpi crit"><b>${h.unrestored}</b><span>not yet restored</span></div>
        <div class="kpi"><b style="font-size:18px">${peso(h.cost)}</b><span>estimated damage</span></div>
      </div>
      <p class="note" style="margin:8px 0 0">Affected categories: ${cats}</p></div>`));
  });
}

/* ------------------------------------------------------------------ integrity */
async function integrity(main) {
  main.innerHTML = '';
  main.append(el('<h1>Chain Verification &amp; Tamper Proofing</h1><p class="lead">The core paper claim: an incoming administration can mathematically verify the complete history it inherits without trusting the outgoing administration.</p>'));

  const box = el(`<div class="card">
    <div class="row spread"><b>Cryptographic verification</b><span class="note">recomputes every SHA-256 hash</span></div>
    <div class="row" style="margin-top:10px">
      <button class="act solid" id="run">Run verification</button>
      <button class="act" id="turnover">Download turnover pack (.zip)</button>
      <button class="act" id="seal">Seal turnover at head</button>
    </div><div id="out" style="margin-top:12px"></div></div>`);
  main.append(box);

  box.querySelector('#run').onclick = async () => {
    box.querySelector('#out').textContent = 'Recomputing hash chain…';
    const r = await api('/api/verify', { method: 'POST' });
    box.querySelector('#out').innerHTML = r.ok
      ? `<div class="ok-box">VERIFIED: ${r.events_checked} events valid, ${r.checkpoints_checked} witness checkpoints match identically.<br><span class="mono">Head: ${esc(r.head_hash)}</span></div>`
      : `<div class="bad-box">TAMPER DETECTED: ${r.finding_count} discrepancies found.<br>${r.findings.map(f => `#${f.position} ${f.kind}: ${f.detail}`).join('<br>')}</div>`;
  };
  box.querySelector('#turnover').onclick = () => { window.location = '/api/exports/turnover-pack'; };
  box.querySelector('#seal').onclick = async () => {
    const s = await api('/api/turnover/seal', { method: 'POST', body: {} });
    toast(`Turnover sealed at position #${s.globalPosition}`);
  };

  const t = el(`<h2>Tamper demonstration</h2><div class="card">
    <p class="note">These buttons simulate an insider turning database protections off and altering records directly. The endpoints exist solely for academic evaluation and demonstration.</p>
    <div class="row" style="margin-top:8px">
      <button class="act danger" data-m="edit">Edit a repair cost</button>
      <button class="act danger" data-m="delete">Delete an event</button>
      <button class="act danger" data-m="truncate">Drop the newest events</button>
      <button class="act danger" data-m="rewrite">Edit and recompute every later hash</button>
      <button class="act" id="reset">Reset demo data</button>
    </div><div id="tout" style="margin-top:12px"></div></div>`);
  main.append(t);
  const tout = t.querySelector('#tout');
  t.querySelectorAll('button[data-m]').forEach(b => b.onclick = async () => {
    tout.textContent = 'Simulating attack…';
    const r = await api(`/api/demo/tamper?mode=${b.dataset.m}`, { method: 'POST' });
    tout.innerHTML = `<div class="bad-box"><b>Attacker:</b> ${esc(r.what_the_attacker_did)}</div>
      <table style="margin-top:10px"><thead><tr><th>Verification Method</th><th>Detection Status</th><th>Finding</th></tr></thead>
      <tbody>
        <tr><td>Chain only, no external witness</td>
            <td>${r.without_witness.detected ? '<b style="color:var(--ph-green)">DETECTED</b>' : '<b style="color:var(--ph-red)">MISSED</b>'}</td>
            <td class="mono">${esc(r.without_witness.kinds.join(', ') || 'None (internal consistency looks valid)')}</td></tr>
        <tr><td>Chain plus witnessed checkpoints</td>
            <td>${r.with_witness.detected ? '<b style="color:var(--ph-green)">DETECTED</b>' : '<b style="color:var(--ph-red)">MISSED</b>'}</td>
            <td class="mono">${esc(r.with_witness.kinds.join(', ') || '—')}</td></tr>
      </tbody></table>
      <p class="note">Click "Reset demo data" to restore clean state.</p>`;
  });
  t.querySelector('#reset').onclick = async () => {
    tout.textContent = 'Reseeding…';
    const r = await api('/api/demo/reset', { method: 'POST' });
    tout.innerHTML = `<div class="ok-box">Fresh log restored with ${r.events} events.</div>`;
  };

  const rb = el(`<h2>Disposable read models</h2><div class="card">
    <p class="note">Delete all projection tables and replay the log from position 1. If the recomputed registry matches, the immutable event log is the only source of truth.</p>
    <div class="row" style="margin-top:8px"><button class="act" id="rebuild">Drop and replay</button><span id="rout" class="note"></span></div></div>`);
  main.append(rb);
  rb.querySelector('#rebuild').onclick = async () => {
    rb.querySelector('#rout').textContent = 'Replaying log…';
    const r = await api('/api/admin/rebuild', { method: 'POST' });
    rb.querySelector('#rout').innerHTML = `${r.events_replayed} events replayed · ${r.assets_before} assets before, ${r.assets_after} after · <b style="color:${r.identical ? 'var(--ph-green)' : 'var(--ph-red)'}">${r.identical ? 'IDENTICAL MATCH' : 'MISMATCH'}</b>`;
  };

  const cps = await api('/api/checkpoints');
  main.append(el(`<h2>Checkpoints anchored by external witnesses</h2><div class="card tw"><table>
    <thead><tr><th>Position</th><th>Head Hash</th><th>Timestamp</th><th>Witness Channel</th></tr></thead>
    <tbody>${cps.witness.slice(-8).reverse().map(w => `<tr><td>#${w.position}</td>
      <td class="mono">${esc(short(w.head_hash))}</td><td>${day(w.received_at)}</td>
      <td>${esc(w.channel)}</td></tr>`).join('')}</tbody></table></div>`));
}

const RENDER = {
  login: loginView, report: reportView, my: myReportsView,
  dashboard, assets, queue, insights, integrity,
};

(function boot() {
  let start = { view: 'dashboard' };
  try { const b = JSON.parse(window.__BOOT__); if (b && b.view) start = b; } catch {}
  const bootAsset = start.asset || null;

  api('/api/auth/me').then(r => {
    if (!r.user) { state.asset = bootAsset; return go('login'); }
    state.user = r.user;
    openStream();
    if (bootAsset) {
      go(r.user.role === 'PUBLIC' ? 'report' : 'assets', bootAsset);
    } else {
      go(r.user.role === 'PUBLIC' ? 'report' : 'dashboard');
    }
  }).catch(() => { state.asset = bootAsset; go('login'); });
})();
