from __future__ import annotations

from html import escape
from pathlib import Path

from app.models.article import Article, Reference
from app.models.journal import JournalConfig
from app.utils.dates import format_short_spanish_date
from app.utils.files import ensure_directory


class IntermediateHtmlRenderer:
    """Creates a deterministic HTML document from the domain model for dry runs."""

    def render_to_file(self, article: Article, journal: JournalConfig, output_path: Path) -> Path:
        ensure_directory(output_path.parent)
        output_path.write_text(self.render(article, journal), encoding="utf-8")
        return output_path

    def render(self, article: Article, journal: JournalConfig) -> str:
        title = article.primary_title
        author_html = "\n".join(self._render_author(author) for author in article.authors)
        figures_html = "\n".join(self._render_figure(figure, journal) for figure in article.figures)
        sections_html = "\n".join(self._render_section(section.title, section.html_content) for section in article.sections)
        references_html = "\n".join(self._render_reference(reference) for reference in article.references)

        return f"""<!doctype html>
<html lang="{escape(article.language.value)}">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="galleys.css">
</head>
<body>
  <header class="journal-header">
    <img class="journal-logo" src="{escape(journal.logo)}" alt="{escape(journal.name)}">
    <p class="journal-name">{escape(journal.name)}</p>
    <p class="journal-meta"><a href="{escape(journal.url)}">{escape(journal.url)}</a> ISSN: {escape(journal.issn)}</p>
  </header>
  <main>
    <article>
      <h1>{escape(title)}</h1>
      <h2>{escape(article.title_en or "")}</h2>
      <section class="authors">
        {author_html}
      </section>
      <section class="manuscript-dates">
        <p>Recibido/Received: {format_short_spanish_date(article.received_date)}</p>
        <p>Revisado/Reviewed: {format_short_spanish_date(article.reviewed_date)}</p>
        <p>Aceptado/Accepted: {format_short_spanish_date(article.accepted_date)}</p>
      </section>
      <section class="abstract abstract-es">
        <h2>Resumen</h2>
        <p>{escape(article.abstract_es or "")}</p>
        <p><strong>Palabras clave:</strong> {escape(", ".join(article.keywords_es))}</p>
      </section>
      <section class="abstract abstract-en">
        <h2>Abstract</h2>
        <p>{escape(article.abstract_en or "")}</p>
        <p><strong>Keywords:</strong> {escape(", ".join(article.keywords_en))}</p>
      </section>
      {sections_html}
      <section class="figures">
        <h2>Figuras y tablas</h2>
        {figures_html}
      </section>
      <section class="references">
        <h2>Referencias</h2>
        <ol>
          {references_html}
        </ol>
      </section>
    </article>
  </main>
</body>
</html>
"""

    def _render_author(self, author) -> str:
        email = f' <a href="mailto:{escape(author.email)}">{escape(author.email)}</a>' if author.email else ""
        orcid = f' <a href="{escape(author.orcid)}">{escape(author.orcid)}</a>' if author.orcid else ""
        institution = f"<span>{escape(author.institution)}</span>" if author.institution else ""
        return f'<p class="author"><strong>{escape(author.full_name)}</strong> {institution}{email}{orcid}</p>'

    def _render_section(self, title: str, html_content: str) -> str:
        return f"<section>\n<h2>{escape(title)}</h2>\n{html_content}\n</section>"

    def _render_figure(self, figure, journal: JournalConfig) -> str:
        caption = escape(figure.caption or f"Figura {figure.number}")
        return (
            "<figure>"
            f'<img src="{escape(figure.output_filename)}" alt="{caption}" '
            f'style="{escape(journal.image_style.html_style)}">'
            f"<figcaption>{caption}</figcaption>"
            "</figure>"
        )

    def _render_reference(self, reference: Reference) -> str:
        return f'<li id="ref-{reference.number}">[{reference.number}] {escape(reference.raw_text)}</li>'
