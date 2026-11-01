"""New-animal registration form as an A2UI widget (https://a2ui.org, spec v0.9).

While Chocolate is collecting the required details of a new animal, its
reply also carries a small form -- animal ID, goat/sheep, breed, male/female
and a Register button -- so the farmer can give everything at once instead
of one question per turn.

The registration itself does not change: the app turns the Register button
into one ordinary chat message ("animal ID: GAURI-2; species: goat; breed:
Sirohi; sex: female") that goes through animal_registration exactly like a
typed message, so the duplicate-ID check, the breed check against the
species, the optional-details step and the final "Shall I save this?" all
still apply.

Only shown while required details are missing (state COLLECTING). In the
later steps -- optional details, the final confirmation, a correction --
the existing questions and buttons take over.

Breeds differ by species. Every breed option carries "visibleWhen" (the
species it belongs to), so the app shows only the chosen species' breeds the
moment goat or sheep is tapped, with no extra request. "visibleWhen" is a
FlokIQ addition on top of the basic catalog's option shape (label, value): a
renderer that does not know it shows every breed, and a breed that does not
fit the species is still caught by animal_registration's own check.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Optional

from services.a2ui.common import clean, lang_code, surface_messages, widgets_enabled

_log = logging.getLogger("a2ui_registration_widget")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

SUBMIT_EVENT = "submit_registration"
_FORM_STATES = {"COLLECTING"}
_SPECIES = ("goat", "sheep")
_SEXES = ("female", "male")

# Title and button in the farmer's language. Field names come from
# animal_registration's own labels, so the form and the readback use the
# same words.
_TEXT: dict[str, dict[str, str]] = {
    "en": {"title": "Register a new animal", "register": "Register"},
    "hi": {"title": "नया पशु जोड़ें", "register": "रजिस्टर करें"},
    "mr": {"title": "नवीन जनावर नोंदवा", "register": "नोंदणी करा"},
    "ta": {"title": "புதிய விலங்கைப் பதிவு செய்", "register": "பதிவு செய்"},
    "te": {"title": "కొత్త జంతువును నమోదు చేయండి", "register": "నమోదు చేయండి"},
    "kn": {"title": "ಹೊಸ ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸಿ", "register": "ನೋಂದಾಯಿಸಿ"},
    "ml": {"title": "പുതിയ മൃഗത്തെ രജിസ്റ്റർ ചെയ്യുക", "register": "രജിസ്റ്റർ ചെയ്യുക"},
}
_FIELD_FALLBACK = {"unique_animal_id": "animal ID", "species": "species", "breed": "breed", "sex": "sex"}
_SPECIES_PATH = "/animal/species"


def _caption(label: str) -> str:
    return label[:1].upper() + label[1:] if label else label


def _breed_options(breeds_by_species: Mapping[str, Iterable[str]]) -> list[tuple[str, list[str]]]:
    """Every breed once, in list order, with the species it belongs to. A
    few names (Gaddi, Marwari, the regional "Local" types) are breeds of
    both goat and sheep, so they are shown for either."""
    order: list[str] = []
    species_of: dict[str, list[str]] = {}
    shown: dict[str, str] = {}
    for species in _SPECIES:
        for name in breeds_by_species.get(species) or []:
            text = clean(name)
            if not text:
                continue
            key = text.lower()
            if key not in species_of:
                order.append(key)
                species_of[key] = []
                shown[key] = text
            if species not in species_of[key]:
                species_of[key].append(species)
    return [(shown[k], species_of[k]) for k in order]


def build_registration_widget(result: dict[str, Any], language: str,
                              breeds_by_species: Mapping[str, Iterable[str]],
                              field_labels: Optional[Mapping[str, str]] = None,
                              value_labels: Optional[Mapping[str, str]] = None,
                              surface_id: str = "register") -> Optional[list[dict]]:
    """A2UI v0.9 messages for the registration form, or None when no form
    should be shown (not collecting, nothing missing, malformed result).

    `result` is animal_registration's turn result (state, draft,
    missing_fields). Values already given are filled in so the farmer only
    completes what is missing."""
    if not isinstance(result, dict) or result.get("state") not in _FORM_STATES:
        return None
    if not result.get("missing_fields"):
        return None
    draft = result.get("draft") if isinstance(result.get("draft"), dict) else {}
    text = _TEXT[lang_code(language, _TEXT)]
    fields = {**_FIELD_FALLBACK, **{k: v for k, v in (field_labels or {}).items() if isinstance(v, str) and v}}
    words = value_labels or {}

    species = clean(draft.get("species")).lower()
    species = species if species in _SPECIES else ""
    sex = clean(draft.get("sex")).lower()
    sex = sex if sex in _SEXES else ""
    breeds = _breed_options(breeds_by_species)
    breed = clean(draft.get("breed"))
    fits = {name for name, kinds in breeds if not species or species in kinds}
    data = {
        "animal_id": clean(draft.get("unique_animal_id")),
        "species": [species] if species else [],
        # A breed outside the list (a raw guess, "not specified", or one
        # that does not fit the species) is not pre-selected; the dropdown
        # would have nothing to show for it.
        "breed": [breed] if breed in fits else [],
        "sex": [sex] if sex else [],
    }

    def label_of(value: str) -> str:
        return words.get(value) or value

    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Card", "child": "form"},
        {"id": "form", "component": "Column",
         "children": ["title", "id_label", "animal_id", "species_label", "species",
                      "breed_label", "breed", "sex_label", "sex", "register"]},
        {"id": "title", "component": "Text", "text": text["title"], "variant": "h4"},
        {"id": "id_label", "component": "Text", "text": _caption(fields["unique_animal_id"]), "variant": "caption"},
        {"id": "animal_id", "component": "TextField", "label": _caption(fields["unique_animal_id"]),
         "value": {"path": "/animal/animal_id"}, "textFieldType": "shortText"},
        {"id": "species_label", "component": "Text", "text": _caption(fields["species"]), "variant": "caption"},
        {"id": "species", "component": "ChoicePicker",
         "options": [{"label": label_of(s), "value": s} for s in _SPECIES],
         "selections": {"path": _SPECIES_PATH}, "maxAllowedSelections": 1},
        {"id": "breed_label", "component": "Text", "text": _caption(fields["breed"]), "variant": "caption"},
        {"id": "breed", "component": "ChoicePicker",
         "options": [{"label": name, "value": name, "visibleWhen": {"path": _SPECIES_PATH, "in": kinds}}
                     for name, kinds in breeds],
         "selections": {"path": "/animal/breed"}, "maxAllowedSelections": 1},
        {"id": "sex_label", "component": "Text", "text": _caption(fields["sex"]), "variant": "caption"},
        {"id": "sex", "component": "ChoicePicker",
         "options": [{"label": label_of(s), "value": s} for s in _SEXES],
         "selections": {"path": "/animal/sex"}, "maxAllowedSelections": 1},
        {"id": "register", "component": "Button", "child": "register_text", "variant": "primary",
         "action": {"event": {"name": SUBMIT_EVENT, "context": {
             # Plain-word keys and stored English values ("goat", "female"):
             # the app sends them as "key: value" in one chat message, which
             # the registration extraction reads like any typed answer.
             "animal ID": {"path": "/animal/animal_id"},
             "species": {"path": "/animal/species"},
             "breed": {"path": "/animal/breed"},
             "sex": {"path": "/animal/sex"},
         }}}},
        {"id": "register_text", "component": "Text", "text": text["register"]},
    ]
    return surface_messages(surface_id, components, "/animal", data)


def registration_widget_for(farmer_id: str, session_id: str, result: dict[str, Any],
                            language: str) -> Optional[list[dict]]:
    """The form for this registration turn, or None. Never raises: a problem
    building the widget only drops the widget, never the reply."""
    if not widgets_enabled() or not isinstance(result, dict) or result.get("state") not in _FORM_STATES:
        return None
    try:
        # The same breed lists and words the registration itself checks
        # against and reads back, so the form offers what it will accept.
        from services.animal_registration import service as registration

        lang = lang_code(language, registration._LABELS)
        messages = build_registration_widget(
            result, language, registration._BREEDS_BY_SPECIES,
            field_labels=registration._LABELS.get(lang),
            value_labels=registration._VALUE_LABELS.get(lang),
            surface_id=f"register-{session_id}",
        )
    except Exception as exc:  # the reply must never fail because of the widget
        _log.warning("a2ui registration widget skipped farmer=%s err=%s", farmer_id, exc)
        return None
    if messages:
        _log.info("a2ui registration widget sent farmer=%s missing=%s", farmer_id,
                  ",".join(result.get("missing_fields") or []))
    return messages
