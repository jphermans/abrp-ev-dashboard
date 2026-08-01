# ═════════════════════════════════════════════════════════════════
# ABRP EV Dashboard — Dockerfile
# Multi-arch (ARM64 + AMD64), low-resource for Raspberry Pi
# ═════════════════════════════════════════════════════════════════

# Slim base: python-slim is ~45MB, much lighter than full python image
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install only system deps needed for openpyxl (no build tools needed)
# Keep layer small — clean up apt cache in same layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first (better Docker layer caching)
COPY docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (modular structure)
COPY server.py config.py excel_parser.py auth.py data_utils.py ./
COPY templates/ templates/
COPY routes/ routes/
COPY routes/ routes/
COPY connectors/ connectors/
COPY locales/ locales/

# Create data directory (will be mounted as volume)
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Environment defaults
ENV PORT=8000
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Use gunicorn for production (2 workers = low memory on Pi)
# --workers 2: enough for a few concurrent users
# --threads 2: handle uploads + API calls without blocking
# --timeout 120: allow slow Excel parsing
# --max-requests 100: restart workers periodically to free memory
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "120", "--max-requests", "100", "--access-logfile", "-", "server:app"]
