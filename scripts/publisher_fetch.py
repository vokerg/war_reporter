"""Publisher-domain policy for article retrieval and redirect traversal."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import requests

try:
    from .collector_common import (
        CollectionError,
        _article_fields,
        ensure_public_url,
    )
except ImportError:
    from collector_common import (
        CollectionError,
        _article_fields,
        ensure_public_url,
    )


_SERVICE_PREFIXES = {"www", "rss", "feed", "feeds", "api"}


def _host(value: Any) -> str | None:
    parsed = urlparse(str(value or "").strip())
    return parsed.hostname.rstrip(".").lower() if parsed.hostname else None


def _publisher_domains(
    source: dict[str, Any], settings: dict[str, Any]
) -> set[str]:
    domains: set[str] = set()
    source_host = _host(source.get("url"))
    if source_host:
        domains.add(source_host)
        labels = source_host.split(".")
        if len(labels) >= 3 and labels[0] in _SERVICE_PREFIXES:
            domains.add(".".join(labels[1:]))

    configured = settings.get("article_host_allowlist", {})
    if isinstance(configured, dict):
        configured = configured.get(str(source.get("id", "")), [])
    else:
        configured = []
    source_hosts = source.get("article_hosts", [])
    for raw in list(configured or []) + list(source_hosts or []):
        candidate = str(raw).strip().rstrip(".").lower()
        if candidate and "/" not in candidate and ":" not in candidate:
            domains.add(candidate)
    return domains


def publisher_url_allowed(
    source: dict[str, Any], settings: dict[str, Any], url: str
) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    hostname = parsed.hostname.rstrip(".").lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in _publisher_domains(source, settings)
    )


def publisher_get(
    session: requests.Session,
    source: dict[str, Any],
    settings: dict[str, Any],
    url: str,
    *,
    timeout: int,
) -> requests.Response:
    """Fetch one publisher URL while enforcing the domain policy per hop."""
    current = url
    for _ in range(6):
        if not publisher_url_allowed(source, settings, current):
            raise CollectionError("publisher host is not allowed")
        ensure_public_url(current)
        response = session.get(
            current,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                return response
            current = urljoin(current, location)
            continue
        return response
    raise CollectionError("too many publisher redirects")


def extract_publisher_article(
    session: requests.Session,
    source: dict[str, Any],
    settings: dict[str, Any],
    url: str,
    timeout: int,
) -> tuple[str, str, str, list[str], str | None, str]:
    response = publisher_get(
        session,
        source,
        settings,
        url,
        timeout=timeout,
    )
    response.raise_for_status()
    return _article_fields(response)
