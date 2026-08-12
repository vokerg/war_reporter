from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from .common import clean_text, parse_time
except ImportError:
    from common import clean_text, parse_time


TOPIC_LABELS = {
    "frontline": "Фронт",
    "strikes": "Дальние и воздушные удары",
    "civilian-harm": "Потери и гражданские последствия",
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

SANCTIONS_PATTERNS = (
    r"\bsanctions\b",
    r"\bsanctioned\b",
    r"\bсанкци(?:и|й|ями|ях|он\w*)\b",
    r"\bсанкці(?:ї|й|ями|ях|йн\w*)\b",
)

CANONICAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ukraine", (r"\bukraine\b", r"\bукраїн\w*", r"\bукраин\w*", r"\bвсу\b", r"\bзсу\b")),
    ("russia", (r"\brussia\w*\b", r"\bросси\w*", r"\bросі\w*", r"\bвс рф\b")),
    ("crimea", (r"\bcrimea\b", r"\bкрым\w*", r"\bкрим\w*")),
    ("odesa", (r"\bodes[as]\w*\b", r"\bодес\w*", r"\bодещ\w*")),
    ("kyiv", (r"\bkyiv\w*\b", r"\bkiev\w*\b", r"\bки[єї]в\w*", r"\bкиев\w*")),
    ("kharkiv", (r"\bkharkiv\w*\b", r"\bхарьков\w*", r"\bхарків\w*", r"\bхарков\w*")),
    (
        "sumy",
        (
            r"\bsumy\w*\b",
            r"\bсуми\b",
            r"\bсумы\b",
            r"\bсумщ\w*",
            r"\bсумск\w*",
            r"\bсумськ\w*",
            r"\bсумах\b",
        ),
    ),
    ("kherson", (r"\bkherson\w*\b", r"\bхерсон\w*")),
    ("zaporizhzhia", (r"\bzapori\w*\b", r"\bзапорож\w*", r"\bзапоріж\w*")),
    ("dnipro", (r"\bdnipro\w*\b", r"\bднепр\w*", r"\bдніпр\w*")),
    ("donetsk", (r"\bdonetsk\w*\b", r"\bдонец\w*", r"\bдонець\w*")),
    ("luhansk", (r"\bluhansk\w*\b", r"\blugansk\w*\b", r"\bлуган\w*")),
    ("kursk", (r"\bkursk\w*\b", r"\bкурск\w*")),
    ("belgorod", (r"\bbelgorod\w*\b", r"\bбелгород\w*")),
    ("sevastopol", (r"\bsevastopol\w*\b", r"\bсевастопол\w*")),
    ("black-sea", (r"\bblack sea\b", r"\bчерн\w+\s+мор\w+", r"\bчорн\w+\s+мор\w+")),
    ("konstantynivka", (r"\bkonstant\w*\b", r"\bконстантинов\w*", r"\bкостянтинів\w*")),
    ("pokrovsk", (r"\bpokrovsk\w*\b", r"\bпокровск\w*", r"\bпокровськ\w*")),
    ("chasiv-yar", (r"\bchasiv yar\b", r"\bчасов\w*\s+яр\w*", r"\bчасів\w*\s+яр\w*")),
    ("kupiansk", (r"\bkupiansk\w*\b", r"\bkupyansk\w*\b", r"\bкупянск\w*", r"\bкуп.?янськ\w*")),
    ("sloviansk", (r"\bsloviansk\w*\b", r"\bslavyansk\w*\b", r"\bславянск\w*", r"\bслов.?янськ\w*")),
    ("chernihiv", (r"\bchernihiv\w*\b", r"\bчерніг\w*", r"\bчерниг\w*")),
    ("mykolaiv", (r"\bmykolaiv\w*\b", r"\bмиколаїв\w*", r"\bниколаев\w*")),
    ("poltava", (r"\bpoltava\w*\b", r"\bполтав\w*")),
    ("tula", (r"\btula\w*\b", r"\bтульск\w*")),
    ("rostov", (r"\brostov\w*\b", r"\bростов\w*")),
    ("krasnodar", (r"\bkrasnodar\w*\b", r"\bкраснодар\w*")),
    ("drone", (r"\bdrones?\b", r"\buav\w*\b", r"\bбпла\b", r"\bдрон\w*", r"\bбезпілот\w*", r"\bбеспилот\w*")),
    ("missile", (r"\bmissiles?\b", r"\brockets?\b", r"\bракет\w*")),
    ("strike", (r"\bstrikes?\b", r"\battack\w*\b", r"\bудар\w*", r"\bатак\w*", r"\bобстріл\w*", r"\bобстрел\w*")),
    ("air-defence", (r"\bair defen[cs]e\b", r"\bпво\b", r"\bпротиповітр\w*")),
    ("frontline", (r"\bfrontline\b", r"\badvance\w*\b", r"\bassault\w*\b", r"\bфронт\w*", r"\bнаступ\w*", r"\bштурм\w*", r"\bпродвиж\w*")),
    (
        "casualties",
        (
            r"\bkilled\b",
            r"\bwounded\b",
            r"\bcasualt\w*\b",
            r"\bпогиб\w*",
            r"\bпострадав\w*",
            r"\bранен\w*",
            r"\bзагин\w*",
            r"\bпоран\w*",
        ),
    ),
    ("refinery", (r"\brefiner\w*\b", r"\bнпз\b", r"\bнефтеперераб\w*", r"\bнафтоперероб\w*")),
    ("railway", (r"\brailway\w*\b", r"\brailroad\w*\b", r"\bжелезнодорож\w*", r"\bж/д\b", r"\bзалізнич\w*")),
    ("port", (r"\bports?\b", r"\bпорт\w*")),
    ("s400", (r"\bs-?400\b", r"\bс-?400\b")),
    ("patriot", (r"\bpatriot\b",)),
    ("pantsir", (r"\bpantsir\b", r"\bпанцир\w*")),
    ("tor", (r"\bтор\b", r"\btor\b")),
    ("sanctions", SANCTIONS_PATTERNS),
    ("aid", (r"\bmilitary aid\b", r"\bweapons? package\b", r"\bвоенн\w+\s+помощ\w*", r"\bвійськов\w+\s+допомог\w*")),
)

LOCATION_ANCHORS = {
    "crimea", "odesa", "kyiv", "kharkiv", "sumy", "kherson", "zaporizhzhia",
    "dnipro", "donetsk", "luhansk", "kursk", "belgorod", "sevastopol",
    "black-sea", "konstantynivka", "pokrovsk", "chasiv-yar", "kupiansk", "sloviansk",
    "chernihiv", "mykolaiv", "poltava", "tula", "rostov", "krasnodar",
}
WAR_ACTION_ANCHORS = {
    "drone", "missile", "strike", "air-defence", "frontline", "casualties",
    "refinery", "railway", "port",
}
CONTEXT_ANCHORS = {"ukraine", "russia", "crimea"} | LOCATION_ANCHORS
SUPPORT_ANCHORS = {"sanctions", "aid"}

MAJOR_SIGNAL_PATTERNS = re.compile(
    r"\bmassiv\w*|\blarge[- ]scale\b|\bмассирован\w*|\bмасован\w*|"
    r"\bbreakthrough\b|\bпрорыв\w*|\bstrategic\w*|\bстратегичес\w*|\bстратегіч\w*",
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

    if group == "official-ua" and (has_action or has_support):
        return "relevant"
    if has_context and (has_action or has_support):
        return "relevant"

    political = bool(
        re.search(
            r"\bceasefire\b|\bnegotiat\w*|\btreaty\b|\bsummit\b|"
            r"\bпереговор\w*|\bперемир\w*|\bсаммит\w*|\bмирн\w+\s+угод\w*|"
            r"\bpeace deal\b|\bsecurity guarantee\b",
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
    if "black-sea" in anchors or re.search(
        r"\bnaval\w*|\bморск\w+|\bморськ\w+",
        canonical_text,
    ):
        return "naval"
    if "air-defence" in anchors or anchors.intersection(
        {"s400", "patriot", "pantsir", "tor"}
    ):
        return "air-defence"
    if anchors.intersection({"drone", "missile", "strike"}):
        return "strikes"
    if "frontline" in anchors:
        return "frontline"
    if anchors.intersection({"refinery", "railway", "port"}):
        return "energy"
    if anchors.intersection(SUPPORT_ANCHORS):
        return "support"
    if re.search(
        r"\bosint\b|\bgeolocat\w*|\bгеолокац\w*|\bверификац\w*",
        canonical_text,
    ):
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
        published_at=parse_time(item.get("published_at"))
        or parse_time(item.get("collected_at")),
        text=text,
        canonical_text=canonical_text,
        tokens=_tokens(canonical_text),
        anchors=frozenset(anchors),
        topic=classify_topic(anchors, canonical_text),
        relevance=relevance,
    )


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
    perspectives = {
        item.perspective
        for item in unique
        if item.perspective not in {"", "unknown"}
    }
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
