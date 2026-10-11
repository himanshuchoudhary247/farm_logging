# pincode_latlon.csv — provenance

19,258 India PIN codes with lat/lon, district, state. One row per PIN
(first valid office found; PINs with no usable coordinates in the
source are dropped).

**Source:** [harshvardhaniimi/IndiaPIN](https://github.com/harshvardhaniimi/IndiaPIN)
(`data-raw/pincode.csv`), MIT licensed. That repo's own data is built
from India Post's public pincode directory (data.gov.in).

**Built:** 2026-10-12, via a one-off local script (download the raw
CSV, dedupe by PIN, drop rows with missing/out-of-India-range lat/lon,
title-case district/state). Not re-run automatically — if the upstream
directory gets new PINs or corrections, this file needs rebuilding by
hand from the same source.

**Used by:** `services/weather_alert/service.py::resolve_location()` —
an exact-PIN-shaped query (`_is_pin_code`) for India resolves against
this table first, skipping the Nominatim geocode call entirely. Only
the exact-PIN case; free-text place names and PINs missing from this
table still go through Nominatim exactly as before.
