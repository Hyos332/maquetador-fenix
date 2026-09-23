from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

ORCID_PATTERN = re.compile(r"(\d{4}-\d{4}-\d{4}-[\dX]{4})", re.IGNORECASE)


class ArticleLanguage(StrEnum):
    SPANISH = "es"
    ENGLISH = "en"
    PORTUGUESE = "pt"


class Author(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str
    email: str | None = None
    institution: str | None = None
    country: str | None = None
    orcid: str | None = None

    @field_validator("orcid")
    @classmethod
    def normalize_orcid(cls, value: str | None) -> str | None:
        if not value:
            return None

        match = ORCID_PATTERN.search(value)
        if not match:
            return value.strip()

        return f"https://orcid.org/{match.group(1).upper()}"


class Section(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str
    html_content: str = ""


class Figure(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    number: int = Field(ge=1)
    source: Path
    output_filename: str
    caption: str | None = None
    is_logo: bool = False
    block_index: int | None = None
    caption_block_index: int | None = None
    group_id: str | None = None
    group_row: int | None = None
    group_col: int | None = None


class ArticleTable(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    number: int = Field(ge=1)
    caption: str | None = None
    html_content: str


class Reference(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    number: int = Field(ge=1)
    raw_text: str
    urls: list[str] = Field(default_factory=list)


class Article(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    language: ArticleLanguage = ArticleLanguage.SPANISH
    journal: str
    title_es: str | None = None
    title_en: str | None = None
    abstract_es: str | None = None
    abstract_en: str | None = None
    keywords_es: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(default_factory=list)
    authors: list[Author] = Field(default_factory=list)
    doi: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    received_date: date | None = None
    reviewed_date: date | None = None
    accepted_date: date | None = None
    sections: list[Section] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    tables: list[ArticleTable] = Field(default_factory=list)

    @property
    def primary_title(self) -> str:
        if self.language == ArticleLanguage.ENGLISH:
            return self.title_en or self.title_es or ""
        return self.title_es or self.title_en or ""
