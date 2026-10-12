"""Compare pin_lookup.csv with Nominatim (India only) for a random sample of
PINs: distance between the two points and whether the state matches.

    python scripts/validate_pin_lookup.py --sample 150

Manual tool, not a test: it calls the public Nominatim API at 1 request/sec
(their usage policy), so 150 PINs take ~3 minutes.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pin_lookup import DEFAULT_OUT, km  # noqa: E402

FIXED = ["411001", "302001", "560001", "600001", "695001"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with open(args.table, encoding="utf-8", newline="") as f:
        table = {r["pin"]: r for r in csv.DictReader(f)}

    random.seed(args.seed)
    sample = random.sample(sorted(table), args.sample) + [p for p in FIXED if p in table]

    dists, state_ok, state_bad, not_found = [], 0, [], []
    for i, pin in enumerate(sample, 1):
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": pin, "countrycodes": "in", "format": "jsonv2", "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": "farmer-chat-pin-lookup-check/1.0"})
        try:
            res = json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception as exc:  # network trouble: report and keep going
            print("  error", pin, exc)
            res = []
        time.sleep(1.1)
        if not res:
            not_found.append(pin)
            continue
        ours, theirs = table[pin], res[0]
        d = km((float(ours["lat"]), float(ours["lon"])), (float(theirs["lat"]), float(theirs["lon"])))
        dists.append((d, pin, ours["district"], theirs.get("display_name", "")[:70]))
        parts = [p.strip() for p in theirs.get("display_name", "").split(",") if p.strip() and not p.strip().isdigit()]
        their_state = parts[-2] if len(parts) >= 2 else ""
        if their_state.lower() == ours["state"].lower():
            state_ok += 1
        else:
            state_bad.append((pin, ours["state"], their_state))
        if i % 25 == 0:
            print(f"  {i}/{len(sample)}")

    if not dists:
        print("nothing to compare")
        return
    dists.sort()
    km_only = [d[0] for d in dists]

    def pct(p: float) -> float:
        return round(km_only[min(len(km_only) - 1, int(len(km_only) * p))], 1)

    print(f"compared: {len(dists)} | not in Nominatim (India): {len(not_found)} {not_found[:10]}")
    print(f"distance km: median {pct(0.5)} | 90% {pct(0.9)} | 95% {pct(0.95)} | max {round(km_only[-1], 1)}")
    for limit in (10, 25, 50):
        print(f"within {limit} km: {sum(d <= limit for d in km_only)}/{len(km_only)}")
    print(f"state match: {state_ok}/{len(dists)} {state_bad[:10]}")
    print("worst 10:")
    for d in dists[-10:]:
        print(f"  {round(d[0], 1)} km  {d[1]}  ours: {d[2]}  nominatim: {d[3]}")


if __name__ == "__main__":
    main()
    