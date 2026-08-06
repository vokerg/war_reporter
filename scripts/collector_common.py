#!/usr/bin/env python3
"""Shared safety, extraction and public-projection primitives."""

from __future__ import annotations

import html as html_lib
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

try:
    from .common import (
        ROOT,
        append_unique,
        atomic_json,
        clean_text,
        env_int,
        iso,
        load_json,
        parse_time,
        raw_path,
        source_handle,
        stable_id,
        utc_now,
    )
except ImportError:
    from common import (
        ROOT,
        append_unique,
        atomic_json,
        clean_text,
        env_int,
        iso,
        load_json,
        parse_time,
        raw_path,
        source_handle,
        stable_id,
        utc_now,
    )

LOG = logging.getLogger("war-reporter.collect")


class CollectionError(RuntimeError):
    pass


def json_safe(value: Any) -> Any:
    """Return a JSON-serializable copy of untrusted platform payloads."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def ensure_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CollectionError(f"unsafe URL: {url}")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise CollectionError(f"private URL is not allowed: {url}")
    try:
        addresses = {
            row[4][0]
            for row in socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise CollectionError(f"DNS lookup failed for {hostname}: {exc}") from exc
    if not addresses:
        raise CollectionError(f"DNS lookup returned no addresses for {hostname}")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise CollectionError(f"private destination is not allowed: {url}")
    return url


def safe_get(
    session: requests.Session,
    url: str,
    *,
    timeout: int,
    params: dict[str, Any] | None = None,
    same_host_only: bool = False,
) -> requests.Response:
    current = url
    original_host = urlparse(url).hostname
    current_params = params
    for _ in range(6):
        ensure_public_url(current)
        response = session.get(
            current,
            params=current_params,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                return response
            redirected = urljoin(current, location)
            if (
                same_host_only
                and urlparse(redirected).hostname != original_host
            ):
                raise CollectionError(
                    f"cross-host redirect is not allowed: {url}"
                )
            current = redirected
            current_params = None
            continue
        return response
    raise CollectionError(f"too many redirects: {url}")


def session_for(source: dict[str, Any], settings: dict[str, Any]) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": settings["user_agent"],
            "Accept-Language": ",".join(source.get("languages", ["en"])),
        }
    )
    return session


def make_item(
    source: dict[str, Any],
    *,
    url: str,
    published_at: str | None,
    title: str = "",
    text: str = "",
    html: str = "",
    media: list[str] | None = None,
    author: str = "",
    raw: Any = None,
) -> dict[str, Any]:
    collected = iso()
    text = clean_text(text)
    title = clean_text(title)
    return {
        "id": stable_id(
            source["platform"] if source["platform"] == "x" else source["id"],
            url,
            published_at,
            text or title,
        ),
        "source": source["id"],
        "source_name": source["name"],
        "platform": source["platform"],
        "url": url,
        "published_at": published_at,
        "collected_at": collected,
        "title": title,
        "text": text,
        "html": html,
        "media": list(dict.fromkeys(media or [])),
        "author": clean_text(author),
        "language": (source.get("languages") or ["und"])[0],
        "group": source.get("group", "other"),
        "perspective": source.get("perspective", "unknown"),
        "trust": source.get("trust", "unknown"),
        "tags": source.get("tags", []),
        "raw": json_safe(raw),
    }


def public_projection(
    item: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    """Create the only record allowed to enter the public Git archive."""
    projected = dict(item)
    excerpt_limit = max(1, int(settings.get("public_excerpt_chars", 1200)))
    media_limit = max(0, int(settings.get("public_media_limit", 8)))
    text = str(item.get("text") or "")
    captured_html = str(item.get("html") or "")
    raw_payload = json_safe(item.get("raw"))
    fingerprint_material = json.dumps(
        {"text": text, "html": captured_html, "raw": raw_payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    minimal_platform: dict[str, Any] = {}
    if isinstance(raw_payload, dict):
        if item.get("platform") == "telegram":
            minimal_platform = {"post": raw_payload.get("post")}
        elif item.get("platform") == "x":
            tweet = raw_payload.get("tweet")
            minimal_platform = {
                "tweet_id": tweet.get("id") if isinstance(tweet, dict) else None,
                "collected_via": raw_payload.get("collected_via"),
            }
        elif item.get("platform") == "rss":
            minimal_platform = {
                "entry_id": raw_payload.get("id") or raw_payload.get("guid"),
                "entry_link": raw_payload.get("link"),
            }
        elif item.get("platform") == "web":
            minimal_platform = {
                "content_type": raw_payload.get("content_type"),
            }
    minimal_platform = {
        key: value for key, value in minimal_platform.items() if value is not None
    }

    redact_tags = set(settings.get("public_redact_tags", []))
    permanently_redacted = bool(
        redact_tags.intersection(str(tag) for tag in item.get("tags", []))
    )
    projected["text"] = "" if permanently_redacted else text[:excerpt_limit]
    projected["html"] = ""
    projected["media"] = (
        []
        if permanently_redacted
        else list(item.get("media") or [])[:media_limit]
    )
    projected["raw"] = {
        "archive_policy": "public_excerpt_v1",
        "content_sha256": hashlib.sha256(fingerprint_material).hexdigest(),
        "original_text_chars": len(text),
        "original_html_chars": len(captured_html),
        "text_truncated": len(text) > excerpt_limit,
        "media_count": len(item.get("media") or []),
        "platform": minimal_platform,
    }
    return projected


def _published_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = parse_time(value.strip())
    except (TypeError, ValueError):
        return None
    return iso(parsed) if parsed is not None else None


def extract_publication_time(soup: BeautifulSoup) -> str | None:
    meta_candidates = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "date"),
        ("name", "datePublished"),
        ("name", "publication_date"),
        ("itemprop", "datePublished"),
    ]
    for attribute, value in meta_candidates:
        node = soup.find("meta", attrs={attribute: value})
        if node is not None:
            published = _published_value(node.get("content"))
            if published:
                return published

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text() or "")
        except (TypeError, json.JSONDecodeError):
            continue
        stack = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key in ("datePublished", "dateCreated", "uploadDate"):
                    published = _published_value(current.get(key))
                    if published:
                        return published
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)

    for node in soup.find_all("time", attrs={"datetime": True}):
        published = _published_value(node.get("datetime"))
        if published:
            return published
    return None


def discover_article_urls(
    base_url: str, html: str, *, limit: int
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(base_url)
    candidates: dict[str, int] = {}
    container = soup.find("main") or soup.body or soup
    date_path = re.compile(r"/(?:19|20)\d{2}/(?:0?[1-9]|1[0-2])(?:/|-)")
    hint_path = re.compile(
        r"/(news|novyny|article|analysis|posts?|press|blog|events?|content)/",
        re.IGNORECASE,
    )
    blocked_path = re.compile(
        r"/(search|login|signin|tags?|topics?|authors?|categories?)(?:/|$)",
        re.IGNORECASE,
    )
    for anchor in container.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        candidate = urljoin(base_url, href)
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.hostname != base.hostname:
            continue
        if parsed.path.rstrip("/") == base.path.rstrip("/"):
            continue
        if blocked_path.search(parsed.path):
            continue
        if re.search(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|zip)$", parsed.path, re.I):
            continue
        label = clean_text(anchor.get_text(" ", strip=True))
        score = 0
        if hint_path.search(parsed.path):
            score += 3
        if date_path.search(parsed.path):
            score += 3
        if anchor.find_parent(["article", "h2", "h3"]):
            score += 2
        if len(label) >= 24:
            score += 1
        if score < 2:
            continue
        normalized = parsed._replace(fragment="").geturl()
        candidates[normalized] = max(candidates.get(normalized, 0), score)
    ranked = sorted(candidates.items(), key=lambda row: (-row[1], row[0]))
    return [url for url, _score in ranked[: max(1, limit)]]


def _article_fields(
    response: requests.Response,
) -> tuple[str, str, str, list[str], str | None, str]:
    soup = BeautifulSoup(response.text, "html.parser")
    published_at = extract_publication_time(soup)
    for node in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        node.decompose()
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    article = soup.find("article") or soup.find("main") or soup.body or soup
    text = clean_text(article.get_text(" ", strip=True))
    media = [
        urljoin(response.url, img.get("src"))
        for img in article.find_all("img", src=True)
        if img.get("src")
    ]
    return title, text, str(article), media, published_at, response.url


def extract_article(
    session: requests.Session, url: str, timeout: int
) -> tuple[str, str, str, list[str], str | None, str]:
    response = safe_get(session, url, timeout=timeout)
    response.raise_for_status()
    return _article_fields(response)
