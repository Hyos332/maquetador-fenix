from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict

from app.config.settings import Settings, settings as app_settings
from app.models.pipeline import PipelineResult, PipelineStatus
from app.pipeline.article_pipeline import ArticlePipeline
from app.services.docx_parser import DocxParser, ParagraphBlock, TableBlock
from app.utils.files import ensure_directory, sanitize_filename
from app.utils.strings import word_count

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
    abstract_es: str | None = None
    abstract_en: str | None = None
    abstract_es_word_count: int | None = None
    abstract_en_word_count: int | None = None
    abstract_word_limit: int = 250
    ai_suggestions: list[str] = []
    suggested_abstract_es: str | None = None
    suggested_abstract_en: str | None = None
    html_url: str | None = None
    source_preview_url: str | None = None
    epub_url: str | None = None
    delivery_dir_path: str | None = None
    delivery_url: str | None = None
    delivery_archive_url: str | None = None


class AbstractReviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    abstract_es: str | None = None
    abstract_en: str | None = None


jobs: dict[str, JobRecord] = {}
jobs_lock = threading.Lock()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> CreateJobResponse:
    filename = sanitize_filename(file.filename or "article.docx")
    if not filename.lower().endswith((".zip", ".docx")):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .zip o .docx.")

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


@router.patch("/jobs/{job_id}/abstracts", response_model=CreateJobResponse)
def update_job_abstracts(
    job_id: str,
    payload: AbstractReviewRequest,
    background_tasks: BackgroundTasks,
) -> CreateJobResponse:
    overrides = payload.model_dump(exclude_none=True)
    if not overrides:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un resumen.")

    with jobs_lock:
        record = jobs.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
        if record.status not in {PipelineStatus.COMPLETED, PipelineStatus.FAILED, PipelineStatus.NEEDS_REVIEW}:
            raise HTTPException(status_code=409, detail="El trabajo todavía está en proceso.")
        record.status = PipelineStatus.PENDING
        record.message = "Regenerando con resúmenes revisados."
        record.warnings = []
        record.error = None
        record.updated_at = datetime.now(UTC)
        source_zip = record.source_zip

    background_tasks.add_task(_run_job, job_id, source_zip, app_settings, overrides)
    return CreateJobResponse(job_id=job_id, status=PipelineStatus.PENDING, message=record.message)


@router.get("/jobs/{job_id}/html")
def get_job_html(job_id: str) -> FileResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.html_path:
        raise HTTPException(status_code=404, detail="HTML no disponible.")
    return FileResponse(record.result.html_path, media_type="text/html")


@router.get("/jobs/{job_id}/source-preview")
def get_job_source_preview(job_id: str) -> HTMLResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.article:
        raise HTTPException(status_code=404, detail="Vista DOCX no disponible.")

    source_docx = _source_docx_for_preview(record)
    if not source_docx:
        raise HTTPException(status_code=404, detail="DOCX original no disponible.")

    parsed = DocxParser().parse(source_docx)
    return HTMLResponse(_render_docx_preview(record.job_id, parsed, record.result))


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
def get_job_delivery(job_id: str) -> HTMLResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.delivery_dir:
        raise HTTPException(status_code=404, detail="Entrega no disponible.")
    return HTMLResponse(_render_delivery_folder(record.job_id, record.result.delivery_dir))


@router.get("/jobs/{job_id}/delivery/archive")
def get_job_delivery_archive(job_id: str) -> FileResponse:
    record = _get_record(job_id)
    if not record.result or not record.result.delivery_zip:
        raise HTTPException(status_code=404, detail="Entrega no disponible.")
    return FileResponse(
        record.result.delivery_zip,
        media_type="application/zip",
        filename=record.result.delivery_zip.name,
    )


@router.get("/jobs/{job_id}/delivery/files/{asset_name}")
def get_delivery_file(job_id: str, asset_name: str) -> FileResponse:
    if "/" in asset_name or "\\" in asset_name or asset_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Nombre de recurso inválido.")

    record = _get_record(job_id)
    if not record.result or not record.result.delivery_dir:
        raise HTTPException(status_code=404, detail="Entrega no disponible.")

    asset_path = record.result.delivery_dir / asset_name
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    return FileResponse(asset_path, filename=asset_path.name)


@router.get("/jobs/{job_id}/{asset_name}")
def get_job_asset(job_id: str, asset_name: str) -> FileResponse:
    if "/" in asset_name or "\\" in asset_name or asset_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Nombre de recurso inválido.")

    record = _get_record(job_id)
    if not record.result:
        raise HTTPException(status_code=404, detail="Recurso no disponible.")

    asset_path = record.result.workspace.generated_dir / asset_name
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Recurso no encontrado.")

    return FileResponse(asset_path)


def _run_job(
    job_id: str,
    source_zip: Path,
    runtime_settings: Settings,
    abstract_overrides: dict[str, str] | None = None,
) -> None:
    def progress(status: PipelineStatus, message: str) -> None:
        with jobs_lock:
            record = jobs[job_id]
            record.status = status
            record.message = message
            record.updated_at = datetime.now(UTC)

    try:
        result = ArticlePipeline(runtime_settings).run(
            source_zip,
            progress=progress,
            abstract_overrides=abstract_overrides,
        )
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
    source_preview_url = (
        f"/api/jobs/{record.job_id}/source-preview"
        if record.result and record.result.article and _source_docx_for_preview(record)
        else None
    )
    epub_url = f"/api/jobs/{record.job_id}/epub" if record.result and record.result.epub_path else None
    delivery_url = f"/api/jobs/{record.job_id}/delivery" if record.result and record.result.delivery_dir else None
    delivery_archive_url = (
        f"/api/jobs/{record.job_id}/delivery/archive"
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
        abstract_es=article.abstract_es if article else None,
        abstract_en=article.abstract_en if article else None,
        abstract_es_word_count=word_count(article.abstract_es) if article else None,
        abstract_en_word_count=word_count(article.abstract_en) if article else None,
        ai_suggestions=record.result.ai_suggestions if record.result else [],
        suggested_abstract_es=record.result.suggested_abstract_es if record.result else None,
        suggested_abstract_en=record.result.suggested_abstract_en if record.result else None,
        html_url=html_url,
        source_preview_url=source_preview_url,
        epub_url=epub_url,
        delivery_dir_path=_delivery_dir_path(record.result),
        delivery_url=delivery_url,
        delivery_archive_url=delivery_archive_url,
    )


def _delivery_dir_path(result: PipelineResult | None) -> str | None:
    if not result or not result.delivery_dir:
        return None

    try:
        relative_path = result.delivery_dir.relative_to(app_settings.deliveries_dir)
    except ValueError:
        return str(result.delivery_dir)

    return str(Path("deliveries") / relative_path)


def _render_delivery_folder(job_id: str, delivery_dir: Path) -> str:
    files = sorted(path for path in delivery_dir.iterdir() if path.is_file())
    rows = "\n".join(_render_delivery_row(job_id, path) for path in files)
    folder_name = escape(delivery_dir.name)
    folder_path = escape(str(delivery_dir))

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{folder_name}</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #17202a; background: #f6f8fb; }}
    main {{ max-width: 1100px; margin: 36px auto; padding: 0 20px; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; }}
    code {{ color: #576175; }}
    table {{ width: 100%; margin-top: 24px; border-collapse: collapse; background: white; border: 1px solid #d7dee8; }}
    th, td {{ padding: 13px 16px; border-bottom: 1px solid #e5eaf1; text-align: left; }}
    th {{ font-size: 13px; color: #667085; background: #f9fafb; }}
    a {{ color: #0f766e; font-weight: 700; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <main>
    <h1>{folder_name}</h1>
    <code>{folder_path}</code>
    <table>
      <thead>
        <tr>
          <th>Archivo</th>
          <th>Tamaño</th>
          <th>Acción</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </main>
</body>
</html>"""


def _render_delivery_row(job_id: str, path: Path) -> str:
    name = escape(path.name)
    href = f"/api/jobs/{job_id}/delivery/files/{quote(path.name)}"
    size = _format_size(path.stat().st_size)
    return f"""<tr>
  <td>{name}</td>
  <td>{size}</td>
  <td><a href="{href}" target="_blank" rel="noreferrer">Abrir</a></td>
</tr>"""


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _source_docx_for_preview(record: JobRecord) -> Path | None:
    if record.source_zip.suffix.lower() == ".docx" and record.source_zip.exists():
        return record.source_zip

    if record.result and record.result.delivery_dir:
        docx_files = sorted(record.result.delivery_dir.glob("*.docx"))
        if docx_files:
            return docx_files[0]

    return None


def _render_docx_preview(job_id: str, parsed, result: PipelineResult) -> str:
    article = result.article
    figures_by_block: dict[int, list] = {}
    if article:
        for figure in article.figures:
            if figure.block_index is not None:
                figures_by_block.setdefault(figure.block_index, []).append(figure)

    body_parts: list[str] = []
    for block_index, block in enumerate(parsed.blocks):
        if block_index in figures_by_block:
            body_parts.extend(_render_source_figure(job_id, figure) for figure in figures_by_block[block_index])

        if isinstance(block, ParagraphBlock):
            if block.text:
                body_parts.append(f"<p>{escape(block.text)}</p>")
        elif isinstance(block, TableBlock):
            if block.image_relationship_ids or block.chart_relationship_ids:
                table_text = _table_text(block)
                if table_text:
                    body_parts.append(f'<p class="embedded-text">{escape(table_text)}</p>')
                continue
            body_parts.append(_render_source_table(block))

    title = escape(article.primary_title if article else parsed.path.stem)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DOCX original - {title}</title>
  <style>
    body {{ margin: 0; padding: 18px; color: #1f2937; background: #fff; font-family: Arial, Helvetica, sans-serif; line-height: 1.38; }}
    main {{ max-width: 980px; margin: 0 auto; }}
    h1 {{ margin: 0 0 18px; font-size: 18px; color: #334155; }}
    p {{ margin: 0 0 12px; font-size: 15px; }}
    table {{ width: 100%; margin: 12px 0; border-collapse: collapse; table-layout: fixed; }}
    td {{ border: 1px solid #d7dee8; padding: 8px; vertical-align: top; overflow-wrap: anywhere; }}
    img {{ display: block; max-width: 100%; height: auto; margin: 14px auto; border: 1px solid #e5e7eb; }}
    .embedded-text {{ color: #475569; font-style: italic; text-align: center; }}
  </style>
</head>
<body>
  <main>
    <h1>DOCX original</h1>
    {"".join(body_parts)}
  </main>
</body>
</html>"""


def _render_source_figure(job_id: str, figure) -> str:
    source = f"/api/jobs/{job_id}/{quote(figure.output_filename)}"
    alt = escape(figure.caption or figure.output_filename)
    caption = f'<p class="embedded-text">{escape(figure.caption)}</p>' if figure.caption else ""
    return f'<img src="{source}" alt="{alt}">{caption}'


def _render_source_table(block: TableBlock) -> str:
    rows = []
    for row in block.rows:
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in row)
        rows.append(f"<tr>{cells}</tr>")
    return "<table><tbody>" + "".join(rows) + "</tbody></table>"


def _table_text(block: TableBlock) -> str:
    return " ".join(cell for row in block.rows for cell in row if cell).strip()
