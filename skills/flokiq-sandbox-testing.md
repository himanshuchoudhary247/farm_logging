# flokiq-sandbox: testing notes

Operational knowledge for logging into and testing the flokiquser app
against the real `sandboxapi.flokiq.com` backend. Companion to
`db-access.md` (DB schema/access) and `otp_server.py` /
`register_test_farmer.py` (tooling) in this same directory.

## Two user roles, different post-login destinations

`users.role` decides where the app sends you right after OTP verify
(`src/pages/dashboard/dashboard.tsx`):

```js
if (user?.user?.role === "farmer") {
  history.push("/tabs/dashboard");       // real app: animals, appointments, shop, etc.
} else {
  history.push("/tabs/lead-generation/add");  // KYC/"Add New Farmer" form
}
```

- **`role=farmer`** — the actual end-user persona. Logs into the real
  dashboard and every farm-management screen.
- **`role=agent`** — flokiq field staff. Always redirected to the
  "Add New Farmer" KYC form (Aadhaar, name, address, PAN, education,
  occupation, etc.) regardless of whether they've already completed it
  once.

**Tested finding**: submitting the KYC form successfully does **not**
flip `role` from `agent` to `farmer`. Confirmed live — phone
`9959737365` has a `farmers` table row from a prior test but is still
`role=agent` in `users`. Whatever promotes an agent to farmer status
(if anything does) is not the KYC form submission itself — didn't dig
further into backend logic for this.

**Practical implication**: to test the real farmer-facing app, log in
with a phone that already has `role=farmer` in the DB. Don't rely on
completing the KYC form to get there.

## Farmer-role test phones (flokiq-sandbox, as of 2026-09-16)

```
9885828089
8545895892
9642736712
9966589658
6985764125
6302803566
6302803565
```

**Tested live 2026-09-16: none of these 7 phones accept login.** Every
one returns `404 {"code":404,"message":"Incorrect phone number"}` from
`POST /auth/login`, despite being valid `role=farmer` rows in `users`.
DB row existence does not guarantee login works on this backend — some
other server-side gate exists that isn't visible from `users`/`agents`/
`farmers` table contents (checked `deletedAt`, `password`, linked
`agents` row — none explain it).

One relevant clue: `9885828089`'s `farmers` row has
`zohoSyncStatus: SUCCESS` — this record looks imported from Zoho CRM by
a backend job, not created through the app's own signup flow. Possibly
imported accounts were never "activated" for direct login. Not
confirmed — backend source isn't available from here.

**Root cause found, 2026-09-17.** Created a brand-new farmer end to end
via the real API (`POST /farmers` with `mobileNo=7000000001`, agent
`9959737365` as `onboardedBy`) — got `201`, confirmed `role=farmer` in
`users` immediately after. That number *still* fails login with the
same `404 Incorrect phone number`. This rules out role, DB row
completeness, and Zoho-import status entirely — a farmer created 30
seconds earlier through the app's own real flow fails identically to
the 7-month-old imported rows.

Only 2 phone numbers have ever worked in this whole investigation:
`9959737365` and `7676239999`, both `role=agent`. Every synthetic/test
number tried — DB-seeded farmer rows, a freshly-created real farmer,
sequential filler numbers — fails. The pattern only makes sense if
`/auth/login` validates the phone against something **outside the
`users` table** before even generating an OTP — most likely a
real-number/carrier-validity check (e.g. Twilio Lookup or similar).
Real, deliverable mobile numbers pass; synthetic test numbers don't,
regardless of what's in the database.

**Conclusion: a farmer login on this backend requires a real, physical
phone number.** No DB read, write, or API call from this machine can
produce one — the gate sits before OTP generation, outside anything
inspectable or mutable here. Get a real farmer test number from the
team; don't spend more time on DB-side workarounds for this.

**What does work**: `role=agent` phones, but even those are
inconsistent — `9959737365` and `7676239999` accept login,
`8639660691` (also role=agent) returns the same 404. No DB-visible
differentiator found between the working and failing agent accounts
either.

**Recommendation**: don't assume any DB-listed phone will log in. Ask
the team for a phone number *confirmed working* for farmer-role login,
or test each candidate with `POST /auth/login` before spending time on
it via the UI.

Re-query any time:

```bash
source ~/code/farmer_chat/venv/bin/activate
export $(grep -v '^#' ~/code/flokiquser/.env | grep -v '^$' | grep -v VITE_ | xargs)
python -c "
import os, pymysql
conn = pymysql.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'], database='flokiq-sandbox',
    port=int(os.environ['DB_PORT']), cursorclass=pymysql.cursors.DictCursor)
with conn.cursor() as cur:
    cur.execute(\"SELECT id, phone FROM users WHERE role='farmer' AND phone IS NOT NULL LIMIT 10\")
    for r in cur.fetchall(): print(r['id'], r['phone'])
conn.close()
"
```

## Logging in without SMS access

The sandbox writes real OTPs to `otpverifications.otp` — no SMS needed
for testing.

**Option A — local button UI**: `python skills/otp_server.py`, open
`http://localhost:5555/`, type the phone, click "Get latest OTP". Reads
the *most recent* OTP row for that phone — trigger `/auth/login` first
(via the app UI) so a fresh row exists, then click the button.

**Option B — one-shot CLI**:

```bash
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"phone":"9885828089"}' https://sandboxapi.flokiq.com/api/v1/auth/login
```

then read the OTP:

```bash
source ~/code/farmer_chat/venv/bin/activate
export $(grep -v '^#' ~/code/flokiquser/.env | grep -v '^$' | grep -v VITE_ | xargs)
python -c "
import os, pymysql
conn = pymysql.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'], database='flokiq-sandbox',
    port=int(os.environ['DB_PORT']), cursorclass=pymysql.cursors.DictCursor)
with conn.cursor() as cur:
    cur.execute('SELECT u.phone, o.otp, o.createdAt FROM otpverifications o '
                'JOIN users u ON u.id=o.userId WHERE u.phone=%s '
                'ORDER BY o.createdAt DESC LIMIT 1', ('9885828089',))
    print(cur.fetchone())
conn.close()
"
```

## Local `.env` for real backend

`~/code/flokiquser/.env` (gitignored):

```
VITE_SITE_KEY=https://sandboxapi.flokiq.com/api/v1
VITE_PUBLIC_API_FILE_PATHS=https://sandboxapi.flokiq.com/uploads/
```

Restart Vite after changing it:

```bash
pkill -f "flokiquser/node_modules/.bin/vite"
cd ~/code/flokiquser && npm run dev
```

## Auth API quirks found live

- `POST /auth/verify-otp` — `otp` field must be sent as a **string**,
  not a number. Sending `{"otp": 1234}` returns
  `{"code":400,"message":"\"otp\" must be a string"}`.
- `POST /farmers` (creating/updating a farmer profile) — the frontend
  code (`api.saveFarmer` in `src/lib/apis.ts`) calls this with `PUT`,
  but the sandbox backend only accepts `POST` on that path; `PUT
  /farmers` 404s. Client/server drift — flag to the backend/frontend
  team if this matters for real usage, not just test scripts.
- `POST /farmers` field validation observed live:
  - `gender` must be exactly `"Male"`, `"Female"`, or `"Other"`
    (capitalized)
  - `hasPanCard` / `hasGovernmentId` must be lowercase `"yes"` /
    `"no"`
  - `landHolding` must be a **number**, not a string
  - `mobileNo` is taken from the logged-in user's own phone
    (`user.user.phone`), not a separate field — this form registers
    the *current account* as a farmer, it does not let an agent
    onboard a different phone number's farmer profile through this
    endpoint.
  - Re-submitting for a phone that already has a farmer record returns
    `409 {"code":409,"message":"Farmer already exists with this mobile number"}`

See `skills/register_test_farmer.py` for a working end-to-end script
(login → read OTP → verify → POST /farmers) using these corrected
field values.

## Reference

- `skills/db-access.md` — DB schema/connection details, all 78
  flokiq-sandbox tables grouped by function, read-only user setup
- `skills/otp_server.py` — local button UI to fetch OTPs
- `skills/register_test_farmer.py` — scripted farmer registration
