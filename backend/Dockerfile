FROM python:3.11-slim

WORKDIR /app

RUN groupadd --system appgroup && useradd --system --gid appgroup --create-home appuser

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN PIP_CONFIG_FILE=/dev/null PIP_REQUIRE_HASHES=0 \
    pip install --isolated --no-cache-dir .

COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

RUN mkdir -p /app/uploads && chown -R appuser:appgroup /app

ENV PYTHONPATH=/app

USER appuser

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
