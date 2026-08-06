"""Final fail-closed hardening for records entering the public archive."""

from __future__ import annotations

from typing import Any


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
    result["title"] = ""
    result["text"] = ""
    result["html"] = ""
    result["media"] = []
    result["raw"] = {
        "archive_policy": "public_redacted_v1",
        "redacted": True,
        "platform": platform,
    }
    return result
