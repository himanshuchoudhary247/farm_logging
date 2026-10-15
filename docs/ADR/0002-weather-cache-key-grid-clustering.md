# 0002 - Weather cache key is a coarse lat/lng grid cell, not raw PIN or raw lat/lng

**Status:** Accepted (2026-10-15)

## Context

~1,000 distinct farm PIN codes exist today, growing. A naive "one cache
entry per PIN" design means one farmer_chat call per PIN per 4h cycle --
fine at today's scale, but every PIN added is a new call forever, with no
ceiling.

Many PINs are geographically close enough that their weather is
indistinguishable at Open-Meteo's own forecast-model resolution. Caching
each separately wastes calls for zero accuracy gain. Raw lat/lng as the key
has the opposite problem: two coordinates a few meters apart (same farm,
slightly different geocode run) would miss each other's cache entry
entirely.

## Decision

A PIN is resolved to lat/lng (via the persistent geocode cache,
main_backend's `pincode_locations` table), then that lat/lng is rounded to
a 0.1 degree grid (~11km, matching Open-Meteo's own forecast grid
resolution) before being used as the cache key. PIN is the lookup key
callers use; the grid cell is the dedupe layer underneath it, invisible to
callers.

Nearby PINs collapse onto the same grid cell and share one farmer_chat
call. The grid size was chosen to lose no real forecast accuracy (Open-Meteo
does not resolve weather any finer than this anyway), not tuned for a
specific call-volume target.

## Consequences

- The number of farmer_chat calls per refresh cycle is bounded by distinct
  grid cells, not distinct PINs -- gives headroom as the PIN count grows
  without needing another design change.
- Two farms whose true locations differ by anything up to ~11km can
  legitimately receive an identical weather report. This is an intentional
  accuracy/cost trade-off, not a bug -- see
  [0001](0001-per-farmer-weather-report-source.md)'s note that PIN-centroid
  resolution is already the finest signal available (no per-farm lat/lng
  exists in main_backend's `Farms` model today).
- If `Farms` ever gains a precise per-farm lat/lng (a separate, currently
  out-of-scope idea raised during planning), the same grid-rounding keys
  apply directly to that coordinate instead of the PIN's centroid --
  revisit the grid size then, since real per-farm GPS would make a tighter
  grid worthwhile.
