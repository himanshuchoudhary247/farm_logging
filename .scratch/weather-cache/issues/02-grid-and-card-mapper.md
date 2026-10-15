# 02: Grid + card-mapping utilities

**What to build:** two pure, independently testable functions in
main_backend -- `roundToGrid(lat, lon)` (coarse 0.1-degree cache key) and
`mapAlertToCard(alertPayload)` (farmer_chat's `/weather/alert` response ->
the dashboard card shape: condition/icon/next24/windSpeed/humidity/temp/
summary/riskLevel).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `src/utils/weatherGrid.js::roundToGrid` -- stable string key, correct
      boundary rounding, negative longitude handled
- [ ] `src/services/weather/weatherCardMapper.js::mapAlertToCard` --
      condition/icon/next24 via existing `WeatherMap.getWeatherInfo`;
      windSpeed/humidity/temp numeric and rounded; summary/riskLevel
      passthrough; null-safe on empty `forecast_days`
- [ ] Jest tests for both, matching `tests/internal-geocode.test.js`'s
      conventions
