from pathlib import Path

from lxml import html

from app.models.article import Article, Author, Figure, Section
from app.models.pipeline import PipelineStatus
from app.services.html_renderer import IntermediateHtmlRenderer
from app.services.html_processor import HtmlProcessor
from app.services.journal_config import JournalConfigService
from app.services.validator import Validator
from app.tests_helpers import build_alberto_article


def test_html_renderer_processor_and_validator_keep_critical_header(tmp_path: Path) -> None:
    article, intermediate_html, assets_dir = build_alberto_article(tmp_path)
    journal = JournalConfigService().load(article.journal)

    unsafe_extra = """
    <aside class="generic-citation">
      <h2>Como citar este artículo:</h2>
      <p>Mundet Peña Muñoz 10.29314/mlser.v5i2.531</p>
    </aside>
    """
    intermediate_html.write_text(
        intermediate_html.read_text(encoding="utf-8").replace("</article>", unsafe_extra + "</article>"),
        encoding="utf-8",
    )

    output_path = tmp_path / "processed.html"
    result = HtmlProcessor().process_file(intermediate_html, output_path, article, journal)
    validation = Validator().validate_html(result.output_path, article, journal, assets_dir=assets_dir)

    assert validation.ok, validation.errors
    processed_text = output_path.read_text(encoding="utf-8")
    assert "Como citar este artículo" not in processed_text
    assert "Mundet" not in processed_text
    assert article.primary_title in processed_text
    assert article.authors[0].email in processed_text

    root = html.fromstring(processed_text)
    assert root.xpath("//table[contains(concat(' ', normalize-space(@class), ' '), ' header-table ')]")
    assert root.xpath("//div[@id='article-title']//*[contains(@class, 'center-text')]")
    assert not root.xpath("//header[contains(concat(' ', normalize-space(@class), ' '), ' journal-header ')]")


def test_pipeline_generates_valid_postprocessed_html(tmp_path: Path) -> None:
    from app.config.settings import Settings
    from app.pipeline.article_pipeline import ArticlePipeline

    fixture = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")
    settings = Settings(
        workspaces_dir=tmp_path / "workspaces",
        deliveries_dir=tmp_path / "deliveries",
        dry_run=True,
    )
    result = ArticlePipeline(settings).run(fixture)

    assert result.html_path is not None
    assert result.html_path.exists()
    assert result.status in {PipelineStatus.COMPLETED, PipelineStatus.NEEDS_REVIEW}

    root = html.fromstring(result.html_path.read_text(encoding="utf-8"))
    figure_sources = [Path(image.get("src")).name for image in root.xpath("//img[@src]")]
    assert "Figure_1.PNG" in figure_sources
    assert not root.xpath("//img[starts-with(@src, 'data:image/')]")

    rendered_html = result.html_path.read_text(encoding="utf-8")
    references_index = rendered_html.index('<p class="title">Referencias</p>')
    assert rendered_html.index("Figure_1.PNG") < references_index
    assert rendered_html.index("Figure_7.PNG") < references_index


def test_renderer_keeps_multi_image_table_as_figure_grid() -> None:
    journal = JournalConfigService().load("mlser")
    article = Article(
        journal="mlser",
        title_es="Artículo con figura compuesta",
        authors=[Author(full_name="Ana Test")],
        sections=[
            Section(
                title="Resultados",
                html_content=(
                    "<p>Antes</p>\n"
                    "<!-- FIGURE:1 -->\n"
                    "<!-- FIGURE:2 -->\n"
                    "<!-- FIGURE:3 -->\n"
                    "<!-- FIGURE:4 -->\n"
                    "<p>Después</p>"
                ),
            )
        ],
        figures=[
            Figure(
                number=1,
                source=Path("word/media/a.png"),
                output_filename="Figure_1.PNG",
                caption="Figura 2. Condición A",
                block_index=1,
                group_id="figure-table-1",
                group_row=0,
                group_col=0,
            ),
            Figure(
                number=2,
                source=Path("word/media/b.png"),
                output_filename="Figure_2.PNG",
                caption="Figura 2. Condición B",
                block_index=1,
                group_id="figure-table-1",
                group_row=0,
                group_col=1,
            ),
            Figure(
                number=3,
                source=Path("word/media/c.png"),
                output_filename="Figure_3.PNG",
                caption="Figura 2. Condición C",
                block_index=1,
                group_id="figure-table-1",
                group_row=1,
                group_col=0,
            ),
            Figure(
                number=4,
                source=Path("word/media/d.png"),
                output_filename="Figure_4.PNG",
                caption="Figura 2. Condición D",
                block_index=1,
                group_id="figure-table-1",
                group_row=1,
                group_col=1,
            ),
        ],
    )

    rendered = IntermediateHtmlRenderer().render(article, journal)
    root = html.fromstring(rendered)

    assert len(root.xpath("//table[contains(concat(' ', normalize-space(@class), ' '), ' figure-grid ')]")) == 1
    assert len(root.xpath("//table[contains(concat(' ', normalize-space(@class), ' '), ' figure-grid ')]//img")) == 4
    assert rendered.count("Figura 2</i>") == 1
