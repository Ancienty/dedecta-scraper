#!/bin/bash
set -e

echo "Scraper container started (HTTP mode)"

# Start uvicorn server
exec uvicorn src.server:app --host 0.0.0.0 --port 8000
