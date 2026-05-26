# LLM providers and prompts

Text generation is abstracted behind a small **adapter** interface. The active provider comes from [`config/llm.yaml`](../config/llm.yaml) (or `LLM_CONFIG_PATH`).

## Module layout

| File | Responsibility |
| ---- | -------------- |
| [`llm/config.py`](../llm/config.py) | Load YAML; Pydantic models `TextLLMConfig`, `VoiceLLMConfig`, `LLMConfigFile`; `get_api_key` for API-key providers |
| [`llm/adapters.py`](../llm/adapters.py) | `TextAdapter` ABC; OpenAI, Gemini, Bedrock implementations; `get_text_adapter()` factory |
| [`llm/prompts.py`](../llm/prompts.py) | `GENERAL_SYSTEM`, `TRIAGE_SYSTEM` strings |
| [`llm/__init__.py`](../llm/__init__.py) | Re-exports `TextAdapter`, `get_text_adapter` |

## Adapter interface

```text
complete(messages: list[dict[str, str]], system: str | None) -> str
```

Each message dict has `role` (`user` or `assistant` in practice; adapters filter as needed) and `content` (string).

- **General Q&A:** full thread + `GENERAL_SYSTEM` as `system`.
- **Describe issue:** full thread + `TRIAGE_SYSTEM` as `system`.

## Providers

### OpenAI (`provider: openai`)

- Client: official **`openai`** Python SDK (`OpenAI`).
- **Config:** `model` (e.g. `gpt-4o-mini`), `api_key_env` (non-empty name of env var holding the key).
- **Calls:** Chat Completions; optional `system` message prepended.

### Gemini / Google (`provider: gemini` or `google`)

- Client: **`google-generativeai`**.
- **Config:** `model`, `api_key_env`.
- **Calls:** `GenerativeModel` with `system_instruction`; prior turns as chat history; last user message sent.

### Amazon Bedrock (`provider: bedrock` or `aws-bedrock`)

- Client: **`boto3`** `bedrock-runtime`, **`converse`** API.
- **Auth:** IAM (instance profile, task role, `~/.aws/credentials`, env vars, SSO). No API key in YAML for Bedrock.
- **Config:** `model` is the **Bedrock model id** (e.g. `anthropic.claude-3-haiku-20240307-v1:0`), `region` optional (falls back to `AWS_REGION`, then `us-east-1`), `aws_profile` optional for named profile.
- **Calls:** `converse` with `messages`, optional `system` block, `inferenceConfig.maxTokens` 4096.

See [09 – AWS and Bedrock](09-aws-and-bedrock.md).

## Voice section in YAML

[`VoiceLLMConfig`](../llm/config.py) mirrors optional `region` and `aws_profile` for future use. **The Streamlit app does not read the voice block yet**; only `text` is used for chat. Keeping `voice` in the file validates the full config and documents future voice provider settings.

## System prompts

### `GENERAL_SYSTEM` ([`llm/prompts.py`](../llm/prompts.py))

Used for **General Q&A**: smallholder livestock focus, cautious guidance, escalation to a veterinarian, concise answers.

### `TRIAGE_SYSTEM`

Used for **Describe issue**: short follow-up questions (at most about two per reply in instructions), no definitive diagnosis, urgent vet cues, mobile-friendly brevity.

To change behavior, edit `llm/prompts.py` or refactor to load prompts from YAML (not implemented in v1).

## Factory

`get_text_adapter()` reads [`load_llm_config().text`](../llm/config.py) and instantiates the matching adapter. Unknown `provider` raises `ValueError`.

## Caching in the UI

[`app.py`](../app.py) uses `@st.cache_resource` on `_text_adapter()`. Changing YAML or credentials may require **restarting Streamlit** or clearing cache from the app menu for changes to apply.

## Related

- [06 – Configuration reference](06-configuration-reference.md) – every YAML field and env var.
- [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml) – Bedrock-only sample file.
