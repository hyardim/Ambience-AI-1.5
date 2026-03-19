FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN PIP_CONFIG_FILE=/dev/null PIP_REQUIRE_HASHES=0 \
    pip install --isolated --no-cache-dir -r requirements.txt

COPY src /app/src
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

ENV PYTHONPATH=/app

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
