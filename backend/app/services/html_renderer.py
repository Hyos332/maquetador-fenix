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
TABLE_PLACEHOLDER_PATTERN = re.compile(r"<!--\s*TABLE:(\d+)\s*-->")


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
        figure_groups = _figure_groups(article.figures)
        tables_by_number = {table.number: table for table in article.tables}
        rendered_groups: set[str] = set()
        sections_html = "\n".join(
            self._render_section(
                section.title,
                section.html_content,
                figures_by_number,
                figure_groups,
                tables_by_number,
                rendered_groups,
                journal,
            )
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
        figure_groups: dict[str, list[Figure]],
        tables_by_number,
        rendered_groups: set[str],
        journal: JournalConfig,
    ) -> str:
        html_content = self._replace_figure_placeholders(
            html_content,
            figures_by_number,
            figure_groups,
            rendered_groups,
            journal,
        )
        html_content = self._replace_table_placeholders(html_content, tables_by_number)
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

    def _render_figure_group(self, figures: list[Figure]) -> str:
        sorted_figures = sorted(
            figures,
            key=lambda figure: (
                figure.group_row if figure.group_row is not None else 0,
                figure.group_col if figure.group_col is not None else 0,
                figure.number,
            ),
        )
        rows: dict[int, dict[int, Figure]] = {}
        for figure in sorted_figures:
            row = figure.group_row if figure.group_row is not None else 0
            col = figure.group_col if figure.group_col is not None else len(rows.get(row, {}))
            rows.setdefault(row, {})[col] = figure

        max_col = max((col for row in rows.values() for col in row), default=0)
        table_rows = []
        for row_index in sorted(rows):
            cells = []
            for col_index in range(max_col + 1):
                figure = rows[row_index].get(col_index)
                if figure is None:
                    cells.append('<td style="border: 1px solid #9ca3af; padding: 6px;"></td>')
                    continue

                caption = _subcaption(figure)
                caption_html = (
                    f'<p style="margin: 0 0 5px; font-size: 12px; font-weight: 700;">{escape(caption)}</p>'
                    if caption
                    else ""
                )
                alt = escape(figure.caption or figure.output_filename)
                cells.append(
                    '<td style="border: 1px solid #9ca3af; padding: 6px; text-align: center; vertical-align: top;">'
                    f"{caption_html}"
                    f'<img src="{escape(figure.output_filename)}" alt="{alt}" '
                    'style="max-width: 100%; height: auto;">'
                    "</td>"
                )
            table_rows.append("<tr>" + "".join(cells) + "</tr>")

        return (
            '<div class="center-text">'
            '<table class="figure-grid" '
            'style="width: auto; max-width: 900px; margin: 12px auto; border-collapse: collapse; table-layout: fixed;">'
            "<tbody>"
            + "".join(table_rows)
            + "</tbody></table>"
            + "</div>"
        )

    def _render_reference(self, reference: Reference) -> str:
        return f'<p id="ref-{reference.number}">[{reference.number}] {escape(reference.raw_text)}</p>'

    def _replace_figure_placeholders(
        self,
        html_content: str,
        figures_by_number: dict[int, Figure],
        figure_groups: dict[str, list[Figure]],
        rendered_groups: set[str],
        journal: JournalConfig,
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            figure = figures_by_number.get(int(match.group(1)))
            if not figure:
                return ""
            if figure.group_id:
                if figure.group_id in rendered_groups:
                    return ""
                rendered_groups.add(figure.group_id)
                return self._render_figure_group(figure_groups.get(figure.group_id, [figure]))
            return self._render_figure(figure, journal)

        return FIGURE_PLACEHOLDER_PATTERN.sub(replace, html_content)

    def _replace_table_placeholders(self, html_content: str, tables_by_number) -> str:
        def replace(match: re.Match[str]) -> str:
            table = tables_by_number.get(int(match.group(1)))
            if not table or not table.output_filename:
                return ""
            alt = escape(table.caption or f"Tabla {table.number}")
            return (
                '<div class="center-text table-image">'
                f'<img src="{escape(table.output_filename)}" alt="{alt}" '
                'style="max-width: 100%; height: auto;">'
                "</div>"
            )

        return TABLE_PLACEHOLDER_PATTERN.sub(replace, html_content)

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


def _figure_groups(figures: list[Figure]) -> dict[str, list[Figure]]:
    groups: dict[str, list[Figure]] = {}
    for figure in figures:
        if not figure.group_id:
            continue
        groups.setdefault(figure.group_id, []).append(figure)
    return groups


def _group_caption(figures: list[Figure]) -> str | None:
    for figure in figures:
        if not figure.caption:
            continue
        first_part = figure.caption.split(".", 1)[0].strip()
        if first_part.casefold().startswith(("figura ", "figure ")):
            return first_part
    return None


def _subcaption(figure: Figure) -> str | None:
    if not figure.caption:
        return None
    group_caption = _group_caption([figure])
    if group_caption and figure.caption.startswith(group_caption):
        return figure.caption[len(group_caption) :].lstrip(".:; ").strip() or None
    return figure.caption
