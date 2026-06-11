# syntax=docker/dockerfile:1

###############################################################################
# Builder stage: install dependencies into an isolated virtualenv
###############################################################################
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and force unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build tools are only needed at install time (asyncpg etc. ship wheels,
# but keep build-essential available so a source build never breaks deploy).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated virtualenv we can copy to the runtime image
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt .

# uvicorn[standard] pulls in websockets + httptools + uvloop, which this app
# needs for its /ws/* WebSocket endpoints and for production performance.
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install "uvicorn[standard]"

###############################################################################
# Runtime stage: slim image with only the venv and application code
###############################################################################
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# curl is used by the container HEALTHCHECK below
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --no-create-home appuser

WORKDIR /app

# Copy the pre-built virtualenv from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source
COPY app/ ./app/

# Drop root privileges
USER appuser

EXPOSE 8000

# Lightweight liveness probe against the app's /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# Bind to 0.0.0.0 so the service is reachable from outside the container.
# Use shell form so ${PORT} is expanded at runtime (overridable via -e PORT=...).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
