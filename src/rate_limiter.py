"""Per-domain async rate limiting."""

from __future__ import annotations

import asyncio
import time

from src.config import RateLimitingConfig


class DomainRateLimiter:
    """Enforces configurable delays between requests to the same domain."""

    def __init__(self, config: RateLimitingConfig) -> None:
        self._default_delay = config.default_delay
        self._per_domain = dict(config.per_domain)
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    def get_delay(self, domain: str) -> float:
        """Get the configured delay for a domain."""
        return self._per_domain.get(domain, self._default_delay)

    def _get_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    async def acquire(self, domain: str) -> None:
        """Wait until it's safe to make a request to this domain.

        Blocks if another request to the same domain is in-flight or
        if the delay hasn't elapsed since the last request.
        """
        lock = self._get_lock(domain)
        async with lock:
            delay = self.get_delay(domain)
            last = self._last_request.get(domain, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            self._last_request[domain] = time.monotonic()
