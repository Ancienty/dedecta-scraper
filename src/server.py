"""FastAPI HTTP server — on-demand scraping with warm browser sessions."""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from pydantic import HttpUrl

from src.config import load_settings
from src.logging_config import get_logger, setup_logging
from src.models import FetchResponse, ScrapeResult, UnifiedMetrics
from src.proxy_pool import ProxyPool
from src.rate_limiter import DomainRateLimiter
from src.scraper import Scraper
from src.scrapling_pool import ScraplingPool

log = get_logger(__name__)

# Platform domain -> canonical name
DOMAIN_TO_PLATFORM: dict[str, str] = {
    "instagram.com": "instagram",
    "youtube.com": "youtube",
    "x.com": "x",
    "twitter.com": "x",
    "facebook.com": "facebook",
    "sikayetvar.com": "sikayetvar",
}

# Per-platform mapping from raw metric names to unified field names
METRIC_NAME_MAP: dict[str, dict[str, str]] = {
    "instagram": {},  # likes/comments already match
    "youtube": {},    # likes/comments/views already match
    "x": {},          # likes/reposts/replies/views already match
    "facebook": {},   # reactions/comments/shares already match
    "sikayetvar": {
        "view_count": "views",
        "comment_count": "comments",
    },
}

# Metrics that belong in meta, not in UnifiedMetrics
META_FIELDS = {"username"}


def _resolve_platform(url: str) -> str | None:
    """Extract platform name from URL domain."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return DOMAIN_TO_PLATFORM.get(domain)


def _build_response(url: str, platform: str | None, result: ScrapeResult) -> FetchResponse:
    """Map a ScrapeResult to the unified FetchResponse schema."""
    metrics = UnifiedMetrics()
    meta: dict[str, str | int | None] = {}

    name_map = METRIC_NAME_MAP.get(platform or "", {})

    for mv in result.metrics:
        if mv.name in META_FIELDS:
            meta[mv.name] = mv.value
            continue

        unified_name = name_map.get(mv.name, mv.name)

        if hasattr(metrics, unified_name) and mv.value is not None:
            setattr(metrics, unified_name, int(mv.value) if not isinstance(mv.value, int) else mv.value)

    return FetchResponse(
        success=result.success,
        platform=platform,
        url=str(result.url),
        scraped_at=result.scraped_at,
        metrics=metrics,
        meta=meta,
        error=result.error,
    )


# --- App state (populated during lifespan) ---

_scraper: Scraper | None = None
_scrapling_pool: ScraplingPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start browser sessions at boot, shut down on exit."""
    global _scraper, _scrapling_pool

    settings = load_settings()
    setup_logging(level=settings.logging.level, json_output=settings.logging.json_output)

    proxy_pool = ProxyPool(settings.proxies)
    rate_limiter = DomainRateLimiter(settings.rate_limiting)
    _scrapling_pool = ScraplingPool(settings.scrapling, proxy_pool)

    await _scrapling_pool.start()
    log.info("server_scrapling_pool_started")

    _scraper = Scraper(
        config=settings.scraper,
        scrapling_pool=_scrapling_pool,
        rate_limiter=rate_limiter,
    )

    yield

    await _scrapling_pool.shutdown()
    log.info("server_scrapling_pool_shutdown")


app = FastAPI(title="Scraper API", lifespan=lifespan)


# --- Endpoints ---


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/fetch", response_model=FetchResponse)
async def fetch(url: HttpUrl = Query(..., description="URL to scrape")):
    assert _scraper is not None, "Server not initialized"

    url_str = str(url)
    platform = _resolve_platform(url_str)

    if platform is None:
        return FetchResponse(
            success=False,
            platform=None,
            url=url_str,
            scraped_at=datetime.now(timezone.utc),
            error=f"Unsupported platform: {urlparse(url_str).netloc}",
        )

    try:
        result = await _scraper.scrape_url(url_str)
    except Exception as e:
        log.error("fetch_endpoint_error", url=url_str, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return _build_response(url_str, platform, result)
