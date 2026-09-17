from datetime import date
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.pipeline.article_pipeline import ArticlePipeline
from app.services.docx_parser import DocxParser, ParagraphBlock, TableBlock
from app.services.image_extractor import ImageExtractor
from app.services.metadata_extractor import MetadataExtractor
from app.services.reference_processor import ReferenceProcessor
from app.services.section_extractor import SectionExtractor
from app.services.zip_service import ZipService

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")


@pytest.fixture()
def parsed_alberto(tmp_path: Path):
    package = ZipService(tmp_path / "workspaces").extract_article_zip(
        ALBERTO_FIXTURE,
        job_id="alberto",
    )
    return DocxParser().parse(package.primary_docx)


pytestmark = pytest.mark.skipif(
    not ALBERTO_FIXTURE.exists(),
    reason="Alberto fixture ZIP is not available",
)


def test_docx_parser_preserves_body_order_and_sdt_references(parsed_alberto) -> None:
    assert isinstance(parsed_alberto.blocks[0], TableBlock)
    assert isinstance(parsed_alberto.blocks[1], ParagraphBlock)
    assert parsed_alberto.blocks[1].text.endswith("10.60134/mlshn.v5n1.4594")

    reference_blocks = [
        block
        for block in parsed_alberto.blocks
        if isinstance(block, ParagraphBlock) and block.text.startswith("[")
    ]
    assert len(reference_blocks) == 175
    assert reference_blocks[0].text.startswith("[1]Boutari")
    assert reference_blocks[-1].text.startswith("[175]Carrello")


def test_metadata_references_sections_and_images_from_alberto(parsed_alberto, tmp_path: Path) -> None:
    article = MetadataExtractor().extract(parsed_alberto)
    article.references = ReferenceProcessor().extract(parsed_alberto)
    article.sections = SectionExtractor().extract(parsed_alberto)
    image_result = ImageExtractor().extract_figures(parsed_alberto, output_dir=tmp_path / "figures")
    article.figures = image_result.figures

    assert article.journal == "mlshnr"
    assert article.doi == "10.60134/mlshn.v5n1.4594"
    assert article.received_date == date(2025, 12, 2)
    assert article.reviewed_date == date(2025, 12, 5)
    assert article.accepted_date == date(2026, 6, 2)
    assert article.volume == "5"
    assert article.issue == "1"
    assert article.pages == "64-92"
    assert article.authors[0].full_name == "Alberto Nilson"
    assert article.authors[0].email == "alberto.a.nilson@gmail.com"
    assert article.authors[0].orcid == "https://orcid.org/0009-0000-5786-8060"
    assert article.title_es.startswith("Impactos de un programa virtual")
    assert article.title_en.startswith("Impacts of a holistic virtual program")
    assert article.abstract_es and "programa virtual" in article.abstract_es
    assert article.abstract_en and "virtual holistic" in article.abstract_en
    assert len(article.references) == 175
    assert [reference.number for reference in article.references] == list(range(1, 176))
    assert len(article.figures) == 7
    assert [figure.output_filename for figure in article.figures] == [
        f"Figure_{number}.PNG" for number in range(1, 8)
    ]
    assert all((tmp_path / "figures" / figure.output_filename).exists() for figure in article.figures)
    assert not image_result.warnings
    assert [section.title for section in article.sections] == [
        "Introducción",
        "Método",
        "Resultados",
        "Discusión y conclusiones",
        "Agradecimientos",
        "Conflicto de intereses",
    ]


def test_article_pipeline_dry_run_uses_same_services(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )
    result = ArticlePipeline(settings).run(ALBERTO_FIXTURE)

    assert result.article is not None
    assert result.article.doi == "10.60134/mlshn.v5n1.4594"
    assert len(result.article.references) == 175
    assert result.workspace.generated_dir.exists()
