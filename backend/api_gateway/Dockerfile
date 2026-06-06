# syntax=docker/dockerfile:1.6
# ============================================================
# Stage 1 — Builder: install Python dependencies
# ============================================================
FROM python:3.12-slim AS builder

# Prevents Python from writing pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build tools needed for native extensions (cryptography, asyncpg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install deps into a dedicated prefix for easy COPY
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


# ============================================================
# Stage 2 — Final: slim production image
# ============================================================
FROM python:3.12-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # Disable .pyc compilation at runtime
    PYTHONDONTWRITEBYTECODE=1

# Runtime libraries only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libssl3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Create non-root user and group
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --no-create-home --shell /sbin/nologin appuser

WORKDIR /app

# Copy application source
COPY --chown=appuser:appgroup . .

# Drop to non-root
USER appuser

# Expose application port
EXPOSE 8000

# Health check (Docker / Kubernetes liveness probe)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with 4 uvicorn workers
# Use --no-access-log — request logging handled by RequestLoggingMiddleware
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--no-access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
