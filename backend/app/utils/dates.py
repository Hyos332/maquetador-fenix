from __future__ import annotations

from datetime import date


def format_short_spanish_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d/%m/%y")


def format_epub_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.isoformat()
