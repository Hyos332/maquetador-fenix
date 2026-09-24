from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

from app.config.settings import Settings
from app.models.pre_analysis import PreAnalysisResult
from app.services.ai_reviewer import LocalAiReviewer
from app.services.docx_parser import DocxParser, TableBlock
from app.services.metadata_extractor import MetadataExtractor
from app.services.reference_processor import ReferenceProcessor
from app.utils.strings import word_count


def _smart_trim_abstract(text: str, max_words: int = 245) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    accumulated: list[str] = []
    current_words = 0
    for s in sentences:
        words = word_count(s)
        if current_words + words <= max_words:
            accumulated.append(s)
            current_words += words
        else:
            break
    if accumulated:
        return " ".join(accumulated)
    words = text.split()[:max_words]
    return " ".join(words) + "."


class PreAnalyzerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.docx_parser = DocxParser()
        self.metadata_extractor = MetadataExtractor()
        self.reference_processor = ReferenceProcessor()
        self.ai_reviewer = LocalAiReviewer(
            enabled=settings.ai_review_enabled,
            endpoint=settings.ai_review_endpoint,
            model=settings.ai_review_model,
            timeout_seconds=min(settings.ai_review_timeout_seconds, 10),
        )

    def analyze_file(self, file_path: Path, original_filename: str) -> PreAnalysisResult:
        file_size = file_path.stat().st_size if file_path.exists() else 0
        suffix = file_path.suffix.lower()

        if suffix == ".docx":
            return self._analyze_docx(file_path, original_filename, file_size)
        elif suffix == ".zip":
            return self._analyze_zip(file_path, original_filename, file_size)
        else:
            return PreAnalysisResult(
                file_name=original_filename,
                file_size_bytes=file_size,
                issues=["Formato no soportado. Debe ser .docx o .zip"],
            )

    def _analyze_zip(self, zip_path: Path, original_filename: str, file_size: int) -> PreAnalysisResult:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    docx_members = [
                        name for name in archive.namelist()
                        if name.lower().endswith(".docx") and not name.startswith("__MACOSX/")
                    ]
                    if not docx_members:
                        return PreAnalysisResult(
                            file_name=original_filename,
                            file_size_bytes=file_size,
                            issues=["El archivo ZIP no contiene ningún documento .docx."],
                        )
                    primary_member = docx_members[0]
                    extracted_docx = temp_path / "article.docx"
                    extracted_docx.write_bytes(archive.read(primary_member))
                    return self._analyze_docx(extracted_docx, original_filename, file_size)
            except (zipfile.BadZipFile, OSError):
                return PreAnalysisResult(
                    file_name=original_filename,
                    file_size_bytes=file_size,
                    issues=["El archivo ZIP es inválido o está corrupto."],
                )

    def _analyze_docx(self, docx_path: Path, original_filename: str, file_size: int) -> PreAnalysisResult:
        try:
            parsed = self.docx_parser.parse(docx_path)
        except Exception as exc:
            return PreAnalysisResult(
                file_name=original_filename,
                file_size_bytes=file_size,
                issues=[f"Error al analizar DOCX: {exc}"],
            )

        article = self.metadata_extractor.extract(parsed)
        references = self.reference_processor.extract(parsed)

        es_count = word_count(article.abstract_es or "")
        en_count = word_count(article.abstract_en or "")
        limit = 250

        figures_count = len(parsed.image_relationships)
        tables_count = sum(1 for block in parsed.blocks if isinstance(block, TableBlock))
        references_count = len(references)

        issues: list[str] = []
        suggestions: list[str] = []

        if es_count > limit:
            issues.append(f"Resumen en español excede el límite ({es_count}/{limit} palabras).")
        if en_count > limit:
            issues.append(f"Abstract en inglés excede el límite ({en_count}/{limit} palabras).")
        if not article.doi:
            issues.append("No se detectó código DOI en el documento.")

        if not article.authors:
            suggestions.append("No se detectaron autores claramente identificados.")
        else:
            for author in article.authors:
                if not author.orcid:
                    suggestions.append(f"Autor {author.full_name} no tiene ORCID especificado.")
                if not author.email:
                    suggestions.append(f"Autor {author.full_name} no tiene correo especificado.")

        if len(article.keywords_es) < 3:
            suggestions.append("Se detectaron menos de 3 palabras clave en español.")
        if len(article.keywords_en) < 3:
            suggestions.append("Se detectaron menos de 3 keywords en inglés.")

        seq_warnings = self.reference_processor.sequence_warnings(references)
        suggestions.extend(seq_warnings)

        estimated_seconds = max(10, 8 + (figures_count * 2) + (tables_count * 2) + int(references_count * 0.1))

        suggested_es = None
        suggested_en = None

        if self.settings.ai_review_enabled and (es_count > limit or en_count > limit):
            ai_result = self.ai_reviewer.review(article, docx_path, issues)
            suggested_es = ai_result.suggested_abstract_es
            suggested_en = ai_result.suggested_abstract_en
            for s in ai_result.suggestions:
                if s not in suggestions:
                    suggestions.append(s)

        if not suggested_es and es_count > limit and article.abstract_es:
            suggested_es = _smart_trim_abstract(article.abstract_es, max_words=245)

        if not suggested_en and en_count > limit and article.abstract_en:
            suggested_en = _smart_trim_abstract(article.abstract_en, max_words=245)

        return PreAnalysisResult(
            file_name=original_filename,
            file_size_bytes=file_size,
            article_title=article.primary_title,
            doi=article.doi,
            journal=article.journal,
            abstract_es_word_count=es_count,
            abstract_en_word_count=en_count,
            abstract_word_limit=limit,
            figures_count=figures_count,
            tables_count=tables_count,
            references_count=references_count,
            estimated_seconds=estimated_seconds,
            issues=issues,
            suggestions=suggestions,
            suggested_abstract_es=suggested_es,
            suggested_abstract_en=suggested_en,
        )
