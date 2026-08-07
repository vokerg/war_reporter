"""Final fail-closed hardening for records entering the public archive."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlparse


def _netloc(parsed) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    return host if port is None else f"{host}:{port}"


def _provenance_url(value: Any) -> str:
    parsed = urlparse(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return parsed._replace(
        netloc=_netloc(parsed),
        params="",
        query="",
        fragment="",
    ).geturl()


def _redacted_public_url(value: Any, platform: str) -> str:
    parsed = urlparse(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    path = parsed.path if platform in {"telegram", "x"} else "/"
    return parsed._replace(
        netloc=_netloc(parsed),
        path=path or "/",
        params="",
        query="",
        fragment="",
    ).geturl()


def _redacted_id(item: dict[str, Any]) -> str:
    material = "\n".join(
        (
            str(item.get("source") or ""),
            str(item.get("platform") or ""),
            _provenance_url(item.get("url")),
            str(item.get("published_at") or ""),
        )
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def harden_public_projection(
    projected: dict[str, Any],
    item: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Remove content-derived metadata for permanently redacted records."""
    redact_tags = {str(tag) for tag in settings.get("public_redact_tags", [])}
    item_tags = {str(tag) for tag in item.get("tags", [])}
    if not redact_tags.intersection(item_tags):
        return projected

    result = dict(projected)
    base_raw = projected.get("raw")
    platform = (
        dict(base_raw.get("platform", {}))
        if isinstance(base_raw, dict) and isinstance(base_raw.get("platform"), dict)
        else {}
    )
    platform_name = str(item.get("platform") or "")
    if platform_name == "rss":
        platform = {}
    elif platform_name == "web":
        platform = {
            key: value
            for key, value in platform.items()
            if key == "content_type"
        }

    result["id"] = _redacted_id(item)
    result["url"] = _redacted_public_url(item.get("url"), platform_name)
    result["title"] = ""
    result["text"] = ""
    result["html"] = ""
    result["media"] = []
    result["author"] = ""
    result["raw"] = {
        "archive_policy": "public_redacted_v1",
        "redacted": True,
        "platform": platform,
    }
    return result
