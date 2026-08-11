from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import quote, urlparse

try:
    from .common import clean_text
    from .summary_context import (
        EventCluster,
        PreparedItem,
        TOPIC_LABELS,
        _sample_items,
        assess_temporal,
        evidence_score,
        importance_score,
        prepare_item,
        telegram_pulse,
    )
except ImportError:
    from common import clean_text
    from summary_context import (
        EventCluster,
        PreparedItem,
        TOPIC_LABELS,
        _sample_items,
        assess_temporal,
        evidence_score,
        importance_score,
        prepare_item,
        telegram_pulse,
    )


DISPLAY_LOCATION_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("kyiv", "Киев/область", (r"\bkyiv\w*\b", r"\bkiev\w*\b", r"ки[єї]в\w*", r"киев\w*")),
    ("odesa", "Одесса/область", (r"\bodes[as]\w*\b", r"одес\w*", r"одещ\w*")),
    ("kharkiv", "Харьков/область", (r"\bkharkiv\w*\b", r"харьков\w*", r"харків\w*", r"харков\w*")),
    ("sumy", "Сумская область", (r"\bsumy\w*\b", r"сумщ\w*", r"сумск\w*", r"сумськ\w*", r"\bсумах\b")),
    ("kherson", "Херсон/область", (r"\bkherson\w*\b", r"херсон\w*")),
    ("zaporizhzhia", "Запорожье/область", (r"\bzapori\w*\b", r"запорож\w*", r"запоріж\w*")),
    ("dnipro", "Днепропетровская область", (r"\bdnipro\w*\b", r"днепр\w*", r"дніпр\w*")),
    ("donetsk", "Донецкая область", (r"\bdonetsk\w*\b", r"донец\w*", r"донець\w*")),
    ("luhansk", "Луганская область", (r"\bluhansk\w*\b", r"\blugansk\w*\b", r"луган\w*")),
    ("crimea", "Крым", (r"\bcrimea\w*\b", r"крым\w*", r"крим\w*")),
    ("kursk", "Курская область", (r"\bkursk\w*\b", r"курск\w*")),
    ("belgorod", "Белгородская область", (r"\bbelgorod\w*\b", r"белгород\w*")),
    ("sevastopol", "Севастополь", (r"\bsevastopol\w*\b", r"севастопол\w*")),
    ("black-sea", "Чёрное море", (r"\bblack sea\b", r"черн\w+\s+мор\w+", r"чорн\w+\s+мор\w+")),
    ("konstantynivka", "Константиновка", (r"\bkonstant\w*\b", r"константинов\w*", r"костянтинів\w*")),
    ("pokrovsk", "Покровск", (r"\bpokrovsk\w*\b", r"покровск\w*", r"покровськ\w*")),
    ("chasiv-yar", "Часов Яр", (r"\bchasiv yar\b", r"часов\w*\s+яр\w*", r"часів\w*\s+яр\w*")),
    ("kupiansk", "Купянск", (r"\bkupiansk\w*\b", r"\bkupyansk\w*\b", r"купянск\w*", r"куп.?янськ\w*")),
    ("sloviansk", "Славянск", (r"\bsloviansk\w*\b", r"\bslavyansk\w*\b", r"славянск\w*", r"слов.?янськ\w*")),
    ("chernihiv", "Чернигов/область", (r"\bchernihiv\w*\b", r"черніг\w*", r"черниг\w*")),
    ("mykolaiv", "Николаев/область", (r"\bmykolaiv\w*\b", r"миколаїв\w*", r"николаев\w*")),
    ("poltava", "Полтавская область", (r"\bpoltava\w*\b", r"полтав\w*")),
    ("tula", "Тульская область", (r"\btula\w*\b", r"тульск\w*")),
    ("rostov", "Ростовская область", (r"\brostov\w*\b", r"ростов\w*")),
    ("krasnodar", "Краснодарский край", (r"\bkrasnodar\w*\b", r"краснодар\w*")),
)

CORE_TEMPORAL_LOCATIONS = {
    "kyiv", "odesa", "kharkiv", "sumy", "kherson", "zaporizhzhia", "dnipro",
    "donetsk", "luhansk", "crimea", "kursk", "belgorod", "sevastopol",
    "black-sea", "konstantynivka", "pokrovsk", "chasiv-yar", "kupiansk", "sloviansk",
}

ROUTINE_ALERT_RE = re.compile(
    r"повітрян\w+\s+тривог|воздушн\w+\s+тревог|air raid|"
    r"загроз\w*|угроз\w*|небезпек\w*|опасност\w*|"
    r"\bкурс\w*|\bкурсом\b|\bнапрямк\w*|\bв бік\b|\bв сторону\b|"
    r"залишайтеся в укритт|оставайтесь в укрыт|не ігноруйте тривог",
    re.IGNORECASE,
)
CASUALTY_RE = re.compile(
    r"\bпостраждал\w*|\bпоран\w*|\bзагин\w*|\bзагибл\w*|\bпогиб\w*|\bранен\w*|"
    r"\bkilled\b|\bwounded\b|\bcasualt\w*",
    re.IGNORECASE,
)
MATERIAL_EFFECT_RE = re.compile(
    r"\bпостраждал\w*|\bпоран\w*|\bзагин\w*|\bзагибл\w*|\bпогиб\w*|\bранен\w*|"
    r"\bпошкод\w*|\bповрежд\w*|\bзруйн\w*|\bразруш\w*|\bвлучан\w*|\bпопадан\w*|"
    r"\bkilled\b|\bwounded\b|\bdamage\w*|\bdestroy\w*|\bimpact\w*|"
    r"\bпожеж\w*|\bпожар\w*",
    re.IGNORECASE,
)
MEMORIAL_RE = re.compile(
    r"\bпам.?ят\w*|\bпамяти\b|\bмемориал\w*|\bвшанув\w*|\bпочтил\w*|"
    r"\bназавжди\b|\bгодовщин\w*|\bрічниц\w*|"
    r"(?:поліг|загинув|погиб)\b.{0,80}\b20\d{2}\b|"
    r"\bнародився\b.{0,160}\b(?:навчався|служив|здобув)\b",
    re.IGNORECASE,
)
CURRENT_WAR_CONTEXT_RE = re.compile(
    r"\bukrain\w*|\bукраїн\w*|\bукраин\w*|\bвсу\b|\bзсу\b|\bсво\b|"
    r"\boccupation\w*|\boccupied\b|\bокупован\w*|\bоккупирован\w*",
    re.IGNORECASE,
)
STRICT_STRIKE_RE = re.compile(
    r"\bdrone\w*|\buav\w*|\bmissile\w*|\brocket\w*|\bstrike\w*|\battack\w*|"
    r"\bбпла\b|\bдрон\w*|\bбезпілот\w*|\bбеспилот\w*|\bракет\w*|"
    r"\bудар\w*|\bатак\w*|\bобстріл\w*|\bобстрел\w*|\bавіаудар\w*|\bавиаудар\w*",
    re.IGNORECASE,
)
STRICT_FRONTLINE_RE = re.compile(
    r"\bfrontline\b|\badvance\w*|\bassault\w*|\bbattle\w*|\bcombat\w*|"
    r"\bфронт\w*|\bнаступ\w*|\bпродвиж\w*|\bштурм\w*|\bбо[йи]\b|\bбоїв\b|\bбоев\b|"
    r"\bоборон\w*|\bконтрол\w*|\bосвобод\w*|\bзахоп\w*",
    re.IGNORECASE,
)
STRICT_AIRDEF_RE = re.compile(
    r"\bair defen[cs]e\b|\bпво\b|\bпротиповітр\w*|\bs-?400\b|\bс-?400\b|"
    r"\bpatriot\b|\bpantsir\b|\bпанцир\w*|\btor\b|\bтор\b",
    re.IGNORECASE,
)
STRICT_INFRA_RE = re.compile(
    r"\brefiner\w*|\bнпз\b|\bнефтеперераб\w*|\bнафтоперероб\w*|"
    r"\brailway\w*|\brailroad\w*|\bжелезнодорож\w*|\bзалізнич\w*|"
    r"\bports?\b|\bпорт\w*|\benergy\b|\bэнергет\w*|\bенергет\w*",
    re.IGNORECASE,
)
STRICT_NAVAL_RE = re.compile(
    r"\bblack sea\b|черн\w+\s+мор\w+|чорн\w+\s+мор\w+|"
    r"\bnaval drone\w*|\bsea drone\w*|\bморск\w+\s+(?:дрон\w*|беспилот\w*|катер\w*)|"
    r"\bморськ\w+\s+(?:дрон\w*|безпілот\w*|катер\w*)|\bкорабл\w*|\bсудн\w*",
    re.IGNORECASE,
)
STRICT_SUPPORT_RE = re.compile(
    r"\bsanctions?\b|\bсанкц\w*|\bmilitary aid\b|\bweapons? package\b|"
    r"\bвоенн\w+\s+помощ\w*|\bвійськов\w+\s+допомог\w*|\bpatriot\b",
    re.IGNORECASE,
)
EQUIPMENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("refinery", r"\brefiner\w*|\bнпз\b|\bнефтеперераб\w*|\bнафтоперероб\w*"),
    ("railway", r"\brailway\w*|\brailroad\w*|\bжелезнодорож\w*|\bзалізнич\w*"),
    ("port", r"\bports?\b|\bпорт\w*"),
    ("s400", r"\bs-?400\b|\bс-?400\b"),
    ("patriot", r"\bpatriot\b"),
    ("pantsir", r"\bpantsir\b|\bпанцир\w*"),
    ("tor", r"\btor\b|\bтор\b"),
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


def _representative_line(item: PreparedItem) -> str:
    source = markdown_escape(
        clean_text(str(item.raw.get("source_name") or item.raw.get("source") or "unknown"))
    )
    published = markdown_escape(
        str(item.raw.get("published_at") or item.raw.get("collected_at") or "")
    )
    url = markdown_url(item.raw.get("url"))
    link = f"[оригинал]({url})" if url else "оригинал недоступен"
    return (
        f"  - **{source}** · `{markdown_escape(item.group)}` · "
        f"`{markdown_escape(item.perspective)}` · {published} — "
        f"{_excerpt(item.text)} · {link}"
    )


def _item_location_map(item: PreparedItem) -> dict[str, str]:
    source = clean_text(str(item.raw.get("source_name") or item.raw.get("source") or ""))
    text = clean_text(f"{source} {item.text}").casefold()
    return {
        key: label
        for key, label, patterns in DISPLAY_LOCATION_PATTERNS
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    }


def _cluster_location_map(cluster: EventCluster) -> dict[str, str]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for item in cluster.items:
        for key, label in _item_location_map(item).items():
            counts[key] += 1
            labels[key] = label
    if not counts:
        return {}
    threshold = max(1, int(len(cluster.items) * 0.2))
    stable = [key for key, count in counts.most_common() if count >= threshold]
    if not stable:
        stable = [counts.most_common(1)[0][0]]
    return {key: labels[key] for key in stable[:3]}


def _editorial_topic(item: PreparedItem) -> str:
    return "civilian-harm" if CASUALTY_RE.search(item.text) else item.topic


def _strict_candidate(item: PreparedItem, topic: str, locations: tuple[str, ...]) -> bool:
    text = item.text
    if MEMORIAL_RE.search(text):
        return False

    current_context = bool(CURRENT_WAR_CONTEXT_RE.search(text))
    contextualized = bool(locations) or current_context or item.group == "official-ua"

    if topic == "civilian-harm":
        return (
            bool(CASUALTY_RE.search(text))
            and contextualized
            and (bool(locations) or current_context or bool(STRICT_STRIKE_RE.search(text)))
        )
    if topic == "strikes":
        return contextualized and bool(STRICT_STRIKE_RE.search(text))
    if topic == "air-defence":
        return contextualized and bool(STRICT_AIRDEF_RE.search(text))
    if topic == "frontline":
        return contextualized and bool(STRICT_FRONTLINE_RE.search(text))
    if topic == "energy":
        return contextualized and bool(STRICT_INFRA_RE.search(text))
    if topic == "naval":
        return contextualized and bool(STRICT_NAVAL_RE.search(text))
    if topic == "support":
        return bool(STRICT_SUPPORT_RE.search(text)) and (
            current_context
            or item.group in {"official-ua", "international-media", "analysts"}
        )
    if topic == "investigations":
        return item.group in {"osint", "analysts"} and (
            contextualized
            or bool(STRICT_STRIKE_RE.search(text))
            or bool(STRICT_FRONTLINE_RE.search(text))
        )
    return False


def _semantic_signature(item: PreparedItem, topic: str) -> tuple[str, ...]:
    if topic == "civilian-harm":
        return ("casualties",)
    equipment = tuple(
        sorted(
            key
            for key, pattern in EQUIPMENT_PATTERNS
            if re.search(pattern, item.text, flags=re.IGNORECASE)
        )
    )
    if equipment:
        return equipment
    if topic == "support":
        if re.search(r"\bsanctions?\b|\bсанкц\w*", item.text, flags=re.IGNORECASE):
            return ("sanctions",)
        if STRICT_SUPPORT_RE.search(item.text):
            return ("aid",)
    return ()


def _build_situation_clusters(
    items: Iterable[dict[str, Any]],
) -> tuple[list[EventCluster], dict[str, int]]:
    """Build conservative daily situation clusters for editorial navigation."""
    prepared = [prepare_item(item) for item in items]
    counts = Counter(row.relevance for row in prepared)
    candidates = [row for row in prepared if row.relevance in {"relevant", "peripheral"}]
    buckets: dict[tuple[str, tuple[str, ...], tuple[str, ...]], EventCluster] = {}

    for item in candidates:
        topic = _editorial_topic(item)
        locations = tuple(sorted(_item_location_map(item)))
        if not _strict_candidate(item, topic, locations):
            counts["strict_filtered"] += 1
            continue
        counts["accepted"] += 1

        semantic = _semantic_signature(item, topic)
        if not locations and topic not in {"support", "investigations"}:
            semantic = semantic + (f"source:{item.source_family}",)

        key = (topic, locations, semantic)
        cluster = buckets.setdefault(key, EventCluster(topic=topic))
        cluster.add(item)
        for location in locations:
            if location in CORE_TEMPORAL_LOCATIONS:
                cluster.anchor_union.add(location)

    return list(buckets.values()), dict(counts)


def _display_title(cluster: EventCluster) -> str:
    labels = list(_cluster_location_map(cluster).values())[:2]
    suffix = ", ".join(labels) if labels else "без устойчивой геопривязки"
    return f"{TOPIC_LABELS.get(cluster.topic, cluster.topic)} — {suffix}"


def _unique_source_families(cluster: EventCluster) -> int:
    return len({item.source_family for item in cluster.items})


def _is_routine_alert(cluster: EventCluster) -> bool:
    if cluster.topic not in {"strikes", "air-defence"}:
        return False
    texts = [item.text for item in cluster.items if item.text]
    if not texts or any(MATERIAL_EFFECT_RE.search(text) for text in texts):
        return False
    hits = sum(bool(ROUTINE_ALERT_RE.search(text)) for text in texts)
    return hits / len(texts) >= 0.5 and _unique_source_families(cluster) <= 3


def _is_broad_roundup(cluster: EventCluster) -> bool:
    location_sets = [set(_item_location_map(item)) for item in cluster.items]
    if not location_sets:
        return False
    threshold = 2 if cluster.topic == "civilian-harm" else 3
    multi = sum(len(locations) >= threshold for locations in location_sets)
    return multi / len(location_sets) >= 0.5


def _is_weak_unlocated(cluster: EventCluster) -> bool:
    if _cluster_location_map(cluster) or cluster.topic in {"support", "investigations"}:
        return False
    return _unique_source_families(cluster) < 2


def _insufficient_primary_evidence(cluster: EventCluster) -> bool:
    score = evidence_score(cluster)[0]
    if cluster.topic in {"frontline", "air-defence", "naval"}:
        return score < 3.0
    if cluster.topic == "support":
        return score < 1.5
    return False


def _effective_editorial_rank(cluster: EventCluster, temporal: Any) -> float:
    evidence = evidence_score(cluster)[0]
    pulse = telegram_pulse(cluster)[0]
    score = (
        0.42 * importance_score(cluster)
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
    if _is_broad_roundup(cluster):
        score -= 1.2
    if _is_weak_unlocated(cluster):
        score -= 1.5
    if _insufficient_primary_evidence(cluster):
        score -= 1.0
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
        if (
            _is_routine_alert(cluster)
            or _is_broad_roundup(cluster)
            or _is_weak_unlocated(cluster)
            or _insufficient_primary_evidence(cluster)
        ):
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
    current_clusters, counts = _build_situation_clusters(current_items)
    history_clusters = {
        day: _build_situation_clusters(items)[0]
        for day, items in history_items_by_day.items()
    }

    assessed = [
        (cluster, assess_temporal(cluster, history_clusters))
        for cluster in current_clusters
    ]
    assessed.sort(key=lambda pair: _effective_editorial_rank(pair[0], pair[1]), reverse=True)

    primary = _select_primary(assessed, max_primary)
    primary_ids = {id(cluster) for cluster, _ in primary}
    pulse_watch = sorted(
        [
            pair
            for pair in assessed
            if id(pair[0]) not in primary_ids and telegram_pulse(pair[0])[0] >= 4.0
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
            "ситуационные кластеры и отдельно показывает evidence mix, Telegram pulse "
            "и изменение относительно предыдущих дней. Это не независимая "
            "верификация и не заменяет атрибуцию в итоговой сводке."
        ),
        "",
        f"- День: **{markdown_escape(target_day)}**",
        f"- Situation clusters: **{len(current_clusters)}**",
        f"- Accepted публикаций после strict gate: **{counts.get('accepted', 0)}**",
        f"- Strict-filtered ложных/слабых кандидатов: **{counts.get('strict_filtered', 0)}**",
        f"- Relevant публикаций до strict gate: **{counts.get('relevant', 0)}**",
        f"- Peripheral публикаций до strict gate: **{counts.get('peripheral', 0)}**",
        f"- Отфильтровано как off-topic первым gate: **{counts.get('irrelevant', 0)}**",
        f"- Redacted записей, не использованных для синтеза: **{counts.get('redacted', 0)}**",
        f"- Исторический baseline: **{len(history_clusters)} дн.**",
        "",
        "### Приоритетные situation clusters",
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
        group_summary = ", ".join(
            f"{markdown_escape(group)}: {count}" for group, count in groups.most_common()
        ) or "нет данных"
        lines += [
            f"#### {index}. {markdown_escape(_display_title(cluster))} · `{markdown_escape(temporal.status)}`",
            "",
            (
                f"- Editorial rank: **{rank:.1f}**; importance: **{importance:.1f}/10**; "
                f"novelty: **{temporal.novelty:.1f}/10**"
            ),
            (
                f"- Evidence mix: **{markdown_escape(evidence_label)} ({evidence_value:.1f}/10)** — "
                f"{group_summary}"
            ),
            (
                f"- Telegram pulse: **{markdown_escape(pulse_label)} ({pulse_value:.1f}/10)** — "
                f"{tg_families} unique channels, {tg_posts} posts, {tg_perspectives} perspectives"
            ),
            (
                f"- 7-day delta: **{markdown_escape(temporal.status)}**; matched historical days: "
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
            notes: list[str] = []
            if _is_routine_alert(cluster):
                notes.append("routine alert stream")
            if _is_broad_roundup(cluster):
                notes.append("broad roundup")
            if _is_weak_unlocated(cluster):
                notes.append("unlocated single-source")
            if _insufficient_primary_evidence(cluster):
                notes.append("thin evidence")
            note = " · " + ", ".join(notes) if notes else ""
            lines.append(
                f"- **{markdown_escape(_display_title(cluster))}** · "
                f"`{markdown_escape(temporal.status)}` · pulse "
                f"**{markdown_escape(pulse_label)} {pulse_value:.1f}/10** · "
                f"{tg_families} channels / {tg_posts} posts{note}"
            )
        lines.append("")

    lines += [
        "### Правила чтения контекста",
        "",
        "- Первый relevance gate максимизирует recall; strict editorial gate повторно проверяет war-сигналы с границами слов и отсекает ложные совпадения вроде `удар` внутри `государственный`.",
        "- Memorial/obituary/hero-history posts не трактуются как новое событие суток, даже если внутри биографии описан исторический удар.",
        "- `Evidence mix` — эвристика разнообразия типов источников, а не число независимых подтверждений.",
        "- `Telegram pulse` измеряет интенсивность и ширину обсуждения, а не достоверность.",
        "- Production clustering использует topic + explicit geographic signature; multi-location roundups не могут цепочкой склеивать разные театры.",
        "- Оперативные публикации без явной географии не объединяются между разными source families.",
        "- Поток рутинных предупреждений о движении целей не конкурирует за top-rank с подтверждёнными последствиями и многоканальными событиями.",
        "- Frontline/PVO/naval clusters с `thin` evidence остаются ниже primary; слабый support-сигнал также не поднимается только за счёт novelty.",
        "- В primary top-N действует ограничение на доминирование одной темы; это редакционный diversity guard, а не оценка истины.",
        "- `NEW/ESCALATING/CONTINUING/DECLINING` сравнивают кластер с эвристически похожими событиями предыдущих дней.",
        "- Итоговая редакционная сводка должна сохранять атрибуцию спорных и односторонних утверждений.",
        "",
    ]
    return "\n".join(lines)
