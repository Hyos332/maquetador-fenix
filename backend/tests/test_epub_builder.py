from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from app.config.settings import Settings
from app.pipeline.article_pipeline import ArticlePipeline
from app.services.journal_config import JournalConfigService
from app.services.validator import Validator

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")


def test_pipeline_builds_valid_epub_from_validated_html(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )
    result = ArticlePipeline(settings).run(ALBERTO_FIXTURE)

    assert result.article is not None
    assert result.epub_path is not None
    assert result.epub_path.exists()

    with ZipFile(result.epub_path) as archive:
        infos = archive.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
        assert "EPUB/article.xhtml" in archive.namelist()
        assert "EPUB/content.opf" in archive.namelist()
        assert "EPUB/nav.xhtml" in archive.namelist()
        assert "EPUB/Figure_1.PNG" in archive.namelist()

    journal = JournalConfigService().load(result.article.journal)
    validation = Validator().validate_epub(result.epub_path, result.article, journal)
    assert validation.ok, validation.errors
