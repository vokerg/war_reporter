"""Platform-specific collector adapters."""

from __future__ import annotations

from .collector_common import *  # noqa: F401,F403
from .collector_common import _article_fields


def collect_rss(
    source: dict[str, Any], settings: dict[str, Any], since: datetime
) -> list[dict[str, Any]]:
    session = session_for(source, settings)
    response = safe_get(
        session,
        source["url"],
        timeout=settings["request_timeout_seconds"],
    )
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
        supplied_html = (
            "\n".join(block.get("value", "") for block in content_blocks)
            or summary_html
        )
        supplied_text = clean_text(
            BeautifulSoup(supplied_html, "html.parser").get_text(" ", strip=True)
        )
        title = entry.get("title", "")
        article_html, article_text, media = "", supplied_text, []
        try:
            (
                fetched_title,
                fetched_text,
                article_html,
                media,
                fetched_published_at,
                fetched_url,
            ) = extract_article(
                session, url, settings["request_timeout_seconds"]
            )
            url = fetched_url
            title = title or fetched_title
            if published is None and fetched_published_at:
                published = parse_time(fetched_published_at)
            if len(fetched_text) > len(article_text):
                article_text = fetched_text
        except (requests.RequestException, CollectionError):
            pass
        items.append(
            make_item(
                source,
                url=url,
                published_at=iso(published) if published else None,
                title=title,
                text=article_text,
                html=article_html or supplied_html,
                media=media,
                author=entry.get("author", ""),
                raw=dict(entry),
            )
        )
    return items


def collect_telegram(
    source: dict[str, Any], settings: dict[str, Any], since: datetime
) -> list[dict[str, Any]]:
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
        response = safe_get(
            session,
            public_url,
            timeout=settings["request_timeout_seconds"],
        )
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
                match = re.search(
                    r"url\(['\"]?([^'\")]+)", node.get("style", "")
                )
                if match:
                    media.append(html_lib.unescape(match.group(1)))
            for node in wrap.select("video[src], source[src], a[href]"):
                value = node.get("src") or node.get("href")
                if value and (
                    "cdn" in value or "video" in value or "photo" in value
                ):
                    media.append(urljoin(public_url, value))
            if not text and not media:
                continue
            items.append(
                make_item(
                    source,
                    url=canonical,
                    published_at=iso(published) if published else published_at,
                    text=text,
                    html=message_html,
                    media=media,
                    author=source["name"],
                    raw={"post": post},
                )
            )
        if reached_since or not page_ids:
            break
        oldest = min(page_ids)
        if before is not None and oldest >= before:
            break
        before = oldest
    return items


def x_api_get(
    session: requests.Session, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = safe_get(
        session,
        url,
        params=params,
        timeout=30,
        same_host_only=True,
    )
    if response.status_code >= 400:
        raise CollectionError(
            f"X API {response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise CollectionError("X API returned a non-object payload")
    return payload


def _x_pages(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any],
    max_pages: int,
    *,
    token_param: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    token: str | None = None
    for _ in range(max_pages):
        page_params = dict(params)
        if token:
            page_params[token_param] = token
        payload = x_api_get(session, endpoint, page_params)
        users = {
            row["id"]: row
            for row in payload.get("includes", {}).get("users", [])
        }
        media = {
            row["media_key"]: row
            for row in payload.get("includes", {}).get("media", [])
        }
        for tweet in payload.get("data", []):
            expanded = dict(tweet)
            expanded["_expanded_author"] = users.get(
                tweet.get("author_id"), {}
            )
            expanded["_expanded_media"] = [
                media.get(key, {})
                for key in tweet.get("attachments", {}).get(
                    "media_keys", []
                )
            ]
            rows.append(expanded)
        token = payload.get("meta", {}).get("next_token")
        if not token:
            break
    return rows


def collect_x(
    source: dict[str, Any], settings: dict[str, Any], since: datetime
) -> list[dict[str, Any]]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise CollectionError("X_BEARER_TOKEN is not configured")
    session = session_for(source, settings)
    session.headers["Authorization"] = f"Bearer {token}"
    max_pages = int(settings.get("x_max_pages", 10))
    params: dict[str, Any] = {
        "max_results": 100,
        "start_time": iso(since),
        "tweet.fields": (
            "id,text,author_id,created_at,lang,entities,attachments,"
            "referenced_tweets"
        ),
        "expansions": "author_id,attachments.media_keys",
        "user.fields": "id,username,name",
        "media.fields": (
            "media_key,type,url,preview_image_url,alt_text"
        ),
    }
    query = source.get("query")
    if query:
        recent_floor = utc_now() - timedelta(days=7) + timedelta(minutes=1)
        params["start_time"] = iso(max(since, recent_floor))
        params["query"] = query
        tweets = _x_pages(
            session,
            "https://api.x.com/2/tweets/search/recent",
            params,
            max_pages,
            token_param="next_token",
        )
    else:
        username = source_handle(source["url"])
        user = x_api_get(
            session,
            f"https://api.x.com/2/users/by/username/{username}",
            {},
        )
        user_id = user.get("data", {}).get("id")
        if not user_id:
            raise CollectionError(f"X user not found: {username}")
        tweets = _x_pages(
            session,
            f"https://api.x.com/2/users/{user_id}/tweets",
            params,
            max_pages,
            token_param="pagination_token",
        )

    items: list[dict[str, Any]] = []
    for expanded in tweets:
        tweet = {
            key: value
            for key, value in expanded.items()
            if not key.startswith("_expanded_")
        }
        author = expanded.get("_expanded_author", {})
        expanded_media = expanded.get("_expanded_media", [])
        username = (
            author.get("username")
            or source_handle(source["url"])
            or "i"
        )
        media = [
            row.get("url") or row.get("preview_image_url")
            for row in expanded_media
        ]
        known_sources = settings.get("_x_sources_by_handle", {})
        canonical_source = source
        if query and isinstance(known_sources, dict):
            matched = known_sources.get(str(username).lower())
            if isinstance(matched, dict):
                canonical_source = matched
        items.append(
            make_item(
                canonical_source,
                url=f"https://x.com/{username}/status/{tweet['id']}",
                published_at=tweet.get("created_at"),
                text=tweet.get("text", ""),
                media=[value for value in media if value],
                author=author.get("name") or username,
                raw={
                    "tweet": tweet,
                    "author": author,
                    "media": expanded_media,
                    "collected_via": source["id"],
                },
            )
        )
    return items


def x_discovery_sources(
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for index, query in enumerate(
        settings.get("x_search_queries", []), 1
    ):
        sources.append(
            {
                "id": f"x-discovery-{index}",
                "name": f"X recent search {index}",
                "platform": "x",
                "url": (
                    "https://x.com/search?q="
                    f"{requests.utils.quote(query)}"
                ),
                "query": query,
                "group": "x-discovery",
                "perspective": "mixed",
                "trust": "unknown",
                "priority": 99,
                "languages": ["und"],
                "tags": ["discovery"],
                "enabled": True,
            }
        )
    return sources


def collect_web(
    source: dict[str, Any], settings: dict[str, Any], since: datetime
) -> list[dict[str, Any]]:
    session = session_for(source, settings)
    response = safe_get(
        session,
        source["url"],
        timeout=settings["request_timeout_seconds"],
    )
    response.raise_for_status()
    index_fields = _article_fields(response)
    tags = set(source.get("tags") or [])
    snapshot_mode = source.get("web_mode") == "snapshot" or bool(
        tags.intersection({"map", "maps"})
    )

    if not snapshot_mode:
        links = discover_article_urls(
            response.url,
            response.text,
            limit=int(settings.get("web_max_links", 12)),
        )
        items: list[dict[str, Any]] = []
        for link in links:
            try:
                title, text, html, media, published_at, canonical = extract_article(
                    session, link, settings["request_timeout_seconds"]
                )
            except (requests.RequestException, CollectionError):
                continue
            published = parse_time(published_at) if published_at else None
            if published is not None and published < since:
                continue
            if not text:
                continue
            items.append(
                make_item(
                    source,
                    url=canonical,
                    published_at=published_at,
                    title=title,
                    text=text,
                    html=html,
                    media=media,
                    author=source["name"],
                    raw={
                        "content_type": "web_article",
                        "discovered_from": response.url,
                    },
                )
            )
        if items:
            return items

    title, text, html, media, published_at, canonical = index_fields
    if not text:
        return []
    return [
        make_item(
            source,
            url=canonical,
            published_at=published_at,
            title=title,
            text=text,
            html=html,
            media=media,
            author=source["name"],
            raw={"content_type": "web_snapshot"},
        )
    ]


COLLECTORS = {
    "rss": collect_rss,
    "telegram": collect_telegram,
    "x": collect_x,
    "web": collect_web,
}
