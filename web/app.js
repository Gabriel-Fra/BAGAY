/* BAGAY demo UI. No build step and no CDN on purpose: it has to run on a laptop with
   no internet. The production client in the design docs is React + TypeScript + Vite. */

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
  const wrap = document.createElement('section');   // keep every root, not just the first
  wrap.append(t.content);
  return wrap;
};
const esc = (s) => String(s ?? '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
const peso = (n) => 'PHP ' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
const day = (s) => (s ? String(s).slice(0, 10) : '—');
const pill = (v) => `<span class="pill ${esc(v)}">${esc(String(v || '').replace(/_/g, ' ').toLowerCase())}</span>`;
const short = (h) => (h ? String(h).slice(0, 12) + '…' : '—');

const state = { view: 'dashboard', asset: null, busy: false };
const VIEWS = [
  ['dashboard', 'Dashboard'], ['assets', 'Assets'], ['queue', 'Work queue'],
  ['insights', 'Insights'], ['integrity', 'Integrity'], ['public', 'Resident view'],
];

function toast(msg, ms = 4000) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = el(`<div class="toast">${esc(msg)}</div>`);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function renderNav() {
  const nav = document.getElementById('nav');
  nav.innerHTML = '';
  VIEWS.forEach(([id, label]) => {
    const b = el(`<button aria-current="${state.view === id}">${label}</button>`);
    b.onclick = () => go(id);
    nav.appendChild(b);
  });
}

async function go(view, asset) {
  state.view = view;
  if (asset !== undefined) state.asset = asset;
  renderNav();
  const main = document.getElementById('app');
  main.innerHTML = '<p class="note">Loading…</p>';
  try { await RENDER[view](main); } catch (e) { main.innerHTML = `<div class="bad-box">${esc(e.message)}</div>`; }
}

/* ------------------------------------------------------------------ dashboard */
async function dashboard(main) {
  const o = await api('/api/overview');
  main.innerHTML = '';
  main.append(el(`<h1>Barangay Halimbawa</h1>`));
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

  // actions: real commands against the command API
  const act = el(`<div class="card">
    <div class="row spread"><b>Record something</b><span class="note">writes an event, then the
      projections catch up</span></div>
    <div class="row" style="margin-top:8px">
      <select id="ev">
        <option value="InspectionRecorded">Inspection</option>
        <option value="DamageRecorded">Damage</option>
        <option value="WorkOrderOpened">Open work order</option>
        <option value="IssueReported">Resident report</option>
      </select>
      <select id="cond">
        <option>GOOD</option><option>FAIR</option><option selected>POOR</option><option>UNSAFE</option>
      </select>
      <button class="act solid" id="send">Record</button>
      <span class="note">as ${a.status === 'UNDER_REPAIR' ? 'field worker' : 'field worker / secretary'}</span>
    </div></div>`);
  act.querySelector('#send').onclick = async () => {
    const type = act.querySelector('#ev').value;
    const cond = act.querySelector('#cond').value;
    const body = { assetId: id, actorRole: 'FIELD_WORKER', payload: {} };
    if (type === 'InspectionRecorded') body.payload = { condition: cond, findings: 'Recorded from the demo UI' };
    if (type === 'DamageRecorded') body.payload = { severity: cond === 'UNSAFE' ? 'MAJOR' : 'MINOR', service_disrupted: cond === 'UNSAFE' };
    if (type === 'WorkOrderOpened') { body.actorRole = 'SECRETARY'; body.payload = { work_order_id: crypto.randomUUID(), priority: cond === 'UNSAFE' ? 'P1' : 'P3' }; }
    if (type === 'IssueReported') { body.actorRole = 'PUBLIC'; body.payload = { issue_id: crypto.randomUUID(), issue_category: 'NOT_WORKING', description: 'Reported from the demo UI' }; }
    try {
      const r = await api(`/api/commands/${type}`, { method: 'POST', body });
      toast(`Appended #${r.globalPosition} · ${r.eventHash.slice(0, 12)}…`);
      go('assets', id);
    } catch (e) { toast(e.data && e.data.detail ? e.data.detail : e.message); }
  };
  main.append(act);

  const tl = d.timeline.map(t => `<div class="e"><b>${esc(t.summary_en)}</b>
    <small>${esc(t.summary_fil)}</small>
    <small>${day(t.occurred_at)} · ${esc(t.actor_role.replace(/_/g, ' ').toLowerCase())} ·
      ${pill(t.trust_level)} · <span class="mono">#${t.global_position} ${short(t.event_hash)}</span></small>
    </div>`).join('');
  main.append(el(`<h2>History (${d.timeline.length} events)</h2>
    <div class="card"><div class="tl">${tl}</div></div>`));

  // time travel
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

/* ------------------------------------------------------------------ queue */
async function queue(main) {
  const d = await api('/api/queue');
  main.innerHTML = '';
  main.append(el('<h1>Work queue</h1><p class="lead">Resident reports are claims until an officer triages them. Accepting one opens a work order.</p>'));

  const issues = d.issues.map(i => `<tr><td>${esc(i.name || i.asset_id)}<br><span class="mono">${esc(i.asset_id)}</span></td>
    <td>${esc(i.category.replace(/_/g, ' ').toLowerCase())}</td><td>${day(i.reported_at)}</td>
    <td><button class="act" data-accept="${esc(i.issue_id)}" data-asset="${esc(i.asset_id)}">Accept</button>
        <button class="act" data-reject="${esc(i.issue_id)}" data-asset="${esc(i.asset_id)}">Reject</button></td></tr>`).join('');
  const t1 = el(`<h2>Resident reports (${d.issues.length})</h2><div class="card tw"><table>
    <thead><tr><th>Asset</th><th>Reported issue</th><th>When</th><th>Triage</th></tr></thead>
    <tbody>${issues || '<tr><td colspan="4" class="note">Nothing waiting.</td></tr>'}</tbody></table></div>`);
  t1.querySelectorAll('button[data-accept],button[data-reject]').forEach(b => b.onclick = async () => {
    const accept = b.hasAttribute('data-accept');
    const issueId = b.dataset.accept || b.dataset.reject;
    await api('/api/commands/IssueTriaged', { method: 'POST', body: {
      assetId: b.dataset.asset, actorRole: 'SECRETARY',
      payload: { issue_id: issueId, decision: accept ? 'ACCEPTED' : 'REJECTED' } } });
    toast(accept ? 'Accepted; asset now needs attention' : 'Report rejected');
    go('queue');
  });
  main.append(t1);

  const wos = d.work_orders.map(w => `<tr><td>${esc(w.name || w.asset_id)}</td>
    <td>${pill(w.priority)}</td><td>${esc(w.status.toLowerCase())}</td>
    <td>${day(w.opened_at)}</td><td>${day(w.due_on)}</td>
    <td>${w.status === 'OPEN'
      ? `<button class="act" data-start="${esc(w.work_order_id)}" data-asset="${esc(w.asset_id)}">Start repair</button>`
      : `<button class="act solid" data-done="${esc(w.work_order_id)}" data-asset="${esc(w.asset_id)}">Complete</button>`}</td></tr>`).join('');
  const t2 = el(`<h2>Open work orders (${d.work_orders.length})</h2><div class="card tw"><table>
    <thead><tr><th>Asset</th><th>Priority</th><th>Status</th><th>Opened</th><th>Due</th><th></th></tr></thead>
    <tbody>${wos || '<tr><td colspan="6" class="note">Queue is clear.</td></tr>'}</tbody></table></div>`);
  t2.querySelectorAll('button[data-start],button[data-done]').forEach(b => b.onclick = async () => {
    const start = b.hasAttribute('data-start');
    const wo = b.dataset.start || b.dataset.done;
    const type = start ? 'RepairStarted' : 'RepairCompleted';
    const payload = start ? { work_order_id: wo }
      : { work_order_id: wo, actual_cost: 2500, resulting_condition: 'GOOD' };
    try {
      await api(`/api/commands/${type}`, { method: 'POST', body: {
        assetId: b.dataset.asset, actorRole: 'FIELD_WORKER', payload } });
      toast(start ? 'Repair started' : 'Repair completed, PHP 2,500 recorded');
      go('queue');
    } catch (e) { toast(e.data && e.data.detail ? e.data.detail : e.message); }
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

/* ------------------------------------------------------------------ public QR view */
async function publicView(main) {
  let id = state.asset;
  if (!id) { const list = await api('/api/assets?limit=1&status=NEEDS_ATTENTION'); id = (list.assets[0] || {}).asset_id; }
  const d = await api(`/public/assets/${encodeURIComponent(id)}`);
  const a = d.asset;
  main.innerHTML = '';
  main.append(el('<h1>Resident view</h1><p class="lead">What someone sees after scanning the QR tag on the asset. No login, bilingual, and it shows how each fact was recorded.</p>'));
  const card = el(`<div class="phone">
    <p class="note" style="margin:0">Barangay Halimbawa · ${esc(a.purok || '')}</p>
    <h2 style="margin:4px 0">${esc(a.name)}</h2>
    <div>${pill(a.status)} <span class="note">${esc(a.condition || '')}</span></div>
    <p class="note">${esc(a.asset_id)}</p>
    <div class="tl">${d.timeline.slice(0, 6).map(t => `<div class="e"><b>${esc(t.summary_fil)}</b>
      <small>${esc(t.summary_en)}</small><small>${day(t.occurred_at)} · ${pill(t.trust_level)}</small></div>`).join('')}</div>
    <div class="row" style="margin-top:10px">
      <select id="kind"><option value="NOT_WORKING">Hindi gumagana</option>
        <option value="DAMAGED">Sira</option><option value="CLOGGED">Barado</option>
        <option value="UNSAFE">Delikado</option></select>
      <button class="act solid" id="report">Iulat · Report</button></div>
    <p class="note" style="margin-top:10px">Record <span class="mono">${esc(short(a.stream_head_hash))}</span>
      · checkpoint #${d.latest_checkpoint ? d.latest_checkpoint.position : '—'}</p>
  </div>`);
  card.querySelector('#report').onclick = async () => {
    const r = await api(`/public/assets/${encodeURIComponent(id)}/reports`, { method: 'POST',
      body: { issueCategory: card.querySelector('#kind').value, description: 'Sent from the resident view' } });
    toast(`Salamat. Report filed as event #${r.globalPosition}; it shows as a resident claim until an officer triages it.`);
    go('public', id);
  };
  main.append(card);
  const pick = el('<div class="card" style="margin-top:14px"><span class="note">Showing a sample asset. Open any asset from the registry and use its QR link: <span class="mono">/a/{asset-id}</span></span></div>');
  main.append(pick);
}

const RENDER = { dashboard, assets, queue, insights, integrity, public: publicView };

(function boot() {
  let start = { view: 'dashboard' };
  try { const b = JSON.parse(window.__BOOT__); if (b && b.view) start = b; } catch { /* placeholder not replaced */ }
  state.asset = start.asset || null;
  go(start.view === 'public' ? 'public' : start.view);
})();
