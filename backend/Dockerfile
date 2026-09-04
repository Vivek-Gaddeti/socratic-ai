FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for faiss, pymupdf)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# Create required directories
RUN mkdir -p uploads faiss_store static

# Expose port
EXPOSE 8000

# Start the server (respects Render's dynamic PORT variable)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

