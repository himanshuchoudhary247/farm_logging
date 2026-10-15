# 03: Geocode lookup/persist service

**What to build:** main_backend can read its own `PincodeLocation` table
directly (no HTTP round-trip to itself) to find a PIN's cached grid cell,
and can persist a newly-resolved PIN's location (lat/lon/display_name/
district/state) back into the same table.

**Blocked by:** PR #6 (`pincode_locations` table + `/internal/geocode`
routes) merged into the integration branch; and Ticket 02 (needs
`roundToGrid` from `weatherGrid.js`). (Coded against
`feat/weather-geocode-persistent-cache` locally, merged with Ticket 02's
branch for `roundToGrid` -- this ticket's *code* is unblocked; its
eventual merge upstream is sequenced behind PR #6.)

**Implements:** [ADR 0002](../../../docs/ADR/0002-weather-cache-key-grid-clustering.md)

**Status:** ready-for-agent

- [ ] `src/services/weather/pincodeGeocode.service.js::lookupKnownGrid(pincode)`
      -> `{gridKey, lat, lon} | null`, same `lookup_key = "in:<pincode>"`
      format as `geocode.controller.js`
- [ ] `persistResolvedLocation(pincode, {lat, lon, displayName, district, state})`
      -> upsert with `source: 'weather_cron'`
- [ ] Jest tests with mocked `PincodeLocation`
