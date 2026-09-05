// Chargeback Responder — Local Dashboard Application

let allDisputes = [];
let filteredDisputes = [];
let currentPage = 1;
let pageSize = 50;
let sortColumn = "dispute_id";
let sortOrder = "asc";
let activeDispute = null;
let activePacketData = null;
let activeTab = "overview";
let metricsData = null;

const fmtINR = (num) => {
  if (num === null || num === undefined) return "₹0.00";
  return "₹" + Number(num).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

const fmtPercent = (val) => {
  if (val === null || val === undefined) return "0.0%";
  return (Number(val) * 100).toFixed(1) + "%";
};

// ---------------- Init ----------------
document.addEventListener("DOMContentLoaded", () => {
  loadMetrics();
  loadDisputes();
  setupEventListeners();
});

function setupEventListeners() {
  document.getElementById("filter-search").addEventListener("input", debounce(applyFilters, 150));
  document.getElementById("filter-decision").addEventListener("change", applyFilters);
  document.getElementById("filter-network").addEventListener("change", applyFilters);
  document.getElementById("filter-gap").addEventListener("change", applyFilters);
  document.getElementById("filter-novelty").addEventListener("change", applyFilters);

  document.getElementById("select-page-size").addEventListener("change", (e) => {
    pageSize = parseInt(e.target.value, 10);
    currentPage = 1;
    renderTable();
  });

  document.getElementById("btn-prev").addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage--;
      renderTable();
    }
  });

  document.getElementById("btn-next").addEventListener("click", () => {
    const totalPages = Math.ceil(filteredDisputes.length / pageSize) || 1;
    if (currentPage < totalPages) {
      currentPage++;
      renderTable();
    }
  });

  document.querySelectorAll(".dispute-table th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.dataset.sort;
      if (sortColumn === col) {
        sortOrder = sortOrder === "asc" ? "desc" : "asc";
      } else {
        sortColumn = col;
        sortOrder = col === "amount_inr" || col === "p_win_adjusted" || col === "expected_value" ? "desc" : "asc";
      }
      applyFilters();
    });
  });

  // Drawer events
  document.getElementById("drawer-close").addEventListener("click", closeDrawer);
  document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);

  document.querySelectorAll(".drawer-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".drawer-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      activeTab = tab.dataset.tab;
      renderDrawerTab();
    });
  });

  document.getElementById("btn-copy-packet").addEventListener("click", copyPacket);
  document.getElementById("btn-download-packet").addEventListener("click", downloadPacket);

  document.getElementById("btn-rerun").addEventListener("click", runBatch);
}

// ---------------- Fetch Data ----------------
async function loadMetrics() {
  try {
    const res = await fetch("/api/metrics");
    if (!res.ok) throw new Error("Failed to fetch metrics");
    const data = await res.json();
    metricsData = data;
    renderKPIs(data.summary);
  } catch (err) {
    console.error("Error loading metrics:", err);
  }
}

function renderKPIs(s) {
  if (!s) return;
  document.getElementById("kpi-at-risk").textContent = fmtINR(s.amount_at_risk);
  document.getElementById("kpi-disputes-count").textContent = s.total_disputes.toLocaleString();
  
  const netEl = document.getElementById("kpi-net-pnl");
  netEl.textContent = fmtINR(s.net_pnl);
  if (s.net_pnl < 0) netEl.classList.remove("positive");
  
  document.getElementById("kpi-gross-recovered").textContent = fmtINR(s.gross_recovered);
  document.getElementById("kpi-recovery-rate").textContent = fmtPercent(s.recovery_rate);
  document.getElementById("kpi-fight-win-rate").textContent = fmtPercent(s.fight_win_rate);
  
  document.getElementById("kpi-routing-summary").textContent = 
    `${s.fight_count} / ${s.concede_count} / ${s.escalate_count}`;

  document.getElementById("kpi-precision").textContent = fmtPercent(s.model_precision);
  document.getElementById("kpi-prauc").textContent = s.model_pr_auc.toFixed(3);
  document.getElementById("kpi-cutoff").textContent = s.optimal_threshold.toFixed(2);
}

async function loadDisputes() {
  try {
    const res = await fetch("/api/disputes?page_size=5000");
    if (!res.ok) throw new Error("Failed to fetch disputes");
    const data = await res.json();
    allDisputes = data.disputes || [];
    applyFilters();
  } catch (err) {
    console.error("Error loading disputes:", err);
  }
}

// ---------------- Filtering & Sorting ----------------
function applyFilters() {
  const q = document.getElementById("filter-search").value.trim().toLowerCase();
  const decision = document.getElementById("filter-decision").value;
  const network = document.getElementById("filter-network").value;
  const gap = document.getElementById("filter-gap").value;
  const novelty = document.getElementById("filter-novelty").value;

  filteredDisputes = allDisputes.filter((d) => {
    if (decision !== "all" && d.decision !== decision) return false;
    if (network !== "all" && d.network !== network) return false;
    if (gap === "has_gap" && (!d.critical_gaps || d.critical_gaps.length === 0)) return false;
    if (gap === "no_gap" && d.critical_gaps && d.critical_gaps.length > 0) return false;
    if (novelty === "novel" && !d.novelty_flag) return false;

    if (q) {
      const idMatch = d.dispute_id.toLowerCase().includes(q);
      const codeMatch = d.reason_code.toLowerCase().includes(q);
      const netMatch = d.network.toLowerCase().includes(q);
      const decMatch = d.decision.toLowerCase().includes(q);
      if (!idMatch && !codeMatch && !netMatch && !decMatch) return false;
    }
    return true;
  });

  // Sort
  filteredDisputes.sort((a, b) => {
    let va = a[sortColumn];
    let vb = b[sortColumn];
    if (va === undefined || va === null) va = "";
    if (vb === undefined || vb === null) vb = "";

    if (typeof va === "number" && typeof vb === "number") {
      return sortOrder === "asc" ? va - vb : vb - va;
    }
    va = va.toString().toLowerCase();
    vb = vb.toString().toLowerCase();
    if (va < vb) return sortOrder === "asc" ? -1 : 1;
    if (va > vb) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });

  currentPage = 1;
  renderTable();
}

// ---------------- Render Table ----------------
function renderTable() {
  const tbody = document.getElementById("dispute-tbody");
  tbody.innerHTML = "";

  const total = filteredDisputes.length;
  const totalPages = Math.ceil(total / pageSize) || 1;
  if (currentPage > totalPages) currentPage = totalPages;

  const startIdx = (currentPage - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, total);
  const slice = filteredDisputes.slice(startIdx, endIdx);

  document.getElementById("table-record-count").textContent = 
    `Showing ${total === 0 ? 0 : startIdx + 1}–${endIdx} of ${total.toLocaleString()} disputes`;

  document.getElementById("page-indicator").textContent = `Page ${currentPage} of ${totalPages}`;
  document.getElementById("btn-prev").disabled = currentPage <= 1;
  document.getElementById("btn-next").disabled = currentPage >= totalPages;

  if (slice.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="10" style="text-align:center; padding: 36px; color: var(--text-muted);">
      No disputes matching current filter criteria.
    </td>`;
    tbody.appendChild(tr);
    return;
  }

  slice.forEach((row) => {
    const tr = document.createElement("tr");
    if (activeDispute && activeDispute.dispute_id === row.dispute_id) {
      tr.classList.add("row-selected");
    }

    // State Pill
    const stateTag = row.days_remaining <= 0 ? 
      `<span class="tag tag-ok">EXPIRED</span>` : 
      `<span class="tag tag-disputed">DISPUTED</span>`;

    // Decision Tag
    let decTag = "";
    if (row.decision === "fight") decTag = `<span class="tag tag-fight">FIGHT</span>`;
    else if (row.decision === "concede") decTag = `<span class="tag tag-concede">CONCEDE</span>`;
    else decTag = `<span class="tag tag-escalate">ESCALATE</span>`;

    // Evidence Status
    let evTag = "";
    if (row.critical_gaps && row.critical_gaps.length > 0) {
      evTag = `<span class="tag tag-gap">${row.critical_gaps.length} Critical Gap</span>`;
    } else {
      evTag = `<span class="tag tag-ok">${row.artifacts_found} Artifacts</span>`;
    }

    if (row.novelty_flag) {
      evTag += ` <span class="tag tag-novel" title="Out of distribution pattern detected">OOD</span>`;
    }

    // Win prob bar
    const pPct = Math.round(row.p_win_adjusted * 100);
    const pColor = row.p_win_adjusted >= 0.5 ? "#059669" : (row.p_win_adjusted >= 0.25 ? "#d97706" : "#64748b");

    // EV color
    const evColor = row.expected_value > 0 ? "var(--tag-fight-text)" : "var(--text-muted)";

    tr.innerHTML = `
      <td class="cell-id mono">${escapeHTML(row.dispute_id)}</td>
      <td>${stateTag}</td>
      <td><span class="pill-network">${escapeHTML(row.network)}</span></td>
      <td><span class="mono">${escapeHTML(row.reason_code)}</span></td>
      <td class="cell-amount mono">${fmtINR(row.amount_inr)}</td>
      <td class="cell-prob">
        <div class="prob-cell">
          <span class="mono">${pPct}%</span>
          <div class="mini-bar"><div class="mini-bar-fill" style="width: ${pPct}%; background: ${pColor};"></div></div>
        </div>
      </td>
      <td class="cell-ev mono" style="color: ${evColor};">${row.expected_value >= 0 ? "+" : ""}${fmtINR(row.expected_value)}</td>
      <td>${evTag}</td>
      <td>${decTag}</td>
      <td class="mono" style="font-size: 11px; color: ${row.days_remaining <= 5 ? '#dc2626' : 'var(--text-secondary)'};">
        ${row.days_remaining}d left
      </td>
    `;

    tr.addEventListener("click", () => openDrawer(row.dispute_id));
    tbody.appendChild(tr);
  });
}

// ---------------- Side Drawer ----------------
async function openDrawer(disputeId) {
  activeDispute = allDisputes.find((d) => d.dispute_id === disputeId);
  if (!activeDispute) return;

  renderTable(); // Update selected row highlight

  document.getElementById("drawer-id").textContent = activeDispute.dispute_id;
  const decTagEl = document.getElementById("drawer-decision-tag");
  decTagEl.textContent = activeDispute.decision.toUpperCase();
  decTagEl.className = `tag tag-${activeDispute.decision}`;

  document.getElementById("drawer-network-code").textContent = 
    `${activeDispute.network} ${activeDispute.reason_code}`;

  document.getElementById("drawer-backdrop").classList.add("open");
  document.getElementById("drawer-panel").classList.add("open");

  // Show loading in body
  const body = document.getElementById("drawer-body");
  body.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted);">Loading evidence audit...</div>`;

  try {
    const res = await fetch(`/api/packet?id=${encodeURIComponent(disputeId)}`);
    if (!res.ok) throw new Error("Packet fetch failed");
    activePacketData = await res.json();
    renderDrawerTab();
  } catch (err) {
    body.innerHTML = `<div style="padding: 20px; color: #dc2626;">Failed to load packet: ${err.message}</div>`;
  }
}

function closeDrawer() {
  document.getElementById("drawer-backdrop").classList.remove("open");
  document.getElementById("drawer-panel").classList.remove("open");
  activeDispute = null;
  activePacketData = null;
  renderTable();
}

function renderDrawerTab() {
  if (!activePacketData || !activeDispute) return;
  const body = document.getElementById("drawer-body");
  const p = activePacketData;
  const d = activeDispute;
  const r = p.reason_info || {};

  if (activeTab === "overview") {
    const evColor = d.expected_value > 0 ? "var(--tag-fight-text)" : "#dc2626";
    body.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Dispute Economics</div>
        <div class="grid-2col">
          <div class="meta-field">
            <span class="meta-field-label">Disputed Amount</span>
            <span class="meta-field-value mono">${fmtINR(d.amount_inr)}</span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Expected Value (Net)</span>
            <span class="meta-field-value mono" style="color: ${evColor}; font-weight: 600;">
              ${d.expected_value >= 0 ? "+" : ""}${fmtINR(d.expected_value)}
            </span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Breakeven Win Cutoff</span>
            <span class="meta-field-value mono">${fmtPercent(d.breakeven_p)}</span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Model Win Probability</span>
            <span class="meta-field-value mono">${fmtPercent(d.p_win_adjusted)}</span>
          </div>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Routing &amp; Policy Decision</div>
        <div class="grid-2col" style="margin-bottom: 12px;">
          <div class="meta-field">
            <span class="meta-field-label">Policy Action</span>
            <span class="meta-field-value"><span class="tag tag-${d.decision}">${d.decision.toUpperCase()}</span></span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Filing Deadline</span>
            <span class="meta-field-value mono">${d.days_remaining} calendar days</span>
          </div>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">Decision Rationale</span>
          <span class="meta-field-value" style="font-size: 12px; font-weight: 400; color: var(--text-secondary); margin-top: 4px;">
            ${getDecisionRationale(d)}
          </span>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Anomaly &amp; Out-of-Distribution Guard</div>
        <div class="grid-2col">
          <div class="meta-field">
            <span class="meta-field-label">Isolation Forest Flag</span>
            <span class="meta-field-value">
              ${d.novelty_flag ? 
                '<span class="tag tag-novel">Novel / OOD Pattern</span>' : 
                '<span class="tag tag-ok">In-Distribution</span>'}
            </span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Shrinkage Penalty</span>
            <span class="meta-field-value mono">
              ${d.p_win_raw !== d.p_win_adjusted ? 
                `${fmtPercent(d.p_win_raw)} → ${fmtPercent(d.p_win_adjusted)}` : 
                'None (Raw)'}
            </span>
          </div>
        </div>
      </div>
    `;
  } else if (activeTab === "evidence") {
    const arts = p.evidence?.artifacts || {};
    const gaps = p.evidence?.gaps || [];

    let artsHTML = "";
    Object.values(arts).forEach((a) => {
      artsHTML += `
        <div class="evidence-item">
          <svg class="evidence-status-icon check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 6 9 17l-5-5"/>
          </svg>
          <div class="evidence-content">
            <div class="evidence-header-line">
              <span class="evidence-name">${escapeHTML(a.description)}</span>
              <span class="tag tag-ok mono">${escapeHTML(a.artifact_id)}</span>
            </div>
            <div class="evidence-val">${escapeHTML(a.value)}</div>
          </div>
        </div>
      `;
    });

    let gapsHTML = "";
    if (gaps.length === 0) {
      gapsHTML = `<div style="font-size: 12px; color: var(--tag-fight-text); font-weight: 500;">✓ No critical or minor evidence gaps identified. All mandated artifacts present.</div>`;
    } else {
      gaps.forEach((g) => {
        gapsHTML += `
          <div class="evidence-item missing">
            <svg class="evidence-status-icon alert" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <div class="evidence-content">
              <div class="evidence-header-line">
                <span class="evidence-name">${escapeHTML(g.description)}</span>
                <span class="tag ${g.severity === 'critical' ? 'tag-gap' : 'tag-ok'}">${g.severity.toUpperCase()} GAP</span>
              </div>
              <div class="evidence-val" style="color: #b91c1c;">Artifact not located in merchant order records.</div>
            </div>
          </div>
        `;
      });
    }

    body.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Retrieved Artifacts (${Object.keys(arts).length})</div>
        <div class="evidence-list">${artsHTML || '<div style="color:var(--text-muted)">No artifacts retrieved.</div>'}</div>
      </div>
      <div class="drawer-section">
        <div class="drawer-section-title">Disclosed Evidence Gaps (${gaps.length})</div>
        <div class="evidence-list">${gapsHTML}</div>
      </div>
    `;
  } else if (activeTab === "packet") {
    const rawPacket = p.packet_text || "No packet generated.";
    // Highlight citations like [EV-01]
    const highlighted = escapeHTML(rawPacket).replace(
      /\[(EV-[0-9]{2}(?:,\s*EV-[0-9]{2})*|NO-EVIDENCE)\]/g,
      '<span class="packet-citation">[$1]</span>'
    );

    body.innerHTML = `
      <div class="drawer-section" style="padding: 12px;">
        <div class="drawer-section-title" style="margin-bottom: 8px;">
          <span>Generated Representment Packet</span>
          <span class="tag tag-ok">Citation Validated</span>
        </div>
        <pre class="packet-container">${highlighted}</pre>
      </div>
    `;
  } else if (activeTab === "rules") {
    body.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Network Reason Code Specification</div>
        <div class="grid-2col" style="margin-bottom: 12px;">
          <div class="meta-field">
            <span class="meta-field-label">Code / Network</span>
            <span class="meta-field-value mono">${r.network} ${r.code}</span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Category</span>
            <span class="meta-field-value">${r.category}</span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Statutory Deadline</span>
            <span class="meta-field-value mono">${r.deadline_days} days</span>
          </div>
          <div class="meta-field">
            <span class="meta-field-label">Prior Win Rate</span>
            <span class="meta-field-value mono">${fmtPercent(r.base_win_rate)}</span>
          </div>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">Official Title</span>
          <span class="meta-field-value">${r.title}</span>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Required Evidence Artifacts</div>
        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
          ${(r.required || []).map((req) => `• <strong>${req}</strong>: ${p.artifact_definitions?.[req] || req}`).join("<br>")}
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Supporting Evidence Artifacts</div>
        <div style="font-size: 12px; color: var(--text-muted); line-height: 1.6;">
          ${(r.supporting || []).map((sup) => `• <strong>${sup}</strong>: ${p.artifact_definitions?.[sup] || sup}`).join("<br>")}
        </div>
      </div>
    `;
  }
}

function getDecisionRationale(d) {
  if (d.decision === "fight") {
    return `Win probability (${fmtPercent(d.p_win_adjusted)}) exceeds the amount-dependent breakeven threshold (${fmtPercent(d.breakeven_p)}), yielding a net positive expected value of ${fmtINR(d.expected_value)}.`;
  } else if (d.decision === "concede") {
    if (d.critical_gaps && d.critical_gaps.length > 0 && d.p_win_adjusted < 0.5) {
      return `Conceded: Missing network-mandated artifact (${d.critical_gaps.join(", ")}) with win score below 50%. Submitting would burn analyst time without recovery.`;
    }
    return `Win probability (${fmtPercent(d.p_win_adjusted)}) fails to clear the ₹450 representment operational breakeven threshold (${fmtPercent(d.breakeven_p)}).`;
  } else {
    if (d.novelty_flag) {
      return `Escalated: Flagged as out-of-distribution friendly-fraud anomaly by Isolation Forest on ticket size clearing senior review threshold.`;
    }
    return `Escalated: Margin near breakeven on a high-value ticket justify senior manual review before submission.`;
  }
}

function copyPacket() {
  if (!activePacketData || !activePacketData.packet_text) return;
  navigator.clipboard.writeText(activePacketData.packet_text).then(() => {
    const btn = document.getElementById("btn-copy-packet");
    const original = btn.innerHTML;
    btn.innerHTML = `✓ Copied!`;
    setTimeout(() => (btn.innerHTML = original), 1500);
  });
}

function downloadPacket() {
  if (!activePacketData || !activePacketData.packet_text) return;
  const blob = new Blob([activePacketData.packet_text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `representment_${activeDispute.dispute_id}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

async function runBatch() {
  const btn = document.getElementById("btn-rerun");
  btn.disabled = true;
  btn.innerHTML = `Running Batch...`;
  try {
    const res = await fetch("/api/run-batch", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      await loadMetrics();
      await loadDisputes();
      btn.innerHTML = `✓ Evaluated`;
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = `Re-evaluate Batch`;
      }, 1500);
    } else {
      alert("Batch error: " + (data.error || "Unknown"));
      btn.disabled = false;
      btn.innerHTML = `Re-evaluate Batch`;
    }
  } catch (err) {
    alert("Batch execution failed: " + err.message);
    btn.disabled = false;
    btn.innerHTML = `Re-evaluate Batch`;
  }
}

function debounce(fn, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn.apply(this, args), wait);
  };
}

function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
