# 01: Auth-gate /weather/alert

**What to build:** `POST /weather/alert` on farmer_chat rejects a request
with no/wrong `X-Api-Key` header once `FARMER_CHAT_API_KEY` is set, and
behaves exactly as today for a request carrying the correct key (or when
the key is unset, matching every other `require_api_key` route).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `POST /weather/alert` depends on `require_api_key`
- [ ] `require_api_key` unit tests: wrong/missing key -> raises; correct
      key -> no raise; key unset -> no raise regardless of header
- [ ] `services/farmer_onboarding_service/api.py`'s duplicate route and
      `gateways.py::fetch_weather_alert` left untouched
