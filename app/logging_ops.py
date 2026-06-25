"""LLMOps logging: one JSON line per request (stdout + logs/llmops.jsonl) AND MLflow.

The same logger is called from the shared pipeline so BOTH channels (Streamlit + FastAPI)
emit identical records. `estimated_cost_usd` is 0.0 on the free tier (see config.FREE_TIER).
Logging never raises into the request path — failures are swallowed.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import config

# MLflow 3.x puts the local file store in "maintenance mode" and raises unless we opt in.
# mlflow-skinny ships without SQLAlchemy, so the file store is our backend here.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

_MLFLOW_OK = False
try:
    import mlflow

    # Path().as_uri() yields a proper file:///… URI (a raw Windows path makes MLflow read
    # the "C:" drive letter as a URI scheme and fail).
    mlflow.set_tracking_uri(Path(config.MLRUNS_DIR).as_uri())
    mlflow.set_experiment("week5-support-bot")
    _MLFLOW_OK = True
except Exception:  # mlflow optional — JSON-line logging still works without it
    _MLFLOW_OK = False


def log_request(*, channel: str, model: str, prompt_tokens: int, completion_tokens: int,
                latency_ms: int, guardrail_status: str, blocked: bool) -> dict:
    total = prompt_tokens + completion_tokens
    record = {
        "request_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "model": "none" if blocked else model,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
        "estimated_cost_usd": config.estimate_cost_usd(model, prompt_tokens, completion_tokens),
        "guardrail_status": guardrail_status,
        "blocked": blocked,
    }

    line = json.dumps(record)
    print(line, flush=True)  # one JSON line per request -> stdout (captured by Render logs)
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        with open(os.path.join(config.LOG_DIR, "llmops.jsonl"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    if _MLFLOW_OK:
        try:
            with mlflow.start_run(run_name=record["request_id"]):
                mlflow.log_params({
                    "channel": channel,
                    "model": record["model"],
                    "guardrail_status": guardrail_status,
                    "blocked": blocked,
                })
                mlflow.log_metrics({
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total,
                    "estimated_cost_usd": record["estimated_cost_usd"],
                })
        except Exception:
            pass

    return record
