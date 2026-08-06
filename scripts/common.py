from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temp = Path(handle.name)
    temp.replace(path)


def stable_id(source: str, url: str, published_at: str | None, text: str) -> str:
    material = "\n".join((source, url, published_at or "", text)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def source_handle(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1].lstrip("@") if path else ""


def raw_path(root: Path, published_at: str | None, collected_at: str) -> Path:
    stamp = parse_time(published_at) or parse_time(collected_at) or utc_now()
    return root / f"{stamp:%Y/%m/%d}" / "items.ndjson"


def read_ndjson(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if isinstance(value, dict):
                rows.append(value)
    return rows


def append_unique(path: Path, items: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing.add(str(json.loads(line).get("id", "")))
            except json.JSONDecodeError:
                continue
    added = 0
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            item_id = str(item.get("id", ""))
            if not item_id or item_id in existing:
                continue
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing.add(item_id)
            added += 1
    return added


def env_int(name: str, fallback: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return fallback
    try:
        return max(1, int(raw))
    except ValueError:
        return fallback
