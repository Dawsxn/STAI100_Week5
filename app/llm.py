"""LLM provider abstraction: Gemini (real) or mock (offline, no key).

Public surface:
  - stream_generate(system, user, usage) -> Iterator[str]   (fills `usage` dict at the end)
  - summarize(text) -> str
  - Embeddings().embed_documents(list[str]) / embed_query(str)
"""
from __future__ import annotations

import hashlib
import math
from typing import Iterator

from app import config

EMBED_DIM = 256  # dimension used by the mock embedder


# ── Mock provider (no API key needed) ──────────────────────────────────────────
def _mock_stream(system: str, user: str, usage: dict) -> Iterator[str]:
    reply = (
        "[MOCK MODE] No Gemini API key is set, so this is a canned reply. "
        "Set GEMINI_API_KEY and LLM_PROVIDER=gemini for real answers. "
        "With a key, the assistant would answer using the retrieved handbook context above."
    )
    for word in reply.split(" "):
        yield word + " "
    usage["prompt_tokens"] = max(1, len(system + user) // 4)
    usage["completion_tokens"] = max(1, len(reply) // 4)
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]


def _mock_embed(texts: list[str]) -> list[list[float]]:
    out = []
    for t in texts:
        vec = [0.0] * EMBED_DIM
        for token in t.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % EMBED_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


# ── Gemini provider (google-genai SDK) ──────────────────────────────────────────
_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _gemini_stream(system: str, user: str, usage: dict) -> Iterator[str]:
    from google.genai import types

    client = _get_client()
    cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.0)
    last_usage = None
    for chunk in client.models.generate_content_stream(
        model=config.GEN_MODEL, contents=user, config=cfg
    ):
        text = getattr(chunk, "text", None)
        if text:
            yield text
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            last_usage = um
    if last_usage is not None:
        usage["prompt_tokens"] = getattr(last_usage, "prompt_token_count", 0) or 0
        usage["completion_tokens"] = getattr(last_usage, "candidates_token_count", 0) or 0
        usage["total_tokens"] = getattr(last_usage, "total_token_count", 0) or (
            usage["prompt_tokens"] + usage["completion_tokens"]
        )


def _gemini_embed(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    result = client.models.embed_content(model=config.EMBED_MODEL, contents=texts)
    return [list(e.values) for e in result.embeddings]


# ── Public API ───────────────────────────────────────────────────────────────────
def stream_generate(system: str, user: str, usage: dict) -> Iterator[str]:
    if config.LLM_PROVIDER == "gemini":
        yield from _gemini_stream(system, user, usage)
    else:
        yield from _mock_stream(system, user, usage)


def summarize(text: str) -> str:
    system = "Summarise this conversation concisely for use as future context. 1-2 sentences."
    usage: dict = {}
    return "".join(stream_generate(system, text, usage)).strip()


class Embeddings:
    """Provider-aware batch + query embedding."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if config.LLM_PROVIDER == "gemini":
            return _gemini_embed(texts)
        return _mock_embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
