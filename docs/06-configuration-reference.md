# Configuration reference

This document lists **environment variables** and **YAML fields** used by the Farmer livestock assistant.

## Environment variables

| Variable | Required | Default / behavior |
| -------- | -------- | ------------------ |
| `LLM_CONFIG_PATH` | No | If unset: [`config/llm.yaml`](../config/llm.yaml) under project root (resolved from [`llm/config.py`](../llm/config.py)). |
| `FARMER_CHAT_DATA_DIR` | No | If unset: [`data/`](../data/) next to project root. All JSON persistence uses this directory. |
| `OPENAI_API_KEY` | When `text.provider` is **openai** | Read via `api_key_env` in YAML (typically `OPENAI_API_KEY`). |
| `GEMINI_API_KEY` | When provider is **gemini** / **google** | Same pattern as OpenAI with the name in YAML. |
| `AWS_REGION` | Recommended for **Bedrock** | Used when `text.region` is omitted in YAML. |
| `AWS_PROFILE` | No | Optional; Bedrock can also use per-config `aws_profile` in YAML. |
| Standard AWS vars | For Bedrock without profile file | e.g. `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, session token if applicable. |

**dotenv:** If a `.env` file exists at the project root, `python-dotenv` loads it when the API service starts. Keep `.env` out of version control.

---

## `config/llm.yaml` structure

The file must parse as a single mapping with **`text`** and **`voice`** keys (both required by Pydantic).

### `text` — `TextLLMConfig`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `provider` | string | `openai`, `gemini`, `google`, `bedrock`, or `aws-bedrock`. |
| `model` | string | OpenAI model name, Gemini model id, or Bedrock foundation model id. |
| `api_key_env` | string | Name of environment variable holding the API key. **Empty string** for Bedrock (IAM only). Default `""` in schema. |
| `region` | string or omitted | AWS region for Bedrock runtime. Falls back to `AWS_REGION`, then `us-east-1`. |
| `aws_profile` | string or omitted | Named AWS profile for boto3 Session. |

### `voice` — `VoiceLLMConfig`

Same fields as above structurally (`provider`, `model`, `api_key_env`, optional `region`, `aws_profile`). **Not consumed by the voice pipeline** (which uses `BEDROCK_MODEL_ID` and AWS env vars); reserved for per-voice-provider overrides.

### Example: OpenAI (default style)

```yaml
text:
  provider: openai
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
voice:
  provider: gemini
  model: gemini-2.0-flash
  api_key_env: GEMINI_API_KEY
```

### Example file: Bedrock

See [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml). Point the app at it:

```bash
export LLM_CONFIG_PATH=/path/to/farmer_chat/config/llm.bedrock.example.yaml
```

---

## Other project files (reference)

| File | Purpose |
| ---- | ------- |
| [`aws/env.example`](../aws/env.example) | Example env block for AWS-oriented runs |
| [`aws/iam-bedrock-invoke.json`](../aws/iam-bedrock-invoke.json) | Sample IAM policy fragment for Bedrock invoke |
| [`pytest.ini`](../pytest.ini) | `pythonpath = .` for tests |

---

## Dependency lockfile

`requirements.txt` declares floors (`>=`) only, for readability -- the
actual pinned versions used in CI and production live in
`requirements.lock.txt` (plain `pip freeze` output, exact versions
including transitives). The "Check lockfile matches requirements.txt" step
in `.github/workflows/ci.yml` installs `requirements.txt` in a fresh venv
with the lockfile as constraints (`-c requirements.lock.txt`) and then runs
`scripts/check_lockfile.py`: every installed package must be pinned in the
lockfile at that version. So CI fails when `requirements.txt` gains or bumps
a dependency without the lockfile being regenerated -- but a new upstream
release alone never fails it.

To regenerate after deliberately bumping a dependency in `requirements.txt`:

```bash
python -m venv /tmp/relock-venv
/tmp/relock-venv/bin/pip install -r requirements.txt
/tmp/relock-venv/bin/pip freeze > requirements.lock.txt
```

Commit the updated `requirements.lock.txt` alongside the `requirements.txt`
change. Production installs from the lockfile (see
`deploy/bootstrap.sh`), never from the floors directly -- this is what
would have caught the `litellm`/`mcp` incident (a newer `litellm`, pulled
in transitively by `google-adk[extensions]`, hard-imported a package
nothing declared) before it reached a running server.

---

## Validation errors

- **Missing API key:** `get_api_key` raises if `api_key_env` is empty (for key-based providers) or the env var is unset/empty.
- **Unknown provider:** `get_text_adapter()` raises `ValueError`.
- **Invalid YAML / missing keys:** Pydantic validation error on startup when config loads.

---

## Related

- [05 – LLM providers and prompts](05-llm-providers-and-prompts.md)
- [09 – AWS and Bedrock](09-aws-and-bedrock.md)
- [01 – Getting started](01-getting-started.md)
