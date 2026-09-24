from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import httpx

from .resolver import USER_AGENT

KeyStatus = Literal["active", "standby", "exhausted", "invalid"]


@dataclass
class HunterKeyStat:
    index: int
    key_suffix: str
    status: KeyStatus
    requests_made: int = 0
    credits_available: int | None = None
    credits_used: int | None = None
    reset_date: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "key_suffix": self.key_suffix,
            "status": self.status,
            "requests_made": self.requests_made,
            "credits_available": self.credits_available,
            "credits_used": self.credits_used,
            "reset_date": self.reset_date,
            "error": self.error,
        }


@dataclass
class HunterKeyPool:
    keys: list[str]
    active_index: int = 0
    stats: list[HunterKeyStat] = field(default_factory=list)
    exhausted: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.keys = [k.strip() for k in self.keys if k and k.strip()]
        if not self.stats:
            self.stats = [
                HunterKeyStat(
                    index=i,
                    key_suffix=_suffix(k),
                    status="active" if i == self.active_index else "standby",
                )
                for i, k in enumerate(self.keys)
            ]
        if self.keys and self.active_index >= len(self.keys):
            self.active_index = 0

    def apply_client_states(self, states: list[dict]) -> None:
        """Mark keys exhausted/invalid from browser-side live credit data."""
        for state in states:
            idx = state.get("index")
            if idx is None or idx < 0 or idx >= len(self.keys):
                continue
            credits = state.get("credits_available")
            status = (state.get("status") or "").lower()
            if status == "invalid":
                self.mark_invalid(idx, "Invalid API key")
                continue
            if status == "exhausted" or credits == 0:
                self.mark_exhausted(idx, "Daily limit reached (0 credits)")
                continue
            if credits is not None:
                self.stats[idx].credits_available = credits
            used = state.get("credits_used")
            if used is not None:
                self.stats[idx].credits_used = used
            reset = state.get("reset_date")
            if reset:
                self.stats[idx].reset_date = reset

    def apply_account(self, index: int, acct: dict) -> None:
        if index < 0 or index >= len(self.stats):
            return
        if not acct.get("valid"):
            self.mark_invalid(index, acct.get("error") or "Invalid API key")
            return
        self.stats[index].credits_available = acct.get("credits_available")
        self.stats[index].credits_used = acct.get("credits_used")
        self.stats[index].reset_date = acct.get("reset_date")
        if acct.get("credits_available") == 0:
            self.mark_exhausted(index, "Daily limit reached (0 credits)")

    def _is_usable(self, index: int) -> bool:
        if index in self.exhausted:
            return False
        credits = self.stats[index].credits_available if index < len(self.stats) else None
        if credits == 0:
            return False
        return True

    def current_index(self) -> int | None:
        if not self.keys:
            return None
        if self._is_usable(self.active_index):
            return self.active_index
        for i in range(len(self.keys)):
            idx = (self.active_index + i) % len(self.keys)
            if self._is_usable(idx):
                self.active_index = idx
                if idx < len(self.stats):
                    self.stats[idx].status = "active"
                return idx
        return None

    def mark_exhausted(self, index: int, error: str) -> None:
        self.exhausted.add(index)
        if index < len(self.stats):
            self.stats[index].status = "exhausted"
            self.stats[index].error = error
            self.stats[index].credits_available = 0

    def mark_invalid(self, index: int, error: str) -> None:
        self.exhausted.add(index)
        if index < len(self.stats):
            self.stats[index].status = "invalid"
            self.stats[index].error = error

    def record_request(self, index: int) -> None:
        if index < len(self.stats):
            self.stats[index].requests_made += 1
            if self.stats[index].credits_available is not None and self.stats[index].credits_available > 0:
                self.stats[index].credits_available -= 1
                if self.stats[index].credits_used is not None:
                    self.stats[index].credits_used += 1

    def rotate(self) -> tuple[int, str] | None:
        start = self.active_index
        for offset in range(1, len(self.keys) + 1):
            idx = (start + offset) % len(self.keys)
            if self._is_usable(idx):
                self.active_index = idx
                for i, st in enumerate(self.stats):
                    if i == idx:
                        st.status = "active"
                    elif st.status == "active" and i not in self.exhausted:
                        st.status = "standby"
                return idx, self.keys[idx]
        return None

    def get_key(self, index: int) -> str | None:
        if 0 <= index < len(self.keys):
            return self.keys[index]
        return None

    def snapshot(self) -> list[dict]:
        for i, st in enumerate(self.stats):
            if i in self.exhausted:
                if st.status not in ("invalid", "exhausted"):
                    st.status = "exhausted"
                continue
            if i == self.active_index:
                st.status = "active"
            elif st.status not in ("invalid", "exhausted"):
                st.status = "standby"
        return [s.to_dict() for s in self.stats]


def _suffix(key: str) -> str:
    k = key.strip()
    return f"...{k[-6:]}" if len(k) > 8 else k


async def fetch_hunter_account(api_key: str) -> dict:
    """Return Hunter account/credit info for a key."""
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(
            "https://api.hunter.io/v2/account",
            params={"api_key": api_key},
        )
        if resp.status_code == 401:
            return {"valid": False, "error": "Invalid API key"}
        if resp.status_code != 200:
            return {"valid": False, "error": f"HTTP {resp.status_code}"}
        data = (resp.json() or {}).get("data") or {}
        requests = data.get("requests") or {}
        searches = requests.get("searches") or {}
        return {
            "valid": True,
            "email": data.get("email"),
            "plan_name": data.get("plan_name"),
            "credits_available": searches.get("available"),
            "credits_used": searches.get("used"),
            "reset_date": searches.get("resets_at"),
        }


async def prime_pool_with_usable_key(pool: HunterKeyPool) -> bool:
    """Pick the first usable key; only call Hunter when credits are unknown."""
    attempts = len(pool.keys)
    for _ in range(attempts):
        idx = pool.current_index()
        if idx is None:
            return False

        stat = pool.stats[idx] if idx < len(pool.stats) else None
        if stat and stat.credits_available is not None:
            if stat.credits_available > 0:
                return True
            pool.mark_exhausted(idx, "Daily limit reached (0 credits)")
            if not pool.rotate():
                return False
            continue

        api_key = pool.get_key(idx)
        if not api_key:
            return False

        acct = await fetch_hunter_account(api_key)
        pool.apply_account(idx, acct)
        if idx not in pool.exhausted and pool._is_usable(idx):
            return True
        if not pool.rotate():
            return False
    return False
