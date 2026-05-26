# AWS layout

This folder holds **deployment and Bedrock** notes. Application code stays at the repo root (`app.py`, `storage.py`, `llm/`, etc.).

**Detailed docs:** [`docs/aws-folder-explained.md`](../docs/aws-folder-explained.md) · [`docs/09-aws-and-bedrock.md`](../docs/09-aws-and-bedrock.md) · **[Cost-effective hosting](../docs/cost-effective-aws.md)** (small EC2, EBS, Bedrock spend, what to skip)

## Amazon Bedrock (text LLM)

1. **Region** – Pick a [Bedrock region](https://docs.aws.amazon.com/general/latest/gr/bedrock.html) and enable it for your account.

2. **Model access** – In the AWS console: **Bedrock → Model access** (or **Bedrock → Foundation models**) and request access to the models you use (e.g. Claude Haiku).

3. **IAM** – Grant the runtime principal permission to invoke models. Example actions:

   - `bedrock:InvokeModel`
   - `bedrock:InvokeModelWithResponseStream` (optional, for streaming later)

   Scope `Resource` to specific model ARNs in production; `*` is acceptable for development only.

4. **Configuration** – Point the app at a Bedrock config file:

   ```bash
   export AWS_REGION=us-east-1
   export LLM_CONFIG_PATH=/path/to/farmer_chat/config/llm.bedrock.example.yaml
   streamlit run app.py
   ```

   Or merge the `text:` block from [`config/llm.bedrock.example.yaml`](../config/llm.bedrock.example.yaml) into `config/llm.yaml`.

5. **Local development** – Use `aws configure` (credentials + default region) or set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Optional YAML field `aws_profile` selects a named profile.

## Where credentials come from

| Environment        | Typical auth                         |
| ------------------ | ------------------------------------ |
| Laptop             | `~/.aws/credentials`, env vars, or SSO |
| EC2                | Instance profile IAM role            |
| ECS Fargate / EKS  | Task / pod IAM role                  |
| Lambda             | Execution role                       |

No API key is stored in `llm.yaml` for Bedrock; OpenAI/Gemini still use `api_key_env` as before.

## Data directory on AWS

JSON data (`FARMER_CHAT_DATA_DIR`) should live on **persistent storage** if you run more than one task or replace containers:

- **ECS**: EFS volume mount
- **EC2**: EBS disk path
- **Quick try**: single instance with a host directory mount

Do not commit `data/` or secrets; keep buckets/EFS backups per your retention policy.

## Files here

- [`env.example`](env.example) – Example environment variables for Bedrock-focused runs.
- [`iam-bedrock-invoke.json`](iam-bedrock-invoke.json) – Sample IAM policy (tighten `Resource` in production; see docs above).
