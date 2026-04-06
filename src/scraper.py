"""Core scraping orchestrator — single-URL page visits with rate limiting."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from src.config import ScraperConfig
from src.extractor import extract_from_response
from src.logging_config import get_logger
from src.models import PostURL, ScrapeResult
from src.platform_selectors import get_platform_def
from src.rate_limiter import DomainRateLimiter
from src.scrapling_pool import ScraplingPool

log = get_logger(__name__)


def _get_domain(url: str) -> str:
    """Extract domain from a URL (e.g., 'x.com' from 'https://x.com/user/123')."""
    parsed = urlparse(str(url))
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


class Scraper:
    """Orchestrates scraping with rate limiting and Scrapling extraction."""

    def __init__(
        self,
        config: ScraperConfig,
        scrapling_pool: ScraplingPool,
        rate_limiter: DomainRateLimiter,
    ) -> None:
        self._config = config
        self._scrapling_pool = scrapling_pool
        self._rate_limiter = rate_limiter
        self._semaphore = asyncio.Semaphore(config.concurrency)

    async def scrape_url(self, url: str) -> ScrapeResult:
        """Scrape a single URL on demand (used by the HTTP API).

        Creates a synthetic PostURL and delegates to _scrape_single.
        """
        post = PostURL(id="api", url=url, captured_at=datetime.now(timezone.utc))
        domain = _get_domain(url)
        return await self._scrape_single(post, domain)

    async def _scrape_single(self, post: PostURL, domain: str) -> ScrapeResult:
        """Scrape a single post URL using Scrapling + hardcoded platform selectors."""
        url_str = str(post.url)

        async with self._semaphore:
            try:
                await self._rate_limiter.acquire(domain)

                platform_def = get_platform_def(domain)

                # Build combined page_action: capture live page for js_eval + run platform action
                page_ref: dict[str, Any] = {}

                async def combined_action(page: Any) -> None:
                    page_ref["page"] = page  # capture for js_eval in extractor
                    if platform_def and platform_def.page_action:
                        await platform_def.page_action(page)

                response = await self._scrapling_pool.fetch(
                    url=url_str,
                    page_action=combined_action,
                    wait_selector=platform_def.wait_selector if platform_def else None,
                    wait_selector_state=platform_def.wait_selector_state if platform_def else "visible",
                    network_idle=platform_def.network_idle if platform_def else True,
                    use_stealthy=platform_def.use_stealthy if platform_def else True,
                )

                live_page = page_ref.get("page")
                if live_page is None and platform_def and any(
                    sd.method == "js_eval"
                    for selectors in platform_def.metrics.values()
                    for sd in selectors
                ):
                    log.warning("js_eval_page_not_captured", domain=domain, url=url_str)

                if platform_def and platform_def.metrics:
                    metrics = await extract_from_response(
                        response=response,
                        page=live_page,
                        metric_defs=platform_def.metrics,
                    )
                else:
                    log.warning("no_platform_def", domain=domain, url=url_str)
                    metrics = []

                return ScrapeResult(
                    post_id=post.id,
                    url=url_str,
                    metrics=metrics,
                    scraped_at=datetime.now(timezone.utc),
                    success=True,
                )

            except Exception as e:
                log.error("scrape_error", url=url_str, error=str(e))
                return ScrapeResult(
                    post_id=post.id,
                    url=url_str,
                    metrics=[],
                    scraped_at=datetime.now(timezone.utc),
                    success=False,
                    error=str(e),
                )
