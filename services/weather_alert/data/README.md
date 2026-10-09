# pin_lookup.csv

Offline PIN code → location table used by `services/weather_alert/pin_lookup.py`,
so a 6-digit PIN does not need a Nominatim call.

## Source
- India Post "All India Pincode Directory" with latitude/longitude
  (Department of Posts, Government of India; published on data.gov.in under the
  Government Open Data License – India).
- Raw file used: `data-raw/pincode.csv` from github.com/harshvardhaniimi/IndiaPIN
  (a copy of that directory, Dec 2021). 157,126 post offices, 19,300 PINs.

## Build
    python scripts/build_pin_lookup.py --raw <path>/pincode.csv

See the script docstring for the cleaning steps.

## Numbers (9 Oct 2026 build)
- 18,421 of 19,300 PINs (95.4%). The rest fall back to Nominatim:
  42 have no usable coordinates, 837 had all offices > 60 km from their district centre.
- Compared with Nominatim (India only) on 155 random PINs
  (`python scripts/validate_pin_lookup.py`):
  median 4.2 km, 87% within 25 km, 97% within 50 km, state matched 136/137.
  18 of the 155 are not in Nominatim at all (e.g. 471111) — this table is the only
  source for them.

## Known limits
- Data is from Dec 2021: PINs created later are missing (Nominatim fallback).
- Points are post offices, not PIN area centres. Fine for weather (km level).
- A few PINs are far from Nominatim's point (e.g. 425502/425504, Jalgaon, ~120 km).
  Not clear which source is right.

## Update
Download a newer directory, re-run the build script, re-run the validate script,
and update the numbers above.
