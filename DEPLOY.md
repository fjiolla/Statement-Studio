# Deploying for free

The backend (FastAPI + OCR) and the frontend (Next.js) deploy separately. Both options below are free.

| Part | Host | Why |
|---|---|---|
| Backend | **Hugging Face Spaces** (Docker, free CPU tier) | 2 vCPU / 16 GB RAM, enough for OCR. Render's free tier (512 MB) runs out of memory. |
| Frontend | **Vercel** (Hobby) | Zero-config Next.js hosting |

## 1. Backend → Hugging Face Space

1. Create a Space at https://huggingface.co/new-space, choosing **SDK: Docker** and the **Blank** template.
2. Push the contents of `backend/` to the root of the Space repo (the Dockerfile must be at the root):
   ```bash
   git clone https://huggingface.co/spaces/<user>/<space> hf-space
   cp -r backend/{app,samples,scripts,Dockerfile,.dockerignore,requirements.txt} hf-space/
   ```
3. Add this header to the Space's `README.md` (HF reads it to configure the container):
   ```yaml
   ---
   title: Statement Studio API
   sdk: docker
   app_port: 7860
   ---
   ```
4. Under Space **Settings → Variables**, set:
   - `BEFREE_CORS_ORIGINS` = `https://<your-app>.vercel.app`
   - optional: `BEFREE_CORS_REGEX` = `https://.*\.vercel\.app` (allows Vercel preview URLs)
   - optional: `BEFREE_RETENTION_HOURS` = `24`
5. Push. The first build takes about 5 minutes because it downloads the OCR models. Check it with `https://<user>-<space>.hf.space/api/health`.

Notes
- The free tier sleeps after inactivity, and the first request afterwards takes about 30 s to wake it.
- Storage is ephemeral (`/tmp`), so uploaded statements disappear on restart. This suits a demo and matches the 24-hour privacy retention.
- `classifier.joblib` was trained with scikit-learn 1.9.1, which `requirements.txt` pins. If you change that version, retrain with `python scripts/train_model.py`.

## 2. Frontend → Vercel

1. Import the repo on Vercel and set **Root Directory** to `frontend`.
2. Add the environment variable `NEXT_PUBLIC_API_URL` = `https://<user>-<space>.hf.space` (no trailing slash).
3. Deploy. Vercel detects pnpm from `pnpm-lock.yaml`.

## Run locally

```bash
# backend (Python 3.12)
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/pytest -q                       # 45 tests; add -m "not slow" to skip OCR-heavy ones

# frontend (Node 20+)
cd frontend && pnpm install && pnpm dev   # http://localhost:3000
```

Or run the backend container directly: `docker build -t statement-api backend && docker run -p 7860:7860 -e BEFREE_CORS_ORIGINS=http://localhost:3000 statement-api`. Then point `NEXT_PUBLIC_API_URL` at `http://localhost:7860`.
