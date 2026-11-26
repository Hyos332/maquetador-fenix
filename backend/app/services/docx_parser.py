from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

from lxml import etree

from app.services.docx_formatting import StyleResolver, paragraph_alignment, paragraph_inline_html
from app.utils.strings import clean_word_text

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"

NS = {
    "w": WORD_NS,
    "pr": REL_NS,
    "r": OFFICE_REL_NS,
    "a": DRAWING_NS,
    "c": CHART_NS,
}


@dataclass(frozen=True)
class ImageRelationship:
    relationship_id: str
    target: str
    package_path: str


@dataclass(frozen=True)
class ChartRelationship:
    relationship_id: str
    target: str
    package_path: str


@dataclass(frozen=True)
class ParagraphBlock:
    index: int
    text: str
    image_relationship_ids: tuple[str, ...] = ()
    chart_relationship_ids: tuple[str, ...] = ()
    html: str = ""


@dataclass(frozen=True)
class TableCell:
    text: str
    html: str
    colspan: int = 1
    rowspan: int = 1
    align: str = ""


@dataclass(frozen=True)
class TableBlock:
    index: int
    rows: tuple[tuple[str, ...], ...]
    image_relationship_ids: tuple[str, ...] = ()
    image_cell_positions: tuple[tuple[int, int], ...] = ()
    chart_relationship_ids: tuple[str, ...] = ()
    cells: tuple[tuple[TableCell, ...], ...] = ()
    has_nested_table: bool = False


DocumentBlock = ParagraphBlock | TableBlock


@dataclass(frozen=True)
class ParsedDocument:
    path: Path
    blocks: tuple[DocumentBlock, ...]
    image_relationships: dict[str, ImageRelationship]
    chart_relationships: dict[str, ChartRelationship]

    @property
    def full_text(self) -> str:
        parts: list[str] = []
        for block in self.blocks:
            if isinstance(block, ParagraphBlock):
                parts.append(block.text)
            else:
                parts.extend(cell for row in block.rows for cell in row)
        return "\n".join(part for part in parts if part)


class DocxParser:
    """OOXML parser that preserves the order of body blocks."""

    def parse(self, docx_path: Path) -> ParsedDocument:
        docx_path = docx_path.expanduser().resolve()
        with ZipFile(docx_path) as archive:
            document_root = etree.fromstring(archive.read("word/document.xml"))
            relationships = self._read_image_relationships(archive)
            chart_relationships = self._read_chart_relationships(archive)
            resolver = StyleResolver.from_archive(archive)
            body = document_root.find("w:body", NS)
            if body is None:
                return ParsedDocument(
                    path=docx_path,
                    blocks=(),
                    image_relationships=relationships,
                    chart_relationships=chart_relationships,
                )

            blocks = tuple(self._parse_body(body, resolver))
            return ParsedDocument(
                path=docx_path,
                blocks=blocks,
                image_relationships=relationships,
                chart_relationships=chart_relationships,
            )

    def _read_image_relationships(self, archive: ZipFile) -> dict[str, ImageRelationship]:
        rels_root = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
        relationships: dict[str, ImageRelationship] = {}

        for rel in rels_root.xpath("./pr:Relationship", namespaces=NS):
            rel_type = rel.get("Type", "")
            if not rel_type.endswith("/image"):
                continue

            relationship_id = rel.get("Id")
            target = rel.get("Target")
            if not relationship_id or not target:
                continue

            package_path = target if target.startswith("word/") else f"word/{target}"
            relationships[relationship_id] = ImageRelationship(
                relationship_id=relationship_id,
                target=target,
                package_path=package_path,
            )

        return relationships

    def _read_chart_relationships(self, archive: ZipFile) -> dict[str, ChartRelationship]:
        rels_root = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
        relationships: dict[str, ChartRelationship] = {}

        for rel in rels_root.xpath("./pr:Relationship", namespaces=NS):
            rel_type = rel.get("Type", "")
            if not rel_type.endswith("/chart"):
                continue

            relationship_id = rel.get("Id")
            target = rel.get("Target")
            if not relationship_id or not target:
                continue

            package_path = target if target.startswith("word/") else f"word/{target}"
            relationships[relationship_id] = ChartRelationship(
                relationship_id=relationship_id,
                target=target,
                package_path=package_path,
            )

        return relationships

    def _parse_body(self, body: etree._Element, resolver: StyleResolver) -> Iterable[DocumentBlock]:
        index = 0
        for child in self._iter_content_children(body):
            parsed = self._parse_block(child, index=index + 1, resolver=resolver)
            if parsed is None:
                continue

            index += 1
            yield parsed

    def _iter_content_children(self, parent: etree._Element) -> Iterable[etree._Element]:
        for child in parent:
            tag = etree.QName(child).localname
            if tag == "sdt":
                content = child.find("w:sdtContent", NS)
                if content is not None:
                    yield from self._iter_content_children(content)
                continue

            if tag in {"p", "tbl"}:
                yield child

    def _parse_block(
        self,
        element: etree._Element,
        index: int,
        resolver: StyleResolver,
    ) -> DocumentBlock | None:
        tag = etree.QName(element).localname
        if tag == "p":
            return self._parse_paragraph(element, index, resolver)
        if tag == "tbl":
            return self._parse_table(element, index, resolver)
        return None

    def _parse_paragraph(
        self,
        paragraph: etree._Element,
        index: int,
        resolver: StyleResolver,
    ) -> ParagraphBlock | None:
        text = self._paragraph_text(paragraph)
        image_ids = tuple(paragraph.xpath(".//a:blip/@r:embed", namespaces=NS))
        chart_ids = tuple(paragraph.xpath(".//c:chart/@r:id", namespaces=NS))

        if not text and not image_ids and not chart_ids:
            return None

        return ParagraphBlock(
            index=index,
            text=text,
            image_relationship_ids=image_ids,
            chart_relationship_ids=chart_ids,
            html=paragraph_inline_html(paragraph, resolver) if text else "",
        )

    def _parse_table(
        self,
        table: etree._Element,
        index: int,
        resolver: StyleResolver,
    ) -> TableBlock | None:
        rows: list[tuple[str, ...]] = []
        image_ids: list[str] = []
        image_positions: list[tuple[int, int]] = []
        chart_ids: list[str] = []

        for row_index, row in enumerate(table.xpath("./w:tr", namespaces=NS)):
            cells: list[str] = []
            for col_index, cell in enumerate(row.xpath("./w:tc", namespaces=NS)):
                paragraphs = [self._paragraph_text(p) for p in cell.xpath("./w:p", namespaces=NS)]
                cells.append(" | ".join(text for text in paragraphs if text))
                cell_image_ids = tuple(cell.xpath(".//a:blip/@r:embed", namespaces=NS))
                image_ids.extend(cell_image_ids)
                image_positions.extend((row_index, col_index) for _ in cell_image_ids)
                chart_ids.extend(cell.xpath(".//c:chart/@r:id", namespaces=NS))
            rows.append(tuple(cells))

        if not rows and not image_ids and not chart_ids:
            return None

        return TableBlock(
            index=index,
            rows=tuple(rows),
            image_relationship_ids=tuple(image_ids),
            image_cell_positions=tuple(image_positions),
            chart_relationship_ids=tuple(chart_ids),
            cells=self._parse_table_cells(table, resolver),
            has_nested_table=bool(table.xpath("./w:tr/w:tc//w:tbl", namespaces=NS)),
        )

    def _parse_table_cells(
        self,
        table: etree._Element,
        resolver: StyleResolver,
    ) -> tuple[tuple[TableCell, ...], ...]:
        rows: list[list[dict]] = []
        merge_origins: dict[int, dict] = {}
        for row in table.xpath("./w:tr", namespaces=NS):
            grid_column = _int_attribute(row.find("w:trPr/w:gridBefore", NS), default=0)
            cells: list[dict] = []
            for cell in row.xpath("./w:tc", namespaces=NS):
                colspan = _int_attribute(cell.find("w:tcPr/w:gridSpan", NS), default=1)
                vertical_merge = cell.find("w:tcPr/w:vMerge", NS)
                merge_value = None
                if vertical_merge is not None:
                    merge_value = vertical_merge.get(f"{{{WORD_NS}}}val", "continue")
                origin = merge_origins.get(grid_column)
                if merge_value == "continue" and origin is not None:
                    origin["rowspan"] += 1
                    grid_column += colspan
                    continue

                paragraphs = cell.xpath("./w:p", namespaces=NS)
                fragments = [paragraph_inline_html(paragraph, resolver) for paragraph in paragraphs]
                texts = [self._paragraph_text(paragraph) for paragraph in paragraphs]
                alignments = [
                    paragraph_alignment(paragraph)
                    for paragraph, text in zip(paragraphs, texts)
                    if text
                ]
                data = {
                    "text": " | ".join(text for text in texts if text),
                    "html": "<br>".join(fragment for fragment in fragments if fragment),
                    "colspan": colspan,
                    "rowspan": 1,
                    "align": alignments[0] if alignments else "",
                }
                if merge_value == "restart":
                    merge_origins[grid_column] = data
                else:
                    merge_origins.pop(grid_column, None)
                cells.append(data)
                grid_column += colspan
            rows.append(cells)
        return tuple(tuple(TableCell(**data) for data in cells) for cells in rows)

    def _paragraph_text(self, paragraph: etree._Element) -> str:
        parts: list[str] = []
        for element in paragraph.xpath(".//w:t | .//w:tab | .//w:br | .//w:cr", namespaces=NS):
            tag = etree.QName(element).localname
            parts.append(element.text or "" if tag == "t" else " ")
        return clean_word_text("".join(parts))


def _int_attribute(node: etree._Element | None, default: int) -> int:
    if node is None:
        return default
    try:
        return max(int(node.get(f"{{{WORD_NS}}}val", default)), 0) or default
    except ValueError:
        return default
