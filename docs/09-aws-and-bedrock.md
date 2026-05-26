# AWS and Amazon Bedrock

This guide explains how **Amazon Bedrock** fits into the app and how to align the repository’s **AWS-oriented files** with your deployment.

For a shorter overview, see [`aws/README.md`](../aws/README.md).

## Architecture note

Application code stays at the **repository root** (`app.py`, `storage.py`, `llm/`, …). The [`aws/`](../aws/) folder holds **examples and IAM snippets**, not runnable app code.

## Amazon Bedrock (text LLM)

### How the app calls Bedrock

- Module: [`llm/adapters.py`](../llm/adapters.py), class **`BedrockAdapter`**.
- Boto3 client: **`bedrock-runtime`**.
- API: **`converse`** (not the older `invoke_model` raw body format).
- **Authentication:** IAM only. Credentials come from the default credential chain (environment, shared config, instance/task role).

### Configuration

Use `text.provider: bedrock` (or `aws-bedrock`) in YAML. Example file: [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml).

Important fields:

| YAML field | Role |
| ---------- | ---- |
| `model` | Bedrock model id (e.g. Anthropic Claude Haiku id in your region) |
| `region` | Overrides default; else `AWS_REGION`, else `us-east-1` |
| `aws_profile` | Optional boto3 profile name for local dev |
| `api_key_env` | Leave empty for Bedrock |

Set:

```bash
export LLM_CONFIG_PATH=/path/to/farmer_chat/config/llm.bedrock.example.yaml
export AWS_REGION=us-east-1
```

Or merge the `text:` block into [`config/llm.yaml`](../config/llm.yaml).

### AWS account steps

1. **Region:** Enable Bedrock in a supported region.
2. **Model access:** In the Bedrock console, request access to the models you reference in `model`.
3. **IAM:** Attach a policy allowing **`bedrock:InvokeModel`** (and optionally **`bedrock:InvokeModelWithResponseStream`**) on the target model ARNs—or use a tightened policy in production.

Sample policy file: [`aws/iam-bedrock-invoke.json`](../aws/iam-bedrock-invoke.json). Replace wildcard `Resource` with specific ARNs when hardening.

### Where credentials come from

| Environment | Typical source |
| ----------- | -------------- |
| Laptop | `~/.aws/credentials`, SSO, or env vars |
| EC2 | Instance profile |
| ECS / EKS | Task role / IRSA |
| Lambda | Execution role |

## File reference under `aws/`

| File | Description |
| ---- | ----------- |
| [`aws/README.md`](../aws/README.md) | Concise Bedrock + persistence notes |
| [`aws/env.example`](../aws/env.example) | Example `AWS_REGION`, optional `LLM_CONFIG_PATH`, `FARMER_CHAT_DATA_DIR` |
| [`aws/iam-bedrock-invoke.json`](../aws/iam-bedrock-invoke.json) | Dev-oriented IAM statement (narrow for prod) |

## Persisting `data/` on AWS

[`storage.py`](../storage.py) writes JSON to **`FARMER_CHAT_DATA_DIR`**. On ephemeral containers:

- Mount **EFS**, **EBS**, or another **persistent volume** to that path.
- Or plan a future migration to S3 / RDS (not in v1).

Single-container demos can use a host bind mount.

## Voice block and Bedrock

The **`voice`** section in YAML can list Bedrock-related fields for documentation and future features. **The current UI does not call voice models.**

## Related docs

- [05 – LLM providers and prompts](05-llm-providers-and-prompts.md)
- [06 – Configuration reference](06-configuration-reference.md)
- [10 – Security and operations](10-security-and-operations.md)
