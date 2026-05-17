FROM python:3.12-slim

ENV PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Install Chromium and OS libraries into the image for Linux production.
RUN uv run playwright install --with-deps chromium

CMD ["uv", "run", "python", "-m", "src.main"]
