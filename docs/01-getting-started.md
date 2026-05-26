# Getting started

This guide walks you from a clean clone to a running Streamlit app with sample data.

## Prerequisites

- **Python 3.9 or newer** (3.10+ also supported).
- A **terminal** and **git** (to clone the repo).
- For LLM features: either **API keys** (OpenAI/Google) or **AWS credentials** with Bedrock access.

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

Main packages: **Streamlit**, **Pydantic**, **PyYAML**, **bcrypt**, **openai**, **google-generativeai**, **boto3**, **python-dotenv**, **filelock**, **pytest** (dev).

## 4. Load environment variables (optional)

The app calls `load_dotenv()` at startup. You can place a **`.env`** file in the project root (do not commit it; it is gitignored if you add it to `.gitignore` for `.env`).

Example secrets:

```bash
OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...   # if using Gemini
# AWS_REGION=us-east-1 # if using Bedrock
```

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

```bash
streamlit run app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

## 9. Run tests

```bash
pytest
```

Tests use a temporary directory via `FARMER_CHAT_DATA_DIR`; see [08 – Testing](08-testing.md).

## Troubleshooting

| Symptom | What to check |
| ------- | ------------- |
| `ModuleNotFoundError` | Activate venv; `pip install -r requirements.txt` |
| LLM errors in the UI | Provider in YAML matches env vars or AWS IAM/region |
| Empty animal lists | Run `seed_data.py` or check `animals.json` and selected farmer |
| `data/` missing | Run seed script; ensure `FARMER_CHAT_DATA_DIR` points to the folder you expect |

## Next steps

- [02 – Application and UI](02-application-and-ui.md) – what each screen does.
- [09 – AWS and Bedrock](09-aws-and-bedrock.md) – running on AWS with Bedrock.
