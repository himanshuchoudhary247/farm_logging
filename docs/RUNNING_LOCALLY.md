# Running FarmHerd locally

Two ways to run this, depending on whether you have your own AWS access.

## Option A — you have your own AWS credentials

```bash
python3.12 -m venv venv   # 3.12+ required
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: fill in AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, VOICE_BUCKET
# (a real S3 bucket in ap-south-1 your IAM user can read/write)

set -a && source .env && set +a
uvicorn services.api_service.main:app --host 127.0.0.1 --port 8001
```

Visit `http://127.0.0.1:8001/docs` — should return the FastAPI docs page.
That confirms the server booted and Bedrock's connection pre-warmed
successfully (check the terminal for `Bedrock connection pre-warmed`).

## Option B — no AWS credentials, use the dev proxy

If you don't have your own AWS access, another engineer who's already
running this app (with real AWS credentials) can share two values with
you instead of any AWS key:

- their server's base URL (e.g. `http://<their-ip>:8001`)
- a `DEV_PROXY_API_KEY`

Your `.env` then needs **no AWS credentials at all**:

```bash
cp .env.example .env
```

Edit `.env`:
```
LLM_PROXY_BASE_URL=http://<their-ip>:8001
DEV_PROXY_API_KEY=<the key they gave you>
# leave AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / VOICE_BUCKET blank
```

Then run exactly the same way:
```bash
set -a && source .env && set +a
uvicorn services.api_service.main:app --host 127.0.0.1 --port 8001
```

Every Bedrock/Transcribe/Polly call your local instance makes gets
forwarded over HTTP to their server, which has the real AWS access. Your
machine touches AWS never, directly or indirectly.

**Real limits of this mode, know them going in:**
- Every call bills the *other* engineer's AWS account. There's a per-key
  daily request cap (`DEV_PROXY_DAILY_LIMIT`, default 200) on their end —
  once you hit it you get `429` until the next day. Don't run load tests
  against someone else's shared proxy key.
- Latency is one extra network hop (your machine → their server → AWS →
  back). Fine for manual testing, not representative of production
  latency numbers.
- If their server is offline, your local instance can't do anything
  Bedrock/Transcribe/Polly-related — extraction, health recommendations,
  query_agent, English/Hindi TTS all depend on it. (Kannada/Tamil/Telugu/
  Malayalam TTS still uses gTTS regardless of this mode — see
  `config/llm.yaml`'s `tts.fallback_provider` — but currently gets routed
  through the proxy too for simplicity, so it's affected the same way.)

## Verify it's actually working, either mode

```bash
curl -X POST http://127.0.0.1:8001/farmers/f-001/chat/turn \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-1","text":"how many animals do I have","language":"en-IN","include_audio":false}'
```

Should return a real answer referencing `f-001`'s actual animal count
(check `data/animals.json` for the demo dataset), not an error.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` (frontend `.env`) to wherever your backend is
running (`http://127.0.0.1:8001` by default).

## Common gotchas

- **Python version**: this app requires 3.12+ (bumped from 3.9 — Nova
  Sonic's SDK needs it). `python3 --version` first if something fails to
  import.
- **`ffmpeg` on PATH** — needed for audio format conversion (STT/TTS
  paths). `brew install ffmpeg` on macOS.
- **`[ENV ERROR] Missing required environment variables`** on startup
  means you're in Option A shape but missing a required var, or you meant
  Option B but forgot to set `LLM_PROXY_BASE_URL` — check `.env` against
  `.env.example`.
- **Branch protection**: `main` requires a PR + passing CI check to merge
  — you can't `git push origin main` directly. Push a branch, open a PR.
