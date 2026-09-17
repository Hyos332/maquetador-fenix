from __future__ import annotations

import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.exceptions import DocumentNotFoundError, ZipValidationError
from app.models.pipeline import WorkspacePaths
from app.utils.files import ensure_directory, ensure_within_directory, sanitize_filename


@dataclass(frozen=True)
class ExtractedPackage:
    workspace: WorkspacePaths
    source_zip: Path
    docx_files: list[Path]
    pdf_files: list[Path]
    css_files: list[Path]
    logo_files: list[Path]

    @property
    def primary_docx(self) -> Path:
        if not self.docx_files:
            raise DocumentNotFoundError("No DOCX file found in article ZIP.")
        return self.docx_files[0]


class ZipService:
    def __init__(self, workspaces_dir: Path, max_size_mb: int = 100) -> None:
        self.workspaces_dir = workspaces_dir
        self.max_size_bytes = max_size_mb * 1024 * 1024

    def extract_article_zip(self, source_zip: Path, job_id: str | None = None) -> ExtractedPackage:
        source_zip = source_zip.expanduser().resolve()
        self._validate_source_zip(source_zip)

        workspace = self._create_workspace(job_id)
        original_copy = workspace.original_dir / sanitize_filename(source_zip.name, "article.zip")
        shutil.copy2(source_zip, original_copy)

        with zipfile.ZipFile(source_zip) as archive:
            self._validate_members(archive)
            archive.extractall(workspace.extracted_dir)

        files = [path for path in workspace.extracted_dir.rglob("*") if path.is_file()]
        docx_files = sorted(path for path in files if path.suffix.lower() == ".docx")
        pdf_files = sorted(path for path in files if path.suffix.lower() == ".pdf")
        css_files = sorted(path for path in files if path.suffix.lower() == ".css")
        logo_files = sorted(
            path
            for path in files
            if path.suffix.lower() in {".svg", ".png", ".jpg", ".jpeg"}
            and "logo" in path.name.casefold()
        )

        if not docx_files:
            raise DocumentNotFoundError("No DOCX file found in article ZIP.")

        return ExtractedPackage(
            workspace=workspace,
            source_zip=original_copy,
            docx_files=docx_files,
            pdf_files=pdf_files,
            css_files=css_files,
            logo_files=logo_files,
        )

    def _validate_source_zip(self, source_zip: Path) -> None:
        if not source_zip.exists():
            raise ZipValidationError(f"ZIP not found: {source_zip}")
        if source_zip.suffix.lower() != ".zip":
            raise ZipValidationError("Only .zip files are supported.")
        if source_zip.stat().st_size > self.max_size_bytes:
            raise ZipValidationError("ZIP exceeds configured size limit.")
        if not zipfile.is_zipfile(source_zip):
            raise ZipValidationError("File is not a valid ZIP archive.")

    def _validate_members(self, archive: zipfile.ZipFile) -> None:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ZipValidationError(f"Unsafe ZIP member path: {member.filename}")

            destination = self.workspaces_dir / "_validation" / member.filename
            try:
                ensure_within_directory(self.workspaces_dir / "_validation", destination)
            except ValueError as exc:
                raise ZipValidationError(str(exc)) from exc

    def _create_workspace(self, job_id: str | None) -> WorkspacePaths:
        workspace_id = job_id or uuid.uuid4().hex
        root = ensure_directory(self.workspaces_dir / workspace_id)
        original_dir = ensure_directory(root / "original")
        extracted_dir = ensure_directory(root / "extracted")
        generated_dir = ensure_directory(root / "generated")
        backups_dir = ensure_directory(root / "backups")
        logs_dir = ensure_directory(root / "logs")

        return WorkspacePaths(
            job_id=workspace_id,
            root=root,
            original_dir=original_dir,
            extracted_dir=extracted_dir,
            generated_dir=generated_dir,
            backups_dir=backups_dir,
            logs_dir=logs_dir,
        )
