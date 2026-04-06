FROM python:3.13-slim-bookworm

# Install Firefox runtime dependencies (Scrapling StealthyFetcher uses Camoufox/Firefox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libx11-xcb1 \
    libasound2 \
    libpci3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies and download Scrapling browsers
COPY pyproject.toml .
RUN pip install --no-cache-dir . \
    && python -m scrapling install

# Copy application
COPY src/ src/
COPY config/ config/
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh \
    && groupadd -r scraper \
    && useradd -r -g scraper scraper \
    && chown -R scraper:scraper /app

USER scraper

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1


ENTRYPOINT ["/app/entrypoint.sh"]
