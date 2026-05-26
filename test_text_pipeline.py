from services.voice_agent.orchestrator import process_text_input
from services.voice_agent.session_store import clear_session


def run_case(session_id: str, text: str):
    out = process_text_input(text, session_id=session_id)
    print("\n=== INPUT ===")
    print(text)
    print("--- OUTPUT ---")
    for k, v in out.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    print("\n# Scenario 1: create animal with follow-ups")
    sid = "demo-create-animal"
    clear_session(sid)
    run_case(sid, "I want to add details about my animal")
    run_case(sid, "new")
    run_case(
        sid,
        "name is gauri, goat female, breed sirohi, 2 years, feeding details green fodder morning and evening",
    )

    print("\n# Scenario 2: existing animal update (fetch + update)")
    sid = "demo-update-existing"
    clear_session(sid)
    run_case(sid, "existing animal id a-f-001-99")
    run_case(sid, "update breed to jamunapari and feeding details concentrate 1kg daily")

    print("\n# Scenario 3: health log")
    sid = "demo-health"
    clear_session(sid)
    run_case(sid, "my goat is not eating since yesterday")

    print("\n# Scenario 4: appointment")
    sid = "demo-appointment"
    clear_session(sid)
    run_case(sid, "book a vet appointment")
    run_case(sid, "tomorrow at 5 pm")

    print("\n# Scenario 5: unrelated")
    sid = "demo-unrelated"
    clear_session(sid)
    run_case(sid, "hi how are you")
