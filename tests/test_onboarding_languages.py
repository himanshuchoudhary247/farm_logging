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


    