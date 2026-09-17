from __future__ import annotations

import re
import unicodedata

WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return normalize_whitespace(ascii_value).casefold()


def word_count(value: str | None) -> int:
    if not value:
        return 0
    return len(re.findall(r"\b[\w'-]+\b", value, flags=re.UNICODE))
