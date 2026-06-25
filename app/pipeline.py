"""Shared pipeline used by BOTH channels (Streamlit UI and FastAPI /chat/stream).

flow: input guardrails -> MMR retrieval -> prompt(history + context) -> streamed LLM
      -> (post-stream) output PII scrub + validate -> LLMOps log -> store to memory

Streaming is real (tokens are yielded as they arrive). The output guardrail runs after the
stream completes — see README "Streaming vs. output guardrails" for why this is best-effort.
"""
from __future__ import annotations

import time
from typing import Iterator

from app import config, guardrails, llm
from app.logging_ops import log_request
from app.memory import ConversationMemory
from app.rag import VectorStore

SYSTEM_PROMPT = (
    "You are a strict university FAQ assistant for Oakridge Academy. "
    "Answer the student's question using ONLY the provided handbook context. "
    'If the context does not contain the answer, reply exactly: "Data Not Found." '
    "Cite the source and page when they appear in the context. Do not guess or use outside "
    "knowledge. Never provide medical diagnoses, prescriptions, or treatment advice."
)


def _build_user_prompt(history: str, context: str, question: str) -> str:
    return (
        f"CONVERSATION SO FAR:\n{history or '(none)'}\n\n"
        f"RETRIEVED HANDBOOK CONTEXT:\n{context or '(no relevant context found)'}\n\n"
        f"STUDENT QUESTION:\n{question}\n\nANSWER:"
    )


def answer_stream(message: str, memory: ConversationMemory, store: VectorStore,
                  channel: str) -> Iterator[str]:
    """Yields response tokens for one user message, then logs + stores the turn."""
    t0 = time.time()

    # 1. Input guardrail — Layer A (keyword/topic). Blocks before any LLM call.
    allowed, reason = guardrails.layer_a_topic_filter(message)
    if not allowed:
        for word in guardrails.block_message(reason).split(" "):
            yield word + " "
        log_request(channel=channel, model=config.GEN_MODEL, prompt_tokens=0, completion_tokens=0,
                    latency_ms=int((time.time() - t0) * 1000),
                    guardrail_status=f"blocked: {reason}", blocked=True)
        return

    # Layer B — PII redaction on input
    clean = guardrails.redact_pii(message)

    # 2. Retrieval (MMR, k=3)
    hits = store.mmr_search(clean)
    context = "\n\n".join(f"[Source: {h.source} | Page {h.page}]\n{h.text}" for h in hits)

    # 3. Prompt assembly + streamed generation
    user_prompt = _build_user_prompt(memory.load_history(), context, clean)
    usage: dict = {}
    pieces: list[str] = []
    for token in llm.stream_generate(SYSTEM_PROMPT, user_prompt, usage):
        pieces.append(token)
        yield token
    raw = "".join(pieces)

    # 4. Output guardrails (post-stream, best-effort — documented in README)
    safe = guardrails.redact_pii(raw)
    valid, vreason = guardrails.layer_c_output_validator(safe)
    status = "ok" if valid else f"output_flagged: {vreason}"

    # 5. LLMOps log + memory store (store the scrubbed text)
    log_request(channel=channel, model=config.GEN_MODEL,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                latency_ms=int((time.time() - t0) * 1000),
                guardrail_status=status, blocked=False)
    memory.add(clean, safe)
