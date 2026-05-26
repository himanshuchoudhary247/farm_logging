# `config/llm.bedrock.example.yaml` explained

Companion guide to [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml). Use this file (or merge its `text` section into [`config/llm.yaml`](../config/llm.yaml)) when you want **Amazon Bedrock** for text generation.

## When to use this file

- You have **AWS credentials** (or an IAM role) with permission to call **Bedrock** in a chosen region.
- You have **enabled model access** in the Bedrock console for the model id you put in `model`.

## Line-by-line (conceptual)

Comments at the top of the YAML remind you:

1. **IAM auth** — No third-party LLM API key in the file.
2. **Console** — One-time **model access** for the account/region.

### `text` section

| Field | Example | Notes |
| ----- | ------- | ----- |
| `provider` | `bedrock` | Selects [`BedrockAdapter`](../llm/adapters.py). `aws-bedrock` is equivalent. |
| `model` | `anthropic.claude-3-haiku-20240307-v1:0` | Must match an id **available in your region**. Update when AWS renames or deprecates ids. |
| `api_key_env` | `""` | Intentionally empty; Bedrock does not use this for auth. |
| `region` | `us-east-1` | Passed to boto3 `bedrock-runtime`. If omitted in YAML, code uses `AWS_REGION` then defaults to `us-east-1`. |
| `aws_profile` | commented | Uncomment to force a **named profile** from `~/.aws/config` / credentials. |

### `voice` section

Placeholder values satisfy Pydantic (`voice` is required in the full config file). They do **not** enable voice in the UI. You may set `provider: bedrock` and a harmless `model` string for documentation.

## Activating the file

```bash
export AWS_REGION=us-east-1   # if not in YAML
export LLM_CONFIG_PATH=/absolute/path/to/farmer_chat/config/llm.bedrock.example.yaml
streamlit run app.py
```

## IAM

Attach a policy allowing **`bedrock:InvokeModel`** (and optionally streaming) to the principal that runs the app. See [`aws/iam-bedrock-invoke.json`](../aws/iam-bedrock-invoke.json) and [09 – AWS and Bedrock](09-aws-and-bedrock.md).

## Related

- [config-llm-yaml-explained.md](config-llm-yaml-explained.md)
- [06 – Configuration reference](06-configuration-reference.md)
- [aws-folder-explained.md](aws-folder-explained.md)
