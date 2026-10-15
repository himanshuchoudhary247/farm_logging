# 08: Dashboard follow-ups (optional)

**What to build:** flokiquser's Dashboard stops blocking the weather card
render on `navigator.geolocation.getCurrentPosition` (dead latency now
that the PIN path doesn't need it for most farmers), and hides the "Wind
Direction" line when the field is absent rather than rendering blank.

**Blocked by:** 06

**Implements:** [ADR 0005](../../../docs/ADR/0005-farm-weather-endpoint-pin-first.md)

**Status:** ready-for-agent

- [ ] Weather card no longer waits on geolocation before its first fetch
- [ ] "Wind Direction" row conditionally rendered only when
      `weather?.windDirection` is present
- [ ] Not required to ship -- explicitly optional per the approved plan
