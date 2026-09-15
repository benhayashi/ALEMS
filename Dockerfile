FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ALEMS_HOST=0.0.0.0 \
    ALEMS_PORT=8085

WORKDIR /app

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application files
COPY . .

# Ensure data and exports directories exist
RUN mkdir -p /app/data /app/exports

EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8085/api/status || exit 1

CMD ["python", "run.py", "start", "--host", "0.0.0.0", "--port", "8085"]
