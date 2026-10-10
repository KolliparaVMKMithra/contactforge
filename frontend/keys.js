const STORAGE_KEY = "contactforge_hunter_keys_v2";
const SEED_VERSION_KEY = "contactforge_seed_version";
const SEED_VERSION = 38;
const CREDITS_POLL_MS = 60000;

let creditsPollTimer = null;
let isCheckingCredits = false;
let keyStoreCache = { keys: [], activeKeyId: null };
let saveTimer = null;
let keysReadyPromise = null;
let activePickerFilter = "all";
let activePickerSearch = "";
let activeTableFilter = "";

function uid() {
  return "k_" + Math.random().toString(36).slice(2, 11);
}

function normalizeStore(store) {
  const keys = Array.isArray(store?.keys) ? store.keys : [];
  return {
    keys,
    activeKeyId: store?.activeKeyId || keys[0]?.id || null,
  };
}

function loadLocalKeyStoreOnly() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (Array.isArray(data.keys)) return normalizeStore(data);
    }
    const legacy = localStorage.getItem("contactforge_hunter_keys_v1");
    if (legacy) {
      const data = JSON.parse(legacy);
      if (Array.isArray(data.keys)) return normalizeStore(data);
    }
  } catch (_) {}
  return { keys: [], activeKeyId: null };
}

function loadKeyStore() {
  return keyStoreCache;
}

async function persistKeyStoreToServer(store) {
  keyStoreCache = normalizeStore(store);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keyStoreCache));
  try {
    const res = await fetch("/api/hunter/keys", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(keyStoreCache),
    });
    if (res.status === 401) {
      window.location.href = "/login";
      return false;
    }
    return res.ok;
  } catch (_) {
    return false;
  }
}

function saveKeyStore(store) {
  keyStoreCache = normalizeStore(store);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keyStoreCache));
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    persistKeyStoreToServer(keyStoreCache);
  }, 300);
}

async function flushKeyStore() {
  clearTimeout(saveTimer);
  return persistKeyStoreToServer(keyStoreCache);
}

async function syncKeysFromServer() {
  try {
    const res = await fetch("/api/hunter/keys", { credentials: "same-origin" });
    if (res.status === 401) {
      window.location.href = "/login";
      return false;
    }
    if (!res.ok) return false;

    const serverStore = normalizeStore(await res.json());
    const localStore = loadLocalKeyStoreOnly();

    const mergedKeys = [...serverStore.keys];
    const serverKeyStrings = new Set(serverStore.keys.map((k) => k.key));

    let localAddedCount = 0;
    for (const lKey of localStore.keys) {
      if (lKey && lKey.key && !serverKeyStrings.has(lKey.key)) {
        mergedKeys.push(lKey);
        serverKeyStrings.add(lKey.key);
        localAddedCount++;
      }
    }

    // Also merge system default keys if not present
    const defaultKeys = window.ContactForgeDefaultKeys || [];
    for (const dKey of defaultKeys) {
      const trimmed = String(dKey).trim();
      if (trimmed.length >= 20 && !serverKeyStrings.has(trimmed)) {
        mergedKeys.push({
          id: uid(),
          key: trimmed,
          label: `Key ${mergedKeys.length + 1}`,
          status: mergedKeys.length === 0 ? "active" : "standby",
          creditsAvailable: null,
          creditsUsed: null,
          resetDate: null,
          requestsMade: 0,
          error: null,
        });
        serverKeyStrings.add(trimmed);
        localAddedCount++;
      }
    }

    const mergedStore = {
      keys: mergedKeys,
      activeKeyId: serverStore.activeKeyId || localStore.activeKeyId || (mergedKeys[0]?.id ?? null),
    };

    keyStoreCache = normalizeStore(mergedStore);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(keyStoreCache));

    if (localAddedCount > 0 || serverStore.keys.length < mergedKeys.length) {
      await persistKeyStoreToServer(keyStoreCache);
    }

    return true;
  } catch (_) {
    const local = loadLocalKeyStoreOnly();
    if (local.keys.length) keyStoreCache = local;
    return false;
  }
}

function maskKey(key) {
  if (!key || key.length < 10) return key || "—";
  return key.slice(0, 6) + "…" + key.slice(-6);
}

function isKeyUsable(key) {
  if (!key) return false;
  if (key.status === "invalid" || key.status === "exhausted") return false;
  if (key.creditsAvailable === 0) return false;
  return true;
}

function getActiveKey(store) {
  if (!store.keys.length) return null;
  const found = store.keys.find((k) => k.id === store.activeKeyId);
  return found || store.keys[0];
}

function autoSelectBestKey(store) {
  const current = getActiveKey(store);
  if (current && isKeyUsable(current)) return current;

  const usable = store.keys.find((k) => isKeyUsable(k));
  if (usable) {
    store.activeKeyId = usable.id;
    store.keys.forEach((k) => {
      if (k.id === usable.id) k.status = "active";
      else if (k.status === "active") k.status = "standby";
    });
    saveKeyStore(store);
    return usable;
  }
  return current;
}

function getActiveKeyIndex(store) {
  const active = autoSelectBestKey(store);
  if (!active) return 0;
  const idx = store.keys.findIndex((k) => k.id === active.id);
  return idx >= 0 ? idx : 0;
}

function getKeyList(store) {
  return store.keys.map((k) => k.key);
}

function getKeyStatesForRequest(store) {
  return store.keys.map((k, index) => ({
    index,
    credits_available: k.creditsAvailable,
    credits_used: k.creditsUsed,
    reset_date: k.resetDate,
    status: k.status,
  }));
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setDockRotationNote(message) {
  const el = document.getElementById("dock-rotation-note");
  if (!el) return;
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = message;
}

function getBadgeInfo(key) {
  if (key.status === "exhausted" || key.creditsAvailable === 0) {
    return { text: "Exhausted", class: "key-badge--danger" };
  }
  if (key.status === "invalid") {
    return { text: "Invalid", class: "key-badge--warn" };
  }
  if (key.creditsAvailable != null) {
    return {
      text: `${key.creditsAvailable} credits left`,
      class: key.creditsAvailable <= 5 ? "key-badge--warn" : "key-badge--ok",
    };
  }
  return {
    text: isCheckingCredits ? "Checking…" : "Ready",
    class: "key-badge--idle",
  };
}

function renderKeyDropdown() {
  const store = loadKeyStore();
  const currentEl = document.getElementById("key-picker-current");
  const countEl = document.getElementById("dock-key-count");
  const dotEl = document.getElementById("active-key-dot");

  autoSelectBestKey(store);
  const active = getActiveKey(store);

  if (countEl) {
    const usable = store.keys.filter((k) => isKeyUsable(k)).length;
    const poolCredits = store.keys.reduce((sum, k) => sum + (k.creditsAvailable ?? 0), 0);
    const poolLabel = poolCredits > 0 ? ` · ${poolCredits} total credits` : "";
    countEl.textContent = `${store.keys.length} keys · ${usable} ready${poolLabel}`;
  }

  if (dotEl) {
    dotEl.className = "key-active-badge-dot";
    if (!active) {
      dotEl.classList.add("is-exhausted");
    } else if (active.status === "exhausted" || active.creditsAvailable === 0) {
      dotEl.classList.add("is-exhausted");
    } else if (active.status === "invalid") {
      dotEl.classList.add("is-invalid");
    }
  }

  if (currentEl) {
    if (!active) {
      currentEl.textContent = "No API keys — click to add";
    } else {
      const idx = store.keys.indexOf(active) + 1;
      const label = active.label || `Key ${idx}`;
      const credits = active.creditsAvailable != null ? `${active.creditsAvailable} left` : "Ready";
      const status = active.status === "exhausted" ? "exhausted" : active.status === "invalid" ? "invalid" : credits;
      currentEl.textContent = `${label} (${maskKey(active.key)}) · ${status}`;
    }
  }

  renderPickerList();
  renderManageKeysTable();
}

function renderPickerList() {
  const listEl = document.getElementById("key-picker-list");
  if (!listEl) return;

  const store = loadKeyStore();
  const active = getActiveKey(store);

  const countAllEl = document.getElementById("count-all");
  const countUsableEl = document.getElementById("count-usable");
  const countExhaustedEl = document.getElementById("count-exhausted");

  const totalAll = store.keys.length;
  const totalUsable = store.keys.filter((k) => isKeyUsable(k)).length;
  const totalExhausted = store.keys.filter((k) => !isKeyUsable(k)).length;

  if (countAllEl) countAllEl.textContent = String(totalAll);
  if (countUsableEl) countUsableEl.textContent = String(totalUsable);
  if (countExhaustedEl) countExhaustedEl.textContent = String(totalExhausted);

  const query = activePickerSearch.trim().toLowerCase();

  const filtered = store.keys.filter((k, idx) => {
    // Filter tab
    if (activePickerFilter === "usable" && !isKeyUsable(k)) return false;
    if (activePickerFilter === "exhausted" && isKeyUsable(k)) return false;

    // Search query
    if (!query) return true;
    const label = (k.label || `Key ${idx + 1}`).toLowerCase();
    const mask = maskKey(k.key).toLowerCase();
    const status = (k.status || "").toLowerCase();
    return label.includes(query) || mask.includes(query) || status.includes(query) || String(idx + 1) === query;
  });

  if (!filtered.length) {
    listEl.innerHTML = `<div class="key-picker-empty">No keys match your filter.</div>`;
    return;
  }

  listEl.innerHTML = filtered
    .map((key) => {
      const idx = store.keys.indexOf(key) + 1;
      const isActive = key.id === active?.id;
      const badge = getBadgeInfo(key);
      const label = key.label || `Key ${idx}`;

      return `
        <button type="button" class="key-picker-item ${isActive ? "is-active" : ""}" data-select-key="${escapeHtml(key.id)}">
          <div class="key-item-left">
            <span class="key-radio-icon"></span>
            <span class="key-item-label">${escapeHtml(label)}</span>
            <span class="key-item-mask">${escapeHtml(maskKey(key.key))}</span>
          </div>
          <span class="key-item-badge ${badge.class}">${escapeHtml(badge.text)}</span>
        </button>
      `;
    })
    .join("");

  listEl.querySelectorAll("[data-select-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-select-key");
      selectActiveKey(id);
      toggleKeyPicker(false);
    });
  });
}

function renderManageKeysTable() {
  const container = document.getElementById("keys-manage-list");
  const countBadge = document.getElementById("table-keys-count");
  if (!container) return;

  const store = loadKeyStore();
  const active = getActiveKey(store);
  if (countBadge) countBadge.textContent = String(store.keys.length);

  const query = activeTableFilter.trim().toLowerCase();
  const filtered = store.keys.filter((k, idx) => {
    if (!query) return true;
    const label = (k.label || `Key ${idx + 1}`).toLowerCase();
    const mask = maskKey(k.key).toLowerCase();
    return label.includes(query) || mask.includes(query) || String(idx + 1) === query;
  });

  if (!filtered.length) {
    container.innerHTML = `<div class="key-picker-empty">No keys found.</div>`;
    return;
  }

  container.innerHTML = filtered
    .map((key) => {
      const idx = store.keys.indexOf(key) + 1;
      const isActive = key.id === active?.id;
      const badge = getBadgeInfo(key);
      const label = key.label || `Key ${idx}`;
      const usedText = key.creditsUsed != null ? ` · ${key.creditsUsed} used today` : "";

      return `
        <div class="manage-key-row ${isActive ? "is-active" : ""}">
          <div class="manage-key-info">
            <div class="manage-key-top">
              <span class="manage-key-label">${escapeHtml(label)}</span>
              <span class="manage-key-mask">${escapeHtml(maskKey(key.key))}</span>
              <span class="key-item-badge ${badge.class}">${escapeHtml(badge.text)}</span>
            </div>
            <div class="manage-key-meta">
              <span>${key.requestsMade || 0} reqs${usedText}</span>
              ${key.resetDate ? `<span>Reset: ${escapeHtml(key.resetDate)}</span>` : ""}
              ${key.error ? `<span class="key-error">· ${escapeHtml(key.error)}</span>` : ""}
            </div>
          </div>
          <div class="manage-key-actions">
            ${!isActive ? `<button type="button" class="btn-make-active" data-action="activate" data-id="${escapeHtml(key.id)}">Set Active</button>` : `<span class="key-picker-active" style="font-weight:600; font-size:0.8rem; color:var(--accent-deep); padding:0 6px;">Active</span>`}
            <button type="button" class="btn-delete-key" data-action="delete" data-id="${escapeHtml(key.id)}" title="Delete key">Delete</button>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll('[data-action="activate"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      selectActiveKey(btn.getAttribute("data-id"));
    });
  });

  container.querySelectorAll('[data-action="delete"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-id");
      removeKeyById(id);
    });
  });
}

function selectActiveKey(keyId) {
  const store = loadKeyStore();
  const selected = store.keys.find((k) => k.id === keyId);
  if (!selected) return;

  store.activeKeyId = selected.id;
  store.keys.forEach((k) => {
    k.status = k.id === selected.id ? "active" : k.status === "active" ? "standby" : k.status;
  });

  saveKeyStore(store);
  updateLiveCreditsDisplay();
  flushKeyStore();
  checkAllKeys({ silent: true });
}

function updateLiveCreditsDisplay() {
  const store = loadKeyStore();
  const active = autoSelectBestKey(store);
  const textEl = document.getElementById("live-credits-text");
  const badgeEl = document.getElementById("live-credits");
  if (!textEl || !badgeEl) return;

  renderKeyDropdown();

  if (!active) {
    textEl.textContent = "Add Hunter API keys in Manage keys below";
    badgeEl.className = "live-credits live-credits--idle";
    return;
  }

  const avail = active.creditsAvailable;
  const used = active.creditsUsed;
  const reset = active.resetDate ? formatDate(active.resetDate) : null;

  if (avail == null && used == null) {
    textEl.textContent = isCheckingCredits
      ? "Fetching live credits from Hunter…"
      : `Using ${active.label || "key"} (${maskKey(active.key)})`;
    badgeEl.className = "live-credits live-credits--loading";
    return;
  }

  const poolCredits = store.keys.reduce((sum, k) => sum + (k.creditsAvailable ?? 0), 0);
  const poolUsed = store.keys.reduce((sum, k) => sum + (k.creditsUsed ?? 0), 0);
  const parts = [
    `Using ${active.label || "key"} (${maskKey(active.key)})`,
    `${avail ?? "?"} credits left`,
  ];
  if (used != null) parts.push(`${used} used today`);
  if (reset) parts.push(`resets ${reset}`);
  if (store.keys.length > 1 && poolCredits > 0) {
    parts.push(`pool: ${poolCredits} left / ${poolUsed} used across ${store.keys.length} keys`);
  }
  textEl.textContent = parts.join(" · ");

  if (avail === 0 || active.status === "exhausted") {
    badgeEl.className = "live-credits live-credits--danger";
  } else if (avail != null && avail <= 5) {
    badgeEl.className = "live-credits live-credits--warn";
  } else {
    badgeEl.className = "live-credits live-credits--ok";
  }
}

function startCreditsPolling() {
  stopCreditsPolling();
  creditsPollTimer = setInterval(() => {
    checkAllKeys({ silent: true });
  }, CREDITS_POLL_MS);
}

function stopCreditsPolling() {
  if (creditsPollTimer) {
    clearInterval(creditsPollTimer);
    creditsPollTimer = null;
  }
}

function addKey(key, label) {
  const store = loadKeyStore();
  const trimmed = key.trim();
  const exists = store.keys.some((k) => k.key === trimmed);
  if (exists) return false;

  const entry = {
    id: uid(),
    key: trimmed,
    label: label?.trim() || `Key ${store.keys.length + 1}`,
    status: store.keys.length === 0 ? "active" : "standby",
    creditsAvailable: null,
    creditsUsed: null,
    resetDate: null,
    requestsMade: 0,
    error: null,
  };
  store.keys.push(entry);
  if (!store.activeKeyId) store.activeKeyId = entry.id;
  saveKeyStore(store);
  updateLiveCreditsDisplay();
  return true;
}

function bulkAddKeys(rawText) {
  const lines = String(rawText || "")
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter((s) => s.length >= 20);

  const store = loadKeyStore();
  let added = 0;
  for (const key of lines) {
    if (store.keys.some((k) => k.key === key)) continue;
    const entry = {
      id: uid(),
      key,
      label: `Key ${store.keys.length + 1}`,
      status: store.keys.length === 0 ? "active" : "standby",
      creditsAvailable: null,
      creditsUsed: null,
      resetDate: null,
      requestsMade: 0,
      error: null,
    };
    store.keys.push(entry);
    if (!store.activeKeyId) store.activeKeyId = entry.id;
    added += 1;
  }
  if (added > 0) saveKeyStore(store);
  updateLiveCreditsDisplay();
  return added;
}

function seedDefaultKeys() {
  const defaults = window.ContactForgeDefaultKeys || [];
  if (!defaults.length) return 0;

  const store = loadKeyStore();
  let added = 0;
  for (const key of defaults) {
    const trimmed = String(key).trim();
    if (trimmed.length < 20 || store.keys.some((k) => k.key === trimmed)) continue;
    const entry = {
      id: uid(),
      key: trimmed,
      label: `Key ${store.keys.length + 1}`,
      status: store.keys.length === 0 ? "active" : "standby",
      creditsAvailable: null,
      creditsUsed: null,
      resetDate: null,
      requestsMade: 0,
      error: null,
    };
    store.keys.push(entry);
    if (!store.activeKeyId) store.activeKeyId = entry.id;
    added += 1;
  }

  if (added > 0) saveKeyStore(store);
  localStorage.setItem(SEED_VERSION_KEY, String(SEED_VERSION));
  return added;
}

function applyKeyInfoToStore(store, infos) {
  (infos || []).forEach((info) => {
    const entry = store.keys[info.index];
    if (!entry) return;
    entry.creditsAvailable = info.credits_available;
    entry.creditsUsed = info.credits_used;
    entry.resetDate = info.reset_date;
    entry.error = info.valid ? null : info.error;
    if (!info.valid) entry.status = "invalid";
    else if (info.credits_available === 0) entry.status = "exhausted";
    else if (entry.id === store.activeKeyId) entry.status = "active";
    else if (entry.status !== "invalid" && entry.status !== "exhausted") entry.status = "standby";
  });
  autoSelectBestKey(store);
  saveKeyStore(store);
}

function updateKeyStatsFromResponse(stats, activeIndex) {
  if (!stats || !stats.length) return;
  const store = loadKeyStore();

  stats.forEach((st) => {
    const entry = store.keys[st.index];
    if (!entry) return;
    entry.status = st.status;
    entry.requestsMade = st.requests_made;
    entry.creditsAvailable = st.credits_available;
    entry.creditsUsed = st.credits_used;
    entry.resetDate = st.reset_date;
    entry.error = st.error;
  });

  if (typeof activeIndex === "number" && store.keys[activeIndex]) {
    store.activeKeyId = store.keys[activeIndex].id;
    store.keys.forEach((k, i) => {
      if (i === activeIndex) k.status = "active";
      else if (k.status === "active") k.status = "standby";
    });
  } else {
    autoSelectBestKey(store);
  }

  const prevActive = store.keys.find((k) => k.id === store.activeKeyId);
  saveKeyStore(store);

  const activeStat = stats.find((s) => s.status === "active") || stats[activeIndex];
  if (activeStat && prevActive) {
    const rotated = stats.some(
      (s) => s.status === "exhausted" && s.index !== activeIndex && s.key_suffix
    );
    if (rotated) {
      setDockRotationNote(
        `Switched to ${prevActive.label || "key"} (${maskKey(prevActive.key)}) — previous key hit daily limit`
      );
      setTimeout(() => setDockRotationNote(""), 8000);
    }
  }

  updateLiveCreditsDisplay();
}

async function checkAllKeys({ silent = false } = {}) {
  const store = loadKeyStore();
  const keys = getKeyList(store);
  if (!keys.length) {
    updateLiveCreditsDisplay();
    return null;
  }

  const btn = document.getElementById("check-keys-btn");
  if (btn) btn.disabled = true;
  isCheckingCredits = true;
  updateLiveCreditsDisplay();

  try {
    const res = await fetch("/api/hunter/check-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ hunter_api_keys: keys }),
    });
    if (res.status === 401) {
      window.location.href = "/login";
      return null;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Check failed");

    applyKeyInfoToStore(store, data.keys);
    await flushKeyStore();
    updateLiveCreditsDisplay();
    return data;
  } catch (err) {
    if (!silent) {
      setDockRotationNote(err.message || "Could not refresh credits");
      setTimeout(() => setDockRotationNote(""), 5000);
    }
    return null;
  } finally {
    isCheckingCredits = false;
    if (btn) btn.disabled = false;
    updateLiveCreditsDisplay();
  }
}

async function removeKeyById(keyId) {
  const store = loadKeyStore();
  if (!store.keys.some((k) => k.id === keyId)) return;

  store.keys = store.keys.filter((k) => k.id !== keyId);
  if (store.activeKeyId === keyId) {
    const next = store.keys.find((k) => isKeyUsable(k)) || store.keys[0];
    store.activeKeyId = next?.id || null;
    if (next) next.status = "active";
  }

  saveKeyStore(store);
  updateLiveCreditsDisplay();
  const savedOk = await flushKeyStore();
  setDockRotationNote(savedOk ? "Key deleted and synced across all devices." : "Key deleted locally.");
  if (store.keys.length) checkAllKeys({ silent: true });
  setTimeout(() => setDockRotationNote(""), 5000);
}

async function cleanExhaustedKeys() {
  const store = loadKeyStore();
  const exhaustedKeys = store.keys.filter((k) => !isKeyUsable(k));
  if (!exhaustedKeys.length) {
    alert("No exhausted or invalid keys found to clean.");
    return;
  }

  const confirmMsg = `Are you sure you want to remove ${exhaustedKeys.length} exhausted / invalid key(s) from your account?`;
  if (!confirm(confirmMsg)) return;

  store.keys = store.keys.filter((k) => isKeyUsable(k));
  autoSelectBestKey(store);
  saveKeyStore(store);
  updateLiveCreditsDisplay();
  await flushKeyStore();
  setDockRotationNote(`Cleaned ${exhaustedKeys.length} exhausted keys.`);
  setTimeout(() => setDockRotationNote(""), 5000);
}

function toggleKeyPicker(forceOpen) {
  const popup = document.getElementById("key-picker-popup");
  const trigger = document.getElementById("key-dropdown-trigger");
  if (!popup || !trigger) return;

  const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : popup.hidden;
  popup.hidden = !shouldOpen;
  trigger.setAttribute("aria-expanded", shouldOpen ? "true" : "false");

  if (shouldOpen) {
    const searchInput = document.getElementById("key-picker-search");
    searchInput?.focus();
    renderPickerList();
  }
}

function bindDockControls() {
  const pickerTrigger = document.getElementById("key-dropdown-trigger");
  const pickerPopup = document.getElementById("key-picker-popup");
  const pickerClose = document.getElementById("key-picker-close");
  const pickerSearch = document.getElementById("key-picker-search");
  const filterTabs = document.querySelectorAll(".key-filter-tab");
  const btnOpenManage = document.getElementById("btn-open-manage-panel");
  const tableSearch = document.getElementById("table-keys-filter");
  const cleanExhaustedBtn = document.getElementById("clean-exhausted-btn");

  pickerTrigger?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleKeyPicker();
  });

  pickerClose?.addEventListener("click", () => {
    toggleKeyPicker(false);
  });

  pickerSearch?.addEventListener("input", (e) => {
    activePickerSearch = e.target.value;
    renderPickerList();
  });

  filterTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      filterTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      activePickerFilter = tab.dataset.filter || "all";
      renderPickerList();
    });
  });

  btnOpenManage?.addEventListener("click", () => {
    toggleKeyPicker(false);
    const panel = document.getElementById("api-dock-panel");
    const toggleBtn = document.getElementById("dock-toggle-btn");
    if (panel) panel.hidden = false;
    toggleBtn?.setAttribute("aria-expanded", "true");
    toggleBtn?.textContent && (toggleBtn.textContent = "Hide keys");
    document.body.classList.add("dock-expanded");
  });

  tableSearch?.addEventListener("input", (e) => {
    activeTableFilter = e.target.value;
    renderManageKeysTable();
  });

  cleanExhaustedBtn?.addEventListener("click", () => {
    cleanExhaustedKeys();
  });

  document.addEventListener("click", (e) => {
    if (pickerPopup && !pickerPopup.hidden) {
      if (!pickerPopup.contains(e.target) && !pickerTrigger?.contains(e.target)) {
        toggleKeyPicker(false);
      }
    }
  });

  const toggleBtn = document.getElementById("dock-toggle-btn");
  const panel = document.getElementById("api-dock-panel");
  toggleBtn?.addEventListener("click", () => {
    const open = panel?.hidden !== false;
    if (panel) panel.hidden = !open;
    toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
    toggleBtn.textContent = open ? "Hide keys" : "Manage keys";
    document.body.classList.toggle("dock-expanded", open);
    if (open) {
      toggleKeyPicker(false);
      renderManageKeysTable();
    }
  });

  document.getElementById("add-key-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const keyInput = document.getElementById("new-key-input");
    const labelInput = document.getElementById("new-key-label");
    const key = keyInput?.value.trim();
    const label = labelInput?.value.trim();
    if (!key) return;

    if (addKey(key, label)) {
      keyInput.value = "";
      if (labelInput) labelInput.value = "";
      const savedOk = await flushKeyStore();
      setDockRotationNote(savedOk ? "Key saved and synced to your server account!" : "Key saved locally");
      checkAllKeys({ silent: true });
      setTimeout(() => setDockRotationNote(""), 5000);
    } else {
      setDockRotationNote("This API key is already in your list.");
      setTimeout(() => setDockRotationNote(""), 4000);
    }
  });

  document.getElementById("bulk-key-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const textarea = document.getElementById("bulk-keys-input");
    const added = bulkAddKeys(textarea?.value || "");
    if (textarea) textarea.value = "";
    if (added > 0) {
      const savedOk = await flushKeyStore();
      setDockRotationNote(`Imported ${added} API key${added === 1 ? "" : "s"} — synced across devices`);
      checkAllKeys({ silent: true });
      setTimeout(() => setDockRotationNote(""), 5000);
    } else {
      setDockRotationNote("No new keys found to import");
      setTimeout(() => setDockRotationNote(""), 4000);
    }
  });

  document.getElementById("check-keys-btn")?.addEventListener("click", () => {
    checkAllKeys({ silent: false });
  });
}

async function initKeys() {
  bindDockControls();
  setDockRotationNote("Loading your API keys…");

  await syncKeysFromServer();

  if (!keyStoreCache.keys.length) {
    const seeded = seedDefaultKeys();
    if (seeded > 0) {
      await flushKeyStore();
      setDockRotationNote(`Loaded ${seeded} API keys — checking live daily limits…`);
    } else {
      setDockRotationNote("");
    }
  } else {
    setDockRotationNote("");
  }

  updateLiveCreditsDisplay();
  await checkAllKeys({ silent: true });
  startCreditsPolling();
  return true;
}

function whenKeysReady() {
  if (!keysReadyPromise) keysReadyPromise = initKeys();
  return keysReadyPromise;
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    keysReadyPromise = initKeys();
  });
} else {
  keysReadyPromise = initKeys();
}

window.ContactForgeKeys = {
  loadKeyStore,
  getKeyList,
  getActiveKeyIndex,
  getKeyStatesForRequest,
  updateKeyStatsFromResponse,
  checkAllKeys,
  updateLiveCreditsDisplay,
  startCreditsPolling,
  bulkAddKeys,
  whenReady: whenKeysReady,
  flushKeyStore,
};
