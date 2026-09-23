from inspect import signature

from app.automation.mls_page import MlsPage, _replace_media_placeholders


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


def test_mls_page_replaces_table_placeholders_before_pasting() -> None:
    html = "<p>Antes</p><!-- FIGURE:2 --><!-- TABLE:6 --><p>Después</p>"

    replaced = _replace_media_placeholders(html)

    assert "Figure_2.PNG" in replaced
    assert "Table_6.PNG" in replaced
    assert 'style="max-width: 700px; max-height: 600px;"' in replaced
    assert "<!-- TABLE:6 -->" not in replaced
