# Farmer livestock assistant

Streamlit app for farmers: general livestock Q&A, structured health logging, and conversational issue triage. Data is stored as JSON files on disk.

## Documentation

**Full documentation hub:** [`docs/README.md`](docs/README.md) — getting started, UI, storage, auth, LLM (OpenAI / Gemini / Bedrock), configuration, scripts, testing, AWS, and security. Per-file deep dives (e.g. `llm.yaml`, `aws/` bundle) are linked from there.

## Setup

Requires Python 3.9+.

```bash
cd /path/to/farmer_chat
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run tests:

```bash
pytest
```

Create data files (100 demo farmers + one admin; logins below):

```bash
python scripts/seed_data.py
```

If you already have `data/` and only need an admin account:

```bash
python scripts/add_admin_user.py
```

**Default logins (change in production):**

| User        | Username   | Password   |
| ----------- | ---------- | ---------- |
| Admin       | `admin`    | `admin123` |
| Demo farmer | `farmer001` | `changeme` |

**LLM providers**

- **OpenAI / Gemini** – Set API keys (never commit them):

  ```bash
  export OPENAI_API_KEY=sk-...
  # Gemini: set config/llm.yaml provider to gemini and:
  export GEMINI_API_KEY=...
  ```

- **Amazon Bedrock** – IAM-based (no LLM API key). See [`aws/README.md`](aws/README.md). Use `config/llm.bedrock.example.yaml` or set `text.provider: bedrock` with a Bedrock `model` id and `region`.

Optional:

- `LLM_CONFIG_PATH` — path to YAML (defaults to `config/llm.yaml`).
- `FARMER_CHAT_DATA_DIR` — directory for JSON data (defaults to `./data`).
- `AWS_REGION` — used by Bedrock when `region` is omitted in YAML.

## Run

```bash
streamlit run app.py
```

## Service-split mode (new)

The codebase now supports a lightweight multi-service split while keeping monolith mode as default.

- `services/api_service/main.py` — data/auth API
- `services/llm_service/main.py` — LLM completion API
- `app.py` — Streamlit UI (can call services via `gateways.py`)

### Start split services

Terminal 1:

```bash
uvicorn services.api_service.main:app --host 0.0.0.0 --port 8001
```

Terminal 2:

```bash
uvicorn services.llm_service.main:app --host 0.0.0.0 --port 8002
```

Terminal 3:

```bash
export APP_MODE=services
export API_SERVICE_URL=http://localhost:8001
export LLM_SERVICE_URL=http://localhost:8002
streamlit run app.py
```

If `APP_MODE` is unset (or `monolith`), Streamlit uses in-process modules directly.

## Voice config

`voice` section in `config/llm.yaml` is reserved for a future release; only `text` is used by the app today.

## Single-worker note

JSON writes use `filelock`. For multiple Streamlit workers, prefer one worker or migrate to SQLite later.
