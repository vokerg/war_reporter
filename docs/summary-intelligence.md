# Summary intelligence layer

## Purpose

War Reporter collection is intentionally unchanged by this layer. The collector continues to persist attributable public source projections and `reports/daily/YYYY-MM-DD.md` remains the complete source ledger.

The summary intelligence layer exists only to make the editorial synthesis input tractable and useful. It converts the publication stream into stable daily situation clusters before ChatGPT writes `reports/summary/YYYY-MM-DD.md`.

The target question is no longer only "what did configured sources publish today?". The summary should primarily answer:

> What materially changed today compared with the recent baseline, how well is that development supported, and where is there a meaningful early information pulse that still needs verification?

## Boundary

The layer is post-collection and deterministic.

It must not:

- fetch new sources;
- modify `data/raw/` or `data/state.json`;
- create a second persistence system;
- call an LLM or external model API;
- reconstruct content removed by `public_redacted_v1`;
- convert source repetition into independent corroboration;
- infer verified territorial control.

It may read the current public source projection and up to seven previous local report days to build editorial navigation context.

## Pipeline

```text
configured collection                          unchanged
        |
        v
public source projections
        |
        +------------------------------+
        |                              |
        v                              v
complete source ledger          summary intelligence layer
reports/daily/...               relevance filtering
                               -> multilingual normalization
                               -> topic classification
                               -> explicit geographic signature
                               -> daily situation clusters
                               -> evidence mix
                               -> Telegram pulse
                               -> temporal comparison
                               -> materiality-aware ranking
                                      |
                                      v
                              pre-synthesis context
                                      |
                                      v
                              ChatGPT editorial summary
```

The pre-synthesis context is embedded near the top of the existing daily digest. The full source ledger remains below it. This avoids shards, intermediate JSON, another durable report tree or another write-capable workflow.

## Relevance

Source membership must never determine topic relevance by itself.

A Russian milblogger post about wildfires in France, Iran or another unrelated conflict remains in the source ledger but must not enter summary clustering merely because the source belongs to `ru-milbloggers`.

The first implementation uses conservative multilingual war-context and action anchors. The output classes are:

- `relevant`: direct war development suitable for situation clustering;
- `peripheral`: contextual diplomacy/politics that can surface at lower priority;
- `irrelevant`: kept in the ledger but omitted from synthesis context;
- `redacted`: content-neutral public projection; never synthesized.

False negatives are preferable to turning a high-volume source group into an automatic topic label. The full ledger remains available for audit and correction.

## Situation clusters

The unit of synthesis is a **daily situation cluster**, not a publication and not a fuzzy global claim graph.

The first prototype used conservative lexical similarity between candidate events. A real-day quality pass on 2026-08-05 exposed a failure mode: single-linkage-style accumulation could let broad roundups bridge unrelated places and gradually contaminate a large cluster.

Production grouping therefore uses a simpler and more explainable rule:

- topic;
- explicit geographic signature found in the publication text/source identity;
- a small semantic signature for equipment/infrastructure classes when useful.

Publications with one location are grouped with the same topic/location stream. Multi-location roundups keep their own signature and cannot bridge single-location clusters. Unlocated material remains explicitly unlocated instead of inheriting geography from neighboring posts.

This deliberately trades some recall for cluster purity. For a daily executive summary, several clean situation clusters are preferable to one large but ambiguous semantic cluster.

Multilingual canonicalization remains useful for normalization and temporal comparison, but lexical similarity is not allowed to override an explicit geographic mismatch in the production grouping path.

The implementation aims to reduce roughly one thousand daily publications to tens of situation clusters and then expose a small ranked set plus a Telegram watchlist.

## Evidence and pulse are separate axes

There is no single universal source weight.

### Evidence mix

Evidence mix answers:

> What kinds of sources are represented around this situation cluster?

The heuristic gives the strongest structural weight to OSINT, specialist analysis and established media, while retaining official sources as authoritative for their own statements. Low-trust milbloggers contribute much less to evidence strength.

The value is explicitly **not** a count of independent confirmations. Shared upstream reporting can still exist across different outlets.

OSINT therefore raises the structural evidence signal without suppressing faster but weaker signals.

### Telegram pulse

Telegram pulse answers a different question:

> How broad and intense is discussion of this development across Telegram right now?

Pulse is based primarily on:

- unique source families/channels;
- capped mentions per channel;
- perspective diversity.

Repeated posts from one channel are capped. A single channel posting twelve times must not look like a twelve-source event. Conversely, several Russian and Ukrainian channels converging rapidly on one topic can produce a high pulse even before independent verification exists.

Pulse is not truth and never increases a claim's factual status by itself.

## Routine alerts

Target-movement warnings and air-raid alerts are valuable as pulse data but are usually poor executive-summary units by themselves.

A stream dominated by phrases such as target course, direction, threat or shelter warning is classified as routine alert chatter when it has no reported material effects and only a narrow source-family footprint.

Routine alert streams:

- remain visible in the complete source ledger;
- may appear in the Telegram pulse watchlist when genuinely broad;
- do not compete directly for primary top-rank against casualties, damage, territorial developments or multi-source material events.

This prevents dozens of individually `NEW` Air Force alerts from displacing the actual combined attack they describe.

## Temporal delta

Current situation clusters are compared with structurally similar clusters from up to seven preceding report days.

The initial states are:

- `NEW`: no comparable recent situation cluster;
- `ESCALATING`: current pulse is materially above the matched recent baseline;
- `CONTINUING`: similar pattern and intensity remain present;
- `DECLINING`: current pulse is materially below the matched recent baseline.

Future iterations may add `REVERSAL` and `DISPUTED` only when the implementation can identify those states without pretending that heuristics establish operational truth.

Temporal status is a navigation aid. It does not independently establish that the underlying event occurred.

## Editorial ranking

Ranking intentionally separates four concepts:

- **importance**: inherent military/political significance of the candidate topic;
- **novelty**: degree of change against the recent baseline;
- **pulse**: current information-space intensity;
- **evidence mix**: structural strength/diversity of source types.

`NEW` is not automatically the most important state. Materiality, evidence structure and multi-channel pulse can outrank novelty alone. Source-family breadth provides a bounded bonus, while routine alerts and broad multi-location roundups receive penalties in primary selection.

Primary top-N also has a per-topic diversity guard so that one high-volume category cannot consume the entire executive context.

The coefficients are editorial heuristics and must be tuned against observed historical reports. They are not epistemic probabilities.

## Daily digest contract

The automatic daily digest has two layers:

1. a compact `Контекст для редакционного синтеза` section near the top;
2. the existing complete attributable source ledger below it.

The context includes:

- relevance/off-topic counts;
- situation-cluster count;
- top material situation clusters by editorial rank;
- importance and novelty;
- evidence mix;
- Telegram pulse;
- seven-day delta;
- representative source excerpts from diverse source families;
- a pulse watchlist for lower-ranked but rapidly discussed candidates.

`public_redacted_v1` records are counted but never contribute content.

All untrusted source names and excerpts are Markdown-escaped before inclusion. Original links are rendered only when they are valid `http`/`https` URLs.

## ChatGPT summary contract

ChatGPT should use the deterministic context as its primary navigation layer, then inspect the underlying source-ledger records needed to resolve attribution, disagreements, casualty updates and high-impact claims.

The final daily summary should be change-oriented:

1. **Картина дня** — compact overall assessment;
2. **Что изменилось** — ranked material changes vs recent baseline;
3. **Фронт** — only changed, disputed or unusually high-pulse sectors;
4. **Дальние удары** — changes in scale, geography and target pattern, not a strike chronology;
5. **Telegram pulse** — early/high-velocity signals clearly separated from verification;
6. **Установлено / вероятно / заявления сторон** — concise epistemic separation with attribution;
7. **На что смотреть дальше** — concrete indicators that could confirm or weaken the emerging interpretation.

The summary must not repeat deterministic scores as if they were probabilities. It should translate them into editorial prioritization while preserving source semantics.

## Quality gates

Regression coverage must include at least:

- off-topic material from a war-focused Telegram source is excluded from context;
- cross-language publications about one development can normalize consistently;
- one channel cannot manufacture high Telegram pulse through repeated posts;
- multi-channel, cross-perspective Telegram activity can surface as high pulse;
- OSINT improves evidence mix independently of pulse;
- historical matching distinguishes new from escalating/continuing patterns;
- redacted content never enters pre-synthesis excerpts;
- untrusted Markdown/HTML cannot alter context structure;
- routine alert fragments do not outrank material multi-source developments;
- Ukrainian geographic inflections are normalized for grouping;
- multi-location roundups cannot bridge otherwise separate local clusters;
- one topic cannot monopolize primary top-N;
- the complete source ledger remains present after context insertion.

Real historical days are part of the acceptance surface. A synthetic green test suite is not enough if the generated top clusters remain editorially incoherent.

Future quality work should add corpus-based golden tests for cluster purity, missed-event rate, source concentration, novelty ranking and summary usefulness across several historical days.
