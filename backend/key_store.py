from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "hunter_keys"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_KEYS = 100


DEFAULT_KEYS_FILE = ROOT / "backend" / "default_keys.json"
FRONTEND_DEFAULT_KEYS = ROOT / "frontend" / "default-keys.js"


def _load_system_default_keys() -> list[str]:
    keys: list[str] = []
    if DEFAULT_KEYS_FILE.exists():
        try:
            data = json.loads(DEFAULT_KEYS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for k in data:
                    k_str = str(k).strip()
                    if len(k_str) >= 20 and k_str not in keys:
                        keys.append(k_str)
        except Exception:
            pass

    from .enrichment import _env_hunter_keys
    for k in _env_hunter_keys():
        if k and k not in keys:
            keys.append(k)

    return keys


def _sync_default_files(keys: list[str]) -> None:
    try:
        DEFAULT_KEYS_FILE.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        js_content = "// Default Hunter API keys synced from server\nwindow.ContactForgeDefaultKeys = " + json.dumps(keys, indent=2) + ";\n"
        FRONTEND_DEFAULT_KEYS.write_text(js_content, encoding="utf-8")
    except Exception:
        pass


def _user_path(email: str) -> Path:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return DATA_DIR / f"{digest}.json"


def _empty_store() -> dict:
    return {"keys": [], "activeKeyId": None}


def load_user_keys(email: str) -> dict:
    path = _user_path(email)
    store = _empty_store()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("keys"), list):
                store = {
                    "keys": data.get("keys", [])[:MAX_KEYS],
                    "activeKeyId": data.get("activeKeyId"),
                }
        except (json.JSONDecodeError, OSError):
            pass

    default_keys = _load_system_default_keys()

    if not store.get("keys"):
        if default_keys:
            seeded = [
                {
                    "id": f"k_{i+1}",
                    "key": k,
                    "label": f"Key {i+1}",
                    "status": "active" if i == 0 else "standby",
                    "creditsAvailable": None,
                    "creditsUsed": None,
                    "resetDate": None,
                    "requestsMade": 0,
                    "error": None,
                }
                for i, k in enumerate(default_keys[:MAX_KEYS])
            ]
            store = {"keys": seeded, "activeKeyId": seeded[0]["id"] if seeded else None}
            try:
                save_user_keys(email, store)
            except Exception:
                pass
    else:
        # Merge any system default keys not already in the store
        existing_keys = {k["key"] for k in store["keys"] if isinstance(k, dict) and k.get("key")}
        added = False
        for k in default_keys:
            if k not in existing_keys and len(store["keys"]) < MAX_KEYS:
                store["keys"].append({
                    "id": f"k_{len(store['keys'])+1}",
                    "key": k,
                    "label": f"Key {len(store['keys'])+1}",
                    "status": "standby",
                    "creditsAvailable": None,
                    "creditsUsed": None,
                    "resetDate": None,
                    "requestsMade": 0,
                    "error": None,
                })
                existing_keys.add(k)
                added = True
        if added:
            try:
                save_user_keys(email, store)
            except Exception:
                pass

    return store


def save_user_keys(email: str, store: dict) -> dict:
    keys = store.get("keys") or []
    if not isinstance(keys, list):
        raise ValueError("keys must be a list")
    if len(keys) > MAX_KEYS:
        raise ValueError(f"Maximum {MAX_KEYS} API keys allowed")

    cleaned = {
        "keys": keys,
        "activeKeyId": store.get("activeKeyId"),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _user_path(email)
    path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")

    # Keep default files updated with all known keys
    all_key_strings = [k["key"].strip() for k in keys if isinstance(k, dict) and k.get("key")]
    if all_key_strings:
        _sync_default_files(all_key_strings)

    return cleaned
