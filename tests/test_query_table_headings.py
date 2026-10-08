"""Query result table headings follow the app's language: the script alone
can't tell Marathi from Hindi (both Devanagari), and Roman-script typing
looks like English."""
from services.chat_orchestrator import adk_router
from services.query_agent.adk_agent import _labels_language, _localize_columns, _localize_numbers


def test_marathi_app_gets_marathi_headings_not_hindi():
    assert _labels_language("hi", "mr-IN") == "mr"
    assert _localize_columns(["species", "breed"], _labels_language("hi", "mr-IN")) == ["प्रजाती", "जात"]


def test_underscore_locale_tag_normalized_same_as_dash():
    """"mr_IN" (underscore separator) must resolve the same as "mr-IN" --
    without normalizing it, an underscore tag fell through to script_lang,
    reinstating the Hindi-for-Marathi bug (found in deep-review of PR #41)."""
    assert _labels_language("hi", "mr_IN") == "mr"
    assert _labels_language("hi", "mr_IN") == _labels_language("hi", "mr-IN")


def test_headings_and_row_digits_use_the_same_language():
    """Columns and rows in the display block must agree on one language --
    previously rows used the raw script-detected language while columns
    used the app-preferred one, so an en-IN app user typing Hindi script
    could get English headings over Devanagari digits (found in
    deep-review of PR #41)."""
    labels_lang = _labels_language("hi", "en-IN")
    assert labels_lang == "en"
    assert _localize_numbers("12", labels_lang) == "12"  # not Devanagari १२


def test_localize_numbers_is_a_noop_for_a_language_with_no_native_digits():
    """Malayalam uses Western digits in practice (no _NATIVE_DIGITS entry)
    -- must short-circuit like English, not walk the whole tree retyping
    ints to str for no reason (found in deep-review of PR #39/#41)."""
    assert _localize_numbers(12, "ml") == 12
    assert isinstance(_localize_numbers(12, "ml"), int)
    assert _localize_numbers({"age": 12}, "ml") == {"age": 12}


def test_roman_script_typing_still_gets_app_language_headings():
    assert _labels_language("en", "hi-IN") == "hi"


def test_without_app_language_script_detection_is_unchanged():
    assert _labels_language("ta", None) == "ta"
    assert _labels_language("hi", None) == "hi"


def test_unknown_app_language_falls_back_to_script():
    assert _labels_language("kn", "xx-IN") == "kn"


def _async_returning(value):
    async def _f(*args, **kwargs):
        return value
    return _f


def test_router_passes_the_app_language_to_the_query_agent(monkeypatch):
    seen = {}

    def fake_query(query, farmer_id, session_id=None, app_language=None):
        seen["app_language"] = app_language
        return {"answer": "12", "sql": "SELECT ...", "data": {}}

    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_classify_intent_async", _async_returning("query"))
    monkeypatch.setattr(adk_router, "process_query_adk", fake_query)
    monkeypatch.setattr(adk_router, "synthesize_speech", lambda text, target_lang=None: (None, None))

    adk_router.route_turn_adk("f-1", "s-1", "किती जनावरे आहेत", "mr-IN")
    assert seen["app_language"] == "mr-IN"


def test_english_gets_readable_headings_not_db_names():
    assert _labels_language("en", "en-IN") == "en"
    assert _localize_columns(["tag_or_name", "age_years"], "en") == ["Tag / Name", "Age (years)"]
