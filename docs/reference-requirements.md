# `requirements.txt` reference

[`requirements.txt`](../requirements.txt) lists **pip** dependencies with **minimum versions** (compatible with Python **3.9+**).

| Package | Role in this project |
| ------- | -------------------- |
| `streamlit` | Web UI / [`app.py`](../app.py) |
| `pydantic` | Validate config and JSON-backed models in [`models.py`](../models.py), [`llm/config.py`](../llm/config.py) |
| `pyyaml` | Parse [`config/llm.yaml`](../config/llm.yaml) |
| `bcrypt` | Password hashing in [`auth.py`](../auth.py) |
| `openai` | OpenAI chat adapter in [`llm/adapters.py`](../llm/adapters.py) |
| `google-generativeai` | Gemini adapter |
| `boto3` | Amazon Bedrock **`bedrock-runtime`** client |
| `python-dotenv` | Optional `.env` loading in [`app.py`](../app.py) |
| `filelock` | Serialize JSON writes in [`storage.py`](../storage.py) |
| `pytest` | Test runner ([`tests/`](../tests/)) |

## Installing

```bash
pip install -r requirements.txt
```

Use a **virtual environment** recommended in [01 – Getting started](01-getting-started.md).

## Pinning in production

For reproducible deploys, consider generating a **lock file** (e.g. `pip freeze` or Poetry/pip-tools) from a tested environment; the repo intentionally keeps simple `>=` constraints for flexibility.

## Related

- [01 – Getting started](01-getting-started.md)
- [05 – LLM providers](05-llm-providers-and-prompts.md)
