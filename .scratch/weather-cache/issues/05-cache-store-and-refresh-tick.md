# 05: Cache store + cron refresh tick

**What to build:** an in-memory cache keyed by grid cell, and the refresh
job that fills it: distinct farm PINs -> resolve/dedup by grid -> one
`/weather/alert` call per distinct cell -> mapped card stored.

**Blocked by:** 02, 03, 04

**Implements:** [ADR 0002](../../../docs/ADR/0002-weather-cache-key-grid-clustering.md), [ADR 0003](../../../docs/ADR/0003-weather-cache-ownership-main-backend.md)

**Status:** ready-for-agent

- [ ] `src/services/weather/weatherCacheStore.js` -- module-level `Map`,
      `get(gridKey)`/`set(gridKey, data)`
- [ ] `src/services/weather/weatherRefresh.service.js::getDistinctFarmPincodes()`
      and `refreshAll()`: known PINs grouped by grid cell (one upstream
      call per distinct cell -- the dedup proof); unknown PINs resolved
      individually, grid computed from `resolved_location`, persisted via
      Ticket 03's service
- [ ] Per-PIN/per-cell errors caught and logged individually -- one
      farmer_chat failure does not abort the rest of the tick
- [ ] Jest test proving: N PINs sharing a grid cell -> 1 upstream call;
      an unknown PIN triggers a `PincodeLocation` upsert; a mid-tick
      failure doesn't stop later PINs from being processed
