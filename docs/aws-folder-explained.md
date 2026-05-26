# `aws/` folder explained

The [`aws/`](../aws/) directory groups **Amazon Web Services** deployment and **Bedrock** material. It does **not** contain the Streamlit application entrypoint; those stay in the repo root.

## Files

### `aws/README.md`

Short operational checklist:

- Bedrock region and **model access** in console.
- IAM permissions for **`bedrock:InvokeModel`**.
- How to set **`LLM_CONFIG_PATH`** and **`AWS_REGION`**.
- Where credentials come from (laptop vs EC2/ECS/Lambda).
- Reminder that **`FARMER_CHAT_DATA_DIR`** should be on **persistent storage** for multi-instance or replaceable containers.

For a longer version with cross-links, see [09 – AWS and Bedrock](09-aws-and-bedrock.md).

### `aws/env.example`

Template environment variables, not loaded automatically. Copy values into your shell, **`.env`**, or an **ECS task definition** / **Lambda configuration**:

- `AWS_REGION`
- Optional `LLM_CONFIG_PATH`, `FARMER_CHAT_DATA_DIR`
- Optional `AWS_PROFILE` for local dev
- Comments that OpenAI/Gemini keys are unused when on Bedrock-only text

See also [06 – Configuration reference](06-configuration-reference.md).

### `aws/iam-bedrock-invoke.json`

A minimal **IAM policy document** fragment (not a full role) demonstrating `Allow` on:

- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`

**`Resource` is `*`** — convenient for development; **tighten to specific model ARNs** in production and follow your org’s least-privilege standards.

Attach this JSON (or its statements) to:

- An **IAM user** or **role** used locally, or
- An **EC2 instance profile**, **ECS task role**, **Lambda execution role**, etc.

## Relationship to Python code

- Runtime behavior is implemented in [`llm/adapters.py`](../llm/adapters.py) (`BedrockAdapter`).
- YAML shape is defined in [`llm/config.py`](../llm/config.py).

## Related

- [09 – AWS and Bedrock](09-aws-and-bedrock.md)
- [config-llm-bedrock-example-explained.md](config-llm-bedrock-example-explained.md)
- [11 – Repository file index](11-repository-file-index.md)
