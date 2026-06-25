"""Central configuration: provider, models, pricing, RAG/memory knobs, paths."""
import os

from dotenv import load_dotenv

load_dotenv()  # local dev reads .env; on Render env vars come from the dashboard

# ── Provider ──────────────────────────────────────────────────────────────────
# "gemini" = real Google Gemini API (needs GEMINI_API_KEY)
# "mock"   = offline echo provider + deterministic fake embeddings (no key)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEN_MODEL = os.getenv("GEN_MODEL", "gemini-2.5-flash").strip()
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001").strip()

# No key? Fall back to mock so the app still boots (useful for plumbing tests / CI).
if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    LLM_PROVIDER = "mock"

# ── Cost ────────────────────────────────────────────────────────────────────────
# Gemini's free tier costs $0, so estimated_cost_usd logs 0.0 while FREE_TIER is on.
# The price table + formula below are real, so flipping FREE_TIER=false (or moving to a
# paid tier) computes genuine dollars — the cost code is not throwaway.
FREE_TIER = os.getenv("FREE_TIER", "true").strip().lower() in ("1", "true", "yes", "on")

# Published Google Gemini API list prices — USD per 1,000,000 tokens (reference only).
# Source: https://ai.google.dev/gemini-api/docs/pricing  (rates change; verify before billing)
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD for one request. Returns 0.0 on the free tier (the actual spend)."""
    if FREE_TIER:
        return 0.0
    price = PRICING.get(model)
    if not price:
        return 0.0
    cost = (prompt_tokens / 1_000_000) * price["input"] + (completion_tokens / 1_000_000) * price["output"]
    return round(cost, 6)


# ── RAG knobs (match Week 3/4) ────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "3"))
FETCH_K = int(os.getenv("FETCH_K", "10"))
MMR_LAMBDA = float(os.getenv("MMR_LAMBDA", "0.5"))

# ── Memory knobs (match Week 4) ───────────────────────────────────────────────
MAX_BUFFER_TURNS = int(os.getenv("MAX_BUFFER_TURNS", "4"))

# ── Paths ──────────────────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)
SEED_PDF = os.path.join(APP_DIR, "seed", "school_handbook.pdf")
LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))
MLRUNS_DIR = os.environ.get("MLRUNS_DIR", os.path.join(BASE_DIR, "mlruns"))

os.makedirs(LOG_DIR, exist_ok=True)
