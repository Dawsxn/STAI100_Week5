"""Three-layer guardrail pipeline (ported from the Week 4 lab).

Layer A: deterministic keyword / off-topic filter — blocks BEFORE the LLM is called.
Layer B: regex PII redaction — applied on input AND on output.
Layer C: output validator — flags low-confidence / hallucination phrasing.
"""
import re

# ── Layer A: keyword / topic filter ───────────────────────────────────────────
BLOCKED_KW = [
    "diagnose", "do i have", "prescribe", "am i sick",
    "what illness", "what do i have", "cure", "treatment for",
]
OFF_TOPIC_KW = [
    "stock price", "crypto", "tax", "lawsuit", "invest",
    "recipe", "weather", "sports", "movie",
]


def layer_a_topic_filter(text: str) -> tuple[bool, str]:
    """Returns (allowed, reason). `reason` is '' when allowed."""
    lower = text.lower()
    for kw in BLOCKED_KW:
        if kw in lower:
            return False, f"diagnosis keyword '{kw}' detected"
    for kw in OFF_TOPIC_KW:
        if kw in lower:
            return False, f"off-topic keyword '{kw}' detected"
    return True, ""


# ── Layer B: PII redaction ─────────────────────────────────────────────────────
def redact_pii(text: str) -> str:
    """Replace personal identifiers with [REDACTED]. Domain/academic terms are kept."""
    text = re.sub(r'\b(?:\+63[-\s]?|0)9\d{2}[-\.\s]?\d{3,4}[-\.\s]?\d{4}\b', '[REDACTED]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', '[REDACTED]', text)
    text = re.sub(r'\b\d{1,3}[ \-]years?[ \-]old\b', '[REDACTED]', text, flags=re.IGNORECASE)
    text = re.sub(
        r'\b\d+\s+[A-Za-z][A-Za-z ]+?(?:St(?:reet)?|Ave(?:nue)?|Blvd|Road|Rd|Drive|Dr|Lane|Ln)\.?\b',
        '[REDACTED]', text, flags=re.IGNORECASE,
    )
    text = re.sub(r'(My name is|my name is|I am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', r'\1 [REDACTED]', text)
    text = re.sub(r'\b\d{4}-\d{7}-\d{1}\b', '[REDACTED]', text)  # PH national ID
    return text


# ── Layer C: output validator ───────────────────────────────────────────────────
HALLUCINATION_PHRASES = [
    "as far as i know", "i think", "i believe", "probably",
    "i am not sure", "it might be", "i assume",
]


def layer_c_output_validator(response: str) -> tuple[bool, str]:
    """Returns (valid, reason). `reason` is '' when valid."""
    lower = response.lower()
    for phrase in HALLUCINATION_PHRASES:
        if phrase in lower:
            return False, f"possible hallucination phrase '{phrase}'"
    return True, ""


# ── Canned safe replies when input is blocked ───────────────────────────────────
def block_message(reason: str) -> str:
    if "off-topic" in reason:
        return ("I can only help with questions about the student handbook — academics, "
                "conduct, attendance, dress code, and campus policies. "
                f"(Blocked: {reason}.)")
    return ("I can share general information from the handbook, but I can't provide medical "
            "diagnoses or treatment advice. Please consult a qualified professional. "
            f"(Blocked: {reason}.)")
