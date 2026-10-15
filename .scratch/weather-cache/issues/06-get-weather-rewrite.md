# 06: GET /weather rewritten

**What to build:** the dashboard's weather endpoint resolves the
authenticated farmer's own farm PIN first (cache read, lazy-fill on miss);
only falls back to client-supplied lat/lng when the farm has no PIN on
file -- using the OLD live Open-Meteo path unchanged for that fallback.

**Blocked by:** 05

**Implements:** [ADR 0005](../../../docs/ADR/0005-farm-weather-endpoint-pin-first.md)

**Status:** ready-for-agent

- [ ] Correct two-step lookup: `Farmer.findOne({where:{userId: req.user.id}})`
      -> `Farms.findOne({where:{farmerId: farmer.id}, ...})` (same
      where/order clause as `internal/farm.controller.js::getFarmLocation`)
      -- NOT `Farms.findOne({where:{farmerId: req.user.id}})`
- [ ] Farm with PIN + cache hit -> served from `weatherCacheStore`
- [ ] Farm with PIN + cache miss -> lazy-fill via Tickets 03/04,
      `weatherCacheStore.set`, then served
- [ ] No farm / no PIN -> old `lat`/`lng` + `weather.service.js` path,
      byte-for-byte unchanged; 400 if `lat`/`lng` also missing
- [ ] Jest tests for all four branches
