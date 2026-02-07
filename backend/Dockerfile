# Use Python 3.11
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for Postgres & compilation)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from the root of backend/
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- THE FIX IS HERE ---
# We now copy the 'src' folder, not 'app'
COPY src /app/src

# Add /app to PYTHONPATH so python can find 'src'
ENV PYTHONPATH=/app

# Start the application pointing to 'src.main:app'
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]