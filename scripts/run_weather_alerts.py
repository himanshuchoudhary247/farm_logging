from __future__ import annotations

from gateways import create_farmer_weather_notification
from storage import farmer_accounts


def run_daily_weather_alerts(days: int = 3) -> dict[str, int]:
    sent = 0
    skipped = 0
    errors = 0

    for farmer in farmer_accounts():
        location = (farmer.weather_location or "").strip()
        if not location:
            skipped += 1
            continue
        try:
            note = create_farmer_weather_notification(
                farmer_id=farmer.id,
                location_or_pin=location,
                country_code="in",
                days=days,
            )
            risk = str(note.get("risk_level") or "low")
            if risk in {"medium", "high"}:
                sent += 1
            else:
                skipped += 1
        except Exception:
            errors += 1

    return {"sent": sent, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    out = run_daily_weather_alerts(days=3)
    print(
        f"Daily weather alert run complete: sent={out['sent']} skipped={out['skipped']} errors={out['errors']}"
    )
