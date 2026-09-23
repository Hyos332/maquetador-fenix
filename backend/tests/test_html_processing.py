from pathlib import Path

from lxml import html

from app.models.article import Article, ArticleTable, Author, Figure, Section
from app.services.docx_parser import ParagraphBlock, ParsedDocument, TableBlock
from app.models.pipeline import PipelineStatus
from app.services.html_renderer import IntermediateHtmlRenderer
from app.services.html_processor import HtmlProcessor
from app.services.journal_config import JournalConfigService
from app.services.section_extractor import SectionExtractor
from app.services.table_image_extractor import TableImageExtractor
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
    assert rendered.count('class="figure-grid"') == 1
    assert 'style="max-width: 700px; max-height: 600px;"' in rendered
    assert "Condición A" in rendered


def test_renderer_keeps_table_captures_centered_at_mls_image_size() -> None:
    journal = JournalConfigService().load("mlser")
    article = Article(
        journal="mlser",
        title_es="Artículo con tabla capturada",
        authors=[Author(full_name="Ana Test")],
        sections=[
            Section(
                title="Resultados",
                html_content="<p>Antes</p>\n<!-- TABLE:1 -->\n<p>Después</p>",
            )
        ],
        tables=[
            ArticleTable(
                number=1,
                html_content="<table></table>",
                output_filename="Table_1.PNG",
                block_index=10,
            )
        ],
    )

    rendered = IntermediateHtmlRenderer().render(article, journal)
    root = html.fromstring(rendered)

    image = root.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' table-image ')]//img")[0]
    assert image.get("src") == "Table_1.PNG"
    assert image.get("style") == "max-width: 700px; max-height: 600px;"


def test_section_extractor_preserves_group_caption_before_figure_grid() -> None:
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            ParagraphBlock(index=1, text="Resultados"),
            ParagraphBlock(index=2, text="Figura 2"),
            ParagraphBlock(index=3, text="Subtítulo de la figura compuesta"),
            TableBlock(
                index=4,
                rows=(("Condición A", "Condición B"),),
                image_relationship_ids=("rFigureA", "rFigureB"),
                image_cell_positions=((0, 0), (0, 1)),
            ),
            ParagraphBlock(index=5, text="Nota: elaboración propia."),
        ),
        image_relationships={},
        chart_relationships={},
    )
    figures = [
        Figure(
            number=1,
            source=Path("word/media/a.png"),
            output_filename="Figure_1.PNG",
            caption="Figura 2. Condición A",
            block_index=3,
            caption_block_index=1,
            group_id="figure-table-3",
            group_row=0,
            group_col=0,
        ),
        Figure(
            number=2,
            source=Path("word/media/b.png"),
            output_filename="Figure_2.PNG",
            caption="Figura 2. Condición B",
            block_index=3,
            caption_block_index=1,
            group_id="figure-table-3",
            group_row=0,
            group_col=1,
        ),
    ]

    section = SectionExtractor().extract(parsed, figures=figures)[0]

    assert '<p class="figure-caption"><i>Figura 2</i></p>' in section.html_content
    assert '<p class="figure-subtitle"><i>Subtítulo de la figura compuesta</i></p>' in section.html_content
    assert section.html_content.index("Figura 2") < section.html_content.index("<!-- FIGURE:1 -->")
    assert section.html_content.index("Subtítulo") < section.html_content.index("<!-- FIGURE:1 -->")
    assert section.html_content.index("<!-- FIGURE:2 -->") < section.html_content.index("Nota: elaboración")


def test_section_extractor_preserves_text_rows_around_media_table() -> None:
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            ParagraphBlock(index=1, text="Resultados"),
            ParagraphBlock(index=2, text="Figura 2"),
            TableBlock(
                index=3,
                rows=(
                    ("Aumento de la sensibilidad a las condiciones iniciales", ""),
                    ("Condición A", "Condición B"),
                    ("Nota: elaboración propia.", ""),
                ),
                image_relationship_ids=("rFigureA", "rFigureB"),
                image_cell_positions=((1, 0), (1, 1)),
            ),
        ),
        image_relationships={},
        chart_relationships={},
    )
    figures = [
        Figure(
            number=1,
            source=Path("word/media/a.png"),
            output_filename="Figure_1.PNG",
            caption="Figura 2. Condición A",
            block_index=2,
            caption_block_index=1,
            group_id="figure-table-2",
            group_row=0,
            group_col=0,
        ),
        Figure(
            number=2,
            source=Path("word/media/b.png"),
            output_filename="Figure_2.PNG",
            caption="Figura 2. Condición B",
            block_index=2,
            caption_block_index=1,
            group_id="figure-table-2",
            group_row=0,
            group_col=1,
        ),
    ]

    section = SectionExtractor().extract(parsed, figures=figures)[0]

    assert section.html_content.index("Aumento de la sensibilidad") < section.html_content.index("<!-- FIGURE:1 -->")
    assert section.html_content.index("<!-- FIGURE:2 -->") < section.html_content.index("Nota: elaboración propia.")


def test_table_image_extractor_captures_body_tables_only() -> None:
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            TableBlock(index=1, rows=(("Resumen", "Texto"),)),
            ParagraphBlock(index=2, text="Introducción"),
            ParagraphBlock(index=3, text="Texto previo."),
            TableBlock(index=4, rows=(("Celda A", "Celda B"), ("Celda C", "Celda D"))),
            ParagraphBlock(index=5, text="Referencias"),
            TableBlock(index=6, rows=(("No", "capturar"),)),
        ),
        image_relationships={},
        chart_relationships={},
    )

    result = TableImageExtractor().extract_tables(parsed)

    assert len(result.tables) == 1
    assert result.tables[0].output_filename == "Table_1.PNG"
    assert result.tables[0].block_index == 3
