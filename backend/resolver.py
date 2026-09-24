from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from ddgs import DDGS


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def _normalize_domain(url_or_domain: str) -> Optional[str]:
    raw = (url_or_domain or "").strip().lower()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = urlparse(raw).netloc or urlparse(raw).path
    except Exception:
        return None
    host = host.split("@")[-1].split(":")[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    return host


async def resolve_company(company_name: str) -> dict:
    """Resolve company name to domain/website using public sources only."""
    name = company_name.strip()
    result = {
        "company_name": name,
        "domain": None,
        "website": None,
        "logo": None,
        "sources": [],
    }

    # 1) Clearbit autocomplete (public, no API key)
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(
                "https://autocomplete.clearbit.com/v1/companies/suggest",
                params={"query": name},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    best = data[0]
                    domain = _normalize_domain(best.get("domain") or "")
                    if domain:
                        result["domain"] = domain
                        result["website"] = f"https://{domain}"
                        result["logo"] = best.get("logo")
                        result["company_name"] = best.get("name") or name
                        result["sources"].append("clearbit")
                        return result
    except Exception:
        pass

    # 2) DuckDuckGo web search for official site
    try:
        with DDGS() as ddgs:
            hits = list(
                ddgs.text(
                    f"{name} official website",
                    max_results=8,
                )
            )
        skip = (
            "linkedin.com",
            "facebook.com",
            "twitter.com",
            "x.com",
            "instagram.com",
            "youtube.com",
            "crunchbase.com",
            "bloomberg.com",
            "wikipedia.org",
            "glassdoor.com",
            "indeed.com",
            "zoominfo.com",
            "apollo.io",
            "rocketreach.co",
            "yelp.com",
        )
        for hit in hits:
            href = hit.get("href") or hit.get("link") or ""
            domain = _normalize_domain(href)
            if not domain:
                continue
            if any(s in domain for s in skip):
                continue
            # Prefer domains that resemble company name
            slug = re.sub(r"[^a-z0-9]", "", name.lower())
            host_slug = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
            if slug and (slug[:4] in host_slug or host_slug[:4] in slug or len(slug) < 4):
                result["domain"] = domain
                result["website"] = f"https://{domain}"
                result["sources"].append("duckduckgo")
                return result
        # Fallback: first non-skipped domain
        for hit in hits:
            href = hit.get("href") or hit.get("link") or ""
            domain = _normalize_domain(href)
            if domain and not any(s in domain for s in skip):
                result["domain"] = domain
                result["website"] = f"https://{domain}"
                result["sources"].append("duckduckgo")
                return result
    except Exception:
        pass

    return result
