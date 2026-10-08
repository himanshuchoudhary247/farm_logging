"""Every supported language needs an onboarding prompt instruction, or
the next onboarding question silently falls back to English (seen: Tamil
was missing from both lists)."""
import pytest

from services.common.draft_supervisor import SUPPORTED_LANGUAGES
from services.farmer_onboarding_service import extraction
from services.llm_service import bedrock_adapter

LANGS = sorted({tag.split("-")[0] for tag in SUPPORTED_LANGUAGES})


@pytest.mark.parametrize("module", [extraction, bedrock_adapter])
@pytest.mark.parametrize("lang", LANGS)
def test_every_supported_language_has_an_onboarding_prompt(module, lang):
    assert lang in module._LANG_INSTRUCTIONS, f"{module.__name__} has no onboarding prompt for {lang}"


@pytest.mark.parametrize("module", [extraction, bedrock_adapter])
def test_tamil_onboarding_prompt(module):
    instruction = module._LANG_INSTRUCTIONS["ta"]
    assert "Tamil" in instruction and "தமிழ்" in instruction


@pytest.mark.parametrize("module", [extraction, bedrock_adapter])
@pytest.mark.parametrize("lang", LANGS)
def test_full_locale_tag_resolves_same_as_bare_code(module, lang):
    """Callers elsewhere in the codebase (SUPPORTED_LANGUAGES, the
    frontend selector) use the full "ta-IN" format, not the bare "ta"
    key this dict is keyed by. _lang_instruction must normalize that,
    or a full-tag caller silently falls back to English (found in
    deep-review of PR #40)."""
    bare = module._lang_instruction(lang)
    full_tag = module._lang_instruction(f"{lang}-IN")
    assert full_tag == bare
    assert full_tag != "Ask the next question in English." or lang == "en"


@pytest.mark.parametrize("module", [extraction, bedrock_adapter])
def test_mix_codes_still_match_exactly(module):
    """"mix-hi" etc must keep resolving via the exact-match branch, not
    get mangled by the bare-prefix fallback meant for locale tags."""
    assert module._lang_instruction("mix-hi") == module._LANG_INSTRUCTIONS["mix-hi"]


@pytest.mark.parametrize("module", [extraction, bedrock_adapter])
def test_unknown_language_falls_back_to_english(module):
    assert module._lang_instruction("xx-XX") == "Ask the next question in English."
    assert module._lang_instruction(None) == module._LANG_INSTRUCTIONS["en"]


    