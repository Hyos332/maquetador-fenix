from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from lxml import etree, html

from app.models.article import Article
from app.utils.strings import word_count


@dataclass(frozen=True)
class AiReviewResult:
    suggestions: list[str] = field(default_factory=list)
    suggested_abstract_es: str | None = None
    suggested_abstract_en: str | None = None


class LocalAiReviewer:
    def __init__(
        self,
        *,
        enabled: bool,
        endpoint: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        self.enabled = enabled
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds

    def review(self, article: Article, html_path: Path, existing_warnings: list[str]) -> AiReviewResult:
        if not self.enabled:
            return AiReviewResult()

        try:
            payload = {
                "model": self.model,
                "prompt": self._build_prompt(article, html_path, existing_warnings),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            }
            request = Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (OSError, TimeoutError, URLError, json.JSONDecodeError):
            return AiReviewResult()

        content = raw.get("response") if isinstance(raw, dict) else None
        if not isinstance(content, str):
            return AiReviewResult()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return AiReviewResult()

        return self._normalize_result(parsed)

    def _build_prompt(self, article: Article, html_path: Path, existing_warnings: list[str]) -> str:
        html_text = _html_visible_text(html_path)
        snapshot = {
            "title": article.primary_title,
            "language": article.language.value,
            "journal": article.journal,
            "doi": article.doi,
            "authors": [
                {
                    "name": author.full_name,
                    "email": author.email,
                    "orcid": author.orcid,
                    "institution": author.institution,
                    "country": author.country,
                }
                for author in article.authors
            ],
            "dates": {
                "received": str(article.received_date) if article.received_date else None,
                "reviewed": str(article.reviewed_date) if article.reviewed_date else None,
                "accepted": str(article.accepted_date) if article.accepted_date else None,
            },
            "figures": [
                {
                    "number": figure.number,
                    "filename": figure.output_filename,
                    "caption": figure.caption,
                }
                for figure in article.figures
            ],
            "references_count": len(article.references),
            "abstract_es_word_count": word_count(article.abstract_es),
            "abstract_en_word_count": word_count(article.abstract_en),
            "abstract_es": article.abstract_es,
            "abstract_en": article.abstract_en,
            "existing_warnings": existing_warnings,
            "html_preview_text": html_text[:5000],
        }

        return (
            "Eres un revisor editorial técnico para artículos MLS. "
            "Revisa el JSON y detecta problemas de maquetación o metadatos. "
            "No inventes datos, no cambies la intención científica y no reescribas el artículo completo. "
            "Si un resumen supera 250 palabras, puedes proponer una versión de máximo 250 palabras conservando el sentido. "
            "Responde SOLO JSON con esta forma exacta: "
            '{"suggestions":["..."],"suggested_abstract_es":null,"suggested_abstract_en":null}. '
            "Máximo 6 sugerencias, cortas y accionables, en español. "
            f"Datos:\n{json.dumps(snapshot, ensure_ascii=False)}"
        )

    def _normalize_result(self, parsed: object) -> AiReviewResult:
        if not isinstance(parsed, dict):
            return AiReviewResult()

        suggestions = parsed.get("suggestions", [])
        if not isinstance(suggestions, list):
            suggestions = []
        clean_suggestions = [str(item).strip() for item in suggestions if str(item).strip()]

        abstract_es = _clean_optional_text(parsed.get("suggested_abstract_es"))
        abstract_en = _clean_optional_text(parsed.get("suggested_abstract_en"))
        if abstract_es and word_count(abstract_es) > 250:
            abstract_es = None
        if abstract_en and word_count(abstract_en) > 250:
            abstract_en = None

        return AiReviewResult(
            suggestions=clean_suggestions[:6],
            suggested_abstract_es=abstract_es,
            suggested_abstract_en=abstract_en,
        )


def _html_visible_text(html_path: Path) -> str:
    try:
        root = html.fromstring(html_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, etree.ParserError):
        return ""
    return " ".join(root.text_content().split())


def _clean_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None
