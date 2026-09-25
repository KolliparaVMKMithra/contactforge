from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "hunter_keys"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_KEYS = 100


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

    if not store.get("keys"):
        from .enrichment import _env_hunter_keys
        env_keys = _env_hunter_keys()
        if env_keys:
            seeded = [
                {
                    "id": f"k_env_{i}",
                    "key": k,
                    "label": f"Env Key {i+1}",
                    "status": "active" if i == 0 else "standby",
                    "creditsAvailable": None,
                    "creditsUsed": None,
                    "resetDate": None,
                    "requestsMade": 0,
                    "error": None,
                }
                for i, k in enumerate(env_keys)
            ]
            store = {"keys": seeded, "activeKeyId": seeded[0]["id"]}
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
    return cleaned
