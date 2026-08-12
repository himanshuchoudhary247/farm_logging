"""Async emergency-alert nightly scanner for the 10 demo PIN codes.

Flow per PIN (4 sources blended):
  1. Open-Meteo forecast → classified alerts (thunderstorm / heavy rain / wind)
  2. ICAR-NIVEDI disease catalogue → seasonal disease advisory digest
  3. IMD public warnings → best-effort weather warnings (often unavailable)
  4. wttr.in → current conditions, classified if severe
  For every alert: Bedrock Mistral generates an actionable insight in the
  farmer's language. Dedupe by {pin, date, type + reasons fingerprint}.

Runs standalone (`python -m services.emergency_alerts.scan`) for cron.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from .config import DEMO_PINS, LANG_NAMES, SCAN_HORIZON_DAYS
from .fetch_icar import advisory_digest as _icar_digest
from .fetch_imd import fetch_imd_warnings as _fetch_imd
from .fetch_wttr import fetch_wttr as _fetch_wttr
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


def _base_record(pin: str, district: str, state: str, display_name: str, language: str) -> dict[str, Any]:
    return {
        "pin": pin,
        "district": district,
        "state": state,
        "location": display_name,
        "language": language,
        "language_name": LANG_NAMES.get(language, "English"),
    }


def scan_pin(pin_info: dict[str, str], *, generate: bool = True) -> dict[str, Any]:
    pin = pin_info["pin"]
    district = pin_info["district"]
    state = pin_info["state"]
    language = pin_info.get("language", "en")

    weather = get_weather_alert(pin, country_code="in", days=SCAN_HORIZON_DAYS)
    resolved = weather.get("resolved_location", {}) or {}
    display_name = resolved.get("display_name", district)

    alerts: list[dict[str, Any]] = []

    # ── Source 1: Open-Meteo forecast alerts ──
    for a in weather.get("alerts", []):
        reasons = a.get("reasons") or []
        alert_type = reasons[0] if reasons else "weather"
        record = _base_record(pin, district, state, display_name, language)
        record.update({
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
        })
        if generate:
            record["insight"] = generate_alert_insight(alert=a, district=district, language=language)
        alerts.append(record)

    # ── Source 2: ICAR-NIVEDI disease catalogue advisory ──
    icar = _icar_digest(district, state, language)
    if icar.get("advisory"):
        icar_insight = None
        if generate:
            icar_insight = generate_digest_insight(icar["advisory"], district, language)
        record = _base_record(pin, district, state, display_name, language)
        record.update({
            "date": utc_today(),
            "level": "medium",
            "type": "ICAR disease advisory",
            "reasons": [f"Active diseases: {', '.join(icar.get('active_diseases', []))}"],
            "source": "ICAR-NIVEDI NADRES",
            "insight": icar_insight,
            "digest": icar,
        })
        alerts.append(record)

    # ── Source 3: IMD public warnings (best-effort, often unavailable) ──
    imd = _fetch_imd(district, state)
    if imd.get("status") == "ok" and imd.get("warnings"):
        for w in imd["warnings"][:3]:
            record = _base_record(pin, district, state, display_name, language)
            record.update({
                "date": utc_today(),
                "level": "high",
                "type": "IMD weather warning",
                "reasons": [w.get("title", "IMD warning")],
                "source": "IMD",
                "insight": None,
                "digest": None,
            })
            if generate:
                record["insight"] = generate_alert_insight(
                    alert={"level": "high", "reasons": record["reasons"]},
                    district=district, language=language,
                )
            alerts.append(record)

    # ── Source 4: wttr.in current conditions ──
    wttr = _fetch_wttr(pin, district, state)
    if wttr.get("alert"):
        wa = wttr["alert"]
        record = _base_record(pin, district, state, display_name, language)
        record.update({
            "date": utc_today(),
            "level": wa.get("level", "medium"),
            "type": f"wttr.in: {wa.get('type', 'severe weather')}",
            "reasons": [f"Current condition: {wa.get('type', 'severe weather')}"],
            "weather_code": wa.get("weather_code"),
            "source": "wttr.in",
            "insight": None,
            "digest": None,
        })
        if generate:
            record["insight"] = generate_alert_insight(
                alert={"level": record["level"], "reasons": record["reasons"]},
                district=district, language=language,
            )
        alerts.append(record)

    return {
        "pin": pin,
        "district": district,
        "state": state,
        "resolved_location": display_name,
        "risk_level": weather.get("risk_level", "low"),
        "alerts": alerts,
        "sources": {
            "open_meteo": weather.get("risk_level", "low") != "low",
            "icar": icar.get("status", "ok"),
            "imd": imd.get("status", "unavailable"),
            "wttr_in": wttr.get("status", "unavailable"),
        },
        "icar_digest": icar,
        "imd_status": imd,
        "wttr_status": wttr,
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
