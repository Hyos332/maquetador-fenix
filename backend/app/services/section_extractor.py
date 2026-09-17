from __future__ import annotations

from html import escape

from app.models.article import Section
from app.services.docx_parser import ParagraphBlock, ParsedDocument, TableBlock
from app.utils.strings import normalize_for_match

MAIN_SECTION_TITLES = {
    "introduccion": "Introducción",
    "metodo": "Método",
    "resultados": "Resultados",
    "discusion y conclusiones": "Discusión y conclusiones",
    "agradecimientos": "Agradecimientos",
    "conflicto de intereses": "Conflicto de intereses",
}


class SectionExtractor:
    def extract(self, parsed: ParsedDocument) -> list[Section]:
        sections: list[Section] = []
        current_title: str | None = None
        current_html: list[str] = []

        for block in parsed.blocks:
            if isinstance(block, ParagraphBlock):
                normalized = normalize_for_match(block.text.rstrip(":"))
                if normalized == "referencias":
                    break

                if normalized in MAIN_SECTION_TITLES:
                    if current_title:
                        sections.append(Section(title=current_title, html_content="\n".join(current_html)))
                    current_title = MAIN_SECTION_TITLES[normalized]
                    current_html = []
                    continue

                inline_heading = self._split_inline_heading(block.text)
                if inline_heading:
                    title, content = inline_heading
                    if current_title:
                        sections.append(Section(title=current_title, html_content="\n".join(current_html)))
                    current_title = title
                    current_html = [f"<p>{escape(content)}</p>"] if content else []
                    continue

                if current_title and block.text:
                    current_html.append(f"<p>{escape(block.text)}</p>")
            elif isinstance(block, TableBlock) and current_title:
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
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in row)
        rows.append(f"<tr>{cells}</tr>")
    return "<table>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"
