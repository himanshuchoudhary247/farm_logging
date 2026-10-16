"""The query agent's prompt lists the farmer's real species, breeds and animal
names ("Values in this farmer's records"), so the model maps local-language
words and other-script names to stored values instead of guessing.

Found by the evals suite (evals/, layer 1, 3 runs each on dev 8d172d8):
Kannada chicken count said "no chickens" 3/3, Marathi buffalo count was 2 or 9
(not 16) 3/3, Telugu "గౌరి" never matched 'GAURI' 3/3, and "RAJA कौन सा जानवर
है?" was refused as general knowledge 3/3.
"""
from services.query_agent import adk_agent
from services.query_agent.adk_agent import _INSTRUCTION_TEMPLATE, _farm_values_for_prompt


def test_values_block_uses_the_farmers_real_data():
    # f-001 is the demo farmer in data/ (53 animals, 5 species).
    block = _farm_values_for_prompt("f-001")
    for species in ("buffalo", "chicken", "cow", "goat", "sheep"):
        assert species in block
    assert "sheep: Nali" in block and "buffalo: Nili-Ravi" in block
    for name in ("GAURI", "RAJA", "LAKSHMI", "MOTI", "BIJLI"):
        assert name in block


def test_values_block_is_in_the_instruction():
    block = _farm_values_for_prompt("f-001")
    text = _INSTRUCTION_TEMPLATE.format(schema="(schema)", farm_values=block)
    assert "Values in this farmer's records" in text
    assert "{farm_values}" not in text and "{schema}" not in text


def test_values_block_comes_last_so_the_static_prefix_is_shared():
    # Everything before the per-farmer block must be the same for every
    # farmer, so prompt caching (bedrock_adapter.py) can reuse it.
    assert _INSTRUCTION_TEMPLATE.rstrip().endswith("{farm_values}")
    assert _INSTRUCTION_TEMPLATE.count("{farm_values}") == 1


def test_kill_switch_removes_the_block(monkeypatch):
    monkeypatch.setenv("QUERY_AGENT_VALUE_HINTS", "0")
    assert _farm_values_for_prompt("f-001") == ""


def test_farmer_without_animals_gets_no_block():
    assert _farm_values_for_prompt("no-such-farmer-for-tests") == ""


def test_query_error_drops_the_hint_instead_of_failing(monkeypatch):
    def boom(sql, farmer_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(adk_agent, "execute_query", boom)
    assert _farm_values_for_prompt("f-001") == ""


def test_braces_in_stored_values_never_reach_the_instruction(monkeypatch):
    # ADK reads {name} in an instruction as a session-state variable.
    def fake(sql, farmer_id):
        return {"success": True, "rows": [["{bad}"], ["GOOD"]]}
    monkeypatch.setattr(adk_agent, "execute_query", fake)
    block = _farm_values_for_prompt("f-001")
    assert "{" not in block and "}" not in block
    assert "bad" in block and "GOOD" in block


def test_long_name_lists_are_capped(monkeypatch):
    names = [[f"TAG-{i:04d}"] for i in range(adk_agent._MAX_HINT_NAMES + 50)]

    def fake(sql, farmer_id):
        return {"success": True, "rows": names if "tag_or_name" in sql else [["goat"]]}
    monkeypatch.setattr(adk_agent, "execute_query", fake)
    block = _farm_values_for_prompt("f-001")
    assert f"TAG-{adk_agent._MAX_HINT_NAMES - 1:04d}" in block
    assert f"TAG-{adk_agent._MAX_HINT_NAMES:04d}" not in block
    assert "more exist" in block
    