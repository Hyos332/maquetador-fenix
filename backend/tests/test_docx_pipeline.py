from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.config.settings import Settings
from app.pipeline.article_pipeline import ArticlePipeline
from app.services.docx_parser import DocxParser, ImageRelationship, ParagraphBlock, ParsedDocument, TableBlock
from app.services.image_extractor import ImageExtractor
from app.services.metadata_extractor import MetadataExtractor
from app.services.reference_processor import ReferenceProcessor
from app.services.section_extractor import SectionExtractor
from app.services.zip_service import ZipService

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")
ANTONIO_DOCX_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Antonio Abarca_Eng.docx")
BESSY_DOCX_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Documentos/Bessy Valeska_Eng.docx")
CARBALLIDO_DOCX_FIXTURE = Path(
    "/home/luis.hoyos@ctdesarrollo-sdr.org/Escritorio/felipe.hoyos/maquetador-fenix/"
    "workspaces/ca63247341c948c3bb39414b03de5b3a/extracted/1. Carballidp Perea-Eng.docx"
)


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


def test_image_extractor_keeps_real_table_images_without_caption_and_skips_header_logo(tmp_path: Path) -> None:
    docx_path = tmp_path / "article.docx"
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with ZipFile(docx_path, "w") as archive:
        archive.writestr("word/media/logo.png", tiny_png)
        archive.writestr("word/media/figure.png", tiny_png)

    parsed = ParsedDocument(
        path=docx_path,
        blocks=(
            TableBlock(
                index=1,
                rows=(("MLS - EDUCATIONAL RESEARCH (MLSER) | ISSN: 2603-5820",),),
                image_relationship_ids=("rLogo",),
            ),
            ParagraphBlock(index=2, text="Introduction"),
            TableBlock(index=3, rows=(("",),), image_relationship_ids=("rFigure",)),
        ),
        image_relationships={
            "rLogo": ImageRelationship("rLogo", "media/logo.png", "word/media/logo.png"),
            "rFigure": ImageRelationship("rFigure", "media/figure.png", "word/media/figure.png"),
        },
        chart_relationships={},
    )

    result = ImageExtractor().extract_figures(parsed, output_dir=tmp_path / "figures")

    assert [figure.output_filename for figure in result.figures] == ["Figure_1.PNG"]
    assert result.figures[0].caption is None
    assert (tmp_path / "figures" / "Figure_1.PNG").exists()


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


@pytest.mark.skipif(not ANTONIO_DOCX_FIXTURE.exists(), reason="Antonio DOCX fixture is not available")
def test_article_pipeline_accepts_english_docx_without_zip(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )
    result = ArticlePipeline(settings).run(ANTONIO_DOCX_FIXTURE)

    assert result.article is not None
    assert result.article.journal == "mlser"
    assert result.article.language == "en"
    assert result.article.primary_title.startswith("ACTIVE METHODOLOGIES")
    assert result.article.authors[0].email == "antonioabarcaz1@hotmail.com"
    assert len(result.article.references) == 35
    assert result.delivery_dir is not None
    assert result.delivery_dir.name.endswith("-eng")


@pytest.mark.skipif(not BESSY_DOCX_FIXTURE.exists(), reason="Bessy DOCX fixture is not available")
def test_article_pipeline_exports_word_charts_as_png_figures(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )
    result = ArticlePipeline(settings).run(BESSY_DOCX_FIXTURE)

    assert [figure.output_filename for figure in result.article.figures] == [
        "Figure_1.PNG",
        "Figure_2.PNG",
        "Figure_3.PNG",
    ]
    assert result.delivery_dir is not None
    assert all((result.delivery_dir / f"Figure_{number}.PNG").exists() for number in range(1, 4))


@pytest.mark.skipif(not CARBALLIDO_DOCX_FIXTURE.exists(), reason="Carballido DOCX fixture is not available")
def test_article_pipeline_accepts_mlspci_front_matter_docx(tmp_path: Path) -> None:
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )
    result = ArticlePipeline(settings).run(CARBALLIDO_DOCX_FIXTURE)

    assert result.article is not None
    assert result.article.journal == "mlspci"
    assert result.article.language == "en"
    assert result.article.primary_title.startswith("Geodidactic proposal")
    assert [author.email for author in result.article.authors] == [
        "aurigeo33@gmail.com",
        "acazares@upn.mx",
    ]
    assert [figure.output_filename for figure in result.article.figures] == ["Figure_1.PNG", "Figure_2.PNG"]
    assert result.delivery_dir is not None
    assert result.delivery_dir.name == "Aurea Barbara Carballido Perea-eng"
    assert all((result.delivery_dir / f"Figure_{number}.PNG").exists() for number in range(1, 3))
