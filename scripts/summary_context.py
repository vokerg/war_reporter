from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

try:
    from .common import clean_text, parse_time
except ImportError:
    from common import clean_text, parse_time


TOPIC_LABELS = {
    "frontline": "Фронт",
    "strikes": "Дальние и воздушные удары",
    "civilian-harm": "Гражданские последствия",
    "air-defence": "ПВО",
    "naval": "Чёрное море",
    "energy": "Энергетика и логистика",
    "support": "Военная помощь и дипломатия",
    "investigations": "OSINT и расследования",
    "other": "Прочее",
}

TOPIC_IMPORTANCE = {
    "frontline": 8.0,
    "strikes": 8.0,
    "civilian-harm": 7.5,
    "air-defence": 7.0,
    "naval": 6.5,
    "energy": 6.5,
    "support": 5.5,
    "investigations": 5.0,
    "other": 3.0,
}

GROUP_EVIDENCE_WEIGHT = {
    "osint": 3.5,
    "analysts": 2.5,
    "international-media": 2.5,
    "official-ua": 1.6,
    "official-ru": 1.6,
    "ua-media-bloggers": 1.0,
    "ru-milbloggers": 0.6,
}

TRUST_RANK = {
    "high": 4,
    "primary": 3,
    "medium": 2,
    "unknown": 1,
    "low": 0,
}

GROUP_SAMPLE_RANK = {
    "osint": 7,
    "international-media": 6,
    "analysts": 5,
    "official-ua": 4,
    "official-ru": 4,
    "ua-media-bloggers": 2,
    "ru-milbloggers": 1,
}

STOPWORDS = {
    "который", "которая", "которые", "этого", "этой", "этот", "также", "после",
    "через", "между", "сегодня", "вчера", "более", "менее", "около", "только",
    "було", "була", "були", "який", "яка", "які", "цього", "після", "також",
    "сьогодні", "вчора", "понад", "лише", "щодо", "повідомив",
    "сообщил", "сообщили", "заявил", "заявили", "заявила", "данным", "даними",
    "about", "after", "before", "their", "there", "which", "while", "today",
    "yesterday", "reported", "reports", "according", "would", "could", "should",
    "have", "has", "with", "from", "into", "over", "under", "more", "than",
}

CANONICAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ukraine", (r"\bukraine\b", r"україн\w*", r"украин\w*", r"\bвсу\b", r"\bзсу\b")),
    ("russia", (r"\brussia\w*\b", r"росси\w*", r"\bвс рф\b")),
    ("crimea", (r"\bcrimea\b", r"крым\w*", r"крим\w*")),
    ("odesa", (r"\bodes[as]\w*\b", r"одес\w*", r"одещ\w*")),
    ("kyiv", (r"\bkyiv\w*\b", r"\bkiev\w*\b", r"київ\w*", r"киев\w*")),
    ("kharkiv", (r"\bkharkiv\w*\b", r"харьков\w*", r"харків\w*")),
    ("sumy", (r"\bsumy\b", r"сум\w*")),
    ("kherson", (r"\bkherson\w*\b", r"херсон\w*")),
    ("zaporizhzhia", (r"\bzapori\w*\b", r"запорож\w*", r"запоріж\w*")),
    ("dnipro", (r"\bdnipro\w*\b", r"днепр\w*", r"дніпр\w*")),
    ("donetsk", (r"\bdonetsk\w*\b", r"донец\w*", r"донець\w*")),
    ("luhansk", (r"\bluhansk\w*\b", r"\blugansk\w*\b", r"луган\w*")),
    ("kursk", (r"\bkursk\w*\b", r"курск\w*")),
    ("belgorod", (r"\bbelgorod\w*\b", r"белгород\w*")),
    ("sevastopol", (r"\bsevastopol\w*\b", r"севастопол\w*")),
    ("black-sea", (r"\bblack sea\b", r"черн\w+\s+мор\w+", r"чорн\w+\s+мор\w+")),
    ("konstantynivka", (r"\bkonstant\w*\b", r"константинов\w*", r"костянтинів\w*")),
    ("pokrovsk", (r"\bpokrovsk\w*\b", r"покровск\w*", r"покровськ\w*")),
    ("chasiv-yar", (r"\bchasiv yar\b", r"часов\w*\s+яр\w*", r"часів\w*\s+яр\w*")),
    ("kupiansk", (r"\bkupiansk\w*\b", r"\bkupyansk\w*\b", r"купянск\w*", r"куп'янськ\w*")),
    ("sloviansk", (r"\bsloviansk\w*\b", r"\bslavyansk\w*\b", r"славянск\w*", r"слов'янськ\w*")),
    ("drone", (r"\bdrones?\b", r"\buav\w*\b", r"бпла", r"дрон\w*", r"безпілот\w*", r"беспилот\w*")),
    ("missile", (r"\bmissiles?\b", r"\brockets?\b", r"ракет\w*")),
    ("strike", (r"\bstrikes?\b", r"\battack\w*\b", r"удар\w*", r"атак\w*", r"обстріл\w*", r"обстрел\w*")),
    ("air-defence", (r"\bair defen[cs]e\b", r"\bпво\b", r"протиповітр\w*")),
    ("frontline", (r"\bfrontline\b", r"\badvance\w*\b", r"\bassault\w*\b", r"фронт\w*", r"наступ\w*", r"штурм\w*", r"продвиж\w*")),
    ("casualties", (r"\bkilled\b", r"\bwounded\b", r"\bcasualt\w*\b", r"погиб\w*", r"пострадав\w*", r"ранен\w*", r"загин\w*", r"поран\w*")),
    ("refinery", (r"\brefiner\w*\b", r"\bнпз\b", r"нефтеперераб\w*", r"нафтоперероб\w*")),
    ("railway", (r"\brailway\w*\b", r"\brailroad\w*\b", r"железнодорож\w*", r"\bж/д\b", r"залізнич\w*")),
    ("port", (r"\bports?\b", r"порт\w*")),
    ("s400", (r"\bs-?400\b", r"\bс-?400\b")),
    ("patriot", (r"\bpatriot\b",)),
    ("pantsir", (r"\bpantsir\b", r"панцир\w*")),
    ("tor", (r"\bтор\b", r"\btor\b")),
    ("sanctions", (r"\bsanctions?\b", r"санкц\w*")),
    ("aid", (r"\bmilitary aid\b", r"\bweapons? package\b", r"военн\w+\s+помощ\w*", r"військов\w+\s+допомог\w*")),
)

LOCATION_ANCHORS = {
    "crimea", "odesa", "kyiv", "kharkiv", "sumy", "kherson", "zaporizhzhia",
    "dnipro", "donetsk", "luhansk", "kursk", "belgorod", "sevastopol",
    "black-sea", "konstantynivka", "pokrovsk", "chasiv-yar", "kupiansk", "sloviansk",
}
EQUIPMENT_ANCHORS = {"refinery", "railway", "port", "s400", "patriot", "pantsir", "tor"}
WAR_ACTION_ANCHORS = {"drone", "missile", "strike", "air-defence", "frontline", "casualties", "refinery", "railway", "port"}
CONTEXT_ANCHORS = {"ukraine", "russia", "crimea"} | LOCATION_ANCHORS
SUPPORT_ANCHORS = {"sanctions", "aid"}

DISPLAY_ANCHORS = {
    "crimea": "Крым",
    "odesa": "Одесса/область",
    "kyiv": "Киев/область",
    "kharkiv": "Харьков/область",
    "sumy": "Сумская область",
    "kherson": "Херсон/область",
    "zaporizhzhia": "Запорожье/область",
    "dnipro": "Днепропетровская область",
    "donetsk": "Донецкая область",
    "luhansk": "Луганская область",
    "kursk": "Курская область",
    "belgorod": "Белгородская область",
    "sevastopol": "Севастополь",
    "black-sea": "Чёрное море",
    "konstantynivka": "Константиновка",
    "pokrovsk": "Покровск",
    "chasiv-yar": "Часов Яр",
    "kupiansk": "Купянск",
    "sloviansk": "Славянск",
    "refinery": "НПЗ",
    "railway": "железная дорога",
    "port": "портовая инфраструктура",
    "s400": "С-400",
    "patriot": "Patriot",
    "pantsir": "Панцирь",
    "tor": "Тор",
}

MAJOR_SIGNAL_PATTERNS = re.compile(
    r"\bmassiv\w*|\blarge[- ]scale\b|массирован\w*|масован\w*|"
    r"\bbreakthrough\b|прорыв\w*|strategic\w*|стратегичес\w*|стратегіч\w*",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[a-zа-яіїєґ0-9][a-zа-яіїєґ0-9'-]{2,}", re.IGNORECASE)


@dataclass(frozen=True)
class PreparedItem:
    raw: dict[str, Any]
    source_family: str
    platform: str
    group: str
    perspective: str
    trust: str
    published_at: datetime | None
    text: str
    canonical_text: str
    tokens: frozenset[str]
    anchors: frozenset[str]
    topic: str
    relevance: str


@dataclass
class EventCluster:
    topic: str
    items: list[PreparedItem] = field(default_factory=list)
    token_union: set[str] = field(default_factory=set)
    anchor_union: set[str] = field(default_factory=set)

    def add(self, item: PreparedItem) -> None:
        self.items.append(item)
        self.token_union.update(item.tokens)
        self.anchor_union.update(item.anchors)

    @property
    def location_anchors(self) -> set[str]:
        return self.anchor_union & LOCATION_ANCHORS


@dataclass(frozen=True)
class TemporalAssessment:
    status: str
    novelty: float
    baseline_pulse: float | None
    matched_days: int


def _source_family(item: dict[str, Any]) -> str:
    value = clean_text(str(item.get("source_name") or item.get("source") or "unknown"))
    return re.sub(r"\s+", " ", value).casefold()


def _canonicalize(text: str) -> tuple[str, set[str]]:
    value = clean_text(text).casefold()
    anchors: set[str] = set()
    for canonical, patterns in CANONICAL_PATTERNS:
        matched = False
        for pattern in patterns:
            if re.search(pattern, value, flags=re.IGNORECASE):
                matched = True
                value = re.sub(pattern, f" {canonical} ", value, flags=re.IGNORECASE)
        if matched:
            anchors.add(canonical)
    return clean_text(value), anchors


def _tokens(canonical_text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in TOKEN_RE.findall(canonical_text)
        if len(token) >= 4 and token not in STOPWORDS
    )


def classify_relevance(
    item: dict[str, Any],
    anchors: set[str],
    canonical_text: str,
) -> str:
    raw = item.get("raw")
    if isinstance(raw, dict) and raw.get("archive_policy") == "public_redacted_v1":
        return "redacted"
    if not canonical_text:
        return "irrelevant"

    group = str(item.get("group") or "other")
    has_context = bool(anchors & CONTEXT_ANCHORS)
    has_action = bool(anchors & WAR_ACTION_ANCHORS)
    has_support = bool(anchors & SUPPORT_ANCHORS)

    # Ukrainian official/local authorities often report attacks without saying
    # "Ukraine" explicitly; the source identity supplies the missing context.
    if group == "official-ua" and (has_action or has_support):
        return "relevant"

    if has_context and (has_action or has_support):
        return "relevant"

    political = bool(
        re.search(
            r"\bceasefire\b|\bnegotiat\w*|\btreaty\b|\bsummit\b|"
            r"переговор\w*|перемир\w*|саммит\w*|мирн\w+\s+угод\w*|"
            r"peace deal|security guarantee",
            canonical_text,
            flags=re.IGNORECASE,
        )
    )
    if has_context and political:
        return "peripheral"
    return "irrelevant"


def classify_topic(anchors: set[str], canonical_text: str) -> str:
    if "casualties" in anchors:
        return "civilian-harm"
    if "black-sea" in anchors or re.search(r"\bnaval\w*|морск\w+|морськ\w+", canonical_text):
        return "naval"
    if "air-defence" in anchors or anchors.intersection({"s400", "patriot", "pantsir", "tor"}):
        return "air-defence"
    if anchors.intersection({"drone", "missile", "strike"}):
        return "strikes"
    if "frontline" in anchors:
        return "frontline"
    if anchors.intersection({"refinery", "railway", "port"}):
        return "energy"
    if anchors.intersection(SUPPORT_ANCHORS):
        return "support"
    if re.search(r"\bosint\b|geolocat\w*|геолокац\w*|верификац\w*", canonical_text):
        return "investigations"
    return "other"


def prepare_item(item: dict[str, Any]) -> PreparedItem:
    text = clean_text(
        " ".join(
            part
            for part in (
                clean_text(item.get("title")),
                clean_text(item.get("text")),
            )
            if part
        )
    )
    canonical_text, anchors = _canonicalize(text)
    relevance = classify_relevance(item, anchors, canonical_text)
    return PreparedItem(
        raw=item,
        source_family=_source_family(item),
        platform=str(item.get("platform") or "unknown"),
        group=str(item.get("group") or "other"),
        perspective=str(item.get("perspective") or "unknown"),
        trust=str(item.get("trust") or "unknown"),
        published_at=parse_time(item.get("published_at")) or parse_time(item.get("collected_at")),
        text=text,
        canonical_text=canonical_text,
        tokens=_tokens(canonical_text),
        anchors=frozenset(anchors),
        topic=classify_topic(anchors, canonical_text),
        relevance=relevance,
    )


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a = set(left)
    b = set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _topics_compatible(item: PreparedItem, cluster: EventCluster) -> bool:
    if item.topic == cluster.topic:
        return True
    paired = {item.topic, cluster.topic}
    if paired <= {"strikes", "civilian-harm", "air-defence", "energy"}:
        return bool((set(item.anchors) & cluster.anchor_union) & LOCATION_ANCHORS)
    return False


def _cluster_similarity(item: PreparedItem, cluster: EventCluster) -> float:
    if not _topics_compatible(item, cluster):
        return 0.0
    item_locations = set(item.anchors) & LOCATION_ANCHORS
    cluster_locations = cluster.location_anchors
    if item_locations and cluster_locations and not (item_locations & cluster_locations):
        return 0.0

    shared_anchors = set(item.anchors) & cluster.anchor_union
    anchor_score = min(1.0, len(shared_anchors) / 3)
    token_score = _jaccard(item.tokens, cluster.token_union)

    if item_locations and cluster_locations and (item_locations & cluster_locations):
        anchor_score = max(anchor_score, 0.65)

    return 0.65 * anchor_score + 0.35 * token_score


def build_event_clusters(items: Iterable[dict[str, Any]]) -> tuple[list[EventCluster], dict[str, int]]:
    prepared = [prepare_item(item) for item in items]
    counts = Counter(row.relevance for row in prepared)
    candidates = [row for row in prepared if row.relevance in {"relevant", "peripheral"}]
    candidates.sort(key=lambda row: row.published_at.isoformat() if row.published_at else "")

    clusters: list[EventCluster] = []
    for item in candidates:
        best: EventCluster | None = None
        best_score = 0.0
        for cluster in clusters:
            score = _cluster_similarity(item, cluster)
            if score > best_score:
                best = cluster
                best_score = score
        threshold = 0.36 if item.topic == "frontline" else 0.31
        if best is not None and best_score >= threshold:
            best.add(item)
        else:
            cluster = EventCluster(topic=item.topic)
            cluster.add(item)
            clusters.append(cluster)
    return clusters, dict(counts)


def _unique_family_items(cluster: EventCluster) -> list[PreparedItem]:
    by_family: dict[str, PreparedItem] = {}
    for item in cluster.items:
        current = by_family.get(item.source_family)
        candidate_rank = (
            GROUP_SAMPLE_RANK.get(item.group, 0),
            TRUST_RANK.get(item.trust, 0),
            item.published_at.isoformat() if item.published_at else "",
        )
        current_rank = (
            GROUP_SAMPLE_RANK.get(current.group, 0),
            TRUST_RANK.get(current.trust, 0),
            current.published_at.isoformat() if current and current.published_at else "",
        ) if current else (-1, -1, "")
        if current is None or candidate_rank > current_rank:
            by_family[item.source_family] = item
    return list(by_family.values())


def evidence_score(cluster: EventCluster) -> tuple[float, str, Counter[str]]:
    unique = _unique_family_items(cluster)
    groups = Counter(item.group for item in unique)
    perspectives = {item.perspective for item in unique if item.perspective not in {"", "unknown"}}
    score = 0.0
    for group, count in groups.items():
        weight = GROUP_EVIDENCE_WEIGHT.get(group, 0.5)
        score += weight * min(count, 2)
    if len(perspectives) >= 2:
        score += 1.0
    score = min(10.0, score)
    label = "strong" if score >= 6.0 else "mixed" if score >= 3.2 else "thin"
    return score, label, groups


def telegram_pulse(cluster: EventCluster) -> tuple[float, str, int, int, int]:
    telegram = [item for item in cluster.items if item.platform == "telegram"]
    families = {item.source_family for item in telegram}
    capped_mentions = sum(
        min(3, count)
        for count in Counter(item.source_family for item in telegram).values()
    )
    perspectives = {
        item.perspective
        for item in telegram
        if item.perspective not in {"", "unknown"}
    }
    score = (
        1.8 * math.log2(1 + len(families))
        + 0.35 * capped_mentions
        + 0.7 * max(0, len(perspectives) - 1)
    )
    score = min(10.0, score)
    label = "high" if score >= 6.0 else "medium" if score >= 3.0 else "low"
    return score, label, len(families), len(telegram), len(perspectives)


def importance_score(cluster: EventCluster) -> float:
    base = TOPIC_IMPORTANCE.get(cluster.topic, 3.0)
    text = " ".join(item.canonical_text for item in cluster.items[:20])
    if MAJOR_SIGNAL_PATTERNS.search(text):
        base += 1.0
    if cluster.anchor_union.intersection({"s400", "patriot", "refinery", "port"}):
        base += 0.5
    if cluster.topic == "civilian-harm" and "casualties" in cluster.anchor_union:
        base += 0.5
    return min(10.0, base)


def _cluster_match_score(current: EventCluster, historical: EventCluster) -> float:
    if current.topic != historical.topic:
        paired = {current.topic, historical.topic}
        if not paired <= {"strikes", "civilian-harm", "air-defence", "energy"}:
            return 0.0
    current_locations = current.location_anchors
    historical_locations = historical.location_anchors
    if current_locations and historical_locations:
        if not (current_locations & historical_locations):
            return 0.0
        location = 1.0
    else:
        location = 0.0
    anchors = _jaccard(current.anchor_union, historical.anchor_union)
    tokens = _jaccard(current.token_union, historical.token_union)
    return 0.55 * location + 0.30 * anchors + 0.15 * tokens


def assess_temporal(
    cluster: EventCluster,
    history_by_day: dict[str, list[EventCluster]],
) -> TemporalAssessment:
    matched_pulses: list[float] = []
    matched_days = 0
    for clusters in history_by_day.values():
        day_matches = [
            candidate
            for candidate in clusters
            if _cluster_match_score(cluster, candidate) >= 0.48
        ]
        if not day_matches:
            continue
        matched_days += 1
        best = max(day_matches, key=lambda candidate: _cluster_match_score(cluster, candidate))
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


def editorial_rank(cluster: EventCluster, temporal: TemporalAssessment) -> float:
    importance = importance_score(cluster)
    pulse = telegram_pulse(cluster)[0]
    evidence = evidence_score(cluster)[0]
    return 0.55 * importance + 0.30 * temporal.novelty + 0.10 * pulse + 0.05 * evidence


def _cluster_title(cluster: EventCluster) -> str:
    anchors = [
        DISPLAY_ANCHORS[key]
        for key in sorted(cluster.location_anchors)
        if key in DISPLAY_ANCHORS
    ]
    if not anchors:
        anchors = [
            DISPLAY_ANCHORS[key]
            for key in sorted(cluster.anchor_union & EQUIPMENT_ANCHORS)
            if key in DISPLAY_ANCHORS
        ]
    suffix = ", ".join(anchors[:2]) if anchors else "без устойчивой геопривязки"
    return f"{TOPIC_LABELS.get(cluster.topic, cluster.topic)} — {suffix}"


def _sample_items(cluster: EventCluster, limit: int = 5) -> list[PreparedItem]:
    unique = _unique_family_items(cluster)
    unique.sort(
        key=lambda item: (
            GROUP_SAMPLE_RANK.get(item.group, 0),
            TRUST_RANK.get(item.trust, 0),
            item.published_at.isoformat() if item.published_at else "",
        ),
        reverse=True,
    )
    selected: list[PreparedItem] = []
    used_groups: set[str] = set()
    for item in unique:
        if item.group in used_groups:
            continue
        selected.append(item)
        used_groups.add(item.group)
        if len(selected) >= limit:
            return selected
    for item in unique:
        if item in selected:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _excerpt(value: str, limit: int = 240) -> str:
    text = clean_text(value)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def render_summary_context(
    target_day: str,
    current_items: Iterable[dict[str, Any]],
    history_items_by_day: dict[str, Iterable[dict[str, Any]]],
    *,
    max_primary: int = 14,
    max_pulse_watch: int = 6,
) -> str:
    current_clusters, relevance_counts = build_event_clusters(current_items)
    history_clusters = {
        day: build_event_clusters(items)[0]
        for day, items in history_items_by_day.items()
    }

    assessed = [
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
        f"- День: **{target_day}**",
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
        lines += [
            f"#### {index}. {_cluster_title(cluster)} · `{temporal.status}`",
            "",
            (
                f"- Editorial rank: **{rank:.1f}**; importance: **{importance:.1f}/10**; "
                f"novelty: **{temporal.novelty:.1f}/10**"
            ),
            (
                f"- Evidence mix: **{evidence_label} ({evidence_value:.1f}/10)** — "
                + ", ".join(f"{group}: {count}" for group, count in groups.most_common())
            ),
            (
                f"- Telegram pulse: **{pulse_label} ({pulse_value:.1f}/10)** — "
                f"{tg_families} unique channels, {tg_posts} posts, "
                f"{tg_perspectives} perspectives"
            ),
            (
                f"- 7-day delta: **{temporal.status}**; matched historical days: "
                f"**{temporal.matched_days}**; baseline pulse: **{baseline}**"
            ),
            f"- Публикаций в cluster: **{len(cluster.items)}**",
            "- Репрезентативные источники:",
        ]
        for item in _sample_items(cluster):
            source = clean_text(str(item.raw.get("source_name") or item.raw.get("source") or "unknown"))
            published = str(item.raw.get("published_at") or item.raw.get("collected_at") or "")
            url = str(item.raw.get("url") or "")
            excerpt = _excerpt(item.text)
            lines.append(
                f"  - **{source}** · `{item.group}` · `{item.perspective}` · "
                f"{published} — {excerpt} · {url}"
            )
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
                f"- **{_cluster_title(cluster)}** · `{temporal.status}` · "
                f"pulse **{pulse_label} {pulse_value:.1f}/10** · "
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
