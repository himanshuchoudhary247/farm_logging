# WhatsApp channel

Reach the FarmHerd agentic system over a WhatsApp Business number. This
is a **transport module**, not a new agent -- inbound messages flow
through the same `services.chat_orchestrator.adk_router.route_turn_adk`
pipeline that powers the app and voice UIs. What's new is a
**channel-scoped feature gate**: WhatsApp only exposes a configured
subset of the agentic system's intents (default: all four; typical
production config: `query` + `appointment` only, so farmers can't
register animals or check weather over WhatsApp).

## When to use this instead of the app or voice UI

- Farmers who prefer chat but don't want to install another app.
- Ambient support: "how many goats do I have" without opening anything.
- Follow-ups on appointments after they were booked in the app.

Not a fit for: photo uploads (out of scope -- see below), long-form
seasonal reports, or anything that requires multi-panel UI.

## Quick-start (local dev, no real Meta/Twilio account)

The `mock` provider records outbound sends in-process; no network is
needed. Perfect for exercising the full pipeline locally.

```bash
# 1. Start the backend with WhatsApp enabled + mock provider
export WHATSAPP_ENABLED=1
export WHATSAPP_PROVIDER=mock
export WHATSAPP_ALLOWED_INTENTS=query,appointment
uvicorn services.api_service.main:app --host 127.0.0.1 --port 8000

# 2. In another shell, fire a canned inbound
python scripts/whatsapp_dev_send.py \
    --text "how many animals do I have" \
    --from "+919876543210"
```

The router will:
1. Look up `+919876543210` -- if that number is a registered farmer's
   `phone`, they resolve immediately (no enrollment prompt).
2. Detect the language from the message script (Devanagari -> Hindi,
   Latin -> English, etc).
3. Dispatch through `route_turn_adk` with `allowed_intents={query,
   appointment}`.
4. Send the reply back through the mock provider (visible in server
   logs as `whatsapp send_text to=...`).

## The channel gate (the whole point of the module)

`config/channels.yaml`:

```yaml
channels:
  whatsapp:
    enabled: true
    allowed_intents: [query, appointment]  # subset of the full set
    default_language: en-IN
    include_audio: false
    max_reply_chars: 4000
    provider: meta
    rate_limit: { per_phone_per_min: 6, per_phone_per_hour: 100 }
    enrollment: { enabled: true }
```

Every knob has a matching `WHATSAPP_*` env var (env wins if set). Full
list in `.env.example` under the "WhatsApp channel" heading.

**Full intent set:** `query`, `appointment`, `weather`, `add_animal`.
Setting `allowed_intents: [query, appointment]` makes the channel say
"that request is not available on WhatsApp right now, please use the
FarmHerd app" (localized in the farmer's language) when the message
classifies as `weather` or `add_animal`. The agent is NOT run for
blocked intents -- no drafts are created or advanced.

The gate integrates with sticky routing too: an active appointment
draft on the app does NOT bypass the gate when the farmer messages
WhatsApp with `allowed_intents=[query]`. Sticky routes are only honored
for allowed intents.

## Farmer identity

If a WhatsApp message arrives from `+91XXX` and any farmer's `phone`
canonicalizes to that same number, the router resolves immediately --
no enrollment prompt, no "reply with your farmer ID" ceremony. This is
the common case for farmers already registered with the same phone
they use on WhatsApp.

For the edge case where a farmer uses a different WhatsApp number than
their registered contact number (spouse's phone, work number), an
optional `whatsapp_phone` field on `Farmer` overrides `phone` when set.
The enrollment flow (below) fills this automatically on first contact.

### Enrollment flow

When `enrollment.enabled: true` (the default), an unknown-phone message
triggers a localized prompt asking the farmer for their **registered
phone number or FarmHerd username** (never "farmer ID" -- those are
internal UUIDs farmers don't know). On the next message, the router:
1. If the reply canonicalizes to a phone number matching any farmer's
   registered `phone` -> bind `whatsapp_phone`, confirm.
2. Else if the reply matches a farmer's `login_username` -> bind, confirm.
3. Else -> send the enrollment failure message, prompt again.

When `enrollment.enabled: false`, unknown-phone messages get a generic
"this number is not registered" reply and are dropped.

## Provider setup: Meta Cloud API (production)

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api

1. Register a Meta app + WhatsApp Business account; get the Phone
   Number ID and a long-lived access token.
2. Set env:
   ```
   WHATSAPP_META_PHONE_ID=<from Meta>
   WHATSAPP_META_ACCESS_TOKEN=<long-lived token>
   WHATSAPP_META_APP_SECRET=<app secret from Meta dashboard>
   WHATSAPP_META_VERIFY_TOKEN=<any string you pick>
   ```
3. Point Meta's webhook config at
   `https://<your-host>/whatsapp/webhook`. Meta issues a one-time GET
   with `hub.verify_token=<yours>&hub.challenge=...`; our
   `GET /whatsapp/webhook` handler echoes the challenge on match.
4. Subscribe to the `messages` field.

Inbound messages are HMAC-SHA256 signed with the app secret in
`X-Hub-Signature-256`; forged signatures return 403.

## Provider setup: Twilio (skeleton -- send + verify work, media stubbed)

Reference: https://www.twilio.com/docs/whatsapp/api

1. Sign up for Twilio, get Account SID and Auth Token, and a
   WhatsApp-enabled number (sandbox is fine for dev).
2. Set env:
   ```
   WHATSAPP_PROVIDER=twilio
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   ```
3. Point Twilio's webhook config at `https://<your-host>/whatsapp/webhook`
   with method POST.

Twilio's inbound is form-encoded (not JSON); the webhook handler in
`main.py` handles both content types. Signature verification uses
Twilio's HMAC-SHA1-over-URL+params scheme.

**Note:** the Twilio provider ships as a working skeleton --
`verify_signature` and `send_text` are real. `download_media` and
`send_audio` raise `NotImplementedError`; fill in per Twilio's docs
when needed. The Meta provider covers the primary use case.

## Rate limits, dedupe, session identity

- **Rate limit:** in-memory rolling window per phone number. Default
  6/min, 100/hour. Configurable via `WHATSAPP_RATE_LIMIT_*` env or the
  YAML `rate_limit` block.
- **Dedupe:** in-memory TTL set on inbound `message.id` (Meta retries
  webhooks aggressively). Default 24h TTL.
- **Session identity:** `session_id = whatsapp-<sha1(phone)[:12]>`.
  Explicit namespace so it can never collide with app browser-session
  UUIDs. sha1-shortened so log lines stay readable. Sticky routing
  (`_has_active_booking_draft`, `_has_active_registration_draft`)
  works exactly like on the app -- same farmer, different session_id.

Both the rate limiter and dedupe are per-process. Multi-worker
deployments will double-process a small percentage of retries; known v1
limitation, acceptable given the low volume this module targets.

## Out of scope

- **Photo uploads.** Farmers can send photos on WhatsApp, but our
  agents have no photo-consumption path today. The router replies with
  "photos are coming soon; please describe in text".
- **Templated / HSM outbound messages** (WhatsApp's pre-approved
  notification templates). Separate cost + compliance surface, not
  needed for a farmer-initiated support channel.
- **Group chats.** WhatsApp Business API doesn't support them at all.
- **`/menu` command / slash-commands.** Not a fifth classifier
  category. Follow-up PR if the product wants it.
- **Meta Business account creation / phone-number verification.** Needs
  a human, not scriptable. Point at Meta's own docs.

## Testing

Unit tests, mocked at the network / LLM boundary (never hit real
Meta/Twilio/Bedrock): `tests/test_whatsapp_*.py`. Full suite:

```bash
python -m pytest tests/ -q
```

Passes with AND without AWS credentials in the environment (matches CI).

## Verification recipes

Live-verify the gate:

```bash
# 1. allowed_intents=[query]  -> add_animal blocked
export WHATSAPP_ALLOWED_INTENTS=query
uvicorn services.api_service.main:app --port 8000 &
python scripts/whatsapp_dev_send.py --text "add a new goat"
# expected: mock provider logs a blocked_intent reply

# 2. allowed_intents=[query,add_animal]  -> add_animal dispatches
export WHATSAPP_ALLOWED_INTENTS=query,add_animal
# restart uvicorn
python scripts/whatsapp_dev_send.py --text "add a new goat"
# expected: animal_registration.turn() is called
```

Live-verify against a real Meta test number: point Meta's webhook at
your public URL (ngrok / cloudflare-tunnel for local dev), set the
`WHATSAPP_META_*` env vars, send a message from your personal WhatsApp
to the Meta test number. Blocked while the AWS Bedrock account issue
persists -- the classifier itself needs Bedrock (or the
`LLM_PROVIDER=freellmapi` fallback active).
