FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src /app/src
COPY scripts /app/scripts
COPY configs /app/configs
RUN pip install --no-cache-dir -e . && \
    python -m nltk.downloader punkt punkt_tab && \
    python scripts/verify_nltk.py

ENV PYTHONPATH=/app
CMD ["python", "-m", "http.server", "8001"]
# TODO: update once src/main.py is created with FastAPI app
# CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]