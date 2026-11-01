"""Tests for the A2UI farm records card (services/a2ui/query_widget.py).

The rows fed to the card come from the real query layer: records are saved
as the app's own models into a temporary data folder, the real
query_agent.db.execute_query runs the kind of SQL the query agent writes,
and the result is put together the way query_agent.adk_agent does it (same
localized headings via its own helpers). Only the LLM is left out, so the
card is tested against exactly what it receives in the chat."""
from __future__ import annotations

import json
import threading
from datetime import date

import pytest

from models import AIHealthLog, Animal, Appointment, Farmer, HealthLog, VaccinationRecord
from services.a2ui import query_widget as qw
from services.a2ui import widgets
from services.query_agent import adk_agent
from services.query_agent import db as query_db

FID = "f-qw-test"
LANGS = ("en", "hi", "mr", "ta", "te", "kn", "ml")
SUPPORTED = {"Card", "Column", "Row", "Text", "Divider"}
LONG_ADVICE = ("Keep the goat in a clean, well-ventilated but draft-free area. Ensure access to fresh, "
               "clean water to prevent dehydration. Offer easily digestible feed like green fodder. "
               "Watch for any changes in behavior, appetite, or breathing.")


def _animals(extra: int = 0) -> list[dict]:
    rows = [
        Animal(id="a-1", farmer_id=FID, species="goat", tag_or_name="GAURI", sex="female", breed="Sirohi",
               age_years=2.5, birth_date="2024-04-10"),
        Animal(id="a-2", farmer_id=FID, species="goat", tag_or_name="MOTI", sex="male", breed="Barbari", age_years=1),
        Animal(id="a-3", farmer_id=FID, species="sheep", tag_or_name="BHURI", sex="female", breed="Deccani",
               status="sick", age_years=3),
    ]
    rows += [Animal(id=f"a-x{i}", farmer_id=FID, species="sheep", tag_or_name=f"S-{i}", sex="male")
             for i in range(extra)]
    return [a.model_dump() for a in rows]


@pytest.fixture
def farm(tmp_path, monkeypatch):
    """A farm saved through the app's own models; returns a function that
    runs SQL through the real query layer and builds the query agent's result."""
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CHAT_A2UI_WIDGETS", raising=False)

    def save(name, rows):
        (tmp_path / name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def setup(extra_animals: int = 0):
        save("animals.json", _animals(extra_animals))
        save("farmers.json", [Farmer(id=FID, name="Ramesh", login_username="ramesh01", password_hash="pbkdf2$secret",
                                     phone="9000000001").model_dump()])
        save("health_logs.json", [HealthLog(id="h-1", farmer_id=FID, animal_id="a-1",
                                            recorded_at="2026-10-29T20:14:17.147916+00:00",
                                            issue="Reduced feed intake and mild fever",
                                            params={"appetite": "reduced", "temperature_c": 39.8},
                                            notes="").model_dump()])
        save("ai_health_logs.json", [
            AIHealthLog(log_id="c30edce1-7e6e-4c8b-b1cd-ec9ef55c1b56", farmer_id=FID, animal_id="a-1", pincode="",
                        symptoms_reported=["fever", "cough"], ai_diagnosis_suggestion="Possible respiratory infection.",
                        potential_ailments=["Respiratory infection"], first_aid_advice=LONG_ADVICE,
                        risk_level="High", source="ai_unverified",
                        log_timestamp="2026-10-29T20:30:00+00:00").model_dump(),
            AIHealthLog(log_id="d1", farmer_id=FID, animal_id="a-2", pincode="", symptoms_reported=["loose stool"],
                        ai_diagnosis_suggestion="Mild indigestion.", potential_ailments=[], first_aid_advice="Water.",
                        risk_level="Low", source="ai_unverified", log_timestamp="2026-10-28T05:00:00+00:00").model_dump(),
            AIHealthLog(log_id="d2", farmer_id=FID, animal_id="a-3", pincode="", symptoms_reported=["limping"],
                        ai_diagnosis_suggestion="Hoof problem.", potential_ailments=[], first_aid_advice="Rest.",
                        risk_level="Low", source="ai_unverified", log_timestamp="2026-10-27T05:00:00+00:00").model_dump(),
        ])
        save("vaccination_records.json", [
            VaccinationRecord(id="v-1", farmer_id=FID, animal_id="a-1", vaccine_name="PPR", status="pending",
                              due_date="2026-11-05", created_at="2026-10-01T00:00:00+00:00").model_dump(),
            VaccinationRecord(id="v-2", farmer_id=FID, animal_id="a-2", vaccine_name="PPR", status="administered",
                              administered_date="2026-10-02", created_at="2026-10-01T00:00:00+00:00").model_dump(),
            VaccinationRecord(id="v-3", farmer_id=FID, animal_id="a-3", vaccine_name="Enterotoxaemia",
                              status="pending", due_date="2026-11-09", created_at="2026-10-01T00:00:00+00:00").model_dump(),
        ])
        save("appointments.json", [Appointment(id="ap-1", farmer_id=FID, date="2026-11-01", time="10:00",
                                               status="confirmed", doctor_id="doc-9", animal_id="a-1",
                                               issue_summary="Fever", created_at="2026-10-30").model_dump()])
        query_db.clear_cache(FID)

    def run(sql: str, language: str = "en-IN", answer: str = "Here you go."):
        sql_result = query_db.execute_query(sql, FID)
        assert sql_result["success"], sql_result.get("error")
        # Same assembly as query_agent.adk_agent._run_query_async.
        labels_lang = adk_agent._labels_language("en", language)
        data = {"columns": sql_result["columns"], "rows": sql_result["rows"],
                "row_count": sql_result["row_count"], "truncated": sql_result.get("truncated", False)}
        data["display"] = {"columns": adk_agent._localize_columns(data["columns"], labels_lang),
                           "rows": adk_agent._localize_numbers(data["rows"], labels_lang)}
        return {"answer": answer, "sql": sql_result["sql"], "data": data, "speech_text": answer}

    setup()
    run.setup = setup
    yield run
    query_db.clear_cache(FID)


def _parts(messages):
    create, update, data = messages
    comps = {c["id"]: c for c in update["updateComponents"]["components"]}
    return create["createSurface"], comps, data["updateDataModel"]


def _texts(messages) -> list[str]:
    """Every text on the card, top to bottom."""
    _, comps, _ = _parts(messages)
    out: list[str] = []

    def walk(cid):
        c = comps[cid]
        if c["component"] == "Text":
            out.append(c["text"])
        for child in c.get("children", []) + ([c["child"]] if "child" in c else []):
            walk(child)

    walk("root")
    return out


def _valid_tree(messages):
    """Every referenced child exists, there is one root, only display components, no buttons."""
    _, comps, _ = _parts(messages)
    assert "root" in comps
    for c in comps.values():
        assert c["component"] in SUPPORTED, c
        for child in c.get("children", []) + ([c["child"]] if "child" in c else []):
            assert child in comps, (c["id"], child)


def _card(run, sql, language="en-IN", **kw):
    return qw.build_query_widget(run(sql, language), language, **kw)


HEALTH_SQL = ("SELECT h.log_id, a.tag_or_name, h.risk_level, h.symptoms_reported, h.first_aid_advice, "
              "h.log_timestamp, h.source FROM ai_health_logs h JOIN animals a ON a.id = h.animal_id "
              "ORDER BY h.log_timestamp DESC")


# ---- health report: several records -------------------------------------------

def test_health_report_is_a_list_of_animal_cards_with_risk_first(farm):
    messages = _card(farm, HEALTH_SQL)
    _valid_tree(messages)
    texts = _texts(messages)
    assert texts[0] == "AI health checks (3)"  # what the records are, read from the columns
    assert texts[1] == "🔴 High risk: 1 · 🟢 Low risk: 2"
    gauri = texts.index("GAURI")
    assert texts[gauri + 1] == "🔴 High risk"  # risk right under the name, without a label
    assert "Symptoms: fever, cough" in texts  # the JSON list text, read as a list
    assert "Recorded on: 30-10-2026" in texts  # 20:30 UTC on the 29th is the 30th in India


def test_health_report_never_shows_ids_or_the_internal_source(farm):
    texts = " ".join(_texts(_card(farm, HEALTH_SQL)))
    assert "c30edce1" not in texts and "ai_unverified" not in texts and "d1" not in texts.split()


def test_long_advice_is_cut_short_at_a_word(farm):
    advice = next(t for t in _texts(_card(farm, HEALTH_SQL)) if t.startswith("First aid: Keep"))
    value = advice.split(": ", 1)[1]
    assert value.endswith("…") and len(value) <= qw.MAX_TEXT + 1
    assert LONG_ADVICE.startswith(value[:-1])


def test_health_report_in_hindi_uses_the_query_agents_headings_and_farmer_words(farm):
    texts = _texts(_card(farm, HEALTH_SQL, "hi-IN"))
    assert texts[0] == "AI स्वास्थ्य जाँच (3)"
    assert "🔴 ज़्यादा जोखिम" in texts
    assert "लक्षण: fever, cough" in texts  # heading from adk_agent._COLUMN_LABELS, symptoms as stored


@pytest.mark.parametrize("lang", LANGS)
def test_every_language_gets_its_own_headings_and_words(farm, lang):
    texts = _texts(_card(farm, HEALTH_SQL, f"{lang}-IN"))
    heading = adk_agent._COLUMN_LABELS[lang]["symptoms_reported"]
    assert any(t.startswith(f"{heading}: ") for t in texts)
    assert texts[0] == f'{qw._TEXT[lang]["topics"]["health_checks"]} (3)'
    assert texts[1].startswith("🔴 ")


def test_every_language_has_the_same_words():
    keys = set(qw._TEXT["en"])
    statuses = set(qw._TEXT["en"]["statuses"])
    topics = set(qw._TEXT["en"]["topics"])
    assert topics == {t for t, _ in qw._TOPIC_COLUMNS}
    for lang in LANGS:
        assert set(qw._TEXT[lang]) == keys, lang
        assert set(qw._TEXT[lang]["statuses"]) == statuses, lang
        assert set(qw._TEXT[lang]["topics"]) == topics, lang


def test_new_health_headings_exist_in_all_languages():
    for column in ("vaccine_name", "risk_level", "symptoms_reported", "first_aid_advice", "due_date"):
        for lang in LANGS:
            assert adk_agent._COLUMN_LABELS[lang][column], (lang, column)


# ---- vaccinations: status --------------------------------------------------------

VACC_SQL = ("SELECT a.tag_or_name, v.vaccine_name, v.status, v.due_date, v.administered_date "
            "FROM vaccination_records v JOIN animals a ON a.id = v.animal_id ORDER BY a.tag_or_name")


def test_vaccinations_show_status_words_and_a_status_summary(farm):
    texts = _texts(_card(farm, VACC_SQL))
    assert texts[1] == "⏳ Pending: 2 · ✅ Given: 1"
    assert "Status: ⏳ Pending" in texts and "Status: ✅ Given" in texts
    assert "Due date: 05-11-2026" in texts
    assert "BHURI" in texts  # title is the animal, vaccine is a field
    assert "Vaccine: Enterotoxaemia" in texts


def test_vaccination_status_in_marathi(farm):
    texts = _texts(_card(farm, VACC_SQL, "mr-IN"))
    assert "⏳ बाकी: 2 · ✅ दिली: 1" == texts[1]


def test_an_empty_cell_is_left_out_not_shown_as_blank(farm):
    texts = _texts(_card(farm, VACC_SQL))
    assert not any(t.endswith(": ") or t.endswith(":") for t in texts)
    # MOTI's vaccine was given: no due date line on its card.
    moti = texts.index("MOTI")
    assert not any(t.startswith("Due date") for t in texts[moti:moti + 4])


# ---- breakdown ---------------------------------------------------------------

def test_breakdown_shows_each_group_with_count_share_and_total(farm):
    messages = _card(farm, "SELECT species, COUNT(*) AS count FROM animals GROUP BY species ORDER BY species")
    _valid_tree(messages)
    texts = _texts(messages)
    assert texts == ["Species", "Goat", "2 · 67%", "Sheep", "1 · 33%", "Total", "3"]
    _, comps, _ = _parts(messages)
    assert comps["g0_l"]["weight"] == 3 and comps["g0_v"]["weight"] == 2  # label and number share the row


def test_breakdown_in_hindi_shows_farmer_words_for_species(farm):
    result = farm("SELECT species, COUNT(*) FROM animals GROUP BY species ORDER BY species", "hi-IN")
    texts = _texts(qw.query_widget_for(FID, "s1", result, "hi-IN"))
    assert texts[:3] == ["प्रजाति", "बकरी", "2 · 67%"]
    assert "कुल" in texts


def test_breakdown_of_averages_has_no_total_or_share(farm):
    texts = _texts(_card(farm, "SELECT species, AVG(age_years) AS avg_age FROM animals "
                               "WHERE age_years IS NOT NULL GROUP BY species"))
    assert texts == ["Species · Avg age", "Goat", "1.8", "Sheep", "3"]


def test_breakdown_of_plain_numbers_is_not_added_up(farm):
    # Whole-number ages per animal: two columns, but not counts -- no share, no total.
    texts = _texts(_card(farm, "SELECT tag_or_name, CAST(age_years AS INTEGER) AS age FROM animals "
                               "WHERE age_years IS NOT NULL ORDER BY tag_or_name"))
    assert texts == ["Tag / Name · Age", "BHURI", "3", "GAURI", "2", "MOTI", "1"]


def test_breakdown_with_a_count_alias_adds_up(farm):
    texts = _texts(_card(farm, "SELECT sex, COUNT(*) AS animal_count FROM animals GROUP BY sex ORDER BY sex"))
    assert texts == ["Sex", "Female", "2 · 67%", "Male", "1 · 33%", "Total", "3"]


def test_a_single_group_is_a_details_card_not_a_breakdown(farm):
    texts = _texts(_card(farm, "SELECT species, COUNT(*) AS total FROM animals WHERE species='sheep' GROUP BY species"))
    assert texts == ["Sheep", "Total: 1"]


# ---- one record ----------------------------------------------------------------

def test_one_animal_is_a_details_card(farm):
    messages = _card(farm, "SELECT * FROM animals WHERE tag_or_name = 'gauri'")
    _valid_tree(messages)
    texts = _texts(messages)
    assert texts[0] == "GAURI"
    assert "Species: Goat" in texts and "Breed: Sirohi" in texts and "Age (years): 2.5" in texts
    assert "Date of birth: 10-04-2024" in texts and "Status: Active" in texts
    assert not any("a-1" in t or FID in t for t in texts)  # id and farmer_id never shown
    assert not any(t.startswith("Sire") or t.startswith("Dam") for t in texts)  # empty fields left out


def test_farmer_record_never_shows_login_or_password(farm):
    texts = " ".join(_texts(_card(farm, "SELECT * FROM farmers")))
    assert "pbkdf2" not in texts and "ramesh01" not in texts
    assert "Ramesh" in texts


def test_json_object_columns_are_not_shown(farm):
    texts = " ".join(_texts(_card(farm, "SELECT issue, params, recorded_at FROM health_logs")))
    assert "temperature_c" not in texts and "{" not in texts
    assert "Reduced feed intake" in texts


# ---- no card -------------------------------------------------------------------

def test_a_single_value_gets_no_card(farm):
    assert _card(farm, "SELECT COUNT(*) FROM animals") is None


def test_no_rows_gets_no_card(farm):
    assert _card(farm, "SELECT * FROM animals WHERE species = 'cow'") is None


@pytest.mark.parametrize("result", [
    None, "text", {}, {"answer": "x", "data": None},
    {"data": {"columns": [], "rows": []}},
    {"data": {"columns": ["a", "b"], "rows": [[1]]}},  # row does not match the columns
    {"data": {"columns": [1, 2], "rows": [[1, 2], [3, 4]]}},
    {"data": {"columns": ["id", "farmer_id"], "rows": [["a", "b"], ["c", "d"]]}},  # only hidden columns
])
def test_unusable_results_get_no_card(result):
    assert qw.build_query_widget(result, "en-IN") is None


# ---- many records --------------------------------------------------------------

def test_many_records_show_the_first_cards_and_say_how_many(farm):
    farm.setup(extra_animals=20)
    messages = _card(farm, "SELECT tag_or_name, species, sex FROM animals")
    _, comps, _ = _parts(messages)
    assert sum(1 for c in comps if c.startswith("i") and c[1:].isdigit()) == qw.MAX_ITEMS
    texts = _texts(messages)
    assert texts[0] == "Animals (23)" and texts[-1] == f"Showing {qw.MAX_ITEMS} of 23"


def test_a_truncated_result_says_there_are_more(farm):
    result = farm("SELECT tag_or_name, species FROM animals")
    result["data"]["truncated"] = True
    texts = _texts(qw.build_query_widget(result, "en-IN"))
    assert texts[0] == "Animals (3+)" and texts[-1] == "Showing 3 of 3+"


def test_a_card_has_at_most_max_fields_lines(farm):
    texts = _texts(_card(farm, "SELECT * FROM animals WHERE species = 'goat'"))
    gauri, moti = texts.index("GAURI"), texts.index("MOTI")
    assert moti - gauri - 1 <= qw.MAX_FIELDS + 1  # + the one line of species, breed and sex


def test_animal_cards_say_what_kind_of_animal_in_one_line(farm):
    texts = _texts(_card(farm, "SELECT tag_or_name, species, breed, sex, age_years, status FROM animals ORDER BY tag_or_name"))
    gauri = texts.index("GAURI")
    assert texts[gauri + 1:gauri + 4] == ["Goat · Sirohi · Female", "Age (years): 2.5", "Status: Active"]
    _, comps, _ = _parts(_card(farm, "SELECT tag_or_name, species, breed, sex FROM animals"))
    assert comps["i0_kind"]["variant"] == "body"


def test_animal_kind_line_in_hindi_uses_farmer_words(farm):
    result = farm("SELECT tag_or_name, species, breed, sex FROM animals ORDER BY tag_or_name", "hi-IN")
    texts = _texts(qw.query_widget_for(FID, "s1", result, "hi-IN"))
    assert texts[texts.index("GAURI") + 1] == "बकरी · Sirohi · मादा"  # breed names stay as they are


def test_two_columns_with_the_same_name_from_a_join(farm):
    messages = _card(farm, "SELECT a.tag_or_name, a.status, v.status FROM animals a "
                           "JOIN vaccination_records v ON v.animal_id = a.id")
    _valid_tree(messages)
    assert "Status: ⏳ Pending" in _texts(messages)


# ---- the switch, the dispatcher, the log, never raising -------------------------

def test_switched_off_sends_no_card(farm, monkeypatch):
    monkeypatch.setenv("CHAT_A2UI_WIDGETS", "false")
    assert qw.query_widget_for(FID, "s1", farm(HEALTH_SQL), "en-IN") is None


def test_dispatcher_sends_the_card_for_query_answers(farm):
    messages = widgets.widget_for("query_agent", FID, "s1", farm(HEALTH_SQL), "hi-IN")
    create, _, data = _parts(messages)
    assert create["surfaceId"] == "query-s1" and data["path"] == "/query"
    assert messages[0]["version"] == "v0.9"
    assert "AI स्वास्थ्य जाँच (3)" in _texts(messages)


def test_card_messages_are_plain_json(farm):
    messages = qw.query_widget_for(FID, "s1", farm(HEALTH_SQL), "en-IN")
    assert json.loads(json.dumps(messages, ensure_ascii=False)) == messages
    assert all(set(m) <= {"version", "createSurface", "updateComponents", "updateDataModel"} for m in messages)


def test_a_problem_building_the_card_drops_only_the_card(farm, monkeypatch, caplog):
    def broken(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(qw, "_build", broken)
    assert qw.query_widget_for(FID, "s1", farm(HEALTH_SQL), "en-IN") is None
    assert "a2ui query widget skipped" in caplog.text


def test_sent_card_is_logged_with_its_shape(farm, caplog):
    qw.query_widget_for(FID, "s1", farm(HEALTH_SQL), "en-IN")
    assert "a2ui query widget sent" in caplog.text and "shape=list" in caplog.text and "rows=3" in caplog.text


def test_two_turns_at_once_get_the_same_card(farm):
    result = farm(HEALTH_SQL)
    out = []
    threads = [threading.Thread(target=lambda: out.append(qw.query_widget_for(FID, "s1", result, "en-IN")))
               for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(out) == 6 and all(o == out[0] for o in out)


def test_chat_envelope_carries_the_card():
    pytest.importorskip("google.adk")
    from services.chat_orchestrator import adk_router

    result = {"answer": "You have 2 animals.", "sql": "SELECT", "speech_text": "2 animals.",
              "data": {"columns": ["tag_or_name", "species"], "rows": [["GAURI", "goat"], ["MOTI", "goat"]],
                       "row_count": 2, "truncated": False,
                       "display": {"columns": ["Tag / Name", "Species"], "rows": [["GAURI", "goat"], ["MOTI", "goat"]]}}}
    env = adk_router._envelope("query_agent", "query", result, "You have 2 animals.", FID, "s1", "my animals",
                               include_audio=False, language="en-IN")
    assert env["reply_text"] == "You have 2 animals."
    assert env["a2ui"][0]["createSurface"]["surfaceId"] == "query-s1"


# ---- titles, topics, overdue ----------------------------------------------------

def test_the_animal_is_the_title_even_under_an_alias(farm):
    texts = _texts(_card(farm, "SELECT a.tag_or_name AS animal_name, v.vaccine_name, v.due_date "
                               "FROM vaccination_records v JOIN animals a ON a.id = v.animal_id "
                               "WHERE v.status = 'pending' ORDER BY v.due_date", today=date(2026, 10, 31)))
    assert texts[0] == "Vaccinations (2)"
    assert texts[1:4] == ["GAURI", "Vaccine: PPR", "Due date: 05-11-2026"]


def test_a_passed_due_date_is_marked_overdue_unless_done(farm):
    texts = _texts(_card(farm, VACC_SQL, today=date(2026, 11, 6)))
    assert "Due date: 05-11-2026 ⚠️ Overdue" in texts  # GAURI's PPR, still pending
    assert "Due date: 09-11-2026" in texts  # BHURI's, not due yet
    done = {"data": {"columns": ["tag_or_name", "status", "due_date"],
                     "rows": [["A", "administered", "2026-10-01"], ["B", "pending", "2026-10-01"]],
                     "row_count": 2, "truncated": False}}
    texts = _texts(qw.build_query_widget(done, "en-IN", today=date(2026, 11, 6)))
    assert "Due date: 01-10-2026" in texts and "Due date: 01-10-2026 ⚠️ Overdue" in texts


def test_overdue_in_hindi(farm):
    result = farm(VACC_SQL, "hi-IN")
    texts = _texts(qw.build_query_widget(result, "hi-IN", today=date(2026, 11, 6)))
    assert any(t.endswith("⚠️ समय निकल गया") for t in texts)


def test_one_record_without_an_animal_is_titled_by_what_it_is(farm):
    texts = _texts(_card(farm, "SELECT symptoms_reported, risk_level, first_aid_advice FROM ai_health_logs "
                               "WHERE risk_level = 'High'"))
    assert texts[0] == "AI health checks"  # not the symptoms
    assert texts[1] == "🔴 High risk"  # risk first, on its own
    assert "Symptoms: fever, cough" in texts


# ---- several lookups for one answer --------------------------------------------

def _health_report(farm, language="en-IN"):
    """What the query agent returns for a health report that took several lookups."""
    checks = farm(HEALTH_SQL, language)
    problems = farm("SELECT a.tag_or_name, h.issue, h.recorded_at FROM health_logs h "
                    "JOIN animals a ON a.id = h.animal_id", language)
    count = farm("SELECT COUNT(*) AS c FROM vaccination_records WHERE status = 'pending'", language)
    vaccines = farm(VACC_SQL + "", language)
    result = dict(vaccines)
    result["data_sets"] = [checks["data"], problems["data"], count["data"], vaccines["data"]]
    return result


def test_a_health_report_shows_each_lookup_as_its_own_section(farm):
    messages = qw.build_query_widget(_health_report(farm), "en-IN", today=date(2026, 10, 31))
    _valid_tree(messages)
    texts = _texts(messages)
    # The single count adds nothing and is left out; the one health problem is a details section.
    assert texts[0] == "AI health checks (3)"
    assert "Health problems · GAURI" in texts
    assert "Vaccinations (3)" in texts
    assert texts.index("AI health checks (3)") < texts.index("Health problems · GAURI") < texts.index("Vaccinations (3)")
    _, comps, _ = _parts(messages)
    assert sum(1 for c in comps.values() if c["id"].startswith("sep")) == 2  # a line between sections


def test_at_most_max_sections_the_last_ones(farm):
    result = _health_report(farm)
    animals = farm("SELECT tag_or_name, species FROM animals")["data"]
    result["data_sets"] = [animals] + result["data_sets"]
    texts = _texts(qw.build_query_widget(result, "en-IN", today=date(2026, 10, 31)))
    assert qw.MAX_SECTIONS == 3 and "Animals (3)" not in texts  # the oldest useful lookup is left out
    assert texts[0] == "AI health checks (3)" and "Vaccinations (3)" in texts


def test_one_lookup_in_data_sets_is_shown_from_data(farm):
    result = farm(HEALTH_SQL)
    result["data_sets"] = [result["data"]]
    assert qw.build_query_widget(result, "en-IN") == qw.build_query_widget(farm(HEALTH_SQL), "en-IN")


def test_query_agent_keeps_each_distinct_lookup_once(farm):
    a = query_db.execute_query(HEALTH_SQL, FID)
    b = query_db.execute_query(VACC_SQL, FID)
    c = query_db.execute_query("SELECT tag_or_name FROM animals", FID)
    d = query_db.execute_query("SELECT species FROM animals", FID)
    assert adk_agent._distinct_lookups([a, a, b]) == [a, b]  # a retried identical query counts once
    assert adk_agent._distinct_lookups([a, b, c, d]) == [a, b, c, d]
    assert adk_agent._distinct_lookups([a, b, c, d, a, b, c, d]) == [a, b, c, d]
    many = [query_db.execute_query(f"SELECT tag_or_name, {n} AS n FROM animals", FID) for n in range(1, 8)]
    assert adk_agent._distinct_lookups(many) == many[-adk_agent._MAX_DATA_SETS:]  # the last few
    payload = adk_agent._data_payload(a, "hi")
    assert payload["columns"] == a["columns"] and payload["display"]["columns"][1] == "टैग/नाम"


def test_query_agent_turn_returns_every_lookup_as_data_sets(farm, monkeypatch):
    """The real _run_query_async loop, with the model replaced by a fake run
    that makes two lookups (as for a health report) and then answers."""
    import asyncio
    from types import SimpleNamespace

    checks = query_db.execute_query(HEALTH_SQL, FID)
    vaccines = query_db.execute_query(VACC_SQL, FID)
    failed = {"success": False, "error": "no such column"}

    def event(responses=(), final=None):
        return SimpleNamespace(
            get_function_responses=lambda: [SimpleNamespace(name="run_sql_query", response=r) for r in responses],
            is_final_response=lambda: final is not None,
            content=SimpleNamespace(parts=[SimpleNamespace(text=final)]) if final else None,
        )

    class FakeRunner:
        def __init__(self, **kwargs):
            pass

        async def run_async(self, **kwargs):
            for e in (event([failed]), event([checks]), event([checks]), event([vaccines]),
                      event(final="Here is the health report.\n---SPOKEN---\nTwo animals need care.")):
                yield e

    class FakeSessions:
        async def create_session(self, **kwargs):
            return SimpleNamespace(id="s", events=[])

    monkeypatch.setattr(adk_agent, "Runner", FakeRunner)
    monkeypatch.setattr(adk_agent, "build_query_agent", lambda farmer_id: None)
    monkeypatch.setattr(adk_agent, "_session_service", lambda: FakeSessions())
    out = asyncio.run(adk_agent._run_query_async("health report", FID, app_language="en-IN"))
    assert out["answer"] == "Here is the health report." and out["speech_text"] == "Two animals need care."
    assert out["data"]["columns"] == vaccines["columns"]  # unchanged: the last lookup, for the table
    assert [d["columns"] for d in out["data_sets"]] == [checks["columns"], vaccines["columns"]]
    texts = _texts(qw.build_query_widget(out, "en-IN", today=date(2026, 10, 31)))
    assert texts[0] == "AI health checks (3)" and "Vaccinations (3)" in texts


def test_one_lookup_turn_has_no_data_sets(farm, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    animals = query_db.execute_query("SELECT tag_or_name, species FROM animals", FID)

    class FakeRunner:
        def __init__(self, **kwargs):
            pass

        async def run_async(self, **kwargs):
            yield SimpleNamespace(get_function_responses=lambda: [SimpleNamespace(name="run_sql_query", response=animals)],
                                  is_final_response=lambda: False, content=None)
            yield SimpleNamespace(get_function_responses=lambda: [], is_final_response=lambda: True,
                                  content=SimpleNamespace(parts=[SimpleNamespace(text="Three animals.")]))

    class FakeSessions:
        async def create_session(self, **kwargs):
            return SimpleNamespace(id="s", events=[])

    monkeypatch.setattr(adk_agent, "Runner", FakeRunner)
    monkeypatch.setattr(adk_agent, "build_query_agent", lambda farmer_id: None)
    monkeypatch.setattr(adk_agent, "_session_service", lambda: FakeSessions())
    out = asyncio.run(adk_agent._run_query_async("my animals", FID, app_language="en-IN"))
    assert "data_sets" not in out and out["data"]["row_count"] == 3


# ---- counts per table, aliases ----------------------------------------------------

COUNTS_SQL = ("SELECT 'health_logs' AS source, COUNT(*) AS count FROM health_logs "
              "UNION ALL SELECT 'ai_health_logs', COUNT(*) FROM ai_health_logs "
              "UNION ALL SELECT 'vaccination_records', COUNT(*) FROM vaccination_records")


def test_counts_per_table_are_a_breakdown_with_farmer_words(farm):
    # Real shape from the 31 Oct live run: the model named its own column "source".
    texts = _texts(_card(farm, COUNTS_SQL))
    assert texts == ["Source", "Health problems", "1 · 14%", "AI health checks", "3 · 43%",
                     "Vaccinations", "3 · 43%", "Total", "7"]


def test_counts_per_table_in_hindi(farm):
    texts = _texts(_card(farm, COUNTS_SQL, "hi-IN"))
    assert texts[1] == "स्वास्थ्य समस्याएँ" and texts[3] == "AI स्वास्थ्य जाँच" and texts[5] == "टीके"


def test_only_numbers_get_no_card(farm):
    # Nothing says what the numbers are: no card rather than "0, 0, 0".
    result = {"data": {"columns": ["count", "total"], "rows": [[0, 0], [0, 0], [0, 0]],
                       "row_count": 3, "truncated": False}}
    assert qw.build_query_widget(result, "en-IN") is None


def test_the_internal_source_marker_is_still_hidden(farm):
    texts = " ".join(_texts(_card(farm, "SELECT a.tag_or_name, h.source, h.risk_level FROM ai_health_logs h "
                                        "JOIN animals a ON a.id = h.animal_id")))
    assert "ai_unverified" not in texts and "Source" not in texts


def test_kind_line_has_one_order_whatever_the_query_order(farm):
    # Real shape from the 31 Oct live run: the model selected sex before breed.
    texts = _texts(_card(farm, "SELECT tag_or_name, sex, breed, species FROM animals ORDER BY tag_or_name"))
    assert texts[texts.index("GAURI") + 1] == "Goat · Sirohi · Female"
