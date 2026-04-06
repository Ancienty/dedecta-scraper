"""Debug tool: test Scrapling extraction against a live URL.

Usage:
    python scripts/test_mapping.py <url>

Visits the URL with Scrapling, runs platform selector extraction,
and prints all metric results with raw values.
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.extractor import extract_from_response
from src.logging_config import setup_logging
from src.platform_selectors import get_platform_def
from src.proxy_pool import ProxyPool
from src.scrapling_pool import ScraplingPool


def _get_domain(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    return domain[4:] if domain.startswith("www.") else domain


async def test_url(url: str) -> None:
    settings = load_settings()
    setup_logging(level="DEBUG", json_output=False)

    domain = _get_domain(url)
    print(f"\nDomain: {domain}")
    print(f"URL: {url}\n")

    platform_def = get_platform_def(domain)
    if platform_def:
        print(f"Platform def found: {list(platform_def.metrics.keys())}")
        print(f"  use_stealthy: {platform_def.use_stealthy}")
        print(f"  wait_selector: {platform_def.wait_selector!r}")
    else:
        print("No platform def — will fetch without selectors (raw HTML only)")
    print()

    proxy_pool = ProxyPool(settings.proxies)
    pool = ScraplingPool(settings.scrapling, proxy_pool)

    try:
        print("Starting Scrapling sessions...")
        await pool.start()

        page_ref: dict = {}

        async def combined_action(page) -> None:
            page_ref["page"] = page
            if platform_def and platform_def.page_action:
                print("  Running platform page_action (modal dismiss / JS wait)...")
                await platform_def.page_action(page)

        print("Fetching URL...")
        response = await pool.fetch(
            url=url,
            page_action=combined_action,
            wait_selector=platform_def.wait_selector if platform_def else None,
            wait_selector_state=platform_def.wait_selector_state if platform_def else "visible",
            network_idle=platform_def.network_idle if platform_def else True,
            use_stealthy=platform_def.use_stealthy if platform_def else True,
        )
        print("  Fetch complete.\n")

        # Always save HTML for inspection
        html = getattr(response, "html_content", None) or ""
        debug_path = Path(f"data/debug_{domain.replace('.', '_')}.html")
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(str(html), encoding="utf-8", errors="replace")
        print(f"  HTML saved: {debug_path} ({len(str(html)):,} chars)\n")

        if not platform_def or not platform_def.metrics:
            print("No metrics defined for this platform.")
            return

        print("Extracting metrics...")
        metrics = await extract_from_response(
            response=response,
            page=page_ref.get("page"),
            metric_defs=platform_def.metrics,
        )

        print("\n--- Results ---")
        for m in metrics:
            status = "OK" if m.value is not None else "MISSING"
            raw_safe = (m.raw_text or "").encode("ascii", errors="replace").decode("ascii")
            print(f"  {m.name}: {m.value}  (raw: {raw_safe!r})  [{status}]")

        any_valid = any(m.value is not None for m in metrics)
        print(f"\nExtraction valid: {any_valid}")

        if not any_valid:
            # Save HTML for debugging
            html = getattr(response, "html_content", None) or str(response)
            debug_path = Path(f"data/debug_{domain.replace('.', '_')}.html")
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(str(html), encoding="utf-8")
            print(f"All metrics null — HTML saved to {debug_path}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await pool.shutdown()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_mapping.py <url>")
        sys.exit(1)

    asyncio.run(test_url(sys.argv[1]))
