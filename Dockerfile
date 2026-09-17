# ─── Builder Stage ──────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml ./
COPY src/ ./src/

# Build production wheel package
RUN uv build --wheel --out-dir /dist

# ─── Production Runner Stage ─────────────────────────────────────────
FROM python:3.13-slim AS runner

LABEL maintainer="IT Context Platform"
LABEL service="mcp-gateway"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl wget ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

# Install production package from wheel into system site-packages
COPY --from=builder /dist /dist
RUN uv pip install --system --no-cache /dist/*.whl \
    && rm -rf /dist

EXPOSE 8001

CMD ["uvicorn", "mcp_gateway.main:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
