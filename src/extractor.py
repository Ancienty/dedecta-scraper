"""Metric extraction — applies platform selector definitions to Scrapling responses."""

from __future__ import annotations

import json
import re
from typing import Any

from src.logging_config import get_logger
from src.models import MetricValue, SelectorDef
from src.transforms import apply_transform

log = get_logger(__name__)


async def extract_from_response(
    response: Any,
    page: Any,
    metric_defs: dict[str, list[SelectorDef]],
) -> list[MetricValue]:
    """Extract all metrics from a Scrapling response using per-platform defs.

    Args:
        response: Scrapling response object (has .css(), .xpath(), etc.)
        page: Live Playwright Page object (captured via page_action closure, may be None)
        metric_defs: Per-metric ordered list of SelectorDef fallbacks

    Returns:
        List of MetricValue — some may have value=None if no selector matched.
    """
    results: list[MetricValue] = []
    for name, selector_list in metric_defs.items():
        metric = await _try_selectors(response, page, name, selector_list)
        results.append(metric)
    return results


async def _try_selectors(
    response: Any,
    page: Any,
    name: str,
    selector_list: list[SelectorDef],
) -> MetricValue:
    """Try each SelectorDef in order; return first non-null result."""
    for selector_def in selector_list:
        raw_text = await _extract_one(response, page, selector_def)
        if raw_text is not None:
            try:
                value = apply_transform(selector_def.transform, raw_text)
                return MetricValue(name=name, value=value, raw_text=raw_text)
            except Exception as e:
                log.debug("transform_error", name=name, raw=raw_text, error=str(e))
    return MetricValue(name=name, value=None, raw_text=None)


async def _extract_one(
    response: Any,
    page: Any,
    selector_def: SelectorDef,
) -> str | None:
    """Dispatch to the appropriate extraction method."""
    try:
        if selector_def.method == "css":
            return _extract_css_scrapling(response, selector_def)
        elif selector_def.method == "xpath":
            return _extract_xpath_scrapling(response, selector_def)
        elif selector_def.method == "js_eval":
            return await _extract_js_eval(page, selector_def)
        elif selector_def.method == "regex":
            return _extract_regex_scrapling(response, selector_def)
        elif selector_def.method == "css_json_path":
            return _extract_css_json_path(response, selector_def)
        else:
            log.warning("unknown_method", method=selector_def.method)
            return None
    except Exception as e:
        log.debug("extract_error", selector=selector_def.selector, error=str(e))
        return None


def _extract_css_scrapling(response: Any, selector_def: SelectorDef) -> str | None:
    if selector_def.attribute:
        result = response.css(
            f"{selector_def.selector}::attr({selector_def.attribute})"
        ).get()
    else:
        result = response.css(f"{selector_def.selector}::text").get()
    return result if result else None


def _extract_xpath_scrapling(response: Any, selector_def: SelectorDef) -> str | None:
    result = response.xpath(selector_def.selector).get()
    return result if result else None


async def _extract_js_eval(page: Any, selector_def: SelectorDef) -> str | None:
    """Evaluate a JS expression in the page context via the captured Playwright page.

    The expression is passed as an argument (not interpolated into function source)
    to prevent accidental JS injection if a selector were ever constructed from
    untrusted input.
    """
    if page is None:
        return None
    try:
        result = await page.evaluate(
            "(expr) => { try { return String(eval(expr)); } catch(e) { return null; } }",
            selector_def.selector,
        )
        if result and result not in ("null", "undefined"):
            return result
        return None
    except Exception:
        return None


def _extract_regex_scrapling(response: Any, selector_def: SelectorDef) -> str | None:
    html = getattr(response, "html_content", None) or ""
    match = re.search(selector_def.selector, str(html))
    if match:
        return match.group(1) if match.lastindex else match.group(0)
    return None


def _extract_css_json_path(response: Any, selector_def: SelectorDef) -> str | None:
    """Extract from a CSS-selected element's content parsed as JSON, then apply json_path."""
    if not selector_def.json_path:
        return None

    raw = response.css(f"{selector_def.selector}::text").get()
    if not raw:
        raw = response.css(selector_def.selector).get()
        if not raw:
            return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    try:
        value = _json_path_get(data, selector_def.json_path)
        return str(value) if value is not None else None
    except Exception as e:
        log.debug("json_path_error", path=selector_def.json_path, error=str(e))
        return None


def _json_path_get(data: Any, path: str) -> Any:
    """Very simple JSON path getter — supports dot notation and [n] indexing only."""
    current = data
    for part in re.split(r"\.", path):
        if not part:
            continue
        # Handle array index: key[0]
        m = re.match(r"^(.+?)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            current = current[key][idx]
        else:
            current = current[part]
    return current


def is_extraction_valid(metrics: list[MetricValue]) -> bool:
    """Return True if at least one metric has a non-None value."""
    if not metrics:
        return False
    return any(m.value is not None for m in metrics)
