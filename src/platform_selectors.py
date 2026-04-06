"""Per-platform hardcoded selector definitions and page_action functions.

Each PlatformDef contains:
  - metrics: ordered fallback lists of SelectorDef per metric name
  - page_action: Playwright coroutine for modal dismissal / JS waiting
  - wait_selector: Scrapling waits for this CSS selector before returning
  - use_stealthy: True = StealthyFetcher (Camoufox/Cloudflare bypass),
                  False = DynamicFetcher (lighter, faster)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from playwright.async_api import Page

from src.models import SelectorDef


@dataclass
class PlatformDef:
    """Full scraping definition for one platform domain."""

    domain: str
    metrics: dict[str, list[SelectorDef]]
    page_action: Callable[[Page], Awaitable[None]] | None = None
    wait_selector: str | None = None
    wait_selector_state: str = "visible"  # Playwright state: "visible"|"attached"|"hidden"
    network_idle: bool = True             # False for meta-tag-only platforms (much faster)
    use_stealthy: bool = True             # False = use DynamicFetcher


# ---------------------------------------------------------------------------
# Page actions — run after network idle, before wait_selector
# ---------------------------------------------------------------------------


async def _instagram_action(page: Page) -> None:
    """Close Instagram login modal if it appears."""
    for selector in [
        'button[aria-label="Close"]',
        'button:has-text("Not now")',
        '[role="dialog"] button',
    ]:
        try:
            await page.click(selector, timeout=2000)
            await page.wait_for_timeout(800)
            return
        except Exception:
            continue


async def _youtube_action(page: Page) -> None:
    """Wait for ytInitialData and yt-formatted-string elements."""
    try:
        await page.wait_for_function(
            "typeof window.ytInitialData !== 'undefined'",
            timeout=15000,
        )
    except Exception:
        pass
    try:
        await page.wait_for_selector("yt-formatted-string", timeout=8000)
    except Exception:
        pass


async def _x_action(page: Page) -> None:
    """Wait for X.com SPA body content."""
    try:
        await page.wait_for_function(
            "document.body && document.body.innerText.trim().length > 100",
            timeout=20000,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Platform definitions
# ---------------------------------------------------------------------------

PLATFORM_DEFS: dict[str, PlatformDef] = {
    # ------------------------------------------------------------------
    # Instagram — real-time metrics extracted from embedded Relay JSON
    #
    # og:description is server-cached and stale (e.g. shows 46 likes when
    # the post actually has 794). The real data lives in:
    #   <script type="application/json" data-sjs="">
    # specifically the adp_PolarisPostRootQueryRelayPreloader script tag.
    #
    # Regex extraction reads response.html_content (full page HTML).
    # The discriminating pattern for likes uses "logging_info_token" which
    # immediately follows the authoritative like_count field in the JSON.
    #
    # network_idle=False: the Relay scripts are server-rendered, present
    # without waiting for background XHRs — avoids the 80s timeout trap.
    # wait_selector: og:description still used as a fast "page is ready" signal.
    # ------------------------------------------------------------------
    "instagram.com": PlatformDef(
        domain="instagram.com",
        page_action=_instagram_action,
        wait_selector='meta[property="og:description"]',
        wait_selector_state="attached",   # <meta> is never "visible"
        network_idle=False,               # Relay scripts are server-rendered, no need to wait
        metrics={
            "likes": [
                SelectorDef(
                    # Matches: "like_count": 794, "logging_info_token": ...
                    # The logging_info_token field immediately follows the authoritative like_count
                    selector=r'"like_count"\s*:\s*(\d+)\s*,\s*"logging_info_token"',
                    method="regex",
                    transform="parse_number",
                ),
                # Fallback: og:description (stale but better than nothing)
                SelectorDef(
                    selector='meta[property="og:description"]',
                    method="css",
                    attribute="content",
                    transform="instagram_likes",
                ),
            ],
            "comments": [
                SelectorDef(
                    # Matches the comment_count near like_count in the same JSON object
                    selector=r'"like_count"\s*:\s*\d+.{0,200}?"comment_count"\s*:\s*(\d+)',
                    method="regex",
                    transform="parse_number",
                ),
                # Fallback: og:description
                SelectorDef(
                    selector='meta[property="og:description"]',
                    method="css",
                    attribute="content",
                    transform="instagram_comments",
                ),
            ],
            "username": [
                SelectorDef(
                    selector='meta[name="instapp:owner_user_name"]',
                    method="css",
                    attribute="content",
                    transform="identity",
                ),
                # Second choice: first "username" key in embedded Relay JSON
                SelectorDef(
                    selector=r'"username"\s*:\s*"([^"]+)"',
                    method="regex",
                    transform="identity",
                ),
                # Fallback: parse from og:description
                SelectorDef(
                    selector='meta[property="og:description"]',
                    method="css",
                    attribute="content",
                    transform="instagram_username",
                ),
            ],
        },
    ),
    # ------------------------------------------------------------------
    # YouTube — real data is in embedded ytInitialData JSON
    #
    # viewCount and likeCount are available as numeric strings in the JSON.
    # The DOM elements (yt-formatted-string, factoid-renderer) show abbreviated
    # text ("84.4M", "16,807,590,880 views") but are not reliably selectable
    # by name because YouTube periodically changes its custom element names.
    #
    # Regex on the embedded JSON is the most stable approach.
    # Comment count is not exposed in the public page HTML.
    # ------------------------------------------------------------------
    "youtube.com": PlatformDef(
        domain="youtube.com",
        page_action=_youtube_action,
        wait_selector="yt-formatted-string",
        metrics={
            "views": [
                SelectorDef(
                    selector=r'"viewCount"\s*:\s*"(\d+)"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "likes": [
                SelectorDef(
                    selector=r'"likeCount"\s*:\s*"(\d+)"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "comments": [
                SelectorDef(
                    selector=r'"commentCount"\s*:\s*"(\d+)"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
        },
    ),
    # ------------------------------------------------------------------
    # X.com — engagement metrics from button aria-label attributes
    #
    # X renders engagement data in aria-labels without requiring auth:
    #   <button aria-label="0 Likes. Like">
    #   <button aria-label="0 reposts. Repost">
    #   <button aria-label="1 Reply. Reply">
    #   <div role="group" aria-label="1 reply, 1 bookmark, 696 views">
    #
    # Regex on raw HTML is reliable because these exact strings are
    # baked into the SSR payload and do not change with CSS class renames.
    # network_idle=False: SPA loads the tweet in the initial HTML.
    # ------------------------------------------------------------------
    "x.com": PlatformDef(
        domain="x.com",
        page_action=_x_action,
        wait_selector=None,
        network_idle=False,
        metrics={
            "likes": [
                SelectorDef(
                    selector=r'"(\d+)\s+Likes?\.\s+Like"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "reposts": [
                SelectorDef(
                    selector=r'"(\d+)\s+reposts?\.\s+Repost"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "replies": [
                SelectorDef(
                    selector=r'"(\d+)\s+Repl(?:y|ies)\.\s+Reply"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "views": [
                SelectorDef(
                    # Group aria-label: "1 reply, 1 bookmark, 696 views"
                    selector=r'(\d+)\s+views"',
                    method="regex",
                    transform="parse_number",
                ),
            ],
        },
    ),
    # ------------------------------------------------------------------
    # Facebook — engagement metrics from embedded JSON payload
    #
    # Facebook bundles full feedback data in its page JS payload even
    # without login. The JSON is not a <script type="application/json">
    # tag — it is inlined inside require() calls — so regex on
    # html_content is the correct extraction path.
    #
    # Verified patterns (as of 2026-04):
    #   reactions: "reaction_count":{"count":<N>}
    #   comments:  "comments":{"total_count":<N>}
    #   shares:    "share_count":{"count":<N>}
    # ------------------------------------------------------------------
    "facebook.com": PlatformDef(
        domain="facebook.com",
        page_action=None,
        wait_selector=None,
        network_idle=False,
        metrics={
            "reactions": [
                SelectorDef(
                    selector=r'"reaction_count"\s*:\s*\{"count"\s*:\s*(\d+)',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "comments": [
                SelectorDef(
                    selector=r'"comments"\s*:\s*\{"total_count"\s*:\s*(\d+)',
                    method="regex",
                    transform="parse_number",
                ),
            ],
            "shares": [
                SelectorDef(
                    selector=r'"share_count"\s*:\s*\{"count"\s*:\s*(\d+)',
                    method="regex",
                    transform="parse_number",
                ),
            ],
        },
    ),
    # ------------------------------------------------------------------
    # Şikayetvar — Turkish consumer complaint platform
    #
    # Each complaint page has a view counter (.js-view-count), comment
    # count (.review-count), and a supporter list (.viewer-item spans).
    # The support/upvote count is rendered as a list of user avatars —
    # no direct numeric span exists; view + comment counts are reliable.
    # ------------------------------------------------------------------
    "sikayetvar.com": PlatformDef(
        domain="sikayetvar.com",
        page_action=None,
        wait_selector=None,
        use_stealthy=False,  # DynamicFetcher sufficient
        network_idle=False,  # Ad/analytics scripts keep firing; HTML data is server-rendered
        metrics={
            "view_count": [
                SelectorDef(
                    selector="span.js-view-count",
                    method="css",
                    transform="parse_number",
                ),
            ],
            "comment_count": [
                SelectorDef(
                    selector="span.review-count",
                    method="css",
                    transform="parse_number",
                ),
            ],
        },
    ),
}


def get_platform_def(domain: str) -> PlatformDef | None:
    """Return the PlatformDef for a domain, or None if not configured."""
    return PLATFORM_DEFS.get(domain)
