# Backend Dockerfile
FROM python:3.9-slim

# Install system dependencies for Tesseract and others
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy source code (kept as the `backend` package so its relative imports resolve)
COPY backend/ backend/

# Expose port
EXPOSE 8000

# Start command (overridden by compose usually, but good default)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
