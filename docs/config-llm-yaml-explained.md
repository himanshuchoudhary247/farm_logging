# `config/llm.yaml` explained

This document describes the **default** LLM configuration file at [`config/llm.yaml`](../config/llm.yaml). The app loads it unless **`LLM_CONFIG_PATH`** points to another file.

## Purpose

The file is a single **YAML** document loaded by [`load_llm_config()`](../llm/config.py) and validated by **Pydantic** models `LLMConfigFile`, `TextLLMConfig`, and `VoiceLLMConfig`.

- **`text`** — Used today by the Streamlit app for all chat completions.
- **`voice`** — Parsed and stored for forward compatibility; **the UI does not call voice models yet.**

## Top-level structure

```yaml
text:
  # ...
voice:
  # ...
```

Both keys are **required**. Omitting `voice` causes validation to fail.

## `text` block (active)

| Key | Typical value | Meaning |
| --- | ------------- | ------- |
| `provider` | `openai` | Which adapter `get_text_adapter()` builds. Alternatives: `gemini`, `google`, `bedrock`, `aws-bedrock`. |
| `model` | `gpt-4o-mini` | Provider-specific model identifier. |
| `api_key_env` | `OPENAI_API_KEY` | Name of the **environment variable** that holds the secret key. Not the key itself. For Bedrock, use `""`. |
| `region` | omitted or `us-east-1` | AWS region for Bedrock (`bedrock-runtime`). Optional if `AWS_REGION` is set. |
| `aws_profile` | omitted | Optional boto3 profile name for local AWS credentials. |

**OpenAI flow:** [`OpenAIAdapter`](../llm/adapters.py) calls `get_api_key(api_key_env)` and passes the key to the official OpenAI client.

## `voice` block (reserved)

The schema requires **`provider`**, **`model`**, and allows optional **`api_key_env`**, **`region`**, **`aws_profile`**.

In the default file, `voice` often mirrors a second vendor (e.g. Gemini) so you can switch voice integrations later without restructuring YAML. **Changing this block does not change current app behavior** because no voice code path reads it.

## Switching providers without editing defaults

Prefer overriding the file path:

```bash
export LLM_CONFIG_PATH=/path/to/custom.yaml
streamlit run app.py
```

For Bedrock-only setups, start from [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml); see [config-llm-bedrock-example-explained.md](config-llm-bedrock-example-explained.md).

## Validation and errors

- **Wrong types or missing keys:** Pydantic raises when the app loads config (typically at first LLM use or import of `get_text_adapter`).
- **Empty `api_key_env` for OpenAI/Gemini:** `get_api_key` raises a clear error.
- **Bedrock without IAM permission:** AWS SDK raises `ClientError` at runtime when sending a message.

## Related

- [06 – Configuration reference](06-configuration-reference.md)
- [05 – LLM providers and prompts](05-llm-providers-and-prompts.md)
- [docs/README.md](README.md)
