from __future__ import annotations

import re
from html import escape
from pathlib import Path

from app.models.article import Article, Figure, Reference
from app.models.article import ArticleLanguage
from app.models.journal import JournalConfig
from app.utils.dates import format_short_spanish_date
from app.utils.files import ensure_directory

FIGURE_PLACEHOLDER_PATTERN = re.compile(r"<!--\s*FIGURE:(\d+)\s*-->")


class IntermediateHtmlRenderer:
    """Creates a deterministic HTML document from the domain model for dry runs."""

    def render_to_file(self, article: Article, journal: JournalConfig, output_path: Path) -> Path:
        ensure_directory(output_path.parent)
        output_path.write_text(self.render(article, journal), encoding="utf-8")
        return output_path

    def render(self, article: Article, journal: JournalConfig) -> str:
        title = article.primary_title
        author_html = "\n".join(self._render_author(author) for author in article.authors)
        figures_by_number = {figure.number: figure for figure in article.figures}
        sections_html = "\n".join(
            self._render_section(section.title, section.html_content, figures_by_number, journal)
            for section in article.sections
        )
        references_html = "\n".join(self._render_reference(reference) for reference in article.references)
        citation_html = self._render_citation(article, journal)
        secondary_title = article.title_es if article.language == ArticleLanguage.ENGLISH else article.title_en
        secondary_title_html = self._render_translated_title(secondary_title)
        abstract_blocks_html = self._render_abstract_blocks(article)
        references_title = "References" if article.language == ArticleLanguage.ENGLISH else "Referencias"

        return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <link rel="stylesheet" href="galleys.css">
</head>
<body>
    <div>
        <div>
            <table class="header-table center-text">
                <tbody>
                    <tr>
                        <td class="info">
                            <h1>{escape(journal.name)}</h1>
                            <a target="_blank" href="{escape(journal.url)}">{escape(journal.url)}</a>
                            <p>ISSN: {escape(journal.issn)}</p>
                        </td>
                        <td class="logo-cell">
                            <img class="journal-logo" src="{escape(journal.logo)}" style="width: 200px!important">
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
        {citation_html}
        <div id="article-title">
            <p class="center-text"><b>{escape(title)}</b></p>
        </div>
        <div>
            {author_html}
        </div>
        <p>{self._render_dates(article)}</p>
    </div>

    {abstract_blocks_html}
    <hr>
    {secondary_title_html}
    <hr>
    {sections_html}
    <div>
        <p class="title">{references_title}</p>
        {references_html}
    </div>
</body>
</html>
"""

    def _render_author(self, author) -> str:
        institution = escape(author.institution or "")
        if author.country:
            institution = f"{institution} ({escape(author.country)})"
        email = (
            f'<a target="_blank" href="mailto:{escape(author.email)}">{escape(author.email)}</a>'
            if author.email
            else ""
        )
        orcid = (
            f'<a target="_blank" href="{escape(author.orcid)}">{escape(author.orcid)}</a>'
            if author.orcid
            else ""
        )
        contact = " · ".join(part for part in (email, orcid) if part)
        contact_html = f"<br />{contact}" if contact else ""
        institution_html = f"<br />{institution}" if institution else ""
        return (
            '<p class="center-text">'
            f"<b>{escape(author.full_name)}</b>"
            f"{institution_html}"
            f"{contact_html}"
            "</p>"
        )

    def _render_section(
        self,
        title: str,
        html_content: str,
        figures_by_number: dict[int, Figure],
        journal: JournalConfig,
    ) -> str:
        html_content = self._replace_figure_placeholders(html_content, figures_by_number, journal)
        return f'<div>\n<p class="title">{escape(title)}</p>\n{html_content}\n</div>'

    def _render_figure(self, figure, journal: JournalConfig) -> str:
        caption = escape(figure.caption or f"Figura {figure.number}")
        return (
            '<div class="center-text">'
            f'<img src="{escape(figure.output_filename)}" alt="{caption}" '
            f'style="{escape(journal.image_style.html_style)}">'
            f"<p><i>{caption}</i></p>"
            "</div>"
        )

    def _render_reference(self, reference: Reference) -> str:
        return f'<p id="ref-{reference.number}">[{reference.number}] {escape(reference.raw_text)}</p>'

    def _replace_figure_placeholders(
        self,
        html_content: str,
        figures_by_number: dict[int, Figure],
        journal: JournalConfig,
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            figure = figures_by_number.get(int(match.group(1)))
            if not figure:
                return ""
            return self._render_figure(figure, journal)

        return FIGURE_PLACEHOLDER_PATTERN.sub(replace, html_content)

    def _render_dates(self, article: Article) -> str:
        return (
            f"<b>Fecha de recepción:</b> {format_short_spanish_date(article.received_date)} / "
            f"<b>Fecha de revisión:</b> {format_short_spanish_date(article.reviewed_date)} / "
            f"<b>Fecha de aceptación:</b> {format_short_spanish_date(article.accepted_date)}"
        )

    def _render_citation(self, article: Article, journal: JournalConfig) -> str:
        if not article.doi:
            return ""

        year = article.accepted_date.year if article.accepted_date else ""
        volume_issue = ""
        if article.volume and article.issue:
            volume_issue = f", {escape(article.volume)}({escape(article.issue)})"

        return (
            "<div>"
            '<p class="center-text" style="color: #308BCC;">'
            f"<b>({year}) {escape(_citation_journal_name(journal))}{volume_issue}, "
            f"doi.org/{escape(article.doi)}</b>"
            "</p>"
            "</div>"
        )

    def _render_translated_title(self, title_en: str | None) -> str:
        if not title_en:
            return ""
        return (
            '<div id="article-title">'
            f'<p class="center-text"><b>{escape(title_en)}</b></p>'
            "</div>"
        )

    def _render_abstract_blocks(self, article: Article) -> str:
        if article.language == ArticleLanguage.ENGLISH:
            return "\n".join(
                block for block in (self._render_abstract_en(article), self._render_abstract_es(article)) if block
            )
        return "\n".join(
            block for block in (self._render_abstract_es(article), self._render_abstract_en(article)) if block
        )

    def _render_abstract_es(self, article: Article) -> str:
        if not article.abstract_es and not article.keywords_es:
            return ""
        return (
            "<div>"
            f"<p><strong>Resumen: </strong>{escape(article.abstract_es or '')}</p>"
            f"<p><b>Palabras clave</b>: {escape(', '.join(article.keywords_es))}</p>"
            "</div>"
        )

    def _render_abstract_en(self, article: Article) -> str:
        if not article.abstract_en and not article.keywords_en:
            return ""
        return (
            "<div>"
            f"<p><strong>Abstract: </strong>{escape(article.abstract_en or '')}</p>"
            f"<p><b>Keywords</b>: {escape(', '.join(article.keywords_en))}</p>"
            "</div>"
        )


def _citation_journal_name(journal: JournalConfig) -> str:
    if journal.key == "mlshnr":
        return "MLS-Health & Nutrition Research"
    return journal.name
