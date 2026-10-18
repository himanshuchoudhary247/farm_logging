"""The query agent adds a short note to the farmer's message when a word
most likely names one of the farmer's own animals (any script/spelling).

Without it the model read Telugu "గోరి" as "గొర్రె" (sheep) and listed sheep
breeds, or answered that no animal "गोरी" exists while listing GAURI.
"""
from services.query_agent import adk_agent
from services.query_agent.adk_agent import _INSTRUCTION_TEMPLATE, _with_name_notes


def _fake_store(monkeypatch, names=None, fail=None):
    """execute_query with the shape db.execute_query really returns."""
    def fake(sql, farmer_id):
        if fail == "raise":
            raise ValueError("db down")
        if fail == "error":
            return {"success": False, "sql": sql, "error": "no such table: animals"}
        joined = "\n".join(names) if names else None
        return {"success": True, "sql": sql, "columns": ["names"], "rows": [[joined]],
                "row_count": 1, "truncated": False}
    monkeypatch.setattr(adk_agent, "execute_query", fake)


def test_note_names_the_stored_animal(monkeypatch):
    _fake_store(monkeypatch, ["GAURI", "MOTI", "LAKSHMI"])
    out = _with_name_notes("గోరి బ్రీడ్ ఏమిటి?", "farmer-x")
    assert out.startswith("గోరి బ్రీడ్ ఏమిటి?")
    assert "GAURI" in out and "MOTI" not in out


def test_no_match_leaves_the_message_unchanged(monkeypatch):
    _fake_store(monkeypatch, ["GAURI", "MOTI"])
    assert _with_name_notes("how many goats do I have", "farmer-x") == "how many goats do I have"


def test_farmer_with_no_animals(monkeypatch):
    _fake_store(monkeypatch, [])
    assert _with_name_notes("गोरी की नस्ल", "farmer-x") == "गोरी की नस्ल"


def test_store_failure_never_breaks_the_turn(monkeypatch):
    for mode in ("raise", "error"):
        _fake_store(monkeypatch, fail=mode)
        assert _with_name_notes("गोरी की नस्ल", "farmer-x") == "गोरी की नस्ल"


def test_kill_switch(monkeypatch):
    _fake_store(monkeypatch, ["GAURI"])
    monkeypatch.setenv("QUERY_AGENT_NAME_HINTS", "0")
    assert _with_name_notes("गोरी की नस्ल", "farmer-x") == "गोरी की नस्ल"


def test_at_most_three_notes(monkeypatch):
    _fake_store(monkeypatch, ["GAURI", "MOTI", "LAKSHMI", "SHERU"])
    out = _with_name_notes("गोरी मोती लक्ष्मी शेरू", "farmer-x")
    assert out.count("most likely means") == 3


def test_instruction_explains_the_note():
    assert "most likely refers to" in _INSTRUCTION_TEMPLATE
    assert _INSTRUCTION_TEMPLATE.rstrip().endswith("{farm_values}")


def test_real_farm_data():
    # The real store and SQL (f-001, the demo farmer in data/).
    out = _with_name_notes("గోరి బ్రీడ్ ఏమిటి?", "f-001")
    assert "GAURI" in out



def test_instruction_covers_local_words_in_english_letters():
    # Roman-script Tamil "ennidam ethanai aadugal irukku" (how many goats)
    # was answered with all 53 animals: the species filter was dropped.
    assert "English letters" in _INSTRUCTION_TEMPLATE
    assert "never count or list all animals without that species filter" in _INSTRUCTION_TEMPLATE


def test_instruction_covers_a_word_that_means_more_than_one_species():
    # Roman Tamil "ennidam ethanai aadugal irukku": "aadu" alone covers goats
    # and sheep; the agent picked sheep only (7) in 2 of 3 runs. It must give
    # each species it can mean, and still filter when the kind is said.
    assert "can mean more than one stored species" in _INSTRUCTION_TEMPLATE
    assert "do not pick one species yourself" in _INSTRUCTION_TEMPLATE
    assert "do not list the whole farm" in _INSTRUCTION_TEMPLATE
    assert "filter on that one species only" in _INSTRUCTION_TEMPLATE
    
       