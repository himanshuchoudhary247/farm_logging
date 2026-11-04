"""Several problems at once in the A2UI booking form: any number of problem
chips can be picked, and problems the booking already holds (its issue and
every symptom) show as selected chips, the rest in the "Other problem" box.

`result` uses the shape appointment_supervisor._response() returns, as in
test_a2ui_booking_widget.py."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.a2ui import booking_widget as bw
from services.appointment_supervisor.service import _SYMPTOM_KEYS, _symptom_options
from services.common.draft_supervisor import SUPPORTED_LANGUAGES

ANIMALS = [SimpleNamespace(id="a1", tag_or_name="GAURI")]
SYMPTOMS = ["Not eating", "Fever", "Limping", "Swelling", "Not drinking"]
EN_ALIASES = dict(zip(_SYMPTOM_KEYS, SYMPTOMS))


def _result(draft=None, missing=("animal_identifier", "issue", "date", "time")):
    return {
        "session_id": "s1", "state": "COLLECTING", "language": "en-IN", "transcript": None,
        "draft": {"symptoms": [], "attachments": [], "miscellaneous_notes": "", **(draft or {})},
        "missing_fields": list(missing),
        "response_text": "Hello.", "prompt_text": None,
        "response_audio_base64": None, "audio_error": None,
    }


def _comps_and_data(messages):
    _, update, data = messages
    return {c["id"]: c for c in update["updateComponents"]["components"]}, data["updateDataModel"]["value"]


def test_problem_picker_allows_several_choices_and_animal_stays_single():
    comps, _ = _comps_and_data(bw.build_booking_widget(_result(), "en-IN", ANIMALS, SYMPTOMS))
    assert "maxAllowedSelections" not in comps["problem"]
    assert comps["animal"]["maxAllowedSelections"] == 1


def test_book_still_sends_the_problems_in_the_one_message():
    comps, _ = _comps_and_data(bw.build_booking_widget(_result(), "en-IN", ANIMALS, SYMPTOMS))
    context = comps["book"]["action"]["event"]["context"]
    assert context["problem"] == {"path": "/booking/problem"}
    assert context["other problem"] == {"path": "/booking/other_problem"}


def test_issue_and_symptoms_already_given_show_as_selected_chips():
    # What the booking holds after "she is not eating and has fever".
    draft = {"issue": "not eating", "symptoms": ["not eating", "fever"]}
    _, data = _comps_and_data(bw.build_booking_widget(
        _result(draft=draft), "en-IN", ANIMALS, SYMPTOMS, symptom_aliases=EN_ALIASES))
    assert data["problem"] == ["Not eating", "Fever"]
    assert data["other_problem"] == ""


def test_problems_without_a_chip_go_to_the_box_once():
    draft = {"issue": "wound on leg", "symptoms": ["fever", "wound", "wound on leg", "cough"]}
    _, data = _comps_and_data(bw.build_booking_widget(
        _result(draft=draft), "en-IN", ANIMALS, SYMPTOMS, symptom_aliases=EN_ALIASES))
    assert data["problem"] == ["Fever"]
    assert data["other_problem"] == "wound on leg, cough"


def test_labels_match_in_any_case_without_aliases():
    _, data = _comps_and_data(bw.build_booking_widget(
        _result(draft={"issue": "FEVER", "symptoms": ["limping"]}), "en-IN", ANIMALS, SYMPTOMS))
    assert data["problem"] == ["Fever", "Limping"]


def test_nothing_given_yet_means_nothing_selected():
    _, data = _comps_and_data(bw.build_booking_widget(_result(), "en-IN", ANIMALS, SYMPTOMS))
    assert data["problem"] == [] and data["other_problem"] == ""


def test_symptoms_that_are_not_a_list_are_ignored():
    _, data = _comps_and_data(bw.build_booking_widget(
        _result(draft={"issue": "fever", "symptoms": "fever"}), "en-IN", ANIMALS, SYMPTOMS, symptom_aliases=EN_ALIASES))
    assert data["problem"] == ["Fever"]


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_every_language_shows_the_given_problems_as_its_own_chips(monkeypatch, language):
    """End to end through booking_widget_for with the real chip labels of
    each language: the booking's English symptom words select the chips."""
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    from services.flokiq_sync import client as flokiq_sync
    monkeypatch.setattr(flokiq_sync, "get_farm_animals", lambda farmer_id, *a, **k: [])
    result = _result(draft={"issue": "fever", "symptoms": ["fever", "not eating"]})
    result["language"] = language
    comps, data = _comps_and_data(bw.booking_widget_for("f-001", "s1", result, language))
    chips = _symptom_options(language)["choices"]
    assert data["problem"] == [chips[_SYMPTOM_KEYS.index("fever")], chips[_SYMPTOM_KEYS.index("not eating")]]
    assert data["other_problem"] == ""
    assert "maxAllowedSelections" not in comps["problem"]
