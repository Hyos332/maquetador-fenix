from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.config.settings import Settings, settings as app_settings
from app.models.pipeline import PipelineResult, PipelineStatus
from app.pipeline.article_pipeline import ArticlePipeline
from app.utils.files import ensure_directory, sanitize_filename

router = APIRouter(prefix="/api", tags=["jobs"])


@dataclass
class JobRecord:
    job_id: str
    source_zip: Path
    status: PipelineStatus = PipelineStatus.PENDING
    message: str = "Trabajo pendiente."
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    result: PipelineResult | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CreateJobResponse(BaseModel):
    job_id: str
    status: PipelineStatus
    message: str


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    job_id: str
    status: PipelineStatus
    message: str
    warnings: list[str] = []
    error: str | None = None
    article_title: str | None = None
    doi: str | None = None
    references_count: int | None = None
    figures_count: int | None = None
    html_url: str | None = None
    epub_url: str | None = None
    delivery_url: str | None = None


jobs: dict[str, JobRecord] = {}
jobs_lock = threading.Lock()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> CreateJobResponse:
    filename = sanitize_filename(file.filename or "article.zip")
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .zip.")

    job_id = uuid.uuid4().hex
    upload_dir = ensure_directory(app_settings.workspaces_dir / "incoming")
    source_zip = upload_dir / f"{job_id}_{filename}"
    source_zip.write_bytes(await file.read())

    record = JobRecord(job_id=job_id, source_zip=source_zip)
    with jobs_lock:
        jobs[job_id] = record

    background_tasks.add_task(_run_job, job_id, source_zip, app_settings)
    return CreateJobResponse(job_id=job_id, status=record.status, message=record.message)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    record = _get_record(job_id)
    return _to_status_response(record)


@router.get("/jobs/{job_id}/html")
def get_job_html(job_id: str) -> FileResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.html_path:
        raise HTTPException(status_code=404, detail="HTML no disponible.")
    return FileResponse(record.result.html_path, media_type="text/html")


@router.get("/jobs/{job_id}/epub")
def get_job_epub(job_id: str) -> FileResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.epub_path:
        raise HTTPException(status_code=404, detail="EPUB no disponible.")
    return FileResponse(
        record.result.epub_path,
        media_type="application/epub+zip",
        filename=record.result.epub_path.name,
    )


@router.get("/jobs/{job_id}/delivery")
def get_job_delivery(job_id: str) -> FileResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.delivery_zip:
        raise HTTPException(status_code=404, detail="Entrega no disponible.")
    return FileResponse(
        record.result.delivery_zip,
        media_type="application/zip",
        filename=record.result.delivery_zip.name,
    )


def _run_job(job_id: str, source_zip: Path, runtime_settings: Settings) -> None:
    def progress(status: PipelineStatus, message: str) -> None:
        with jobs_lock:
            record = jobs[job_id]
            record.status = status
            record.message = message
            record.updated_at = datetime.now(UTC)

    try:
        result = ArticlePipeline(runtime_settings).run(source_zip, progress=progress)
        with jobs_lock:
            record = jobs[job_id]
            record.status = result.status
            record.message = "Trabajo finalizado."
            record.warnings = result.warnings
            record.result = result
            record.updated_at = datetime.now(UTC)
    except Exception as exc:  # Intentional API boundary: convert expected/unexpected failures to job state.
        with jobs_lock:
            record = jobs[job_id]
            record.status = PipelineStatus.FAILED
            record.message = "El trabajo falló."
            record.error = str(exc)
            record.updated_at = datetime.now(UTC)


def _get_record(job_id: str) -> JobRecord:
    with jobs_lock:
        record = jobs.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    return record


def _to_status_response(record: JobRecord) -> JobStatusResponse:
    article = record.result.article if record.result else None
    html_url = f"/api/jobs/{record.job_id}/html" if record.result and record.result.html_path else None
    epub_url = f"/api/jobs/{record.job_id}/epub" if record.result and record.result.epub_path else None
    delivery_url = (
        f"/api/jobs/{record.job_id}/delivery"
        if record.result and record.result.delivery_zip
        else None
    )

    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        message=record.message,
        warnings=record.warnings,
        error=record.error,
        article_title=article.primary_title if article else None,
        doi=article.doi if article else None,
        references_count=len(article.references) if article else None,
        figures_count=len(article.figures) if article else None,
        html_url=html_url,
        epub_url=epub_url,
        delivery_url=delivery_url,
    )
