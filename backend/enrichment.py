from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .hunter_pool import HunterKeyPool, fetch_hunter_account, prime_pool_with_usable_key
from .resolver import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

# Hunter queries focused on HR / leadership / senior talent teams
HUNTER_HR_QUERIES: list[dict] = [
    {"department": "hr"},
    {"department": "hr", "seniority": "executive"},
    {"department": "hr", "seniority": "senior"},
    {"department": "management", "seniority": "executive"},
    {"seniority": "executive"},
    {"seniority": "senior"},
]

# Broader queries when HR results are not enough
HUNTER_FALLBACK_QUERIES: list[dict] = [
    {},  # all departments
    {"department": "executive"},
    {"department": "management"},
    {"department": "it"},
    {"department": "sales"},
    {"department": "marketing"},
    {"department": "finance"},
    {"department": "operations"},
    {"seniority": "executive"},
    {"seniority": "senior"},
    {"seniority": "junior"},
]

# Run fallback if HR pass finds fewer than this many contacts
HR_MIN_BEFORE_FALLBACK = 5

HR_TITLE_PATTERN = re.compile(
    r"(?i)\b("
    r"human\s+resources?|hr\b|people\s+ops|people\s+operations|people\s+team|"
    r"talent\s+acquisition|talent\s+partner|talent\s+advisor|talent\s+lead|"
    r"recruit(?:er|ing|ment)?|staffing|hiring|headhunt|"
    r"chief\s+people|chief\s+human|cpo\b|"
    r"vp\s+(?:of\s+)?(?:people|hr|human|talent)|"
    r"vice\s+president\s+(?:of\s+)?(?:people|hr|human|talent)|"
    r"head\s+of\s+(?:people|hr|human|talent|recruiting|recruitment)|"
    r"director\s+(?:of\s+)?(?:people|hr|human|talent|recruiting)|"
    r"hr\s+(?:manager|director|lead|partner|bp|business\s+partner)|"
    r"hrbp|people\s+(?:manager|director|partner|lead)|"
    r"founder|co-?founder|"
    r"ceo\b|cto\b|cfo\b|coo\b|chief\s+(?:executive|technology|financial|operating)|"
    r"president\b|managing\s+director|"
    r"senior\s+(?:hr|recruiter|talent|people)"
    r")\b"
)


def _env_hunter_keys() -> list[str]:
    keys: list[str] = []
    for var in ("HUNTER_API_KEY", "HUNTER_API_KEYS", "HUNTER_KEYS"):
        raw = os.getenv(var, "").strip()
        if raw:
            for k in re.split(r"[\n,;]+", raw):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)
    return keys


def enrichment_status() -> dict:
    keys = _env_hunter_keys()
    return {
        "hunter_configured": True,
        "hunter_key_count": len(keys),
        "hunter_keys_source": "browser" if not keys else "browser+env",
        "source": "hunter.io",
        "focus": "HR, talent acquisition, leadership",
    }


def is_hr_relevant_contact(person: dict) -> bool:
    """Keep HR/TA/leadership/senior people contacts."""
    title = (person.get("designation") or person.get("position") or "") or ""
    dept = (person.get("department") or "") or ""
    seniority = (person.get("seniority") or "") or ""
    blob = f"{title} {dept} {seniority}".strip()
    if not blob:
        return True  # keep if Hunter didn't tag title — domain HR query already scoped
    if HR_TITLE_PATTERN.search(blob):
        return True
    if dept.lower() == "hr":
        return True
    if seniority.lower() in ("executive", "senior") and any(
        x in title.lower()
        for x in ("manager", "director", "head", "lead", "partner", "chief", "vp", "president")
    ):
        return True
    return False


def _row_to_person(row: dict, company: str, hr_only: bool = True) -> dict | None:
    first = (row.get("first_name") or "").strip()
    last = (row.get("last_name") or "").strip()
    name = f"{first} {last}".strip() or None
    email = (row.get("value") or "").strip().lower() or None
    position = (row.get("position") or "").strip() or None
    conf = row.get("confidence")
    if not email and not name:
        return None

    is_hr = is_hr_relevant_contact(
        {
            "designation": position,
            "department": row.get("department"),
            "seniority": row.get("seniority"),
        }
    )

    if hr_only and not is_hr:
        return None

    source = "hunter.io" if is_hr else "hunter.io (general)"
    base_conf = 0.55 + float(conf or 50) / 200.0
    if not is_hr:
        base_conf = min(0.88, base_conf * 0.92)

    return {
        "name": name,
        "company": company,
        "email": email,
        "designation": position,
        "department": row.get("department"),
        "seniority": row.get("seniority"),
        "source": source,
        "is_hr": is_hr,
        "confidence": min(0.98, base_conf),
    }


async def _hunter_domain_query(
    client: httpx.AsyncClient,
    api_key: str,
    domain: str,
    company: str,
    pool: HunterKeyPool,
    key_index: int,
    department: str | None = None,
    seniority: str | None = None,
    hr_only: bool = True,
) -> tuple[list[dict], str | None]:
    params: dict = {
        "domain": domain,
        "api_key": api_key,
        "limit": 10,
        "type": "personal",
    }
    if department:
        params["department"] = department
    if seniority:
        params["seniority"] = seniority

    pool.record_request(key_index)
    resp = await client.get("https://api.hunter.io/v2/domain-search", params=params)

    if resp.status_code == 401:
        pool.mark_invalid(key_index, "Invalid API key (401)")
        return [], "invalid"
    if resp.status_code == 429:
        pool.mark_exhausted(key_index, "Rate limit / credits exhausted (429)")
        return [], "exhausted"
    if resp.status_code == 402:
        pool.mark_exhausted(key_index, "Insufficient credits (402)")
        return [], "exhausted"
    if resp.status_code != 200:
        return [], None

    rows = ((resp.json() or {}).get("data") or {}).get("emails") or []
    out = []
    for row in rows:
        person = _row_to_person(row, company, hr_only=hr_only)
        if person:
            out.append(person)
    return out, None


async def _run_hunter_queries(
    client: httpx.AsyncClient,
    pool: HunterKeyPool,
    domain: str,
    company: str,
    queries: list[dict],
    seen: set[str],
    people: list[dict],
    want: int,
    hr_only: bool,
    errors: list[str],
) -> None:
    """Execute a batch of Hunter queries, rotating keys on limit errors."""
    for query in queries:
        if len(people) >= want:
            break

        idx = pool.current_index()
        if idx is None:
            errors.append("All Hunter API keys exhausted for today — credits reset daily.")
            break

        api_key = pool.get_key(idx)
        if not api_key:
            break

        batch, status = await _hunter_domain_query(
            client,
            api_key,
            domain,
            company,
            pool,
            idx,
            department=query.get("department"),
            seniority=query.get("seniority"),
            hr_only=hr_only,
        )

        if status == "exhausted":
            rotated = pool.rotate()
            if rotated:
                errors.append(
                    f"Key {pool.stats[idx].key_suffix} exhausted — rotated to {pool.stats[rotated[0]].key_suffix}"
                )
                batch, status = await _hunter_domain_query(
                    client,
                    pool.get_key(rotated[0]) or "",
                    domain,
                    company,
                    pool,
                    rotated[0],
                    department=query.get("department"),
                    seniority=query.get("seniority"),
                    hr_only=hr_only,
                )
            else:
                break
        elif status == "invalid":
            rotated = pool.rotate()
            if not rotated:
                errors.append(f"Key {pool.stats[idx].key_suffix} is invalid.")
                break
            continue

        for person in batch:
            email = (person.get("email") or "").lower()
            key = email or (person.get("name") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            people.append(person)
            if len(people) >= want:
                break

async def hunter_hr_search(
    domain: str,
    company: str,
    limit: int = 50,
    api_keys: list[str] | None = None,
    active_key_index: int = 0,
    key_states: list[dict] | None = None,
) -> tuple[list[dict], str | None, HunterKeyPool | None, dict]:
    """
    HR-focused Hunter search with fallback to general company employees.
    Returns (people, error_message, key_pool_state, meta).
    """
    keys = [k.strip() for k in (api_keys or []) if k and k.strip()]
    if not keys:
        keys = _env_hunter_keys()
    if not keys:
        return [], "No Hunter API keys configured. Add keys in Manage keys at the bottom.", None, {}
    if not domain:
        return [], "Could not resolve company domain.", None, {}

    want = max(1, min(int(limit or 50), 200))
    pool = HunterKeyPool(keys=keys, active_index=max(0, min(active_key_index, len(keys) - 1)))
    if key_states:
        pool.apply_client_states(key_states)

    if not await prime_pool_with_usable_key(pool):
        return [], "All Hunter API keys are exhausted. Credits reset daily — try again later.", pool, {}

    seen: set[str] = set()
    people: list[dict] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}) as client:
        # Pass 1: HR / leadership / talent acquisition
        await _run_hunter_queries(
            client, pool, domain, company,
            HUNTER_HR_QUERIES, seen, people, want,
            hr_only=True, errors=errors,
        )

        hr_count = sum(1 for p in people if p.get("is_hr"))

        # Pass 2: general employees if HR results are thin
        if len(people) < want and hr_count < HR_MIN_BEFORE_FALLBACK:
            await _run_hunter_queries(
                client, pool, domain, company,
                HUNTER_FALLBACK_QUERIES, seen, people, want,
                hr_only=False, errors=errors,
            )
        elif len(people) < want:
            # Have some HR but not enough — still top up with general contacts
            await _run_hunter_queries(
                client, pool, domain, company,
                HUNTER_FALLBACK_QUERIES, seen, people, want,
                hr_only=False, errors=errors,
            )

    active = pool.current_index()
    if active is not None:
        acct = await fetch_hunter_account(pool.get_key(active) or "")
        pool.apply_account(active, acct)

    hr_final = sum(1 for p in people if p.get("is_hr"))
    general_final = len(people) - hr_final
    meta = {
        "hr_count": hr_final,
        "general_count": general_final,
        "used_fallback": general_final > 0,
    }

    if not people:
        msg = errors[0] if errors else "No contacts found for this company."
        return [], msg, pool, meta

    return people[:want], (errors[0] if errors else None), pool, meta


async def check_hunter_keys(api_keys: list[str]) -> list[dict]:
    """Validate keys and return live credit/limit info for UI (parallel)."""
    cleaned = [(i, k.strip()) for i, k in enumerate(api_keys) if k and k.strip()]
    sem = asyncio.Semaphore(8)

    async def _check_one(index: int, key: str) -> dict:
        async with sem:
            acct = await fetch_hunter_account(key)
            return {
                "index": index,
                "key_suffix": f"...{key[-6:]}" if len(key) > 8 else key,
                "valid": acct.get("valid", False),
                "error": acct.get("error"),
                "plan_name": acct.get("plan_name"),
                "credits_available": acct.get("credits_available"),
                "credits_used": acct.get("credits_used"),
                "reset_date": acct.get("reset_date"),
                "email": acct.get("email"),
            }

    results = await asyncio.gather(*[_check_one(i, k) for i, k in cleaned])
    return sorted(results, key=lambda r: r["index"])
