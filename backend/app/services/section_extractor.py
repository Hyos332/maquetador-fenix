from __future__ import annotations

from html import escape

from app.models.article import ArticleTable, Figure, Section
from app.services.docx_parser import ParagraphBlock, ParsedDocument, TableBlock
from app.utils.strings import clean_word_text, normalize_for_match

MAIN_SECTION_TITLES = {
    "introduccion": "Introducción",
    "introduction": "Introduction",
    "metodo": "Método",
    "method": "Method",
    "methods": "Methods",
    "resultados": "Resultados",
    "results": "Results",
    "discusion y conclusiones": "Discusión y conclusiones",
    "discussion and conclusions": "Discussion and Conclusions",
    "agradecimientos": "Agradecimientos",
    "acknowledgements": "Acknowledgements",
    "acknowledgments": "Acknowledgments",
    "conflicto de intereses": "Conflicto de intereses",
    "conflict of interest": "Conflict of Interest",
    "conflicts of interest": "Conflicts of Interest",
}


class SectionExtractor:
    def extract(
        self,
        parsed: ParsedDocument,
        figures: list[Figure] | None = None,
        tables: list[ArticleTable] | None = None,
    ) -> list[Section]:
        sections: list[Section] = []
        current_title: str | None = None
        current_html: list[str] = []
        figures_by_block = _figures_by_block_index(figures or [])
        tables_by_block = _tables_by_block_index(tables or [])
        caption_block_indexes = {
            figure.caption_block_index
            for figure in figures or []
            if figure.caption_block_index is not None
        }
        grouped_caption_block_indexes = {
            figure.caption_block_index
            for figure in figures or []
            if figure.group_id and figure.caption_block_index is not None
        }
        figure_subtitle_block_indexes = _figure_subtitle_block_indexes(parsed, figures or [])

        for block_index, block in enumerate(parsed.blocks):
            if current_title and block_index in figures_by_block:
                if isinstance(block, TableBlock):
                    before_table_text, after_table_text = _media_table_text(block)
                    current_html.extend(before_table_text)
                current_html.extend(
                    f"<!-- FIGURE:{figure.number} -->"
                    for figure in figures_by_block[block_index]
                )
                if isinstance(block, TableBlock):
                    current_html.extend(after_table_text)
                if isinstance(block, ParagraphBlock) or _block_has_media(block):
                    continue

            if isinstance(block, ParagraphBlock):
                text = clean_word_text(block.text)
                normalized = normalize_for_match(text.rstrip(":"))
                if normalized in {"referencias", "references"}:
                    break

                if block_index in caption_block_indexes and block_index not in grouped_caption_block_indexes:
                    continue

                if normalized in MAIN_SECTION_TITLES:
                    if current_title:
                        sections.append(Section(title=current_title, html_content="\n".join(current_html)))
                    current_title = MAIN_SECTION_TITLES[normalized]
                    current_html = []
                    continue

                inline_heading = self._split_inline_heading(text)
                if inline_heading:
                    title, content = inline_heading
                    if current_title:
                        sections.append(Section(title=current_title, html_content="\n".join(current_html)))
                    current_title = title
                    current_html = [f"<p>{escape(content)}</p>"] if content else []
                    continue

                if current_title and text:
                    if block_index in grouped_caption_block_indexes:
                        current_html.append(f'<p class="figure-caption"><i>{escape(text)}</i></p>')
                    elif block_index in figure_subtitle_block_indexes:
                        current_html.append(f'<p class="figure-subtitle"><i>{escape(text)}</i></p>')
                    else:
                        current_html.append(f"<p>{escape(text)}</p>")
            elif isinstance(block, TableBlock) and current_title and block.rows:
                if block_index in tables_by_block:
                    current_html.append(f"<!-- TABLE:{tables_by_block[block_index].number} -->")
                    continue
                current_html.append(_table_to_html(block))

        if current_title:
            sections.append(Section(title=current_title, html_content="\n".join(current_html)))

        return sections

    def _split_inline_heading(self, text: str) -> tuple[str, str] | None:
        if ":" not in text:
            return None

        raw_heading, content = text.split(":", 1)
        normalized = normalize_for_match(raw_heading)
        if normalized not in MAIN_SECTION_TITLES:
            return None

        return MAIN_SECTION_TITLES[normalized], content.strip()


def _table_to_html(block: TableBlock) -> str:
    rows = []
    for row in block.rows:
        cleaned_cells = [clean_word_text(cell) for cell in row]
        if not any(cleaned_cells):
            continue
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in cleaned_cells)
        rows.append(f"<tr>{cells}</tr>")
    if not rows:
        return ""
    return "<table>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"


def _figures_by_block_index(figures: list[Figure]) -> dict[int, list[Figure]]:
    figures_by_block: dict[int, list[Figure]] = {}
    for figure in figures:
        if figure.block_index is None:
            continue
        figures_by_block.setdefault(figure.block_index, []).append(figure)
    return figures_by_block


def _tables_by_block_index(tables: list[ArticleTable]) -> dict[int, ArticleTable]:
    tables_by_block: dict[int, ArticleTable] = {}
    for table in tables:
        if table.block_index is None:
            continue
        tables_by_block[table.block_index] = table
    return tables_by_block


def _block_has_media(block) -> bool:
    return bool(block.image_relationship_ids or block.chart_relationship_ids)


def _figure_subtitle_block_indexes(parsed: ParsedDocument, figures: list[Figure]) -> set[int]:
    indexes: set[int] = set()
    for figure in figures:
        caption_index = figure.caption_block_index
        figure_index = figure.block_index
        if caption_index is None or figure_index is None:
            continue
        if figure_index <= caption_index + 1:
            continue

        for block_index in range(caption_index + 1, figure_index):
            block = parsed.blocks[block_index]
            if not isinstance(block, ParagraphBlock):
                continue
            text = clean_word_text(block.text)
            if not text or _looks_like_caption_or_note(text):
                continue
            indexes.add(block_index)
    return indexes


def _looks_like_caption_or_note(text: str) -> bool:
    normalized = normalize_for_match(text.rstrip(":"))
    return normalized.startswith(
        (
            "figura ",
            "figure ",
            "tabla ",
            "table ",
            "fig. ",
            "nota",
            "note",
        )
    )


def _media_table_text(block: TableBlock) -> tuple[list[str], list[str]]:
    if not block.image_cell_positions and not block.chart_relationship_ids:
        return [], []

    media_rows = {row for row, _ in block.image_cell_positions}
    if not media_rows:
        return [], []

    first_media_row = min(media_rows)
    last_media_row = max(media_rows)
    before: list[str] = []
    after: list[str] = []

    for row_index, row in enumerate(block.rows):
        if row_index in media_rows:
            continue

        text = clean_word_text(" ".join(cell for cell in row if clean_word_text(cell)))
        if not text:
            continue

        html_text = f'<p class="figure-subtitle"><i>{escape(text)}</i></p>'
        if row_index < first_media_row:
            before.append(html_text)
        elif row_index > last_media_row:
            after.append(html_text)
        else:
            after.append(html_text)

    return before, after
