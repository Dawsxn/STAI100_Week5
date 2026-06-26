# syntax=docker/dockerfile:1
# ── Stage 1: build dependencies into an isolated venv, then trim hard ───────────
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# binutils gives us `strip` (build stage only — not in the runtime image).
RUN apt-get update && apt-get install -y --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Trim: strip debug symbols from shared libs (numpy/pandas/pyarrow/etc. carry large
# symbol tables) and drop tests, C headers, and bytecode caches.
RUN find /opt/venv -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true ; \
    find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + ; \
    find /opt/venv -type d -name "tests" -prune -exec rm -rf {} + ; \
    find /opt/venv -type d -name "test" -prune -exec rm -rf {} + ; \
    find /opt/venv -name "*.pyc" -delete ; \
    rm -rf /opt/venv/lib/python*/site-packages/pyarrow/include ; \
    rm -rf /opt/venv/lib/python*/site-packages/pyarrow/tests

# ── Stage 2: slim runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Caddy reverse-proxy binary, copied from the official image (no extra apt deps).
COPY --from=caddy:2 /usr/bin/caddy /usr/bin/caddy

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY api.py streamlit_app.py Caddyfile start.sh ./
RUN chmod +x start.sh

# Build-time smoke test: verify the stripped libraries still import and the app wires
# up (mock mode, fully offline). Fails the build before a bad strip can reach runtime.
RUN LOG_DIR=/tmp/l MLRUNS_DIR=/tmp/m LLM_PROVIDER=mock \
    python -c "import streamlit, altair, pandas, pyarrow, numpy, fastapi, mlflow, pypdf; from google import genai; import api; print('smoke import OK')" \
    && rm -rf /tmp/l /tmp/m

EXPOSE 8080
CMD ["./start.sh"]
