# 0005 - main_backend's GET /weather resolves the farmer's PIN first, lat/lng only as fallback

**Status:** Accepted (2026-10-15)

## Context

Today's `GET /weather?lat&lng` (main_backend) is already `auth()`-gated --
it knows which farmer is calling, but still requires the client to supply
coordinates on every call, and those coordinates have no relationship to
the PIN-keyed cache from [0002](0002-weather-cache-key-grid-clustering.md)
and [0003](0003-weather-cache-ownership-main-backend.md).

Not every farm is guaranteed to have a PIN on file (checked: `Farms.pincode`
is nullable), so PIN cannot be treated as always available.

## Decision

The route resolves the authenticated farmer's own farm PIN first (server
side, via the same `Farms` lookup `internal/farm.controller.js` already
does) and reads the cache keyed by that PIN's grid cell. Only when the farm
has no PIN on file does it fall back to the client-supplied `lat`/`lng`,
rounding them to the same grid directly (skipping the PIN-to-geocode step
entirely, since the client already gave coordinates).

`lat`/`lng` remain optional request params for this fallback path; they
are no longer the primary signal.

## Consequences

- Most calls no longer depend on the client holding/sending coordinates at
  all -- the farmer's own farm record is the source of truth, consistent
  with [0003](0003-weather-cache-ownership-main-backend.md)'s "for each
  farmer user" framing.
- The fallback path exists specifically for farms with no PIN recorded --
  a real, if presumably small, case, not a hypothetical one.
- `flokiquser`'s `src/lib/apis.ts::getWeatherConditions(lat, lng)` keeps
  its signature (coordinates stay useful as the fallback input) but no
  longer needs to be the primary path -- the app can keep sending them
  opportunistically without the backend depending on it.
