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


def _clean_title(title: str) -> str:
    cleaned = re.sub(r"\s*[-|•·]\s*(Official Website|LinkedIn|Home|Overview|Contact|About).*$", "", title, flags=re.I).strip()
    return cleaned or title


async def search_company_candidates(query: str) -> list[dict]:
    name = query.strip()
    if not name:
        return []

    candidates: list[dict] = []
    seen_domains: set[str] = set()

    # Direct domain check (e.g. user typed "snabbit.com")
    direct_domain = _normalize_domain(name)
    if direct_domain and "." in name:
        company_label = name.split(".")[0].capitalize()
        candidates.append({
            "company_name": company_label,
            "domain": direct_domain,
            "website": f"https://{direct_domain}",
            "logo": f"https://www.google.com/s2/favicons?domain={direct_domain}&sz=128",
            "description": f"Direct domain for {direct_domain}",
            "source": "direct",
        })
        seen_domains.add(direct_domain)

    # 1) Clearbit autocomplete API (public, free)
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(
                "https://autocomplete.clearbit.com/v1/companies/suggest",
                params={"query": name},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data[:6]:
                        dom = _normalize_domain(item.get("domain") or "")
                        if dom and dom not in seen_domains:
                            seen_domains.add(dom)
                            logo = item.get("logo") or f"https://www.google.com/s2/favicons?domain={dom}&sz=128"
                            candidates.append({
                                "company_name": item.get("name") or name.title(),
                                "domain": dom,
                                "website": f"https://{dom}",
                                "logo": logo,
                                "description": f"Verified company domain on Clearbit ({dom})",
                                "source": "clearbit",
                            })
    except Exception:
        pass

    # 2) Web Search for Official Sites & LinkedIn Company Profiles
    skip_domains = (
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
        "github.com",
    )

    try:
        with DDGS() as ddgs:
            web_hits = list(ddgs.text(f"{name} company official website", max_results=10))
            for hit in web_hits:
                href = hit.get("href") or hit.get("link") or ""
                dom = _normalize_domain(href)
                if not dom or dom in seen_domains:
                    continue
                if any(s in dom for s in skip_domains):
                    continue

                title = _clean_title(hit.get("title") or name.title())
                snippet = hit.get("body") or hit.get("snippet") or f"Official website: {dom}"
                seen_domains.add(dom)
                candidates.append({
                    "company_name": title,
                    "domain": dom,
                    "website": f"https://{dom}",
                    "logo": f"https://www.google.com/s2/favicons?domain={dom}&sz=128",
                    "description": snippet[:180],
                    "source": "duckduckgo",
                })

            li_hits = list(ddgs.text(f"{name} site:linkedin.com/company", max_results=5))
            for hit in li_hits:
                href = hit.get("href") or hit.get("link") or ""
                title = hit.get("title") or ""
                snippet = hit.get("body") or hit.get("snippet") or ""
                if "linkedin.com/company" in href.lower():
                    comp_name = re.sub(r"[-|:•·]\s*LinkedIn.*$", "", title, flags=re.I).strip()
                    comp_name = re.sub(r"\s*\(.*?\)", "", comp_name).strip()
                    dom_match = re.search(r"\b([a-z0-9-]+\.(?:com|in|io|co|net|org|app|dev|ai))\b", snippet.lower())
                    dom = dom_match.group(1) if dom_match else None
                    if dom and dom not in seen_domains and not any(s in dom for s in skip_domains):
                        seen_domains.add(dom)
                        candidates.append({
                            "company_name": comp_name or name.title(),
                            "domain": dom,
                            "website": f"https://{dom}",
                            "logo": f"https://www.google.com/s2/favicons?domain={dom}&sz=128",
                            "description": f"LinkedIn: {snippet[:150]}",
                            "source": "linkedin",
                        })
    except Exception:
        pass

    return candidates


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

    candidates = await search_company_candidates(name)
    if candidates:
        best = candidates[0]
        result["domain"] = best["domain"]
        result["website"] = best["website"]
        result["logo"] = best.get("logo")
        result["company_name"] = best["company_name"]
        result["sources"].append(best.get("source", "search"))

    return result
