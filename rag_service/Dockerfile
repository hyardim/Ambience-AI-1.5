FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure this says COPY src
COPY src /app/src

ENV PYTHONPATH=/app
# Ensure this points to src/main.py
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
