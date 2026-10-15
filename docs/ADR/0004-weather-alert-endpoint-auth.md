# 0004 - farmer_chat's /weather/alert requires FARMER_CHAT_API_KEY before main_backend calls it on a schedule

**Status:** Accepted (2026-10-15)

## Context

`POST /weather/alert` (`services/api_service/main.py`) has no auth
dependency today -- it was built for the chatbot's own internal use and
has stayed open. [0003](0003-weather-cache-ownership-main-backend.md) adds
a new caller: main_backend's cron, hitting it automatically every 4 hours
rather than a human-triggered chatbot turn.

An automated, scheduled, unauthenticated caller is a materially different
risk than "nobody's gotten around to calling this from outside the process
yet" -- it is now a standing, predictable, externally-reachable endpoint.

farmer_chat already has a reusable gate for exactly this
(`require_api_key`, backed by `FARMER_CHAT_API_KEY`), used on
`/farmers/*` routes today.

## Decision

Add `_auth: None = Depends(require_api_key)` to `POST /weather/alert`,
same as the existing `/farmers/*` routes. main_backend's cron sends the
same `FARMER_CHAT_API_KEY` header value as any other authenticated caller.

## Consequences

- No new auth mechanism -- reuses the existing shared-secret header
  already used elsewhere in this same service.
- main_backend needs this key configured (likely the same env var name,
  or a differently-named env var holding the same value) before its cron
  can successfully call the endpoint -- a deploy-time configuration step,
  not a code dependency.
- Corrected during planning: a second, structurally identical `POST
  /weather/alert` route also exists on `services/farmer_onboarding_service/api.py`
  (deployed separately, port 8004, `deploy/farmer-onboarding.service`,
  `--workers 2`). No live caller was found for it anywhere in this repo or
  in main_backend/flokiquser -- it appears to be leftover scaffolding from
  the service-split effort (`docs/service-split-plan.md`), not something
  this change's cron will call. Left unauthenticated and out of scope
  here; flagged for whoever eventually prunes dead endpoints on that
  service. `gateways.py::fetch_weather_alert` (a "remote mode" HTTP client
  for the same call) was also checked and has no caller today -- also
  dead code, also out of scope.
