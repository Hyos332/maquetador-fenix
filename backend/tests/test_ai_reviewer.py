import json
from datetime import date
from pathlib import Path
from urllib.error import URLError

from app.models.article import Article, ArticleLanguage, Author
from app.services.ai_reviewer import LocalAiReviewer


def test_ai_reviewer_disabled_returns_empty_result(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Artículo</body></html>", encoding="utf-8")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("AI reviewer should not call Ollama when disabled.")

    monkeypatch.setattr("app.services.ai_reviewer.urlopen", fail_urlopen)

    result = LocalAiReviewer(
        enabled=False,
        endpoint="http://localhost:11434/api/generate",
        model="llama3.2:3b",
        timeout_seconds=1,
    ).review(_article(), html_path, [])

    assert result.suggestions == []
    assert result.suggested_abstract_es is None


def test_ai_reviewer_parses_ollama_json_response(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Artículo con DOI y fechas.</body></html>", encoding="utf-8")

    response_payload = {
        "response": json.dumps(
            {
                "suggestions": ["Revisar la leyenda de la Figura 2."],
                "suggested_abstract_es": "Resumen breve conservando la intención.",
                "suggested_abstract_en": " ".join(["word"] * 251),
            }
        )
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return json.dumps(response_payload).encode("utf-8")

    monkeypatch.setattr("app.services.ai_reviewer.urlopen", lambda *args, **kwargs: FakeResponse())

    result = LocalAiReviewer(
        enabled=True,
        endpoint="http://localhost:11434/api/generate",
        model="llama3.2:3b",
        timeout_seconds=1,
    ).review(_article(), html_path, [])

    assert result.suggestions == ["Revisar la leyenda de la Figura 2."]
    assert result.suggested_abstract_es == "Resumen breve conservando la intención."
    assert result.suggested_abstract_en is None


def test_ai_reviewer_unavailable_model_is_silent(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Artículo</body></html>", encoding="utf-8")

    def unavailable(*args, **kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr("app.services.ai_reviewer.urlopen", unavailable)

    result = LocalAiReviewer(
        enabled=True,
        endpoint="http://localhost:11434/api/generate",
        model="llama3.2:3b",
        timeout_seconds=1,
    ).review(_article(), html_path, [])

    assert result.suggestions == []
    assert result.suggested_abstract_es is None
    assert result.suggested_abstract_en is None


def test_ai_reviewer_invalid_ollama_response_is_silent(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Artículo</body></html>", encoding="utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return json.dumps({"error": "model is still downloading"}).encode("utf-8")

    monkeypatch.setattr("app.services.ai_reviewer.urlopen", lambda *args, **kwargs: FakeResponse())

    result = LocalAiReviewer(
        enabled=True,
        endpoint="http://localhost:11434/api/generate",
        model="llama3.2:3b",
        timeout_seconds=1,
    ).review(_article(), html_path, [])

    assert result.suggestions == []


def _article() -> Article:
    return Article(
        language=ArticleLanguage.SPANISH,
        journal="mlser",
        title_es="Título de prueba",
        abstract_es="Resumen de prueba.",
        authors=[Author(full_name="Ana Test", email="ana@example.com")],
        doi="10.1000/test",
        accepted_date=date(2026, 1, 1),
    )
