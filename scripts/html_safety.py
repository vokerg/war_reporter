"""Allowlist sanitizer for rendered report fragments."""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment

_ALLOWED_TAGS = {
    "a", "blockquote", "br", "code", "em", "h1", "h2", "h3", "h4",
    "h5", "h6", "hr", "li", "ol", "p", "pre", "strong", "table",
    "tbody", "td", "th", "thead", "tr", "ul",
}
_DROP_WITH_CONTENT = {
    "base", "button", "embed", "form", "iframe", "input", "link", "math",
    "meta", "object", "option", "script", "select", "style", "svg",
    "textarea",
}


def _safe_href(value: str) -> str | None:
    value = value.strip()
    if not value or any(ord(char) < 32 for char in value):
        return None
    parsed = urlparse(value)
    if parsed.scheme:
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        return value
    if value.startswith(("//", "\\", "#")):
        return None
    return value


def sanitize_report_html(fragment: str) -> str:
    """Remove active content and unsafe attributes from Markdown output."""
    soup = BeautifulSoup(fragment, "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in list(soup.find_all(True)):
        name = tag.name.lower()
        if name in _DROP_WITH_CONTENT:
            tag.decompose()
            continue
        if name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        attributes: dict[str, str] = {}
        if name == "a":
            href = _safe_href(str(tag.get("href") or ""))
            if href is not None:
                attributes["href"] = href
                if urlparse(href).scheme in {"http", "https"}:
                    attributes["rel"] = "noopener noreferrer"
            title = str(tag.get("title") or "").strip()
            if title:
                attributes["title"] = title[:300]
        elif name in {"td", "th"}:
            for key in ("colspan", "rowspan"):
                value = str(tag.get(key) or "")
                if value.isdigit() and 1 <= int(value) <= 100:
                    attributes[key] = value
        tag.attrs = attributes
    return str(soup)
