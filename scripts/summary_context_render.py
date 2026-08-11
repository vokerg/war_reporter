from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote, urlparse

try:
    from .common import clean_text
    from .summary_context import (
        EventCluster,
        _cluster_title,
        _sample_items,
        assess_temporal,
        build_event_clusters,
        editorial_rank,
        evidence_score,
        importance_score,
        telegram_pulse,
    )
except ImportError:
    from common import clean_text
    from summary_context import (
        EventCluster,
        _cluster_title,
        _sample_items,
        assess_temporal,
        build_event_clusters,
        editorial_rank,
        evidence_score,
        importance_score,
        telegram_pulse,
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


def render_summary_context(
    target_day: str,
    current_items: Iterable[dict[str, Any]],
    history_items_by_day: dict[str, Iterable[dict[str, Any]]],
    *,
    max_primary: int = 14,
    max_pulse_watch: int = 6,
) -> str:
    """Render the deterministic summary context with untrusted text escaped."""
    current_clusters, relevance_counts = build_event_clusters(current_items)
    history_clusters = {
        day: build_event_clusters(items)[0]
        for day, items in history_items_by_day.items()
    }

    assessed: list[tuple[EventCluster, Any]] = [
        (cluster, assess_temporal(cluster, history_clusters))
        for cluster in current_clusters
    ]
    assessed.sort(
        key=lambda pair: editorial_rank(pair[0], pair[1]),
        reverse=True,
    )
    primary = assessed[:max_primary]
    primary_ids = {id(cluster) for cluster, _ in primary}
    pulse_watch = sorted(
        [
            pair
            for pair in assessed
            if id(pair[0]) not in primary_ids
            and telegram_pulse(pair[0])[0] >= 3.0
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
        f"- Кандидатных event clusters: **{len(current_clusters)}**",
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
        rank = editorial_rank(cluster, temporal)
        baseline = (
            f"{temporal.baseline_pulse:.1f}"
            if temporal.baseline_pulse is not None
            else "нет сопоставимого события"
        )
        safe_title = markdown_escape(_cluster_title(cluster))
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
            lines.append(
                f"- **{markdown_escape(_cluster_title(cluster))}** · "
                f"`{markdown_escape(temporal.status)}` · pulse "
                f"**{markdown_escape(pulse_label)} {pulse_value:.1f}/10** · "
                f"{tg_families} channels / {tg_posts} posts"
            )
        lines.append("")

    lines += [
        "### Правила чтения контекста",
        "",
        "- `Evidence mix` — эвристика разнообразия типов источников, а не число независимых подтверждений.",
        "- `Telegram pulse` измеряет интенсивность и ширину обсуждения, а не достоверность.",
        "- `NEW/ESCALATING/CONTINUING/DECLINING` сравнивают кластер с эвристически похожими событиями предыдущих дней.",
        "- Итоговая редакционная сводка должна сохранять атрибуцию спорных и односторонних утверждений.",
        "",
    ]
    return "\n".join(lines)
