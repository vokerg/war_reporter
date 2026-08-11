from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import quote, urlparse

try:
    from .common import clean_text
    from .summary_context import (
        EventCluster,
        TOPIC_LABELS,
        _sample_items,
        assess_temporal,
        build_event_clusters,
        evidence_score,
        importance_score,
        telegram_pulse,
    )
except ImportError:
    from common import clean_text
    from summary_context import (
        EventCluster,
        TOPIC_LABELS,
        _sample_items,
        assess_temporal,
        build_event_clusters,
        evidence_score,
        importance_score,
        telegram_pulse,
    )


DISPLAY_LOCATION_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("kyiv", "Киев/область", (r"\bkyiv\w*\b", r"\bkiev\w*\b", r"ки[єї]в\w*", r"киев\w*")),
    ("odesa", "Одесса/область", (r"\bodes[as]\w*\b", r"одес\w*", r"одещ\w*")),
    ("kharkiv", "Харьков/область", (r"\bkharkiv\w*\b", r"харьков\w*", r"харків\w*", r"харков\w*")),
    ("sumy", "Сумская область", (r"\bsumy\w*\b", r"сумщ\w*", r"сумск\w*", r"сумськ\w*")),
    ("kherson", "Херсон/область", (r"\bkherson\w*\b", r"херсон\w*")),
    ("zaporizhzhia", "Запорожье/область", (r"\bzapori\w*\b", r"запорож\w*", r"запоріж\w*")),
    ("dnipro", "Днепропетровская область", (r"\bdnipro\w*\b", r"днепр\w*", r"дніпр\w*")),
    ("donetsk", "Донецкая область", (r"\bdonetsk\w*\b", r"донец\w*", r"донець\w*")),
    ("luhansk", "Луганская область", (r"\bluhansk\w*\b", r"\blugansk\w*\b", r"луган\w*")),
    ("crimea", "Крым", (r"\bcrimea\w*\b", r"крым\w*", r"крим\w*")),
    ("kursk", "Курская область", (r"\bkursk\w*\b", r"курск\w*")),
    ("belgorod", "Белгородская область", (r"\bbelgorod\w*\b", r"белгород\w*")),
    ("konstantynivka", "Константиновка", (r"\bkonstant\w*\b", r"константинов\w*", r"костянтинів\w*")),
    ("pokrovsk", "Покровск", (r"\bpokrovsk\w*\b", r"покровск\w*", r"покровськ\w*")),
    ("chasiv-yar", "Часов Яр", (r"\bchasiv yar\b", r"часов\w*\s+яр\w*", r"часів\w*\s+яр\w*")),
    ("kupiansk", "Купянск", (r"\bkupiansk\w*\b", r"\bkupyansk\w*\b", r"купянск\w*", r"куп.?янськ\w*")),
    ("sloviansk", "Славянск", (r"\bsloviansk\w*\b", r"\bslavyansk\w*\b", r"славянск\w*", r"слов.?янськ\w*")),
    ("chernihiv", "Чернигов/область", (r"\bchernihiv\w*\b", r"черніг\w*", r"черниг\w*")),
    ("mykolaiv", "Николаев/область", (r"\bmykolaiv\w*\b", r"миколаїв\w*", r"николаев\w*")),
    ("poltava", "Полтавская область", (r"\bpoltava\w*\b", r"полтав\w*")),
)

ROUTINE_ALERT_RE = re.compile(
    r"повітрян\w+\s+тривог|воздушн\w+\s+тревог|air raid|"
    r"загроз\w*|угроз\w*|небезпек\w*|опасност\w*|"
    r"\bкурс\w*|\bкурсом\b|\bнапрямк\w*|\bв бік\b|\bв сторону\b|"
    r"залишайтеся в укритт|оставайтесь в укрыт|не ігноруйте тривог",
    re.IGNORECASE,
)
MATERIAL_EFFECT_RE = re.compile(
    r"постраждал\w*|поран\w*|загин\w*|погиб\w*|ранен\w*|"
    r"пошкод\w*|поврежд\w*|зруйн\w*|разруш\w*|влучан\w*|попадан\w*|"
    r"\bkilled\b|\bwounded\b|\bdamage\w*|\bdestroy\w*|\bimpact\w*|"
    r"пожеж\w*|пожар\w*",
    re.IGNORECASE,
)


def markdown_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "<", ">"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def markdown_url(value: Any) -> str | None:
    url = str(value or "")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return quote(url, safe=":/%?&=#@+~!$,;'*-._")


def _excerpt(value: str, limit: int = 240) -> str:
    text = clean_text(value)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return markdown_escape(text)


def _representative_line(item: Any) -> str:
    source = markdown_escape(
        clean_text(
            str(item.raw.get("source_name") or item.raw.get("source") or "unknown")
        )
    )
    group = markdown_escape(item.group)
    perspective = markdown_escape(item.perspective)
    published = markdown_escape(
        str(item.raw.get("published_at") or item.raw.get("collected_at") or "")
    )
    url = markdown_url(item.raw.get("url"))
    link = f"[оригинал]({url})" if url else "оригинал недоступен"
    return (
        f"  - **{source}** · `{group}` · `{perspective}` · {published} — "
        f"{_excerpt(item.text)} · {link}"
    )


def _detected_locations(cluster: EventCluster) -> dict[str, str]:
    text = clean_text(" ".join(item.text for item in cluster.items)).casefold()
    found: dict[str, str] = {}
    for key, label, patterns in DISPLAY_LOCATION_PATTERNS:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            found[key] = label
    return found


def _display_title(cluster: EventCluster) -> str:
    locations = _detected_locations(cluster)
    labels = list(locations.values())[:2]
    suffix = ", ".join(labels) if labels else "без устойчивой геопривязки"
    return f"{TOPIC_LABELS.get(cluster.topic, cluster.topic)} — {suffix}"


def _coalesce_clusters(clusters: list[EventCluster]) -> list[EventCluster]:
    """Merge same-topic, same-single-location fragments before editorial ranking.

    The lower-level lexical clustering intentionally stays conservative. This pass
    reconnects split alert/update fragments for one place without allowing broad
    multi-location posts to bridge otherwise unrelated theatres.
    """
    buckets: dict[tuple[str, str], EventCluster] = {}
    passthrough: list[EventCluster] = []
    for cluster in clusters:
        locations = _detected_locations(cluster)
        if len(locations) != 1:
            passthrough.append(cluster)
            continue
        location = next(iter(locations))
        key = (cluster.topic, location)
        target = buckets.get(key)
        if target is None:
            target = EventCluster(topic=cluster.topic)
            buckets[key] = target
        for item in cluster.items:
            target.add(item)
        # For locations already known by the lower-level temporal matcher, inject
        # the normalized key so Ukrainian case inflections do not erase history.
        target.anchor_union.add(location)
    return passthrough + list(buckets.values())


def _unique_source_families(cluster: EventCluster) -> int:
    return len({item.source_family for item in cluster.items})


def _is_routine_alert(cluster: EventCluster) -> bool:
    if cluster.topic not in {"strikes", "air-defence"}:
        return False
    if not cluster.items:
        return False
    texts = [item.text for item in cluster.items if item.text]
    if not texts:
        return False
    if any(MATERIAL_EFFECT_RE.search(text) for text in texts):
        return False
    alert_hits = sum(bool(ROUTINE_ALERT_RE.search(text)) for text in texts)
    return alert_hits / len(texts) >= 0.5 and _unique_source_families(cluster) <= 3


def _effective_editorial_rank(cluster: EventCluster, temporal: Any) -> float:
    importance = importance_score(cluster)
    evidence = evidence_score(cluster)[0]
    pulse = telegram_pulse(cluster)[0]
    score = (
        0.42 * importance
        + 0.22 * temporal.novelty
        + 0.18 * pulse
        + 0.18 * evidence
    )
    families = _unique_source_families(cluster)
    if families >= 4:
        score += 0.5
    elif families == 1 and cluster.topic in {"strikes", "air-defence"}:
        score -= 0.4
    if _is_routine_alert(cluster):
        score -= 3.0
    return max(0.0, min(10.0, score))


def _select_primary(
    assessed: list[tuple[EventCluster, Any]],
    max_primary: int,
    *,
    max_per_topic: int = 4,
) -> list[tuple[EventCluster, Any]]:
    selected: list[tuple[EventCluster, Any]] = []
    topic_counts: Counter[str] = Counter()
    for cluster, temporal in assessed:
        if _is_routine_alert(cluster):
            continue
        if topic_counts[cluster.topic] >= max_per_topic:
            continue
        selected.append((cluster, temporal))
        topic_counts[cluster.topic] += 1
        if len(selected) >= max_primary:
            break
    return selected


def render_summary_context(
    target_day: str,
    current_items: Iterable[dict[str, Any]],
    history_items_by_day: dict[str, Iterable[dict[str, Any]]],
    *,
    max_primary: int = 14,
    max_pulse_watch: int = 6,
) -> str:
    """Render deterministic, change-oriented context with untrusted text escaped."""
    raw_current_clusters, relevance_counts = build_event_clusters(current_items)
    current_clusters = _coalesce_clusters(raw_current_clusters)
    history_clusters = {
        day: _coalesce_clusters(build_event_clusters(items)[0])
        for day, items in history_items_by_day.items()
    }

    assessed: list[tuple[EventCluster, Any]] = [
        (cluster, assess_temporal(cluster, history_clusters))
        for cluster in current_clusters
    ]
    assessed.sort(
        key=lambda pair: _effective_editorial_rank(pair[0], pair[1]),
        reverse=True,
    )
    primary = _select_primary(assessed, max_primary)
    primary_ids = {id(cluster) for cluster, _ in primary}
    pulse_watch = sorted(
        [
            pair
            for pair in assessed
            if id(pair[0]) not in primary_ids
            and telegram_pulse(pair[0])[0] >= 4.0
        ],
        key=lambda pair: telegram_pulse(pair[0])[0],
        reverse=True,
    )[:max_pulse_watch]

    lines = [
        "## Контекст для редакционного синтеза",
        "",
        (
            "> Детерминированный pre-synthesis слой поверх сохранённой публичной "
            "проекции. Он фильтрует нерелевантный шум, группирует публикации в "
            "кандидатные события и отдельно показывает evidence mix, Telegram pulse "
            "и изменение относительно предыдущих дней. Это не независимая "
            "верификация и не заменяет атрибуцию в итоговой сводке."
        ),
        "",
        f"- День: **{markdown_escape(target_day)}**",
        f"- Кандидатных event clusters после coalescing: **{len(current_clusters)}**",
        f"- Исходных candidate fragments: **{len(raw_current_clusters)}**",
        f"- Relevant публикаций: **{relevance_counts.get('relevant', 0)}**",
        f"- Peripheral публикаций: **{relevance_counts.get('peripheral', 0)}**",
        f"- Отфильтровано как off-topic: **{relevance_counts.get('irrelevant', 0)}**",
        f"- Redacted записей, не использованных для синтеза: **{relevance_counts.get('redacted', 0)}**",
        f"- Исторический baseline: **{len(history_clusters)} дн.**",
        "",
        "### Приоритетные event clusters",
        "",
    ]

    for index, (cluster, temporal) in enumerate(primary, 1):
        importance = importance_score(cluster)
        evidence_value, evidence_label, groups = evidence_score(cluster)
        pulse_value, pulse_label, tg_families, tg_posts, tg_perspectives = telegram_pulse(cluster)
        rank = _effective_editorial_rank(cluster, temporal)
        baseline = (
            f"{temporal.baseline_pulse:.1f}"
            if temporal.baseline_pulse is not None
            else "нет сопоставимого события"
        )
        safe_title = markdown_escape(_display_title(cluster))
        safe_status = markdown_escape(temporal.status)
        safe_evidence_label = markdown_escape(evidence_label)
        safe_pulse_label = markdown_escape(pulse_label)
        group_summary = ", ".join(
            f"{markdown_escape(group)}: {count}"
            for group, count in groups.most_common()
        ) or "нет данных"
        lines += [
            f"#### {index}. {safe_title} · `{safe_status}`",
            "",
            (
                f"- Editorial rank: **{rank:.1f}**; importance: **{importance:.1f}/10**; "
                f"novelty: **{temporal.novelty:.1f}/10**"
            ),
            (
                f"- Evidence mix: **{safe_evidence_label} ({evidence_value:.1f}/10)** — "
                f"{group_summary}"
            ),
            (
                f"- Telegram pulse: **{safe_pulse_label} ({pulse_value:.1f}/10)** — "
                f"{tg_families} unique channels, {tg_posts} posts, "
                f"{tg_perspectives} perspectives"
            ),
            (
                f"- 7-day delta: **{safe_status}**; matched historical days: "
                f"**{temporal.matched_days}**; baseline pulse: **{baseline}**"
            ),
            f"- Публикаций в cluster: **{len(cluster.items)}**",
            "- Репрезентативные источники:",
        ]
        lines.extend(_representative_line(item) for item in _sample_items(cluster))
        lines.append("")

    if pulse_watch:
        lines += [
            "### Telegram pulse watchlist",
            "",
            (
                "Сюжеты ниже не вошли в основной top-rank, но имеют заметный "
                "многоканальный Telegram-сигнал. Pulse не является подтверждением."
            ),
            "",
        ]
        for cluster, temporal in pulse_watch:
            pulse_value, pulse_label, tg_families, tg_posts, _ = telegram_pulse(cluster)
            alert_note = " · routine alert stream" if _is_routine_alert(cluster) else ""
            lines.append(
                f"- **{markdown_escape(_display_title(cluster))}** · "
                f"`{markdown_escape(temporal.status)}` · pulse "
                f"**{markdown_escape(pulse_label)} {pulse_value:.1f}/10** · "
                f"{tg_families} channels / {tg_posts} posts{alert_note}"
            )
        lines.append("")

    lines += [
        "### Правила чтения контекста",
        "",
        "- `Evidence mix` — эвристика разнообразия типов источников, а не число независимых подтверждений.",
        "- `Telegram pulse` измеряет интенсивность и ширину обсуждения, а не достоверность.",
        "- Поток рутинных предупреждений о движении целей не конкурирует за top-rank с подтверждёнными последствиями и многоканальными событиями.",
        "- В primary top-N действует ограничение на доминирование одной темы; это редакционный diversity guard, а не оценка истины.",
        "- `NEW/ESCALATING/CONTINUING/DECLINING` сравнивают кластер с эвристически похожими событиями предыдущих дней.",
        "- Итоговая редакционная сводка должна сохранять атрибуцию спорных и односторонних утверждений.",
        "",
    ]
    return "\n".join(lines)
