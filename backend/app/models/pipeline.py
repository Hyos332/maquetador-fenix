from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.models.article import Article


class PipelineStatus(StrEnum):
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    METADATA_EXTRACTED = "METADATA_EXTRACTED"
    AUTOMATING_MLS = "AUTOMATING_MLS"
    HTML_DOWNLOADED = "HTML_DOWNLOADED"
    POST_PROCESSING = "POST_PROCESSING"
    BUILDING_EPUB = "BUILDING_EPUB"
    VALIDATING = "VALIDATING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PipelineStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    status: PipelineStatus
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkspacePaths(BaseModel):
    job_id: str
    root: Path
    original_dir: Path
    extracted_dir: Path
    generated_dir: Path
    backups_dir: Path
    logs_dir: Path


class PipelineResult(BaseModel):
    job_id: str
    status: PipelineStatus
    workspace: WorkspacePaths
    article: Article | None = None
    warnings: list[str] = Field(default_factory=list)
    html_path: Path | None = None
    epub_path: Path | None = None
    delivery_dir: Path | None = None
    delivery_zip: Path | None = None
