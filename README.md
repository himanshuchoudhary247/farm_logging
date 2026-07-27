# Farmer Livestock Assistant

Streamlit app for farmers: general livestock Q&A, structured health logging, conversational issue triage, weather advisories, and voice-enabled onboarding. Data is stored as JSON files on disk.

## Live Deployment (EC2)

| Service | Port | URL |
|---|---|---|
| Weather Advisory API | 8000 | `https://65.0.181.84:8000` |
| Weather Streamlit UI | 8501 | `https://65.0.181.84:8501` |
| Onboarding API | 8004 | `https://65.0.181.84:8004` |
| Onboarding Streamlit UI | 8503 | `https://65.0.181.84:8503` |

**Instance:** `i-017b9a61a29f8c1e0` (Ubuntu, ap-south-1)
**Key pair:** `temp-weather-key` (PEM at `~/.ssh/temp-weather-key.pem`)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    EC2 (65.0.181.84)                     │
├─────────────────────┬───────────────────────────────────┤
│  Weather Services   │  Onboarding Services              │
│  ┌───────────────┐  │  ┌─────────────────────────────┐  │
│  │ Streamlit UI  │  │  │ Streamlit UI (Chat + Voice) │  │
│  │ Port 8501     │  │  │ Port 8503 (HTTPS)           │  │
│  └───────┬───────┘  │  └──────────┬──────────────────┘  │
│          │          │             │                      │
│  ┌───────▼───────┐  │  ┌──────────▼──────────────────┐  │
│  │ Weather API   │  │  │ Onboarding API              │  │
│  │ Port 8000     │  │  │ Port 8004 (HTTPS)           │  │
│  └───────────────┘  │  └──────────┬──────────────────┘  │
│                     │             │                      │
│  ┌───────────────┐  │  ┌──────────▼──────────────────┐  │
│  │ Disease       │  │  │ AWS Bedrock                 │  │
│  │ Catalogue     │  │  │ Mistral Large 3             │  │
│  │ (JSON)        │  │  │ (Field Extraction)          │  │
│  └───────────────┘  │  └─────────────────────────────┘  │
│                     │                                    │
│  ┌───────────────┐  │  ┌─────────────────────────────┐  │
│  │ Google Speech  │  │  │ Self-Signed SSL            │  │
│  │ Recognition   │  │  │ cert.pem / key.pem         │  │
│  └───────────────┘  │  └─────────────────────────────┘  │
└─────────────────────┴───────────────────────────────────┘
```

## Models & Services

### Production (EC2)

| Model / Service | Provider | Purpose |
|---|---|---|
| `mistral.mistral-large-3-675b-instruct` | AWS Bedrock | Farmer field extraction from conversation |
| Google Speech Recognition | Google (via SpeechRecognition pkg) | Voice-to-text transcription |
| ICAR-NIVEDI Disease Catalogue | Static JSON | Sheep/goat disease data (5 states, 8 diseases) |

### Development / Test (Local)

| Model | Provider | Purpose |
|---|---|---|
| `deepseek.v3-v1:0` | AWS Bedrock | Dev/test UIs |
| `anthropic.claude-3-sonnet-20240229-v1:0` | AWS Bedrock | Legacy LLM adapter |
| `mistral.mistral-large-2402-v1:0` | AWS Bedrock | Legacy extraction |
| Amazon Transcribe | AWS | Voice-to-text (alternative) |
| AWS Polly | AWS | Text-to-speech |

### OpenCode Swarm Agents

| Model | Agents |
|---|---|
| `opencode/big-pickle` | architect, explorer, sme, researcher, reviewer, docs, critic |
| `opencode/gpt-5-nano` | test_engineer, critic_sounding_board, curators |

## Setup

Requires Python 3.9+.

```bash
cd /path/to/farmer_chat
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Additional Dependencies (EC2)

```bash
pip install --break-system-packages SpeechRecognition
```

## Services

### Weather Advisory

- **API** (`api_server.py`): `/health`, `/weather/alert`, `/weather/seasonal-advisory`
- **UI** (`weather_streamlit_app.py`): 4 tabs — Risk Alert, SMS Advisory, Historical Data, Weekly Insight
- **Disease data** (`disease_catalogue.json`): ICAR-NIVEDI NADRES catalogue

### Onboarding

- **API** (`onboarding_api.py`): `/health`, `/onboarding` (POST), `/voice`, `/voice_done`
- **UI** (`onboarding_app.py`): Chat Mode (voice + text) + Manual Form
- **Voice input**: `st.audio_input` → Google Speech Recognition → Bedrock LLM extraction
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
| `weather-sg` | 8501, 8000 | Weather services (public) |
| `onboarding-sg` | 8502, 8503, 8004 | Onboarding services (public) |

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
# Weather services
cd farmer-weather
python3 api_server.py &                    # Port 8000
streamlit run app.py --server.port 8501    # Port 8501

# Onboarding services
cd onboarding-weather
python3 onboarding_api.py &                # Port 8004 (HTTPS)
streamlit run onboarding_app.py --server.port 8503 --server.sslCertFile cert.pem --server.sslKeyFile key.pem  # Port 8503 (HTTPS)
```

## Service-split Mode

The codebase supports lightweight multi-service split:

- `services/api_service/main.py` — data/auth API
- `services/llm_service/main.py` — LLM completion API
- `app.py` — Streamlit UI (calls services via `gateways.py`)

Set `APP_MODE=services` to enable service mode.

## Single-worker Note

JSON writes use `filelock`. For multiple Streamlit workers, prefer one worker or migrate to SQLite later.
