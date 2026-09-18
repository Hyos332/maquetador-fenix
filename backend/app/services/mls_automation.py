from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.automation.mls_page import MlsPage
from app.config.settings import Settings
from app.models.article import Article, ArticleLanguage


class MlsAutomationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_html(self, article: Article, output_path: Path) -> Path:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.settings.playwright_headless)
            try:
                mls_page = MlsPage.create(
                    browser=browser,
                    base_url=self.settings.maquetador_url,
                    downloads_dir=output_path.parent,
                )
                mls_page.open()
                mls_page.select_language(_maquetador_language(article.language))
                mls_page.fill_article(article)
                return mls_page.generate_and_download_html(output_path)
            finally:
                browser.close()


def _maquetador_language(language: ArticleLanguage) -> str:
    return {
        ArticleLanguage.ENGLISH: "English",
        ArticleLanguage.PORTUGUESE: "Português",
        ArticleLanguage.SPANISH: "Español",
    }.get(language, "Español")
