# Security and operations

Practical notes for operating the Farmer livestock assistant beyond local development.

## Secrets and configuration

| Item | Guidance |
| ---- | -------- |
| API keys (OpenAI, Gemini) | Store in environment variables or a secrets manager; **never** commit to git. |
| AWS keys | Prefer **IAM roles** on compute; avoid long-lived access keys where possible. |
| `farmers.json` | Contains **password hashes**; restrict file permissions and backup access. |
| `.env` | Convenient locally; add to `.gitignore` if used; do not commit. |
| Default passwords (`changeme`, `admin123`) | **Change** before any shared or production deployment. |

## Transport

Streamlit over plain HTTP is normal on `localhost`. In production, terminate **TLS** at a reverse proxy (nginx, ALB, CloudFront, etc.) and restrict network access to the Streamlit port.

## Session and access control

- **Farmers** only see data for their own `farmer_id` (animals, logs, consultations).
- **Admins** choose a farmer scope in the UI; enforce **who may use admin accounts** outside the app (VPN, SSO gateway, IP allowlists).
- Streamlit **session state** is not a substitute for enterprise IAM; this is a lightweight v1 design.

## Concurrency and scaling

- JSON writes use **file locks** and **atomic replace** to reduce corruption risk on concurrent updates.
- **Multiple Streamlit workers** or replicas writing the **same** JSON directory can still race; prefer **one write-capable instance** or move to a proper database if you scale horizontally.
- **Read-heavy** scaling is easier with replicated read-only copies only if you accept eventual consistency or migrate storage.

## Observability

v1 does not ship structured logging or metrics. For production:

- Capture **stdout/stderr** from the Streamlit process.
- Optionally wrap LLM calls with logging of latency and error rates (without logging full PHI or secrets).

## Backups

- Back up the directory pointed to by `FARMER_CHAT_DATA_DIR` on a schedule appropriate to your RPO/RTO.
- Test restore procedures on a non-production copy.

## Compliance and livestock advice

- The LLM provides **general information**, not veterinary diagnosis. System prompts encourage seeking a **qualified veterinarian** for urgent cases; your deployment may need disclaimers and local regulatory review.

## Dependency updates

- Pin major versions in [`requirements.txt`](../requirements.txt) for reproducible deploys.
- Regularly apply **security patches** for Python packages and the base image if containerized.

## Related

- [04 – Authentication and roles](04-authentication-and-roles.md)
- [03 – Data models and storage](03-data-models-and-storage.md)
- [09 – AWS and Bedrock](09-aws-and-bedrock.md)
