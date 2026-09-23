from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.models.article import ArticleTable
from app.services.docx_parser import ParagraphBlock, ParsedDocument, TableBlock
from app.services.section_extractor import MAIN_SECTION_TITLES
from app.utils.files import ensure_directory
from app.utils.strings import clean_word_text, normalize_for_match


@dataclass(frozen=True)
class TableImageExtractionResult:
    tables: list[ArticleTable]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _TableCandidate:
    number: int
    block_index: int
    output_filename: str
    html_content: str
    signature: str


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

        candidates: list[_TableCandidate] = []
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

            if not isinstance(block, TableBlock):
                continue

            force_capture = _follows_figure_or_table_caption(parsed, block_index)
            if not _should_capture_table(block, force_capture=force_capture):
                continue

            table_number = len(candidates) + 1
            output_filename = f"Table_{table_number}.PNG"
            candidates.append(
                _TableCandidate(
                    number=table_number,
                    block_index=block_index,
                    output_filename=output_filename,
                    html_content=_table_to_html(block),
                    signature=_table_signature(block),
                )
            )

        captured_numbers: set[int] | None = None
        if output_dir and candidates:
            try:
                captured_numbers = self._capture_original_tables(parsed.path, candidates, output_dir, warnings)
            except (OSError, RuntimeError, subprocess.SubprocessError, PlaywrightError) as exc:
                warnings.append(f"Could not capture original DOCX tables: {exc}")
                return TableImageExtractionResult(tables=[], warnings=warnings)

        for candidate in candidates:
            if captured_numbers is not None and candidate.number not in captured_numbers:
                continue
            tables.append(
                ArticleTable(
                    number=candidate.number,
                    html_content=candidate.html_content,
                    output_filename=candidate.output_filename,
                    block_index=candidate.block_index,
                )
            )

        return TableImageExtractionResult(tables=tables, warnings=warnings)

    def _capture_original_tables(
        self,
        docx_path: Path,
        candidates: list[_TableCandidate],
        output_dir: Path,
        warnings: list[str],
    ) -> set[int]:
        captured_numbers: set[int] = set()
        with tempfile.TemporaryDirectory() as temporary_dir:
            converted_html = self._convert_docx_to_html(docx_path, Path(temporary_dir))
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(device_scale_factor=2, viewport={"width": 1400, "height": 1200})
                    page.goto(converted_html.as_uri(), wait_until="load")
                    page.add_style_tag(
                        content="body { background: white !important; padding-left: 120px !important; }"
                    )
                    tables = page.locator("table")
                    used_indexes: set[int] = set()
                    for candidate in candidates:
                        table_index = self._find_rendered_table_index(tables, candidate.signature, used_indexes)
                        if table_index is None:
                            warnings.append(f"Could not match original DOCX table for {candidate.output_filename}.")
                            continue

                        used_indexes.add(table_index)
                        locator = tables.nth(table_index)
                        locator.scroll_into_view_if_needed()
                        self._screenshot_with_padding(page, locator, output_dir / candidate.output_filename)
                        captured_numbers.add(candidate.number)
                finally:
                    browser.close()
        return captured_numbers

    def _screenshot_with_padding(self, page, locator, output_path: Path) -> None:
        box = locator.bounding_box()
        if box is None:
            locator.screenshot(path=str(output_path))
            return

        padding_x = 90
        padding_bottom = 12
        clip = {
            "x": max(box["x"] - padding_x, 0),
            "y": box["y"],
            "width": box["width"] + padding_x * 2,
            "height": box["height"] + padding_bottom,
        }
        page.screenshot(path=str(output_path), clip=clip)

    def _convert_docx_to_html(self, docx_path: Path, output_dir: Path) -> Path:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "html",
                "--outdir",
                str(output_dir),
                str(docx_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "unknown LibreOffice error").strip()
            raise RuntimeError(message)

        html_files = sorted(output_dir.glob("*.html"))
        if not html_files:
            raise RuntimeError("LibreOffice did not produce HTML")
        return html_files[0]

    def _find_rendered_table_index(self, tables, signature: str, used_indexes: set[int]) -> int | None:
        count = tables.count()
        for index in range(count):
            if index in used_indexes:
                continue
            rendered_text = tables.nth(index).evaluate(
                '(element) => element.innerText || element.textContent || ""',
            )
            normalized = normalize_for_match(rendered_text)
            if signature and signature in normalized:
                return index
        return None


def _should_capture_table(block: TableBlock, force_capture: bool = False) -> bool:
    if block.image_relationship_ids or block.chart_relationship_ids:
        return False

    nonempty_cells = [cell for row in block.rows for cell in row if clean_word_text(cell)]
    if not nonempty_cells:
        return False

    if force_capture:
        return True

    max_columns = max((len(row) for row in block.rows), default=0)
    return max_columns > 1 and len(nonempty_cells) >= 2


def _follows_figure_or_table_caption(parsed: ParsedDocument, block_index: int) -> bool:
    for previous_index in range(max(0, block_index - 3), block_index):
        block = parsed.blocks[previous_index]
        if not isinstance(block, ParagraphBlock):
            continue
        normalized = normalize_for_match(clean_word_text(block.text).rstrip(":"))
        if normalized.startswith(("figura ", "figure ", "tabla ", "table ")):
            return True
    return False


def _table_to_html(block: TableBlock) -> str:
    rows = []
    for row in block.rows:
        cleaned_cells = [clean_word_text(cell) for cell in row]
        if not any(cleaned_cells):
            continue
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in cleaned_cells)
        rows.append(f"<tr>{cells}</tr>")
    return "<table><tbody>" + "".join(rows) + "</tbody></table>"


def _table_signature(block: TableBlock) -> str:
    for row in block.rows:
        for cell in row:
            text = clean_word_text(cell.replace("|", " "))
            if len(text) >= 12:
                return normalize_for_match(text[:80])
    return normalize_for_match(_block_text(block).replace("|", " ")[:80])


def _block_text(block) -> str:
    if isinstance(block, TableBlock):
        return " ".join(cell for row in block.rows for cell in row)
    return getattr(block, "text", "")
