#!/usr/bin/env python3
"""Parallel raw-first collector for Telegram, X, RSS and public web pages."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

try:
    from .common import (
        ROOT, append_unique, atomic_json, clean_text, env_int, iso, load_json,
        parse_time, raw_path, source_handle, stable_id, utc_now,
    )
except ImportError:
    from common import (
        ROOT, append_unique, atomic_json, clean_text, env_int, iso, load_json,
        parse_time, raw_path, source_handle, stable_id, utc_now,
    )

LOG = logging.getLogger("war-reporter.collect")


class CollectionError(RuntimeError):
    pass


def session_for(source: dict[str, Any], settings: dict[str, Any]) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": settings["user_agent"],
        "Accept-Language": ",".join(source.get("languages", ["en"])),
    })
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
        "id": stable_id(source["platform"], url, published_at, text or title),
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
        "raw": raw,
    }


def extract_article(session: requests.Session, url: str, timeout: int) -> tuple[str, str, str, list[str]]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        node.decompose()
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    article = soup.find("article") or soup.find("main") or soup.body or soup
    text = clean_text(article.get_text(" ", strip=True))
    media = [
        urljoin(url, img.get("src"))
        for img in article.find_all("img", src=True)
        if img.get("src")
    ]
    return title, text, str(article), media


def collect_rss(source: dict[str, Any], settings: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    session = session_for(source, settings)
    response = session.get(source["url"], timeout=settings["request_timeout_seconds"])
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise CollectionError(str(parsed.bozo_exception))
    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
        elif entry.get("updated_parsed"):
            published = datetime(*entry.updated_parsed[:6], tzinfo=UTC)
        if published and published < since:
            continue
        url = entry.get("link") or source["url"]
        summary_html = entry.get("summary", "")
        content_blocks = entry.get("content") or []
        supplied_html = "\n".join(block.get("value", "") for block in content_blocks) or summary_html
        supplied_text = clean_text(BeautifulSoup(supplied_html, "html.parser").get_text(" ", strip=True))
        title = entry.get("title", "")
        article_html, article_text, media = "", supplied_text, []
        try:
            fetched_title, fetched_text, article_html, media = extract_article(
                session, url, settings["request_timeout_seconds"]
            )
            title = title or fetched_title
            if len(fetched_text) > len(article_text):
                article_text = fetched_text
        except requests.RequestException:
            pass
        items.append(make_item(
            source,
            url=url,
            published_at=iso(published) if published else None,
            title=title,
            text=article_text,
            html=article_html or supplied_html,
            media=media,
            author=entry.get("author", ""),
            raw=dict(entry),
        ))
    return items


def collect_telegram(source: dict[str, Any], settings: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    handle = source_handle(source["url"])
    if not handle:
        raise CollectionError("Telegram source has no channel handle")
    session = session_for(source, settings)
    max_pages = int(settings.get("telegram_max_pages", 20))
    items: list[dict[str, Any]] = []
    seen_posts: set[str] = set()
    before: int | None = None

    for _ in range(max_pages):
        public_url = f"https://t.me/s/{handle}"
        if before is not None:
            public_url += f"?before={before}"
        response = session.get(public_url, timeout=settings["request_timeout_seconds"])
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        wraps = soup.select(".tgme_widget_message_wrap")
        if not wraps:
            break
        page_ids: list[int] = []
        reached_since = False
        for wrap in wraps:
            message = wrap.select_one(".tgme_widget_message")
            if message is None:
                continue
            post = message.get("data-post", "")
            if not post or post in seen_posts:
                continue
            seen_posts.add(post)
            try:
                page_ids.append(int(post.rsplit("/", 1)[-1]))
            except ValueError:
                pass
            canonical = f"https://t.me/{post}"
            time_node = wrap.select_one("time[datetime]")
            published_at = time_node.get("datetime") if time_node else None
            published = parse_time(published_at)
            if published and published < since:
                reached_since = True
                continue
            text_node = wrap.select_one(".tgme_widget_message_text")
            text = text_node.get_text("\n", strip=True) if text_node else ""
            message_html = str(message)
            media: list[str] = []
            for node in wrap.select("[style*='background-image']"):
                match = re.search(r"url\(['\"]?([^'\")]+)", node.get("style", ""))
                if match:
                    media.append(html_lib.unescape(match.group(1)))
            for node in wrap.select("video[src], source[src], a[href]"):
                value = node.get("src") or node.get("href")
                if value and ("cdn" in value or "video" in value or "photo" in value):
                    media.append(urljoin(public_url, value))
            if not text and not media:
                continue
            items.append(make_item(
                source,
                url=canonical,
                published_at=iso(published) if published else published_at,
                text=text,
                html=message_html,
                media=media,
                author=source["name"],
                raw={"post": post},
            ))
        if reached_since or not page_ids:
            break
        oldest = min(page_ids)
        if before is not None and oldest >= before:
            break
        before = oldest
    return items


def x_api_get(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=30)
    if response.status_code >= 400:
        raise CollectionError(f"X API {response.status_code}: {response.text[:300]}")
    return response.json()


def _x_pages(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any],
    max_pages: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    token: str | None = None
    for _ in range(max_pages):
        page_params = dict(params)
        if token:
            page_params["pagination_token"] = token
        payload = x_api_get(session, endpoint, page_params)
        users = {row["id"]: row for row in payload.get("includes", {}).get("users", [])}
        media = {row["media_key"]: row for row in payload.get("includes", {}).get("media", [])}
        for tweet in payload.get("data", []):
            tweet["_expanded_author"] = users.get(tweet.get("author_id"), {})
            tweet["_expanded_media"] = [
                media.get(key, {})
                for key in tweet.get("attachments", {}).get("media_keys", [])
            ]
            rows.append(tweet)
        token = payload.get("meta", {}).get("next_token")
        if not token:
            break
    return rows


def collect_x(source: dict[str, Any], settings: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise CollectionError("X_BEARER_TOKEN is not configured")
    session = session_for(source, settings)
    session.headers["Authorization"] = f"Bearer {token}"
    max_pages = int(settings.get("x_max_pages", 10))
    params: dict[str, Any] = {
        "max_results": 100,
        "start_time": iso(since),
        "tweet.fields": "id,text,author_id,created_at,lang,entities,attachments,referenced_tweets",
        "expansions": "author_id,attachments.media_keys",
        "user.fields": "id,username,name",
        "media.fields": "media_key,type,url,preview_image_url,alt_text",
    }
    query = source.get("query")
    if query:
        params["query"] = query
        tweets = _x_pages(
            session,
            "https://api.x.com/2/tweets/search/recent",
            params,
            max_pages,
        )
    else:
        username = source_handle(source["url"])
        user = x_api_get(session, f"https://api.x.com/2/users/by/username/{username}", {})
        user_id = user.get("data", {}).get("id")
        if not user_id:
            raise CollectionError(f"X user not found: {username}")
        tweets = _x_pages(
            session,
            f"https://api.x.com/2/users/{user_id}/tweets",
            params,
            max_pages,
        )

    items: list[dict[str, Any]] = []
    for tweet in tweets:
        author = tweet.pop("_expanded_author", {})
        expanded_media = tweet.pop("_expanded_media", [])
        username = author.get("username") or source_handle(source["url"]) or "i"
        media = [row.get("url") or row.get("preview_image_url") for row in expanded_media]
        items.append(make_item(
            source,
            url=f"https://x.com/{username}/status/{tweet['id']}",
            published_at=tweet.get("created_at"),
            text=tweet.get("text", ""),
            media=[value for value in media if value],
            author=author.get("name") or username,
            raw=tweet,
        ))
    return items


def x_discovery_sources(settings: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for index, query in enumerate(settings.get("x_search_queries", []), 1):
        sources.append({
            "id": f"x-discovery-{index}",
            "name": f"X recent search {index}",
            "platform": "x",
            "url": f"https://x.com/search?q={requests.utils.quote(query)}",
            "query": query,
            "group": "x-discovery",
            "perspective": "mixed",
            "trust": "unknown",
            "priority": 99,
            "languages": ["und"],
            "tags": ["discovery"],
            "enabled": True,
        })
    return sources


def collect_web(source: dict[str, Any], settings: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    del since
    session = session_for(source, settings)
    title, text, html, media = extract_article(
        session, source["url"], settings["request_timeout_seconds"]
    )
    if not text:
        return []
    return [make_item(
        source,
        url=source["url"],
        published_at=None,
        title=title,
        text=text,
        html=html,
        media=media,
        author=source["name"],
        raw={"content_type": "web_snapshot"},
    )]


COLLECTORS = {
    "rss": collect_rss,
    "telegram": collect_telegram,
    "x": collect_x,
    "web": collect_web,
}


def collect_one(source: dict[str, Any], settings: dict[str, Any], since: datetime) -> list[dict[str, Any]]:
    collector = COLLECTORS.get(source.get("platform"))
    if collector is None:
        raise CollectionError(f"unsupported platform: {source.get('platform')}")
    return collector(source, settings, since)


def append_errors(root: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    day = utc_now().strftime("%Y/%m/%d")
    path = root / day / "errors.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_collection(
    root: Path = ROOT,
    *,
    lookback_hours: int | None = None,
    workers: int | None = None,
    groups: set[str] | None = None,
    platforms: set[str] | None = None,
) -> dict[str, Any]:
    settings = load_json(root / "config/settings.json")
    registry = load_json(root / "config/sources.json")
    if not isinstance(settings, dict) or not isinstance(registry, dict):
        raise ValueError("missing config/settings.json or config/sources.json")
    lookback = lookback_hours or int(settings["default_lookback_hours"])
    since = utc_now() - timedelta(hours=lookback)
    all_sources = list(registry.get("sources", [])) + x_discovery_sources(settings)
    candidates = [
        row for row in all_sources
        if row.get("enabled", True)
        and (not groups or row.get("group") in groups)
        and (not platforms or row.get("platform") in platforms)
    ]
    candidates.sort(key=lambda row: (-int(row.get("priority", 0)), row["id"]))
    worker_count = workers or env_int("WAR_REPORTER_WORKERS", int(settings["workers"]))
    raw_root = root / settings["raw_root"]
    errors: list[dict[str, Any]] = []
    total_added = 0
    per_source: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_to_source = {
            pool.submit(collect_one, source, settings, since): source
            for source in candidates
        }
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                items = future.result()
                added = 0
                grouped: dict[Path, list[dict[str, Any]]] = {}
                for item in items:
                    grouped.setdefault(
                        raw_path(raw_root, item.get("published_at"), item["collected_at"]), []
                    ).append(item)
                for path, rows in grouped.items():
                    added += append_unique(path, rows)
                total_added += added
                per_source[source["id"]] = {"fetched": len(items), "added": added}
                LOG.info("%s: fetched=%d added=%d", source["id"], len(items), added)
            except Exception as exc:
                row = {
                    "source": source["id"],
                    "platform": source.get("platform"),
                    "url": source.get("url"),
                    "collected_at": iso(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
                errors.append(row)
                per_source[source["id"]] = {"error": row["error"]}
                LOG.warning("%s: %s", source["id"], row["error"])

    append_errors(root / settings["error_root"], errors)
    state = {
        "last_run_at": iso(),
        "since": iso(since),
        "sources_attempted": len(candidates),
        "items_added": total_added,
        "errors": len(errors),
        "per_source": per_source,
    }
    atomic_json(root / settings["state_file"], state)
    return state


def parse_set(value: str | None) -> set[str] | None:
    return {part.strip() for part in value.split(",") if part.strip()} if value else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--lookback-hours", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--groups", help="comma-separated source groups")
    parser.add_argument("--platforms", help="comma-separated platforms")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        result = run_collection(
            args.root,
            lookback_hours=args.lookback_hours,
            workers=args.workers,
            groups=parse_set(args.groups),
            platforms=parse_set(args.platforms),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.error("%s", exc)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
