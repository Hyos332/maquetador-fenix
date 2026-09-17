from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from app.config.settings import Settings, settings
from app.models.pipeline import PipelineResult, PipelineStatus
from app.services.delivery_service import DeliveryService
from app.services.docx_parser import DocxParser
from app.services.epub_builder import EpubBuilder
from app.services.html_processor import HtmlProcessor
from app.services.html_renderer import IntermediateHtmlRenderer
from app.services.image_extractor import ImageExtractor
from app.services.journal_config import JournalConfigService
from app.services.metadata_extractor import MetadataExtractor
from app.services.mls_automation import MlsAutomationService
from app.services.reference_processor import ReferenceProcessor
from app.services.section_extractor import SectionExtractor
from app.services.validator import Validator
from app.services.zip_service import ZipService
from app.utils.strings import word_count


class ArticlePipeline:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings
        self.zip_service = ZipService(
            workspaces_dir=self.settings.workspaces_dir,
            max_size_mb=self.settings.max_zip_size_mb,
        )
        self.docx_parser = DocxParser()
        self.metadata_extractor = MetadataExtractor()
        self.section_extractor = SectionExtractor()
        self.reference_processor = ReferenceProcessor()
        self.image_extractor = ImageExtractor()
        self.journal_config_service = JournalConfigService()
        self.html_renderer = IntermediateHtmlRenderer()
        self.html_processor = HtmlProcessor()
        self.epub_builder = EpubBuilder()
        self.validator = Validator()
        self.delivery_service = DeliveryService(self.settings.deliveries_dir)

    def run(
        self,
        source_zip: Path,
        progress: Callable[[PipelineStatus, str], None] | None = None,
        abstract_overrides: dict[str, str] | None = None,
    ) -> PipelineResult:
        self._notify(progress, PipelineStatus.ANALYZING, "Analizando ZIP y DOCX.")
        package = self.zip_service.extract_article_zip(source_zip)
        parsed = self.docx_parser.parse(package.primary_docx)
        article = self.metadata_extractor.extract(parsed)
        self._apply_abstract_overrides(article, abstract_overrides)
        self._notify(progress, PipelineStatus.METADATA_EXTRACTED, "Metadatos extraídos.")

        image_result = self.image_extractor.extract_figures(
            parsed,
            output_dir=package.workspace.generated_dir,
        )
        article.figures = image_result.figures
        article.sections = self.section_extractor.extract(parsed, figures=article.figures)
        article.references = self.reference_processor.extract(parsed)

        warnings = []
        warnings.extend(self.reference_processor.sequence_warnings(article.references))
        warnings.extend(image_result.warnings)
        warnings.extend(self._abstract_warnings(article.abstract_es, "Resumen"))
        warnings.extend(self._abstract_warnings(article.abstract_en, "Abstract"))
        journal = self.journal_config_service.load(article.journal)
        self._copy_input_assets(package.css_files, package.logo_files, package.workspace.generated_dir, journal)

        source_html = package.workspace.generated_dir / "01_intermediate.html"
        final_html = package.workspace.generated_dir / "02_postprocessed.html"
        if self.settings.dry_run:
            self._notify(progress, PipelineStatus.POST_PROCESSING, "Generando HTML intermedio.")
            self.html_renderer.render_to_file(article, journal, source_html)
        else:
            self._notify(progress, PipelineStatus.AUTOMATING_MLS, "Rellenando maquetador MLS.")
            MlsAutomationService(self.settings).generate_html(article, source_html)

        self._notify(progress, PipelineStatus.POST_PROCESSING, "Corrigiendo HTML.")
        html_result = self.html_processor.process_file(source_html, final_html, article, journal)
        warnings.extend(html_result.warnings)

        self._notify(progress, PipelineStatus.VALIDATING, "Validando HTML.")
        article_validation = self.validator.validate_article(article)
        html_validation = self.validator.validate_html(
            final_html,
            article,
            journal,
            assets_dir=package.workspace.generated_dir,
        )
        self._notify(progress, PipelineStatus.BUILDING_EPUB, "Construyendo EPUB.")
        epub_path = package.workspace.generated_dir / "article.epub"
        self.epub_builder.build(
            final_html,
            article,
            journal,
            assets_dir=package.workspace.generated_dir,
            output_path=epub_path,
        )
        epub_validation = self.validator.validate_epub(epub_path, article, journal)
        warnings.extend(article_validation.warnings)
        warnings.extend(html_validation.warnings)
        warnings.extend(epub_validation.warnings)
        errors = [*article_validation.errors, *html_validation.errors, *epub_validation.errors]
        if errors:
            warnings.extend(errors)
        warnings = list(dict.fromkeys(warnings))

        delivery_dir = None
        delivery_zip = None
        if not errors:
            delivery_dir, delivery_zip = self.delivery_service.create_delivery(
                article=article,
                journal=journal,
                html_path=final_html,
                epub_path=epub_path,
                assets_dir=package.workspace.generated_dir,
            )

        status = PipelineStatus.FAILED if errors else PipelineStatus.NEEDS_REVIEW if warnings else PipelineStatus.COMPLETED
        self._notify(progress, status, "Pipeline finalizado.")

        return PipelineResult(
            job_id=package.workspace.job_id,
            status=status,
            workspace=package.workspace,
            article=article,
            warnings=warnings,
            html_path=final_html,
            epub_path=epub_path,
            delivery_dir=delivery_dir,
            delivery_zip=delivery_zip,
        )

    def _abstract_warnings(self, value: str | None, label: str) -> list[str]:
        count = word_count(value)
        if count <= 250:
            return []
        return [f"{label} has {count} words; maximum allowed is 250."]

    def _apply_abstract_overrides(self, article, abstract_overrides: dict[str, str] | None) -> None:
        if not abstract_overrides:
            return
        if "abstract_es" in abstract_overrides:
            article.abstract_es = abstract_overrides["abstract_es"].strip()
        if "abstract_en" in abstract_overrides:
            article.abstract_en = abstract_overrides["abstract_en"].strip()

    def _copy_input_assets(
        self,
        css_files: list[Path],
        logo_files: list[Path],
        output_dir: Path,
        journal,
    ) -> None:
        if css_files:
            shutil.copy2(css_files[0], output_dir / "galleys.css")
        elif not (output_dir / "galleys.css").exists():
            (output_dir / "galleys.css").write_text(
                DEFAULT_GALLEYS_CSS,
                encoding="utf-8",
            )

        if logo_files:
            shutil.copy2(logo_files[0], output_dir / logo_files[0].name)
        elif not (output_dir / journal.logo).exists():
            (output_dir / journal.logo).write_text(_default_logo_svg(journal.name), encoding="utf-8")

    def _notify(
        self,
        progress: Callable[[PipelineStatus, str], None] | None,
        status: PipelineStatus,
        message: str,
    ) -> None:
        if progress:
            progress(status, message)


DEFAULT_GALLEYS_CSS = """body{
    font-family: Arial, sans-serif;
    margin: 2vw;
}
h1,h2,h3,h4{
    font-family: Arial,sans-serif;
    margin:0;
}
table.header-table{
    border-collapse: collapse;
    text-align: center;
}
table.header-table td{
    border: 2px solid #0B8BC9;
    padding:7px;
}
table.header-table td.info{
    width: 90vw;
}
table{
    width: 100%;
    border-collapse:collapse;
}
table td{
    border: 1px solid #d0d0d0;
    padding:.3vw;
}
div#article-title{
    text-transform: uppercase;
    font-size: 24px;
    font-weight: bold;
    text-align: center;
}
.center-text {
    text-align: center;
}
.title {
    font-weight: bold;
    text-align: center;
}
"""


def _default_logo_svg(title: str) -> str:
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="110" viewBox="0 0 320 110">
  <rect width="320" height="110" fill="white"/>
  <text x="160" y="48" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" fill="#555">{escaped_title}</text>
  <text x="160" y="76" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" fill="#d71945">MLS Journals</text>
</svg>
"""
