from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "hunter_keys"

MAX_KEYS = 100

DEFAULT_KEYS_FILE = ROOT / "backend" / "default_keys.json"
FRONTEND_DEFAULT_KEYS = ROOT / "frontend" / "default-keys.js"

# ---------------------------------------------------------------------------
# Database backend (PostgreSQL via DATABASE_URL, falls back to local files)
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "")

# psycopg2 is only imported when DATABASE_URL is set
_pg_available: bool | None = None

# Cache the table-creation so we don't run it on every request
_table_ensured = False


def _use_postgres() -> bool:
    global _pg_available
    if not DATABASE_URL:
        return False
    if _pg_available is None:
        try:
            import psycopg2  # noqa: F401
            _pg_available = True
        except ImportError:
            _pg_available = False
    return bool(_pg_available)


def _pg_connect():
    import psycopg2
    url = DATABASE_URL
    # psycopg2 needs postgresql:// not postgres://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    # Supabase (and most hosted PG) require SSL — add sslmode if missing
    if "supabase" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"

    return psycopg2.connect(url)


def _ensure_pg_table() -> None:
    """Create the key_store table if it doesn't exist (runs once per process)."""
    global _table_ensured
    if _table_ensured:
        return
    conn = _pg_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS key_store (
                        email_hash TEXT PRIMARY KEY,
                        store_json TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
        _table_ensured = True
    finally:
        conn.close()


def _pg_load(email: str) -> dict | None:
    _ensure_pg_table()
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    conn = _pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT store_json FROM key_store WHERE email_hash = %s",
                (digest,),
            )
            row = cur.fetchone()
            if row:
                data = json.loads(row[0])
                if isinstance(data, dict) and isinstance(data.get("keys"), list):
                    return {
                        "keys": data.get("keys", [])[:MAX_KEYS],
                        "activeKeyId": data.get("activeKeyId"),
                    }
    finally:
        conn.close()
    return None


def _pg_save(email: str, store: dict) -> None:
    _ensure_pg_table()
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    conn = _pg_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO key_store (email_hash, store_json, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (email_hash) DO UPDATE
                        SET store_json = EXCLUDED.store_json,
                            updated_at = NOW()
                """, (digest, json.dumps(store)))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Local-file backend (used in dev when no DATABASE_URL is set)
# ---------------------------------------------------------------------------

def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _user_path(email: str) -> Path:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return DATA_DIR / f"{digest}.json"


def _file_load(email: str) -> dict | None:
    _ensure_data_dir()
    path = _user_path(email)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("keys"), list):
                return {
                    "keys": data.get("keys", [])[:MAX_KEYS],
                    "activeKeyId": data.get("activeKeyId"),
                }
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _file_save(email: str, store: dict) -> None:
    _ensure_data_dir()
    path = _user_path(email)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Default / system keys
# ---------------------------------------------------------------------------

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
        js_content = (
            "// Default Hunter API keys synced from server\n"
            "window.ContactForgeDefaultKeys = "
            + json.dumps(keys, indent=2)
            + ";\n"
        )
        FRONTEND_DEFAULT_KEYS.write_text(js_content, encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _empty_store() -> dict:
    return {"keys": [], "activeKeyId": None}


def load_user_keys(email: str) -> dict:
    # Load from the appropriate backend
    if _use_postgres():
        store = _pg_load(email)
    else:
        store = _file_load(email)

    if store is None:
        store = _empty_store()

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

    if _use_postgres():
        _pg_save(email, cleaned)
    else:
        _file_save(email, cleaned)

    # Keep default files updated with all known keys
    all_key_strings = [k["key"].strip() for k in keys if isinstance(k, dict) and k.get("key")]
    if all_key_strings:
        _sync_default_files(all_key_strings)

    return cleaned
