from datetime import date
from pathlib import Path
from zipfile import ZipFile

from lxml import html

from app.models.article import Article, ArticleLanguage, Author, Reference, Section
from app.services.docx_parser import DocxParser, ParagraphBlock, ParsedDocument, TableBlock, TableCell
from app.services.html_renderer import IntermediateHtmlRenderer
from app.services.journal_config import JournalConfigService
from app.services.reference_processor import ReferenceProcessor
from app.services.section_extractor import SectionExtractor
from app.services.table_image_extractor import TableImageExtractor

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

STYLES_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:docDefaults><w:rPrDefault><w:rPr/></w:rPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/><w:basedOn w:val="Heading2"/><w:rPr><w:i/></w:rPr>
  </w:style>
  <w:style w:type="character" w:styleId="Emphasis">
    <w:name w:val="Emphasis"/><w:rPr><w:i/></w:rPr>
  </w:style>
</w:styles>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""


def _paragraph(*runs: str, style: str | None = None, align: str | None = None) -> str:
    properties = ""
    if style or align:
        style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
        align_xml = f'<w:jc w:val="{align}"/>' if align else ""
        properties = f"<w:pPr>{style_xml}{align_xml}</w:pPr>"
    return f"<w:p>{properties}{''.join(runs)}</w:p>"


def _run(text: str, properties: str = "") -> str:
    run_properties = f"<w:rPr>{properties}</w:rPr>" if properties else ""
    return f'<w:r>{run_properties}<w:t xml:space="preserve">{text}</w:t></w:r>'


def _cell(content: str, properties: str = "") -> str:
    cell_properties = f"<w:tcPr>{properties}</w:tcPr>" if properties else ""
    return f"<w:tc>{cell_properties}{content}</w:tc>"


def _write_docx(path: Path, body: str) -> Path:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", STYLES_XML)
        archive.writestr("word/_rels/document.xml.rels", RELS_XML)
    return path


def test_parser_keeps_direct_and_style_formatting_as_inline_html(tmp_path: Path) -> None:
    docx = _write_docx(
        tmp_path / "formatting.docx",
        "".join(
            [
                _paragraph(_run("Diseño del estudio", "<w:b/><w:i/>")),
                _paragraph(_run("Participantes"), style="Heading3"),
                _paragraph(_run("Contexto"), style="Heading2"),
                _paragraph(
                    _run("Según "),
                    _run("Piaget", '<w:rStyle w:val="Emphasis"/>'),
                    _run(" (1970) el R"),
                    _run("2", '<w:vertAlign w:val="superscript"/>'),
                    _run(" es &lt;alto&gt;"),
                ),
                _paragraph(_run("No negrita", '<w:b w:val="0"/>'), style="Heading2"),
                _paragraph(_run("  Espacios ", "<w:b/>"), _run(" finales  ")),
            ]
        ),
    )

    blocks = DocxParser().parse(docx).blocks

    assert [block.html for block in blocks] == [
        "<i><strong>Diseño del estudio</strong></i>",
        "<i><strong>Participantes</strong></i>",
        "<strong>Contexto</strong>",
        "Según <i>Piaget</i> (1970) el R<sup>2</sup> es &lt;alto&gt;",
        "No negrita",
        "<strong>Espacios</strong> finales",
    ]
    for block in blocks:
        assert html.fromstring(f"<p>{block.html}</p>").text_content() == block.text


def test_parser_reads_merged_cells_alignment_and_nested_tables(tmp_path: Path) -> None:
    merged_table = (
        "<w:tbl>"
        "<w:tr>"
        + _cell(_paragraph(_run("Grupo", "<w:b/>"), align="center"), '<w:vMerge w:val="restart"/>')
        + _cell(_paragraph(_run("Resultados", "<w:b/>"), align="center"), '<w:gridSpan w:val="2"/>')
        + "</w:tr><w:tr>"
        + _cell(_paragraph(), "<w:vMerge/>")
        + _cell(_paragraph(_run("Pre")))
        + _cell(_paragraph(_run("Post")))
        + "</w:tr><w:tr>"
        + _cell(_paragraph(_run("A")))
        + _cell(_paragraph(_run("10"), align="right"))
        + _cell(_paragraph(_run("12")) + _paragraph(_run("±2")))
        + "</w:tr>"
        "</w:tbl>"
    )
    inner_table = "<w:tbl><w:tr>" + _cell(_paragraph(_run("x"))) + "</w:tr></w:tbl>"
    nested_table = "<w:tbl><w:tr>" + _cell(inner_table + "<w:p/>") + "</w:tr></w:tbl>"
    docx = _write_docx(tmp_path / "tables.docx", merged_table + nested_table)

    merged, nested = DocxParser().parse(docx).blocks

    assert isinstance(merged, TableBlock)
    header, subheader, body = merged.cells
    assert header == (
        TableCell(text="Grupo", html="<strong>Grupo</strong>", rowspan=2, align="center"),
        TableCell(text="Resultados", html="<strong>Resultados</strong>", colspan=2, align="center"),
    )
    assert [cell.text for cell in subheader] == ["Pre", "Post"]
    assert body[1].align == "right"
    assert body[2].html == "12<br>±2"
    assert merged.has_nested_table is False
    assert isinstance(nested, TableBlock)
    assert nested.has_nested_table is True


def test_section_extractor_keeps_subheading_and_inline_formatting() -> None:
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            ParagraphBlock(index=1, text="Método"),
            ParagraphBlock(index=2, text="Participantes", html="<i><strong>Participantes</strong></i>"),
            ParagraphBlock(index=3, text="Según Piaget la muestra", html="Según <i>Piaget</i> la muestra"),
            ParagraphBlock(index=4, text="Texto sin html <b>"),
            ParagraphBlock(index=5, text="Referencias"),
        ),
        image_relationships={},
        chart_relationships={},
    )

    section = SectionExtractor().extract(parsed)[0]

    assert section.html_content.split("\n") == [
        "<p><i><strong>Participantes</strong></i></p>",
        "<p>Según <i>Piaget</i> la muestra</p>",
        "<p>Texto sin html &lt;b&gt;</p>",
    ]


def test_captioned_complex_tables_stay_editable_and_render_merged_cells() -> None:
    complex_table = TableBlock(
        index=4,
        rows=(
            ("Grupo", "Resultados", "", "", "", "", ""),
            ("", "Pre", "Post", "Δ", "p", "d", ""),
            ("A", "10", "12", "2", "0.01", "0.4", ""),
        ),
        cells=(
            (
                TableCell(text="Grupo", html="<strong>Grupo</strong>", rowspan=2),
                TableCell(text="Resultados", html="<strong>Resultados</strong>", colspan=6, align="center"),
            ),
            tuple(TableCell(text=value, html=value) for value in ("Pre", "Post", "Δ", "p", "d", "")),
            tuple(TableCell(text=value, html=value) for value in ("A", "10", "12", "2", "0.01", "0.4", "")),
        ),
    )
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            ParagraphBlock(index=1, text="Resultados"),
            ParagraphBlock(index=2, text="Tabla 1"),
            ParagraphBlock(index=3, text="Comparación pre y post"),
            complex_table,
            ParagraphBlock(index=5, text="Referencias"),
        ),
        image_relationships={},
        chart_relationships={},
    )

    captured = TableImageExtractor().extract_tables(parsed)
    section = SectionExtractor().extract(parsed)[0]
    root = html.fromstring(f"<div>{section.html_content}</div>")

    assert captured.tables == []
    assert "<!-- TABLE:" not in section.html_content
    table = root.xpath("//table[contains(@class, 'data-table')]")[0]
    first_cells = table.xpath(".//tr[1]/*")
    assert first_cells[0].get("rowspan") == "2"
    assert first_cells[1].get("colspan") == "6"
    assert "text-align: center" in first_cells[1].get("style")
    assert first_cells[0].xpath("./strong/text()") == ["Grupo"]
    assert len(table.xpath(".//tr")) == 3


def test_only_figure_or_nested_tables_are_captured_as_images() -> None:
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            ParagraphBlock(index=1, text="Resultados"),
            ParagraphBlock(index=2, text="Figura 1"),
            ParagraphBlock(index=3, text="Esquema del relato"),
            TableBlock(index=4, rows=(("Inicio", "Nudo", "Desenlace"),)),
            ParagraphBlock(index=5, text="Texto intermedio."),
            ParagraphBlock(index=6, text="Otro párrafo."),
            ParagraphBlock(index=7, text="Más texto."),
            TableBlock(index=8, rows=(("Contenido", ""),), has_nested_table=True),
            ParagraphBlock(index=9, text="Párrafo."),
            ParagraphBlock(index=10, text="Párrafo dos."),
            ParagraphBlock(index=11, text="Párrafo tres."),
            TableBlock(index=12, rows=(("A", "", "C", "D", "E", "F", "G"), ("1", "2", "", "4", "5", "6", "7"))),
            ParagraphBlock(index=13, text="Referencias"),
        ),
        image_relationships={},
        chart_relationships={},
    )

    result = TableImageExtractor().extract_tables(parsed)

    assert [table.block_index for table in result.tables] == [3, 7]


def _bilingual_article(language: ArticleLanguage) -> Article:
    return Article(
        journal="mlser",
        language=language,
        title_es="Título en español",
        title_en="English title",
        abstract_es="Resumen del artículo.",
        abstract_en="Article abstract.",
        keywords_es=["educación"],
        keywords_en=["education"],
        authors=[Author(full_name="Ana Test")],
        sections=[Section(title="Introducción", html_content="<p>Texto</p>")],
    )


def _front_matter_sequence(rendered: str) -> list[str]:
    root = html.fromstring(rendered)
    sequence = []
    for node in root.xpath("//body//*[@id='article-title' or self::p]"):
        if node.get("class") == "title":
            break
        text = node.text_content().strip()
        if node.get("id") == "article-title":
            sequence.append(f"TITLE:{text}")
        elif text.startswith(("Resumen:", "Abstract:", "Palabras clave", "Keywords")):
            sequence.append(text.split(":")[0])
    return sequence


def test_spanish_article_puts_english_title_right_before_abstract() -> None:
    journal = JournalConfigService().load("mlser")

    rendered = IntermediateHtmlRenderer().render(_bilingual_article(ArticleLanguage.SPANISH), journal)

    assert _front_matter_sequence(rendered) == [
        "TITLE:Título en español",
        "Resumen",
        "Palabras clave",
        "TITLE:English title",
        "Abstract",
        "Keywords",
    ]


def test_english_article_puts_spanish_title_right_before_resumen() -> None:
    journal = JournalConfigService().load("mlser")

    rendered = IntermediateHtmlRenderer().render(_bilingual_article(ArticleLanguage.ENGLISH), journal)

    assert _front_matter_sequence(rendered) == [
        "TITLE:English title",
        "Abstract",
        "Keywords",
        "TITLE:Título en español",
        "Resumen",
        "Palabras clave",
    ]


def test_references_keep_italics_without_number_prefix() -> None:
    parsed = ParsedDocument(
        path=Path("article.docx"),
        blocks=(
            ParagraphBlock(index=1, text="Referencias"),
            ParagraphBlock(
                index=2,
                text="[1] García, F. (2003). Familia y escuela. CCS.",
                html="[1] García, F. (2003). <i>Familia y escuela</i>. CCS.",
            ),
        ),
        image_relationships={},
        chart_relationships={},
    )
    journal = JournalConfigService().load("mlser")

    references = ReferenceProcessor().extract(parsed)
    article = _bilingual_article(ArticleLanguage.SPANISH).model_copy(update={"references": references})
    rendered = IntermediateHtmlRenderer().render(article, journal)

    assert references[0].html == "García, F. (2003). <i>Familia y escuela</i>. CCS."
    assert '<p id="ref-1">García, F. (2003). <i>Familia y escuela</i>. CCS.</p>' in rendered


def test_references_without_html_are_escaped() -> None:
    journal = JournalConfigService().load("mlser")
    article = _bilingual_article(ArticleLanguage.SPANISH).model_copy(
        update={"references": [Reference(number=1, raw_text="Autor <script> (2020).")]}
    )

    rendered = IntermediateHtmlRenderer().render(article, journal)

    assert "Autor &lt;script&gt; (2020)." in rendered


def _dates_text(language: ArticleLanguage) -> str:
    journal = JournalConfigService().load("mlser")
    article = _bilingual_article(language).model_copy(
        update={
            "received_date": date(2023, 9, 27),
            "reviewed_date": date(2023, 12, 18),
            "accepted_date": date(2024, 2, 14),
        }
    )
    root = html.fromstring(IntermediateHtmlRenderer().render(article, journal))
    return " ".join(root.xpath("//p[contains(., '27/09/2023')]")[0].text_content().split())


def test_english_article_uses_english_date_labels() -> None:
    assert _dates_text(ArticleLanguage.ENGLISH) == (
        "Received: 27/09/2023 / Reviewed: 18/12/2023 / Accepted: 14/02/2024"
    )


def test_spanish_article_keeps_spanish_date_labels() -> None:
    assert _dates_text(ArticleLanguage.SPANISH) == (
        "Fecha de recepción: 27/09/2023 / Fecha de revisión: 18/12/2023 / "
        "Fecha de aceptación: 14/02/2024"
    )
