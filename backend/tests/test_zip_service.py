from pathlib import Path
from zipfile import ZipFile

import pytest

from app.exceptions import DocumentNotFoundError, ZipValidationError
from app.services.zip_service import ZipService

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")


@pytest.mark.skipif(not ALBERTO_FIXTURE.exists(), reason="Alberto fixture ZIP is not available")
def test_extract_article_zip_creates_workspace_and_detects_expected_files(tmp_path: Path) -> None:
    package = ZipService(tmp_path).extract_article_zip(ALBERTO_FIXTURE, job_id="fixture-alberto")

    assert package.workspace.root == tmp_path / "fixture-alberto"
    assert package.workspace.original_dir.exists()
    assert package.workspace.extracted_dir.exists()
    assert package.primary_docx.name == "Alberto Nilson.docx"
    assert len(package.docx_files) == 1
    assert len(package.pdf_files) == 1
    assert [path.name for path in package.css_files] == ["galleys.css"]
    assert [path.name for path in package.logo_files] == ["logo-mlshn.svg"]


def test_extract_article_zip_rejects_zip_slip(tmp_path: Path) -> None:
    malicious_zip = tmp_path / "malicious.zip"
    with ZipFile(malicious_zip, "w") as archive:
        archive.writestr("../escape.docx", "bad")

    with pytest.raises(ZipValidationError):
        ZipService(tmp_path / "workspaces").extract_article_zip(malicious_zip)


def test_extract_article_zip_requires_docx(tmp_path: Path) -> None:
    no_docx_zip = tmp_path / "no_docx.zip"
    with ZipFile(no_docx_zip, "w") as archive:
        archive.writestr("article/readme.txt", "missing docx")

    with pytest.raises(DocumentNotFoundError):
        ZipService(tmp_path / "workspaces").extract_article_zip(no_docx_zip)
