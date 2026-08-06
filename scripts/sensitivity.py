"""Conservative item-level tagging for precise operational locations."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_DECIMAL_PAIR = re.compile(
    r"(?<![\d.])(-?\d{2}\.\d{3,})\s*[,;/]\s*"
    r"(-?\d{2}\.\d{3,})(?![\d.])"
)
_DMS = re.compile(
    r"\b\d{1,2}\s*[°º]\s*\d{1,2}\s*['′]\s*"
    r"(?:\d{1,2}(?:\.\d+)?\s*[\"″]\s*)?[NSСЮ]\b.*?"
    r"\b\d{1,3}\s*[°º]\s*\d{1,2}\s*['′]\s*"
    r"(?:\d{1,2}(?:\.\d+)?\s*[\"″]\s*)?[EWВЗ]\b",
    re.IGNORECASE | re.DOTALL,
)
_MGRS = re.compile(
    r"\b(?:[1-5]?\d|60)[C-HJ-NP-X][A-HJ-NP-Z]{2}"
    r"\s*\d{4,10}\b",
    re.IGNORECASE,
)
_COORDINATE_WORD = re.compile(
    r"\b(?:coordinates?|grid|location|lat(?:itude)?|lon(?:gitude)?|"
    r"координат(?:и|ы|а)?|сітка|широта|довгота)\b",
    re.IGNORECASE,
)
_OPERATIONAL_WORD = re.compile(
    r"\b(?:position(?:s)?|deployment|unit|battery|launcher|command post|"
    r"позиці(?:я|ї|ях|ю)|позиц(?:ия|ии|иях)|підрозділ|подразделен(?:ие|ия)|"
    r"батаре(?:я|ї)|пусков(?:а|ой)|командн(?:ий|ый) пункт|дислокац(?:ія|ия))\b",
    re.IGNORECASE,
)


def _material(item: dict[str, Any]) -> str:
    values = [
        item.get("title"),
        item.get("text"),
        item.get("url"),
        *list(item.get("media") or []),
    ]
    return unicodedata.normalize(
        "NFKC", "\n".join(str(value or "") for value in values)
    )


def _decimal_coordinate_pair(text: str) -> bool:
    for match in _DECIMAL_PAIR.finditer(text):
        try:
            latitude = float(match.group(1))
            longitude = float(match.group(2))
        except ValueError:
            continue
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return True
    return False


def detected_sensitive_tags(item: dict[str, Any]) -> set[str]:
    """Return only high-confidence automatic tags; false negatives stay delayed."""
    text = _material(item)
    precise = bool(
        _decimal_coordinate_pair(text)
        or _DMS.search(text)
        or _MGRS.search(text)
    )
    if not precise:
        return set()
    tags = {"precise-location"}
    if _OPERATIONAL_WORD.search(text) or _COORDINATE_WORD.search(text):
        tags.add("operational-position")
    return tags


def classify_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with deterministic source and detected tags combined."""
    result = dict(item)
    existing = [str(tag) for tag in item.get("tags", [])]
    detected = sorted(detected_sensitive_tags(item) - set(existing))
    result["tags"] = existing + detected
    return result
