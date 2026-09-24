from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PreAnalysisResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    file_name: str
    file_size_bytes: int
    article_title: str | None = None
    doi: str | None = None
    journal: str | None = None
    abstract_es_word_count: int = 0
    abstract_en_word_count: int = 0
    abstract_word_limit: int = 250
    figures_count: int = 0
    tables_count: int = 0
    references_count: int = 0
    estimated_seconds: int = 15
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    suggested_abstract_es: str | None = None
    suggested_abstract_en: str | None = None
