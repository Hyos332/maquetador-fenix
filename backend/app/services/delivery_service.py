from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from app.models.article import Article, ArticleLanguage
from app.models.journal import JournalConfig
from app.utils.files import ensure_directory, sanitize_filename


class DeliveryService:
    def __init__(self, deliveries_dir: Path) -> None:
        self.deliveries_dir = deliveries_dir

    def create_delivery(
        self,
        article: Article,
        journal: JournalConfig,
        html_path: Path,
        epub_path: Path,
        assets_dir: Path,
        source_documents: list[Path] | None = None,
    ) -> tuple[Path, Path]:
        author_name = article.authors[0].full_name if article.authors else "Articulo"
        author_dir_name = sanitize_filename(author_name, "Articulo")
        file_stem = author_dir_name.replace(" ", "_")
        language_suffix = "eng" if article.language == ArticleLanguage.ENGLISH else "esp"

        author_dir = ensure_directory(self.deliveries_dir / author_dir_name)
        delivery_dir = ensure_directory(author_dir / f"{author_dir_name}-{language_suffix}")

        delivery_html = delivery_dir / f"{file_stem}_{language_suffix}.html"
        delivery_epub = delivery_dir / f"{file_stem}_{language_suffix}.epub"
        shutil.copy2(html_path, delivery_html)
        shutil.copy2(epub_path, delivery_epub)
        for source_document in source_documents or []:
            self._copy_if_exists(source_document, delivery_dir / source_document.name)

        self._copy_if_exists(assets_dir / "galleys.css", delivery_dir / "galleys.css")
        self._copy_if_exists(assets_dir / journal.logo, delivery_dir / journal.logo)
        for figure in article.figures:
            self._copy_if_exists(
                assets_dir / figure.output_filename,
                delivery_dir / figure.output_filename,
            )

        delivery_zip = author_dir / f"{file_stem}_{language_suffix}.zip"
        self._zip_delivery(delivery_dir, delivery_zip)
        return delivery_dir, delivery_zip

    def _copy_if_exists(self, source: Path, destination: Path) -> None:
        if source.exists():
            shutil.copy2(source, destination)

    def _zip_delivery(self, delivery_dir: Path, delivery_zip: Path) -> None:
        with zipfile.ZipFile(delivery_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(delivery_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(delivery_dir.name) / path.relative_to(delivery_dir))
