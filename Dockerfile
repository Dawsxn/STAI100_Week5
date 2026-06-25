# syntax=docker/dockerfile:1
# ── Stage 1: build dependencies into an isolated venv ──────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Trim caches to shave the image (no behavioural change).
RUN find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + ; \
    find /opt/venv -name "*.pyc" -delete

# ── Stage 2: slim runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Caddy reverse-proxy binary, copied from the official image (~40MB, no extra apt deps).
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

EXPOSE 8080
CMD ["./start.sh"]
