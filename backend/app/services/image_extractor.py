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
from app.utils.strings import normalize_for_match


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

            caption_match = self._find_caption(parsed, block_index)
            caption, caption_block_index = caption_match if caption_match else (None, None)

            for relationship_id in block.image_relationship_ids:
                if relationship_id in seen_relationship_ids:
                    continue
                seen_relationship_ids.add(relationship_id)

                relationship = parsed.image_relationships.get(relationship_id)
                if not relationship:
                    warnings.append(f"Image relationship not found: {relationship_id}")
                    continue

                output_filename = f"Figure_{len(figures) + 1}.PNG"
                if output_dir:
                    try:
                        self._write_png(parsed, relationship.package_path, output_dir / output_filename)
                    except OSError as exc:
                        warnings.append(f"Could not convert {relationship.package_path}: {exc}")

                figures.append(
                    Figure(
                        number=len(figures) + 1,
                        source=Path(relationship.package_path),
                        output_filename=output_filename,
                        caption=caption,
                        block_index=block_index,
                        caption_block_index=caption_block_index,
                    )
                )

            for relationship_id in block.chart_relationship_ids:
                if relationship_id in seen_relationship_ids:
                    continue
                seen_relationship_ids.add(relationship_id)

                relationship = parsed.chart_relationships.get(relationship_id)
                if not relationship:
                    warnings.append(f"Chart relationship not found: {relationship_id}")
                    continue

                output_filename = f"Figure_{len(figures) + 1}.PNG"
                if output_dir:
                    if chart_export_index >= len(chart_exports):
                        warnings.append(f"Could not export chart {relationship.package_path}.")
                    else:
                        chart_exports[chart_export_index].save(output_dir / output_filename, format="PNG")
                chart_export_index += 1

                figures.append(
                    Figure(
                        number=len(figures) + 1,
                        source=Path(relationship.package_path),
                        output_filename=output_filename,
                        caption=caption,
                        block_index=block_index,
                        caption_block_index=caption_block_index,
                    )
                )

        return ImageExtractionResult(figures=figures, warnings=warnings)

    def _find_caption(self, parsed: ParsedDocument, block_index: int) -> tuple[str, int] | None:
        candidate_indexes = [
            block_index + offset
            for offset in (1, -1, 2, -2, 3, -3)
        ]
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
