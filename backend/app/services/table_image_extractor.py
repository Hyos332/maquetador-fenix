from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.models.article import ArticleTable
from app.services.docx_parser import ParsedDocument, TableBlock
from app.services.section_extractor import MAIN_SECTION_TITLES
from app.utils.files import ensure_directory
from app.utils.strings import clean_word_text, normalize_for_match


@dataclass(frozen=True)
class TableImageExtractionResult:
    tables: list[ArticleTable]
    warnings: list[str] = field(default_factory=list)


class TableImageExtractor:
    def extract_tables(
        self,
        parsed: ParsedDocument,
        output_dir: Path | None = None,
    ) -> TableImageExtractionResult:
        tables: list[ArticleTable] = []
        warnings: list[str] = []
        if output_dir:
            ensure_directory(output_dir)

        inside_article_body = False
        for block_index, block in enumerate(parsed.blocks):
            block_text = _block_text(block)
            normalized = normalize_for_match(block_text.rstrip(":"))
            if normalized in {"referencias", "references"}:
                break
            if normalized in MAIN_SECTION_TITLES:
                inside_article_body = True
                continue
            if not inside_article_body:
                continue

            if not isinstance(block, TableBlock) or not _should_capture_table(block):
                continue

            table_number = len(tables) + 1
            output_filename = f"Table_{table_number}.PNG"
            html_content = _table_to_html(block)
            if output_dir:
                try:
                    self._render_table_png(html_content, output_dir / output_filename)
                except (OSError, PlaywrightError) as exc:
                    warnings.append(f"Could not render {output_filename}: {exc}")
                    continue

            tables.append(
                ArticleTable(
                    number=table_number,
                    html_content=html_content,
                    output_filename=output_filename,
                    block_index=block_index,
                )
            )

        return TableImageExtractionResult(tables=tables, warnings=warnings)

    def _render_table_png(self, html_content: str, output_path: Path) -> None:
        document = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ margin: 0; padding: 16px; background: white; font-family: Arial, sans-serif; }}
table {{ border-collapse: collapse; width: auto; max-width: 980px; font-size: 16px; }}
td {{ border: 1px solid #111; padding: 8px 10px; vertical-align: top; white-space: pre-wrap; }}
</style>
</head>
<body>{html_content}</body>
</html>
"""
        with tempfile.TemporaryDirectory() as temporary_dir:
            html_path = Path(temporary_dir) / "table.html"
            html_path.write_text(document, encoding="utf-8")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(device_scale_factor=2)
                page.goto(html_path.as_uri())
                table = page.locator("table").first
                table.screenshot(path=str(output_path))
                browser.close()


def _should_capture_table(block: TableBlock) -> bool:
    if block.image_relationship_ids or block.chart_relationship_ids:
        return False

    nonempty_cells = [cell for row in block.rows for cell in row if clean_word_text(cell)]
    if not nonempty_cells:
        return False

    max_columns = max((len(row) for row in block.rows), default=0)
    return max_columns > 1 and len(nonempty_cells) >= 2


def _table_to_html(block: TableBlock) -> str:
    rows = []
    for row in block.rows:
        cleaned_cells = [clean_word_text(cell) for cell in row]
        if not any(cleaned_cells):
            continue
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in cleaned_cells)
        rows.append(f"<tr>{cells}</tr>")
    return "<table><tbody>" + "".join(rows) + "</tbody></table>"


def _block_text(block) -> str:
    if isinstance(block, TableBlock):
        return " ".join(cell for row in block.rows for cell in row)
    return getattr(block, "text", "")
