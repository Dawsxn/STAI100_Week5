#!/bin/sh
# Launch all three processes in one container: FastAPI + Streamlit (internal) behind Caddy.
set -e

# Channel 2: FastAPI (internal :8000)
uvicorn api:app --host 127.0.0.1 --port 8000 &

# Channel 1: Streamlit (internal :8501)
streamlit run streamlit_app.py \
  --server.port 8501 \
  --server.address 127.0.0.1 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false &

# Reverse proxy on the public $PORT (Render sets $PORT; defaults to 8080 locally).
exec caddy run --config /app/Caddyfile --adapter caddyfile
