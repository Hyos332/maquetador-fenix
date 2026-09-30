from __future__ import annotations

from collections.abc import Sequence

from app.services.docx_parser import DocumentBlock, ParagraphBlock, TableBlock
from app.utils.strings import clean_word_text, normalize_for_match


def is_simple_data_table(block: TableBlock) -> bool:
    return _is_simple_data_rows(_cleaned_rows(block))


def collect_split_data_table_blocks(
    blocks: Sequence[DocumentBlock],
    start_index: int,
    blocked_indexes: set[int] | None = None,
) -> tuple[TableBlock, ...]:
    first = blocks[start_index]
    if not isinstance(first, TableBlock) or _has_media(first):
        return ()
    if not _has_table_caption_context(blocks, start_index):
        return ()

    tables: list[TableBlock] = []
    column_count = _column_count(first)
    blocked_indexes = blocked_indexes or set()
    for index in range(start_index, len(blocks)):
        if index in blocked_indexes:
            break

        block = blocks[index]
        if not isinstance(block, TableBlock) or _has_media(block):
            break
        if _column_count(block) != column_count:
            break

        tables.append(block)

    if len(tables) < 2:
        return ()

    rows_by_table = [_cleaned_rows(table) for table in tables]
    if any(len(rows) != 1 for rows in rows_by_table):
        return ()

    rows = [row for table_rows in rows_by_table for row in table_rows]
    if not _is_simple_data_rows(rows):
        return ()

    return tuple(tables)


def merge_table_blocks(tables: Sequence[TableBlock]) -> TableBlock:
    first = tables[0]
    return TableBlock(
        index=first.index,
        rows=tuple(row for table in tables for row in table.rows),
    )


def _has_media(block: TableBlock) -> bool:
    return bool(block.image_relationship_ids or block.chart_relationship_ids)


def _column_count(block: TableBlock) -> int:
    cleaned_rows = _cleaned_rows(block)
    return len(cleaned_rows[0]) if cleaned_rows else 0


def _has_table_caption_context(blocks: Sequence[DocumentBlock], start_index: int) -> bool:
    for index in range(max(0, start_index - 4), start_index):
        block = blocks[index]
        if not isinstance(block, ParagraphBlock):
            continue
        normalized = normalize_for_match(clean_word_text(block.text).rstrip(":"))
        if normalized.startswith(("tabla ", "table ")):
            return True
    return False


def _cleaned_rows(block: TableBlock) -> list[list[str]]:
    return [
        [clean_word_text(cell) for cell in row]
        for row in block.rows
        if any(clean_word_text(cell) for cell in row)
    ]


def _is_simple_data_rows(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False

    column_count = len(rows[0])
    if column_count < 2 or column_count > 6:
        return False
    if any(len(row) != column_count for row in rows):
        return False
    if any(not cell for row in rows for cell in row):
        return False

    first_row = rows[0]
    if any(len(cell) > 120 for cell in first_row):
        return False

    uppercase_header = all(
        any(character.isalpha() for character in cell) and cell.upper() == cell
        for cell in first_row
    )
    short_header = all(len(cell.split()) <= 5 for cell in first_row)
    if not uppercase_header and not short_header:
        return False

    return all(len(cell) <= 1200 for row in rows for cell in row)
