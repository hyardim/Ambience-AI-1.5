FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Assuming requirements.txt is in /backend/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything from backend/app/ into the current WORKDIR (/app)
COPY . .

EXPOSE 8000

# Since main.py is now in /app/main.py, we use 'main:app'
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]