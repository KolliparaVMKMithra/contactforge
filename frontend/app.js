let form;
let companyInput;
let maxInput;
let searchBtn;
let btnLabel;
let btnSpinner;
let statusEl;
let summaryEl;
let resultsEl;
let resultsBody;
let filterInput;
let emptyFilter;
let exportBtn;
let exportBtnResults;
let websiteLink;
let candidatesSection;
let candidatesQueryEl;
let candidatesGrid;

let latestContacts = [];
let latestCompany = "";
let xlsxReady = false;

function redirectToLogin() {
  window.location.href = "/login";
}

function handleUnauthorized(res) {
  if (res.status === 401) {
    redirectToLogin();
    return true;
  }
  return false;
}

function setLoading(loading) {
  if (!searchBtn || !btnLabel || !btnSpinner) return;
  searchBtn.disabled = loading;
  btnSpinner.hidden = !loading;
  btnLabel.textContent = loading ? "Searching…" : "Search HR contacts";
}

function showStatus(message, type = "loading") {
  if (!statusEl) return;
  statusEl.hidden = false;
  statusEl.className = `status ${type}`;
  statusEl.textContent = message;
}

function hideStatus() {
  if (statusEl) statusEl.hidden = true;
}

function hideCandidates() {
  if (candidatesSection) candidatesSection.hidden = true;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderRows(contacts) {
  if (!resultsBody || !resultsEl || !emptyFilter || !filterInput) return;

  const q = filterInput.value.trim().toLowerCase();
  const filtered = !q
    ? contacts
    : contacts.filter((c) => {
        const blob = [c.name, c.company, c.email, c.designation, c.source]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return blob.includes(q);
      });

  resultsBody.innerHTML = filtered
    .map((c) => {
      const email = c.email
        ? `<a href="mailto:${escapeHtml(c.email)}">${escapeHtml(c.email)}</a>`
        : "—";
      const conf = typeof c.confidence === "number" ? Math.round(c.confidence * 100) + "%" : "—";
      const sourceLabel = c.source || "hunter.io";
      return `
        <tr>
          <td>${escapeHtml(c.name || "—")}</td>
          <td>${escapeHtml(c.company || "—")}</td>
          <td class="email">${email}</td>
          <td>${escapeHtml(c.designation || "—")}</td>
          <td><span class="confidence">${conf}</span></td>
          <td>${escapeHtml(sourceLabel)}</td>
        </tr>
      `;
    })
    .join("");

  emptyFilter.hidden = filtered.length > 0 || contacts.length === 0;
  resultsEl.hidden = contacts.length === 0;
}

function renderSummary(data) {
  if (!summaryEl) return;
  summaryEl.hidden = false;
  document.getElementById("summary-company").textContent = data.company_name || "Results";
  document.getElementById("summary-message").textContent = data.message || "";
  document.getElementById("stat-count").textContent = String(data.contacts?.length || 0);
  document.getElementById("stat-domain").textContent = data.domain || "—";

  if (data.website && websiteLink) {
    websiteLink.hidden = false;
    websiteLink.href = data.website;
  } else if (websiteLink) {
    websiteLink.hidden = true;
  }

  const hasContacts = !!(data.contacts && data.contacts.length);
  if (exportBtn) exportBtn.hidden = !hasContacts;
  if (exportBtnResults) exportBtnResults.hidden = !hasContacts;

  if (data.hunter_key_stats?.length) {
    window.ContactForgeKeys?.updateKeyStatsFromResponse(
      data.hunter_key_stats,
      data.active_key_index
    );
  }
  window.ContactForgeKeys?.updateLiveCreditsDisplay?.();
}

function loadXlsx() {
  return new Promise((resolve, reject) => {
    if (typeof XLSX !== "undefined") {
      xlsxReady = true;
      resolve();
      return;
    }
    if (xlsxReady) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";
    script.async = true;
    script.onload = () => {
      xlsxReady = true;
      resolve();
    };
    script.onerror = () => reject(new Error("Could not load Excel library"));
    document.head.appendChild(script);
  });
}

async function downloadExcel(contacts) {
  if (!contacts.length) return;
  try {
    await loadXlsx();
  } catch (_) {
    showStatus("Excel library failed to load. Check your internet and try again.", "error");
    return;
  }

  const rows = contacts.map((c) => ({
    Name: c.name || "",
    "Company name": c.company || "",
    Email: c.email || "",
  }));

  const worksheet = XLSX.utils.json_to_sheet(rows, {
    header: ["Name", "Company name", "Email"],
  });
  worksheet["!cols"] = [{ wch: 28 }, { wch: 24 }, { wch: 36 }];

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Contacts");

  const filename = `${(latestCompany || "contacts").replace(/\s+/g, "_").toLowerCase()}_contacts.xlsx`;
  XLSX.writeFile(workbook, filename);
}

function bindExport(btn) {
  if (!btn) return;
  btn.addEventListener("click", () => downloadExcel(latestContacts));
}

async function resolveCompanyCandidates(query) {
  setLoading(true);
  hideCandidates();
  if (summaryEl) summaryEl.hidden = true;
  if (resultsEl) resultsEl.hidden = true;
  showStatus(`Searching Google & web for companies matching "${query}"…`, "loading");

  try {
    const res = await fetch("/api/company/candidates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ query }),
    });

    if (handleUnauthorized(res)) return [];
    if (!res.ok) return [];

    const data = await res.json();
    return data.candidates || [];
  } catch (_) {
    return [];
  } finally {
    setLoading(false);
  }
}

function renderCandidates(query, candidates) {
  if (!candidatesSection || !candidatesGrid) return;

  if (candidatesQueryEl) candidatesQueryEl.textContent = query;
  candidatesSection.hidden = false;

  candidatesGrid.innerHTML = candidates
    .map((c, i) => {
      const logoUrl = c.logo || `https://www.google.com/s2/favicons?domain=${c.domain}&sz=128`;
      return `
        <div class="candidate-card">
          <div class="candidate-card-header">
            <img
              src="${escapeHtml(logoUrl)}"
              alt="${escapeHtml(c.company_name)} logo"
              class="candidate-logo"
              onerror="this.onerror=null; this.src='https://www.google.com/s2/favicons?domain=${escapeHtml(c.domain)}&sz=128';"
            />
            <div class="candidate-card-info">
              <h4 class="candidate-name">${escapeHtml(c.company_name)}</h4>
              <a href="${escapeHtml(c.website)}" target="_blank" rel="noopener" class="candidate-domain">${escapeHtml(c.domain)} ↗</a>
            </div>
          </div>
          <p class="candidate-desc">${escapeHtml(c.description || "Company web presence")}</p>
          <button type="button" class="btn-select-candidate" data-index="${i}">
            <span>Find HR Contacts</span>
            <span class="arrow">→</span>
          </button>
        </div>
      `;
    })
    .join("");

  candidatesGrid.querySelectorAll(".btn-select-candidate").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-index"));
      const selected = candidates[idx];
      if (selected) {
        fetchHRContactsForCompany(selected.company_name, selected.domain);
      }
    });
  });
}

async function fetchHRContactsForCompany(companyName, targetDomain) {
  hideCandidates();
  setLoading(true);
  if (summaryEl) summaryEl.hidden = true;
  if (resultsEl) resultsEl.hidden = true;

  const domainLabel = targetDomain ? ` (${targetDomain})` : "";
  showStatus(`Fetching HR & leadership contacts for ${companyName}${domainLabel} via Hunter.io…`, "loading");

  await window.ContactForgeKeys?.whenReady?.();
  const store = window.ContactForgeKeys?.loadKeyStore() || { keys: [] };
  const keys = window.ContactForgeKeys?.getKeyList(store) || [];
  const activeIndex = window.ContactForgeKeys?.getActiveKeyIndex(store) || 0;
  const keyStates = window.ContactForgeKeys?.getKeyStatesForRequest(store) || [];

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        company_name: companyName,
        domain: targetDomain || null,
        max_results: Number(maxInput?.value) || 50,
        hunter_api_keys: keys,
        active_key_index: activeIndex,
        key_states: keyStates,
      }),
    });

    if (handleUnauthorized(res)) return;

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Search failed");
    }

    latestContacts = data.contacts || [];
    latestCompany = data.company_name || companyName;
    hideStatus();
    renderSummary(data);
    renderRows(latestContacts);
    window.ContactForgeKeys?.checkAllKeys?.({ silent: true });

    if (!latestContacts.length) {
      showStatus(data.message || "No HR contacts found for this company.", "error");
    }
  } catch (err) {
    showStatus(err.message || "Something went wrong.", "error");
  } finally {
    setLoading(false);
  }
}

async function handleSearchSubmit() {
  const company = companyInput?.value.trim();
  if (!company) return;

  await window.ContactForgeKeys?.whenReady?.();

  const store = window.ContactForgeKeys?.loadKeyStore() || { keys: [] };
  const keys = window.ContactForgeKeys?.getKeyList(store) || [];

  if (!keys.length) {
    showStatus("Add at least one Hunter.io API key in Manage keys at the bottom.", "error");
    const panel = document.getElementById("api-dock-panel");
    if (panel) panel.hidden = false;
    return;
  }

  const candidates = await resolveCompanyCandidates(company);
  if (candidates && candidates.length > 0) {
    hideStatus();
    renderCandidates(company, candidates);
  } else {
    // If no candidates found from web search, run direct search
    fetchHRContactsForCompany(company, null);
  }
}

function initApp() {
  form = document.getElementById("search-form");
  companyInput = document.getElementById("company");
  maxInput = document.getElementById("max-results");
  searchBtn = document.getElementById("search-btn");
  btnLabel = searchBtn?.querySelector(".btn-label");
  btnSpinner = searchBtn?.querySelector(".btn-spinner");
  statusEl = document.getElementById("status");
  summaryEl = document.getElementById("summary");
  resultsEl = document.getElementById("results");
  resultsBody = document.getElementById("results-body");
  filterInput = document.getElementById("filter");
  emptyFilter = document.getElementById("empty-filter");
  exportBtn = document.getElementById("export-excel");
  exportBtnResults = document.getElementById("export-excel-results");
  websiteLink = document.getElementById("website-link");
  candidatesSection = document.getElementById("company-candidates");
  candidatesQueryEl = document.getElementById("candidates-query");
  candidatesGrid = document.getElementById("candidates-grid");

  if (!form || !companyInput) {
    console.error("ContactForge: search form not found");
    return;
  }

  bindExport(exportBtn);
  bindExport(exportBtnResults);

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try {
        await fetch("/api/auth/logout", {
          method: "POST",
          credentials: "same-origin",
        });
      } catch (_) {}
      redirectToLogin();
    });
  }

  if (filterInput) {
    filterInput.addEventListener("input", () => renderRows(latestContacts));
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    handleSearchSubmit();
  });

  companyInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleSearchSubmit();
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
