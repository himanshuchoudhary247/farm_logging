"""Which A2UI widget, if any, goes with a chat reply.

One entry per agent that has a widget. The chat router calls widget_for()
for every reply; agents without a widget get None and their reply is sent
exactly as before.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from services.a2ui.booking_widget import booking_widget_for
from services.a2ui.query_widget import query_widget_for
from services.a2ui.registration_widget import registration_widget_for
from services.a2ui.weather_widget import weather_widget_for

_log = logging.getLogger("a2ui_widgets")

_BUILDERS: dict[str, Callable[[str, str, dict[str, Any], str], Optional[list[dict]]]] = {
    "appointment_supervisor": booking_widget_for,
    "animal_registration": registration_widget_for,
    "weather_alert": weather_widget_for,
    "query_agent": query_widget_for,
}


def widget_for(agent: str, farmer_id: str, session_id: str, result: Any, language: str) -> Optional[list[dict]]:
    """A2UI messages to send next to this reply, or None. Never raises."""
    build = _BUILDERS.get(agent)
    if build is None or not isinstance(result, dict):
        return None
    try:
        return build(farmer_id, session_id, result, result.get("language") or language)
    except Exception as exc:  # each builder already guards itself; this is the last net
        _log.warning("a2ui widget skipped agent=%s farmer=%s err=%s", agent, farmer_id, exc)
        return None
