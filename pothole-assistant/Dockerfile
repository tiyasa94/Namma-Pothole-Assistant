FROM python:3.11-slim

# System dependencies for PostGIS client + image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libgdal-dev \
    portaudio19-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose FastAPI port
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
