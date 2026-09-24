from __future__ import annotations

from .enrichment import hunter_hr_search
from .models import Contact
from .resolver import resolve_company


def merge_hunter_contacts(items: list[dict], company: str, max_results: int) -> list[Contact]:
    by_email: dict[str, dict] = {}
    by_name: dict[str, dict] = {}

    for raw in items:
        email = (raw.get("email") or "").lower().strip() or None
        name = (raw.get("name") or "").strip() or None
        designation = (raw.get("designation") or "").strip() or None
        source = raw.get("source") or "hunter.io"
        confidence = float(raw.get("confidence") or 0.75)

        if email:
            existing = by_email.get(email)
            if not existing:
                by_email[email] = {
                    "name": name,
                    "company": company,
                    "email": email,
                    "designation": designation,
                    "source": source,
                    "confidence": confidence,
                }
            else:
                if name and not existing.get("name"):
                    existing["name"] = name
                if designation and not existing.get("designation"):
                    existing["designation"] = designation
                existing["confidence"] = max(existing["confidence"], confidence)
        elif name and designation:
            key = name.lower()
            if key not in by_name:
                by_name[key] = {
                    "name": name,
                    "company": company,
                    "email": None,
                    "designation": designation,
                    "source": source,
                    "confidence": confidence,
                }

    merged = list(by_email.values())
    email_names = {(c["name"] or "").lower() for c in merged if c.get("name")}
    for key, val in by_name.items():
        if key not in email_names:
            merged.append(val)

    merged.sort(
        key=lambda c: (
            1 if c.get("email") else 0,
            1 if "(general)" not in (c.get("source") or "") else 0,
            c.get("confidence", 0),
        ),
        reverse=True,
    )

    contacts = []
    for c in merged[:max_results]:
        contacts.append(
            Contact(
                name=c.get("name"),
                company=company,
                email=c.get("email"),
                designation=c.get("designation"),
                source=c.get("source"),
                confidence=round(float(c.get("confidence") or 0), 2),
            )
        )
    return contacts


async def find_employee_contacts(
    company_name: str,
    max_results: int = 100,
    hunter_api_keys: list[str] | None = None,
    active_key_index: int = 0,
    key_states: list[dict] | None = None,
) -> dict:
    enrichment_errors: list[str] = []
    resolved = await resolve_company(company_name)
    company = resolved.get("company_name") or company_name.strip()
    domain = resolved.get("domain")
    website = resolved.get("website")

    people, hunter_err, pool, meta = await hunter_hr_search(
        domain=domain or "",
        company=company,
        limit=max_results,
        api_keys=hunter_api_keys,
        active_key_index=active_key_index,
        key_states=key_states,
    )

    if hunter_err and not people:
        enrichment_errors.append(hunter_err)

    contacts = merge_hunter_contacts(people, company, max_results)

    key_stats = pool.snapshot() if pool else []
    active_idx = pool.active_index if pool else 0

    hr_count = meta.get("hr_count", 0)
    general_count = meta.get("general_count", 0)

    if contacts:
        if hr_count and general_count:
            message = (
                f"Found {len(contacts)} contacts via Hunter.io "
                f"({hr_count} HR/leadership, {general_count} other employees at {domain})."
            )
        elif hr_count:
            message = (
                f"Found {len(contacts)} HR & leadership contacts via Hunter.io "
                f"(domain: {domain or 'unknown'})."
            )
        else:
            message = (
                f"No HR contacts found — returned {len(contacts)} general employee emails "
                f"from {domain or 'company domain'}."
            )
    else:
        message = (
            hunter_err
            or "No contacts found. Try another company or add more Hunter API keys."
        )

    return {
        "company_name": company,
        "domain": domain,
        "website": website,
        "contacts": contacts,
        "pages_scanned": 0,
        "sources_used": ["hunter.io"] if contacts else [],
        "message": message,
        "enrichment_errors": enrichment_errors,
        "hunter_key_stats": key_stats,
        "active_key_index": active_idx,
    }
