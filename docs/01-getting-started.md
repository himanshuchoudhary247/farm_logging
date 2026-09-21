# Getting started

This guide walks you from a clean clone to a running FarmHerd API + React frontend with sample data.

## Prerequisites

- **Python 3.10 or newer.** This is a hard requirement, not a suggestion:
  `google-adk` (the agent orchestration layer behind
  `services/chat_orchestrator/adk_router.py`, `services/query_agent/
  adk_agent.py`, `services/weather_alert/adk_agent.py`) needs 3.10+, and
  `services/api_service/main.py` imports it unconditionally at startup.
  A 3.9 interpreter will fail to boot the server at all. The project's own
  venv should be built with 3.10+ (this session used 3.13).
- A **terminal** and **git** (to clone the repo).
- **AWS credentials with Bedrock access** -- required, not optional (see
  step 4). This project's real model backend is AWS Bedrock; the
  OpenAI/Gemini packages in `requirements.txt` are unused by the current
  chat/appointment/query/weather agents.

## 1. Clone and enter the project

```bash
cd /path/to/parent
git clone <your-repo-url> farmer_chat
cd farmer_chat
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate    # Linux / macOS
# .venv\Scripts\activate     # Windows
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

Main packages: **FastAPI**, **uvicorn**, **Pydantic**, **PyYAML**, **bcrypt**, **boto3** (real Bedrock backend), **google-adk[extensions]** (agent orchestration -- needs Python 3.10+), **filelock**, **pytest** (dev). `openai`/`google-generativeai` are present but unused by the current chat/appointment/query/weather agents.

## 4. Configure environment variables (required)

The app does **not** auto-load `.env` -- there is no `load_dotenv()` call
anywhere in this codebase, despite what you might expect. `.env` is a
template you must `source` into your shell yourself before starting the
server or the tests, every time (or export the same vars another way):

```bash
cp .env.example .env
# edit .env with real values -- see below
set -a; source .env; set +a
uvicorn services.api_service.main:app --port 8001
```

`.env` is gitignored and never committed; whoever set up this project's
AWS account shares the real values with you separately (credentials do
not belong in git, Slack, or this doc).

Required (the server hard-fails at startup without these -- see
`utils/env_check.py`):

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
VOICE_BUCKET=...          # S3 bucket for voice audio uploads
VOICE_S3_BUCKET=...       # same bucket -- transcribe.py reads this name specifically
```

See `.env.example` in the repo root for the full annotated list (STT/TTS
provider selection, CORS, optional API-key gate, flokiq integration,
data-dir override) and [06 – Configuration reference](06-configuration-reference.md).

## 5. Configure the LLM

By default the app reads [`config/llm.yaml`](../config/llm.yaml). You can point elsewhere:

```bash
export LLM_CONFIG_PATH=/absolute/path/to/my-llm.yaml
```

See [06 – Configuration reference](06-configuration-reference.md) and [05 – LLM providers](05-llm-providers-and-prompts.md).

## 6. Create sample data (farmers, animals, admin)

```bash
python scripts/seed_data.py
```

This writes JSON under `data/` (or under `FARMER_CHAT_DATA_DIR` if set). It creates:

- One **admin** account and **100 farmer** accounts with animals.
- Empty `health_logs.json` and `consultations.json`.

If you already have data and only need an admin row:

```bash
python scripts/add_admin_user.py
```

Details: [07 – Scripts](07-scripts.md).

## 7. Default logins (development only)

| Account | Username | Password |
| -------- | -------- | -------- |
| Administrator | `admin` | `admin123` |
| First demo farmer | `farmer001` | `changeme` |

**Change these before any production use.** See [04 – Authentication](04-authentication-and-roles.md) and [10 – Security](10-security-and-operations.md).

## 8. Run the app

Backend (FastAPI, port 8001) -- remember step 4's `source .env` first:

```bash
set -a; source .env; set +a
uvicorn services.api_service.main:app --port 8001
```

The chat/appointment/weather/query assistant's real frontend is
**`flokiquser`**, a separate sibling repo/directory, not `frontend/` in
this repo. `frontend/` here is the older, separate onboarding/advisory
website (still functional, unrelated to the chat assistant). To run the
assistant UI:

```bash
cd ../flokiquser   # sibling directory, separate git repo
npm install
npm run dev        # defaults to :5174; VITE_ASSISTANT_API_BASE in its own
                    # .env must point at this backend (http://127.0.0.1:8001
                    # for local dev)
```

## 9. Run tests

```bash
pytest
```

A handful of tests (`test_*_adk.py`) exercise the `google-adk` orchestration
layer and use `pytest.importorskip("google.adk")` -- they silently skip
under a pre-3.10 interpreter and run for real under your 3.10+ venv. If
`pytest` reports skips you weren't expecting, check which Python is
actually running it (`python3 --version`) -- a stray system Python without
your venv active is the usual cause.

Tests use a temporary directory via `FARMER_CHAT_DATA_DIR`; see [08 – Testing](08-testing.md).

## Troubleshooting

| Symptom | What to check |
| ------- | ------------- |
| `ModuleNotFoundError` | Activate venv; `pip install -r requirements.txt` |
| `[ENV ERROR] Missing required environment variables` at startup | You forgot to `source .env` into the shell before running uvicorn -- see step 4, this project does not auto-load it |
| `ModuleNotFoundError: No module named 'google.adk'` | Your active Python is older than 3.10, or you're not in the venv where `requirements.txt` was installed |
| LLM errors in the UI | AWS credentials/region in `.env` are correct and have Bedrock access in that region |
| Empty animal lists | Run `seed_data.py` or check `animals.json` and selected farmer |
| `data/` missing | Run seed script; ensure `FARMER_CHAT_DATA_DIR` points to the folder you expect |

## Next steps

- [09 – AWS and Bedrock](09-aws-and-bedrock.md) – running on AWS with Bedrock.
