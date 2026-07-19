"""Farmer Weather Advisory — Streamlit app.

Two modes:
1. API mode: set API_BASE_URL env var for LLM-generated SMS advisories (EC2 backend).
2. Offline mode: no env var needed, uses rule-based outputs from weather_service.py.
"""

import os
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
        r = http.post(f"{API_BASE}{endpoint}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_alert(loc: str, days: int) -> dict[str, Any]:
    return _api("/weather/alert", {"location_or_pin": loc, "days": days}) or _get_alert_offline(loc, days=days)


def get_advisory(loc: str, days: int) -> dict[str, Any]:
    result = _api("/weather/seasonal-advisory", {"location_or_pin": loc, "days": days})
    if result:
        if result.get("advisory"):
            return result
        if result.get("error"):
            pass  # fall through to offline
    data = _get_advisory_data(loc, days=days)
    risk = _get_alert_offline(loc, days=min(days, 3))
    return {
        "district": data.get("district") or data.get("location", loc),
        "location": data.get("location", loc),
        "advisory": None,
        "_weather_data": risk,
        "_raw_data": data,
    }


st.set_page_config(page_title="🌾 Farmer Weather Advisory", page_icon="🌾", layout="centered")
st.title("🌾 Farmer Weather Advisory")

status = "🟢 API" if API_BASE else "🟡 Offline"
with st.sidebar:
    st.markdown(f"**Status:** {status}")
    if API_BASE:
        st.caption(API_BASE)
    else:
        st.caption("No LLM SMS — set API_BASE_URL for Bedrock-powered advisories.")

tab1, tab2, tab3 = st.tabs(["⚠️ Risk Alert", "🧑‍⚕️ SMS Advisory", "📜 Historical Data"])

with tab1:
    with st.form("f1"):
        loc = st.text_input("Location", "Jaipur")
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
                    st.write(f"- {d['date']}: {d.get('temperature_2m_max','')}°C / {d.get('temperature_2m_min','')}°C  🌧️ {d.get('precipitation_sum',0)}mm  💨 {d.get('wind_speed_10m_max',0)}km/h")

with tab2:
    with st.form("f2"):
        loc2 = st.text_input("Location", "Jaipur", key="al")
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
        loc3 = st.text_input("Location", "Jaipur", key="hl")
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
            st.dataframe(h.get("years", []), use_container_width=True)

st.caption("Powered by Open-Meteo + AWS Bedrock + OpenStreetMap.")
