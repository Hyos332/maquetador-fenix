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
from app.services.docx_parser import ParagraphBlock, ParsedDocument
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

        for block_index, block in enumerate(parsed.blocks):
            if not isinstance(block, ParagraphBlock) or not block.image_relationship_ids:
                continue

            caption_match = self._find_caption(parsed, block_index)
            if not caption_match:
                continue
            caption, caption_block_index = caption_match

            for relationship_id in block.image_relationship_ids:
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

        return ImageExtractionResult(figures=figures, warnings=warnings)

    def _find_caption(self, parsed: ParsedDocument, block_index: int) -> tuple[str, int] | None:
        for candidate_index in (block_index + 1, block_index - 1):
            if candidate_index < 0 or candidate_index >= len(parsed.blocks):
                continue

            candidate = parsed.blocks[candidate_index]
            if not isinstance(candidate, ParagraphBlock) or not candidate.text:
                continue

            normalized = normalize_for_match(candidate.text)
            if normalized.startswith("figura ") or normalized.startswith("tabla "):
                return candidate.text, candidate_index

        return None

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
