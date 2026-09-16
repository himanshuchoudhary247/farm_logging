# Farmer Livestock Assistant (FarmHerd)

FarmHerd AI — farmer onboarding + livestock management platform. React frontend,
FastAPI backend, AWS Bedrock LLM extraction, browser-based voice input/output.
Data is stored as JSON files on disk.

## Live Deployment (EC2)

| Service | Port | URL |
|---|---|---|
| Farmer Chat API (FastAPI) | 8001 | `https://65.0.181.84/api/` |
| Weather Advisory API | 8000 | `https://65.0.181.84/weather-api/` |
| Onboarding API | 8004 | `https://65.0.181.84/onboarding-api/` |
| React Frontend | 443 | `https://65.0.181.84` |

**Instance:** `i-017b9a61a29f8c1e0` (Ubuntu, ap-south-1)
**Key pair:** `temp-weather-key` (PEM at `~/.ssh/temp-weather-key.pem`)

### Public Entry Point

The public entry point is `https://65.0.181.84`. Nginx serves the React
frontend and routes API traffic by path:

- `/` — FarmHerd React app (advisory, animals, appointments, voice intake, onboarding)
- `/api/` — backend API (FastAPI, port 8001)
- `/weather-api/` — weather advisory API (port 8000)
- `/onboarding-api/` — onboarding extraction API (port 8004)
- `/api/docs` — FastAPI endpoint reference

Deployment template: `deploy/nginx-farmer-chat.conf`, `deploy/farmer-api.service`.

The React website lives in `frontend/`:

```bash
cd frontend
npm install
npm run build
```

The compiled `frontend/dist/` directory is served by Nginx from
`/var/www/farmer-web/` on the EC2 host.

### Showcase Demo

The project includes one clearly labeled synthetic showcase account. It is safe
for demonstrations and contains no real farmer data:

- Username: `demo`
- Password: `farmherd-demo`
- Farmer ID: `demo-farmer`
- Demo PIN: `583101`

Run `python scripts/seed_demo_user.py` to create or refresh the account in a
configured data directory. The website's **Live Showcase** card opens the
personalized advisory flow with the demo PIN prefilled.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      EC2 (65.0.181.84)                       │
├──────────────────────────────────────────────────────────────┤
│  Nginx (443)                                                 │
│  ├── /            → React frontend (/var/www/farmer-web)     │
│  ├── /api/        → FastAPI farmer API        (port 8001)    │
│  ├── /weather-api/→ Weather advisory API      (port 8000)    │
│  └── /onboarding-api/ → Onboarding extraction (port 8004)    │
│                                                              │
│  FastAPI farmer API (services/api_service/main.py)          │
│  ├── auth, animals, health logs, appointments               │
│  ├── voice appointment supervisor (Web Speech + Bedrock)    │
│  └── query agent (SQL over JSON stores)                     │
│                                                              │
│  AWS Bedrock (mistral.mistral-large-3-675b-instruct)        │
│  └── field extraction, intent detection                     │
│                                                              │
│  Browser (React)                                             │
│  ├── SpeechRecognition  → voice input (~200ms)              │
│  └── speechSynthesis     → spoken responses (local)          │
└──────────────────────────────────────────────────────────────┘
```

Voice latency: follow-up turns ~100-300ms (rule fast-path + browser TTS),
LLM turns ~1.2s. LATENCY-prefixed logs are emitted across the pipeline.

## Models & Services

### Production (EC2)

| Model / Service | Provider | Purpose |
|---|---|---|
| `mistral.mistral-large-3-675b-instruct` | AWS Bedrock | Farmer field extraction from conversation |
| Web Speech API | Browser | Voice-to-text and text-to-speech |
| ICAR-NIVEDI Disease Catalogue | Static JSON | Sheep/goat disease data (5 states, 8 diseases) |
| AWS Transcribe / Polly | AWS | Legacy server-side voice fallback |

### OpenCode Swarm Agents

| Model | Agents |
|---|---|
| `opencode/big-pickle` | architect, explorer, sme, researcher, reviewer, docs, critic |
| `opencode/gpt-5-nano` | test_engineer, critic_sounding_board, curators |

## Setup

Requires Python 3.12+ (bumped from 3.9 on 2026-09-13 — `aws_sdk_bedrock_runtime`, used for Nova Sonic probing, requires 3.12+).

```bash
cd /path/to/farmer_chat
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Services

### Farmer Chat API (`services/api_service/main.py`)

- Auth (`/auth/login`), animals, health logs, appointments, consultations
- `/farmers/{id}/appointments/voice/*` — voice appointment supervisor
  (browser speech recognition posts text; `include_audio=false` skips Polly
  when the browser speaks locally)
- `/farmers/{id}/query` — natural-language query agent
- `/alerts/general/{pin}` — cached PIN alerts
- `/farmers/{id}/advisory/personalized` — personalized advisory

### Onboarding

- **API** (`onboarding_api.py`, port 8004): `/health`, `/onboarding` (POST)
- **Frontend**: conversational onboarding with thumbs up/down confirmation
  and latency panel (React)
- **Extraction**: Mistral Large 3 with conversation context, Hindi/Kannada support

### Onboarding API Request/Response

```json
// POST /onboarding
{
  "text": "I am Ramu from Bangalore with 200 sheep",
  "existing": {"farmer": {"name": "Himanshu"}, "farm": {}},
  "current_field": "city",
  "conversation_history": [
    {"role": "assistant", "content": "What is your name?"},
    {"role": "user", "content": "Himanshu"}
  ]
}

// Response
{
  "farmer": {"name": "Ramu", "city": "Bangalore"},
  "farm": {"sheepCount": 200},
  "missing_fields": ["phone", "aadharNo", ...],
  "follow_up_question": "What is your phone number?",
  "current_field": "city",
  "complete": false
}
```

## Testing

```bash
# Run all tests
pytest

# Run onboarding accuracy test (36 tests, 6 categories)
python test_onboarding.py
```

### Test Coverage

| Category | Tests | Accuracy |
|---|---|---|
| Single Word Answers | 12 | 100% |
| Conversational Phrases | 8 | 100% |
| Multi-Field Extraction | 3 | 100% |
| Hindi Patterns | 5 | 100% |
| Multi-Turn Flow | 4 | 100% |
| Edge Cases | 4 | 100% |
| **Total** | **36** | **100%** |

## AWS Configuration

**Account:** `198799425726` | **Region:** `ap-south-1`

### Security Groups

| Group | Ports | Purpose |
|---|---|---|
| `admin-sg` | 22 | SSH (122.168.70.175, 183.82.105.114, 122.168.65.158) |
| `weather-sg` | 8000 | Weather API (via nginx) |
| `onboarding-sg` | 8004 | Onboarding API (via nginx) |
| `web-sg` | 443 | Public HTTPS (nginx) |

### Credentials

- AWS credentials configured from local `~/.aws/credentials` (user `Himanshu`)
- Bedrock access in `ap-south-1` region
- Self-signed SSL certs in `/home/ubuntu/onboarding-weather/`

## Documentation

- [`docs/README.md`](docs/README.md) — Full documentation hub
- [`aws/README.md`](aws/README.md) — AWS infrastructure
- [`aws/infra/README.md`](aws/infra/README.md) — Infrastructure details

## Run

```bash
# Farmer Chat API (port 8001)
uvicorn services.api_service.main:app --host 127.0.0.1 --port 8001

# Onboarding API (port 8004, HTTPS)
python3 onboarding_api.py &

# React frontend dev server
cd frontend && npm run dev
```

## PIN Alert Cache

Configured PIN codes are listed in `config/pincode_profiles.yaml`. Refresh intervals
are configured independently in `config/cache_settings.yaml`; the refresh job reuses
each API's existing file until that API's interval expires, then rebuilds the PIN's
`general_alert.json`.

Run a refresh manually or from cron:

```bash
python3 scripts/refresh_caches.py
python3 scripts/refresh_caches.py --pin 583101
python3 scripts/refresh_caches.py --service feed_prices
```

Example cron entry (from the repository root):

```cron
*/30 * * * * cd /path/to/farmer_chat && /path/to/.venv/bin/python scripts/refresh_caches.py >> data/cache-refresh.log 2>&1
```

Cached files are written under `data/cache/<pin>/`. The API serves
`GET /alerts/general/{pin}` and `POST /farmers/{farmer_id}/advisory/personalized`.
The per-service cron template is in `deploy/cache-refresh.cron`; it schedules
forecast/THI, seasonal advisory, and feed-price refreshes independently.

## Single-worker Note

JSON writes use `filelock`. Prefer one API worker or migrate to SQLite later.

## Model Latency Benchmark

Compare candidate Bedrock models for extraction latency + quality on the server:

```bash
python3 scripts/benchmark_models.py
```

<!-- CI/CD PR-review flow verified working 2026-09-17 -->
