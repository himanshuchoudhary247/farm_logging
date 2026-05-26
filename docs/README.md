# Documentation index

Detailed guides for the **Farmer livestock assistant** codebase. Start with [Getting started](01-getting-started.md), then dive into specific topics.

| Guide | Description |
| ----- | ----------- |
| [01 – Getting started](01-getting-started.md) | Install, env vars, run the app, seed data, default logins |
| [02 – Application and UI](02-application-and-ui.md) | Streamlit entrypoint, tabs, session state, admin “act as farmer” |
| [03 – Data models and storage](03-data-models-and-storage.md) | JSON files, Pydantic models, locks, atomic writes |
| [04 – Authentication and roles](04-authentication-and-roles.md) | bcrypt, farmers vs admins, adding users |
| [05 – LLM providers and prompts](05-llm-providers-and-prompts.md) | OpenAI, Gemini, Bedrock adapters; system prompts |
| [06 – Configuration reference](06-configuration-reference.md) | All env vars and `llm.yaml` / YAML fields |
| [07 – Scripts](07-scripts.md) | `seed_data.py`, `add_admin_user.py` |
| [08 – Testing](08-testing.md) | pytest, `FARMER_CHAT_DATA_DIR`, storage tests |
| [09 – AWS and Amazon Bedrock](09-aws-and-bedrock.md) | IAM, regions, ECS/EC2 data paths, Bedrock setup |
| [Cost-effective AWS](cost-effective-aws.md) | Small EC2, EBS vs EFS, Bedrock/token cost, avoid NAT/ALB until needed |
| [10 – Security and operations](10-security-and-operations.md) | Secrets, production checklist, scaling caveats |
| [11 – Repository file index](11-repository-file-index.md) | Maps each important repo path to the right guide |
| [Service split plan](service-split-plan.md) | Plan + applied changes to divide app into services |

### Config files, AWS bundle, and tooling (detailed)

| Item | Guides |
| ---- | ------ |
| [`config/llm.yaml`](../config/llm.yaml) | [config-llm-yaml-explained.md](config-llm-yaml-explained.md), [06 – Configuration](06-configuration-reference.md), [05 – LLM](05-llm-providers-and-prompts.md) |
| [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml) | [config-llm-bedrock-example-explained.md](config-llm-bedrock-example-explained.md), [09 – AWS](09-aws-and-bedrock.md) |
| [`aws/`](../aws/) (README, env.example, IAM JSON) | [aws-folder-explained.md](aws-folder-explained.md), [09 – AWS](09-aws-and-bedrock.md), [06 – Configuration](06-configuration-reference.md) |
| [`requirements.txt`](../requirements.txt) | [reference-requirements.md](reference-requirements.md) |
| [`pytest.ini`](../pytest.ini) | [reference-pytest-ini.md](reference-pytest-ini.md) |
| Every major source path | [11 – Repository file index](11-repository-file-index.md) |

### Root readme

The short quickstart lives in the repository [README.md](../README.md).
