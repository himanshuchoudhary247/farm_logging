# 0003 - The 4h refresh scheduler and in-memory cache live in main_backend, not farmer_chat

**Status:** Accepted (2026-10-15)

## Context

Two candidates for where a proactive, scheduled (not lazy/read-through)
weather cache should live:

- **farmer_chat**: already owns the richer weather pipeline, but has no
  scheduler of any kind today -- every existing cache there
  (`weather_alert/service.py`'s 15-minute cache, `pincode_store`'s 12h
  cache, `services/cache_refresh`'s disk cache) is lazy, built on first
  access, never proactively refreshed.
- **main_backend**: already depends on `node-cron` and already runs two
  periodic jobs (`src/controllers/cron.controller.js`, wired in
  `src/app.js`). It also owns the `Farms` table -- the only source of
  "every farmer's PIN" (farmer_chat has no way to enumerate farmers'
  locations without a new cross-service call back to main_backend anyway).

Both services run as a single process today (main_backend via PM2
`instances: 1`; farmer_chat via `uvicorn --workers 1`), so an in-process
cache in either is safe from cross-instance fragmentation for now.

## Decision

The 4-hour cron job and the in-memory cache both live in main_backend,
using the existing `node-cron` pattern. Each cycle: query `Farms` for
`SELECT DISTINCT pincode`, resolve each to its grid cell
([0002](0002-weather-cache-key-grid-clustering.md)), call farmer_chat's
`/weather/alert` once per distinct cell, store the result in an in-memory
map keyed by grid cell.

## Consequences

- No new scheduling mechanism introduced into farmer_chat.
- main_backend's weather read path (`GET /weather`) becomes a cache read
  only -- it never calls farmer_chat synchronously on a farmer's request,
  only the background cron does.
- Single-process-per-service is a known, accepted limitation as of this
  decision (noted, not solved): if either service is ever scaled to
  multiple instances/workers, this in-memory cache needs to move to a
  shared store (Redis, or the database) to avoid each instance holding its
  own stale copy. Revisit then, not preemptively.
