from pathlib import Path
from zipfile import ZipFile

from app.config.settings import Settings
from app.pipeline.article_pipeline import ArticlePipeline

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")


def test_pipeline_creates_clean_delivery_zip(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )

    result = ArticlePipeline(settings).run(ALBERTO_FIXTURE)

    assert result.delivery_dir is not None
    assert result.delivery_zip is not None
    assert result.delivery_zip.exists()

    names = sorted(path.name for path in result.delivery_dir.iterdir())
    assert "Alberto_Nilson_esp.html" in names
    assert "Alberto_Nilson_esp.epub" in names
    assert "galleys.css" in names
    assert "logo-mlshn.svg" in names
    assert "Figure_1.PNG" in names
    assert not any(name.endswith(".docx") or name.endswith(".pdf") for name in names)

    with ZipFile(result.delivery_zip) as archive:
        zip_names = archive.namelist()
        assert "Alberto Nilson-esp/Alberto_Nilson_esp.html" in zip_names
        assert "Alberto Nilson-esp/Alberto_Nilson_esp.epub" in zip_names
        assert not any(name.endswith(".docx") or name.endswith(".pdf") for name in zip_names)
