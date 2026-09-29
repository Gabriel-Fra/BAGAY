/* BAGAY demo UI — "Sinag" theme. No build step and no CDN on purpose: it has to run on a
   laptop with no internet. The production client in the design docs is React + TS + Vite. */

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
const pill = (v) => `<span class="pill ${esc(v)}">${esc(String(v || '').replace(/_/g, ' ').toLowerCase())}</span>`;
const short = (h) => (h ? String(h).slice(0, 12) + '…' : '—');

const state = { view: 'dashboard', asset: null, busy: false, user: null };

const OFFICIAL_VIEWS = [
  ['dashboard', 'Dashboard'], ['assets', 'Assets'], ['queue', 'Work queue'],
  ['insights', 'Insights'], ['integrity', 'Integrity'],
];
const RESIDENT_VIEWS = [['report', 'Mag-ulat · Report'], ['my', 'Aking mga ulat · My reports']];

function toast(msg, ms = 4500) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = el(`<div class="toast"><span class="lamp"></span><span>${esc(msg)}</span></div>`);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

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
  who.appendChild(el(`<div class="badge"><span class="dot">${esc(initial)}</span>
    <span>${esc(state.user.displayName)}<br><span class="note" style="font-weight:700">${esc(state.user.role.replace(/_/g, ' '))}</span></span></div>`));
  const out = el('<button class="linklike">Logout</button>');
  out.onclick = async () => { await api('/api/auth/logout', { method: 'POST' }); closeStream(); state.user = null; go('login'); };
  who.appendChild(out);
}

async function go(view, asset) {
  state.view = view;
  if (asset !== undefined) state.asset = asset;
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
    <div class="fil">Mabuhay!</div>
    <h1>Welcome to Barangay Halimbawa</h1>
    <p class="note" style="margin:0 0 16px">Sign in to continue. Residents can report a broken
      or damaged asset; barangay officials get the full registry.</p>
    <div class="role-pick">
      <button data-role="PUBLIC" aria-pressed="true"><b>🏠 Resident</b><span>File and track reports</span></button>
      <button data-role="OFFICIAL" aria-pressed="false"><b>🏛 Opisyal · Official</b><span>Secretary, field worker, etc.</span></button>
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
        toast(`Kumusta, ${r.user.displayName}!`);
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
      if (d.kind === 'report') toast(`📷 ${who} (${d.purok || 'resident'}) just filed a report — live from their phone`);
      else toast(`${who} recorded ${d.eventType.replace(/([A-Z])/g, ' $1').trim().toLowerCase()}`);
      if (['dashboard', 'queue', 'my'].includes(state.view)) go(state.view);
    };
  } catch { /* SSE unsupported: the UI still works, just without live push */ }
}
function closeStream() { if (es) { es.close(); es = null; } }

/* ------------------------------------------------------------------ camera capture */
function mountCapture(hostSelector, label) {
  const box = el(`<div class="capture">
    <div class="row spread" style="margin-bottom:10px"><b>${esc(label)}</b><span class="note">optional</span></div>
    <div class="capture-frame" id="frame"><span class="placeholder">Walang larawan pa · No photo yet<br>Tap the button below to use your camera</span></div>
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
  let attachment = null; // {hash, url, contentType}
  let uploading = false;

  shutterBtn.onclick = () => fileInput.click();
  retakeBtn.onclick = () => { attachment = null; fileInput.value = ''; frame.innerHTML =
    '<span class="placeholder">Walang larawan pa · No photo yet<br>Tap the button below to use your camera</span>';
    retakeBtn.style.display = 'none'; };

  fileInput.onchange = () => {
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        // Redraw through a canvas: strips EXIF (GPS, device id) and caps the upload size —
        // no server-side image library needed.
        const maxSide = 1400;
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.82);
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
    <div class="fil">Kumusta, ${esc(state.user.displayName)}!</div>
    <h1>May sira ba sa inyo? · Something broken?</h1>
    <p>Enter the asset ID from its tag (or scan its QR code) to file a report. A photo helps
      the barangay prioritize repairs faster.</p></div>`);
  main.append(hero);

  const picker = el(`<div class="card row">
    <input id="aid" placeholder="Asset ID, e.g. BGY-...-SL-00001" value="${esc(state.asset || '')}" style="flex:1;min-width:200px">
    <button class="act solid" id="open">Buksan · Open</button>
    <button class="act" id="sample">Try a sample asset</button></div>`);
  main.append(picker);
  picker.querySelector('#open').onclick = () => {
    const v = picker.querySelector('#aid').value.trim();
    if (v) go('report', v);
  };
  picker.querySelector('#aid').onkeydown = (e) => { if (e.key === 'Enter') picker.querySelector('#open').click(); };
  picker.querySelector('#sample').onclick = async () => {
    const s = await api('/public/sample-asset');
    if (s.assetId) go('report', s.assetId); else toast('No sample asset available yet.');
  };

  if (!state.asset) {
    main.append(el('<div class="empty">Enter an asset ID above, or scan the QR tag on the asset itself.</div>'));
    return;
  }

  let d;
  try { d = await api(`/public/assets/${encodeURIComponent(state.asset)}`); }
  catch (e) {
    main.append(el(`<div class="bad-box">Could not find that asset. Check the ID and try again.</div>`));
    return;
  }
  const a = d.asset;
  const card = el(`<div class="card">
    <div class="row spread"><b>${esc(a.name)}</b>${pill(a.status)}</div>
    <p class="note" style="margin:2px 0 10px">${esc(a.asset_id)} · ${esc(a.purok || '')} · condition ${esc(a.condition || '—')}</p>
    <div class="tl">${d.timeline.slice(0, 5).map(t => `<div class="e"><b>${esc(t.summary_fil)}</b>
      <small>${esc(t.summary_en)}</small><small>${day(t.occurred_at)} · ${pill(t.trust_level)}</small></div>`).join('') || '<p class="note">No public history yet.</p>'}</div>
  </div>`);
  main.append(card);

  const cap = mountCapture(null, 'Kunan ng larawan · Take a photo');
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
    <textarea id="desc" rows="3" style="width:100%" placeholder="Optional details…"></textarea>
  </div>`);
  main.append(form);
  main.append(cap.el);

  const submitBar = el(`<div class="card row spread">
    <span class="note">Filed as a resident claim — an officer confirms it before repairs are scheduled.</span>
    <button class="act gold" id="submit">Isumite ang Ulat · Submit report</button></div>`);
  main.append(submitBar);
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
      toast(`Salamat! Report filed as event #${r.globalPosition}. Track it under "My reports".`);
      go('my');
    } catch (e) {
      toast(e.data && e.data.detail ? e.data.detail : e.message);
      btn.disabled = false; btn.textContent = 'Isumite ang Ulat · Submit report';
    }
  };
}

async function myReportsView(main) {
  const d = await api('/api/my/reports');
  main.innerHTML = '';
  main.append(el(`<div class="res-hero"><div class="fil">Aking mga ulat</div>
    <h1>My reports</h1><p>Every report you have filed, and where it stands.</p></div>`));
  if (!d.reports.length) {
    main.append(el('<div class="empty">You have not filed a report yet. Use "Mag-ulat · Report" to send one.</div>'));
    return;
  }
  const statusLabel = { NEW: 'Naghihintay ng pagsusuri · Awaiting triage', ACCEPTED: 'Tinanggap · Accepted, work ordered',
    REJECTED: 'Hindi kasama · Not accepted', DUPLICATE: 'Kaparehong ulat na naisumite · Duplicate of an earlier report' };
  const list = el('<div class="res-list"></div>');
  d.reports.forEach(r => list.append(el(`<div class="ticket ${r.status === 'NEW' ? '' : ''}">
    <div class="tt"><b>${esc(r.asset_name || r.asset_id)}</b>${pill(r.status)}</div>
    <div class="meta">${esc(r.category.replace(/_/g, ' ').toLowerCase())} · ${day(r.reported_at)}</div>
    ${r.description ? `<p class="note" style="margin:0 0 8px">${esc(r.description)}</p>` : ''}
    ${r.photo_ref ? `<img src="${esc(r.photo_ref)}" style="width:100%;border-radius:10px;margin-bottom:8px" alt="report photo">` : ''}
    <p class="note" style="margin:0">${esc(statusLabel[r.status] || r.status)}</p>
  </div>`)));
  main.append(list);
}

/* ------------------------------------------------------------------ official: dashboard */
async function dashboard(main) {
  const o = await api('/api/overview');
  main.innerHTML = '';
  main.append(el(`<h1>Barangay Halimbawa <span class="live-dot" title="Live"></span></h1>`));
  main.append(el(`<p class="lead">Every number below is derived from the event log by replaying it.
    Delete the read models and they rebuild identically. Sample data.</p>`));
  main.append(el(`<div class="kpis">
    <div class="kpi"><b>${o.assets}</b><span>assets tracked</span></div>
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
      held by ${o.witnesses} witness copies</span></div>
    <div class="row spread"><span class="note">Lifetime repair spend</span><b>${peso(o.repair_cost)}</b></div>
  </div>`));

  const log = await api('/api/log?limit=12');
  const rows = log.events.map(e => `<tr><td class="mono">#${e.global_position}</td>
    <td>${esc(e.event_type)}</td><td>${esc(e.stream_id)}</td>
    <td>${pill(e.trust_level)}</td><td>${day(e.occurred_at)}</td>
    <td class="mono">${short(e.event_hash)}</td></tr>`).join('');
  main.append(el(`<h2>Newest events</h2><div class="card tw"><table>
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
  const search = el(`<div class="card row"><input id="q" placeholder="Search name, purok, id" value="${esc(q)}" style="min-width:260px">
    <button class="act" id="find">Search</button><span class="note">${data.assets.length} shown</span></div>`);
  main.append(search);
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
  const back = el('<button class="act">← All assets</button>');
  back.onclick = () => go('assets', null);
  const bar = el('<div class="row" style="margin-bottom:10px"></div>');
  bar.append(back);
  main.append(bar);
  main.append(el(`<h1>${esc(a.name)}</h1>
    <p class="lead"><span class="mono">${esc(a.asset_id)}</span> · ${esc(a.purok || '')} ·
      acquired ${day(a.acquired_on)} for ${peso(a.acquisition_cost)}</p>`));
  main.append(el(`<div class="kpis">
    <div class="kpi"><b style="font-size:16px">${esc(a.status.replace(/_/g, ' '))}</b><span>status</span></div>
    <div class="kpi"><b style="font-size:16px">${esc(a.condition || '—')}</b><span>condition</span></div>
    <div class="kpi"><b>${a.failure_episodes}</b><span>failure episodes</span></div>
    <div class="kpi"><b style="font-size:18px">${peso(a.lifetime_repair_cost)}</b><span>repair spend</span></div>
    <div class="kpi"><b>${a.stream_version}</b><span>events on this asset</span></div>
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
      <div class="row spread"><b>Record something</b><span class="note">writes an event as ${esc(state.user.displayName)}
        (${esc(state.user.role.replace(/_/g, ' '))})</span></div>
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
      if (type === 'InspectionRecorded') body.payload = { condition: cond, findings: 'Recorded from the demo UI' };
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
    ${t.photo_ref ? `<img src="${esc(t.photo_ref)}" style="max-width:220px;border-radius:10px;margin-top:6px;display:block" alt="">` : ''}
    </div>`).join('');
  main.append(el(`<h2>History (${d.timeline.length} events)</h2>
    <div class="card"><div class="tl">${tl}</div></div>`));

  const positions = d.timeline.map(t => t.global_position);
  const mid = positions[Math.floor(positions.length / 2)] || 1;
  const tt = el(`<div class="card"><div class="row spread"><b>State as of a past point</b>
    <span class="note">rebuilt by replaying this asset's stream</span></div>
    <div class="row" style="margin-top:8px"><input id="pos" type="number" value="${mid}" style="width:120px">
      <button class="act" id="rewind">Rebuild</button><span id="out" class="note"></span></div></div>`);
  tt.querySelector('#rewind').onclick = async () => {
    const pos = tt.querySelector('#pos').value;
    const r = await api(`/api/assets/${encodeURIComponent(id)}?as_of=${pos}`);
    const s = r.as_of.state;
    tt.querySelector('#out').innerHTML = `at #${pos}: ${pill(s.status || 'unknown')} condition
      ${esc(s.condition || '—')}, repair spend ${peso(s.lifetime_repair_cost)},
      ${s.version} events so far`;
  };
  main.append(tt);
}

/* ------------------------------------------------------------------ queue (ticket board) */
async function queue(main) {
  const d = await api('/api/queue');
  main.innerHTML = '';
  main.append(el('<h1>Work queue <span class="live-dot" title="Live"></span></h1><p class="lead">Resident reports are claims until an officer triages them. Accepting one opens a work order. New tickets from phones appear here automatically.</p>'));

  const canTriage = state.user.role === 'SECRETARY';
  const canRepair = state.user.role === 'FIELD_WORKER';

  const t1 = el(`<h2>Resident reports (${d.issues.length})</h2><div class="tickets"></div>`);
  const box1 = t1.querySelector('.tickets');
  if (!d.issues.length) box1.appendChild(el('<div class="empty">Nothing waiting.</div>'));
  d.issues.forEach(i => {
    const card = el(`<div class="ticket">
      <div class="tt"><b>${esc(i.name || i.asset_id)}</b><span class="note">${day(i.reported_at)}</span></div>
      <div class="meta">${esc((i.category || '').replace(/_/g, ' ').toLowerCase())} · <span class="mono">${esc(i.asset_id)}</span></div>
      ${i.photo_ref ? `<img src="${esc(i.photo_ref)}" style="width:100%;border-radius:8px;margin-bottom:8px" alt="">` : ''}
      ${i.description ? `<p class="note" style="margin:0 0 8px">${esc(i.description)}</p>` : ''}
      <div class="stub-actions">${canTriage
        ? `<button class="act solid" data-accept="${esc(i.issue_id)}" data-asset="${esc(i.asset_id)}">Accept</button>
           <button class="act danger" data-reject="${esc(i.issue_id)}" data-asset="${esc(i.asset_id)}">Reject</button>`
        : '<span class="note">Only the secretary can triage.</span>'}</div>
    </div>`);
    card.querySelectorAll('button[data-accept],button[data-reject]').forEach(b => b.onclick = async () => {
      const accept = b.hasAttribute('data-accept');
      const issueId = b.dataset.accept || b.dataset.reject;
      await api('/api/commands/IssueTriaged', { method: 'POST', body: {
        assetId: b.dataset.asset, payload: { issue_id: issueId, decision: accept ? 'ACCEPTED' : 'REJECTED' } } });
      toast(accept ? 'Accepted; asset now needs attention' : 'Report rejected');
      go('queue');
    });
    box1.appendChild(card);
  });
  main.append(t1);

  const t2 = el(`<h2>Open work orders (${d.work_orders.length})</h2><div class="tickets"></div>`);
  const box2 = t2.querySelector('.tickets');
  if (!d.work_orders.length) box2.appendChild(el('<div class="empty">Queue is clear.</div>'));
  d.work_orders.forEach(w => {
    const card = el(`<div class="ticket ${w.priority === 'P1' ? 'p1' : ''}">
      <div class="tt"><b>${esc(w.name || w.asset_id)}</b>${pill(w.priority)}</div>
      <div class="meta">${pill(w.status)} · opened ${day(w.opened_at)} · due ${day(w.due_on)}</div>
      <div class="stub-actions">${canRepair
        ? (w.status === 'OPEN'
            ? `<button class="act solid" data-start="${esc(w.work_order_id)}" data-asset="${esc(w.asset_id)}">Start repair</button>`
            : `<button class="act gold" data-done="${esc(w.work_order_id)}" data-asset="${esc(w.asset_id)}">Complete</button>`)
        : '<span class="note">Only the field worker can update repairs.</span>'}</div>
    </div>`);
    card.querySelectorAll('button[data-start],button[data-done]').forEach(b => b.onclick = async () => {
      const start = b.hasAttribute('data-start');
      const wo = b.dataset.start || b.dataset.done;
      const type = start ? 'RepairStarted' : 'RepairCompleted';
      const payload = start ? { work_order_id: wo } : { work_order_id: wo, actual_cost: 2500, resulting_condition: 'GOOD' };
      try {
        await api(`/api/commands/${type}`, { method: 'POST', body: { assetId: b.dataset.asset, payload } });
        toast(start ? 'Repair started' : 'Repair completed, PHP 2,500 recorded');
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
  main.append(el('<h1>Insights</h1><p class="lead">Derived from the same log. The hazard view is the kind of count SDG indicator 11.5.3 asks for: damage to critical infrastructure and disruptions to basic services.</p>'));

  d.hazards.forEach(h => {
    const cats = h.by_category.map(c => `${esc(c.category)} ${c.n}`).join(' · ') || 'none';
    main.append(el(`<div class="card">
      <div class="row spread"><b>${esc(h.name)}</b><span class="note">${day(h.started_on)} to ${day(h.ended_on)}</span></div>
      <div class="kpis" style="margin:10px 0 0">
        <div class="kpi"><b>${h.damaged}</b><span>assets damaged</span></div>
        <div class="kpi warn"><b>${h.disrupted}</b><span>with service disrupted</span></div>
        <div class="kpi crit"><b>${h.unrestored}</b><span>not yet restored</span></div>
        <div class="kpi"><b style="font-size:18px">${peso(h.cost)}</b><span>estimated damage</span></div>
      </div>
      <p class="note" style="margin:8px 0 0">By category: ${cats}</p></div>`));
  });

  main.append(el(`<h2>Where the money goes</h2><div class="card tw"><table>
    <thead><tr><th>Category</th><th>Assets</th><th>Needing attention</th><th>Failure episodes</th><th>Repair spend</th></tr></thead>
    <tbody>${d.by_category.map(c => `<tr><td>${esc(c.category)}</td><td>${c.assets}</td>
      <td>${c.needs}</td><td>${c.episodes}</td><td>${peso(c.cost)}</td></tr>`).join('')}</tbody></table></div>`));

  main.append(el(`<h2>Heaviest repair burden</h2><div class="card tw"><table>
    <thead><tr><th>Asset</th><th>Purok</th><th>Episodes</th><th>Spend</th><th>Status</th></tr></thead>
    <tbody>${d.worst.map(w => `<tr><td>${esc(w.name)}</td><td>${esc(w.purok || '')}</td>
      <td>${w.failure_episodes}</td><td>${peso(w.lifetime_repair_cost)}</td><td>${pill(w.status)}</td></tr>`).join('')}
    </tbody></table></div>`));
}

/* ------------------------------------------------------------------ integrity */
async function integrity(main) {
  main.innerHTML = '';
  main.append(el('<h1>Integrity and turnover</h1><p class="lead">The log is hash-chained and checkpoints are held by witnesses outside the barangay. Tamper with the database here and watch verification catch it.</p>'));

  const box = el('<div class="card"><div class="row"><button class="act solid" id="verify">Verify the whole log</button><button class="act" id="cp">Publish checkpoint</button><button class="act" id="seal">Seal turnover</button><a class="act" href="/api/exports/turnover-pack" style="text-decoration:none;padding:5px 10px">Download turnover pack</a></div><div id="vout" style="margin-top:12px"></div></div>');
  main.append(box);
  const vout = box.querySelector('#vout');
  const showReport = (r) => {
    vout.innerHTML = r.ok
      ? `<div class="ok-box"><b>Verified.</b> ${r.events_checked} events, ${r.checkpoints_checked} witness checkpoints match. Head <span class="mono">${esc(short(r.head_hash))}</span></div>`
      : `<div class="bad-box"><b>${r.finding_count} finding(s).</b><br>${r.findings.slice(0, 6)
          .map(f => `#${f.position} ${esc(f.kind)} — ${esc(f.detail)}`).join('<br>')}</div>`;
  };
  box.querySelector('#verify').onclick = async () => { vout.textContent = 'Recomputing every hash…'; showReport(await api('/api/verify', { method: 'POST' })); };
  box.querySelector('#cp').onclick = async () => { const c = await api('/api/checkpoints', { method: 'POST' }); toast(`Checkpoint at #${c.position} sent to witnesses`); };
  box.querySelector('#seal').onclick = async () => { const s = await api('/api/turnover/seal', { method: 'POST', body: {} }); toast(`Turnover sealed at #${s.globalPosition}`); };

  const t = el(`<h2>Tamper demo</h2><div class="card">
    <p class="note">These buttons switch the database guard rails off and edit the log directly, the
      way an outgoing administration with full database access could. The endpoint exists only in
      this demo build.</p>
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
    tout.textContent = 'Tampering…';
    const r = await api(`/api/demo/tamper?mode=${b.dataset.m}`, { method: 'POST' });
    tout.innerHTML = `<div class="bad-box"><b>Attacker:</b> ${esc(r.what_the_attacker_did)}</div>
      <table style="margin-top:10px"><thead><tr><th>Verification</th><th>Result</th><th>Finding</th></tr></thead>
      <tbody>
        <tr><td>Chain only, no witness copies</td>
            <td>${r.without_witness.detected ? '<b style="color:var(--ok)">detected</b>' : '<b style="color:var(--crit)">missed</b>'}</td>
            <td class="mono">${esc(r.without_witness.kinds.join(', ') || '—')}</td></tr>
        <tr><td>Chain plus witnessed checkpoints</td>
            <td>${r.with_witness.detected ? '<b style="color:var(--ok)">detected</b>' : '<b style="color:var(--crit)">missed</b>'}</td>
            <td class="mono">${esc(r.with_witness.kinds.join(', ') || '—')}</td></tr>
      </tbody></table>
      <p class="note">Reset the demo data to put the log back.</p>`;
  });
  t.querySelector('#reset').onclick = async () => { tout.textContent = 'Reseeding…'; const r = await api('/api/demo/reset', { method: 'POST' }); tout.innerHTML = `<div class="ok-box">Fresh log with ${r.events} events.</div>`; };

  const rb = el(`<h2>Read models are disposable</h2><div class="card">
    <p class="note">Delete every projection and replay the log. If the rebuild matches, the log really is the source of truth.</p>
    <div class="row" style="margin-top:8px"><button class="act" id="rebuild">Drop and replay</button><span id="rout" class="note"></span></div></div>`);
  main.append(rb);
  rb.querySelector('#rebuild').onclick = async () => {
    rb.querySelector('#rout').textContent = 'Replaying…';
    const r = await api('/api/admin/rebuild', { method: 'POST' });
    rb.querySelector('#rout').innerHTML = `${r.events_replayed} events replayed · ${r.assets_before} assets before, ${r.assets_after} after · <b style="color:${r.identical ? 'var(--ok)' : 'var(--crit)'}">${r.identical ? 'identical' : 'MISMATCH'}</b>`;
  };

  const cps = await api('/api/checkpoints');
  main.append(el(`<h2>Checkpoints held by witnesses</h2><div class="card tw"><table>
    <thead><tr><th>Position</th><th>Head hash</th><th>Received</th><th>Channel</th></tr></thead>
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
  try { const b = JSON.parse(window.__BOOT__); if (b && b.view) start = b; } catch { /* placeholder not replaced */ }
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
