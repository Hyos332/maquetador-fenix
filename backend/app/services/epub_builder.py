from __future__ import annotations

import mimetypes
import zipfile
from html import escape
from pathlib import Path

from lxml import etree, html

from app.models.article import Article
from app.models.journal import JournalConfig
from app.utils.dates import format_epub_date
from app.utils.files import ensure_directory

EPUB_DIR = "EPUB"
META_INF_DIR = "META-INF"


class EpubBuilder:
    def build(
        self,
        html_path: Path,
        article: Article,
        journal: JournalConfig,
        assets_dir: Path,
        output_path: Path,
    ) -> Path:
        ensure_directory(output_path.parent)
        article_xhtml = self._build_article_xhtml(html_path, article)
        nav_xhtml = self._build_nav_xhtml(article)
        content_opf = self._build_content_opf(article, journal, assets_dir)
        container_xml = self._build_container_xml()

        with zipfile.ZipFile(output_path, "w") as archive:
            archive.writestr(
                zipfile.ZipInfo("mimetype"),
                "application/epub+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            archive.writestr(f"{META_INF_DIR}/container.xml", container_xml)
            archive.writestr(f"{EPUB_DIR}/article.xhtml", article_xhtml)
            archive.writestr(f"{EPUB_DIR}/nav.xhtml", nav_xhtml)
            archive.writestr(f"{EPUB_DIR}/content.opf", content_opf)

            self._write_asset_if_exists(archive, assets_dir / "galleys.css", f"{EPUB_DIR}/galleys.css")
            self._write_asset_if_exists(archive, assets_dir / journal.logo, f"{EPUB_DIR}/{journal.logo}")
            for figure in article.figures:
                self._write_asset_if_exists(
                    archive,
                    assets_dir / figure.output_filename,
                    f"{EPUB_DIR}/{figure.output_filename}",
                )
            for table in article.tables:
                if table.output_filename:
                    self._write_asset_if_exists(
                        archive,
                        assets_dir / table.output_filename,
                        f"{EPUB_DIR}/{table.output_filename}",
                    )

        return output_path

    def _build_article_xhtml(self, html_path: Path, article: Article) -> str:
        root = html.fromstring(html_path.read_text(encoding="utf-8"))
        body = root.find("body")
        body_html = ""
        if body is not None:
            body_html = "".join(
                etree.tostring(child, encoding="unicode", method="xml")
                for child in body
            )

        return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="{escape(article.language.value)}" xml:lang="{escape(article.language.value)}">
<head>
  <title>{escape(article.primary_title)}</title>
  <link rel="stylesheet" type="text/css" href="galleys.css" />
</head>
<body>
{body_html}
</body>
</html>
"""

    def _build_nav_xhtml(self, article: Article) -> str:
        section_links = "\n".join(
            f'<li><a href="article.xhtml">{escape(section.title)}</a></li>'
            for section in article.sections
        )
        return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{escape(article.language.value)}">
<head><title>Navigation</title></head>
<body>
<nav epub:type="toc" id="toc">
  <h1>Contenido</h1>
  <ol>
    <li><a href="article.xhtml">{escape(article.primary_title)}</a></li>
    {section_links}
  </ol>
</nav>
</body>
</html>
"""

    def _build_content_opf(self, article: Article, journal: JournalConfig, assets_dir: Path) -> str:
        creators = "\n".join(
            f"    <dc:creator>{escape(author.full_name)}</dc:creator>"
            for author in article.authors
        )
        figure_items = "\n".join(
            f'    <item id="figure-{figure.number}" href="{escape(figure.output_filename)}" media-type="image/png" />'
            for figure in article.figures
        )
        table_items = "\n".join(
            f'    <item id="table-{table.number}" href="{escape(table.output_filename)}" media-type="image/png" />'
            for table in article.tables
            if table.output_filename
        )
        logo_item = ""
        if (assets_dir / journal.logo).exists():
            logo_media_type = mimetypes.guess_type(journal.logo)[0] or "image/svg+xml"
            logo_item = f'    <item id="journal-logo" href="{escape(journal.logo)}" media-type="{logo_media_type}" />'

        return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{escape(article.doi or "")}</dc:identifier>
    <dc:title>{escape(article.primary_title)}</dc:title>
{creators}
    <dc:language>{escape(article.language.value)}</dc:language>
    <dc:publisher>{escape(journal.publisher)}</dc:publisher>
    <dc:date>{escape(format_epub_date(article.accepted_date))}</dc:date>
  </metadata>
  <manifest>
    <item id="article" href="article.xhtml" media-type="application/xhtml+xml" />
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
    <item id="css" href="galleys.css" media-type="text/css" />
{logo_item}
{figure_items}
{table_items}
  </manifest>
  <spine>
    <itemref idref="article" />
  </spine>
</package>
"""

    def _build_container_xml(self) -> str:
        return """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
"""

    def _write_asset_if_exists(self, archive: zipfile.ZipFile, source: Path, archive_name: str) -> None:
        if source.exists():
            archive.write(source, archive_name)
