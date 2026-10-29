"""Shared pieces for Chocolate's A2UI widgets (https://a2ui.org, spec v0.9).

Every widget is a list of plain-JSON A2UI messages -- createSurface,
updateComponents, updateDataModel -- using only components from the A2UI
basic catalog. The app draws them with its own components; nothing here is
code that runs on the device.
"""
from __future__ import annotations

import os
from typing import Any

A2UI_VERSION = "v0.9"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"

_FALSY = {"0", "false", "no", "off"}


def widgets_enabled() -> bool:
    """On unless CHAT_A2UI_WIDGETS is set to a false value. One switch for
    every widget, so a problem in the app can be stopped from the backend
    without a release."""
    return os.getenv("CHAT_A2UI_WIDGETS", "").strip().lower() not in _FALSY


def lang_code(language: Any, table: dict[str, Any]) -> str:
    """"hi-IN" -> "hi" when the table has that language, else "en"."""
    code = (language if isinstance(language, str) and language else "en-IN").split("-")[0].lower()
    return code if code in table else "en"


def clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def surface_messages(surface_id: str, components: list[dict[str, Any]], data_path: str,
                     data: dict[str, Any]) -> list[dict[str, Any]]:
    """The three messages that draw one surface. v0.9: the component with
    id "root" is the top of the tree."""
    return [
        {"version": A2UI_VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": BASIC_CATALOG_ID}},
        {"version": A2UI_VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
        {"version": A2UI_VERSION, "updateDataModel": {"surfaceId": surface_id, "path": data_path, "value": data}},
    ]
