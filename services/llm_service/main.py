from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from llm.adapters import get_text_adapter

app = FastAPI(title="Farmer Chat LLM Service", version="0.1.0")


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatCompleteRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(default_factory=list)
    system: Optional[str] = None


class ChatCompleteResponse(BaseModel):
    content: str


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat/complete", response_model=ChatCompleteResponse)
def complete(req: ChatCompleteRequest) -> ChatCompleteResponse:
    adapter = get_text_adapter()
    content = adapter.complete(
        messages=[{"role": m.role, "content": m.content} for m in req.messages],
        system=req.system,
    )
    return ChatCompleteResponse(content=content)
