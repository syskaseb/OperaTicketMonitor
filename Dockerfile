# Dockerfile for running Opera Ticket Monitor on AWS ECS/Fargate
# or any container platform

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py .
COPY models.py .
COPY scrapers.py .
COPY notifier.py .
COPY monitor.py .

# Create non-root user for security
RUN useradd -m -u 1000 appuser
USER appuser

# Environment variables (override in deployment)
ENV SENDER_EMAIL=""
ENV SENDER_PASSWORD=""
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "print('healthy')" || exit 1

# Run the monitor
CMD ["python", "monitor.py"]
