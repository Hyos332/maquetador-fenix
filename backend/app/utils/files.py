from __future__ import annotations

import re
import unicodedata
from pathlib import Path


SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._ -]+")


def sanitize_filename(name: str, fallback: str = "archivo") -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    cleaned = SAFE_FILENAME_PATTERN.sub("_", ascii_name).strip(" ._")
    return cleaned or fallback


def ensure_within_directory(base_dir: Path, candidate: Path) -> None:
    base = base_dir.resolve()
    target = candidate.resolve()

    if target == base or base in target.parents:
        return

    raise ValueError(f"Unsafe path escapes target directory: {candidate}")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
