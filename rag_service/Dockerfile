FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src /app/src
COPY scripts /app/scripts
COPY configs /app/configs
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN PIP_CONFIG_FILE=/dev/null PIP_REQUIRE_HASHES=0 \
    pip install --isolated --no-cache-dir -e . "python-multipart>0.0.12" && \
    python -c "import python_multipart as pm; v=tuple(int(x) for x in pm.__version__.split('.')[:3]); print('python-multipart', pm.__version__); assert v > (0, 0, 12), pm.__version__" && \
    mkdir -p "$NLTK_DATA" && \
    python scripts/verify_nltk.py

ENV PYTHONPATH=/app
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
