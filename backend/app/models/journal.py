from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ImageStyle(BaseModel):
    max_width_px: int = Field(gt=0)
    max_height_px: int = Field(gt=0)

    @property
    def html_style(self) -> str:
        return f"max-width: {self.max_width_px}px; max-height: {self.max_height_px}px;"


class JournalConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    key: str
    name: str
    publisher: str
    url: str
    issn: str
    logo: str
    logo_source_url: str | None = None
    image_style: ImageStyle
    source_path: Path | None = None
