# Use the official OpenVINO runtime as the base image
FROM intel/openvino_runtime:latest

# Set working directory inside the container
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# Note: We use --no-cache-dir to keep the image slim
RUN pip install --no-cache-dir -r requirements.txt

# Copy the RAG source code into the container
COPY ./src /app/src

# Expose the RAG service port
EXPOSE 8001

# Command to run the RAG API (once we create main.py)
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]