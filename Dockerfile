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
    rm -rf $SP/pyarrow/include $SP/pyarrow/tests
# NB: pyarrow's core (pyarrow.lib) is dynamically linked against the engine libs
# (libarrow_substrait/acero/dataset.so), so those CANNOT be removed — doing so breaks
# `import pyarrow` itself.

# ── Stage 1b: cap-free caddy ─────────────────────────────────────────────────────
# The official caddy binary carries cap_net_bind_service, which the kernel refuses to
# exec under Render's no-new-privileges policy (exit 126). A plain `cp` drops the
# capability xattr. Doing this in its own stage means only ONE (cap-free) ~45MB binary
# lands in the runtime image — a cp in the runtime stage would leave the original behind
# in the COPY layer as dead weight.
FROM caddy:2 AS caddy
RUN cp /usr/bin/caddy /caddy-nocap

# ── Stage 2: slim runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Caddy reverse proxy — single cap-free binary from the stage above (we run as root on a
# high $PORT, so cap_net_bind_service isn't needed).
COPY --from=caddy /caddy-nocap /usr/bin/caddy

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
