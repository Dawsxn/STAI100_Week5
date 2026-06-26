# STAI100 Week 5 — Dual-Channel Support Bot

**Live:** https://stai100-week5-bot.onrender.com

A university FAQ bot serving the same RAG + memory + guardrails pipeline through two channels: a Streamlit chat UI and a FastAPI SSE endpoint.

---

## Setup

**1. Get a free Gemini API key** at https://aistudio.google.com → "Get API key" (no card required).

**2. Configure**
```bash
cp .env.example .env
# open .env and paste your key into GEMINI_API_KEY
```

**3. Install**
```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

**4. Run**

Open two terminals:
```bash
# Terminal 1 — API
uvicorn api:app --port 8000

# Terminal 2 — UI
streamlit run streamlit_app.py
```

- UI → http://localhost:8501
- API docs → http://localhost:8000/docs

**No key?** The app boots in mock mode (fake embeddings, canned reply) so you can test everything offline. Force it with `LLM_PROVIDER=mock`.

---

## Testing the API

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the dress code on Fridays?"}'
```

Or against the deployed URL:
```bash
curl -N -X POST https://stai100-week5-bot.onrender.com/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is the dress code on Fridays?"}'
```

Response is Server-Sent Events, one token per event, ending with `[DONE]`.

Health check: `GET /healthz`

---

## Docker image size

The image is verified under 500 MB on every push via [`.github/workflows/docker-size.yml`](.github/workflows/docker-size.yml). No local Docker needed to check — the CI workflow fails with an error annotation if the budget is exceeded.

---

## LLMOps logs

Every request emits one JSON line to stdout and `logs/llmops.jsonl`:

```json
{"request_id":"…","timestamp":"…","channel":"api","model":"gemini-2.5-flash",
 "latency_ms":1840,"prompt_tokens":812,"completion_tokens":143,"total_tokens":955,
 "estimated_cost_usd":0.0,"guardrail_status":"ok","blocked":false}
```

`estimated_cost_usd` logs `0.0` on the free tier. The actual cost calculation is in `app/config.py` and can be enabled by setting `FREE_TIER=false`.
