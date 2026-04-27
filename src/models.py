"""Pydantic data models for the scraper."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, HttpUrl


# --- Input models ---


class PostURL(BaseModel):
    """A post URL to scrape."""

    id: str
    url: HttpUrl
    platform: str | None = None
    captured_at: datetime


# --- Extraction models ---


class SelectorDef(BaseModel):
    """How to locate a single metric on a page."""

    selector: str
    method: Literal["css", "xpath", "regex", "js_eval", "css_json_path"]
    attribute: str | None = None  # None = textContent
    transform: str = "parse_number"
    json_path: str | None = None  # for css_json_path method


# --- Result models ---


class MetricValue(BaseModel):
    """A single extracted metric."""

    name: str
    value: int | str | None = None
    raw_text: str | None = None


class ScrapeResult(BaseModel):
    """Result of scraping a single post."""

    post_id: str
    url: str
    metrics: list[MetricValue]
    scraped_at: datetime
    success: bool
    error: str | None = None


# --- Unified HTTP response models ---
#
# Cross-platform normalization rules:
#   likes    ← likes, reactions
#   comments ← comments, replies
#   shares   ← shares, reposts
#   views    ← views, view_count
#   author   ← username, channel, page name, complaint creator
#
# Any platform-specific concept that doesn't fit these buckets is dropped.


class Metrics(BaseModel):
    """Unified engagement metrics across all platforms. Missing metrics are null."""

    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    views: int | None = None


class Media(BaseModel):
    """Media artefacts attached to the post (post image, video thumbnail, etc.)."""

    image_url: str | None = None


class FetchResponse(BaseModel):
    """Unified JSON response from the /fetch endpoint."""

    success: bool
    platform: str | None = None
    url: str
    scraped_at: datetime | None = None
    author: str | None = None
    metrics: Metrics = Metrics()
    media: Media = Media()
    error: str | None = None
