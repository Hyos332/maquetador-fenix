from inspect import signature

from app.automation.mls_page import MlsPage


def test_mls_page_exposes_small_page_object_methods() -> None:
    expected_methods = [
        "open",
        "select_language",
        "fill_author",
        "fill_titles",
        "fill_abstracts",
        "fill_keywords",
        "fill_sections",
        "fill_references",
        "generate_and_download_html",
    ]

    for method_name in expected_methods:
        assert hasattr(MlsPage, method_name)

    assert "article" in signature(MlsPage.fill_article).parameters
