from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from lxml import etree, html

from app.models.article import Article
from app.models.journal import JournalConfig
from app.utils.dates import format_epub_date
from app.utils.dates import format_short_spanish_date
from app.utils.strings import word_count


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class Validator:
    def validate_article(self, article: Article) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not article.primary_title:
            errors.append("Article title is empty.")
        if not article.authors:
            errors.append("Article has no authors.")
        if not article.doi:
            errors.append("Article DOI is missing.")
        if not article.accepted_date:
            errors.append("Accepted date is missing.")

        for label, abstract in (("Resumen", article.abstract_es), ("Abstract", article.abstract_en)):
            count = word_count(abstract)
            if count > 250:
                warnings.append(f"{label} has {count} words; maximum allowed is 250.")

        return ValidationResult(errors=errors, warnings=warnings)

    def validate_html(
        self,
        html_path: Path,
        article: Article,
        journal: JournalConfig,
        assets_dir: Path | None = None,
    ) -> ValidationResult:
        root = html.fromstring(html_path.read_text(encoding="utf-8"))
        text = _normalize(root.text_content())
        errors: list[str] = []
        warnings: list[str] = []

        required_texts = [
            article.primary_title,
            *(author.full_name for author in article.authors),
            *(author.email for author in article.authors if author.email),
            *(author.orcid for author in article.authors if author.orcid),
            format_short_spanish_date(article.received_date),
            format_short_spanish_date(article.reviewed_date),
            format_short_spanish_date(article.accepted_date),
            journal.name,
            journal.issn,
        ]

        for value in required_texts:
            if value and _normalize(value) not in text:
                errors.append(f"Required text not found in HTML: {value}")

        forbidden = ["como citar este artículo", "mundet", "peña muñoz", "10.29314/mlser"]
        for value in forbidden:
            if value in text:
                errors.append(f"Forbidden generic citation content found: {value}")

        if root.xpath("//img[starts-with(@src, 'data:image/')]"):
            errors.append("HTML contains base64 images.")

        for image in root.xpath("//img[@src]"):
            source = Path(image.get("src", "")).name
            if not source.lower().startswith("figure_"):
                continue
            if image.get("style") != journal.image_style.html_style:
                errors.append(f"Figure image does not have required style: {source}")
            if assets_dir and not (assets_dir / source).exists():
                errors.append(f"Figure file referenced by HTML does not exist: {source}")

        if root.xpath("//link[contains(@href, 'http://') or contains(@href, 'https://')]"):
            errors.append("HTML still references remote CSS.")

        return ValidationResult(errors=errors, warnings=warnings)

    def validate_epub(self, epub_path: Path, article: Article, journal: JournalConfig) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not epub_path.exists():
            return ValidationResult(errors=[f"EPUB file does not exist: {epub_path}"])

        with ZipFile(epub_path) as archive:
            infos = archive.infolist()
            names = archive.namelist()

            if not names or names[0] != "mimetype":
                errors.append("EPUB mimetype must be the first ZIP entry.")
            elif infos[0].compress_type != ZIP_STORED:
                errors.append("EPUB mimetype must be stored without compression.")
            elif archive.read("mimetype") != b"application/epub+zip":
                errors.append("EPUB mimetype content is invalid.")

            required = {
                "META-INF/container.xml",
                "EPUB/content.opf",
                "EPUB/nav.xhtml",
                "EPUB/article.xhtml",
                "EPUB/galleys.css",
            }
            missing = sorted(required - set(names))
            if missing:
                errors.append(f"EPUB missing required files: {missing}")

            for figure in article.figures:
                figure_path = f"EPUB/{figure.output_filename}"
                if figure_path not in names:
                    errors.append(f"EPUB missing figure: {figure_path}")

            if f"EPUB/{journal.logo}" not in names:
                warnings.append(f"EPUB missing journal logo: {journal.logo}")

            if "EPUB/content.opf" in names:
                self._validate_opf(archive.read("EPUB/content.opf"), article, journal, errors)
            if "EPUB/article.xhtml" in names:
                self._validate_xml(archive.read("EPUB/article.xhtml"), "article.xhtml", errors)
            if "EPUB/nav.xhtml" in names:
                self._validate_xml(archive.read("EPUB/nav.xhtml"), "nav.xhtml", errors)

        return ValidationResult(errors=errors, warnings=warnings)

    def _validate_opf(
        self,
        content: bytes,
        article: Article,
        journal: JournalConfig,
        errors: list[str],
    ) -> None:
        try:
            root = etree.fromstring(content)
        except etree.XMLSyntaxError as exc:
            errors.append(f"content.opf is not valid XML: {exc}")
            return

        text = _normalize(" ".join(root.xpath(".//text()")))
        required = [
            article.primary_title,
            article.doi,
            article.language.value,
            journal.publisher,
            format_epub_date(article.accepted_date),
            *(author.full_name for author in article.authors),
        ]
        for value in required:
            if value and _normalize(value) not in text:
                errors.append(f"Required EPUB metadata not found: {value}")

    def _validate_xml(self, content: bytes, name: str, errors: list[str]) -> None:
        try:
            etree.fromstring(content)
        except etree.XMLSyntaxError as exc:
            errors.append(f"{name} is not valid XML: {exc}")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.casefold().split())
