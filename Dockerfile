# ==============================================================================
# UNIVERSAL TELEGRAM VIDEO DOWNLOADER (LinkGrabber Bot) - DOCKERFILE
# ==============================================================================
FROM python:3.12-slim-bookworm AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies including FFmpeg and ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Install Python requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app /app/app

# Create data, downloads, and logs directories and assign ownership to appuser
RUN mkdir -p /app/data /app/downloads /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Simple operational healthcheck
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import sys, shutil; sys.exit(0 if shutil.which('ffmpeg') else 1)"

# Start bot
CMD ["python", "-m", "app.main"]
