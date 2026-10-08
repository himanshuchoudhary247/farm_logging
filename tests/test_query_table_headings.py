"""Query result table headings follow the app's language: the script alone
can't tell Marathi from Hindi (both Devanagari), and Roman-script typing
looks like English."""
from services.chat_orchestrator import adk_router
from services.query_agent.adk_agent import _labels_language, _localize_columns


def test_marathi_app_gets_marathi_headings_not_hindi():
    assert _labels_language("hi", "mr-IN") == "mr"
    assert _localize_columns(["species", "breed"], _labels_language("hi", "mr-IN")) == ["प्रजाती", "जात"]


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
