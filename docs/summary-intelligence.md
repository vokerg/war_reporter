# Summary intelligence layer

## Purpose

War Reporter collection is intentionally unchanged by this layer. The collector continues to persist attributable public source projections and `reports/daily/YYYY-MM-DD.md` remains the complete source ledger.

The summary intelligence layer exists only to make the editorial synthesis input tractable and useful. It converts the publication stream into candidate events before ChatGPT writes `reports/summary/YYYY-MM-DD.md`.

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
                               -> canonicalization
                               -> candidate event clustering
                               -> evidence mix
                               -> Telegram pulse
                               -> temporal comparison
                               -> editorial ranking
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

A Russian milblogger post about wildfires in France, Iran or another unrelated conflict remains in the source ledger but must not enter summary event clustering merely because the source belongs to `ru-milbloggers`.

The first implementation uses conservative multilingual war-context and action anchors. The output classes are:

- `relevant`: direct war development suitable for event clustering;
- `peripheral`: contextual diplomacy/politics that can surface at lower priority;
- `irrelevant`: kept in the ledger but omitted from synthesis context;
- `redacted`: content-neutral public projection; never synthesized.

False negatives are preferable to turning a high-volume source group into an automatic topic label. The full ledger remains available for audit and correction.

## Candidate event clusters

The unit of synthesis is a candidate event, not a publication.

The deterministic layer canonicalizes common Russian, Ukrainian and English aliases for major locations and event concepts. It then groups compatible publications using:

- event topic;
- shared location/equipment anchors;
- multilingual canonical anchors;
- bounded lexical similarity.

This is deliberately a candidate-clustering heuristic, not an assertion that all grouped publications describe exactly the same fact. ChatGPT must preserve disagreements and attribution inside a cluster.

The first implementation aims to reduce roughly one thousand daily publications to tens of event candidates and then expose a small ranked set plus a Telegram watchlist.

## Evidence and pulse are separate axes

There is no single universal source weight.

### Evidence mix

Evidence mix answers:

> What kinds of sources are represented around this candidate event?

The heuristic gives the strongest structural weight to OSINT, specialist analysis and established media, while retaining official sources as authoritative for their own statements. Low-trust milbloggers contribute much less to evidence strength.

The value is explicitly **not** a count of independent confirmations. Shared upstream reporting can still exist across different outlets.

OSINT therefore raises the structural evidence signal without suppressing faster but weaker signals.

### Telegram pulse

Telegram pulse answers a different question:

> How broad and intense is discussion of this event across Telegram right now?

Pulse is based primarily on:

- unique source families/channels;
- capped mentions per channel;
- perspective diversity.

Repeated posts from one channel are capped. A single channel posting twelve times must not look like a twelve-source event. Conversely, several Russian and Ukrainian channels converging rapidly on one topic can produce a high pulse even before independent verification exists.

Pulse is not truth and never increases a claim's factual status by itself.

## Temporal delta

Current event candidates are compared with heuristically similar event clusters from up to seven preceding report days.

The initial states are:

- `NEW`: no comparable recent event cluster;
- `ESCALATING`: current pulse is materially above the matched recent baseline;
- `CONTINUING`: similar pattern and intensity remain present;
- `DECLINING`: current pulse is materially below the matched recent baseline.

Future iterations may add `REVERSAL` and `DISPUTED` only when the implementation can identify those states without pretending that lexical heuristics establish operational truth.

Temporal status is a navigation aid. It does not independently establish that the underlying event occurred.

## Editorial ranking

Ranking intentionally separates four concepts:

- **importance**: inherent military/political significance of the candidate topic;
- **novelty**: degree of change against the recent baseline;
- **pulse**: current information-space intensity;
- **evidence mix**: structural strength/diversity of source types.

Importance and novelty dominate ranking. Pulse can surface an emerging signal but cannot make routine repetition the top story merely through volume. Evidence mix breaks ties and helps prioritize candidates with better verification structure.

The exact first-pass coefficients are implementation heuristics and should be tuned against observed reports, not treated as epistemic probabilities.

## Daily digest contract

The automatic daily digest now has two layers:

1. a compact `Контекст для редакционного синтеза` section near the top;
2. the existing complete attributable source ledger below it.

The context includes:

- relevance/off-topic counts;
- candidate event count;
- top event candidates by editorial rank;
- importance and novelty;
- evidence mix;
- Telegram pulse;
- seven-day delta;
- representative source excerpts from diverse source families;
- a pulse watchlist for lower-ranked but rapidly discussed candidates.

`public_redacted_v1` records are counted but never contribute content.

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
- cross-language publications about one event can cluster;
- one channel cannot manufacture high Telegram pulse through repeated posts;
- multi-channel, cross-perspective Telegram activity can surface as high pulse;
- OSINT improves evidence mix independently of pulse;
- historical matching distinguishes new from escalating/continuing patterns;
- redacted content never enters pre-synthesis excerpts;
- the complete source ledger remains present after context insertion.

Future quality work should add corpus-based golden tests for cluster purity, missed-event rate, source concentration, novelty ranking and summary usefulness on real historical days.
