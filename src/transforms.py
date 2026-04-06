"""Value transforms for extracting numeric metrics from raw text."""

from __future__ import annotations

import re
from typing import Callable

# Multiplier suffixes — includes Turkish abbreviations
_MULTIPLIERS: dict[str, int] = {
    "k": 1_000,
    "b": 1_000,       # Turkish "bin" = thousand
    "m": 1_000_000,
    "mn": 1_000_000,  # Turkish "milyon"
    "mi": 1_000_000,  # occasional abbreviation
    "mr": 1_000_000_000,  # Turkish "milyar"
    "g": 1_000_000_000,   # rare "giga" style
}

# Pattern: optional number with comma/dot separators, optional suffix
_NUMBER_RE = re.compile(
    r"(?P<num>[0-9]+(?:[.,][0-9]+)*)"
    r"\s*"
    r"(?P<suffix>[a-zA-ZğüşöçıİĞÜŞÖÇ]*)",
    re.IGNORECASE,
)


def parse_number(text: str | None) -> int | None:
    """Parse a human-readable number string into an integer.

    Handles:
      - Plain numbers: "1,234" -> 1234
      - Abbreviated: "1.2K" -> 1200, "3.5M" -> 3_500_000
      - Turkish: "1,2B" (bin=1000), "3,5Mn" (milyon=1M)
      - Aria-label style: "1,234 likes" -> 1234
      - Empty/dash/None -> None
    """
    if not text:
        return None

    text = text.strip()
    if not text or text in ("-", "--", "—", "N/A", "n/a"):
        return None

    match = _NUMBER_RE.search(text)
    if not match:
        return None

    num_str = match.group("num")
    suffix = match.group("suffix").lower().strip()

    # Determine decimal separator: if there's exactly one separator and a suffix
    # follows, it's likely a decimal (e.g., "1.2K", "3,5M")
    if suffix and suffix in _MULTIPLIERS:
        # Treat the last separator as decimal
        num_str = _replace_last_separator_with_dot(num_str)
        num_str = num_str.replace(",", "").replace(".", "", num_str.count(".") - 1)
        try:
            value = float(num_str) * _MULTIPLIERS[suffix]
            return int(value)
        except (ValueError, OverflowError):
            return None

    # No recognized suffix — treat as plain integer
    # Remove thousands separators (both comma and dot)
    cleaned = _parse_plain_number(num_str)
    return cleaned


def _replace_last_separator_with_dot(s: str) -> str:
    """Replace the last comma or dot with a decimal point."""
    for i in range(len(s) - 1, -1, -1):
        if s[i] in (",", "."):
            return s[:i] + "." + s[i + 1 :]
    return s


def _parse_plain_number(num_str: str) -> int | None:
    """Parse a plain number string (no suffix) into int.

    Handles formats like: 1234, 1,234, 1.234, 1,234,567
    Ambiguous cases (1,234 vs 1.234) resolved by context:
      - If there's a single separator with exactly 3 digits after → thousands separator
      - Otherwise treat last separator as decimal
    """
    separators = [c for c in num_str if c in (",", ".")]
    if not separators:
        try:
            return int(num_str)
        except ValueError:
            return None

    # Check if all separators are the same and segments after each are 3 digits
    # e.g., "1,234,567" or "1.234.567" → thousands separators
    parts = re.split(r"[.,]", num_str)
    if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]):
        # All groups are 3 digits → thousands separators, remove them
        try:
            return int("".join(parts))
        except ValueError:
            return None

    # Mixed or ambiguous: treat last separator as decimal
    num_str = _replace_last_separator_with_dot(num_str)
    num_str = num_str.replace(",", "").replace(".", "", num_str.count(".") - 1)
    try:
        return int(float(num_str))
    except (ValueError, OverflowError):
        return None


# Instagram og:description: "1,234 Likes, 56 Comments - username: caption"
# Turkish variant:          "1.234 Beğeni, 56 Yorum - username: caption"
_INSTA_LIKES_RE = re.compile(r"^([\d,\.]+)\s+(?:like[s]?|beğeni)", re.IGNORECASE)
_INSTA_COMMENTS_RE = re.compile(r"([\d,\.]+)\s+(?:comment[s]?|yorum)", re.IGNORECASE)


def instagram_likes(text: str | None) -> int | None:
    """Extract like count from Instagram og:description content."""
    if not text:
        return None
    m = _INSTA_LIKES_RE.search(text)
    if m:
        return parse_number(m.group(1))
    return None


def instagram_comments(text: str | None) -> int | None:
    """Extract comment count from Instagram og:description content."""
    if not text:
        return None
    m = _INSTA_COMMENTS_RE.search(text)
    if m:
        return parse_number(m.group(1))
    return None


# og:description format: "46 likes, 5 comments - cop31champion on March 24, 2026: caption"
_INSTA_USERNAME_RE = re.compile(r"-\s+(\w+)\s+on\s+\w+", re.IGNORECASE)


def instagram_username(text: str | None) -> str | None:
    """Extract username from Instagram og:description content."""
    if not text:
        return None
    m = _INSTA_USERNAME_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def identity(text: str | None) -> str | None:
    """Return the raw text stripped of whitespace (for non-numeric values)."""
    if text is None:
        return None
    return text.strip()


# Registry of transform functions
TRANSFORMS: dict[str, Callable[[str | None], int | str | None]] = {
    "parse_number": parse_number,
    "instagram_likes": instagram_likes,
    "instagram_comments": instagram_comments,
    "instagram_username": instagram_username,
    "identity": identity,
}


def apply_transform(name: str, text: str | None) -> int | str | None:
    """Apply a named transform function."""
    fn = TRANSFORMS.get(name)
    if fn is None:
        raise ValueError(f"Unknown transform: {name!r}")
    return fn(text)
