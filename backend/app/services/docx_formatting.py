from __future__ import annotations

from dataclasses import dataclass
from html import escape
from zipfile import ZipFile

from lxml import etree

from app.utils.strings import WHITESPACE_PATTERN, clean_word_chars

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}
FALSE_TOGGLE_VALUES = {"0", "false", "off", "none"}
VERTICAL_ALIGNMENTS = {"superscript", "subscript"}
TEXT_NODES_XPATH = ".//w:t | .//w:tab | .//w:br | .//w:cr"


@dataclass(frozen=True)
class RunFormat:
    bold: bool = False
    italic: bool = False
    vertical: str = ""


@dataclass(frozen=True)
class _RunProperties:
    bold: bool | None = None
    italic: bool | None = None
    vertical: str | None = None

    def fill_from(self, other: _RunProperties) -> _RunProperties:
        return _RunProperties(
            bold=self.bold if self.bold is not None else other.bold,
            italic=self.italic if self.italic is not None else other.italic,
            vertical=self.vertical if self.vertical is not None else other.vertical,
        )


@dataclass(frozen=True)
class _Style:
    based_on: str | None
    properties: _RunProperties


class StyleResolver:
    def __init__(self, styles_root: etree._Element | None = None) -> None:
        self._styles: dict[str, _Style] = {}
        self._chains: dict[str | None, _RunProperties] = {}
        self._default_paragraph_style: str | None = None
        self._defaults = _RunProperties()
        if styles_root is None:
            return

        default_properties = styles_root.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
        self._defaults = _read_run_properties(default_properties)
        for style in styles_root.findall("w:style", NS):
            style_id = style.get(_w("styleId"))
            if not style_id:
                continue
            based_on = style.find("w:basedOn", NS)
            self._styles[style_id] = _Style(
                based_on=based_on.get(_w("val")) if based_on is not None else None,
                properties=_read_run_properties(style.find("w:rPr", NS)),
            )
            if style.get(_w("type")) == "paragraph" and style.get(_w("default")) in {"1", "true"}:
                self._default_paragraph_style = style_id

    @classmethod
    def from_archive(cls, archive: ZipFile) -> StyleResolver:
        try:
            return cls(etree.fromstring(archive.read("word/styles.xml")))
        except KeyError:
            return cls()

    def run_format(self, paragraph_style: str | None, run: etree._Element | None) -> RunFormat:
        direct = _RunProperties()
        character_style = None
        if run is not None:
            run_properties = run.find("w:rPr", NS)
            direct = _read_run_properties(run_properties)
            character_style_node = None
            if run_properties is not None:
                character_style_node = run_properties.find("w:rStyle", NS)
            if character_style_node is not None:
                character_style = character_style_node.get(_w("val"))

        resolved = (
            direct.fill_from(self._chain(character_style))
            .fill_from(self._chain(paragraph_style or self._default_paragraph_style))
            .fill_from(self._defaults)
        )
        return RunFormat(
            bold=bool(resolved.bold),
            italic=bool(resolved.italic),
            vertical=resolved.vertical or "",
        )

    def _chain(self, style_id: str | None) -> _RunProperties:
        if style_id in self._chains:
            return self._chains[style_id]

        resolved = _RunProperties()
        visited: set[str] = set()
        current = style_id
        while current and current not in visited and current in self._styles:
            visited.add(current)
            style = self._styles[current]
            resolved = resolved.fill_from(style.properties)
            current = style.based_on

        self._chains[style_id] = resolved
        return resolved


def paragraph_style_id(paragraph: etree._Element) -> str | None:
    style = paragraph.find("w:pPr/w:pStyle", NS)
    return style.get(_w("val")) if style is not None else None


def paragraph_alignment(paragraph: etree._Element) -> str:
    alignment = paragraph.find("w:pPr/w:jc", NS)
    value = alignment.get(_w("val"), "") if alignment is not None else ""
    if value == "center":
        return "center"
    if value in {"right", "end"}:
        return "right"
    return ""


def paragraph_inline_html(paragraph: etree._Element, resolver: StyleResolver) -> str:
    style_id = paragraph_style_id(paragraph)
    formats: dict[etree._Element | None, RunFormat] = {}
    segments: list[tuple[str, RunFormat]] = []
    for node in paragraph.xpath(TEXT_NODES_XPATH, namespaces=NS):
        text = node.text or "" if etree.QName(node).localname == "t" else " "
        run = node.getparent()
        if run is None or etree.QName(run).localname != "r":
            run = None
        if run not in formats:
            formats[run] = resolver.run_format(style_id, run)
        segments.append((text, formats[run]))
    return segments_to_html(segments)


def segments_to_html(segments: list[tuple[str, RunFormat]]) -> str:
    collapsed: list[list] = []
    previous_was_space = True
    for raw_text, run_format in segments:
        text = WHITESPACE_PATTERN.sub(" ", clean_word_chars(raw_text))
        if previous_was_space:
            text = text.lstrip(" ")
        if not text:
            continue
        previous_was_space = text.endswith(" ")
        if collapsed and collapsed[-1][1] == run_format:
            collapsed[-1][0] += text
        else:
            collapsed.append([text, run_format])

    while collapsed:
        collapsed[-1][0] = collapsed[-1][0].rstrip(" ")
        if collapsed[-1][0]:
            break
        collapsed.pop()

    return "".join(_render_segment(text, run_format) for text, run_format in collapsed)


def _render_segment(text: str, run_format: RunFormat) -> str:
    core = text.strip(" ")
    if not core:
        return text
    leading = " " if text.startswith(" ") else ""
    trailing = " " if text.endswith(" ") else ""
    content = escape(core, quote=False)
    if run_format.vertical == "superscript":
        content = f"<sup>{content}</sup>"
    elif run_format.vertical == "subscript":
        content = f"<sub>{content}</sub>"
    if run_format.bold:
        content = f"<strong>{content}</strong>"
    if run_format.italic:
        content = f"<i>{content}</i>"
    return f"{leading}{content}{trailing}"


def _read_run_properties(run_properties: etree._Element | None) -> _RunProperties:
    if run_properties is None:
        return _RunProperties()
    vertical_node = run_properties.find("w:vertAlign", NS)
    vertical = None
    if vertical_node is not None:
        value = vertical_node.get(_w("val"), "")
        vertical = value if value in VERTICAL_ALIGNMENTS else ""
    return _RunProperties(
        bold=_read_toggle(run_properties.find("w:b", NS)),
        italic=_read_toggle(run_properties.find("w:i", NS)),
        vertical=vertical,
    )


def _read_toggle(node: etree._Element | None) -> bool | None:
    if node is None:
        return None
    return node.get(_w("val"), "true").casefold() not in FALSE_TOGGLE_VALUES


def _w(name: str) -> str:
    return f"{{{WORD_NS}}}{name}"
