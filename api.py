"""FastAPI channel — POST /chat/stream streams Server-Sent Events from the shared pipeline.

Run locally:   uvicorn api:app --reload --port 8000
Test:          curl -N -X POST localhost:8000/chat/stream \
                    -H 'Content-Type: application/json' \
                    -d '{"message":"What is the dress code on Fridays?"}'
"""
from __future__ import annotations

import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import config, llm, pipeline
from app.memory import ConversationMemory
from app.rag import get_store

app = FastAPI(
    title="Week 5 — Dual-Channel Support Bot API",
    description="SSE chat endpoint over the shared RAG + memory + guardrails pipeline.",
    version="1.0.0",
)

_store = get_store()
_sessions: dict[str, ConversationMemory] = {}


def _memory_for(session_id: str) -> ConversationMemory:
    if session_id not in _sessions:
        _sessions[session_id] = ConversationMemory(summarize_fn=llm.summarize)
    return _sessions[session_id]


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time-ms"] = str(int((time.time() - t0) * 1000))
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "provider": config.LLM_PROVIDER, "kb_chunks": _store.count()}


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream the answer as SSE: each event is `data: {"token": "..."}`, ending with `[DONE]`."""
    memory = _memory_for(req.session_id)

    def event_stream():
        for token in pipeline.answer_stream(req.message, memory, _store, channel="api"):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
