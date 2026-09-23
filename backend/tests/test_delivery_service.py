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
    assert "Alberto Nilson.docx" in names
    assert "Alberto Nilson.pdf" in names

    with ZipFile(result.delivery_zip) as archive:
        zip_names = archive.namelist()
        assert "Alberto Nilson-esp/Alberto_Nilson_esp.html" in zip_names
        assert "Alberto Nilson-esp/Alberto_Nilson_esp.epub" in zip_names
        assert "Alberto Nilson-esp/Alberto Nilson.docx" in zip_names
        assert "Alberto Nilson-esp/Alberto Nilson.pdf" in zip_names


def test_pipeline_replaces_stale_delivery_folder_before_zipping(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )

    stale_dir = settings.deliveries_dir / "Alberto Nilson" / "Alberto Nilson-esp"
    stale_dir.mkdir(parents=True)
    (stale_dir / "Alberto Nilson_esp_1_.docx").write_text("old duplicate", encoding="utf-8")
    (stale_dir / "Figure_99.PNG").write_text("old figure", encoding="utf-8")

    result = ArticlePipeline(settings).run(ALBERTO_FIXTURE)

    assert result.delivery_dir is not None
    assert result.delivery_zip is not None
    delivery_names = {path.name for path in result.delivery_dir.iterdir()}
    assert "Alberto Nilson_esp_1_.docx" not in delivery_names
    assert "Figure_99.PNG" not in delivery_names

    with ZipFile(result.delivery_zip) as archive:
        zip_names = set(archive.namelist())
        assert "Alberto Nilson-esp/Alberto Nilson_esp_1_.docx" not in zip_names
        assert "Alberto Nilson-esp/Figure_99.PNG" not in zip_names
