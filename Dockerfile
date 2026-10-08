FROM ghcr.io/astral-sh/uv:0.11.21 AS uv
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system botfragg && useradd --system --gid botfragg --home-dir /app botfragg

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=botfragg:botfragg src ./src
COPY --chown=botfragg:botfragg assets ./assets
COPY --chown=botfragg:botfragg locales ./locales
RUN uv sync --frozen --no-dev \
    && mkdir -p /app/data /tmp/uv-cache \
    && chown botfragg:botfragg /app/data \
    && chown -R botfragg:botfragg /tmp/uv-cache

USER botfragg

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD ["python", "-m", "src.health"]

CMD ["uv", "run", "--frozen", "--no-dev", "botfragg"]
