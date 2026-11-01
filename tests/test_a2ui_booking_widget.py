"""Tests for the A2UI booking form (services/a2ui/booking_widget.py).

`result` dicts use the exact shape appointment_supervisor._response()
returns (session_id, state, language, draft, missing_fields,
response_text, prompt_text, options), so the widget is tested against what
it really receives."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services.a2ui import booking_widget as bw

ANIMALS = [SimpleNamespace(id=f"a{i}", tag_or_name=n) for i, n in enumerate(
    ["TAG-001-1", "GAURI", "TAG-001-2", "MOTI", "LAKSHMI", "gauri"])]
SYMPTOMS = ["Not eating", "Fever", "Limping", "Swelling", "Not drinking"]


def _result(state="COLLECTING", draft=None, missing=("animal_identifier", "issue", "date", "time"), options=None):
    result = {
        "session_id": "s1", "state": state, "language": "en-IN", "transcript": None,
        "draft": {"symptoms": [], "attachments": [], "miscellaneous_notes": "", **(draft or {})},
        "missing_fields": list(missing),
        "response_text": "Hello. Please tell me the animal name or tag...", "prompt_text": None,
        "response_audio_base64": None, "audio_error": None,
    }
    if options is not None:
        result["options"] = options
    return result


def _parts(messages):
    create, update, data = messages
    comps = {c["id"]: c for c in update["updateComponents"]["components"]}
    return create["createSurface"], update["updateComponents"], comps, data["updateDataModel"]


def test_messages_follow_a2ui_v09():
    messages = bw.build_booking_widget(_result(), "en-IN", ANIMALS, SYMPTOMS, surface_id="booking-s1")
    assert [list(m)[1] for m in messages] == ["createSurface", "updateComponents", "updateDataModel"]
    assert all(m["version"] == "v0.9" for m in messages)
    create, update, comps, data = _parts(messages)
    assert create == {"surfaceId": "booking-s1", "catalogId": bw.BASIC_CATALOG_ID}
    assert update["surfaceId"] == data["surfaceId"] == "booking-s1"
    assert "root" in comps and comps["root"]["component"] == "Card"
    json.dumps(messages, ensure_ascii=False)  # plain JSON, nothing executable


def test_only_basic_catalog_components_and_every_reference_exists():
    allowed = {"Card", "Column", "Row", "Text", "TextField", "DateTimeInput", "ChoicePicker", "Button", "Divider", "Image"}
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(), "en-IN", ANIMALS, SYMPTOMS))
    assert {c["component"] for c in comps.values()} <= allowed
    for c in comps.values():
        for ref in ([c["child"]] if "child" in c else []) + list(c.get("children") or []):
            assert ref in comps, (c["id"], ref)


def test_book_button_sends_every_field_from_the_data_model():
    _, _, comps, data = _parts(bw.build_booking_widget(_result(), "en-IN", ANIMALS, SYMPTOMS))
    event = comps["book"]["action"]["event"]
    assert event["name"] == "submit_booking"
    paths = {k: v["path"] for k, v in event["context"].items()}
    assert paths == {"animal": "/booking/animal", "problem": "/booking/problem", "other problem": "/booking/other_problem",
                     "date": "/booking/date", "time": "/booking/time"}
    assert set(data["value"]) == {"animal", "problem", "other_problem", "date", "time"} and data["path"] == "/booking"


def test_values_already_given_are_filled_in():
    result = _result(draft={"animal_identifier": "GAURI", "issue": "Fever", "date": "2026-10-30", "time": None},
                     missing=("time",))
    _, _, _, data = _parts(bw.build_booking_widget(result, "en-IN", ANIMALS, SYMPTOMS))
    assert data["value"] == {"animal": ["GAURI"], "problem": ["Fever"], "other_problem": "", "date": "2026-10-30", "time": ""}


def test_an_issue_that_is_not_a_listed_symptom_goes_to_the_free_text_box():
    result = _result(draft={"issue": "wound on leg"}, missing=("animal_identifier", "date", "time"))
    _, _, _, data = _parts(bw.build_booking_widget(result, "en-IN", ANIMALS, SYMPTOMS))
    assert data["value"]["problem"] == [] and data["value"]["other_problem"] == "wound on leg"


@pytest.mark.parametrize("date, time", [("30/10/2026", "10 am"), ("tomorrow", "10"), ("", ""), (None, None), (5, 7)])
def test_badly_shaped_dates_and_times_are_left_empty(date, time):
    result = _result(draft={"date": date, "time": time}, missing=("animal_identifier",))
    _, _, _, data = _parts(bw.build_booking_widget(result, "en-IN", ANIMALS, SYMPTOMS))
    assert data["value"]["date"] == "" and data["value"]["time"] == ""


def test_animal_dropdown_puts_the_chosen_and_offered_first_names_before_tags_and_no_duplicates():
    result = _result(draft={"animal_identifier": "MOTI"}, missing=("issue", "date", "time"))
    _, _, comps, _ = _parts(bw.build_booking_widget(result, "en-IN", ANIMALS, SYMPTOMS))
    labels = [o["label"] for o in comps["animal"]["options"]]
    assert labels[0] == "MOTI"
    assert labels.index("GAURI") < labels.index("TAG-001-1")
    assert len({l.lower() for l in labels}) == len(labels), "GAURI / gauri shown once"
    assert comps["animal"]["maxAllowedSelections"] == 1


def test_animals_offered_by_the_flow_come_first_but_symptom_pills_are_not_animals():
    offered = {"choices": ["LAKSHMI", "MOTI"], "other_label": "Other", "other_allowed": True}
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(options=offered), "en-IN", ANIMALS, SYMPTOMS))
    assert [o["label"] for o in comps["animal"]["options"]][:2] == ["LAKSHMI", "MOTI"]
    symptom_pills = {"choices": SYMPTOMS, "other_label": "Other", "other_allowed": True}
    result = _result(draft={"animal_identifier": "GAURI"}, missing=("issue", "date", "time"), options=symptom_pills)
    _, _, comps, _ = _parts(bw.build_booking_widget(result, "en-IN", ANIMALS, SYMPTOMS))
    assert "Fever" not in [o["label"] for o in comps["animal"]["options"]]


def test_a_pill_that_is_not_one_of_the_farmers_animals_is_not_promoted():
    offered = {"choices": ["NOT-MY-ANIMAL", "MOTI"], "other_label": "Other", "other_allowed": True}
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(options=offered), "en-IN", ANIMALS, SYMPTOMS))
    labels = [o["label"] for o in comps["animal"]["options"]]
    assert labels[0] == "MOTI" and "NOT-MY-ANIMAL" not in labels


def test_the_animal_list_is_capped():
    many = [SimpleNamespace(id=str(i), tag_or_name=f"TAG-{i}") for i in range(200)]
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(), "en-IN", many, SYMPTOMS))
    assert len(comps["animal"]["options"]) == bw.MAX_ANIMAL_CHOICES


def test_a_farmer_with_no_animals_still_gets_a_form():
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(), "en-IN", [], SYMPTOMS))
    assert comps["animal"]["options"] == []


def test_no_symptom_pills_means_no_problem_picker():
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(), "en-IN", ANIMALS, []))
    assert "problem" not in comps and "problem" not in comps["form"]["children"]


@pytest.mark.parametrize("lang", ["en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN"])
def test_labels_are_in_the_farmers_language(lang):
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(), lang, ANIMALS, SYMPTOMS))
    text = bw._TEXT[lang.split("-")[0]]
    assert comps["title"]["text"] == text["title"] and comps["book_text"]["text"] == text["book"]
    assert comps["other_problem"]["label"] == text["other_problem"]


def test_every_language_has_every_label():
    assert all(set(t) == set(bw._TEXT["en"]) for t in bw._TEXT.values())


@pytest.mark.parametrize("language", ["fr-FR", "", None])
def test_an_unknown_language_gets_english_labels(language):
    _, _, comps, _ = _parts(bw.build_booking_widget(_result(), language, ANIMALS, SYMPTOMS))
    assert comps["title"]["text"] == bw._TEXT["en"]["title"]


@pytest.mark.parametrize("state", ["CONFIRMING", "READY_TO_SUBMIT", "SUBMITTED", "CANCELLED", None, "whatever"])
def test_no_form_outside_collecting(state):
    assert bw.build_booking_widget(_result(state=state), "en-IN", ANIMALS, SYMPTOMS) is None


def test_correcting_shows_the_form():
    assert bw.build_booking_widget(_result(state="CORRECTING"), "en-IN", ANIMALS, SYMPTOMS) is not None


def test_no_form_when_nothing_is_missing():
    assert bw.build_booking_widget(_result(missing=()), "en-IN", ANIMALS, SYMPTOMS) is None


@pytest.mark.parametrize("bad", [None, "text", 5, [], {"state": "COLLECTING"}])
def test_malformed_results_give_no_form(bad):
    assert bw.build_booking_widget(bad, "en-IN", ANIMALS, SYMPTOMS) is None


def test_a_draft_that_is_not_a_dict_does_not_break_the_form():
    result = _result()
    result["draft"] = "broken"
    assert bw.build_booking_widget(result, "en-IN", ANIMALS, SYMPTOMS) is not None


@pytest.mark.parametrize("value, on", [(None, True), ("", True), ("true", True), ("1", True),
                                       ("false", False), ("0", False), ("off", False), ("NO", False)])
def test_kill_switch(monkeypatch, value, on):
    if value is None:
        monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    else:
        monkeypatch.setenv("CHAT_A2UI_WIDGETS", value)
    assert bw.widgets_enabled() is on


def test_switched_off_sends_nothing_and_loads_nothing(monkeypatch):
    monkeypatch.setenv("CHAT_A2UI_WIDGETS", "false")
    assert bw.booking_widget_for("f-001", "s1", _result(), "en-IN") is None


def test_a_failure_while_building_drops_only_the_widget(monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)

    def boom(*a, **k):
        raise RuntimeError("animals unavailable")

    monkeypatch.setattr(bw, "build_booking_widget", boom)
    assert bw.booking_widget_for("f-001", "s1", _result(), "en-IN") is None


def test_no_animal_lookup_outside_collecting(monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    called = []
    monkeypatch.setattr(bw, "build_booking_widget", lambda *a, **k: called.append(1))
    assert bw.booking_widget_for("f-001", "s1", _result(state="CONFIRMING"), "en-IN") is None
    assert called == []


def test_real_farmer_data_end_to_end(monkeypatch):
    """Uses the repo's own storage and symptom pills for f-001 (the eval
    farmer), with the main_backend animal call switched off."""
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    from services.flokiq_sync import client as flokiq_sync
    monkeypatch.setattr(flokiq_sync, "get_farm_animals", lambda farmer_id, *a, **k: [])
    messages = bw.booking_widget_for("f-001", "s1", _result(), "hi-IN")
    assert messages is not None
    _, _, comps, _ = _parts(messages)
    labels = [o["label"] for o in comps["animal"]["options"]]
    assert "GAURI" in labels and len(labels) <= bw.MAX_ANIMAL_CHOICES
    assert comps["problem"]["options"], "symptom pills from appointment_supervisor"
    assert messages[0]["createSurface"]["surfaceId"] == "booking-s1"
