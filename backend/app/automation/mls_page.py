from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Browser, Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from app.exceptions import AutomationError
from app.models.article import Article, Author, Section


class MlsPage:
    """Page Object for the external MLS maquetador SPA."""

    def __init__(self, page: Page, base_url: str, timeout_ms: int = 15_000) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout_ms = timeout_ms

    @classmethod
    def create(
        cls,
        browser: Browser,
        base_url: str,
        downloads_dir: Path,
        timeout_ms: int = 15_000,
    ) -> "MlsPage":
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        return cls(page=page, base_url=base_url, timeout_ms=timeout_ms)

    def open(self) -> None:
        self.page.goto(self.base_url, wait_until="networkidle")
        expect(self.page.get_by_role("heading", name="MAQUETADOR DE ARTÍCULOS", exact=True)).to_be_visible(
            timeout=self.timeout_ms,
        )

    def select_language(self, language: str = "Español") -> None:
        selector = self.page.locator("select.form-select").nth(1)
        selector.select_option(label=language)

    def fill_article(self, article: Article) -> None:
        self.fill_author(article.authors[0] if article.authors else None)
        self.fill_citation(article)
        self.fill_titles(article.title_es or "", article.title_en or "")
        self.fill_abstracts(article.abstract_es or "", article.abstract_en or "")
        self.fill_keywords(article.keywords_es, article.keywords_en)
        self.fill_sections(article.sections)
        self.fill_references(article)

    def fill_author(self, author: Author | None) -> None:
        if author is None:
            return

        self._fill("#name", author.full_name)
        self._fill("#email", author.email or "")
        self._fill("#institution", author.institution or "")
        self._fill("#country", author.country or "")
        self._fill("#orcid", author.orcid or "")

    def fill_citation(self, article: Article) -> None:
        citation = self._build_citation(article)
        self._fill("#cite", citation)

    def fill_titles(self, title_es: str, title_en: str) -> None:
        self._fill_by_placeholder("Aquí va el título en español", title_es)
        self._fill_by_placeholder("Here goes the title in English", title_en)

    def fill_abstracts(self, abstract_es: str, abstract_en: str) -> None:
        self._fill_by_placeholder("El resumen debe tener entre 200 y 250 palabras", abstract_es)
        self._fill_by_placeholder("The summary must have between 200 and 250 words", abstract_en)

    def fill_keywords(self, keywords_es: list[str], keywords_en: list[str]) -> None:
        self._fill_keyword_group("Palabra Clave", keywords_es)
        self._fill_keyword_group("Keyword", keywords_en)

    def fill_sections(self, sections: list[Section]) -> None:
        self._ensure_section_count(len(sections))

        title_inputs = self.page.locator('input[placeholder="Título del bloque"]')
        editors = self._editors()
        for index, section in enumerate(sections):
            title_inputs.nth(index).fill(section.title)
            self._set_editor_html(editors.nth(index), section.html_content)

    def fill_references(self, article: Article) -> None:
        reference_html = "\n".join(
            f"<p>[{reference.number}] {reference.raw_text}</p>"
            for reference in article.references
        )
        editors = self._editors()
        reference_editor = editors.nth(len(article.sections))
        self._set_editor_html(reference_editor, reference_html)

    def generate_and_download_html(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.page.expect_download(timeout=60_000) as download_info:
                self.page.get_by_text("Generar Html").click()
            download = download_info.value
            download.save_as(str(output_path))
        except PlaywrightTimeoutError as exc:
            raise AutomationError("MLS maquetador did not download generated HTML in time.") from exc

        return output_path

    def _ensure_section_count(self, required_count: int) -> None:
        current = self.page.locator('input[placeholder="Título del bloque"]').count()
        add_block = self.page.get_by_text("Añadir Bloque")
        while current < required_count:
            add_block.click()
            current += 1
            expect(self.page.locator('input[placeholder="Título del bloque"]').nth(current - 1)).to_be_visible()

    def _fill_keyword_group(self, placeholder_prefix: str, values: list[str]) -> None:
        for index, value in enumerate(values[:5], start=1):
            placeholder = f"{placeholder_prefix} {index}"
            self._fill_by_placeholder(placeholder, value)

    def _editors(self) -> Locator:
        editors = self.page.locator('.ck-editor__editable[contenteditable="true"]')
        if editors.count() == 0:
            raise AutomationError("No CKEditor editable blocks were found in MLS maquetador.")
        return editors

    def _set_editor_html(self, editor: Locator, html_content: str) -> None:
        editor.scroll_into_view_if_needed()
        editor.click()
        editor.evaluate(
            """(element, html) => {
                element.innerHTML = html;
                element.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    inputType: 'insertText',
                    data: null
                }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            html_content,
        )

    def _fill(self, selector: str, value: str) -> None:
        self.page.locator(selector).fill(value)

    def _fill_by_placeholder(self, placeholder: str, value: str) -> None:
        locator = self.page.get_by_placeholder(placeholder).first()
        locator.wait_for(state="attached", timeout=self.timeout_ms)
        locator.evaluate(
            """(element, value) => {
                element.value = value;
                element.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    inputType: 'insertText',
                    data: value
                }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            value,
        )

    def _build_citation(self, article: Article) -> str:
        if not article.authors:
            return article.doi or ""
        author = article.authors[0].full_name
        title = article.primary_title
        doi = article.doi or ""
        return f"{author}. {title}. {doi}".strip()
