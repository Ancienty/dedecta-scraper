"""Rotating proxy pool with health tracking."""

from __future__ import annotations

import asyncio
import random
import time

from src.config import ProxiesConfig, ProxyEntry
from src.logging_config import get_logger

log = get_logger(__name__)


class ProxyPool:
    """Manages a pool of proxies with rotation and health tracking."""

    def __init__(self, config: ProxiesConfig) -> None:
        self._proxies = list(config.pool)
        self._strategy = config.rotation_strategy
        self._lock = asyncio.Lock()

        # Round-robin index
        self._rr_index = 0

        # Tracking per proxy: {server: {"uses": int, "errors": int, "cooldown_until": float}}
        self._stats: dict[str, dict] = {
            p.server: {"uses": 0, "errors": 0, "cooldown_until": 0.0}
            for p in self._proxies
        }

    @property
    def size(self) -> int:
        return len(self._proxies)

    def _is_available(self, proxy: ProxyEntry) -> bool:
        stats = self._stats.get(proxy.server, {})
        return time.monotonic() >= stats.get("cooldown_until", 0.0)

    def _available_proxies(self) -> list[ProxyEntry]:
        return [p for p in self._proxies if self._is_available(p)]

    async def get_proxy(self) -> ProxyEntry | None:
        """Get the next proxy according to the rotation strategy.

        Returns None if no proxies are configured or all are in cooldown.
        """
        if not self._proxies:
            return None

        async with self._lock:
            available = self._available_proxies()
            if not available:
                log.warning("all_proxies_in_cooldown", total=len(self._proxies))
                # Fall back to all proxies
                available = list(self._proxies)

            proxy: ProxyEntry

            if self._strategy == "round_robin":
                proxy = available[self._rr_index % len(available)]
                self._rr_index += 1

            elif self._strategy == "random":
                proxy = random.choice(available)

            elif self._strategy == "least_used":
                proxy = min(available, key=lambda p: self._stats[p.server]["uses"])

            else:
                proxy = available[0]

            self._stats[proxy.server]["uses"] += 1
            return proxy

    async def report_error(self, proxy: ProxyEntry, cooldown_seconds: float = 300.0) -> None:
        """Report a proxy error. After 3 consecutive errors, put it in cooldown."""
        async with self._lock:
            stats = self._stats[proxy.server]
            stats["errors"] += 1
            if stats["errors"] >= 3:
                stats["cooldown_until"] = time.monotonic() + cooldown_seconds
                stats["errors"] = 0
                log.warning(
                    "proxy_cooldown",
                    server=proxy.server,
                    cooldown_seconds=cooldown_seconds,
                )

    async def report_success(self, proxy: ProxyEntry) -> None:
        """Report a successful use — resets error counter."""
        async with self._lock:
            self._stats[proxy.server]["errors"] = 0

    def to_playwright_proxy(self, proxy: ProxyEntry) -> dict:
        """Convert a ProxyEntry to Playwright proxy format."""
        result = {"server": proxy.server}
        if proxy.username:
            result["username"] = proxy.username
        if proxy.password:
            result["password"] = proxy.password
        return result
