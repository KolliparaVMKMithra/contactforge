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

Repo: https://github.com/KolliparaVMKMithra/contactforge

### Option A — Public Git URL (no GitHub app; use this if Connect keeps redirecting)

1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. At the top, click the **Public Git repository** tab (not GitHub)
4. Paste this URL exactly:
   ```
   https://github.com/KolliparaVMKMithra/contactforge
   ```
5. Click **Continue**
6. Use the settings below, add env vars, then **Create Web Service**

### Option B — Blueprint (one-click from `render.yaml`)

1. Go to [https://dashboard.render.com/blueprints](https://dashboard.render.com/blueprints)
2. Click **New Blueprint Instance**
3. Paste: `https://github.com/KolliparaVMKMithra/contactforge`
4. Render reads `render.yaml` automatically — enter `AUTH_EMAIL` and `AUTH_PASSWORD` when prompted
5. Click **Apply**

### Option C — Railway (alternative host)

1. Go to [https://railway.app](https://railway.app) → sign in with GitHub
2. **New Project** → **Deploy from GitHub repo** → select `contactforge`
3. Add variables: `AUTH_EMAIL`, `AUTH_PASSWORD`, `AUTH_SECRET_KEY`, `RENDER=true`
4. Railway auto-uses the `Dockerfile` — open the generated URL

### Render manual settings (Options A & B)

1. Go to [https://dashboard.render.com](https://dashboard.render.com) and sign in
2. Create the service using Option A or B above
3. Use these settings if not using Blueprint:

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
