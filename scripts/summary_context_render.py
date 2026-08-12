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
        TemporalAssessment,
        _sample_items,
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
        TemporalAssessment,
        _sample_items,
        evidence_score,
        importance_score,
        prepare_item,
        telegram_pulse,
    )


DISPLAY_LOCATION_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("kyiv", "Киев/область", (r"\bkyiv\w*\b", r"\bkiev\w*\b", r"\bки[єї]в\w*", r"\bкиев\w*")),
    ("odesa", "Одесса/область", (r"\bodes[as]\w*\b", r"\bодес\w*", r"\bодещ\w*")),
    ("kharkiv", "Харьков/область", (r"\bkharkiv\w*\b", r"\bхарьков\w*", r"\bхарків\w*", r"\bхарков\w*")),
    ("sumy", "Сумская область", (r"\bsumy\w*\b", r"\bсуми\b", r"\bсумы\b", r"\bсумщ\w*", r"\bсумск\w*", r"\bсумськ\w*", r"\bсумах\b")),
    ("kherson", "Херсон/область", (r"\bkherson\w*\b", r"\bхерсон\w*")),
    ("zaporizhzhia", "Запорожье/область", (r"\bzapori\w*\b", r"\bзапорож\w*", r"\bзапоріж\w*")),
    ("dnipro", "Днепропетровская область", (r"\bdnipro\w*\b", r"\bднепр\w*", r"\bдніпр\w*")),
    ("donetsk", "Донецкая область", (r"\bdonetsk\w*\b", r"\bдонец\w*", r"\bдонець\w*")),
    ("luhansk", "Луганская область", (r"\bluhansk\w*\b", r"\blugansk\w*\b", r"\bлуган\w*")),
    ("crimea", "Крым", (r"\bcrimea\w*\b", r"\bкрым\w*", r"\bкрим\w*")),
    ("kursk", "Курская область", (r"\bkursk\w*\b", r"\bкурск\w*")),
    ("belgorod", "Белгородская область", (r"\bbelgorod\w*\b", r"\bбелгород\w*")),
    ("sevastopol", "Севастополь", (r"\bsevastopol\w*\b", r"\bсевастопол\w*")),
    ("black-sea", "Чёрное море", (r"\bblack sea\b", r"\bчерн\w+\s+мор\w+", r"\bчорн\w+\s+мор\w+")),
    ("konstantynivka", "Константиновка", (r"\bkonstant\w*\b", r"\bконстантинов\w*", r"\bкостянтинів\w*")),
    ("pokrovsk", "Покровск", (r"\bpokrovsk\w*\b", r"\bпокровск\w*", r"\bпокровськ\w*")),
    ("chasiv-yar", "Часов Яр", (r"\bchasiv yar\b", r"\bчасов\w*\s+яр\w*", r"\bчасів\w*\s+яр\w*")),
    ("kupiansk", "Купянск", (r"\bkupiansk\w*\b", r"\bkupyansk\w*\b", r"\bкупянск\w*", r"\bкуп.?янськ\w*")),
    ("sloviansk", "Славянск", (r"\bsloviansk\w*\b", r"\bslavyansk\w*\b", r"\bславянск\w*", r"\bслов.?янськ\w*")),
    ("chernihiv", "Чернигов/область", (r"\bchernihiv\w*\b", r"\bчерніг\w*", r"\bчерниг\w*")),
    ("mykolaiv", "Николаев/область", (r"\bmykolaiv\w*\b", r"\bмиколаїв\w*", r"\bниколаев\w*")),
    ("poltava", "Полтавская область", (r"\bpoltava\w*\b", r"\bполтав\w*")),
    ("tula", "Тульская область", (r"\btula\w*\b", r"\bтульск\w*")),
    ("rostov", "Ростовская область", (r"\brostov\w*\b", r"\bростов\w*")),
    ("krasnodar", "Краснодарский край", (r"\bkrasnodar\w*\b", r"\bкраснодар\w*")),
)

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
    r"\bblack sea\b|\bчерн\w+\s+мор\w+|\bчорн\w+\s+мор\w+|"
    r"\bnaval drone\w*|\bsea drone\w*|\bморск\w+\s+(?:дрон\w*|беспилот\w*|катер\w*)|"
    r"\bморськ\w+\s+(?:дрон\w*|безпілот\w*|катер\w*)|\bкорабл\w*|\bсудн\w*",
    re.IGNORECASE,
)
STRICT_SANCTIONS_RE = re.compile(
    r"\bsanctions\b|\bsanctioned\b|"
    r"\bсанкци(?:и|й|ями|ях|он\w*)\b|"
    r"\bсанкці(?:ї|й|ями|ях|йн\w*)\b",
    re.IGNORECASE,
)
STRICT_AID_RE = re.compile(
    r"\bmilitary aid\b|\bweapons? package\b|"
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
    url = str(value or "").strip()
    if not url or any(ord(char) < 32 for char in url):
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
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
    text = clean_text(item.text).casefold()
    return {
        key: label
        for key, label, patterns in DISPLAY_LOCATION_PATTERNS
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    }


def _cluster_location_map(cluster: EventCluster) -> dict[str, str]:
    if not cluster.items:
        return {}
    maps = [_item_location_map(item) for item in cluster.items]
    common = set(maps[0])
    for mapping in maps[1:]:
        common.intersection_update(mapping)
    if common:
        first = maps[0]
        return {key: first[key] for key in first if key in common}
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for mapping in maps:
        for key, label in mapping.items():
            counts[key] += 1
            labels[key] = label
    if not counts:
        return {}
    key = counts.most_common(1)[0][0]
    return {key: labels[key]}


def _editorial_topic(item: PreparedItem) -> str:
    if CASUALTY_RE.search(item.text):
        if STRICT_STRIKE_RE.search(item.text):
            return "strikes"
        return "civilian-harm"
    return item.topic


def _has_support_signal(text: str) -> bool:
    return bool(STRICT_SANCTIONS_RE.search(text) or STRICT_AID_RE.search(text))


def _strict_candidate(item: PreparedItem, topic: str, locations: tuple[str, ...]) -> bool:
    text = item.text
    if MEMORIAL_RE.search(text):
        return False
    current_context = bool(CURRENT_WAR_CONTEXT_RE.search(text))
    contextualized = bool(locations) or current_context or item.group == "official-ua"
    if topic == "civilian-harm":
        return bool(CASUALTY_RE.search(text)) and contextualized and (
            bool(locations) or current_context or bool(STRICT_STRIKE_RE.search(text))
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
        return _has_support_signal(text) and (
            current_context or item.group in {"official-ua", "international-media", "analysts"}
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
    if topic == "support":
        if STRICT_SANCTIONS_RE.search(item.text):
            return ("sanctions",)
        if STRICT_AID_RE.search(item.text):
            return ("aid",)
        return ()
    if topic not in {"energy", "air-defence", "naval"}:
        return ()
    return tuple(
        sorted(
            key
            for key, pattern in EQUIPMENT_PATTERNS
            if re.search(pattern, item.text, flags=re.IGNORECASE)
        )
    )


def _build_situation_clusters(
    items: Iterable[dict[str, Any]],
) -> tuple[list[EventCluster], dict[str, int]]:
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
    if cluster.topic in {"frontline", "air-defence", "naval", "support"}:
        return score < 3.0
    if cluster.topic == "energy":
        return score < 1.5
    return False


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a = set(left)
    b = set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _temporal_match_score(current: EventCluster, historical: EventCluster) -> float:
    if current.topic != historical.topic:
        paired = {current.topic, historical.topic}
        if not paired <= {"strikes", "civilian-harm", "air-defence", "energy"}:
            return 0.0
    current_locations = set(_cluster_location_map(current))
    historical_locations = set(_cluster_location_map(historical))
    if current_locations and historical_locations:
        if not current_locations.intersection(historical_locations):
            return 0.0
        location = 1.0
    else:
        location = 0.0
    anchors = _jaccard(current.anchor_union, historical.anchor_union)
    tokens = _jaccard(current.token_union, historical.token_union)
    return 0.55 * location + 0.30 * anchors + 0.15 * tokens


def _assess_temporal(
    cluster: EventCluster,
    history_by_day: dict[str, list[EventCluster]],
) -> TemporalAssessment:
    matched_pulses: list[float] = []
    matched_days = 0
    for clusters in history_by_day.values():
        day_matches = [
            candidate
            for candidate in clusters
            if _temporal_match_score(cluster, candidate) >= 0.48
        ]
        if not day_matches:
            continue
        matched_days += 1
        best = max(day_matches, key=lambda candidate: _temporal_match_score(cluster, candidate))
        matched_pulses.append(telegram_pulse(best)[0])
    if not matched_pulses:
        return TemporalAssessment("NEW", 9.0, None, 0)
    baseline = sum(matched_pulses) / len(matched_pulses)
    current = telegram_pulse(cluster)[0]
    if baseline > 0 and current >= baseline * 1.8 and current - baseline >= 1.0:
        return TemporalAssessment("ESCALATING", 7.0, baseline, matched_days)
    if baseline > 0 and current <= baseline * 0.55 and baseline - current >= 1.0:
        return TemporalAssessment("DECLINING", 4.0, baseline, matched_days)
    return TemporalAssessment("CONTINUING", 2.0, baseline, matched_days)


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
    current_clusters, counts = _build_situation_clusters(current_items)
    history_clusters = {
        day: _build_situation_clusters(items)[0]
        for day, items in history_items_by_day.items()
    }
    assessed = [
        (cluster, _assess_temporal(cluster, history_clusters))
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
        "- Первый relevance gate максимизирует recall; strict editorial gate повторно проверяет war-сигналы с границами слов и отсекает ложные совпадения.",
        "- Memorial/obituary/hero-history posts не трактуются как новое событие суток, даже если внутри биографии описан исторический удар.",
        "- Удар и его последствия в одной географии остаются одним event-centric strike cluster; casualty-only updates остаются отдельной категорией.",
        "- `Evidence mix` — эвристика разнообразия типов источников, а не число независимых подтверждений.",
        "- `Telegram pulse` измеряет интенсивность и ширину обсуждения, а не достоверность.",
        "- Production clustering использует topic + explicit geographic signature; география берётся из текста публикации, а не из имени канала.",
        "- Target/equipment details не раскалывают обычный strike cluster; semantic hard-key применяется только там, где он определяет класс события.",
        "- Оперативные публикации без явной географии не объединяются между разными source families.",
        "- Поток рутинных предупреждений о движении целей не конкурирует за top-rank с подтверждёнными последствиями и многоканальными событиями.",
        "- Frontline/PVO/naval/support clusters с `thin` evidence остаются ниже primary; одиночный low-trust energy claim также не поднимается.",
        "- В primary top-N действует ограничение на доминирование одной темы; это редакционный diversity guard, а не оценка истины.",
        "- `NEW/ESCALATING/CONTINUING/DECLINING` описывают изменение информационного сигнала относительно эвристически похожих кластеров предыдущих дней, а не доказанное оперативное изменение.",
        "- Итоговая редакционная сводка должна сохранять атрибуцию спорных и односторонних утверждений.",
        "",
    ]
    return "\n".join(lines)
