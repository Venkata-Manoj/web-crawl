# syntax=docker/dockerfile:1
FROM python:3.12-slim

LABEL maintainer="Venkata-Manoj"
LABEL description="Website Cloner — Clone websites to local folders with live progress tracking"
LABEL org.opencontainers.image.source="https://github.com/Venkata-Manoj/web-crawl"

WORKDIR /app

# Install system deps (ca-certificates for HTTPS)
RUN apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Skip Playwright browser download in Docker (JS rendering is optional — install browsers manually if needed)
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Copy deps first for layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY cloner.py app.py ./
COPY tests/ ./tests/

# Output dir for cloned sites
RUN mkdir -p /app/cloned_sites

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/', timeout=5)" || exit 1

# Use gunicorn for production serving
RUN pip install --no-cache-dir gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
