"""Farmer Weather Advisory — Streamlit app.

Two modes:
1. API mode: set API_BASE_URL env var for LLM-generated SMS advisories (EC2 backend).
2. Offline mode: no env var needed, uses rule-based outputs from weather_service.py.
"""

import os
import datetime
from typing import Any, Optional

import streamlit as st
import requests as http

from weather_service import (
    get_weather_alert as _get_alert_offline,
    get_seasonal_advisory_data as _get_advisory_data,
    get_historical_weather as _get_hist,
    resolve_location,
)

try:
    from market_prices.mandi import get_feed_price_snapshot as _get_feed_snapshot
except ImportError:
    try:
        from services.market_prices.mandi import get_feed_price_snapshot as _get_feed_snapshot
    except ImportError:
        _get_feed_snapshot = None

try:
    from emergency_alerts.api import fetch_alert_feed as _fetch_alert_feed
except ImportError:
    from services.emergency_alerts.api import fetch_alert_feed as _fetch_alert_feed


def fetch_alert_feed(pin=None):
    return _fetch_alert_feed(pin=pin) or {"pins": [], "records": [], "last_run": None}

API_BASE = os.environ.get("API_BASE_URL", "").rstrip("/")


def _api(endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not API_BASE:
        return None
    try:
        r = http.post(f"{API_BASE}{endpoint}", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_alert(loc: str, days: int) -> dict[str, Any]:
    return _api("/weather/alert", {"location_or_pin": loc, "days": days}) or _get_alert_offline(loc, days=days)


def get_advisory(loc: str, days: int) -> dict[str, Any]:
    result = _api("/weather/seasonal-advisory", {"location_or_pin": loc, "days": days})
    if result and result.get("advisory"):
        return result
    data = _get_advisory_data(loc, days=days)
    risk = _get_alert_offline(loc, days=min(days, 3))
    return {
        "district": data.get("district") or data.get("location", loc),
        "location": data.get("location", loc),
        "advisory": None,
        "_weather_data": risk,
        "_raw_data": data,
    }


@st.cache_data(ttl=3600)
def load_disease_catalogue():
    """Load disease catalogue from local JSON (ICAR-NIVEDI NADRES)."""
    import json as _json
    try:
        with open("disease_catalogue.json", "r") as f:
            return _json.load(f)
    except Exception:
        return {}


def get_disease_context(loc: str, catalogue: dict) -> list[str]:
    """Find active disease risks for a location from the catalogue."""
    loc_lower = loc.lower()
    active = []
    for state, info in catalogue.get("states", {}).items():
        for d in info.get("districts", []):
            if loc_lower in d.lower() or d.lower() in loc_lower:
                for disease in info.get("active_diseases", []):
                    if disease in catalogue.get("diseases", {}):
                        d_info = catalogue["diseases"][disease]
                        active.append(
                            f"{disease}: risk period is {', '.join(d_info['season'])}. "
                            f"Affects {', '.join(d_info['species'])}. {d_info['icar_ref']}"
                        )
                break
    return active[:5]


def get_monthly_diseases(month: int, catalogue: dict) -> list[str]:
    """Get diseases active in the current month based on season."""
    season_map = {
        1: "winter", 2: "winter", 3: "spring", 4: "spring",
        5: "summer", 6: "monsoon", 7: "monsoon", 8: "monsoon",
        9: "monsoon", 10: "post-monsoon", 11: "post-monsoon", 12: "winter",
    }
    current_season = season_map.get(month, "monsoon")
    active = []
    for disease, info in catalogue.get("diseases", {}).items():
        if current_season in info.get("season", []) or "year-round" in info.get("season", []):
            active.append(f"{disease} ({', '.join(info['symptoms'][:3])})")
    return active


st.set_page_config(page_title="Farmer Weather Advisory", page_icon="🌾", layout="centered")
st.title("🌾 Farmer Weather Advisory")

status = "🟢 API" if API_BASE else "🟡 Offline"
with st.sidebar:
    st.markdown(f"**Status:** {status}")
    if API_BASE:
        st.caption(API_BASE)
    else:
        st.caption("No LLM SMS — set API_BASE_URL for Bedrock-powered advisories.")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚠️ Risk Alert", "🧑‍⚕️ SMS Advisory", "📜 Historical Data", "📊 Weekly Insight", "🚨 Emergency Alerts"])

with tab1:
    with st.form("f1"):
        loc = st.text_input("Location", "Bellary")
        days = st.slider("Days", 1, 7, 3)
        if st.form_submit_button("Get Alert"):
            with st.spinner("..."):
                r = get_alert(loc, days)
            risk = r["risk_level"]
            cm = {"high": "red", "medium": "orange", "low": "green"}
            st.markdown(f"### Risk Level: :{cm[risk]}[{risk.upper()}]")
            st.info(r["summary"])
            st.caption(r["resolved_location"]["display_name"])
            for a in r["advisories"]:
                st.write(f"- {a}")
            if r["alerts"]:
                for a in r["alerts"]:
                    st.warning(f"**{a['date']}** — {' | '.join(a['reasons'])}")
            with st.expander("Forecast"):
                for d in r["forecast_days"]:
                    max_t = d.get("temperature_2m_max")
                    min_t = d.get("temperature_2m_min")
                    max_display = f"{max_t}°C" if max_t is not None else "--"
                    min_display = f"{min_t}°C" if min_t is not None else "--"
                    rain = d.get("precipitation_sum", 0)
                    wind = d.get("wind_speed_10m_max", 0)
                    rh = d.get("relative_humidity_2m_mean")
                    thi = d.get("thi")

                    parts = [
                        f"- {d['date']}: {max_display} / {min_display}",
                        f"🌧️ {rain}mm",
                        f"💨 {wind}km/h",
                    ]
                    if rh is not None:
                        parts.append(f"💧 RH {round(rh)}%")
                    if thi is not None:
                        parts.append(f"🔺 THI {thi}")
                    if d.get("heat_stress_level"):
                        parts.append(f"🔥 {d['heat_stress_level'].upper()} heat")

                    st.write("  ".join(parts))
                    if d.get("heat_stress_reason"):
                        st.caption(f"↳ {d['heat_stress_reason']}")

with tab2:
    with st.form("f2"):
        loc2 = st.text_input("Location", "Bellary", key="al")
        if st.form_submit_button("Generate SMS Advisory"):
            with st.spinner("Generating LLM advisory..."):
                adv = get_advisory(loc2, 7)
            st.markdown(f"### 📍 {adv.get('district') or adv.get('location', loc2)}")
            if adv.get("advisory"):
                st.success(adv["advisory"])
            else:
                st.info("LLM offline. Showing weather data.")
                w = adv.get("_weather_data", {})
                if w:
                    st.json({"risk": w["risk_level"], "summary": w["summary"], "advisories": w["advisories"]})
            with st.expander("Raw data"):
                st.json(adv.get("_raw_data", adv))

with tab3:
    with st.form("f3"):
        loc3 = st.text_input("Location", "Bellary", key="hl")
        if st.form_submit_button("Get History"):
            with st.spinner("..."):
                lo = resolve_location(loc3)
                h = _get_hist(lo.lat, lo.lon)
            st.caption(lo.display_name)
            if h.get("summary"):
                s = h["summary"]
                a, b, c2, d = st.columns(4)
                a.metric("High", f"{s['avg_high_temp']}°C")
                b.metric("Low", f"{s['avg_low_temp']}°C")
                c2.metric("Rain", f"{s['avg_rainfall_mm']}mm")
                d.metric("Wind", f"{s['avg_wind_kph']}km/h")
            st.dataframe(h.get("years", []), width="stretch")

with tab4:
    catalogue = load_disease_catalogue()
    with st.form("f4"):
        loc4 = st.text_input("Location", "Bellary", key="wi")
        days4 = st.slider("Forecast days", 3, 14, 7, key="wld")
        if st.form_submit_button("Generate Weekly Insight"):
            feed_snapshot = None
            feed_error: Optional[str] = None
            state_name: Optional[str] = None
            with st.spinner("Analyzing weather + disease risk..."):
                alert = get_alert(loc4, days4)
                advisory = get_advisory(loc4, days4)
                lo = resolve_location(loc4)
                hist = _get_hist(lo.lat, lo.lon)
                state_name = alert.get("resolved_location", {}).get("state") if isinstance(alert, dict) else None
                if _get_feed_snapshot and state_name:
                    try:
                        feed_snapshot = _get_feed_snapshot(state_name)
                    except Exception as exc:  # pragma: no cover - network variability
                        feed_error = str(exc)

            st.subheader(f"Weekly Deep Insight: {loc4}")
            st.caption(f"Location: {alert['resolved_location']['display_name']}")

            r1, r2 = st.columns(2)
            r1.metric("Risk Level", alert["risk_level"].upper())
            r2.metric("Days Covered", days4)

            st.markdown("---")
            st.markdown("### Weather Forecast vs Historical Average")
            if hist.get("summary"):
                s = hist["summary"]
                cols = st.columns(4)
                cols[0].metric("Avg High", f"{s['avg_high_temp']}°C")
                cols[1].metric("Avg Low", f"{s['avg_low_temp']}°C")
                cols[2].metric("Avg Rain", f"{s['avg_rainfall_mm']}mm")
                cols[3].metric("Avg Wind", f"{s['avg_wind_kph']}km/h")

            if alert.get("forecast_days"):
                fc = alert["forecast_days"]
                if fc:
                    avg_high = sum(d.get("temperature_2m_max", 0) for d in fc) / len(fc)
                    avg_rain = sum(d.get("precipitation_sum", 0) for d in fc) / len(fc)
                    avg_wind = sum(d.get("wind_speed_10m_max", 0) for d in fc) / len(fc)
                    hist_s = hist.get("summary", {})
                    if hist_s.get("avg_high_temp"):
                        diff = avg_high - hist_s["avg_high_temp"]
                        sign = "+" if diff > 0 else ""
                        st.write(
                            f"- Temperature this week: **{avg_high:.1f}°C** "
                            f"(vs historical {hist_s['avg_high_temp']}°C, {sign}{diff:.1f}°C)"
                        )
                    if hist_s.get("avg_rainfall_mm"):
                        st.write(f"- Rainfall this week: **{avg_rain:.1f}mm** (vs historical {hist_s['avg_rainfall_mm']}mm)")
                    if hist_s.get("avg_wind_kph"):
                        st.write(f"- Wind this week: **{avg_wind:.1f}km/h** (vs historical {hist_s['avg_wind_kph']}km/h)")

            st.markdown("---")
            st.markdown("### Disease Risk (ICAR-NIVEDI NADRES)")
            disease_ctx = get_disease_context(loc4, catalogue)
            if disease_ctx:
                for d in disease_ctx:
                    st.write(f"- {d}")
            else:
                st.info("No disease risk data available for this location yet.")

            st.markdown("---")
            st.markdown("### Monthly Disease Watch")
            current_month = datetime.datetime.now().month
            monthly = get_monthly_diseases(current_month, catalogue)
            if monthly:
                month_name = datetime.datetime.now().strftime("%B")
                st.write(f"**Active threats in {month_name}:**")
                for m in monthly:
                    st.write(f"- {m}")

            st.markdown("---")
            st.markdown("### Combined Advisory")
            if advisory.get("advisory"):
                st.markdown(advisory["advisory"])
            else:
                w = advisory.get("_weather_data", {})
                if w:
                    st.write(f"**Risk:** {w.get('risk_level', 'N/A')}")
                    for a in w.get("advisories", []):
                        st.write(f"- {a}")

            st.markdown("---")
            st.markdown("### Feed Market Snapshot")
            if not _get_feed_snapshot:
                st.caption("Feed market snapshot unavailable in offline mode.")
            elif feed_error:
                st.warning(f"Could not load mandi prices for {state_name}: {feed_error}")
            elif feed_snapshot and feed_snapshot.get("commodities"):
                st.caption(f"Source: Mandi Price API — latest sync {feed_snapshot.get('latest_fetched_at') or 'recent'}")
                for item in feed_snapshot["commodities"]:
                    avg_price = item.get("modal_price_avg")
                    min_price = item.get("modal_price_min")
                    max_price = item.get("modal_price_max")
                    sample_market = item.get("sample_market") or "multiple markets"
                    arrival = item.get("arrival_date") or "latest"
                    st.write(
                        "- "
                        f"{item['commodity']}: ₹{avg_price:.0f}/qtl (range ₹{min_price}-₹{max_price}) — "
                        f"{sample_market} [{arrival}]"
                    )
            else:
                if state_name:
                    st.info(f"No feed commodity records found today for {state_name}.")
                else:
                    st.info("Could not determine state for this location.")

            if disease_ctx:
                st.markdown("---")
                st.markdown("### Disease Prevention (from ICAR-NIVEDI)")
                for d_info_name in catalogue.get("diseases", {}):
                    d_info = catalogue["diseases"][d_info_name]
                    for dc in disease_ctx:
                        if d_info_name in dc:
                            st.write(f"**{d_info_name}:**")
                            for p in d_info.get("prevention", []):
                                st.write(f"  - {p}")

with tab5:
    st.markdown("### 🚨 Async Emergency Alerts (10 demo PINs)")
    st.caption("Daily feed generated from Open-Meteo forecasts + ICAR/Kisan Suvidha district advisories, with Bedrock-powered actionable insights in the farmer's language.")

    feed = fetch_alert_feed()
    pins = feed.get("pins", [])
    records = feed.get("records", [])
    last_run = feed.get("last_run") or {}

    st.write(f"**Last scan:** {last_run.get('finished_at') or 'never'} — {last_run.get('pins_processed', 0)} pins, {last_run.get('new_alerts', 0)} new alerts")

    if not pins:
        st.info("No demo PIN codes configured.")
        st.stop()

    selected = st.selectbox(
        "Select demo PIN code",
        options=[p["pin"] for p in pins],
        format_func=lambda p: next((f"{x['pin']} — {x['district']} ({x['state']})" for x in pins if x["pin"] == p), p),
    )

    for r in [x for x in records if x.get("pin") == selected]:
        level = r.get("level", "low")
        cm = {"high": "red", "medium": "orange", "low": "green"}
        st.markdown(
            f"### :{cm.get(level, 'green')}[{level.upper()}] · {r.get('date', '')} · {r.get('type', '')}"
        )
        st.write(" | ".join(r.get("reasons", [])))
        if r.get("insight"):
            st.info(r["insight"])
        st.caption(f"🌐 {r.get('source')} · Language: {r.get('language_name', 'English')}")
        st.markdown("---")

    if not [x for x in records if x.get("pin") == selected]:
        st.info("No alerts recorded yet for this PIN. Feed is refreshed by the nightly scan.")

    digest_rows = [x for x in records if x.get("pin") == selected and x.get("digest")]
    if digest_rows:
        with st.expander("ICAR district advisory digest"):
            for r in digest_rows[:1]:
                d = r.get("digest") or {}
                if d.get("advisory"):
                    st.write(d["advisory"])
                else:
                    st.write(d.get("note", "No advisory published yet this week."))

st.caption("Powered by Open-Meteo + AWS Bedrock Mistral + ICAR-NIVEDI NADRES + OpenStreetMap.")
