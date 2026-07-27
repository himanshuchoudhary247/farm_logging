from __future__ import annotations

from typing import Any, Optional

from services.farmer_onboarding_service.extraction import extract
from services.farmer_onboarding_service.models import OnboardingRequest, OnboardingResponse


def process_turn(req: OnboardingRequest, current_field: Optional[str] = None, current_section: Optional[str] = None) -> OnboardingResponse:
    result = extract(text=req.text, existing=req.existing, language=req.language, current_field=current_field, current_section=current_section)

    raw_confidence = result.get("confidence")
    confidence = None
    confirm_fields = []
    if raw_confidence is not None:
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
            confirm_fields = result.get("confirm_fields", [])
        except (ValueError, TypeError):
            pass

    if not confirm_fields:
        new_farmer = {k: v for k, v in result.get("farmer", {}).items() if v not in (None, "", 0, "0")}
        new_farm = {k: v for k, v in result.get("farm", {}).items() if v not in (None, "", 0, "0")}
        low_conf_fields = []
        if confidence is not None and confidence < 0.8:
            if new_farmer:
                low_conf_fields.extend(list(new_farmer.keys())[:2])
            if new_farm:
                low_conf_fields.extend(list(new_farm.keys())[:2])
        confirm_fields = low_conf_fields

    return OnboardingResponse(
        farmer=result.get("farmer", {}),
        farm=result.get("farm", {}),
        missing_fields=result.get("missing_fields", []),
        follow_up_question=result.get("follow_up_question"),
        complete=result.get("complete", False),
        confidence=confidence,
        confirm_fields=confirm_fields,
    )


def build_final_output(farmer: dict, farm: dict) -> dict[str, Any]:
    """Build the final JSON payload for whoever accepts it (DB layer, another service, etc.)."""
    return {
        "farmer": {k: v for k, v in farmer.items() if v not in (None, "", 0, "0")},
        "farm": {k: v for k, v in farm.items() if v not in (None, "", 0, "0")},
    }
