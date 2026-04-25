FROM python:3.11-slim

WORKDIR /app

# Install Playwright system dependencies + utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    fonts-liberation \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early so we can chown browser cache later
RUN groupadd -r agentos && useradd -r -g agentos agentos

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browsers for Playwright (must run as root)
RUN playwright install chromium

# Ensure the non-root user can read/execute the Playwright browsers
RUN chown -R agentos:agentos /root/.cache/ms-playwright || true

COPY app ./app
COPY .env .

# Production hardening
RUN chown -R agentos:agentos /app
USER agentos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
