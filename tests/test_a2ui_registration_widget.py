"""Tests for the A2UI new-animal registration form
(services/a2ui/registration_widget.py) and the widget dispatcher
(services/a2ui/widgets.py).

The results fed to the widget come from the real AnimalRegistrationSupervisor
(only the LLM extraction, speech and animal lists are replaced), so the form
is tested against exactly what it receives in the chat."""
from __future__ import annotations

import json

import pytest

from services.a2ui import registration_widget as rw
from services.a2ui import widgets
from services.animal_registration import service as registration
from services.animal_registration.service import AnimalRegistrationSupervisor


@pytest.fixture
def sup(tmp_path, monkeypatch):
    monkeypatch.setattr(registration, "synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr(registration, "animals_for_farmer", lambda farmer_id: [])
    monkeypatch.setattr(registration.flokiq_sync, "get_farm_animals", lambda farmer_id, *a, **k: [])
    return AnimalRegistrationSupervisor(tmp_path)


def _turns(sup, entities_by_turn, language="en-IN"):
    """Runs one real turn per entities dict and returns every result."""
    calls = iter(entities_by_turn)
    sup._extract = lambda draft, text: next(calls, {})
    return [sup.turn("f-001", "s1", f"turn {i}", language, include_audio=False) for i in range(len(entities_by_turn))]


def _form(result, language="en-IN", surface_id="register-s1"):
    lang = rw.lang_code(language, registration._LABELS)
    return rw.build_registration_widget(result, language, registration._BREEDS_BY_SPECIES,
                                        field_labels=registration._LABELS.get(lang),
                                        value_labels=registration._VALUE_LABELS.get(lang),
                                        surface_id=surface_id)


def _parts(messages):
    create, update, data = messages
    comps = {c["id"]: c for c in update["updateComponents"]["components"]}
    return create["createSurface"], update["updateComponents"], comps, data["updateDataModel"]


def _values(comp):
    return [o["value"] for o in comp["options"]]


# ---- shape -------------------------------------------------------------

def test_first_turn_gets_an_empty_form_in_a2ui_v09(sup):
    [first] = _turns(sup, [{}])
    assert first["state"] == "COLLECTING"
    messages = _form(first)
    assert [list(m)[1] for m in messages] == ["createSurface", "updateComponents", "updateDataModel"]
    assert all(m["version"] == "v0.9" for m in messages)
    create, update, comps, data = _parts(messages)
    assert create["surfaceId"] == update["surfaceId"] == data["surfaceId"] == "register-s1"
    assert comps["root"]["component"] == "Card"
    assert data == {"surfaceId": "register-s1", "path": "/animal",
                    "value": {"animal_id": "", "species": [], "breed": [], "sex": []}}
    json.dumps(messages, ensure_ascii=False)


def test_only_basic_catalog_components_and_every_reference_exists(sup):
    allowed = {"Card", "Column", "Row", "Text", "TextField", "DateTimeInput", "ChoicePicker", "Button", "Divider"}
    [first] = _turns(sup, [{}])
    _, _, comps, _ = _parts(_form(first))
    assert {c["component"] for c in comps.values()} <= allowed
    for c in comps.values():
        for ref in ([c["child"]] if "child" in c else []) + list(c.get("children") or []):
            assert ref in comps, (c["id"], ref)


def test_register_button_sends_every_field(sup):
    [first] = _turns(sup, [{}])
    _, _, comps, data = _parts(_form(first))
    event = comps["register"]["action"]["event"]
    assert event["name"] == "submit_registration"
    assert {k: v["path"] for k, v in event["context"].items()} == {
        "animal ID": "/animal/animal_id", "species": "/animal/species",
        "breed": "/animal/breed", "sex": "/animal/sex"}
    for path in ("animal_id", "species", "breed", "sex"):
        assert path in data["value"]


# ---- options and prefill ----------------------------------------------

def test_species_and_sex_send_the_stored_english_values(sup):
    [first] = _turns(sup, [{}])
    _, _, comps, _ = _parts(_form(first))
    assert _values(comps["species"]) == ["goat", "sheep"]
    assert _values(comps["sex"]) == ["female", "male"]
    assert comps["species"]["maxAllowedSelections"] == comps["sex"]["maxAllowedSelections"] == 1


def test_every_breed_is_offered_once_with_the_species_it_belongs_to(sup):
    [first] = _turns(sup, [{}])
    _, _, comps, _ = _parts(_form(first))
    options = comps["breed"]["options"]
    names = [o["value"] for o in options]
    assert set(registration._GOAT_BREEDS) | set(registration._SHEEP_BREEDS) == set(names)
    assert len(names) == len({n.lower() for n in names}), "Gaddi / Marwari are in both lists, shown once"
    kinds = {o["value"]: o["visibleWhen"] for o in options}
    assert kinds["Sirohi"] == {"path": "/animal/species", "in": ["goat"]}
    assert kinds["Nellore"] == {"path": "/animal/species", "in": ["sheep"]}
    assert kinds["Gaddi"] == {"path": "/animal/species", "in": ["goat", "sheep"]}
    # The rule points at the species picker's own binding.
    assert comps["species"]["selections"] == {"path": kinds["Sirohi"]["path"]}


@pytest.mark.parametrize("species", ["goat", "sheep"])
def test_the_tags_match_the_registrations_own_breed_lists(sup, species):
    """Filtering by the tag gives exactly that species' list, so the app
    shows the same breeds animal_registration accepts."""
    [first] = _turns(sup, [{}])
    _, _, comps, _ = _parts(_form(first))
    shown = [o["value"] for o in comps["breed"]["options"] if species in o["visibleWhen"]["in"]]
    # Same names (order follows the combined list: shared names sit with the goat breeds).
    assert sorted(shown) == sorted(registration._BREEDS_BY_SPECIES[species])
    assert all(registration._match_breed(n, species) == n for n in shown)


@pytest.mark.parametrize("species", ["goat", "sheep"])
def test_a_species_already_given_is_preselected_and_the_full_list_still_sent(sup, species):
    """The app filters by the selected species, and the farmer can still
    switch species in the form, so every breed is always sent."""
    results = _turns(sup, [{"species": species}])
    _, _, comps, data = _parts(_form(results[-1]))
    assert data["value"]["species"] == [species]
    assert len(comps["breed"]["options"]) == len(rw._breed_options(registration._BREEDS_BY_SPECIES))


def test_values_already_given_are_filled_in(sup):
    results = _turns(sup, [{"unique_animal_id": "GAURI-2", "species": "goat", "sex": "female"}])
    assert results[-1]["missing_fields"] == ["breed"]
    _, _, _, data = _parts(_form(results[-1]))
    assert data["value"] == {"animal_id": "GAURI-2", "species": ["goat"], "breed": [], "sex": ["female"]}


def test_a_breed_said_before_the_species_is_kept_but_not_preselected_if_unknown(sup):
    results = _turns(sup, [{"breed": "desi mix"}])
    assert results[-1]["draft"]["breed"] == "desi mix"
    _, _, _, data = _parts(_form(results[-1]))
    assert data["value"]["breed"] == []


def test_a_known_breed_given_with_the_species_is_preselected(sup):
    results = _turns(sup, [{"species": "goat", "breed": "sirohi"}])
    _, _, _, data = _parts(_form(results[-1]))
    assert data["value"]["breed"] == ["Sirohi"]


def test_a_duplicate_id_brings_the_form_back_with_the_id_cleared(sup, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(registration, "animals_for_farmer",
                        lambda farmer_id: [SimpleNamespace(id="a1", tag_or_name="GAURI")])
    results = _turns(sup, [{"unique_animal_id": "gauri", "species": "goat", "breed": "Sirohi", "sex": "female"}])
    assert "already registered" in results[-1]["response_text"]
    _, _, _, data = _parts(_form(results[-1]))
    assert data["value"]["animal_id"] == "" and data["value"]["species"] == ["goat"]


def test_a_breed_that_does_not_fit_the_species_brings_the_form_back(sup):
    results = _turns(sup, [{"species": "goat", "breed": "Nellore", "sex": "male", "unique_animal_id": "X1"}])
    assert results[-1]["state"] == "COLLECTING" and results[-1]["missing_fields"] == ["breed"]
    _, _, comps, data = _parts(_form(results[-1]))
    assert data["value"]["species"] == ["goat"] and data["value"]["breed"] == []
    nellore = next(o for o in comps["breed"]["options"] if o["value"] == "Nellore")
    assert "goat" not in nellore["visibleWhen"]["in"], "hidden while goat is selected"


def test_a_breed_kept_from_before_the_species_is_not_preselected_if_it_does_not_fit():
    """A raw breed said before the species stays in the draft unchecked;
    the form must not pre-select a sheep breed next to goat."""
    result = {"state": "COLLECTING", "missing_fields": ["unique_animal_id"], "language": "en-IN",
              "draft": {"species": "goat", "breed": "Nellore", "sex": "male"}}
    _, _, _, data = _parts(_form(result))
    assert data["value"]["breed"] == []


# ---- when the form is shown ---------------------------------------------

def test_no_form_once_every_required_detail_is_given(sup):
    results = _turns(sup, [{"unique_animal_id": "X1", "species": "goat", "breed": "Sirohi", "sex": "male"}])
    assert results[-1]["state"] == "COLLECTING_OPTIONAL"
    assert _form(results[-1]) is None


def test_no_form_at_confirm_or_after_saving(sup, monkeypatch):
    monkeypatch.setattr(registration, "append_animal", lambda **kw: type(
        "A", (), {"id": "new-1", "tag_or_name": kw["tag_or_name"], "model_dump": lambda self: dict(kw)})())
    results = _turns(sup, [{"unique_animal_id": "X1", "species": "goat", "breed": "Sirohi", "sex": "male"},
                           {"wants_to_skip_optional": True}])
    assert results[-1]["state"] == "CONFIRMING" and _form(results[-1]) is None
    saved = sup.confirm("f-001", "s1", "yes", include_audio=False)
    assert saved["state"] == "SUBMITTED" and _form(saved) is None


def test_no_form_while_correcting(sup):
    results = _turns(sup, [{"unique_animal_id": "X1", "species": "goat", "breed": "Sirohi", "sex": "male"},
                           {"wants_to_skip_optional": True}])
    corrected = sup.confirm("f-001", "s1", "no", include_audio=False)
    assert corrected["state"] == "CORRECTING" and _form(corrected) is None


@pytest.mark.parametrize("bad", [None, "text", 5, [], {"state": "COLLECTING"}, {"state": "COLLECTING", "missing_fields": []}])
def test_malformed_results_give_no_form(bad):
    assert _form(bad) is None


def test_a_draft_that_is_not_a_dict_does_not_break_the_form():
    result = {"state": "COLLECTING", "missing_fields": ["species"], "draft": "broken", "language": "en-IN"}
    assert _form(result) is not None


# ---- language -----------------------------------------------------------

@pytest.mark.parametrize("lang", ["en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN"])
def test_labels_are_in_the_farmers_language(sup, lang):
    [first] = _turns(sup, [{}], language=lang)
    _, _, comps, _ = _parts(_form(first, lang))
    code = lang.split("-")[0]
    assert comps["title"]["text"] == rw._TEXT[code]["title"]
    assert comps["register_text"]["text"] == rw._TEXT[code]["register"]
    assert comps["breed_label"]["text"].lower() == registration._LABELS[code]["breed"].lower()
    goat = next(o for o in comps["species"]["options"] if o["value"] == "goat")
    assert goat["label"] == registration._VALUE_LABELS.get(code, {}).get("goat", "goat")


def test_every_language_has_every_label():
    assert set(rw._TEXT) == set(registration._LABELS)
    assert all(set(t) == set(rw._TEXT["en"]) for t in rw._TEXT.values())


@pytest.mark.parametrize("language", ["fr-FR", "", None])
def test_an_unknown_language_gets_english_labels(language):
    result = {"state": "COLLECTING", "missing_fields": ["species"], "draft": {}}
    _, _, comps, _ = _parts(rw.build_registration_widget(result, language, registration._BREEDS_BY_SPECIES))
    assert comps["title"]["text"] == rw._TEXT["en"]["title"]
    assert comps["id_label"]["text"] == "Animal ID"


# ---- the live entry point and the dispatcher ------------------------------

def test_registration_widget_for_uses_the_registrations_own_lists(sup, monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    [first] = _turns(sup, [{}], language="hi-IN")
    messages = rw.registration_widget_for("f-001", "s1", first, "hi-IN")
    _, _, comps, _ = _parts(messages)
    assert messages[0]["createSurface"]["surfaceId"] == "register-s1"
    assert comps["title"]["text"] == rw._TEXT["hi"]["title"]
    assert "Sirohi" in _values(comps["breed"])


def test_switched_off_sends_nothing(sup, monkeypatch):
    monkeypatch.setenv("CHAT_A2UI_WIDGETS", "false")
    [first] = _turns(sup, [{}])
    assert rw.registration_widget_for("f-001", "s1", first, "en-IN") is None
    assert widgets.widget_for("animal_registration", "f-001", "s1", first, "en-IN") is None


def test_a_failure_while_building_drops_only_the_widget(sup, monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    [first] = _turns(sup, [{}])

    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(rw, "build_registration_widget", boom)
    assert rw.registration_widget_for("f-001", "s1", first, "en-IN") is None


def test_dispatcher_picks_the_form_by_agent(sup, monkeypatch):
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)
    [first] = _turns(sup, [{}])
    messages = widgets.widget_for("animal_registration", "f-001", "s1", first, "en-IN")
    assert messages[0]["createSurface"]["surfaceId"] == "register-s1"
    # Agents without a form, and results that are not dicts, get nothing.
    for agent in ("query_agent", "order_supervisor", "unknown"):
        assert widgets.widget_for(agent, "f-001", "s1", first, "en-IN") is None
    assert widgets.widget_for("animal_registration", "f-001", "s1", "not a dict", "en-IN") is None


def test_dispatcher_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setitem(widgets._BUILDERS, "animal_registration", boom)
    assert widgets.widget_for("animal_registration", "f-001", "s1", {"state": "COLLECTING"}, "en-IN") is None


def test_dispatcher_uses_the_language_of_the_result(monkeypatch):
    seen = {}
    monkeypatch.setitem(widgets._BUILDERS, "animal_registration",
                        lambda farmer_id, session_id, result, language: seen.setdefault("lang", language))
    widgets.widget_for("animal_registration", "f-001", "s1", {"language": "mr-IN"}, "en-IN")
    assert seen["lang"] == "mr-IN"
