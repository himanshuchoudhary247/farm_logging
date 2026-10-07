"""The confirm-before-save summary shows species/sex/"not specified"
breed in the farmer's language, while the draft keeps English values."""
import pytest

from services.animal_registration import service as registration_service


def _draft(language):
    return {
        "language": language,
        "draft": {
            "unique_animal_id": "MHTEST05",
            "species": "goat",
            "breed": registration_service._BREED_UNSPECIFIED,
            "sex": "female",
        },
    }


@pytest.mark.parametrize("language, goat, female", [
    ("mr-IN", "शेळी", "मादी"),
    ("hi-IN", "बकरी", "मादा"),
    ("ta-IN", "வெள்ளாடு", "பெண்"),
    ("te-IN", "మేక", "ఆడ"),
    ("kn-IN", "ಮೇಕೆ", "ಹೆಣ್ಣು"),
])
def test_summary_values_in_farmer_language(tmp_path, language, goat, female):
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)
    draft = _draft(language)

    summary = supervisor._summary(draft, localize_values=True)

    assert goat in summary
    assert female in summary
    assert "goat" not in summary
    assert "Not specified" not in summary
    # The stored draft is untouched.
    assert draft["draft"]["species"] == "goat"
    assert draft["draft"]["sex"] == "female"


def test_english_summary_unchanged(tmp_path):
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)
    summary = supervisor._summary(_draft("en-IN"), localize_values=True)
    assert "goat" in summary and "female" in summary
    assert registration_service._BREED_UNSPECIFIED in summary


def test_default_summary_keeps_english_for_the_llm_prompt(tmp_path):
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)
    summary = supervisor._summary(_draft("mr-IN"))
    assert "goat" in summary and "female" in summary


def test_breed_names_are_not_translated():
    assert registration_service._display_value("Osmanabadi", "mr") == "Osmanabadi"
    