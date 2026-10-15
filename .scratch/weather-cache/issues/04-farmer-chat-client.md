# 04: farmer_chat HTTP client

**What to build:** a main_backend module that calls farmer_chat's
`POST /weather/alert` with the shared API key, mirroring
`services/flokiq_sync/client.py`'s doc style on the farmer_chat side.

**Blocked by:** None to code; needs Ticket 01 live in a real environment
for the call to actually succeed end-to-end.

**Implements:** [ADR 0001](../../../docs/ADR/0001-per-farmer-weather-report-source.md)

**Status:** ready-for-agent

- [ ] `src/services/weather/farmerChatClient.js::fetchWeatherAlert(locationOrPin, {days, countryCode})`
      -- POSTs with `X-Api-Key` header, returns parsed JSON
- [ ] Throws on missing `FARMER_CHAT_API_BASE_URL`/`FARMER_CHAT_API_KEY`
      config (no silent "disabled" mode -- this path has no feature flag)
- [ ] Jest tests with mocked `axios`
