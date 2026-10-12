"""Build services/weather_alert/data/pin_lookup.csv from the India Post
PIN directory CSV (all post offices with latitude/longitude).

    python scripts/build_pin_lookup.py --raw <path>/pincode.csv

Cleaning, in order:
1. Drop rows with empty or non-numeric lat/lon, or outside India's bounding box.
2. Each district's centre = median of all its post offices.
3. Drop offices more than --max-km from their district centre. The raw data has
   points that are inside India but in the wrong place (e.g. one 695001 office
   sits in the sea off Kollam).
4. PIN point = median of its remaining offices. A PIN with none left is left out,
   so the app falls back to Nominatim for it instead of using a bad point.
Output is sorted by PIN so a rebuild gives a clean diff.
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import statistics
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "services" / "weather_alert" / "data" / "pin_lookup.csv"
INDIA_LAT = (6.0, 37.5)
INDIA_LON = (68.0, 97.5)
OFFICE_TYPE_RANK = {"HO": 0, "SO": 1, "BO": 2}
OFFICE_SUFFIXES = (" B.O", " S.O", " H.O", " G.P.O.", " G.P.O", " BO", " SO", " HO")


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def to_float(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def nice(name: str) -> str:
    """'THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU' -> 'Dadra and Nagar Haveli
    and Daman and Diu', matching how Nominatim writes state/district names
    (feed prices look the state up by this name)."""
    words = name.strip().split()
    if words and words[0].upper() == "THE":
        words = words[1:]
    return " ".join(w.lower() if i and w.lower() in ("and", "of") else w.title() for i, w in enumerate(words))


def office_label(name: str) -> str:
    n = name.strip()
    for suffix in OFFICE_SUFFIXES:
        if n.upper().endswith(suffix):
            n = n[: -len(suffix)]
            break
    return nice(n)


def build(raw: Path, out: Path, max_km: float) -> None:
    with open(raw, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.DictReader(f))

    good = []
    for r in rows:
        lat, lon = to_float(r["Latitude"]), to_float(r["Longitude"])
        if lat is None or lon is None:
            continue
        if not (INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]):
            continue
        good.append({**r, "lat": lat, "lon": lon, "pin": r["Pincode"].strip()})

    by_district = collections.defaultdict(list)
    for r in good:
        by_district[(r["StateName"], r["District"])].append((r["lat"], r["lon"]))
    centre = {
        key: (statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts))
        for key, pts in by_district.items()
    }

    by_pin = collections.defaultdict(list)
    for r in good:
        by_pin[r["pin"]].append(r)

    result, dropped_rows, skipped_pins = {}, 0, 0
    for pin, offices in by_pin.items():
        kept = [r for r in offices if km((r["lat"], r["lon"]), centre[(r["StateName"], r["District"])]) <= max_km]
        dropped_rows += len(offices) - len(kept)
        if not kept:
            skipped_pins += 1
            continue
        main = min(kept, key=lambda r: OFFICE_TYPE_RANK.get(r["OfficeType"].strip(), 3))
        result[pin] = {
            "pin": pin,
            "office": office_label(main["OfficeName"]),
            "district": nice(main["District"]),
            "state": nice(main["StateName"]),
            "lat": round(statistics.median(r["lat"] for r in kept), 5),
            "lon": round(statistics.median(r["lon"] for r in kept), 5),
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pin", "office", "district", "state", "lat", "lon"], lineterminator="\n")
        writer.writeheader()
        for pin in sorted(result):
            writer.writerow(result[pin])

    all_pins = {r["Pincode"].strip() for r in rows}
    print(f"raw rows: {len(rows)} | unique PINs: {len(all_pins)}")
    print(f"PINs written: {len(result)}")
    print(f"PINs with no usable point: {len(all_pins - set(by_pin))}")
    print(f"PINs left out (all offices > {max_km:g} km from district centre): {skipped_pins}")
    print(f"office rows dropped as outliers: {dropped_rows}")
    print(f"wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, required=True, help="India Post directory CSV (pincode.csv)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-km", type=float, default=60.0)
    args = parser.parse_args()
    build(args.raw, args.out, args.max_km)


if __name__ == "__main__":
    main()
    