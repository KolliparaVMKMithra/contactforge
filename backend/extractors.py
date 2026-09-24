from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])"
)

# Common junk / non-person emails
JUNK_EMAIL_PREFIXES = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "support",
    "help",
    "info",
    "contact",
    "hello",
    "admin",
    "webmaster",
    "sales",
    "marketing",
    "press",
    "media",
    "jobs",
    "careers",
    "hr",
    "billing",
    "privacy",
    "legal",
    "abuse",
    "postmaster",
    "mailer-daemon",
    "newsletter",
    "subscribe",
    "unsubscribe",
    "team",
    "office",
    "enquiries",
    "enquiry",
    "customerservice",
    "customer.service",
    "directory",
    "notifications",
    "notify",
    "alerts",
    "system",
    "security",
    "feedback",
    "service",
    "services",
    "api",
    "dev",
    "developer",
    "developers",
    "docs",
    "documentation",
    "status",
    "bot",
    "robots",
    "github",
    "git",
    "partners",
    "partner",
    "affiliates",
    "affiliate",
    "community",
}

JUNK_EMAIL_HOST_PARTS = (
    "errors.",
    "sentry",
    "wixpress",
    "example.com",
    "email.ghost",
    "amazonaws.com",
    "cloudfront.net",
    "sentry.io",
    "github.com",
    "googleapis.com",
    "schema.org",
    "w3.org",
    "png",
    "jpg",
)

TITLE_KEYWORDS = [
    "CEO",
    "CTO",
    "CFO",
    "COO",
    "CMO",
    "CIO",
    "CPO",
    "Chief Executive",
    "Chief Technology",
    "Chief Financial",
    "Chief Operating",
    "Chief Marketing",
    "Chief Product",
    "Chief",
    "Co-Founder",
    "CoFounder",
    "Cofounder",
    "Founder",
    "President",
    "Vice President",
    "VP of",
    "VP,",
    "VP ",
    "SVP",
    "EVP",
    "Managing Director",
    "Director of",
    "Director,",
    "Director ",
    "Head of",
    "General Manager",
    "Product Manager",
    "Engineering Manager",
    "Manager",
    "Principal",
    "Partner",
    "Chairman",
    "Executive",
]

TITLE_RE = re.compile(
    r"(?i)\b("
    + "|".join(
        re.escape(t)
        for t in sorted(TITLE_KEYWORDS, key=len, reverse=True)
    )
    + r")\b[^\n|]{0,60}"
)

NAME_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)


DEMO_EMAIL_DOMAINS = {
    "acme.com",
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "email.com",
    "domain.com",
    "yourdomain.com",
    "company.com",
    "emailprovider.com",
    "lovelace.app",
    "sentry.io",
}


PLACEHOLDER_LOCALS = {
    "jane",
    "john",
    "doe",
    "jane.doe",
    "john.doe",
    "john.d",
    "j.doe",
    "j.d",
    "foo",
    "bar",
    "baz",
    "test",
    "testing",
    "user",
    "username",
    "firstname",
    "lastname",
    "first",
    "last",
    "first.last",
    "first.l",
    "f.last",
    "name",
    "your.name",
    "you",
    "me",
    "abc",
    "xyz",
    "someone",
    "anybody",
}


def is_person_email(email: str, domain: Optional[str] = None) -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
    local, _, host = email.partition("@")
    if not local or not host or "." not in host:
        return False
    if host in DEMO_EMAIL_DOMAINS:
        return False
    if any(x in email for x in (".png", ".jpg", ".gif", ".svg", ".webp", "example.com", "sentry.io", "wixpress", "schema.org")):
        return False
    if any(part in host for part in JUNK_EMAIL_HOST_PARTS):
        return False
    # Prefer company-domain employee emails when domain is known
    if domain:
        if host != domain and not host.endswith("." + domain):
            return False
    # UUID / hash / tracking locals (common on modern SaaS sites)
    local_base = local.split("+", 1)[0]
    if local_base in PLACEHOLDER_LOCALS:
        return False
    if re.fullmatch(r"[0-9a-f]{16,}", local_base):
        return False
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", local_base):
        return False
    if len(local_base) > 28 and re.fullmatch(r"[0-9a-f]+", local_base):
        return False
    if local_base.startswith(("u002f", "noreply", "no-reply", "donotreply")):
        return False
    # Role / mailbox aliases
    role = local_base.replace(".", "").replace("-", "").replace("_", "")
    if local_base in JUNK_EMAIL_PREFIXES or role in JUNK_EMAIL_PREFIXES:
        return False
    if any(local_base.startswith(p + "+") or local_base.startswith(p + ".") for p in JUNK_EMAIL_PREFIXES):
        return False
    # Prefer person-shaped locals; reject long random tokens
    if re.match(r"^[a-z]+([._-][a-z]+)+$", local_base):
        return True
    if re.match(r"^[a-z]{2,20}$", local_base) and local_base not in JUNK_EMAIL_PREFIXES:
        return True
    if re.match(r"^[a-z]\.?[a-z]{2,20}$", local_base):
        return True
    # Reject anything that looks machine-generated
    if re.search(r"\d{5,}", local_base):
        return False
    if len(local_base) > 24:
        return False
    return False


def is_valid_person_name(name: Optional[str], company: Optional[str] = None) -> bool:
    if not name:
        return False
    name = _clean_text(name)
    if len(name) < 3 or len(name) > 40:
        return False
    banned = (
        "linkedin",
        "crunchbase",
        "facebook",
        "twitter",
        "instagram",
        "youtube",
        "http",
        "www",
        "style",
        "lineup",
        "startup",
        "unicorn",
        "building",
        "names first",
        "board of",
        "previously",
        "worked at",
        "sits down",
        "talking with",
        "future co",
        "first block",
        "colossus",
        "profile",
        "the ai",
        "workspace",
        "google",
        "microsoft",
        "update",
        "contacts",
        "integration",
        "alum",
        "form",
        "airtable",
        "calendly",
        "try it",
        "phone",
        "number",
        "operations",
        "manager",
        "people team",
        "press",
        "communications",
    )
    low = name.lower()
    if any(b in low for b in banned):
        return False
    # Reject title-like "names"
    if any(w in low.split() for w in ("manager", "director", "founder", "officer", "president", "number", "phone", "team", "people", "executive", "chief", "joins")):
        return False
    # Single-token names only allowed when paired with email elsewhere
    if len(name.split()) < 2:
        return False
    if name.split()[0].lower() in {"first", "last", "john", "jane", "foo", "bar"}:
        return False
    if company and company.lower() in low and low != company.lower():
        # Allow exact company match rejection below; reject "Building Notion" etc.
        if low != company.lower():
            return False
    if company and low == company.lower():
        return False
    # Must look like a personal name: 2-4 capitalized words
    if not re.fullmatch(r"[A-Z][a-z'’.-]+(?:\s+[A-Z][a-z'’.-]+){1,3}", name):
        return False
    junk_words = {"inc", "ltd", "llc", "corp", "co", "the", "and", "with", "from", "for", "director"}
    parts = [p.strip(".,") for p in name.split()]
    if any(p.lower() in junk_words for p in parts):
        return False
    return True


def clean_designation(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    title = _clean_text(title)
    title = re.split(r"[|•·]|[@$]|\s{2,}|\d{4}| - | – | — ", title)[0].strip(" ,;-–—")
    # Keep first clause only
    title = re.split(r"\band\b|\bof\s+\d", title, maxsplit=1, flags=re.I)[0].strip(" ,;-–—")
    if len(title) < 2 or len(title) > 60:
        return None
    low = title.lower()
    if any(x in low for x in ("try it", "integration", "manually", "inputting", "ensu", "compan y")):
        return None
    if not TITLE_RE.match(title):
        return None
    title = re.sub(r"\b(at|of|for)\s+$", "", title, flags=re.I).strip()
    return title or None


def extract_emails(text: str, domain: Optional[str] = None) -> list[str]:
    found = []
    seen = set()
    for match in EMAIL_RE.findall(text or ""):
        email = match.lower().strip(".,;:()[]<>\"'")
        if email in seen:
            continue
        if not is_person_email(email, domain):
            continue
        if domain:
            host = email.split("@", 1)[-1]
            # Prefer company domain but keep other person emails found on company pages
            if host != domain and not host.endswith("." + domain):
                # Still keep if on same crawl — mark later with lower confidence
                pass
        seen.add(email)
        found.append(email)
    return found


def name_from_email(email: str) -> Optional[str]:
    local = email.split("@", 1)[0]
    local = re.sub(r"\d+", "", local)
    parts = re.split(r"[._\-]+", local)
    parts = [p for p in parts if p and len(p) > 1]
    if len(parts) >= 2:
        return " ".join(p.capitalize() for p in parts[:3])
    if len(parts) == 1 and len(parts[0]) >= 3:
        return parts[0].capitalize()
    return None


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def extract_people_from_html(html: str, page_url: str, company: str, domain: Optional[str]) -> list[dict]:
    """Extract people cards / team members from HTML."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    people: list[dict] = []
    seen: set[str] = set()

    # mailto links are high-signal
    for a in soup.select('a[href^="mailto:"]'):
        href = a.get("href", "")
        email = href.replace("mailto:", "").split("?")[0].strip().lower()
        if not is_person_email(email, domain):
            continue
        name = _clean_text(a.get_text()) or name_from_email(email)
        if name and not is_valid_person_name(name, company) and "@" not in (name or ""):
            # Keep email-derived single-token names
            if not name_from_email(email):
                name = name_from_email(email)
        parent_text = _clean_text(a.parent.get_text(" ", strip=True) if a.parent else "")
        title_m = TITLE_RE.search(parent_text)
        designation = clean_designation(title_m.group(0) if title_m else None)
        key = email
        if key not in seen:
            seen.add(key)
            people.append(
                {
                    "name": name,
                    "company": company,
                    "email": email,
                    "designation": designation,
                    "source": page_url,
                    "confidence": 0.9,
                }
            )

    # Team / people cards: look for common patterns
    selectors = [
        "[class*='team']",
        "[class*='people']",
        "[class*='leader']",
        "[class*='staff']",
        "[class*='member']",
        "[class*='employee']",
        "[class*='profile']",
        "[class*='bio']",
        "[id*='team']",
        "[id*='people']",
        "[id*='leadership']",
        "article",
        ".card",
    ]
    blocks = []
    for sel in selectors:
        blocks.extend(soup.select(sel))

    # Deduplicate blocks by identity
    unique_blocks = []
    block_ids = set()
    for b in blocks:
        bid = id(b)
        if bid in block_ids:
            continue
        block_ids.add(bid)
        text = _clean_text(b.get_text(" ", strip=True))
        if 10 < len(text) < 500:
            unique_blocks.append(b)

    for block in unique_blocks[:200]:
        text = _clean_text(block.get_text(" ", strip=True))
        emails = extract_emails(text + " " + str(block), domain)
        names = NAME_RE.findall(text)
        title_m = TITLE_RE.search(text)

        # Heading-based name
        heading = block.find(["h1", "h2", "h3", "h4", "h5", "strong"])
        heading_name = _clean_text(heading.get_text()) if heading else None
        if heading_name and not NAME_RE.fullmatch(heading_name):
            # Allow two/three word capitalized names even if regex strict fails
            if not re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z'.-]+){1,3}$", heading_name):
                heading_name = None

        name = heading_name
        if not name and names:
            # Skip company name itself
            for n in names:
                if n.lower() != company.lower() and "Inc" not in n and "Ltd" not in n:
                    name = n
                    break

        designation = clean_designation(title_m.group(0) if title_m else None)
        email = emails[0] if emails else None

        if name and not is_valid_person_name(name, company):
            name = None
        if not name and email:
            guessed = name_from_email(email)
            name = guessed if is_valid_person_name(guessed, company) else guessed

        if not name and not email:
            continue
        if name and len(name.split()) > 4:
            continue

        key = (email or name or "").lower()
        if not key or key in seen:
            continue
        # Require at least title or email to avoid random capitalized words
        if not email and not designation:
            continue
        if name and not email and not is_valid_person_name(name, company):
            continue
        seen.add(key)
        people.append(
            {
                "name": name,
                "company": company,
                "email": email,
                "designation": designation,
                "source": page_url,
                "confidence": 0.75 if email else 0.55,
            }
        )

    # Whole-page email sweep
    page_text = soup.get_text(" ", strip=True)
    for email in extract_emails(html + " " + page_text, domain):
        if email in seen:
            continue
        # Prefer company-domain emails
        host = email.split("@", 1)[-1]
        conf = 0.7
        if domain and (host == domain or host.endswith("." + domain)):
            conf = 0.85
        seen.add(email)
        people.append(
            {
                "name": name_from_email(email),
                "company": company,
                "email": email,
                "designation": None,
                "source": page_url,
                "confidence": conf,
            }
        )

    return people


def extract_links(html: str, base_url: str, same_domain: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host != same_domain and not host.endswith("." + same_domain):
            continue
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query and any(k in parsed.query.lower() for k in ("page", "p=", "team")):
            clean = f"{clean}?{parsed.query}"
        links.append(clean.rstrip("/"))
    return links


TEAM_PATH_HINTS = (
    "team",
    "people",
    "about",
    "leadership",
    "management",
    "staff",
    "our-team",
    "our-people",
    "company",
    "who-we-are",
    "founders",
    "executives",
    "directors",
    "contact",
    "contacts",
    "directory",
    "employees",
)


def score_team_url(url: str) -> int:
    path = urlparse(url).path.lower()
    score = 0
    for hint in TEAM_PATH_HINTS:
        if hint in path:
            score += 10
    if path in ("", "/"):
        score += 1
    return score
