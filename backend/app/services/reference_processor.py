from __future__ import annotations

import re

from app.models.article import Reference
from app.services.docx_parser import ParagraphBlock, ParsedDocument
from app.utils.strings import normalize_for_match

REFERENCE_PATTERN = re.compile(r"^\[(?P<number>\d+)\]\s*(?P<text>.+)")
URL_PATTERN = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


class ReferenceProcessor:
    def extract(self, parsed: ParsedDocument) -> list[Reference]:
        references_started = False
        references: list[Reference] = []

        for block in parsed.blocks:
            if not isinstance(block, ParagraphBlock) or not block.text:
                continue

            normalized = normalize_for_match(block.text)
            if normalized == "referencias":
                references_started = True
                continue

            if not references_started:
                continue

            match = REFERENCE_PATTERN.match(block.text)
            if not match:
                continue

            raw_text = match.group("text").strip()
            references.append(
                Reference(
                    number=int(match.group("number")),
                    raw_text=raw_text,
                    urls=_extract_urls(raw_text),
                )
            )

        return references

    def sequence_warnings(self, references: list[Reference]) -> list[str]:
        if not references:
            return ["No references were detected."]

        warnings: list[str] = []
        seen = {reference.number for reference in references}
        expected = set(range(1, max(seen) + 1))
        missing = sorted(expected - seen)

        if missing:
            warnings.append(f"Missing reference numbers: {missing}")

        if len(seen) != len(references):
            warnings.append("Duplicate reference numbers detected.")

        return warnings


def _extract_urls(text: str) -> list[str]:
    return [match.group(0).rstrip(".,;") for match in URL_PATTERN.finditer(text)]
