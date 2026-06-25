"""Conversation memory: buffer of recent turns + running summary (ported from Week 4).

Keeps the prompt bounded over long conversations: the last `max_turns` turns are kept
verbatim; once the buffer fills it is compressed into `summary` and flushed. This lets
context survive 10+ turns without the prompt growing without bound.
"""
from app import config


class ConversationMemory:
    def __init__(self, summarize_fn=None, max_turns: int | None = None):
        self.buffer: list[dict] = []          # [{"input": ..., "output": ...}]
        self.summary: str = ""
        self.max_turns = max_turns or config.MAX_BUFFER_TURNS
        # summarize_fn(text) -> str ; injected to avoid a hard import cycle with llm.py
        self._summarize_fn = summarize_fn

    def load_history(self) -> str:
        parts = []
        if self.summary:
            parts.append(f"[Summary of earlier conversation]: {self.summary}")
        for turn in self.buffer:
            parts.append(f"Student: {turn['input']}\nBot: {turn['output']}")
        return "\n".join(parts).strip()

    def add(self, user_input: str, bot_output: str) -> None:
        self.buffer.append({"input": user_input, "output": bot_output})
        if len(self.buffer) >= self.max_turns:
            self._flush()

    def _flush(self) -> None:
        history = "\n".join(f"Student: {t['input']}\nBot: {t['output']}" for t in self.buffer)
        if self._summarize_fn is not None:
            try:
                new = self._summarize_fn(history)
                self.summary = (self.summary + " " + new).strip() if self.summary else new.strip()
            except Exception:
                # Never let summarization break the chat; fall back to keeping raw text.
                self.summary = (self.summary + "\n" + history).strip()
        else:
            self.summary = (self.summary + "\n" + history).strip()
        self.buffer = []
