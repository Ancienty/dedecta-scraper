"""Pool of Scrapling fetcher sessions — replaces browser_pool.py."""

from __future__ import annotations

from typing import Any

from scrapling.fetchers import AsyncDynamicSession, AsyncStealthySession

from src.config import ScraplingConfig
from src.logging_config import get_logger
from src.proxy_pool import ProxyPool

log = get_logger(__name__)


class ScraplingPool:
    """Manages a pair of Scrapling sessions (stealthy + dynamic).

    One AsyncStealthySession (Camoufox-backed, Cloudflare bypass) and one
    AsyncDynamicSession (lighter) are shared across all fetches. Platform
    definitions choose which session to use via `use_stealthy`.
    """

    def __init__(self, config: ScraplingConfig, proxy_pool: ProxyPool) -> None:
        self._config = config
        self._proxy_pool = proxy_pool
        self._stealthy: AsyncStealthySession | None = None
        self._dynamic: AsyncDynamicSession | None = None

    async def start(self) -> None:
        """Launch Scrapling browser sessions."""
        # max_sessions is informational (logged at startup); this pool uses one
        # stealthy session + one dynamic session shared across all fetches.
        self._stealthy = AsyncStealthySession(
            headless=self._config.headless,
            block_webrtc=self._config.block_webrtc,
            hide_canvas=self._config.hide_canvas,
            solve_cloudflare=self._config.solve_cloudflare,
        )
        await self._stealthy.start()

        self._dynamic = AsyncDynamicSession(
            headless=self._config.headless,
        )
        await self._dynamic.start()

        log.info("scrapling_pool_started")

    async def shutdown(self) -> None:
        """Close all sessions gracefully."""
        if self._stealthy:
            try:
                await self._stealthy.close()
            except Exception as e:
                log.warning("stealthy_session_close_error", error=str(e))

        if self._dynamic:
            try:
                await self._dynamic.close()
            except Exception as e:
                log.warning("dynamic_session_close_error", error=str(e))

        log.info("scrapling_pool_shutdown")

    async def fetch(
        self,
        url: str,
        page_action: Any = None,
        wait_selector: str | None = None,
        wait_selector_state: str = "visible",
        network_idle: bool = True,
        use_stealthy: bool = True,
    ) -> Any:
        """Fetch a URL using the appropriate Scrapling session.

        Args:
            url: The URL to fetch.
            page_action: Optional Playwright coroutine for modal dismissal / JS waiting.
            wait_selector: CSS selector Scrapling waits for before returning.
            wait_selector_state: Playwright element state ("visible"|"attached"|"hidden").
                                  Use "attached" for <meta> / <script> elements.
            network_idle: Wait for 500ms of no network activity before returning.
                          Set False for platforms where data is in <head> meta tags.
            use_stealthy: True = AsyncStealthySession, False = AsyncDynamicSession.

        Returns:
            Scrapling response object with .css(), .xpath(), etc.
        """
        proxy = await self._proxy_pool.get_proxy() if self._proxy_pool.size > 0 else None

        kwargs: dict[str, Any] = {
            "network_idle": network_idle,
            "timeout": self._config.timeout,
        }

        if page_action is not None:
            kwargs["page_action"] = page_action
        if wait_selector is not None:
            kwargs["wait_selector"] = wait_selector
            kwargs["wait_selector_state"] = wait_selector_state
        if proxy is not None:
            if proxy.username and proxy.password:
                server = proxy.server
                if "://" in server and "@" not in server:
                    scheme, rest = server.split("://", 1)
                    kwargs["proxy"] = f"{scheme}://{proxy.username}:{proxy.password}@{rest}"
                else:
                    kwargs["proxy"] = server
            else:
                kwargs["proxy"] = proxy.server

        session = self._stealthy if use_stealthy else self._dynamic
        if session is None:
            raise RuntimeError("ScraplingPool.start() must be called before fetch()")

        return await session.fetch(url, **kwargs)
