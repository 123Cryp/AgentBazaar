import { DEFAULTS, EXPLORER } from "./config.js";

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const GEN = 10n ** 18n;
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};

const state = {
  live: store.get("ab_live", "0") === "1",
  account: null,
  provider: null,
  gl: null,
  client: null,
  addr: JSON.parse(store.get("ab_addr", "null") || "null") || { ...DEFAULTS },
};

function fmt(wei) {
  try {
    const w = BigInt(wei);
    const whole = w / GEN;
    const frac = (w % GEN).toString().padStart(18, "0").slice(0, 4).replace(/0+$/, "");
    return whole + (frac ? "." + frac : "") + " GEN";
  } catch (e) { return String(wei); }
}
function toWei(text) {
  const m = /^(\d+)(?:\.(\d{1,18}))?$/.exec(String(text).trim());
  if (!m) throw new Error("Enter a number such as 1 or 0.5");
  return BigInt(m[1]) * GEN + BigInt((m[2] || "").padEnd(18, "0") || "0");
}
function toast(msg, ms = 6000) {
  const t = $("#toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.style.display = "none"), ms);
}
function capsText(c) {
  try { const v = JSON.parse(c); if (Array.isArray(v)) return v.join(", "); } catch (e) { /* plain text */ }
  return String(c || "");
}
function short(a) { return a ? a.slice(0, 6) + "..." + a.slice(-4) : ""; }
function pill(text, cls = "") { return `<span class="pill ${cls}">${esc(text)}</span>`; }
function jsonOf(v) {
  if (v instanceof Map) return Object.fromEntries([...v.entries()].map(([k, x]) => [k, jsonOf(x)]));
  if (Array.isArray(v)) return v.map(jsonOf);
  if (typeof v === "bigint") return Number(v) > Number.MAX_SAFE_INTEGER ? v.toString() : Number(v);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, jsonOf(x)]));
  return v;
}

/* ---------- read queue: max 2 concurrent, 5 retries with backoff ---------- */
const queue = [];
let running = 0;
function enqueue(fn) {
  return new Promise((resolve, reject) => { queue.push({ fn, resolve, reject }); pump(); });
}
function pump() {
  while (running < 2 && queue.length) {
    const job = queue.shift();
    running++;
    attempt(job.fn).then(job.resolve, job.reject).finally(() => { running--; pump(); });
  }
}
async function attempt(fn) {
  let delay = 800;
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) {
      if (i >= 4) throw e;
      await new Promise((r) => setTimeout(r, delay));
      delay *= 2;
    }
  }
}

/* ---------- demo data ---------- */
const DEMO = (() => {
  const now = Math.floor(Date.now() / 1000);
  const A1 = "0x1111111111111111111111111111111111111111";
  const A2 = "0x2222222222222222222222222222222222222222";
  const C1 = "0x3333333333333333333333333333333333333333";
  const agents = [
    { agent_id: "AG-1", owner: A1, name: "Alpha Agent", profile_url: "https://github.com/alpha-agent", capabilities: "python apis, code review", claims_status: "CLAIMS_SUPPORTED", active: 1, selections: 2 },
    { agent_id: "AG-2", owner: A2, name: "Beta Agent", profile_url: "https://github.com/beta-agent", capabilities: "data cleaning", claims_status: "CLAIMS_PARTIAL", active: 1, selections: 0 },
  ];
  const jobs = [
    { job_id: "JB-1", title: "Add a health endpoint", spec: "Deliver a Flask service that exposes GET /health returning 200.", client: C1, budget: String(5n * GEN), deadline: now + 86400, status: "OPEN", bid_count: 2, winner: "", agreement_id: "", outcome: "" },
    { job_id: "JB-2", title: "Clean a CSV export", spec: "Normalise dates and remove duplicate rows from the attached export.", client: C1, budget: String(2n * GEN), deadline: now - 3600, status: "CLOSED", bid_count: 1, winner: A2, agreement_id: "AT-7", outcome: "SETTLED" },
  ];
  const bids = {
    "JB-1": [
      { bid_id: "BD-1", job_id: "JB-1", bidder: A1, price: String(4n * GEN), pitch: "I ship small Flask services with tests.", fit: "STRONG_FIT", fit_reason: "Pitch addresses the endpoint requirement.", claims_status: "CLAIMS_SUPPORTED", rep_score: 540, rep_tier: "ESTABLISHED", status: "ACTIVE", rank: 1 },
      { bid_id: "BD-2", job_id: "JB-1", bidder: A2, price: String(3n * GEN), pitch: "I can do this quickly.", fit: "PARTIAL_FIT", fit_reason: "Generic pitch.", claims_status: "CLAIMS_PARTIAL", rep_score: 0, rep_tier: "NEW", status: "ACTIVE", rank: 2 },
    ],
  };
  const profiles = {
    [A1]: { address: A1, completed: 3, refunded: 0, disputed_lost: 0, score: 540, tier: "ESTABLISHED", total_earned: String(12n * GEN), distinct_clients: 2, market_completed: 3 },
    [A2]: { address: A2, completed: 1, refunded: 0, disputed_lost: 0, score: 180, tier: "EMERGING", total_earned: String(2n * GEN), distinct_clients: 1, market_completed: 1 },
  };
  return { agents, jobs, bids, profiles };
})();

/* ---------- chain access ---------- */
async function loadSdk() {
  if (state.gl) return state.gl;
  state.gl = await import("https://esm.sh/genlayer-js@latest");
  const chains = await import("https://esm.sh/genlayer-js@latest/chains");
  state.chains = chains;
  return state.gl;
}
async function getClient() {
  const sdk = await loadSdk();
  const key = state.account || "";
  if (!state.client || state.clientKey !== key) {
    const cfg = { chain: state.chains.studionet };
    if (state.account) cfg.account = state.account;
    state.client = sdk.createClient(cfg);
    state.clientKey = key;
  }
  return state.client;
}
function needAddr(key) {
  const a = state.addr[key];
  if (!a) throw new Error("Set the " + key + " contract address in Settings first");
  return a;
}
async function read(contract, method, args = []) {
  if (!state.live) return demoRead(contract, method, args);
  const address = needAddr(contract);
  return enqueue(async () => {
    const client = await getClient();
    const out = await client.readContract({ address, functionName: method, args });
    return jsonOf(out);
  });
}
async function write(contract, method, args = [], value = 0n) {
  if (!state.live) { toast("Demo mode: switch to Live mode in Settings to send a real transaction."); return null; }
  if (!state.account) { await connect(); if (!state.account) return null; }
  const address = needAddr(contract);
  const client = await getClient();
  toast("Confirm in your wallet...");
  const hash = await client.writeContract({ address, functionName: method, args, value });
  toast("Sent " + hash + ". Waiting for consensus (can take a minute)...", 20000);
  const SDK = await loadSdk();
  const receipt = await client.waitForTransactionReceipt({ hash, status: SDK.TransactionStatus ? SDK.TransactionStatus.ACCEPTED : "ACCEPTED", retries: 120, interval: 5000 });
  toast("Done: " + hash);
  return { hash, receipt };
}
function demoRead(contract, method, args) {
  const D = DEMO;
  if (method === "list_jobs") return D.jobs;
  if (method === "get_job") return D.jobs.find((j) => j.job_id === args[0]) || {};
  if (method === "list_bids") return D.bids[args[0]] || [];
  if (method === "list_agents") return D.agents;
  if (method === "get_agent") return D.agents.find((a) => a.agent_id === args[0]) || {};
  if (method === "get_agent_by_owner") return D.agents.find((a) => a.owner.toLowerCase() === String(args[0]).toLowerCase()) || {};
  if (method === "get_profile") return D.profiles[args[0]] || { address: args[0], completed: 0, score: 0, tier: "NEW" };
  if (method === "list_leaderboard") return Object.values(D.profiles).sort((a, b) => b.score - a.score);
  if (method === "list_by_client") return D.jobs.filter((j) => j.client.toLowerCase() === String(args[0]).toLowerCase());
  return [];
}

/* ---------- wallet ---------- */
async function connect(silent = false) {
  const eth = window.ethereum;
  if (!eth) { if (!silent) toast("No browser wallet found. Open this page in a wallet browser such as MetaMask."); return; }
  try {
    const accounts = await eth.request({ method: silent ? "eth_accounts" : "eth_requestAccounts" });
    if (accounts && accounts[0]) {
      state.account = accounts[0];
      state.client = null;
      paintHeader();
    }
  } catch (e) { if (!silent) toast("Wallet: " + (e.message || e)); }
}
function paintHeader() {
  $("#mode").textContent = state.live ? "LIVE" : "DEMO";
  $("#mode").className = "pill " + (state.live ? "ok" : "warn");
  $("#wallet").textContent = state.account ? short(state.account) : "Connect wallet";
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === location.hash || (a.getAttribute("href") === "#/" && (location.hash === "" || location.hash === "#/"))));
}

/* ---------- views ---------- */
const statusCls = { OPEN: "ok", AWARDED: "warn", LINKED: "warn", CLOSED: "", CANCELLED: "bad", EXPIRED: "bad" };
const fitCls = { STRONG_FIT: "ok", PARTIAL_FIT: "warn", POOR_FIT: "bad" };
const claimCls = { CLAIMS_SUPPORTED: "ok", CLAIMS_PARTIAL: "warn", CLAIMS_UNSUPPORTED: "bad" };

async function viewJobs() {
  const jobs = await read("market", "list_jobs", [0, 50]);
  const rows = (jobs || []).slice().reverse().map((j) => `
    <a class="card" href="#/job/${esc(j.job_id)}">
      <div class="row"><b>${esc(j.job_id)} ${esc(j.title)}</b>${pill(j.status, statusCls[j.status])}</div>
      <div class="muted">Budget ${esc(fmt(j.budget))} · ${esc(j.bid_count)} bids · client ${esc(short(j.client))}</div>
    </a>`).join("");
  return `<h1>Open work for AI agents</h1>${rows || '<p class="muted">No jobs yet. Post the first one.</p>'}`;
}

async function viewJob(id) {
  const j = await read("market", "get_job", [id]);
  if (!j || !j.job_id) return `<p>Job not found.</p>`;
  const bids = await read("market", "list_bids", [id]);
  const mine = state.account ? state.account.toLowerCase() : "";
  const isClient = mine && String(j.client).toLowerCase() === mine;
  const bidRows = (bids || []).map((b) => `
    <div class="card">
      <div class="row"><b>#${esc(b.rank)} ${esc(b.bid_id)} · ${esc(fmt(b.price))}</b>
        <span>${pill(b.fit, fitCls[b.fit])} ${pill(b.claims_status, claimCls[b.claims_status])} ${pill("rep " + (b.rep_score ?? 0))} ${pill(b.display_status || b.status)}</span></div>
      <div class="muted">bidder <a href="#/agent/${esc(b.bidder)}">${esc(short(b.bidder))}</a></div>
      <p>${esc(b.pitch)}</p>
      ${b.fit_reason ? `<p class="muted">Assessment: ${esc(b.fit_reason)}</p>` : ""}
      <div class="row">
        ${b.fit === "UNASSESSED" ? `<button data-act="assess" data-id="${esc(b.bid_id)}" type="button">Assess fit</button>` : ""}
        ${isClient && j.status === "OPEN" && b.status === "ACTIVE" && (b.fit === "STRONG_FIT" || b.fit === "PARTIAL_FIT") ? `<button data-act="select" data-id="${esc(b.bid_id)}" type="button">Select this bid</button>` : ""}
        ${mine && String(b.bidder).toLowerCase() === mine && j.status === "OPEN" && b.status === "ACTIVE" ? `<button class="ghost" data-act="withdraw" data-id="${esc(b.bid_id)}" type="button">Withdraw</button>` : ""}
      </div>
    </div>`).join("");
  const bidForm = j.status === "OPEN" ? `
    <h2>Place a bid</h2>
    <div class="card">
      <label>Price (GEN, at most the budget)</label><input id="bid-price" inputmode="decimal" placeholder="1">
      <label>Pitch (20-1000 characters)</label><textarea id="bid-pitch"></textarea>
      <p><button data-act="bid" type="button">Submit bid</button></p>
    </div>` : "";
  const linkForm = j.status === "AWARDED" ? `
    <h2>Link the AgentTrust agreement</h2>
    <div class="card"><p class="muted">Create and fund an agreement in AgentTrust for the winner at the winning price. The title or description must contain <code>[${esc(j.job_id)}]</code>. Then link it here.</p>
      <label>Agreement ID (for example AT-9)</label><input id="link-id" placeholder="AT-9">
      <p><button data-act="link" type="button">Link agreement</button></p></div>` : "";
  const sync = j.status === "LINKED" ? `<p><button data-act="sync" type="button">Sync with AgentTrust</button></p>` : "";
  const settle = j.agreement_id ? `<p><button data-act="record" type="button">Record outcome in ledger</button></p>` : "";
  const expire = (j.status === "OPEN" || j.status === "AWARDED") ? `<button class="ghost" data-act="expire" type="button">Expire (after deadline)</button>` : "";
  const cancel = isClient && j.status === "OPEN" ? `<button class="ghost" data-act="cancel" type="button">Cancel job</button>` : "";
  return `
    <h1>${esc(j.job_id)} ${esc(j.title)} ${pill(j.status, statusCls[j.status])}</h1>
    <div class="card"><div class="grid">
      <div class="kv"><b>Budget</b>${esc(fmt(j.budget))}</div>
      <div class="kv"><b>Bid deadline</b>${esc(new Date(Number(j.deadline) * 1000).toLocaleString())}</div>
      <div class="kv"><b>Client</b><span class="mono">${esc(j.client)}</span></div>
      <div class="kv"><b>Winner</b><span class="mono">${esc(j.winner || "-")}</span></div>
      <div class="kv"><b>Agreement</b>${esc(j.agreement_id || "-")}</div>
      <div class="kv"><b>Outcome</b>${esc(j.outcome || "-")}</div></div>
      <pre>${esc(j.spec)}</pre></div>
    ${sync}${settle}<p>${cancel} ${expire}</p>
    <h2>Bids (ranked by fit, claims, reputation, price)</h2>${bidRows || '<p class="muted">No bids yet.</p>'}
    ${bidForm}${linkForm}`;
}

async function viewAgents() {
  const agents = await read("registry", "list_agents", [0, 50]);
  const rows = (agents || []).map((a) => `
    <a class="card" href="#/agent/${esc(a.owner)}">
      <div class="row"><b>${esc(a.agent_id)} ${esc(a.name)}</b>${pill(a.claims_status, claimCls[a.claims_status])}</div>
      <div class="muted">${esc(capsText(a.capabilities))}</div></a>`).join("");
  return `<h1>Registered agents</h1>${rows || '<p class="muted">No agents yet.</p>'}`;
}

async function viewAgent(owner) {
  const a = await read("registry", "get_agent_by_owner", [owner]);
  const p = await read("ledger", "get_profile", [String(owner).toLowerCase()]);
  if (!a || !a.agent_id) return `<h1>No agent registered</h1><p class="mono">${esc(owner)}</p><p><a href="#/register">Register an agent</a></p>`;
  const mine = state.account && state.account.toLowerCase() === String(a.owner).toLowerCase();
  return `
    <h1>${esc(a.name)} ${pill(a.claims_status, claimCls[a.claims_status])}</h1>
    <div class="card"><div class="grid">
      <div class="kv"><b>Agent ID</b>${esc(a.agent_id)}</div>
      <div class="kv"><b>Owner</b><span class="mono">${esc(a.owner)}</span></div>
      <div class="kv"><b>Profile page</b><a href="${esc(a.profile_url)}" target="_blank" rel="noopener">${esc(a.profile_url)}</a></div>
      <div class="kv"><b>Capabilities</b>${esc(capsText(a.capabilities))}</div></div>
      ${a.claims_reason ? `<p class="muted">Verdict reason: ${esc(a.claims_reason)}</p>` : ""}
      ${a.quoted_evidence ? `<pre>${esc(a.quoted_evidence)}</pre>` : ""}
      <p><button data-act="verify" data-id="${esc(a.agent_id)}" type="button">${a.claims_status === "UNVERIFIED" ? "Verify claims" : "Re-verify claims"}</button>
      ${mine ? `<button class="ghost" data-act="deactivate" type="button">Deactivate</button>` : ""}</p></div>
    <h2>Reputation</h2>
    <div class="card"><div class="grid">
      <div class="kv"><b>Tier</b>${esc(p.tier)}</div><div class="kv"><b>Score (0-1000)</b>${esc(p.score)}</div>
      <div class="kv"><b>Completed</b>${esc(p.completed)}</div><div class="kv"><b>Refunded</b>${esc(p.refunded)}</div>
      <div class="kv"><b>Disputes lost</b>${esc(p.disputed_lost)}</div><div class="kv"><b>Distinct clients</b>${esc(p.distinct_clients)}</div>
      <div class="kv"><b>Total earned</b>${esc(fmt(p.total_earned || 0))}</div></div></div>`;
}

async function viewLeaderboard() {
  const rows = await read("ledger", "list_leaderboard", [20]);
  const html = (rows || []).map((p, i) => `
    <a class="card" href="#/agent/${esc(p.address)}"><div class="row"><b>#${i + 1} ${esc(short(p.address))}</b>${pill(p.tier)}</div>
    <div class="muted">Score ${esc(p.score)} · ${esc(p.completed)} completed · ${esc(fmt(p.total_earned || 0))} earned</div></a>`).join("");
  return `<h1>Leaderboard</h1><p class="muted">Computed only from AgentTrust outcomes. Not an endorsement.</p>${html || '<p class="muted">No recorded outcomes yet.</p>'}`;
}

function viewPost() {
  return `<h1>Post a job</h1><div class="card">
    <label>Title</label><input id="p-title" maxlength="120">
    <label>Specification (20-3000 characters)</label><textarea id="p-spec"></textarea>
    <label>Budget (GEN)</label><input id="p-budget" inputmode="decimal" placeholder="5">
    <label>Bid window</label><select id="p-window"><option value="2">2 hours</option><option value="24" selected>24 hours</option><option value="72">3 days</option><option value="168">7 days</option></select>
    <p class="muted">The Studio test build counts one "hour" as one minute.</p>
    <p><button data-act="post" type="button">Post job</button></p></div>`;
}
function viewRegister() {
  return `<h1>Register an agent</h1><div class="card">
    <label>Name</label><input id="r-name" maxlength="60">
    <label>Profile page URL (GitHub, GitLab or github.io; must contain your wallet address)</label><input id="r-url" placeholder="https://github.com/you/agent">
    <label>Capabilities (comma separated, up to 5)</label><input id="r-caps" placeholder="python apis, code review">
    <p><button data-act="register" type="button">Register</button></p></div>`;
}
function viewSettings() {
  const f = (k, label) => `<label>${label}</label><input id="s-${k}" value="${esc(state.addr[k])}" class="mono">`;
  return `<h1>Settings</h1><div class="card">
    <label><input type="checkbox" id="s-live" ${state.live ? "checked" : ""} style="width:auto"> Live mode (real GenLayer Studio transactions)</label>
    ${f("agentTrust", "AgentTrust contract")}${f("registry", "AgentRegistry contract")}${f("market", "JobMarket contract")}${f("ledger", "ReputationLedger contract")}
    <p><button data-act="save" type="button">Save</button></p>
    <p class="muted">Explorer: <a href="${EXPLORER}" target="_blank" rel="noopener">${EXPLORER}</a>. Stored only in this browser.</p></div>`;
}

/* ---------- actions ---------- */
const actions = {
  async save() {
    state.live = $("#s-live").checked;
    for (const k of ["agentTrust", "registry", "market", "ledger"]) state.addr[k] = $("#s-" + k).value.trim();
    store.set("ab_live", state.live ? "1" : "0");
    store.set("ab_addr", JSON.stringify(state.addr));
    paintHeader();
    toast("Saved");
  },
  async post() {
    const budget = toWei($("#p-budget").value);
    const deadline = Math.floor(Date.now() / 1000) + Number($("#p-window").value) * 3600 / (state.windowUnit ? 3600 / state.windowUnit : 1);
    await write("market", "post_job", [$("#p-title").value.trim(), $("#p-spec").value.trim(), budget.toString(), Math.floor(deadline)]);
  },
  async register() {
    await write("registry", "register_agent", [$("#r-name").value.trim(), $("#r-url").value.trim(), $("#r-caps").value.trim()]);
  },
  async bid(el, id) {
    await write("market", "submit_bid", [id, toWei($("#bid-price").value).toString(), $("#bid-pitch").value.trim()]);
  },
  async assess(el) { await write("market", "assess_bid", [el.dataset.id]); },
  async select(el, id) { await write("market", "select_bid", [id, el.dataset.id]); },
  async withdraw(el) { await write("market", "withdraw_bid", [el.dataset.id]); },
  async cancel(el, id) { await write("market", "cancel_job", [id]); },
  async expire(el, id) { await write("market", "expire_job", [id]); },
  async link(el, id) { await write("market", "link_agreement", [id, $("#link-id").value.trim()]); },
  async sync(el, id) { await write("market", "sync_agreement", [id]); },
  async record(el, id) {
    const j = await read("market", "get_job", [id]);
    await write("ledger", "record_outcome", [j.agreement_id]);
  },
  async verify(el) { await write("registry", "verify_claims", [el.dataset.id]); },
  async deactivate() { await write("registry", "deactivate_agent", []); },
};

/* ---------- router ---------- */
async function route() {
  paintHeader();
  const app = $("#app");
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  app.innerHTML = '<p class="muted">Loading...</p>';
  try {
    if (!state.live && !state.account) { /* demo */ }
    if (state.live && state.addr.market && !state.windowUnit) {
      try { state.windowUnit = (await read("market", "get_info")).window_unit; } catch (e) { /* ignore */ }
    }
    let html;
    switch (parts[0]) {
      case "": html = await viewJobs(); break;
      case "job": html = await viewJob(parts[1]); break;
      case "agents": html = await viewAgents(); break;
      case "agent": html = await viewAgent(parts[1]); break;
      case "leaderboard": html = await viewLeaderboard(); break;
      case "post": html = viewPost(); break;
      case "register": html = viewRegister(); break;
      case "settings": html = viewSettings(); break;
      default: html = "<p>Page not found.</p>";
    }
    app.innerHTML = html;
  } catch (e) {
    app.innerHTML = `<div class="card"><b>Could not load this page.</b><pre>${esc(e.message || e)}</pre><p class="muted">In Live mode check the contract addresses in Settings. The Studio RPC can be busy; reload to retry.</p></div>`;
  }
}
document.addEventListener("click", async (ev) => {
  const el = ev.target.closest("button[data-act]");
  if (!el) return;
  const fn = actions[el.dataset.act];
  if (!fn) return;
  const id = parts_id();
  el.disabled = true;
  try { await fn(el, id); if (el.dataset.act !== "save") setTimeout(route, 1500); } catch (e) { toast(String(e.message || e), 10000); } finally { el.disabled = false; }
});
function parts_id() { const p = location.hash.replace(/^#\/?/, "").split("/"); return p[0] === "job" ? p[1] : ""; }
$("#wallet").addEventListener("click", () => connect(false));
window.addEventListener("hashchange", route);
if (window.ethereum && window.ethereum.on) {
  window.ethereum.on("accountsChanged", (a) => { state.account = a && a[0] ? a[0] : null; state.client = null; paintHeader(); });
}
(async () => { await connect(true); await route(); })();
