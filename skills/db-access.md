# flokiq-sandbox DB access

This is how any developer or automated agent reads the sandbox MySQL DB
backing the flokiquser app. Applies to `flokiq-sandbox` only — the same
RDS instance also hosts several unrelated databases; those are out of
scope for this app.

## What this DB is

Amazon RDS for MySQL, single instance, 6 databases live on it. This app
uses one of them:

| Database | Tables | Owner / scope |
|---|---|---|
| **flokiq-sandbox** | 78 | this app |
| banking_core | 20 | different product — do not touch |
| claimportal | 62 | different product — do not touch |
| sustechdb | 140 | different product — do not touch |
| kalavedik_db | 24 | different product — do not touch |
| geneAIus | 14 | different product — do not touch |

Every schema on the instance is reachable from a single admin user right
now. Only query `flokiq-sandbox`. Never `SELECT`, `INSERT`, or `UPDATE`
against the other schemas from this app's context.

## flokiq-sandbox table map

Grouped by function (full DDL in `~/flokiq_only_schema.md`, generated
from `SHOW TABLES` + `DESCRIBE`):

- **Auth / users** (5): `users`, `userdetails`, `otpverifications`,
  `tokens`, `SequelizeMeta` (Sequelize ORM migration marker — read-only
  metadata, never touch)
- **Farmer core** (8): `farmers`, `farmeronboardingpayments`, `farms`,
  `farm_images`, `farm_events`, `farm_visits`, `farm_diseases`,
  `farm_movements_logs`
- **Livestock** (13): `animals`, `animal_groups`, `animal_group_actions`,
  `animal_group_events`, `animal_group_rules`, `animal_group_species`,
  `animal_movements`, `animals_health_records`, `birth_events`,
  `breeding_events`, `offspring_records`, `genomic_samples`
- **Vet / clinical** (7): `appointments`, `clinical_diagnosis`,
  `prescriptions`, `prescriptionItems`, `medical_interventions`,
  `vaccination_schedule`, `health_logs`
- **Farm ops** (3): `feed_nutritions`, `financial_transactions`,
  `production_performance`
- **Field agents / vet camps** (7): `agents`, `agentroles`,
  `agent_location_history`, `camps`, `camp_close`, `camp_coordinators`,
  `camp_farmers`
- **Commerce** (17): `products`, `productcategories`, `productsubcategories`,
  `vendors`, `vendor_products`, `inventory`, `inventory_batches`,
  `inventory_history`, `stores`, `storetypes`, `stock_ledger`,
  `goods_receipts`, `purchase_orders`, `purchase_order_items`, `orders`,
  `orders_items`, `invoices`
- **Livestock marketplace** (5): `listings`, `sale_criteria_filters`,
  `sales_actions`, `sales_pipeline`, `sales_pipeline_animals`
- **Comms** (3): `messages`, `message_recipients`, `alerts`
- **WhatsApp integration** (5): `whatsapp_chat`, `whatsapp_lead_chat`,
  `whatsapp_leads`, `whatsapp_response`, `whatsapp_sessions` — backend
  scaffolding exists; the mobile UI links are dead (see
  `local-dev-setup.md`). Worth checking with the backend team what
  service reads/writes these before layering a new chat feature on top.
- **Lead-generation forms** (2): `questions`, `answers` (the KYC form
  the "Add New Farmer" page renders)
- **Misc** (3): `FarmerFeedbacks`, `categories`, `contracts_escrow`,
  `logistics_transfers`

## Connection details

All settings live in `~/code/flokiquser/.env` (gitignored). Never commit
credentials. The relevant variables:

```
DB_HOST
DB_PORT
DB_NAME=flokiq-sandbox
DB_USER
DB_PASSWORD
DB_DIALECT=mysql
```

Load them into your shell before running any tool:

```bash
export $(grep -v '^#' ~/code/flokiquser/.env | grep -v '^$' | grep -v VITE_ | xargs)
```

The `grep -v VITE_` filter is important — Vite variables are meant for
the client bundle, not shell.

## Setup (one-time)

The main app venv already has the driver. Reuse it:

```bash
source ~/code/farmer_chat/venv/bin/activate   # already has pymysql installed
```

If starting fresh in another environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pymysql
```

## Read-only user (recommended for any automated agent)

Do not hand out the `admin` credential. That user has full write access
across all six databases on the instance. Create a scoped read-only user
instead:

```bash
export $(grep -v '^#' ~/code/flokiquser/.env | grep -v '^$' | grep -v VITE_ | xargs)
python <<'PY'
import os, pymysql, secrets, string
alphabet = string.ascii_letters + string.digits
new_pw = ''.join(secrets.choice(alphabet) for _ in range(24))
conn = pymysql.connect(
    host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    port=int(os.environ["DB_PORT"]), connect_timeout=15,
)
with conn.cursor() as cur:
    cur.execute("CREATE USER 'flokiq_ro'@'%' IDENTIFIED BY %s", (new_pw,))
    cur.execute("GRANT SELECT ON `flokiq-sandbox`.* TO 'flokiq_ro'@'%'")
    cur.execute("FLUSH PRIVILEGES")
conn.commit()
conn.close()
print("user: flokiq_ro")
print(f"password: {new_pw}")
PY
```

Hand only these to the other agent:

```
DB_HOST=<from your .env>
DB_PORT=3306
DB_USER=flokiq_ro
DB_PASSWORD=<generated>
DB_NAME=flokiq-sandbox
```

Cleanup when the agent is done:

```sql
DROP USER 'flokiq_ro'@'%';
```

## Sample connection code (Python)

```python
import os, pymysql
conn = pymysql.connect(
    host=os.environ["DB_HOST"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database="flokiq-sandbox",   # always scope, don't rely on default
    port=int(os.environ["DB_PORT"]),
    connect_timeout=15,
    cursorclass=pymysql.cursors.DictCursor,
)
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) AS n FROM farmers")
    print(cur.fetchone())
conn.close()
```

## `mysql` CLI (optional)

The CLI is not preinstalled on macOS. To use it:

```bash
brew install mysql-client
echo 'export PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" flokiq-sandbox \
  -e "SHOW TABLES"
```

## Common read patterns

Auth lookup by phone (find a real test farmer to sign in with):

```sql
SELECT id, phone, role, isActive, createdAt
FROM users
WHERE phone IS NOT NULL AND phone != ''
ORDER BY createdAt DESC
LIMIT 20;
```

Farmer profile:

```sql
SELECT f.id, f.userId, u.phone, f.boardingDetails
FROM farmers f
JOIN users u ON u.id = f.userId
WHERE u.phone = '<10-digit phone>';
```

Appointments for one farmer (most recent first):

```sql
SELECT id, farmerId, status, appointmentDate, issueSummary
FROM appointments
WHERE farmerId = '<farmer id>'
ORDER BY appointmentDate DESC
LIMIT 20;
```

Animals belonging to one farmer:

```sql
SELECT a.id, a.species, a.tagOrName, a.breed, a.ageYears, a.farmId
FROM animals a
JOIN farms f ON f.id = a.farmId
WHERE f.farmerId = '<farmer id>';
```

Every table's exact columns are in `~/flokiq_only_schema.md`. Use that
before writing any query.

## Rules

- Read-only unless you have a specific reason and permission.
- Every query scopes to `flokiq-sandbox`. Never issue statements without
  the schema prefix or without `USE flokiq-sandbox` first.
- Add a `LIMIT` to any exploratory query. This DB has real data — a
  `SELECT * FROM whatsapp_chat` will return everything.
- Do not `SELECT *` on tables containing PII (`users`, `userdetails`,
  `farmers`, `otpverifications`, `whatsapp_*`) unless you actually need
  the columns. Name the fields explicitly.
- Do not export or forward result rows outside this project's context.
- Every `INSERT`, `UPDATE`, or `DELETE` should go through the flokiquser
  backend API instead of a direct SQL write — the API layer runs
  validation, hooks, and Sequelize model logic that a raw SQL write
  would skip.

## Migrations

The DB is managed by Sequelize.js on the backend. `SequelizeMeta` tracks
applied migrations. Never edit that table by hand. New migrations belong
in the flokiquser backend repo (a different codebase — not this one).

## Security notes

- The `admin` credential currently in `.env` grants full access to five
  DBs beyond this app (`banking_core`, `claimportal`, `sustechdb`,
  `kalavedik_db`, `geneAIus`). Rotate that credential and get a
  `flokiq-sandbox`-scoped account for future work.
- Any credential pasted into a chat or committed file should be treated
  as compromised. Rotate on any such incident.
- `.env` is in `.gitignore` — verify with `git check-ignore -v .env`
  before committing anything.
