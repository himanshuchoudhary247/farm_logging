# Cost-effective AWS deployment

The app is a **single Streamlit process** plus **JSON files** (no RDS in v1). Below is how to keep spend low while staying practical.

## Cheapest patterns (typical order)

### 1. One small EC2 instance, EBS for data (often the lowest 24/7 cost)

- Use a **small instance**: **t4g.nano / t4g.micro** (Graviton) or **t3.micro / t3.small** in a supported region. New AWS accounts may get **Free Tier** on **t2/t3.micro** for 12 months (check current AWS terms).
- Store JSON on **one EBS volume** mounted at e.g. `/data`; set **`FARMER_CHAT_DATA_DIR=/data`**. EBS is inexpensive for tens of GB; **avoid EFS** unless you truly need shared files across instances (EFS adds monthly + throughput cost).
- Run **without an Application Load Balancer** for **internal** pilots: security group allowing your office/VPN IP on port 8501 (or SSH tunnel). Add **ALB + ACM** only when you need public HTTPS and can accept ~$16+/month for ALB in many regions (varies).
- **Stop the instance** nights/weekends for dev/demo if uptime is not required; you only pay for EBS while stopped.

### 2. Amazon Lightsail

- Fixed **monthly bundles** (VM + bandwidth) can be predictable and cheap for a **very low-traffic** demo. Trade-off: fewer AWS networking integrations than raw EC2; still fine for this app.

### 3. ECS Fargate

- **Pay per vCPU-GB RAM-hour**. For **continuous** Streamlit, a **single tiny EC2** often beats Fargate on price unless you already run ECS and want uniformity.
- If you use Fargate: **one task**, **low CPU/memory**, mount **EFS** only if you need persistence across task restarts; otherwise accept **lost local disk** or use a tiny always-on pattern carefully.

## LLM cost (often larger than compute)

| Choice | Cost pattern |
| ------ | ------------ |
| **Amazon Bedrock** | Pay **per input/output token**; model choice matters. Prefer **smaller/faster** models (e.g. Haiku-class) for triage; cap usage in product/policy if needed. |
| **OpenAI / Gemini** | Billed **outside** AWS list price; compare token pricing for your workload. |

**Tip:** Use **Bedrock in the same region** as the app to reduce cross-region calls and latency; avoid unnecessary chat round-trips in the UI.

## What to avoid for “cheap”

- **Multi-AZ ALB + NAT Gateway** for a **handful of users** — NAT alone is often **$30+/month** per gateway; use public subnets + tight SGs for a single cheap demo, or **VPC endpoints** only where required.
- **Over-sized instances** — Streamlit + JSON + Bedrock client is light; start **micro/nano** and scale up only if CPU is pegged.
- **RDS / ElastiCache** — not required for v1; JSON on disk has **no** database hourly fee.

## Operations that save money

- **Automated stop/start** for non-production (EventBridge + Lambda to stop EC2 off-hours).
- **Backups:** snapshot EBS on a **sensible schedule**, not continuous replication.
- **Monitoring:** CloudWatch **basic** metrics; skip paid dashboards until needed.

## Summary

For **lowest steady cost** with minimal complexity: **one small EC2**, **EBS for `data/`**, **IAM to Bedrock** if you use it, **tight security group** or **VPN**, **small Bedrock model**, and **no NAT/ALB** until you need them.

See also: [09 – AWS and Bedrock](09-aws-and-bedrock.md), [10 – Security and operations](10-security-and-operations.md).
