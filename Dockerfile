FROM python:3.13-slim

# System deps for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libwayland-client0 \
    fonts-liberation xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Install Playwright Chromium
RUN uv run playwright install chromium

# Copy source
COPY src/ src/

# Data & logs volumes
RUN mkdir -p data logs

EXPOSE 8100

CMD ["uv", "run", "python", "-m", "coininfo"]
