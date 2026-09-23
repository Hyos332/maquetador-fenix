from __future__ import annotations

import re
from datetime import date

from app.exceptions import MetadataExtractionError
from app.models.article import Article, ArticleLanguage, Author
from app.services.docx_parser import ParagraphBlock, ParsedDocument, TableBlock
from app.utils.strings import normalize_for_match, normalize_whitespace

DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[^\s)]+)", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
DATE_PATTERNS = {
    "received_date": re.compile(r"(?:Recibido|Received)\s*:?\s*(\d{2}/\d{2}/\d{2})", re.I),
    "reviewed_date": re.compile(r"(?:Revisado|Reviewed)\s*:?\s*(\d{2}/\d{2}/\d{2})", re.I),
    "accepted_date": re.compile(r"(?:Aceptado|Accepted)\s*:?\s*(\d{2}/\d{2}/\d{2})", re.I),
}
VOLUME_PATTERN = re.compile(r"\b(?P<volume>\d+)\((?P<issue>\d+)\)\s*[,.;]\s*(?P<pages>\d+\s*-\s*\d+)")


class MetadataExtractor:
    def extract(self, parsed: ParsedDocument) -> Article:
        paragraphs = [block for block in parsed.blocks if isinstance(block, ParagraphBlock) and block.text]
        header_article = self._extract_header_article(parsed, paragraphs)
        if header_article:
            return header_article

        doi = self._extract_doi(parsed.full_text)
        citation_index = self._find_citation_index(paragraphs, doi)

        first_title = self._paragraph_after(paragraphs, citation_index, offset=1)
        second_title = self._paragraph_after(paragraphs, citation_index, offset=2)
        author_name = self._paragraph_after(paragraphs, citation_index, offset=3)
        author_details = self._paragraph_after(paragraphs, citation_index, offset=4)
        author_extra_details = self._paragraph_after(paragraphs, citation_index, offset=5)
        if author_extra_details and ("@" in author_extra_details or "orcid" in author_extra_details.casefold()):
            author_details = f"{author_details or ''} {author_extra_details}".strip()

        if not first_title or not author_name:
            raise MetadataExtractionError("Could not identify article title and author.")

        dates = self._extract_dates(parsed.full_text)
        volume, issue, pages = self._extract_volume_issue_pages(
            paragraphs[citation_index].text if citation_index is not None else ""
        )
        abstract_es, keywords_es, abstract_en, keywords_en, language = self._extract_abstract_table(parsed)
        title_es, title_en = _assign_titles(first_title, second_title, language)

        return Article(
            language=language,
            journal=self._extract_journal_key(parsed.full_text),
            title_es=title_es,
            title_en=title_en,
            abstract_es=abstract_es,
            abstract_en=abstract_en,
            keywords_es=keywords_es,
            keywords_en=keywords_en,
            authors=[self._build_author(author_name, author_details)],
            doi=doi,
            volume=volume,
            issue=issue,
            pages=pages,
            **dates,
        )

    def _extract_doi(self, text: str) -> str | None:
        match = DOI_PATTERN.search(text)
        if not match:
            return None
        return match.group(1).rstrip(".,;")

    def _find_citation_index(
        self,
        paragraphs: list[ParagraphBlock],
        doi: str | None,
    ) -> int | None:
        if doi:
            for index, paragraph in enumerate(paragraphs):
                if doi in paragraph.text:
                    return index

        for index, paragraph in enumerate(paragraphs):
            if DOI_PATTERN.search(paragraph.text):
                return index
        return None

    def _paragraph_after(
        self,
        paragraphs: list[ParagraphBlock],
        citation_index: int | None,
        offset: int,
    ) -> str | None:
        if citation_index is None:
            return None
        target = citation_index + offset
        if target >= len(paragraphs):
            return None
        return paragraphs[target].text

    def _extract_header_article(
        self,
        parsed: ParsedDocument,
        paragraphs: list[ParagraphBlock],
    ) -> Article | None:
        manuscript_index = next(
            (
                index
                for index, paragraph in enumerate(paragraphs)
                if normalize_for_match(paragraph.text).startswith("manuscript information")
            ),
            None,
        )
        if manuscript_index is None or manuscript_index < 3:
            return None

        citation_index = self._find_header_citation_index(paragraphs[:manuscript_index])
        title_start = citation_index + 1 if citation_index is not None else 0
        if title_start + 1 >= manuscript_index:
            return None

        first_title = paragraphs[title_start].text
        second_title = paragraphs[title_start + 1].text
        author_paragraphs = paragraphs[title_start + 2 : manuscript_index]
        authors = self._extract_header_authors(author_paragraphs)
        if not authors:
            return None

        front_text = self._front_matter_text(parsed)
        dates = self._extract_dates(front_text)
        volume, issue, pages = self._extract_volume_issue_pages(
            paragraphs[citation_index].text if citation_index is not None else ""
        )
        abstract_es, keywords_es, abstract_en, keywords_en, language = self._extract_abstract_table(parsed)
        title_es, title_en = _assign_titles(first_title, second_title, language)

        return Article(
            language=language,
            journal=self._extract_journal_key(front_text or parsed.full_text),
            title_es=title_es,
            title_en=title_en,
            abstract_es=abstract_es,
            abstract_en=abstract_en,
            keywords_es=keywords_es,
            keywords_en=keywords_en,
            authors=authors,
            doi=self._extract_doi(front_text),
            volume=volume,
            issue=issue,
            pages=pages,
            **dates,
        )

    def _extract_header_authors(self, author_paragraphs: list[ParagraphBlock]) -> list[Author]:
        authors: list[Author] = []
        index = 0
        while index < len(author_paragraphs):
            full_name = author_paragraphs[index].text
            index += 1
            detail_parts: list[str] = []

            while index < len(author_paragraphs):
                current = author_paragraphs[index].text
                next_text = author_paragraphs[index + 1].text if index + 1 < len(author_paragraphs) else ""
                if detail_parts and _looks_like_author_name(current) and _looks_like_author_detail(next_text):
                    break
                detail_parts.append(current)
                index += 1

            if full_name and detail_parts:
                authors.append(self._build_author(full_name, " ".join(detail_parts)))

        return authors

    def _find_header_citation_index(self, paragraphs: list[ParagraphBlock]) -> int | None:
        for index, paragraph in enumerate(paragraphs[:3]):
            if VOLUME_PATTERN.search(paragraph.text):
                return index
        return None

    def _front_matter_text(self, parsed: ParsedDocument) -> str:
        parts: list[str] = []
        for block in parsed.blocks:
            if isinstance(block, ParagraphBlock):
                if normalize_for_match(block.text) in {"introduction", "introduccion", "introducao"}:
                    break
                parts.append(block.text)
            else:
                parts.extend(cell for row in block.rows for cell in row)
        return "\n".join(part for part in parts if part)

    def _build_author(self, full_name: str | None, details: str | None) -> Author:
        details = details or ""
        email_match = EMAIL_PATTERN.search(details)
        institution, country = _parse_institution_country(details)

        return Author(
            full_name=full_name or "",
            email=email_match.group(0) if email_match else None,
            institution=institution,
            country=country,
            orcid=details,
        )

    def _extract_dates(self, text: str) -> dict[str, date | None]:
        values: dict[str, date | None] = {
            "received_date": None,
            "reviewed_date": None,
            "accepted_date": None,
        }

        for field_name, pattern in DATE_PATTERNS.items():
            match = pattern.search(text)
            if match:
                values[field_name] = _parse_short_date(match.group(1))

        return values

    def _extract_volume_issue_pages(self, citation: str) -> tuple[str | None, str | None, str | None]:
        match = VOLUME_PATTERN.search(citation)
        if not match:
            return None, None, None
        pages = match.group("pages").replace(" ", "")
        return match.group("volume"), match.group("issue"), pages

    def _extract_abstract_table(
        self,
        parsed: ParsedDocument,
    ) -> tuple[str | None, list[str], str | None, list[str], ArticleLanguage]:
        abstract_es: str | None = None
        abstract_en: str | None = None
        keywords_es: list[str] = []
        keywords_en: list[str] = []
        first_abstract_label: str | None = None

        for block in parsed.blocks:
            if not isinstance(block, TableBlock):
                continue

            table_text = normalize_for_match(" ".join(cell for row in block.rows for cell in row))
            if "resumen" not in table_text or "abstract" not in table_text:
                continue

            for row in block.rows:
                if len(row) < 2:
                    continue

                label = normalize_for_match(row[0])
                if label.startswith("palabras clave"):
                    first_abstract_label = first_abstract_label or "es"
                    keywords_es = _split_keywords(row[0])
                    abstract_es = row[1]
                elif label.startswith("keywords"):
                    first_abstract_label = first_abstract_label or "en"
                    keywords_en = _split_keywords(row[0])
                    abstract_en = row[1]

        language = ArticleLanguage.ENGLISH if first_abstract_label == "en" else ArticleLanguage.SPANISH
        return abstract_es, keywords_es, abstract_en, keywords_en, language

    def _extract_journal_key(self, text: str) -> str:
        normalized = normalize_for_match(text)
        if "mlspci" in normalized or "pedagogy, culture and innovation" in normalized:
            return "mlspci"
        if "mls - educational research" in normalized or "mlser" in normalized:
            return "mlser"
        if "health" in normalized and "nutrition" in normalized:
            return "mlshnr"
        return "mlshnr"


def _parse_short_date(value: str) -> date:
    day, month, year = (int(part) for part in value.split("/"))
    full_year = 2000 + year if year < 70 else 1900 + year
    return date(full_year, month, day)


def _split_keywords(value: str) -> list[str]:
    if ":" not in value:
        return []
    raw_keywords = value.split(":", 1)[1].replace("|", " ")
    return [normalize_whitespace(keyword) for keyword in raw_keywords.split(",") if keyword.strip()]


def _parse_institution_country(details: str) -> tuple[str | None, str | None]:
    before_parentheses = normalize_whitespace(details.split("(", 1)[0])
    parenthetical_countries = [
        value
        for value in re.findall(r"\(([^()@]*?)\)", details)
        if "http" not in value.casefold() and "orcid" not in value.casefold()
    ]
    country = next((normalize_whitespace(value) for value in parenthetical_countries if value.strip()), None)
    institution = before_parentheses or None

    if before_parentheses and "," in before_parentheses:
        possible_institution, possible_country = before_parentheses.rsplit(",", 1)
        possible_country = normalize_whitespace(possible_country)
        if possible_country and len(possible_country.split()) <= 4:
            institution = normalize_whitespace(possible_institution) or institution
            country = country or possible_country

    return institution, country


def _looks_like_author_name(value: str) -> bool:
    normalized = normalize_for_match(value)
    if not normalized or "@" in normalized or "orcid" in normalized or "," in normalized:
        return False
    if any(term in normalized for term in ("universidad", "university", "instituto", "institute")):
        return False
    return 2 <= len(normalized.split()) <= 6


def _looks_like_author_detail(value: str) -> bool:
    normalized = normalize_for_match(value)
    return (
        "@" in normalized
        or "orcid" in normalized
        or "," in normalized
        or "universidad" in normalized
        or "university" in normalized
        or "instituto" in normalized
        or "institute" in normalized
    )


def _assign_titles(
    first_title: str,
    second_title: str | None,
    language: ArticleLanguage,
) -> tuple[str | None, str | None]:
    if language == ArticleLanguage.ENGLISH:
        return second_title, first_title
    return first_title, second_title
