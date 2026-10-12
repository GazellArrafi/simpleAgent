/* simpleAgent web UI — vanilla JS. Rancangan: markdown/webui.md */
"use strict";

// ================================================================ utils
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const rp = (n) => (n == null || n === "" ? "—" : (n < 0 ? "-Rp" : "Rp") + Math.abs(Math.round(Number(n))).toLocaleString("id-ID"));
const num = (n) => (n == null ? "—" : Number(n).toLocaleString("id-ID"));
const pct = (x) => `${Math.round(x * 100)}%`;
const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const HARI = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];
function tgl(iso, withDay = false) {
  if (!iso) return "—";
  const d = new Date(String(iso).slice(0, 10) + "T00:00:00");
  if (isNaN(d)) return esc(iso);
  return `${withDay ? HARI[d.getDay()] + ", " : ""}${d.getDate()} ${BULAN[d.getMonth()]} ${d.getFullYear()}`;
}
const dt = (iso) => (iso ? String(iso).slice(0, 16).replace("T", " ") : "—");

const SEV = {
  critical: { cls: "crit", label: "KRITIS", color: "var(--crit)" },
  warning: { cls: "warn", label: "PERHATIAN", color: "var(--warn)" },
  info: { cls: "info", label: "INFO", color: "var(--info)" },
};
const sevBadge = (s) => `<span class="badge ${SEV[s]?.cls || ""}">${SEV[s]?.label || esc(s)}</span>`;

const PERSONA = {
  due_soon: "Jatuh tempo dekat", overdue: "Telat bayar", revolver_near_limit: "Limit hampir habis",
  minimum_payer: "Bayar minimum", spending_spike: "Belanja melonjak", traveler: "Traveler",
  healthy: "Sehat", no_cc: "Tanpa CC", dormant: "Dormant",
};
const personaLabel = (p) => PERSONA[p] || String(p || "").replace(/_/g, " ");

const PRESETS = [
  ["Menyeluruh", null],
  ["Tagihan CC", "Fokus pengingat tagihan kartu kredit saja."],
  ["Cicilan", "Fokus pengingat cicilan pinjaman yang akan jatuh tempo."],
  ["Limit & belanja", "Fokus kesehatan limit kartu kredit dan pola belanja yang tidak biasa."],
  ["Penawaran", "Hanya beri penawaran produk yang relevan bila kondisi nasabah sehat."],
];

const ICON = {
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z" fill="currentColor" stroke="none"/></svg>',
  wallet: '<svg viewBox="0 0 24 24"><path d="M3 7h18v12H3z"/><path d="M3 7l13-3v3M17 13h1"/></svg>',
  card: '<svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/></svg>',
  bill: '<svg viewBox="0 0 24 24"><path d="M6 2h12v20l-3-2-3 2-3-2-3 2z"/><path d="M9 7h6M9 11h6M9 15h3"/></svg>',
  loan: '<svg viewBox="0 0 24 24"><path d="M3 21h18M5 21V10l7-6 7 6v11"/><path d="M10 21v-6h4v6"/></svg>',
  bulb: '<svg viewBox="0 0 24 24"><path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/></svg>',
  warn: '<svg viewBox="0 0 24 24"><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/></svg>',
  info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
  flow: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M6 9v3a3 3 0 0 0 3 3h6"/></svg>',
  inbox: '<svg viewBox="0 0 24 24"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v7H2v-7z"/></svg>',
  chat: '<svg viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-6.4A8 8 0 1 1 21 12z"/></svg>',
  send: '<svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>',
  menu: '<svg viewBox="0 0 24 24"><path d="M3 6h18M3 12h18M3 18h18"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>',
  user: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/></svg>',
  db: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>',
};

function avatar(name, cls = "") {
  const initials = String(name || "?").split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `<div class="avatar ${cls}" style="background:hsl(${h} 55% 52%)">${esc(initials)}</div>`;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage tidak tersedia */ } },
};

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  let res;
  try {
    res = await fetch(path, opt);
  } catch {
    throw new Error("Server tidak bisa dihubungi. Pastikan `python web\\server.py` masih jalan.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function pollJob(jobId, onTick, interval = 400) {
  for (;;) {
    const job = await api(`/api/jobs/${jobId}`);
    onTick?.(job);
    if (job.status !== "running") return job;
    await sleep(interval);
  }
}

function toast(msg, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = (kind === "ok" ? ICON.check : "") + `<span>${esc(msg)}</span>`;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "error" ? 6000 : 3200);
}

function confirmDialog(title, body, okLabel = "Ya, lanjut") {
  const dlg = $("#confirm");
  $("#confirm-title").textContent = title;
  $("#confirm-body").textContent = body;
  $("#confirm-ok").textContent = okLabel;
  dlg.returnValue = "";
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true }));
}

function emptyState(icon, title, text = "", action = "") {
  return `<div class="empty">${ICON[icon] || ""}<strong>${esc(title)}</strong>${text ? `<span>${text}</span>` : ""}${action}</div>`;
}

// tabel generik: cols = [[key, label, fmt?]] ; fmt: "rp" | "num" | "date" | "dt" | "bool" | "pct" | function
const FMT = {
  rp: (v) => rp(v), num: (v) => num(v), date: (v) => tgl(v), dt: (v) => dt(v), pct: (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`),
  bool: (v) => (v ? '<span class="badge ok">ya</span>' : '<span class="badge">tidak</span>'),
  status: (v) => {
    const map = { paid: "ok", current: "ok", active: "ok", approved: "ok", sent: "ok", open: "info", scheduled: "info", overdue: "crit", declined: "crit", late: "warn" };
    return v == null ? "—" : `<span class="badge ${map[v] || ""}">${esc(v)}</span>`;
  },
  sev: (v) => sevBadge(v),
};
function table(rows, cols, { onRow, rowKey } = {}) {
  if (!rows?.length) return emptyState("db", "Tidak ada data");
  const numeric = (f) => f === "rp" || f === "num" || f === "pct";
  const head = cols.map(([, label, f]) => `<th class="${numeric(f) ? "num" : ""}">${esc(label)}</th>`).join("");
  const body = rows.map((r, i) => {
    const tds = cols.map(([k, , f]) => {
      const v = r[k];
      const out = typeof f === "function" ? f(v, r) : f ? FMT[f](v) : v == null || v === "" ? '<span class="muted">—</span>' : esc(Array.isArray(v) ? v.join(", ") : v);
      return `<td class="${numeric(f) ? "num" : ""}" title="${esc(typeof v === "object" ? "" : v)}">${out}</td>`;
    }).join("");
    return `<tr${onRow ? ` class="clickable" data-row="${esc(rowKey ? r[rowKey] : i)}"` : ""}>${tds}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table class="tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function kv(obj, fmts = {}) {
  return `<div class="kv">${Object.entries(obj).map(([k, v]) => {
    const f = fmts[k];
    const val = f ? (typeof f === "function" ? f(v) : FMT[f](v)) : v == null || v === "" ? "—" : typeof v === "boolean" ? FMT.bool(v) : esc(v);
    return `<div><span>${esc(k.replace(/_/g, " "))}</span><span>${val}</span></div>`;
  }).join("")}</div>`;
}

// ================================================================ state
const S = {
  status: null,
  customers: [],
  cid: store.get("cid", null),
  detail: null,        // data nasabah aktif
  inbox: [],
  results: {},         // cid -> hasil agent terakhir
  runs: {},            // cid -> {jobId, steps, plan} saat agent sedang jalan
  tab: store.get("tab", "flow"),
  dataTab: "profil",
  ccDays: 30,
  search: "",
  persona: null,
  objective: null,
  chat: [],
  chatBusy: false,
  seen: {},            // cid -> {analisa, inbox} sudah dilihat setelah run
  outboxFilter: { q: "", sev: "all" },
  apTimer: null,
};

// ================================================================ shell
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
}
applyTheme(store.get("theme", null));
$("#theme-toggle").addEventListener("click", () => {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  applyTheme(next);
  store.set("theme", next);
});

function renderNavStatus() {
  const s = S.status;
  if (!s) return;
  $("#nav-status").innerHTML = `
    <div class="row"><span>LLM</span><span title="${esc(s.llm)}"><i class="dot ${s.online ? "on" : "off"}"></i>${s.online ? "online" : "offline"}</span></div>
    <div class="row"><span>Data</span><span>${esc(s.backend)}</span></div>
    <div class="row"><span>Tanggal sim.</span><span>${s.sim_date ? tgl(s.sim_date) : "—"}</span></div>
    ${s.online ? `<div class="muted small mono" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(s.llm)}">${esc(s.llm)}</div>` : ""}`;
}

async function loadStatus() {
  S.status = await api("/api/status");
  renderNavStatus();
  if (S.status.ready) {
    S.customers = await api("/api/customers");
    if (!S.customers.some((c) => c.customer_id === S.cid)) S.cid = S.customers[0]?.customer_id || null;
  }
}

function route() {
  const [, page = "nasabah", arg] = location.hash.split("/");
  clearInterval(S.apTimer);
  S.apTimer = null;
  $$(".nav-links a").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  if (page === "nasabah" && arg && arg !== S.cid) {
    S.cid = arg.toUpperCase();
    store.set("cid", S.cid);
    S.detail = null;
  }
  if (page === "nasabah" && S.status.ready && $("#cust-main")) {  // ganti nasabah tanpa membangun ulang daftar
    renderCustomerList();
    renderCustomer();
    window.scrollTo(0, 0);
    return;
  }
  const pages = { nasabah: pageNasabah, outbox: pageOutbox, autopilot: pageAutopilot, pengaturan: pagePengaturan };
  (pages[page] || pageNasabah)();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

// ================================================================ halaman: nasabah
function pageNasabah() {
  const main = $("#main");
  if (!S.status.ready) {
    main.innerHTML = `<div class="page"><div class="card">${emptyState("db", "Data dummy belum ada",
      S.status.backend === "postgres"
        ? "Database belum siap. Pastikan PostgreSQL jalan, lalu <span class='mono'>python main.py db-setup</span> dan <span class='mono'>db-load</span>, atau generate data baru."
        : "Generate data dummy dulu supaya ada nasabah yang bisa dianalisa.",
      `<a class="btn btn-primary" href="#/pengaturan" style="margin-top:8px">Buka Pengaturan</a>`)}</div></div>`;
    return;
  }
  main.innerHTML = `
    <div class="cust-layout">
      <aside class="cust-list" id="cust-list">
        <div class="cust-list-head">
          <h2>Nasabah <span class="muted small" id="cust-count"></span></h2>
          <div class="search">${ICON.search}<input class="input" id="cust-search" placeholder="Cari ID, nama, kota, segmen…" value="${esc(S.search)}" autocomplete="off"></div>
          <div class="chips" id="persona-chips"></div>
        </div>
        <div class="cust-items" id="cust-items"></div>
      </aside>
      <section class="cust-main" id="cust-main"></section>
    </div>`;
  renderPersonaChips();
  renderCustomerList();
  $("#cust-search").addEventListener("input", (e) => { S.search = e.target.value; renderCustomerList(); });
  renderCustomer();
}

function renderPersonaChips() {
  const personas = [...new Set(S.customers.map((c) => c.demo_persona))];
  $("#persona-chips").innerHTML = personas.map((p) =>
    `<button class="chip ${S.persona === p ? "active" : ""}" data-p="${esc(p)}" title="Persona demo dari generator (tidak dipakai agent)">${esc(personaLabel(p))}</button>`).join("");
  $$("#persona-chips .chip").forEach((b) => b.addEventListener("click", () => {
    S.persona = S.persona === b.dataset.p ? null : b.dataset.p;
    renderPersonaChips();
    renderCustomerList();
  }));
}

function renderCustomerList() {
  const q = S.search.trim().toLowerCase();
  const list = S.customers.filter((c) => (!S.persona || c.demo_persona === S.persona) &&
    (!q || [c.customer_id, c.full_name, c.city, c.segment, c.occupation, personaLabel(c.demo_persona)].some((v) => String(v).toLowerCase().includes(q))));
  $("#cust-count").textContent = `${list.length} / ${S.customers.length}`;
  $("#cust-items").innerHTML = list.length ? list.slice(0, 400).map((c) => `
    <button class="cust-item ${c.customer_id === S.cid ? "active" : ""}" data-cid="${esc(c.customer_id)}">
      ${avatar(c.full_name)}
      <div class="grow">
        <div class="name">${esc(c.full_name)}</div>
        <div class="meta">${esc(c.customer_id)} · ${esc(c.segment)} · ${esc(personaLabel(c.demo_persona))}</div>
      </div>
      ${S.runs[c.customer_id] ? '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>' : ""}
    </button>`).join("") : emptyState("search", "Tidak ditemukan", "Coba kata kunci lain.");
  $$("#cust-items .cust-item").forEach((b) => b.addEventListener("click", () => {
    $("#cust-list").classList.remove("open");
    location.hash = `#/nasabah/${b.dataset.cid}`;
  }));
}

async function renderCustomer() {
  const el = $("#cust-main");
  if (!el) return;
  const cid = S.cid;
  if (!S.detail || S.detail.profile.customer_id !== cid) {
    el.innerHTML = `<div class="skeleton" style="height:70px"></div><div class="kpis">${'<div class="skeleton" style="height:96px"></div>'.repeat(4)}</div><div class="skeleton" style="height:120px"></div>`;
    try {
      const [detail, inbox] = await Promise.all([api(`/api/customers/${cid}`), api(`/api/customers/${cid}/inbox`)]);
      if (cid !== S.cid) return;
      S.detail = detail;
      S.inbox = inbox;
    } catch (e) {
      el.innerHTML = `<div class="card">${emptyState("warn", "Gagal memuat nasabah", esc(e.message))}</div>`;
      return;
    }
  }
  const { profile: p, credit_cards: cards, statements, savings, loans } = S.detail;
  const card = cards[0];
  const st = statements.at(-1);
  const used = card ? card.current_balance / card.credit_limit : 0;
  const run = S.runs[cid];
  const res = S.results[cid];
  const objective = S.objective ?? S.status.default_objective;
  if (S.tab === "analisa" || S.tab === "inbox") (S.seen[cid] ??= {})[S.tab] = true;

  el.innerHTML = `
    <div class="mobile-bar"><button class="btn" id="open-list">${ICON.menu} Pilih nasabah</button></div>
    <div class="cust-header">
      ${avatar(p.full_name, "lg")}
      <div class="info">
        <h1>${esc(p.full_name)}</h1>
        <div class="muted">${esc(p.customer_id)} · ${esc(p.occupation)} · ${esc(p.city)} · ${esc(p.age)} th · penghasilan ${rp(p.monthly_income)}/bln</div>
        <div class="tags">
          <span class="badge accent">${esc(p.segment)}</span>
          <span class="badge outline">kanal: ${esc(p.preferred_channel)}</span>
          <span class="badge ${p.marketing_consent ? "ok" : ""}">consent marketing: ${p.marketing_consent ? "ya" : "tidak"}</span>
          <span class="badge outline" title="Persona demo dari generator — tidak dipakai agent">persona: ${esc(personaLabel(p.demo_persona))}</span>
        </div>
      </div>
    </div>

    <div class="kpis">
      <div class="card kpi"><span class="label">${ICON.wallet}Saldo tabungan</span><span class="value">${rp(savings.reduce((a, s) => a + Number(s.balance), 0))}</span>
        <span class="sub">${savings.length} rekening${savings.some((s) => s.is_payroll) ? " · payroll" : ""}</span></div>
      <div class="card kpi"><span class="label">${ICON.card}Limit CC terpakai</span>
        ${card ? `<span class="value">${rp(card.current_balance)}</span>
          <div class="meter ${used >= 0.9 ? "crit" : used >= 0.7 ? "warn" : ""}"><div style="width:${Math.min(used, 1) * 100}%"></div></div>
          <span class="sub">${pct(used)} dari ${rp(card.credit_limit)}</span>` : `<span class="value muted">—</span><span class="sub">Tidak punya kartu kredit</span>`}</div>
      <div class="card kpi"><span class="label">${ICON.bill}Tagihan CC terakhir</span>
        ${st ? `<span class="value">${rp(st.total_due)}</span><span class="sub">jatuh tempo ${tgl(st.due_date)} · ${FMT.status(st.days_past_due > 0 ? "overdue" : st.status)}</span>`
          : `<span class="value muted">—</span><span class="sub">Belum ada tagihan</span>`}</div>
      <div class="card kpi"><span class="label">${ICON.loan}Pinjaman</span>
        ${loans.length ? `<span class="value">${esc(loans.map((l) => l.type).join(", "))}</span><span class="sub">cicilan ${rp(loans[0].monthly_installment)} · ${tgl(loans[0].next_due_date)}</span>`
          : `<span class="value muted">—</span><span class="sub">Tidak ada pinjaman</span>`}</div>
    </div>

    <div class="card runbox">
      <label class="field">Objective untuk Supervisor <small>— arahkan fokus agent, atau biarkan default</small>
        <textarea class="input" id="objective" rows="2">${esc(objective)}</textarea>
      </label>
      <button class="btn btn-primary btn-lg" id="run-btn" ${run ? "disabled" : ""}>
        ${run ? '<span class="spinner"></span> Agent bekerja…' : `${ICON.play} Jalankan agent`}</button>
      <div class="presets"><span class="muted small">Preset:</span>
        ${PRESETS.map(([label, text], i) => `<button class="chip ${(text ?? S.status.default_objective) === objective ? "active" : ""}" data-preset="${i}">${esc(label)}</button>`).join("")}
      </div>
    </div>

    <div>
      <div class="tabs" id="tabs">
        ${tabBtn("flow", ICON.flow, "Alur Agent")}
        ${tabBtn("analisa", ICON.bulb, "Hasil Analisa", res && !S.seen[cid]?.analisa ? res.insights?.length : 0)}
        ${tabBtn("inbox", ICON.inbox, "Inbox Nasabah", res && !S.seen[cid]?.inbox ? res.deliveries?.filter((d) => d.status !== "duplicate_skipped").length : 0)}
        ${tabBtn("data", ICON.db, "Data")}
        ${tabBtn("chat", ICON.chat, "Tanya Data")}
      </div>
      <div id="tab-body" style="padding-top:16px"></div>
    </div>`;

  $("#open-list").addEventListener("click", (e) => { e.stopPropagation(); $("#cust-list").classList.add("open"); });
  el.onclick = () => $("#cust-list")?.classList.remove("open");
  $("#objective").addEventListener("input", (e) => { S.objective = e.target.value; });
  $$("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    S.objective = PRESETS[b.dataset.preset][1] ?? S.status.default_objective;
    $("#objective").value = S.objective;
    $$("[data-preset]").forEach((x) => x.classList.toggle("active", x === b));
  }));
  $("#run-btn").addEventListener("click", () => runAgent(cid));
  $$("#tabs .tab").forEach((b) => b.addEventListener("click", () => { S.tab = b.dataset.tab; store.set("tab", S.tab); renderCustomer(); }));
  renderTab();
}

function tabBtn(id, icon, label, count = 0) {
  return `<button class="tab ${S.tab === id ? "active" : ""}" data-tab="${id}">${icon}${label}${count ? `<span class="count">${count}</span>` : ""}</button>`;
}

function renderTab() {
  const body = $("#tab-body");
  ({ flow: tabFlow, analisa: tabAnalisa, inbox: tabInbox, data: tabData, chat: tabChat }[S.tab] || tabFlow)(body);
}

async function runAgent(cid) {
  if (S.runs[cid]) return;
  const objective = ($("#objective")?.value || "").trim();
  try {
    const { job_id } = await api("/api/run", { customer_id: cid, objective });
    S.runs[cid] = { jobId: job_id, steps: [], plan: null };
    S.tab = "flow";
    if (S.cid === cid) renderCustomer();
    renderCustomerList();
    const job = await pollJob(job_id, (j) => {
      const run = S.runs[cid];
      const changed = j.steps.length !== run.steps.length || (j.plan && !run.plan);
      run.steps = j.steps;
      run.plan = j.plan;
      if (changed && S.cid === cid && S.tab === "flow" && $("#pipeline")) $("#pipeline").innerHTML = pipelineHtml(cid);
    });
    delete S.runs[cid];
    if (job.status === "error") throw new Error(job.error);
    S.results[cid] = job.result;
    S.seen[cid] = {};
    const n = job.result.deliveries?.filter((d) => d.status !== "duplicate_skipped").length || 0;
    toast(`${job.result.customer_id}: ${job.result.insights?.length || 0} insight, ${n} pesan terkirim`);
    if (S.cid === cid) S.inbox = await api(`/api/customers/${cid}/inbox`);
  } catch (e) {
    delete S.runs[cid];
    toast(e.message, "error");
  }
  if (S.cid === cid && $("#cust-main")) renderCustomer();
  if ($("#cust-items")) renderCustomerList();
}

// ---------------------------------------------------------------- tab: alur
function pipelineHtml(cid) {
  const nodes = S.status.nodes;
  const core = nodes.filter((n) => n.group === "core");
  const analysts = nodes.filter((n) => n.group === "analyst");
  const run = S.runs[cid];
  const res = S.results[cid];
  const steps = new Set(run ? run.steps : []);
  const plan = run ? run.plan : res?.plan;
  const order = ["supervisor_plan", "data_agent", "analysts", "supervisor_review", "communicator", "delivery"];

  function state(id, isAnalyst) {
    if (run) {
      if (steps.has(id)) return "done";
      if (isAnalyst && plan && !plan.includes(id)) return "skipped";
      const cur = order.find((o) => (o === "analysts" ? plan && plan.some((a) => !steps.has(a)) : !steps.has(o)));
      if (isAnalyst) return cur === "analysts" ? "active" : "idle";
      return cur === id ? "active" : "idle";
    }
    if (res) return isAnalyst && !(plan || []).includes(id) ? "skipped" : "done";
    return "idle";
  }
  const node = (n) => {
    const isAnalyst = n.group === "analyst";
    const [main, sub] = isAnalyst ? [n.label.replace(/^Analis\s+/i, ""), null] : n.label.split(" · ");
    return `<div class="node ${isAnalyst ? "analyst" : ""} ${state(n.id, isAnalyst)}" title="${esc(n.label)}">${esc(main)}${sub ? `<span class="n-sub">${esc(sub)}</span>` : ""}</div>`;
  };
  const byId = Object.fromEntries(core.map((n) => [n.id, n]));
  const arrow = '<div class="pipe-arrow"></div>';
  return `<div class="flow">
      <div class="node trigger">Trigger</div>${arrow}
      ${node(byId.supervisor_plan)}${arrow}${node(byId.data_agent)}${arrow}
      <div class="pipe-fan"><div class="bracket l"></div><div class="pipe-col">${analysts.map(node).join("")}</div><div class="bracket r"></div></div>${arrow}
      ${node(byId.supervisor_review)}${arrow}${node(byId.communicator)}${arrow}${node(byId.delivery)}
    </div>`;
}

function tabFlow(body) {
  const cid = S.cid;
  const res = S.results[cid];
  const run = S.runs[cid];
  let html = `<div class="card pipeline" id="pipeline">${pipelineHtml(cid)}</div>`;
  if (run) {
    html += `<div class="callout info" style="margin-top:14px">${ICON.info}<span>Agent sedang bekerja — node menyala sesuai langkah yang sudah selesai.${S.status.online ? " Mode LLM bisa makan waktu beberapa puluh detik." : ""}</span></div>`;
  } else if (!res) {
    html += `<div class="card" style="margin-top:14px">${emptyState("play", "Belum ada hasil untuk nasabah ini", "Klik <b>Jalankan agent</b> di atas. Supervisor akan memilih analis yang relevan, lalu pesan dikirim ke inbox nasabah.")}</div>`;
  } else {
    html += `<div class="card" style="margin-top:14px">
      <div class="card-head"><div><h3>Jejak kerja agent</h3><div class="muted small">Objective: ${esc(res.objective)}</div></div>
        <span class="badge">${res.trace.length} langkah</span></div>
      <div class="card-pad"><div class="timeline">${res.trace.map((t) => `
        <div class="tl-item"><div class="tl-dot ${t.llm ? "llm" : ""}"></div><div>
          <div class="tl-title"><strong>${esc(t.agent)}</strong>${t.llm ? '<span class="badge accent">LLM</span>' : ""}
            <span class="muted small">${esc(t.ts || "")}${t.duration_ms != null ? ` · ${num(t.duration_ms)} ms` : ""}</span></div>
          <div class="tl-action">${esc(t.action)}</div>
          ${t.detail ? `<details class="fold" style="margin-top:4px"><summary>Detail</summary><pre class="code">${esc(t.detail)}</pre></details>` : ""}
        </div></div>`).join("")}</div></div></div>`;
  }
  body.innerHTML = html;
}

// ---------------------------------------------------------------- tab: analisa
function tabAnalisa(body) {
  const res = S.results[S.cid];
  if (!res) {
    body.innerHTML = `<div class="card">${emptyState("bulb", "Belum ada analisa", "Jalankan agent dulu untuk melihat temuan per analis.")}</div>`;
    return;
  }
  const notes = res.analyst_notes || [];
  const insightHtml = (i) => `
    <div class="insight" style="--sev:${SEV[i.severity]?.color}">
      <div class="insight-title">${sevBadge(i.severity)}<span>${esc(i.title)}</span></div>
      <div class="muted small mono">${esc(i.code)} · prioritas ${esc(i.priority)}</div>
      ${i.facts && Object.keys(i.facts).length ? `<div class="facts">${Object.entries(i.facts).map(([k, v]) =>
        `<div><span>${esc(k)}</span><span>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span></div>`).join("")}</div>` : ""}
      ${i.recommendation ? `<div class="reco">${ICON.bulb}<span>${esc(i.recommendation)}</span></div>` : ""}
    </div>`;
  const decision = (items, held) => items.length ? `<ul>${items.map((i) => `<li><div class="row">${sevBadge(i.severity)}<span>${esc(i.title)}</span></div>
      ${held ? `<span class="why">↳ ${esc(i.hold_reason)}</span>` : ""}</li>`).join("")}</ul>` : `<div class="muted small">—</div>`;

  body.innerHTML = `
    <div class="stack">
      ${res.plan_reason ? `<div class="callout info">${ICON.info}<span><b>Rencana Supervisor:</b> ${esc(res.plan_reason)}</span></div>` : ""}
      <div class="grid-2">
        <div class="card"><div class="card-head"><h3>✅ Dikirim</h3><span class="badge ok">${res.selected?.length || 0}</span></div><div class="decision" style="padding-top:12px">${decision(res.selected || [], false)}</div></div>
        <div class="card"><div class="card-head"><h3>⏸️ Ditahan</h3><span class="badge">${res.held?.length || 0}</span></div><div class="decision" style="padding-top:12px">${decision(res.held || [], true)}</div></div>
      </div>
      <div class="section-title">Temuan per analis</div>
      ${notes.length ? notes.map((n) => {
        const ins = (res.insights || []).filter((i) => i.agent === n.agent);
        return `<div class="card note">
          <div class="note-head"><h3>${esc(n.title)}</h3><div class="row">
            <span class="badge">${ins.length} temuan</span>${n.llm ? '<span class="badge accent">LLM</span>' : '<span class="badge outline">aturan</span>'}</div></div>
          <div class="note-body">
            ${n.analysis ? `<p>${esc(n.analysis)}</p>` : ""}
            ${ins.map(insightHtml).join("")}
            <details class="fold"><summary>Metrik mentah</summary><pre class="code">${esc(JSON.stringify(n.metrics, null, 2))}</pre></details>
          </div></div>`;
      }).join("") : `<div class="card">${emptyState("info", "Tidak ada analis yang ditugaskan")}</div>`}
    </div>`;
}

// ---------------------------------------------------------------- tab: inbox
function tabInbox(body, fresh = false) {
  const p = S.detail.profile;
  if (!fresh) {  // tampilkan cache dulu, lalu ambil versi terbaru (batch/autopilot bisa menambah pesan)
    api(`/api/customers/${p.customer_id}/inbox`).then((rows) => {
      if (S.cid !== p.customer_id || S.tab !== "inbox" || !body.isConnected) return;
      S.inbox = rows;
      tabInbox(body, true);
    }).catch(() => {});
  }
  const res = S.results[S.cid];
  const dup = res?.deliveries?.some((d) => d.status === "duplicate_skipped");
  const now = new Date();
  const items = S.inbox.map((r) => `
    <div class="notif" style="--sev:${SEV[r.severity]?.color}">
      <div class="notif-meta"><span>${sevBadge(r.severity)}</span><span>${dt(r.created_at)}</span></div>
      <div class="notif-title">${esc(r.title)}</div>
      <div class="notif-body">${esc(r.body)}</div>
      ${r.cta ? `<div class="notif-cta">👉 ${esc(r.cta)}</div>` : ""}
      <div class="notif-foot">${r.status === "scheduled" ? `🕗 dijadwalkan ${esc(String(r.send_at || "").slice(11, 16))}` : "✓ terkirim"} · ${esc((r.channels || []).join(", "))}${r.source === "llm" ? " · ditulis LLM" : ""}</div>
      ${r.footer ? `<div class="notif-foot">${esc(r.footer)}</div>` : ""}
    </div>`).join("");
  body.innerHTML = `
    <div class="inbox-wrap">
      <div class="phone"><div class="phone-screen">
        <div class="phone-bar"><span>${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}</span><div class="phone-notch"></div><span>5G ▮▮▮</span></div>
        <div class="phone-title"><div class="muted small">Notifikasi</div><h3>Halo, ${esc(p.nickname || p.full_name)} 👋</h3></div>
        ${items || `<div class="empty" style="padding-top:110px">${ICON.inbox}<strong>Belum ada notifikasi</strong><span>Jalankan agent untuk mengirim pesan.</span></div>`}
      </div></div>
      <div class="stack">
        <div class="card card-pad stack">
          <h3>Tentang inbox</h3>
          <p class="muted">Ini tampilan pesan yang diterima nasabah lewat aplikasi. Warna garis kiri = tingkat urgensi.</p>
          <div class="row wrap">${sevBadge("critical")}${sevBadge("warning")}${sevBadge("info")}</div>
          <p class="muted small">Total ${S.inbox.length} pesan untuk nasabah ini.</p>
        </div>
        ${dup ? `<div class="callout">${ICON.warn}<span>Sebagian pesan tidak dikirim ulang karena aturan dedup (insight sama di tanggal simulasi yang sama). Kosongkan outbox nasabah ini untuk mengulang demo.</span></div>` : ""}
        ${S.inbox.length ? `<button class="btn btn-danger" id="clear-cust-inbox">Kosongkan inbox nasabah ini</button>` : ""}
      </div>
    </div>`;
  $("#clear-cust-inbox")?.addEventListener("click", async () => {
    if (!(await confirmDialog("Kosongkan inbox?", `Semua pesan untuk ${p.full_name} di outbox akan dihapus.`, "Kosongkan"))) return;
    try {
      await api("/api/outbox/clear", { customer_id: p.customer_id });
      S.inbox = [];
      toast("Inbox dikosongkan");
      renderCustomer();
    } catch (e) { toast(e.message, "error"); }
  });
}

// ---------------------------------------------------------------- tab: data
const DATA_TABS = [["profil", "Profil"], ["cards", "Kartu kredit"], ["statements", "Tagihan CC"], ["cctx", "Transaksi CC"], ["savings", "Tabungan"], ["loans", "Pinjaman"]];

async function tabData(body) {
  const d = S.detail;
  body.innerHTML = `<div class="stack">
    <div class="pills">${DATA_TABS.map(([id, l]) => `<button class="pill ${S.dataTab === id ? "active" : ""}" data-dt="${id}">${l}</button>`).join("")}</div>
    <div id="data-body"></div></div>`;
  $$("[data-dt]").forEach((b) => b.addEventListener("click", () => { S.dataTab = b.dataset.dt; tabData(body); }));
  const out = $("#data-body");
  const wrap = (title, inner, extra = "") => `<div class="card"><div class="card-head"><h3>${title}</h3>${extra}</div>${inner}</div>`;

  switch (S.dataTab) {
    case "profil": {
      const { demo_persona, ...p } = d.profile;
      out.innerHTML = `<div class="card card-pad">${kv(p, { monthly_income: "rp", birth_date: "date", joined_date: "date" })}</div>
        <p class="muted small" style="margin-top:8px">Persona demo: ${esc(personaLabel(demo_persona))} (hanya label generator, tidak dipakai agent).</p>`;
      break;
    }
    case "cards":
      out.innerHTML = wrap("Kartu kredit", table(d.credit_cards, [["card_id", "ID"], ["product", "Produk"], ["network", "Network"], ["card_number_masked", "Nomor"],
        ["credit_limit", "Limit", "rp"], ["current_balance", "Terpakai", "rp"], ["available_limit", "Tersedia", "rp"], ["statement_day", "Tgl cetak", "num"],
        ["autodebet", "Autodebet", "bool"], ["reward_points", "Poin", "num"], ["status", "Status", "status"]]));
      break;
    case "statements":
      out.innerHTML = wrap("Tagihan kartu kredit", table([...d.statements].reverse(), [["statement_date", "Tgl cetak", "date"], ["due_date", "Jatuh tempo", "date"],
        ["previous_balance", "Saldo lalu", "rp"], ["new_purchases", "Belanja", "rp"], ["payments", "Pembayaran", "rp"], ["interest", "Bunga", "rp"], ["fees", "Biaya", "rp"],
        ["total_due", "Total tagihan", "rp"], ["minimum_due", "Minimum", "rp"], ["paid_amount", "Dibayar", "rp"], ["paid_date", "Tgl bayar", "date"],
        ["days_past_due", "Telat (hari)", "num"], ["status", "Status", "status"]]));
      break;
    case "cctx": {
      out.innerHTML = wrap("Transaksi kartu kredit", '<div class="card-pad"><div class="skeleton" style="height:200px"></div></div>', daysSelect("cc-days", S.ccDays));
      bindDays("cc-days", (v) => { S.ccDays = v; tabData(body); });
      const tx = await api(`/api/customers/${S.cid}/cc-transactions?days=${S.ccDays}`);
      if (S.dataTab !== "cctx") return;
      out.innerHTML = wrap(`Transaksi kartu kredit <span class="muted small">· ${tx.length} transaksi</span>`, table([...tx].reverse(), [["datetime", "Waktu", "dt"], ["type", "Jenis"],
        ["merchant", "Merchant"], ["category", "Kategori"], ["amount", "Nominal", "rp"], ["currency", "Mata uang"], ["original_amount", "Nominal asli", "num"],
        ["channel", "Kanal"], ["location", "Lokasi"], ["status", "Status", "status"], ["decline_reason", "Alasan tolak"], ["is_recurring", "Berulang", "bool"]]),
        daysSelect("cc-days", S.ccDays));
      bindDays("cc-days", (v) => { S.ccDays = v; tabData(body); });
      break;
    }
    case "savings": {
      out.innerHTML = wrap("Rekening tabungan", table(d.savings, [["account_id", "ID"], ["product", "Produk"], ["balance", "Saldo", "rp"], ["avg_balance_3m", "Rata-rata 3 bln", "rp"],
        ["is_payroll", "Payroll", "bool"], ["opened_date", "Dibuka", "date"], ["status", "Status", "status"]])) +
        `<div style="height:14px"></div><div id="sav-tx">${wrap("Mutasi 60 hari", '<div class="card-pad"><div class="skeleton" style="height:200px"></div></div>')}</div>`;
      const stx = await api(`/api/customers/${S.cid}/savings-transactions?days=60`);
      if (S.dataTab !== "savings") return;
      $("#sav-tx").innerHTML = wrap(`Mutasi 60 hari <span class="muted small">· ${stx.length} mutasi</span>`, table([...stx].reverse(), [["datetime", "Waktu", "dt"],
        ["direction", "Arah", (v) => `<span class="badge ${v === "credit" || v === "in" ? "ok" : ""}">${esc(v)}</span>`], ["category", "Kategori"],
        ["description", "Keterangan"], ["amount", "Nominal", "rp"], ["balance_after", "Saldo akhir", "rp"]]));
      break;
    }
    case "loans":
      out.innerHTML = wrap("Pinjaman", table(d.loans, [["loan_id", "ID"], ["type", "Jenis"], ["product", "Produk"], ["principal", "Pokok", "rp"], ["outstanding", "Sisa", "rp"],
        ["interest_rate_pa", "Bunga p.a.", "pct"], ["monthly_installment", "Cicilan", "rp"], ["remaining_months", "Sisa bln", "num"], ["next_due_date", "Jatuh tempo", "date"],
        ["autodebet", "Autodebet", "bool"], ["days_past_due", "Telat (hari)", "num"], ["status", "Status", "status"]]));
      break;
  }
}

const daysSelect = (id, v) => `<select class="input" id="${id}" style="width:auto;height:32px">${[7, 14, 30, 60, 90, 180].map((d) =>
  `<option value="${d}" ${d === v ? "selected" : ""}>${d} hari terakhir</option>`).join("")}</select>`;
const bindDays = (id, fn) => $(`#${id}`)?.addEventListener("change", (e) => fn(Number(e.target.value)));

// ---------------------------------------------------------------- tab: tanya data
function mdLite(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, '<code>$1</code>');
}

function tabChat(body) {
  const online = S.status.online;
  const examples = [`Berapa total belanja dining ${S.cid} 30 hari terakhir?`, "Siapa nasabah segmen Prioritas di Bandung?",
    `Kapan jatuh tempo tagihan kartu kredit ${S.cid}?`, "Berapa nasabah yang telat bayar kartu kredit?"];
  const log = S.chat.map((m) => `
    <div class="msg ${m.role}">
      <div class="msg-bubble">${m.role === "assistant" ? mdLite(m.content) : esc(m.content)}</div>
      ${m.calls?.length ? `<details class="fold"><summary>${m.calls.length} tool dipanggil</summary><pre class="code">${esc(m.calls.join("\n"))}</pre></details>` : ""}
    </div>`).join("");
  body.innerHTML = `
    ${online ? "" : `<div class="callout" style="margin-bottom:12px">${ICON.warn}<span>Fitur ini butuh LLM. Isi <span class="mono">MODEL_NAME</span> dan API key di <span class="mono">.env</span>, lalu restart server.</span></div>`}
    <div class="card chat">
      <div class="chat-log" id="chat-log">
        ${log || `<div class="suggest">${ICON.chat}<strong style="color:var(--text-2)">Tanya apa saja soal data nasabah</strong>
          <span>Data Agent memakai tools yang sama dengan pipeline untuk mencari jawabannya.</span>
          <div class="chips">${examples.map((q) => `<button class="chip" data-q="${esc(q)}" ${online ? "" : "disabled"}>${esc(q)}</button>`).join("")}</div></div>`}
        ${S.chatBusy ? `<div class="msg assistant"><div class="msg-bubble typing"><span></span><span></span><span></span></div></div>` : ""}
      </div>
      <form class="chat-form" id="chat-form">
        <input class="input" id="chat-input" placeholder="${online ? "Tanya data nasabah…" : "LLM offline"}" ${online && !S.chatBusy ? "" : "disabled"} autocomplete="off">
        <button class="btn btn-primary" ${online && !S.chatBusy ? "" : "disabled"}>${ICON.send}</button>
        ${S.chat.length ? `<button type="button" class="btn btn-ghost" id="chat-clear" title="Mulai percakapan baru">Bersihkan</button>` : ""}
      </form>
    </div>`;
  const logEl = $("#chat-log");
  logEl.scrollTop = logEl.scrollHeight;
  $("#chat-input")?.focus();
  $$("[data-q]").forEach((b) => b.addEventListener("click", () => sendChat(b.dataset.q)));
  $("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); sendChat($("#chat-input").value); });
  $("#chat-clear")?.addEventListener("click", () => { S.chat = []; tabChat(body); });
}

async function sendChat(q) {
  q = q.trim();
  if (!q || S.chatBusy) return;
  const history = S.chat.map(({ role, content }) => ({ role, content }));
  S.chat.push({ role: "user", content: q });
  S.chatBusy = true;
  const rerender = () => { if (S.tab === "chat" && $("#tab-body")) tabChat($("#tab-body")); };
  rerender();
  try {
    const { answer, calls } = await api("/api/ask", { question: q, history });
    S.chat.push({ role: "assistant", content: answer, calls });
  } catch (e) {
    S.chat.push({ role: "assistant", content: `⚠️ ${e.message}` });
  }
  S.chatBusy = false;
  rerender();
}

// ================================================================ halaman: outbox
async function pageOutbox() {
  const main = $("#main");
  main.innerHTML = `<div class="page"><div class="page-head"><div><h1>Outbox</h1><p>Semua pesan yang sudah dikirim agent ke nasabah.</p></div></div>
    <div class="skeleton" style="height:300px"></div></div>`;
  let data;
  try { data = await api("/api/outbox"); } catch (e) { toast(e.message, "error"); return; }
  const { rows, summary } = data;
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Outbox</h1><p>Semua pesan yang sudah dikirim agent ke nasabah. Klik baris untuk membuka nasabahnya.</p></div>
      ${rows.length ? `<button class="btn btn-danger" id="clear-outbox">Kosongkan outbox</button>` : ""}</div>
    <div class="stack">
      <div class="stats">
        <div class="card kpi"><span class="label">Total pesan</span><span class="value">${num(summary.total)}</span></div>
        <div class="card kpi"><span class="label">Nasabah dijangkau</span><span class="value">${num(summary.customers)}</span></div>
        <div class="card kpi"><span class="label">Ditulis LLM</span><span class="value">${num(summary.llm)}</span><span class="sub">${summary.total ? pct(summary.llm / summary.total) : "—"} dari total</span></div>
      </div>
      <div class="card">
        ${rows.length ? `<div class="toolbar">
          <div class="search">${ICON.search}<input class="input" id="ob-q" placeholder="Cari nasabah, judul, kode…" value="${esc(S.outboxFilter.q)}"></div>
          <div class="pills">${[["all", "Semua"], ["critical", "Kritis"], ["warning", "Perhatian"], ["info", "Info"]].map(([v, l]) =>
            `<button class="pill ${S.outboxFilter.sev === v ? "active" : ""}" data-sev="${v}">${l}</button>`).join("")}</div>
        </div>` : ""}
        <div id="ob-table"></div>
      </div>
    </div></div>`;

  const draw = () => {
    const q = S.outboxFilter.q.toLowerCase();
    const f = rows.filter((r) => (S.outboxFilter.sev === "all" || r.severity === S.outboxFilter.sev) &&
      (!q || [r.customer_id, r.title, r.code].some((v) => String(v).toLowerCase().includes(q))));
    $("#ob-table").innerHTML = rows.length ? table(f, [["created_at", "Waktu", "dt"], ["customer_id", "Nasabah"], ["severity", "Severity", "sev"], ["title", "Judul"],
      ["code", "Kode", (v) => `<span class="mono">${esc(v)}</span>`], ["status", "Status", "status"], ["channels", "Kanal"],
      ["source", "Sumber", (v) => (v === "llm" ? '<span class="badge accent">LLM</span>' : '<span class="badge outline">template</span>')]], { onRow: true, rowKey: "customer_id" })
      : emptyState("inbox", "Outbox masih kosong", "Jalankan agent untuk satu nasabah, atau batch di Pengaturan.");
    $$("#ob-table tr.clickable").forEach((tr) => tr.addEventListener("click", () => {
      S.tab = "inbox";
      location.hash = `#/nasabah/${tr.dataset.row}`;
    }));
  };
  draw();
  $("#ob-q")?.addEventListener("input", (e) => { S.outboxFilter.q = e.target.value; draw(); });
  $$("[data-sev]").forEach((b) => b.addEventListener("click", () => {
    S.outboxFilter.sev = b.dataset.sev;
    $$("[data-sev]").forEach((x) => x.classList.toggle("active", x === b));
    draw();
  }));
  $("#clear-outbox")?.addEventListener("click", clearOutbox);
}

async function clearOutbox() {
  if (!(await confirmDialog("Kosongkan outbox?", "Semua pesan untuk semua nasabah akan dihapus. Data nasabah tidak terpengaruh.", "Kosongkan"))) return;
  try {
    await api("/api/outbox/clear", {});
    S.inbox = [];
    toast("Outbox dikosongkan");
    route();
  } catch (e) { toast(e.message, "error"); }
}

// ================================================================ halaman: autopilot
const KIND_ICON = { tick: "🌍", start: "▶️", think: "💭", tool: "🔧", result: "📋", done: "✅", error: "⚠️", report: "📝" };

async function pageAutopilot() {
  const main = $("#main");
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Autopilot</h1>
      <p>Beri misi sekali, lalu agent bekerja sendiri: tiap putaran dunia maju 1 hari, Manager memilih nasabah dan mendelegasikan ke Case Handler → Analis → Communicator.</p></div></div>
    <div class="stack">
      <div class="card">
        <div class="ap-status" id="ap-status"><div class="skeleton" style="height:38px;width:100%"></div></div>
        <div class="ap-controls">
          <label class="field">Hari simulasi <small>0 = terus</small><input class="input" type="number" id="ap-days" min="0" max="365" value="7"></label>
          <label class="field">Jeda per hari <small>detik</small><input class="input" type="number" id="ap-gap" min="0" max="300" step="1" value="5"></label>
          <button class="btn btn-primary" id="ap-start">${ICON.play} Start</button>
          <button class="btn" id="ap-stop">⏹ Stop</button>
          <button class="btn btn-danger" id="ap-reset" title="Hapus feed, memori, follow-up, laporan (data nasabah tetap)">Reset jejak</button>
        </div>
        <div style="padding:0 18px 14px">
          <details class="fold" id="ap-mission"><summary>🎯 Misi tim</summary>
            <form class="stack" id="mission-form" style="margin-top:12px">
              <label class="field">Misi<textarea class="input" name="goal" rows="3"></textarea></label>
              <label class="field">Batasan<textarea class="input" name="constraints" rows="2"></textarea></label>
              <div class="row wrap" style="align-items:end"><label class="field" style="width:200px">Maks kasus per hari<input class="input" type="number" name="max_cases_per_day" min="1" max="30"></label>
                <button class="btn btn-primary">Simpan misi</button><span class="muted small">Dipakai mulai hari simulasi berikutnya.</span></div>
            </form>
          </details>
        </div>
      </div>
      ${S.status.online ? "" : `<div class="callout">${ICON.warn}<span>Mode offline: dunia tetap bergerak, nasabah prioritas diproses pipeline aturan (tanpa agent yang berpikir).</span></div>`}
      <div class="ap-grid">
        <div class="card"><div class="card-head"><h3>Feed agent</h3><span class="muted small" id="ap-feed-count"></span></div><div class="feed" id="ap-feed"></div></div>
        <div class="stack">
          <div class="card"><div class="card-head"><h3>📝 Laporan harian Manager</h3></div><div id="ap-reports" style="max-height:300px;overflow:auto"></div></div>
          <div class="card"><div class="card-head"><h3>⏰ Follow-up terbuka</h3><span class="badge" id="ap-fu-count">0</span></div><div id="ap-fu"></div></div>
          <div class="card"><div class="card-head"><h3>🌍 Kejadian terbaru</h3></div><div id="ap-events"></div></div>
        </div>
      </div>
    </div></div>`;

  let missionLoaded = false;
  let feedSig = "";
  const refresh = async () => {
    let d;
    try { d = await api("/api/autopilot"); } catch (e) { $("#ap-status").innerHTML = `<span class="muted">${esc(e.message)}</span>`; return; }
    if (!$("#ap-status")) return;
    const s = d.state;
    $("#ap-status").innerHTML = `
      <div class="item"><span>Status</span><span><i class="dot ${d.alive ? "on pulse" : "off"}"></i>${d.alive ? "berjalan" : "berhenti"}</span></div>
      <div class="item"><span>Mode</span><span>${esc(s.mode || "—")}</span></div>
      <div class="item"><span>Tanggal simulasi</span><span>${tgl(d.sim_date)}</span></div>
      <div class="item"><span>Hari ke-</span><span>${esc(s.days_done ?? 0)}</span></div>
      <div class="item grow"><span>Fase</span><span>${esc(s.phase || "—")}</span></div>
      ${s.error ? `<div class="callout" style="width:100%">${ICON.warn}<span>${esc(s.error)}</span></div>` : ""}`;
    $("#ap-start").disabled = d.alive;
    $("#ap-stop").disabled = !d.alive;
    $("#ap-reset").disabled = d.alive;
    if (!missionLoaded) {
      const f = $("#mission-form");
      f.goal.value = d.mission.goal;
      f.constraints.value = d.mission.constraints;
      f.max_cases_per_day.value = d.mission.max_cases_per_day;
      missionLoaded = true;
    }
    const sig = d.activity.length + "|" + (d.activity[0]?.ts || "");
    if (sig !== feedSig) {
      feedSig = sig;
      $("#ap-feed-count").textContent = `${d.activity.length} aktivitas terakhir`;
      $("#ap-feed").innerHTML = d.activity.length ? d.activity.map((a) => `
        <div class="feed-item k-${esc(a.kind)}" style="padding-left:${10 + a.depth * 20}px">
          <div class="feed-icon">${KIND_ICON[a.kind] || "•"}</div>
          <div><div class="t">${esc(a.sim_date || "")} ${esc(a.ts || "")}</div>
            <div class="txt"><b>${esc(a.agent)}</b>${a.customer_id ? ` <a href="#/nasabah/${esc(a.customer_id)}" class="mono">[${esc(a.customer_id)}]</a>` : ""}: ${esc(a.text)}</div></div>
        </div>`).join("") : emptyState("play", "Belum ada aktivitas", "Klik Start untuk menjalankan autopilot.");
    }
    $("#ap-reports").innerHTML = d.reports.length ? d.reports.map((r) => `<div class="report"><div class="d">${tgl(r.sim_date, true)}</div><div class="r">${esc(r.report)}</div></div>`).join("")
      : `<div class="card-pad muted small">Belum ada laporan.</div>`;
    $("#ap-fu-count").textContent = d.followups.length;
    $("#ap-fu").innerHTML = d.followups.length ? table(d.followups, [["due_date", "Jatuh tempo", "date"], ["customer_id", "Nasabah"], ["reason", "Alasan", (v) => esc(v)]])
      : `<div class="card-pad muted small">Tidak ada follow-up terbuka.</div>`;
    $("#ap-events").innerHTML = d.events.length ? table(d.events.slice(0, 40), [["date", "Tanggal", "date"], ["customer_id", "Nasabah"], ["type", "Jenis"], ["detail", "Detail"]])
      : `<div class="card-pad muted small">Belum ada kejadian.</div>`;
  };

  $("#ap-start").addEventListener("click", async () => {
    try {
      await api("/api/autopilot/start", { days: Number($("#ap-days").value), interval: Number($("#ap-gap").value) });
      toast("Autopilot dimulai");
      setTimeout(refresh, 1500);
    } catch (e) { toast(e.message, "error"); }
  });
  $("#ap-stop").addEventListener("click", async () => {
    try { await api("/api/autopilot/stop", {}); toast("Autopilot akan berhenti setelah langkah saat ini"); } catch (e) { toast(e.message, "error"); }
  });
  $("#ap-reset").addEventListener("click", async () => {
    if (!(await confirmDialog("Reset jejak autopilot?", "Feed, memori, follow-up, dan laporan akan dihapus. Data nasabah tetap.", "Reset"))) return;
    try { await api("/api/autopilot/reset", {}); feedSig = ""; toast("Jejak autopilot dihapus"); refresh(); } catch (e) { toast(e.message, "error"); }
  });
  $("#mission-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await api("/api/autopilot/mission", { goal: f.goal.value, constraints: f.constraints.value, max_cases_per_day: Number(f.max_cases_per_day.value) });
      toast("Misi disimpan");
    } catch (err) { toast(err.message, "error"); }
  });

  await refresh();
  S.apTimer = setInterval(refresh, 2000);
}

// ================================================================ halaman: pengaturan
function pagePengaturan() {
  const s = S.status;
  const c = s.counts || {};
  $("#main").innerHTML = `<div class="page" style="max-width:900px">
    <div class="page-head"><div><h1>Pengaturan</h1><p>Batch harian, data dummy, dan outbox.</p></div></div>
    <div class="stack">
      <div class="card">
        <div class="card-head"><h3>Status sistem</h3></div>
        <div class="card-pad">${kv({ LLM: s.llm, "Sumber data": s.backend, "Tanggal simulasi": s.sim_date ? tgl(s.sim_date, true) : "—",
          Nasabah: num(c.customers), "Transaksi CC": num(c.cc_transactions), "Mutasi tabungan": num(c.savings_transactions),
          "Tagihan CC": num(c.cc_statements), Pinjaman: num(c.loans) })}</div>
      </div>

      <div class="card">
        <div class="card-head"><div><h3>Batch (simulasi job harian)</h3><div class="muted small">Jalankan agent untuk N nasabah pertama dengan objective default.</div></div></div>
        <div class="card-pad stack">
          <div class="row wrap" style="align-items:end">
            <label class="field" style="width:180px">Jumlah nasabah<input class="input" type="number" id="batch-n" min="1" max="${c.customers || 1}" value="${Math.min(20, c.customers || 1)}"></label>
            <button class="btn btn-primary" id="batch-btn" ${s.ready ? "" : "disabled"}>${ICON.play} Jalankan batch</button>
            <span class="muted small">${s.online ? "Mode LLM: ±7 panggilan LLM per nasabah." : "Mode offline: cepat (±0,1 dtk/nasabah)."}</span>
          </div>
          <div id="batch-progress" class="hidden stack" style="gap:6px"><div class="progress"><div style="width:0"></div></div><span class="muted small"></span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div><h3>Generate ulang data dummy</h3><div class="muted small">Membuat data nasabah baru${s.backend === "postgres" ? " dan memuatnya ke PostgreSQL" : ""}. Data lama ditimpa.</div></div></div>
        <div class="card-pad row wrap" style="align-items:end">
          <label class="field" style="width:160px">Jumlah nasabah<input class="input" type="number" id="gen-n" min="8" max="5000" step="50" value="${c.customers || 200}"></label>
          <label class="field" style="width:120px">Seed<input class="input" type="number" id="gen-seed" min="0" max="99999" value="42"></label>
          <button class="btn" id="gen-btn">Generate data</button>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div><h3>Outbox</h3><div class="muted small">Hapus semua pesan supaya demo bisa diulang (aturan dedup mencegah kirim ulang).</div></div>
          <button class="btn btn-danger" id="clear-outbox">Kosongkan outbox</button></div>
      </div>
    </div></div>`;

  $("#clear-outbox").addEventListener("click", clearOutbox);
  $("#batch-btn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const box = $("#batch-progress");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Berjalan…';
    box.classList.remove("hidden");
    try {
      const { job_id } = await api("/api/batch", { limit: Number($("#batch-n").value) });
      const job = await pollJob(job_id, (j) => {
        const p = j.progress;
        if (!p || !$("#batch-progress")) return;
        $("#batch-progress .progress > div").style.width = `${(p.done / p.total) * 100}%`;
        $("#batch-progress span").textContent = `${p.done}/${p.total} · ${p.label}`;
      }, 600);
      if (job.status === "error") throw new Error(job.error);
      toast(`Batch selesai: ${job.result.processed} nasabah, ${job.result.sent} pesan baru`);
      if ($("#batch-progress span")) $("#batch-progress span").textContent = `Selesai — ${job.result.processed} nasabah diproses, ${job.result.sent} pesan baru masuk outbox.`;
    } catch (err) { toast(err.message, "error"); }
    if ($("#batch-btn")) { btn.disabled = false; btn.innerHTML = `${ICON.play} Jalankan batch`; }
  });
  $("#gen-btn").addEventListener("click", async (e) => {
    const n = Number($("#gen-n").value), seed = Number($("#gen-seed").value);
    if (!(await confirmDialog("Generate ulang data?", `Data ${s.backend} akan diganti dengan ${n} nasabah baru (seed ${seed}). Hasil agent di layar akan hilang.`, "Generate"))) return;
    const btn = e.target;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="border-color:var(--surface-3);border-top-color:var(--accent)"></span> Membuat data…';
    try {
      const { job_id } = await api("/api/generate", { customers: n, seed });
      const job = await pollJob(job_id, null, 800);
      if (job.status === "error") throw new Error(job.error);
      S.results = {};
      S.detail = null;
      await loadStatus();
      toast("Data dummy dibuat ulang");
      pagePengaturan();
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Generate data";
    }
  });
}

// ================================================================ boot
(async function boot() {
  try {
    await loadStatus();
  } catch (e) {
    $("#main").innerHTML = `<div class="page"><div class="card">${emptyState("warn", "Gagal terhubung ke server", esc(e.message))}</div></div>`;
    return;
  }
  if (!location.hash && S.cid) history.replaceState(null, "", `#/nasabah/${S.cid}`);
  route();
})();
