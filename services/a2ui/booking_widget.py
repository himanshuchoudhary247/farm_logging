"""Vet booking form as an A2UI widget (https://a2ui.org, spec v0.9).

While a booking is being collected, Chocolate's reply also carries a small
form -- animal, problem, date, time and a Book button -- so the farmer can
fill in everything at once instead of answering one question per turn. The
form is described as A2UI v0.9 messages (createSurface, updateComponents,
updateDataModel) using only components from the A2UI basic catalog; the app
renders them with its own native components. Nothing here is code that runs
on the device.

The booking itself does not change: the app turns the Book button into one
ordinary chat message ("animal: GAURI; issue: fever; date: 2026-10-30; time:
10:00") that goes through appointment_supervisor exactly like a typed
message, so animal verification, date/time checks, the readback and the
yes/no confirmation all still apply.

Purely additive: the widget is an extra "a2ui" key next to the existing
reply; clients that do not know it ignore it. Kill switch:
CHAT_A2UI_WIDGETS=false stops sending it.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterable, Optional

_log = logging.getLogger("a2ui_booking_widget")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

A2UI_VERSION = "v0.9"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
SUBMIT_EVENT = "submit_booking"

# Booking states in which the form is useful: details are still being
# collected. At CONFIRMING / READY_TO_SUBMIT the existing yes/no buttons
# take over; SUBMITTED / CANCELLED end the booking.
_FORM_STATES = {"COLLECTING", "CORRECTING"}
# A dropdown longer than this is hard to use on a phone; named animals and
# the ones offered by the booking flow come first.
MAX_ANIMAL_CHOICES = 50
_FALSY = {"0", "false", "no", "off"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

# Labels in the farmer's language. Field names (animal, problem, date, time)
# reuse the wording appointment_supervisor already uses in its readback.
_TEXT: dict[str, dict[str, str]] = {
    "en": {"title": "Book a vet visit", "animal": "Animal", "problem": "Problem",
           "other_problem": "Other problem (type here)", "date": "Date", "time": "Time", "book": "Book"},
    "hi": {"title": "पशु डॉक्टर की बुकिंग", "animal": "पशु", "problem": "समस्या",
           "other_problem": "कोई और समस्या (यहाँ लिखें)", "date": "तारीख", "time": "समय", "book": "बुक करें"},
    "mr": {"title": "पशुवैद्यकाची भेट बुक करा", "animal": "जनावर", "problem": "समस्या",
           "other_problem": "दुसरी समस्या (इथे लिहा)", "date": "तारीख", "time": "वेळ", "book": "बुक करा"},
    "ta": {"title": "கால்நடை மருத்துவர் சந்திப்பு", "animal": "விலங்கு", "problem": "பிரச்சினை",
           "other_problem": "வேறு பிரச்சினை (இங்கே எழுதுங்கள்)", "date": "தேதி", "time": "நேரம்", "book": "புக் செய்"},
    "te": {"title": "పశువైద్యుని అపాయింట్‌మెంట్", "animal": "జంతువు", "problem": "సమస్య",
           "other_problem": "వేరే సమస్య (ఇక్కడ రాయండి)", "date": "తేదీ", "time": "సమయం", "book": "బుక్ చేయండి"},
    "kn": {"title": "ಪಶುವೈದ್ಯರ ಭೇಟಿ ಬುಕ್ ಮಾಡಿ", "animal": "ಪ್ರಾಣಿ", "problem": "ಸಮಸ್ಯೆ",
           "other_problem": "ಬೇರೆ ಸಮಸ್ಯೆ (ಇಲ್ಲಿ ಬರೆಯಿರಿ)", "date": "ದಿನಾಂಕ", "time": "ಸಮಯ", "book": "ಬುಕ್ ಮಾಡಿ"},
    "ml": {"title": "മൃഗഡോക്ടറുടെ ബുക്കിംഗ്", "animal": "മൃഗം", "problem": "പ്രശ്നം",
           "other_problem": "മറ്റ് പ്രശ്നം (ഇവിടെ എഴുതുക)", "date": "തീയതി", "time": "സമയം", "book": "ബുക്ക് ചെയ്യുക"},
}


def widgets_enabled() -> bool:
    """On unless CHAT_A2UI_WIDGETS is set to a false value."""
    return os.getenv("CHAT_A2UI_WIDGETS", "").strip().lower() not in _FALSY


def _lang(language: str) -> str:
    code = (language or "en-IN").split("-")[0].lower()
    return code if code in _TEXT else "en"


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _animal_choices(animals: Iterable[Any], offered: Iterable[str], current: str) -> list[str]:
    """Animal names for the dropdown, without duplicates: the animal already
    chosen, then the ones the booking flow just offered, then every other
    animal, named ones before plain tags."""
    names: list[str] = []
    seen: set[str] = set()

    def add(name: Any) -> None:
        text = _clean(name)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            names.append(text)

    add(current)
    for name in offered:
        add(name)
    rest = [_clean(getattr(a, "tag_or_name", "")) for a in animals]
    # Plain tags (TAG-001-1) after real names (GAURI); otherwise keep order.
    for name in sorted(rest, key=lambda n: (n.upper().startswith("TAG-"), )):
        add(name)
    return names[:MAX_ANIMAL_CHOICES]


def build_booking_widget(result: dict[str, Any], language: str, animals: Iterable[Any] = (),
                         symptom_choices: Iterable[str] = (), surface_id: str = "booking") -> Optional[list[dict]]:
    """A2UI v0.9 messages for the booking form, or None when no form should
    be shown (booking not collecting, missing or malformed result).

    `result` is appointment_supervisor's turn result (state, draft,
    missing_fields, options). Values already given are filled in so the
    farmer only completes what is missing."""
    if not isinstance(result, dict) or result.get("state") not in _FORM_STATES:
        return None
    if not result.get("missing_fields"):
        return None
    draft = result.get("draft") if isinstance(result.get("draft"), dict) else {}
    text = _TEXT[_lang(language)]

    current_animal = _clean(draft.get("animal_identifier"))
    animals = list(animals)
    # The flow's pills are either animals (when it asks which animal) or
    # symptoms (when it asks the problem); only the ones that are really
    # this farmer's animals go to the top of the animal list.
    known = {_clean(getattr(a, "tag_or_name", "")).lower() for a in animals}
    options = result.get("options") if isinstance(result.get("options"), dict) else {}
    offered = [c for c in options.get("choices") or [] if isinstance(c, str) and _clean(c).lower() in known]
    animal_names = _animal_choices(animals, offered, current_animal)
    symptoms = [s for s in symptom_choices if _clean(s)]

    issue = _clean(draft.get("issue"))
    date = _clean(draft.get("date"))
    time = _clean(draft.get("time"))
    data = {
        "animal": [current_animal] if current_animal else [],
        "problem": [issue] if issue and issue in symptoms else [],
        "other_problem": issue if issue and issue not in symptoms else "",
        "date": date if _DATE_RE.match(date) else "",
        "time": time if _TIME_RE.match(time) else "",
    }

    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Card", "child": "form"},
        {"id": "form", "component": "Column",
         "children": ["title", "animal_label", "animal", "problem_label"]
         + (["problem"] if symptoms else [])
         + ["other_problem", "date_label", "date", "time_label", "time", "book"]},
        {"id": "title", "component": "Text", "text": text["title"], "variant": "h4"},
        {"id": "animal_label", "component": "Text", "text": text["animal"], "variant": "caption"},
        {"id": "animal", "component": "ChoicePicker",
         "options": [{"label": n, "value": n} for n in animal_names],
         "selections": {"path": "/booking/animal"}, "maxAllowedSelections": 1},
        {"id": "problem_label", "component": "Text", "text": text["problem"], "variant": "caption"},
        {"id": "other_problem", "component": "TextField", "label": text["other_problem"],
         "value": {"path": "/booking/other_problem"}, "textFieldType": "shortText"},
        {"id": "date_label", "component": "Text", "text": text["date"], "variant": "caption"},
        {"id": "date", "component": "DateTimeInput", "value": {"path": "/booking/date"},
         "enableDate": True, "enableTime": False},
        {"id": "time_label", "component": "Text", "text": text["time"], "variant": "caption"},
        {"id": "time", "component": "DateTimeInput", "value": {"path": "/booking/time"},
         "enableDate": False, "enableTime": True},
        {"id": "book", "component": "Button", "child": "book_text", "variant": "primary",
         "action": {"event": {"name": SUBMIT_EVENT, "context": {
             # Plain-word keys: the app sends them as "key: value" in one
             # chat message, which the booking extraction reads like any
             # typed answer.
             "animal": {"path": "/booking/animal"},
             "problem": {"path": "/booking/problem"},
             "other problem": {"path": "/booking/other_problem"},
             "date": {"path": "/booking/date"},
             "time": {"path": "/booking/time"},
         }}}},
        {"id": "book_text", "component": "Text", "text": text["book"]},
    ]
    if symptoms:
        components.append({"id": "problem", "component": "ChoicePicker",
                           "options": [{"label": s, "value": s} for s in symptoms],
                           "selections": {"path": "/booking/problem"}, "maxAllowedSelections": 1})

    return [
        {"version": A2UI_VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": BASIC_CATALOG_ID}},
        # v0.9: the component with id "root" is the top of the tree.
        {"version": A2UI_VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
        {"version": A2UI_VERSION, "updateDataModel": {"surfaceId": surface_id, "path": "/booking", "value": data}},
    ]


def booking_widget_for(farmer_id: str, session_id: str, result: dict[str, Any], language: str) -> Optional[list[dict]]:
    """The form for this booking turn, or None. Never raises: a problem
    building the widget only drops the widget, never the reply."""
    if not widgets_enabled() or not isinstance(result, dict) or result.get("state") not in _FORM_STATES:
        return None
    try:
        # Same animal list and symptom pills the booking flow itself uses,
        # so the form offers exactly what the booking will accept.
        from services.appointment_supervisor.service import _symptom_options
        from services.flokiq_sync import client as flokiq_sync
        from storage import animals_for_farmer, merge_app_animals

        animals = merge_app_animals(farmer_id, animals_for_farmer(farmer_id), flokiq_sync.get_farm_animals(farmer_id))
        symptoms = _symptom_options(language).get("choices") or []
        messages = build_booking_widget(result, language, animals, symptoms, surface_id=f"booking-{session_id}")
    except Exception as exc:  # the reply must never fail because of the widget
        _log.warning("a2ui booking widget skipped farmer=%s err=%s", farmer_id, exc)
        return None
    if messages:
        _log.info("a2ui booking widget sent farmer=%s state=%s missing=%s animals=%d", farmer_id,
                  result.get("state"), ",".join(result.get("missing_fields") or []), len(animals))
    return messages
