from __future__ import annotations

import os
import secrets

from dotenv import load_dotenv

load_dotenv()

AUTH_EMAIL = os.getenv("AUTH_EMAIL", "b_sreekrishna@av.amrita.edu").strip().lower()
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "Krishna@123")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY") or secrets.token_hex(32)

PUBLIC_PATHS = {
    "/login",
    "/api/auth/login",
    "/api/health",
}

PUBLIC_PREFIXES = (
    "/static/",
)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def verify_credentials(email: str, password: str) -> bool:
    email_ok = secrets.compare_digest(email.strip().lower(), AUTH_EMAIL)
    password_ok = secrets.compare_digest(password, AUTH_PASSWORD)
    return email_ok and password_ok
