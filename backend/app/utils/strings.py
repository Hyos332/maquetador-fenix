from __future__ import annotations

import re
import unicodedata

WHITESPACE_PATTERN = re.compile(r"\s+")
INVISIBLE_WORD_CHARS_PATTERN = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff]")
SPACE_LIKE_CHARS = str.maketrans(
    {
        "\u00a0": " ",
        "\u2000": " ",
        "\u2001": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
    }
)


def normalize_whitespace(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def clean_word_text(value: str) -> str:
    """Normalize text copied from DOCX XML without changing its meaning."""
    translated = value.translate(SPACE_LIKE_CHARS)
    without_invisible = INVISIBLE_WORD_CHARS_PATTERN.sub("", translated)
    return normalize_whitespace(without_invisible)


def normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return normalize_whitespace(ascii_value).casefold()


def word_count(value: str | None) -> int:
    if not value:
        return 0
    return len(re.findall(r"\b[\w'-]+\b", value, flags=re.UNICODE))
