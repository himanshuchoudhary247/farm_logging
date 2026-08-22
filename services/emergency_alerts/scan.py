"""Async emergency-alert nightly scanner for the 10 demo PIN codes.

Flow per PIN:
  1. resolve_location(pin) -> Open-Meteo forecast (via weather_alert service)
  2. classify alerts (thunderstorm / heavy rain / strong wind)
  3. pull ICAR/Kisan Suvidha district advisory digest (best-effort)
  4. generate Bedrock actionable insight in the farmer's language
  5. dedupe by {pin, date, type} and persist to data/alert_feed.json

Runs standalone (`python -m services.emergency_alerts.scan`) for cron.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from .config import DEMO_PINS, LANG_NAMES, SCAN_HORIZON_DAYS
from .fetch_kisansuvidha import advisory_digest
from .insight import generate_alert_insight, generate_digest_insight
from .storage import (
    append_run,
    last_run,
    load_feed,
    save_feed,
    sleep_seconds,
    upsert_alerts,
    utc_today,
)

try:
    from services.weather_alert.service import get_weather_alert
except ImportError:  # EC2 flat deployment: weather_service.py at project root
    from weather_service import get_weather_alert


def _run_id() -> str:
    return utc_today()


def scan_pin(pin_info: dict[str, str], *, generate: bool = True) -> dict[str, Any]:
    pin = pin_info["pin"]
    district = pin_info["district"]
    state = pin_info["state"]
    language = pin_info.get("language", "en")

    weather = get_weather_alert(pin, country_code="in", days=SCAN_HORIZON_DAYS)
    resolved = weather.get("resolved_location", {}) or {}
    display_name = resolved.get("display_name", district)

    digest = advisory_digest(district, state)
    digest_insight = None
    if generate and digest.get("advisory"):
        digest_insight = generate_digest_insight(digest["advisory"], district, language)

    alerts: list[dict[str, Any]] = []
    for a in weather.get("alerts", []):
        reasons = a.get("reasons") or []
        alert_type = reasons[0] if reasons else "weather"
        record = {
            "pin": pin,
            "district": district,
            "state": state,
            "location": display_name,
            "language": language,
            "language_name": LANG_NAMES.get(language, "English"),
            "date": a.get("date"),
            "level": a.get("level", "low"),
            "type": alert_type,
            "reasons": reasons,
            "weather_code": a.get("weather_code"),
            "rain_mm": a.get("rain_mm"),
            "wind_kph": a.get("wind_kph"),
            "source": "Open-Meteo forecast",
            "insight": None,
            "digest": None,
        }
        if generate:
            record["insight"] = generate_alert_insight(alert=a, district=district, language=language)
        alerts.append(record)

    if digest.get("advisory"):
        alerts.append({
            "pin": pin,
            "district": district,
            "state": state,
            "location": display_name,
            "language": language,
            "language_name": LANG_NAMES.get(language, "English"),
            "date": utc_today(),
            "level": "low",
            "type": "district advisory digest",
            "reasons": [],
            "source": "ICAR / Kisan Suvidha",
            "insight": digest_insight,
            "digest": digest,
        })

    return {
        "pin": pin,
        "district": district,
        "state": state,
        "resolved_location": display_name,
        "risk_level": weather.get("risk_level", "low"),
        "alerts": alerts,
        "digest": digest,
        "digest_insight": digest_insight,
    }


def scan_all_pins(*, generate: bool = True) -> dict[str, Any]:
    started = time.time()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_new = 0

    for pin_info in DEMO_PINS:
        try:
            result = scan_pin(pin_info, generate=generate)
            results.append(result)
            new = upsert_alerts(result["alerts"])
            total_new += len(new)
            time.sleep(sleep_seconds())
        except Exception as e:  # pragma: no cover - network dependent
            errors.append({"pin": pin_info["pin"], "district": pin_info["district"], "error": str(e)})

    feed = load_feed()
    save_feed(feed)

    run = {
        "run_id": _run_id(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - started, 2),
        "pins_processed": len(results),
        "pins_failed": len(errors),
        "new_alerts": total_new,
        "errors": errors,
    }
    append_run(run)

    return {
        "run": run,
        "pins": [r["pin"] for r in results],
        "errors": errors,
        "feed": feed,
    }


def main() -> int:
    result = scan_all_pins()
    print(f"scan complete: {result['run']['pins_processed']} pins, "
          f"{result['run']['new_alerts']} new alerts, "
          f"{result['run']['pins_failed']} failed")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR {e['pin']} ({e['district']}): {e['error']}", file=sys.stderr)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
