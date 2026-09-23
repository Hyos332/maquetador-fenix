from __future__ import annotations

import base64
import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree, html

from app.exceptions import HtmlValidationError
from app.models.article import Article
from app.models.journal import JournalConfig
from app.utils.dates import format_short_spanish_date
from app.utils.files import ensure_directory

URL_PATTERN = re.compile(r"https?://[^\s<)]+", re.IGNORECASE)
GENERIC_CITATION_MARKERS = (
    "como citar este articulo",
    "como citar este artículo",
    "mundet",
    "peña muñoz",
    "10.29314/mlser",
)


@dataclass(frozen=True)
class HtmlProcessResult:
    output_path: Path
    warnings: list[str] = field(default_factory=list)


class HtmlProcessor:
    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        article: Article,
        journal: JournalConfig,
    ) -> HtmlProcessResult:
        ensure_directory(output_path.parent)
        root = html.fromstring(input_path.read_text(encoding="utf-8"))
        warnings: list[str] = []

        self._localize_stylesheets(root)
        self._apply_journal_assets(root, journal)
        warnings.extend(self._extract_base64_images(root, output_path.parent))
        self._apply_figure_policy(root, journal)
        self._linkify_urls(root)
        self._normalize_orcid_links(root)
        root = self._remove_generic_citation_with_rollback(root, article)

        output_html = etree.tostring(root, encoding="unicode", method="html", pretty_print=True)
        output_html = self._restore_article_dates(output_html, article)
        output_path.write_text(output_html, encoding="utf-8")
        return HtmlProcessResult(output_path=output_path, warnings=warnings)

    def _localize_stylesheets(self, root: html.HtmlElement) -> None:
        for link in root.xpath("//link[contains(concat(' ', normalize-space(@rel), ' '), ' stylesheet ')]"):
            href = link.get("href", "")
            if href.startswith(("http://", "https://")) or href:
                link.set("href", "galleys.css")

    def _apply_journal_assets(self, root: html.HtmlElement, journal: JournalConfig) -> None:
        for image in root.xpath("//img[@src]"):
            source = Path(image.get("src", "")).name.casefold()
            image_class = image.get("class", "").casefold()
            if "logo" not in image_class and source != "logos-null.svg":
                continue
            image.set("src", journal.logo)
            if "journal-logo" not in image_class:
                image.set("class", f"{image.get('class', '').strip()} journal-logo".strip())

    def _restore_article_dates(self, html_content: str, article: Article) -> str:
        dates = [
            format_short_spanish_date(article.received_date),
            format_short_spanish_date(article.reviewed_date),
            format_short_spanish_date(article.accepted_date),
        ]
        for date_text in dates:
            if date_text:
                html_content = html_content.replace("00/00/0000", date_text, 1)
        return html_content

    def _normalize_orcid_links(self, root: html.HtmlElement) -> None:
        for link in root.xpath("//a[contains(@href, 'orcid.org/')]"):
            href = link.get("href", "")
            normalized = _normalize_orcid_url(href)
            if not normalized:
                continue
            link.set("href", normalized)
            if link.text and "orcid.org/" in link.text:
                link.text = normalized

    def _extract_base64_images(self, root: html.HtmlElement, output_dir: Path) -> list[str]:
        warnings: list[str] = []
        image_number = self._next_figure_number(root)

        for image in root.xpath("//img[starts-with(@src, 'data:image/')]"):
            source = image.get("src", "")
            try:
                header, payload = source.split(",", 1)
                extension = "PNG" if "png" in header.lower() else "PNG"
                filename = f"Figure_{image_number}.{extension}"
                (output_dir / filename).write_bytes(base64.b64decode(payload))
                image.set("src", filename)
                image_number += 1
            except (ValueError, base64.binascii.Error) as exc:
                warnings.append(f"Could not extract base64 image: {exc}")

        return warnings

    def _next_figure_number(self, root: html.HtmlElement) -> int:
        highest = 0
        for image in root.xpath("//img[@src]"):
            match = re.search(r"Figure_(\d+)\.PNG", image.get("src", ""), flags=re.I)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def _apply_figure_policy(self, root: html.HtmlElement, journal: JournalConfig) -> None:
        for image in root.xpath("//img[@src]"):
            source = Path(image.get("src", "")).name
            if not source.lower().startswith("figure_"):
                continue
            if _has_ancestor_class(image, "figure-grid"):
                image.set("style", "max-width: 100%; height: auto;")
                continue
            image.set("style", journal.image_style.html_style)

    def _linkify_urls(self, root: html.HtmlElement) -> None:
        for element in list(root.iter()):
            if element.tag == "a":
                continue
            if element.text:
                self._replace_text_with_links(element, "text")
            for child in list(element):
                if child.tail:
                    self._replace_text_with_links(child, "tail")

    def _replace_text_with_links(self, element: html.HtmlElement, attribute: str) -> None:
        text = getattr(element, attribute)
        if not text or not URL_PATTERN.search(text):
            return

        parent = element if attribute == "text" else element.getparent()
        if parent is None:
            return

        parts = []
        last = 0
        for match in URL_PATTERN.finditer(text):
            if match.start() > last:
                parts.append(text[last : match.start()])
            url = match.group(0).rstrip(".,;")
            trailing = match.group(0)[len(url) :]
            link = html.Element("a", href=url, target="_blank")
            link.text = url
            parts.append(link)
            if trailing:
                parts.append(trailing)
            last = match.end()
        if last < len(text):
            parts.append(text[last:])

        if attribute == "text":
            element.text = ""
            insertion_parent = element
            insert_at = 0
        else:
            element.tail = ""
            insertion_parent = parent
            insert_at = list(parent).index(element) + 1

        pending_text_target = element if attribute == "text" else element
        for part in parts:
            if isinstance(part, str):
                if attribute == "text" and insert_at == 0 and not len(insertion_parent):
                    pending_text_target.text = (pending_text_target.text or "") + part
                else:
                    if insert_at == 0 and attribute == "text":
                        insertion_parent.text = (insertion_parent.text or "") + part
                    else:
                        previous = insertion_parent[insert_at - 1] if insert_at > 0 else None
                        if previous is not None:
                            previous.tail = (previous.tail or "") + part
                        else:
                            insertion_parent.text = (insertion_parent.text or "") + part
                continue

            insertion_parent.insert(insert_at, part)
            insert_at += 1

    def _remove_generic_citation_with_rollback(
        self,
        root: html.HtmlElement,
        article: Article,
    ) -> html.HtmlElement:
        original = copy.deepcopy(root)

        for node in self._generic_citation_candidates(root):
            if not self._is_safe_generic_node(node, article):
                continue
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)

        if not self._critical_content_exists(root, article):
            return original

        return root

    def _generic_citation_candidates(self, root: html.HtmlElement) -> list[html.HtmlElement]:
        candidates = []
        for node in root.xpath("//*"):
            normalized = _normalize_text(node.text_content())
            if any(marker in normalized for marker in GENERIC_CITATION_MARKERS):
                candidates.append(node)
        return sorted(candidates, key=lambda candidate: len(candidate.text_content()))

    def _is_safe_generic_node(self, node: html.HtmlElement, article: Article) -> bool:
        text = node.text_content()
        if len(text) > 700:
            return False

        forbidden_values = [article.primary_title, *(author.full_name for author in article.authors)]
        forbidden_values.extend(author.email for author in article.authors if author.email)
        forbidden_values.extend(
            format_short_spanish_date(value)
            for value in (article.received_date, article.reviewed_date, article.accepted_date)
            if value
        )

        normalized_text = _normalize_text(text)
        return not any(value and _normalize_text(value) in normalized_text for value in forbidden_values)

    def _critical_content_exists(self, root: html.HtmlElement, article: Article) -> bool:
        text = _normalize_text(root.text_content())
        required = [article.primary_title, *(author.full_name for author in article.authors)]
        required.extend(author.email for author in article.authors if author.email)

        missing = [value for value in required if value and _normalize_text(value) not in text]
        if missing:
            raise HtmlValidationError(f"Critical HTML content disappeared: {missing}")
        return True


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_orcid_url(value: str) -> str | None:
    match = re.search(r"(\d{4}-\d{4}-\d{4}-[\dX]{4})", value, flags=re.I)
    if not match:
        return None
    return f"https://orcid.org/{match.group(1).upper()}"


def _has_ancestor_class(element: html.HtmlElement, class_name: str) -> bool:
    for ancestor in element.iterancestors():
        classes = ancestor.get("class", "").split()
        if class_name in classes:
            return True
    return False
