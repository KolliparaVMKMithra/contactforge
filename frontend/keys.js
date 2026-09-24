const STORAGE_KEY = "contactforge_hunter_keys_v2";
const SEED_VERSION_KEY = "contactforge_seed_version";
const SEED_VERSION = 36;
const CREDITS_POLL_MS = 30000;

let creditsPollTimer = null;
let isCheckingCredits = false;

function uid() {
  return "k_" + Math.random().toString(36).slice(2, 11);
}

function loadKeyStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (Array.isArray(data.keys)) return data;
    }
    const legacy = localStorage.getItem("contactforge_hunter_keys_v1");
    if (legacy) {
      const data = JSON.parse(legacy);
      if (Array.isArray(data.keys)) {
        saveKeyStore(data);
        return data;
      }
    }
  } catch (_) {}
  return { keys: [], activeKeyId: null };
}

function saveKeyStore(store) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
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

function renderKeyDropdown() {
  const store = loadKeyStore();
  const dropdown = document.getElementById("key-dropdown");
  const countEl = document.getElementById("dock-key-count");
  if (!dropdown) return;

  autoSelectBestKey(store);
  const active = getActiveKey(store);

  if (countEl) {
    const usable = store.keys.filter((k) => isKeyUsable(k)).length;
    const poolCredits = store.keys.reduce((sum, k) => sum + (k.creditsAvailable ?? 0), 0);
    const poolLabel = poolCredits > 0 ? ` · ${poolCredits} total credits` : "";
    countEl.textContent = `${store.keys.length} keys · ${usable} available${poolLabel}`;
  }

  if (!store.keys.length) {
    dropdown.innerHTML = `<option value="">No keys — open Manage keys</option>`;
    dropdown.disabled = true;
    return;
  }

  dropdown.disabled = false;
  dropdown.innerHTML = store.keys
    .map((k, index) => {
      const credits =
        k.creditsAvailable != null ? `${k.creditsAvailable} left` : isCheckingCredits ? "…" : "?";
      const status =
        k.status === "exhausted"
          ? "exhausted"
          : k.status === "invalid"
            ? "invalid"
            : credits;
      const label = `${k.label || `Key ${index + 1}`} (${maskKey(k.key)}) — ${status}`;
      return `<option value="${k.id}" ${k.id === active?.id ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
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
  const exists = store.keys.some((k) => k.key === key);
  if (exists) return false;

  const entry = {
    id: uid(),
    key,
    label: label || `Key ${store.keys.length + 1}`,
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

function bindDockControls() {
  const dropdown = document.getElementById("key-dropdown");
  dropdown?.addEventListener("change", () => {
    const store = loadKeyStore();
    const id = dropdown.value;
    if (!id) return;
    store.activeKeyId = id;
    store.keys.forEach((k) => {
      if (k.id === id) k.status = "active";
      else if (k.status === "active") k.status = "standby";
    });
    saveKeyStore(store);
    updateLiveCreditsDisplay();
    checkAllKeys({ silent: true });
  });

  const toggleBtn = document.getElementById("dock-toggle-btn");
  const panel = document.getElementById("api-dock-panel");
  toggleBtn?.addEventListener("click", () => {
    const open = panel?.hidden !== false;
    if (panel) panel.hidden = !open;
    toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
    toggleBtn.textContent = open ? "Hide keys" : "Manage keys";
    document.body.classList.toggle("dock-expanded", open);
  });

  document.getElementById("add-key-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const keyInput = document.getElementById("new-key-input");
    const labelInput = document.getElementById("new-key-label");
    const key = keyInput?.value.trim();
    const label = labelInput?.value.trim();
    if (!key) return;
    if (addKey(key, label)) {
      keyInput.value = "";
      if (labelInput) labelInput.value = "";
      checkAllKeys({ silent: true });
    }
  });

  document.getElementById("bulk-key-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const textarea = document.getElementById("bulk-keys-input");
    const added = bulkAddKeys(textarea?.value || "");
    if (textarea) textarea.value = "";
    if (added > 0) {
      setDockRotationNote(`Imported ${added} API key${added === 1 ? "" : "s"}`);
      checkAllKeys({ silent: true });
      setTimeout(() => setDockRotationNote(""), 4000);
    } else {
      setDockRotationNote("No new keys found to import");
      setTimeout(() => setDockRotationNote(""), 4000);
    }
  });

  document.getElementById("check-keys-btn")?.addEventListener("click", () => {
    checkAllKeys({ silent: false });
  });
}

function initKeys() {
  const seeded = seedDefaultKeys();
  bindDockControls();
  updateLiveCreditsDisplay();
  if (seeded > 0) {
    setDockRotationNote(`Loaded ${seeded} API keys — checking live daily limits…`);
  }
  checkAllKeys({ silent: true }).then(() => {
    if (seeded > 0) setTimeout(() => setDockRotationNote(""), 5000);
  });
  startCreditsPolling();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initKeys);
} else {
  initKeys();
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
};
