from __future__ import annotations

from pathlib import Path

from app.services.docx_parser import DocxParser
from app.services.html_renderer import IntermediateHtmlRenderer
from app.services.image_extractor import ImageExtractor
from app.services.journal_config import JournalConfigService
from app.services.metadata_extractor import MetadataExtractor
from app.services.reference_processor import ReferenceProcessor
from app.services.section_extractor import SectionExtractor
from app.services.zip_service import ZipService

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")


def build_alberto_article(tmp_path: Path):
    package = ZipService(tmp_path / "workspaces").extract_article_zip(
        ALBERTO_FIXTURE,
        job_id="alberto",
    )
    parsed = DocxParser().parse(package.primary_docx)
    article = MetadataExtractor().extract(parsed)
    article.references = ReferenceProcessor().extract(parsed)
    article.sections = SectionExtractor().extract(parsed)
    article.figures = ImageExtractor().extract_figures(
        parsed,
        output_dir=tmp_path,
    ).figures

    journal = JournalConfigService().load(article.journal)
    html_path = tmp_path / "intermediate.html"
    IntermediateHtmlRenderer().render_to_file(article, journal, html_path)
    return article, html_path, tmp_path
