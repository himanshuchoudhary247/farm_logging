# 0001 - Per-farmer weather short report sources from farmer_chat, not a second Open-Meteo integration

**Status:** Accepted (2026-10-15)

## Context

The app's Dashboard weather card calls main_backend's `GET /weather?lat&lng`
(`src/controllers/farmeronboard/weather.controller.js` in main_backend),
which calls Open-Meteo's `current_weather` directly with no cache at all --
every page load/refresh is a live network call.

Separately, farmer_chat already has a richer weather pipeline
(`services/weather_alert/service.py::get_weather_alert`, exposed as
`POST /weather/alert`) used by the chatbot: risk level, advisories,
heat-stress/THI, on top of the same Open-Meteo forecast data, already sitting
behind two layers of in-process caching (the 15-minute geocode cache in
`service.py`, and `pincode_store`'s 12h bundle cache).

Caching alone fixes "too many calls per page load" regardless of which
pipeline backs it. The remaining question was which pipeline a new 4-hour
proactive cache should be built on top of.

## Decision

The cache is filled by calling farmer_chat's existing `POST /weather/alert`,
not by main_backend re-implementing an Open-Meteo call.

The dashboard card's fields come from that response's `forecast_days[0]`
(today) plus the top-level `summary`/`risk_level`:

```
{
  condition:  mapped from forecast_days[0].weather_code via main_backend's
              existing src/utils/WeatherMap.js (already used by the old
              bare endpoint, no new mapping needed)
  windSpeed:  forecast_days[0].wind_speed_10m_max
  humidity:   forecast_days[0].relative_humidity_2m_mean
  summary:    summary
  riskLevel:  risk_level
}
```

No new farmer_chat endpoint. `/weather/alert` already does only the 3-day
forecast (not the 5-year historical fetch `get_seasonal_advisory_data` does),
light enough to call once per cache miss.

## Consequences

- One THI/heat-stress/advisory implementation (Python), not a duplicate one
  growing independently in main_backend's JS.
- The dashboard card gets richer content (risk level, advisories available
  later if the UI wants them) for free.
- main_backend's weather path now has a runtime dependency on farmer_chat
  being reachable -- see [0004](0004-weather-alert-endpoint-auth.md) for the
  auth implication, and the cache itself (4h TTL) bounds the blast radius of
  a farmer_chat outage to stale-but-present data, not a hard failure.
