from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "tr", "table", "section", "article", "blockquote",
}
_SKIPPED_TAGS = {"script", "style"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS and tag != "li":
            # The next <li> starts its own line, so consecutive items stay on adjacent lines.
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            # Like a browser, treat source line breaks as spaces; only tags start new lines.
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str | None) -> str:
    """Convert posting HTML to plain text, keeping paragraph breaks and list items."""
    if not html:
        return ""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    return normalize_text("".join(extractor.parts))


def normalize_text(text: str | None) -> str:
    """Collapse runs of spaces and blank lines, and replace non-breaking spaces."""
    lines: list[str] = []
    for line in (text or "").replace("\xa0", " ").splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned or (lines and lines[-1]):
            lines.append(cleaned)
    return "\n".join(lines).strip()


def unescape_html(escaped: str | None) -> str:
    """Greenhouse returns HTML with its markup entity-escaped (&lt;p&gt;)."""
    return unescape(escaped or "")
