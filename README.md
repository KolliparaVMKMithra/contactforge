# ContactForge

HR & leadership contact finder powered by Hunter.io. Supports multiple API keys with automatic daily-limit rotation.

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # then edit .env
python run.py
```

Open http://127.0.0.1:8080

### Hunter API keys

Keys are stored in your **browser** (not on the server). After first load:

1. Click **Manage keys** at the bottom of the page
2. Use **Bulk import** and paste keys one per line

For local dev you can also copy `frontend/default-keys.example.js` to `frontend/default-keys.local.js` and paste your keys there (this file is gitignored).

## Deploy on Render

### Step 1 — Push to GitHub

Repo: https://github.com/KolliparaVMKMithra/contactforge

### Step 2 — Create a Render Web Service

1. Go to [https://dashboard.render.com](https://dashboard.render.com) and sign in
2. Click **New +** → **Web Service**
3. Connect your GitHub account if needed
4. Select repository **KolliparaVMKMithra/contactforge**
5. Use these settings:

| Setting | Value |
|---------|--------|
| **Name** | `contactforge` |
| **Region** | closest to you |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Free |

### Step 3 — Environment variables

In Render → your service → **Environment**, add:

| Key | Value |
|-----|--------|
| `AUTH_EMAIL` | your login email |
| `AUTH_PASSWORD` | your login password |
| `AUTH_SECRET_KEY` | a long random string (e.g. 64 chars) |
| `RENDER` | `true` |

**Do not add Hunter API keys here** — they are managed in the browser via the bottom API panel.

### Step 4 — Deploy

Click **Create Web Service**. Render will build and deploy automatically.

Your app URL will be like: `https://contactforge.onrender.com`

### Step 5 — After deploy

1. Open your Render URL
2. Sign in with `AUTH_EMAIL` / `AUTH_PASSWORD`
3. Click **Manage keys** → **Bulk import** → paste all Hunter API keys
4. Search for a company — keys rotate automatically when daily limits are hit

## Notes

- Free Render services sleep after inactivity; first request may take ~30 seconds to wake up
- Session cookies require HTTPS on Render (`RENDER=true` is set automatically via `render.yaml`)
- Excel export loads the XLSX library on demand when you click Download Excel
