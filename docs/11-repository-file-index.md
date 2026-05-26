# Repository file index

Map from **repository paths** to **documentation** that describes them.

## Application and Python modules

| Path | Documentation |
| ---- | ------------- |
| [`app.py`](../app.py) | [02 – Application and UI](02-application-and-ui.md) |
| [`auth.py`](../auth.py) | [04 – Authentication and roles](04-authentication-and-roles.md) |
| [`storage.py`](../storage.py) | [03 – Data models and storage](03-data-models-and-storage.md) |
| [`models.py`](../models.py) | [03 – Data models and storage](03-data-models-and-storage.md) |
| [`llm/config.py`](../llm/config.py) | [05 – LLM](05-llm-providers-and-prompts.md), [06 – Configuration](06-configuration-reference.md) |
| [`llm/adapters.py`](../llm/adapters.py) | [05 – LLM](05-llm-providers-and-prompts.md), [09 – AWS](09-aws-and-bedrock.md) |
| [`llm/prompts.py`](../llm/prompts.py) | [05 – LLM](05-llm-providers-and-prompts.md) |
| [`llm/__init__.py`](../llm/__init__.py) | [05 – LLM](05-llm-providers-and-prompts.md) |

## Configuration

| Path | Documentation |
| ---- | ------------- |
| [`config/llm.yaml`](../config/llm.yaml) | [config-llm-yaml-explained.md](config-llm-yaml-explained.md), [06 – Configuration](06-configuration-reference.md) |
| [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml) | [config-llm-bedrock-example-explained.md](config-llm-bedrock-example-explained.md), [09 – AWS](09-aws-and-bedrock.md) |

## AWS bundle

| Path | Documentation |
| ---- | ------------- |
| [`aws/README.md`](../aws/README.md) | [aws-folder-explained.md](aws-folder-explained.md), [09 – AWS](09-aws-and-bedrock.md) |
| [`aws/env.example`](../aws/env.example) | [aws-folder-explained.md](aws-folder-explained.md), [06 – Configuration](06-configuration-reference.md) |
| [`aws/iam-bedrock-invoke.json`](../aws/iam-bedrock-invoke.json) | [aws-folder-explained.md](aws-folder-explained.md), [09 – AWS](09-aws-and-bedrock.md) |

## Scripts and tooling

| Path | Documentation |
| ---- | ------------- |
| [`scripts/seed_data.py`](../scripts/seed_data.py) | [07 – Scripts](07-scripts.md) |
| [`scripts/add_admin_user.py`](../scripts/add_admin_user.py) | [07 – Scripts](07-scripts.md) |
| [`tests/test_storage.py`](../tests/test_storage.py) | [08 – Testing](08-testing.md) |
| [`pytest.ini`](../pytest.ini) | [reference-pytest-ini.md](reference-pytest-ini.md), [08 – Testing](08-testing.md) |
| [`requirements.txt`](../requirements.txt) | [reference-requirements.md](reference-requirements.md), [01 – Getting started](01-getting-started.md) |

## Data (runtime; usually gitignored)

| Path | Documentation |
| ---- | ------------- |
| `data/*.json` | [03 – Data models and storage](03-data-models-and-storage.md) |

## Top-level readme

| Path | Documentation |
| ---- | ------------- |
| [`README.md`](../README.md) | Quick start; full detail in [docs/README.md](README.md) |
