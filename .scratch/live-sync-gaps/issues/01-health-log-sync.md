# 01: Health-log sync (Chocolate -> main_backend)

**What to build:** a health log created through the Chocolate chatbot
shows up in the farmer's app, the same way a chatbot-booked appointment
already does via `POST /internal/appointments`.

**Blocked by:** None (can start immediately) -- deliberately deferred
out of the live-sync gap-fixing pass this ticket came from, since it's
a full backend feature (new model/route/validation), not a small fix.

**Status:** ready-for-agent

## Context (found during review, verified against real code)

`services/flokiq_sync/client.py::create_health_log` already exists on the
farmer_chat side, gated off by `FLOKIQ_SYNC_HEALTH_LOGS` (default off).
It posts to `POST /health-logs` with a `Bearer {FLOKIQ_API_TOKEN}` header
-- its own docstring says outright: *"PROPOSED endpoint -- does not exist
on the real flokiq backend yet."* Confirmed: main_backend has no
`/health-logs` route anywhere, internal or app-facing (the only
`health.route.js` that exists is `farmeronboard/health.route.js::check-
animals`, an unrelated AI-diagnosis endpoint). Even if the route existed,
auth would still mismatch -- every other internal route
(`/internal/appointments`, `/internal/farmers/{id}/farm-location`,
`/internal/geocode`) uses `X-Internal-Api-Key`; this one alone was built
for a `Bearer` token.

Net effect today: health logs created in Chocolate stay in farmer_chat's
local `data/health_logs.json` only. Zero live impact right now since the
flag defaults off, but the client code describes a contract main_backend
doesn't honor.

## Fix shape (settled during grilling, option (a))

1. **main_backend**: new `POST /internal/health-logs` route, same
   `X-Internal-Api-Key` pattern as `/internal/appointments`
   (`src/controllers/internal/appointment.controller.js` is the template
   -- reuse its farmer-lookup-by-id and idempotency-on-retry shape).
   Needs a `HealthLog`-equivalent model/migration on main_backend (check
   whether one already exists under a different name before adding one).
2. **farmer_chat**: switch `create_health_log` from `Bearer
   {FLOKIQ_API_TOKEN}` to `X-Internal-Api-Key: {FLOKIQ_INTERNAL_API_KEY}`
   (same key `create_appointment` already uses), matching the real route's
   auth once it exists.
3. Leave `FLOKIQ_SYNC_HEALTH_LOGS` off by default until both sides are
   verified end-to-end against a real environment.

- [ ] main_backend: `POST /internal/health-logs` route + controller +
      validation, mirroring `/internal/appointments`'s shape
- [ ] farmer_chat: `create_health_log` auth switched to
      `X-Internal-Api-Key`
- [ ] Tests on both sides matching each repo's existing conventions
      (Jest + mocked Sequelize models; pytest + monkeypatch)
- [ ] Live-verified once both sides deploy, then `FLOKIQ_SYNC_HEALTH_LOGS`
      flipped on deliberately (same two-step rollout as the appointment
      sync feature)
