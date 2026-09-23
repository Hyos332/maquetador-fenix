from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from app.models.article import Figure
from app.services.docx_parser import DocumentBlock, ParagraphBlock, ParsedDocument, TableBlock
from app.utils.files import ensure_directory
from app.utils.strings import clean_word_text, normalize_for_match


@dataclass(frozen=True)
class ImageExtractionResult:
    figures: list[Figure]
    warnings: list[str] = field(default_factory=list)


class ImageExtractor:
    def extract_figures(
        self,
        parsed: ParsedDocument,
        output_dir: Path | None = None,
    ) -> ImageExtractionResult:
        figures: list[Figure] = []
        warnings: list[str] = []
        if output_dir:
            ensure_directory(output_dir)

        seen_relationship_ids: set[str] = set()
        chart_exports = self._export_chart_images(parsed) if parsed.chart_relationships else []
        chart_export_index = 0
        for block_index, block in enumerate(parsed.blocks):
            if (
                not block.image_relationship_ids
                and not block.chart_relationship_ids
            ) or self._is_journal_header_image_block(block_index, block):
                continue

            caption_match = self._find_caption(parsed, block_index) or self._caption_from_image_block(block)
            caption, caption_block_index = caption_match if caption_match else (None, None)
            embedded_text = _block_text(block)
            image_relationship_ids = list(block.image_relationship_ids)
            table_captions = self._table_image_captions(block, caption, len(image_relationship_ids))
            table_positions = self._table_image_positions(block, len(image_relationship_ids))
            group_id = f"figure-table-{block_index}" if table_positions else None

            for image_index, relationship_id in enumerate(image_relationship_ids):
                if relationship_id in seen_relationship_ids:
                    continue
                seen_relationship_ids.add(relationship_id)

                relationship = parsed.image_relationships.get(relationship_id)
                if not relationship:
                    warnings.append(f"Image relationship not found: {relationship_id}")
                    continue

                figure_number = len(figures) + 1
                output_filename = f"Figure_{figure_number}.PNG"
                if output_dir:
                    try:
                        self._write_png(parsed, relationship.package_path, output_dir / output_filename)
                    except OSError as exc:
                        warnings.append(f"Could not convert {relationship.package_path}: {exc}")

                figures.append(
                    Figure(
                        number=figure_number,
                        source=Path(relationship.package_path),
                        output_filename=output_filename,
                        caption=table_captions[image_index] if image_index < len(table_captions) else caption,
                        block_index=block_index,
                        caption_block_index=caption_block_index,
                        group_id=group_id,
                        group_row=table_positions[image_index][0] if image_index < len(table_positions) else None,
                        group_col=table_positions[image_index][1] if image_index < len(table_positions) else None,
                    )
                )
                self._warn_if_complex_image_text(
                    warnings,
                    output_filename,
                    embedded_text,
                    caption,
                    handled=bool(table_captions),
                )

            for relationship_id in block.chart_relationship_ids:
                if relationship_id in seen_relationship_ids:
                    continue
                seen_relationship_ids.add(relationship_id)

                relationship = parsed.chart_relationships.get(relationship_id)
                if not relationship:
                    warnings.append(f"Chart relationship not found: {relationship_id}")
                    continue

                figure_number = len(figures) + 1
                output_filename = f"Figure_{figure_number}.PNG"
                if output_dir:
                    if chart_export_index >= len(chart_exports):
                        warnings.append(f"Could not export chart {relationship.package_path}.")
                    else:
                        chart_exports[chart_export_index].save(output_dir / output_filename, format="PNG")
                chart_export_index += 1

                figures.append(
                    Figure(
                        number=figure_number,
                        source=Path(relationship.package_path),
                        output_filename=output_filename,
                        caption=caption,
                        block_index=block_index,
                        caption_block_index=caption_block_index,
                    )
                )
                self._warn_if_complex_image_text(warnings, output_filename, embedded_text, caption)

        return ImageExtractionResult(figures=figures, warnings=warnings)

    def _find_caption(self, parsed: ParsedDocument, block_index: int) -> tuple[str, int] | None:
        candidate_indexes = [block_index + offset for offset in (-1, 1, -2, 2, -3, 3)]
        for candidate_index in candidate_indexes:
            if candidate_index < 0 or candidate_index >= len(parsed.blocks):
                continue

            candidate = parsed.blocks[candidate_index]
            if not isinstance(candidate, ParagraphBlock) or not candidate.text:
                continue

            normalized = normalize_for_match(candidate.text)
            if (
                normalized.startswith("figura ")
                or normalized.startswith("figure ")
                or normalized.startswith("tabla ")
                or normalized.startswith("table ")
                or normalized.startswith("fig. ")
            ):
                return candidate.text, candidate_index

        return None

    def _caption_from_image_block(self, block: DocumentBlock) -> tuple[str, int | None] | None:
        text = _block_text(block)
        if not text or not self._looks_like_caption(text):
            return None
        return text, None

    def _looks_like_caption(self, text: str) -> bool:
        normalized = normalize_for_match(text)
        return (
            normalized.startswith("figura ")
            or normalized.startswith("figure ")
            or normalized.startswith("tabla ")
            or normalized.startswith("table ")
            or normalized.startswith("fig. ")
        )

    def _table_image_captions(
        self,
        block: DocumentBlock,
        base_caption: str | None,
        image_count: int,
    ) -> list[str]:
        if not isinstance(block, TableBlock) or image_count <= 1:
            return []

        cells = [clean_word_text(cell) for row in block.rows for cell in row if clean_word_text(cell)]
        if len(cells) < image_count:
            return []

        return [_join_caption(base_caption, cell) for cell in cells[:image_count]]

    def _table_image_positions(
        self,
        block: DocumentBlock,
        image_count: int,
    ) -> list[tuple[int, int]]:
        if not isinstance(block, TableBlock) or image_count <= 1:
            return []

        positions = list(block.image_cell_positions)
        if len(positions) != image_count:
            return []

        return positions

    def _warn_if_complex_image_text(
        self,
        warnings: list[str],
        output_filename: str,
        embedded_text: str,
        caption: str | None,
        handled: bool = False,
    ) -> None:
        if handled:
            return
        if not embedded_text or self._looks_like_caption(embedded_text):
            return
        if caption and normalize_for_match(embedded_text) == normalize_for_match(caption):
            return
        warnings.append(
            f"{output_filename} is embedded with extra text in the DOCX; review the figure placement/caption."
        )

    def _is_journal_header_image_block(self, block_index: int, block: DocumentBlock) -> bool:
        if block_index > 2:
            return False

        text = ""
        if isinstance(block, ParagraphBlock):
            text = block.text
        elif isinstance(block, TableBlock):
            text = " ".join(cell for row in block.rows for cell in row)

        normalized = normalize_for_match(text)
        return "issn" in normalized and ("mls" in normalized or "journal" in normalized)

    def _write_png(self, parsed: ParsedDocument, package_path: str, output_path: Path) -> None:
        suffix = Path(package_path).suffix.lower()
        with ZipFile(parsed.path) as archive:
            data = archive.read(package_path)

        if suffix == ".png":
            output_path.write_bytes(data)
            return

        if suffix in {".jpg", ".jpeg"}:
            image = Image.open(BytesIO(data))
            image.save(output_path, format="PNG")
            return

        if suffix in {".emf", ".wmf"}:
            self._convert_vector_with_libreoffice(data, suffix, output_path)
            return

        image = Image.open(BytesIO(data))
        image.save(output_path, format="PNG")

    def _convert_vector_with_libreoffice(self, data: bytes, suffix: str, output_path: Path) -> None:
        libreoffice = shutil.which("libreoffice")
        if not libreoffice:
            raise OSError("libreoffice is required to convert EMF/WMF images.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / f"source{suffix}"
            input_path.write_bytes(data)

            subprocess.run(
                [
                    libreoffice,
                    "--headless",
                    "--convert-to",
                    "png",
                    "--outdir",
                    str(temp_path),
                    str(input_path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )

            converted_path = temp_path / "source.png"
            if not converted_path.exists():
                raise OSError("libreoffice did not create a PNG file.")

            output_path.write_bytes(converted_path.read_bytes())

    def _export_chart_images(self, parsed: ParsedDocument) -> list[Image.Image]:
        libreoffice = shutil.which("libreoffice")
        if not libreoffice:
            return []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            subprocess.run(
                [
                    libreoffice,
                    "--headless",
                    "--convert-to",
                    "html",
                    "--outdir",
                    str(temp_path),
                    str(parsed.path),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )

            images: list[Image.Image] = []
            for path in sorted(temp_path.iterdir(), key=lambda item: item.stat().st_mtime_ns):
                if path.suffix.lower() not in {".gif", ".png", ".jpg", ".jpeg"}:
                    continue
                image = Image.open(path)
                width, height = image.size
                if width < 300 or height < 200:
                    continue
                images.append(image.convert("RGBA"))

            return images


def _block_text(block: DocumentBlock) -> str:
    if isinstance(block, ParagraphBlock):
        return clean_word_text(block.text)
    return clean_word_text(" ".join(cell for row in block.rows for cell in row if cell))


def _join_caption(base_caption: str | None, detail: str) -> str:
    if not base_caption:
        return detail
    if normalize_for_match(detail).startswith(normalize_for_match(base_caption)):
        return detail
    return f"{base_caption}. {detail}"
