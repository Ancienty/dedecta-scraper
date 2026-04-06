"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator


def _resolve_env_vars(obj: object) -> object:
    """Recursively resolve ${ENV_VAR} placeholders in strings."""
    if isinstance(obj, str):
        pattern = re.compile(r"\$\{(\w+)\}")
        def replacer(m: re.Match) -> str:
            return os.environ.get(m.group(1), m.group(0))
        return pattern.sub(replacer, obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(v) for v in obj]
    return obj


# --- Config sub-models ---


class ProxyEntry(BaseModel):
    server: str
    username: str = ""
    password: str = ""


class ProxiesConfig(BaseModel):
    rotation_strategy: Literal["round_robin", "random", "least_used"] = "round_robin"
    pool: list[ProxyEntry] = []


class RateLimitingConfig(BaseModel):
    default_delay: float = 2.0
    per_domain: dict[str, float] = {}


class ScraplingConfig(BaseModel):
    headless: bool = True
    max_sessions: int = 3
    timeout: int = 60000            # ms per page fetch
    solve_cloudflare: bool = True   # StealthyFetcher: auto-solve Cloudflare
    block_webrtc: bool = True
    hide_canvas: bool = True


class ScraperConfig(BaseModel):
    concurrency: int = 10
    max_retries: int = 3
    retry_delay: float = 5.0


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LoggingConfig(BaseModel):
    level: str = "INFO"
    json_output: bool = True


# --- Root config ---


class Settings(BaseModel):
    proxies: ProxiesConfig = ProxiesConfig()
    rate_limiting: RateLimitingConfig = RateLimitingConfig()
    scrapling: ScraplingConfig = ScraplingConfig()
    scraper: ScraperConfig = ScraperConfig()
    server: ServerConfig = ServerConfig()
    logging: LoggingConfig = LoggingConfig()

    @model_validator(mode="before")
    @classmethod
    def resolve_env_placeholders(cls, data: dict) -> dict:
        return _resolve_env_vars(data)

def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file.

    Falls back to config/settings.yaml relative to project root.
    Environment variables override ${VAR} placeholders in the YAML.
    """
    if config_path is None:
        # Look for config relative to this file's parent (src/) -> project root
        project_root = Path(__file__).resolve().parent.parent
        config_path = project_root / "config" / "settings.yaml"

    config_path = Path(config_path)
    if not config_path.exists():
        # Return defaults if no config file
        return Settings()

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    return Settings(**raw)
