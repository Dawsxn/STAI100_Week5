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

# Trim: strip debug symbols from shared libs (numpy/pandas/pyarrow carry large symbol
# tables), drop tests/headers/stubs/caches, remove pip, pydeck (unused), and pyarrow's
# optional engines (parquet/dataset/flight/acero/substrait — never used by this app).
# Each removal below was verified locally to keep `import streamlit`/`import api` working,
# and the build-time smoke test in the runtime stage re-verifies it.
RUN SP=/opt/venv/lib/python3.12/site-packages ; \
    find /opt/venv -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true ; \
    find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + ; \
    find /opt/venv -type d -name tests -prune -exec rm -rf {} + ; \
    find /opt/venv -type d -name test -prune -exec rm -rf {} + ; \
    find /opt/venv -name "*.pyc" -delete ; \
    find /opt/venv -name "*.pyi" -delete ; \
    rm -rf $SP/pip $SP/pip-* /opt/venv/bin/pip /opt/venv/bin/pip3* ; \
    rm -rf $SP/pydeck $SP/pydeck-* ; \
    rm -rf $SP/pyarrow/include $SP/pyarrow/tests $SP/pyarrow/parquet ; \
    rm -f $SP/pyarrow/_parquet* $SP/pyarrow/_dataset* $SP/pyarrow/_acero* \
          $SP/pyarrow/_flight* $SP/pyarrow/_substrait* $SP/pyarrow/_orc* ; \
    rm -f $SP/pyarrow/libparquet.so* $SP/pyarrow/libarrow_dataset.so* \
          $SP/pyarrow/libarrow_acero.so* $SP/pyarrow/libarrow_flight*.so* \
          $SP/pyarrow/libarrow_substrait.so* $SP/pyarrow/libgandiva.so*

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

EXPOSE 8080
CMD ["./start.sh"]
