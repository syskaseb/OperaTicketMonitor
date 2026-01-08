# Dockerfile for AWS Lambda deployment with Playwright support
FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for Playwright/Chromium
RUN dnf install -y \
    alsa-lib \
    at-spi2-atk \
    atk \
    cups-libs \
    gtk3 \
    libXcomposite \
    libXdamage \
    libXrandr \
    libXScrnSaver \
    libdrm \
    mesa-libgbm \
    libxkbcommon \
    nss \
    pango \
    xorg-x11-fonts-100dpi \
    xorg-x11-fonts-75dpi \
    xorg-x11-fonts-Type1 \
    xorg-x11-fonts-misc \
    && dnf clean all

# Copy requirements and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Set Playwright browsers path to a fixed location that persists in Lambda
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Install Playwright Chromium to the fixed path
RUN mkdir -p /opt/playwright-browsers && \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers playwright install chromium && \
    playwright install-deps chromium 2>/dev/null || true && \
    ls -la /opt/playwright-browsers/ && \
    find /opt/playwright-browsers -name "chrome*" -type f

# Copy application code
COPY config.py ${LAMBDA_TASK_ROOT}/
COPY models.py ${LAMBDA_TASK_ROOT}/
COPY scrapers.py ${LAMBDA_TASK_ROOT}/
COPY notifier.py ${LAMBDA_TASK_ROOT}/
COPY monitor.py ${LAMBDA_TASK_ROOT}/
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/
COPY seat_checker.py ${LAMBDA_TASK_ROOT}/

# Set the handler
CMD ["lambda_handler.lambda_handler"]
