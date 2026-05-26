#!/usr/bin/env python3
"""Add a small synthetic dataset for farmer001 (f-001)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import append_consultation, append_health_log, animals_for_farmer


def main() -> None:
    farmer_id = "f-001"
    animals = animals_for_farmer(farmer_id)
    if not animals:
        raise RuntimeError("No animals found for f-001. Run scripts/seed_data.py first.")

    primary = animals[0]
    secondary = animals[1] if len(animals) > 1 else animals[0]

    append_health_log(
        farmer_id=farmer_id,
        animal_id=primary.id,
        issue="Reduced feed intake and mild fever since yesterday",
        params={
            "appetite": "reduced",
            "temperature_c": 39.8,
            "duration": "1 day",
            "feces": "normal",
        },
        notes="Separated from herd for observation.",
    )
    append_health_log(
        farmer_id=farmer_id,
        animal_id=secondary.id,
        issue="Loose stool and low activity",
        params={
            "appetite": "reduced",
            "temperature_c": 39.2,
            "duration": "2 days",
            "feces": "loose",
        },
        notes="Given oral rehydration and clean water.",
    )

    append_consultation(
        farmer_id=farmer_id,
        animal_id=primary.id,
        messages=[
            {"role": "user", "content": "Buffalo is eating less and feels warm."},
            {
                "role": "assistant",
                "content": "Since when did this start, and is there any nasal discharge or coughing?",
            },
            {"role": "user", "content": "Started yesterday, no coughing, slight nasal wetness."},
            {
                "role": "assistant",
                "content": "Monitor temperature every 6-8 hours, keep hydration up, and contact a vet if fever rises or breathing changes.",
            },
        ],
        summary="Buffalo low appetite with mild fever",
    )
    append_consultation(
        farmer_id=farmer_id,
        animal_id=secondary.id,
        messages=[
            {"role": "user", "content": "Goat has loose motion for two days."},
            {
                "role": "assistant",
                "content": "Is there blood in stool, and has feed recently changed?",
            },
            {"role": "user", "content": "No blood. Feed changed three days ago."},
            {
                "role": "assistant",
                "content": "Return gradually to previous feed, provide clean water with electrolytes, and call a vet if weakness or blood appears.",
            },
        ],
        summary="Goat loose stool after feed change",
    )

    print("Added 2 health logs and 2 consultations for farmer001 (f-001).")


if __name__ == "__main__":
    main()
