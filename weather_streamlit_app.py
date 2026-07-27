"""Farmer Weather Advisory — Streamlit app.

Two modes:
1. API mode: set API_BASE_URL env var for LLM-generated SMS advisories (EC2 backend).
2. Offline mode: no env var needed, uses rule-based outputs from weather_service.py.
"""

import os
import datetime
from typing import Any

import streamlit as st
import requests as http

from weather_service import (
    get_weather_alert as _get_alert_offline,
    get_seasonal_advisory_data as _get_advisory_data,
    get_historical_weather as _get_hist,
    resolve_location,
)

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

tab1, tab2, tab3, tab4 = st.tabs(["⚠️ Risk Alert", "🧑‍⚕️ SMS Advisory", "📜 Historical Data", "📊 Weekly Insight"])

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
                    st.write(
                        f"- {d['date']}: {d.get('temperature_2m_max', '')}°C / "
                        f"{d.get('temperature_2m_min', '')}°C  🌧️ "
                        f"{d.get('precipitation_sum', 0)}mm  💨 "
                        f"{d.get('wind_speed_10m_max', 0)}km/h"
                    )

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
            with st.spinner("Analyzing weather + disease risk..."):
                alert = get_alert(loc4, days4)
                advisory = get_advisory(loc4, days4)
                lo = resolve_location(loc4)
                hist = _get_hist(lo.lat, lo.lon)

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

st.caption("Powered by Open-Meteo + AWS Bedrock Mistral + ICAR-NIVEDI NADRES + OpenStreetMap.")
