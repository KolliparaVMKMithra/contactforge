from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .auth import AUTH_SECRET_KEY, is_public_path, verify_credentials
from .enrichment import _env_hunter_keys, check_hunter_keys, enrichment_status
from .key_store import load_user_keys, save_user_keys
from .models import CheckKeysRequest, KeyStorePayload, LoginRequest, SearchRequest, SearchResponse
from .scraper import find_employee_contacts

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="ContactForge — HR Contact Finder",
    description="Find HR, talent acquisition, and leadership contacts via Hunter.io.",
    version="2.0.0",
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if is_public_path(request.url.path):
            return await call_next(request)

        if not request.session.get("authenticated"):
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=AUTH_SECRET_KEY,
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=os.getenv("RENDER") == "true" or os.getenv("SESSION_HTTPS_ONLY", "").lower() == "true",
)


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    if not verify_credentials(req.email, req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    request.session["authenticated"] = True
    request.session["email"] = req.email.strip().lower()
    return {"ok": True, "email": request.session["email"]}


@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"email": request.session.get("email")}


@app.get("/api/health")
async def health():
    return {"status": "ok", **enrichment_status()}


@app.get("/api/hunter/keys")
async def get_saved_keys(request: Request):
    email = request.session.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")
    return load_user_keys(email)


@app.put("/api/hunter/keys")
async def put_saved_keys(payload: KeyStorePayload, request: Request):
    email = request.session.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        saved = save_user_keys(email, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **saved}


@app.post("/api/hunter/check-keys")
async def api_check_keys(req: CheckKeysRequest):
    keys = [k.strip() for k in req.hunter_api_keys if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="At least one API key is required")
    try:
        results = await asyncio.wait_for(check_hunter_keys(keys), timeout=120.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Credit check timed out. Try again.")
    return {"keys": results}


@app.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest, request: Request):
    name = req.company_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")

    req_keys = [k.strip() for k in req.hunter_api_keys if k.strip()]

    email = request.session.get("email")
    stored_keys = []
    if email:
        user_store = load_user_keys(email)
        for entry in user_store.get("keys", []):
            if isinstance(entry, dict) and entry.get("key"):
                k = entry["key"].strip()
                if k and k not in stored_keys:
                    stored_keys.append(k)

    env_keys = _env_hunter_keys()

    combined_keys = []
    for k in req_keys + stored_keys + env_keys:
        if k and k not in combined_keys:
            combined_keys.append(k)

    if not combined_keys:
        raise HTTPException(
            status_code=400,
            detail="Add at least one Hunter.io API key in Manage keys at the bottom or set HUNTER_API_KEY environment variable.",
        )

    try:
        key_states = [s.model_dump() for s in req.key_states]
        result = await asyncio.wait_for(
            find_employee_contacts(
                name,
                max_results=req.max_results,
                hunter_api_keys=combined_keys,
                active_key_index=req.active_key_index,
                key_states=key_states,
            ),
            timeout=120.0,
        )
        return SearchResponse(**result)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Search timed out. Try again.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc


@app.get("/login")
async def login_page():
    login_path = FRONTEND / "login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="Login page not found")
    return FileResponse(login_path)


@app.get("/")
async def index():
    index_path = FRONTEND / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
