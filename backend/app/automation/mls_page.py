from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Browser, Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from app.exceptions import AutomationError
from app.models.article import Article, Author, Section

FIGURE_PLACEHOLDER_PATTERN = re.compile(r"<!--\s*FIGURE:(\d+)\s*-->")

SECTION_TITLE_PLACEHOLDERS = {
    "Español": "Título del bloque",
    "English": "Block title",
    "Portugese": "Título do bloco",
}

TITLE_PLACEHOLDERS = {
    "Español": ("Aquí va el título en español", "Here goes the title in English"),
    "English": ("Here goes the title in English",),
    "Portugese": ("Aqui está o título em português", "Here goes the title in English"),
}

ABSTRACT_PLACEHOLDERS = {
    "Español": ("El resumen debe tener entre 200 y 250 palabras", "The summary must have between 200 and 250 words"),
    "English": ("The summary must have between 200 and 250 words",),
    "Portugese": ("O resumo deve ter entre 200 e 250 palavras", "The summary must have between 200 and 250 words"),
}

KEYWORD_PREFIXES = {
    "Español": ("Palabra Clave", "Keyword"),
    "English": ("Keyword",),
    "Portugese": ("Palavra chave", "Keyword"),
}

ADD_BLOCK_BUTTONS = {
    "Español": "Añadir Bloque",
    "English": "Add Block",
    "Portugese": "Adicionar Bloco",
}

GENERATE_BUTTONS = {
    "Español": "Generar Html",
    "English": "Generate Document",
    "Portugese": "Gerar Documento",
}

DEFAULT_COUNTRIES = {
    "Español": "España",
    "English": "Spain",
    "Portugese": "Espanha",
}


class MlsPage:
    """Page Object for the external MLS maquetador SPA."""

    def __init__(self, page: Page, base_url: str, timeout_ms: int = 15_000) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout_ms = timeout_ms
        self.language = "Español"

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
        self.language = language

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
        self._fill("#country", self._author_country(author))
        self._fill("#orcid", author.orcid or "")

    def fill_citation(self, article: Article) -> None:
        citation = self._build_citation(article)
        self._fill("#cite", citation)

    def fill_titles(self, title_es: str, title_en: str) -> None:
        values = {
            "Aquí va el título en español": title_es,
            "Aqui está o título em português": title_es,
            "Here goes the title in English": title_en,
        }
        for placeholder in TITLE_PLACEHOLDERS.get(self.language, TITLE_PLACEHOLDERS["Español"]):
            self._fill_by_placeholder(placeholder, values.get(placeholder, ""))

    def fill_abstracts(self, abstract_es: str, abstract_en: str) -> None:
        values = {
            "El resumen debe tener entre 200 y 250 palabras": abstract_es,
            "O resumo deve ter entre 200 e 250 palavras": abstract_es,
            "The summary must have between 200 and 250 words": abstract_en,
        }
        for placeholder in ABSTRACT_PLACEHOLDERS.get(self.language, ABSTRACT_PLACEHOLDERS["Español"]):
            self._fill_by_placeholder(placeholder, values.get(placeholder, ""))

    def fill_keywords(self, keywords_es: list[str], keywords_en: list[str]) -> None:
        values = {
            "Palabra Clave": keywords_es,
            "Palavra chave": keywords_es,
            "Keyword": keywords_en,
        }
        for prefix in KEYWORD_PREFIXES.get(self.language, KEYWORD_PREFIXES["Español"]):
            self._fill_keyword_group(prefix, values.get(prefix, []))

    def fill_sections(self, sections: list[Section]) -> None:
        self._ensure_section_count(len(sections))

        title_inputs = self.page.locator(f'input[placeholder="{self._section_title_placeholder}"]')
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
                self.page.get_by_role("button", name=self._generate_button, exact=True).click()
            download = download_info.value
            download.save_as(str(output_path))
        except PlaywrightTimeoutError as exc:
            raise AutomationError("MLS maquetador did not download generated HTML in time.") from exc

        return output_path

    def _ensure_section_count(self, required_count: int) -> None:
        title_inputs = self.page.locator(f'input[placeholder="{self._section_title_placeholder}"]')
        current = title_inputs.count()
        add_block = self.page.get_by_role("button", name=self._add_block_button, exact=True)
        while current < required_count:
            add_block.click()
            current += 1
            expect(title_inputs.nth(current - 1)).to_be_visible()

    def _fill_keyword_group(self, placeholder_prefix: str, values: list[str]) -> None:
        for index, value in enumerate(values[:5], start=1):
            placeholder = f"{placeholder_prefix} {index}"
            self._fill_by_placeholder(placeholder, value)

    def _editors(self) -> Locator:
        editors = self.page.locator(
            '.ck-editor__editable[contenteditable="true"]:not(.ck-editor__nested-editable)'
        )
        if editors.count() == 0:
            raise AutomationError("No CKEditor editable blocks were found in MLS maquetador.")
        return editors

    def _set_editor_html(self, editor: Locator, html_content: str) -> None:
        html_content = _replace_figure_placeholders(html_content)
        editor.scroll_into_view_if_needed()
        editor.click()
        editor.evaluate(
            """(element, html) => {
                if (element.ckeditorInstance) {
                    element.ckeditorInstance.setData(html);
                } else {
                    element.innerHTML = html;
                }
                element.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    inputType: 'insertHTML',
                    data: null
                }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            html_content,
        )

    def _fill(self, selector: str, value: str) -> None:
        self.page.locator(selector).fill(value)

    def _fill_by_placeholder(self, placeholder: str, value: str) -> None:
        locator = self.page.get_by_placeholder(placeholder).first
        locator.wait_for(state="attached", timeout=self.timeout_ms)
        if locator.is_visible():
            locator.fill(value)
            return

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

    @property
    def _section_title_placeholder(self) -> str:
        return SECTION_TITLE_PLACEHOLDERS.get(self.language, SECTION_TITLE_PLACEHOLDERS["Español"])

    @property
    def _add_block_button(self) -> str:
        return ADD_BLOCK_BUTTONS.get(self.language, ADD_BLOCK_BUTTONS["Español"])

    @property
    def _generate_button(self) -> str:
        return GENERATE_BUTTONS.get(self.language, GENERATE_BUTTONS["Español"])

    def _author_country(self, author: Author) -> str:
        if author.country:
            return author.country

        if author.institution and "," in author.institution:
            country = author.institution.rsplit(",", 1)[-1].strip()
            if country:
                return country

        return DEFAULT_COUNTRIES.get(self.language, DEFAULT_COUNTRIES["Español"])


def _replace_figure_placeholders(html_content: str) -> str:
    def replace(match: re.Match[str]) -> str:
        number = int(match.group(1))
        filename = f"Figure_{number}.PNG"
        return (
            f'<p class="figure"><img src="{filename}" alt="Figure {number}" '
            'style="max-width:700px; max-height:600px; width:auto; height:auto;"></p>'
        )

    return FIGURE_PLACEHOLDER_PATTERN.sub(replace, html_content)
