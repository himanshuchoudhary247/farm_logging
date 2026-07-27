"""
Lambda handler for the Farmer Onboarding Service.

Endpoints (via API Gateway):
  POST /onboarding  — process a turn (text + existing_data → extracted fields + follow-up question)
  GET  /onboarding/health — health check

Expected payload for POST:
  {
    "text": "farmer's message",
    "existing": {"farmer": {...}, "farm": {...}},   // optional, for progressive filling
    "language": "en"                                   // optional, defaults to en
  }

Response:
  {
    "farmer": {...},
    "farm": {...},
    "missing_fields": [...],
    "follow_up_question": "next question or null",
    "complete": true/false
  }
"""

from __future__ import annotations

import json
import os
from typing import Any

from services.farmer_onboarding_service.models import OnboardingRequest
from services.farmer_onboarding_service.service import build_final_output, process_turn


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "") or event.get("httpMethod", "")
    path = event.get("rawPath", "") or event.get("path", "")

    # Health check
    if route == "GET /onboarding/health" or path == "/onboarding/health":
        return _ok({"status": "ok", "service": "farmer-onboarding"})

    # Process onboarding turn
    if route == "POST /onboarding" or (path == "/onboarding" and event.get("httpMethod") == "POST"):
        try:
            body = _body(event)
            req = OnboardingRequest(
                text=body.get("text", ""),
                existing=body.get("existing"),
                language=body.get("language", "en"),
            )
            resp = process_turn(req)
            return _ok(resp.model_dump(exclude_none=True))
        except Exception as e:
            return _err(400, str(e))

    return _err(404, f"No route: {route or path}")


def _body(event: dict) -> dict:
    if "body" in event and event["body"]:
        if isinstance(event["body"], str):
            return json.loads(event["body"])
        return event["body"]
    return {}


def _ok(data: Any) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": _cors(),
        "body": json.dumps(data, default=str),
    }


def _err(code: int, msg: str) -> dict[str, Any]:
    return {
        "statusCode": code,
        "headers": _cors(),
        "body": json.dumps({"error": msg}, default=str),
    }


def _cors() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
        "Access-Control-Allow-Headers": "Content-Type",
    }
