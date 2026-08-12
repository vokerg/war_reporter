# Summary intelligence layer

## Purpose

War Reporter collection is intentionally unchanged by this layer. The collector continues to persist attributable public source projections and `reports/daily/YYYY-MM-DD.md` remains the complete source ledger.

The summary intelligence layer exists only to make editorial synthesis tractable. It turns the publication stream into conservative daily situation clusters before ChatGPT writes `reports/summary/YYYY-MM-DD.md`.

The target question is:

> What materially changed today compared with the recent information baseline, how well is that development supported, and where is there a meaningful early information pulse that still needs verification?

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
reports/daily/...               broad relevance recall
                               -> strict editorial relevance
                               -> multilingual normalization
                               -> event-centric topic classification
                               -> explicit body-text geography
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

The pre-synthesis context is embedded near the top of the existing daily digest. The complete source ledger remains below it. There are no summary shards, intermediate JSON files, embeddings database, second durable report tree or extra write-capable workflow.

## Relevance

Source membership must never determine topic relevance by itself.

A war-focused milblogger post about wildfires in France remains in the ledger but must not enter summary clustering merely because of its source group.

Relevance is deliberately two-stage:

1. a recall-oriented multilingual gate marks `relevant`, `peripheral`, `irrelevant` or `redacted`;
2. the production strict gate rechecks event semantics with word-boundary-aware patterns before a publication can enter a situation cluster.

The second gate exists because broad lexical recall is allowed to over-capture. It rejects known collision classes such as `удар` inside `государственный`, `порт` inside `транспорт`, legal `санкция/санкционированный` language mistaken for geopolitical sanctions, and memorial/obituary material containing historical battle vocabulary.

`public_redacted_v1` is content-neutral and never synthesized. False negatives are preferable to silently converting a high-volume source group into a topic label; the full ledger remains available for audit.

## Situation clusters

The unit of synthesis is a **daily situation cluster**, not a publication and not a fuzzy global claim graph.

An early prototype used lexical similarity. A real-day pass on 2026-08-05 exposed cluster drift: broad roundups could bridge unrelated places through single-linkage-style accumulation. That implementation was removed; there is now one production clustering path.

Production grouping prioritizes purity and explainability:

- event-centric editorial topic;
- explicit geographic signature found in the publication body text;
- a bounded semantic signature only where equipment/infrastructure/support class defines event identity;
- no source-name geography inference;
- no cross-source merging for operational items without explicit geography.

A strike and reporting about casualties/damage from that same strike remain in the same strike cluster when they share geography. Casualty-only updates remain under `Потери и гражданские последствия` so military losses are not mislabeled as necessarily civilian.

Target details such as a port mention do **not** split an otherwise identical generic strike cluster. Equipment hard-keys are retained for categories where equipment/target class is itself the distinguishing event dimension, such as energy, air-defence, naval and support streams.

Multi-location roundups keep their own signature and cannot bridge single-location clusters. This deliberately trades some recall for cluster purity.

## Evidence and Telegram pulse are separate axes

There is no single universal source weight.

### Evidence mix

Evidence mix asks what kinds of sources are represented around a cluster. OSINT, specialist analysis and established media have stronger structural weight; official sources remain authoritative for their own statements; low-trust milbloggers contribute much less.

Evidence mix is **not** a count of independent confirmations. Different outlets can share an upstream source.

### Telegram pulse

Telegram pulse asks how broad and intense discussion is across Telegram. It uses:

- unique source families/channels;
- capped mentions per channel;
- perspective diversity.

One channel cannot manufacture high pulse by posting repeatedly. Several channels from different perspectives can create a high early-warning signal, but pulse never becomes factual corroboration by itself.

## Routine alerts and weak evidence

Target-movement warnings and air-raid alerts remain useful sensor data but are poor executive-summary units when they have no material effects. Routine alert streams can remain visible in the ledger or pulse watchlist without competing directly against damage, casualties or multi-source material events.

Primary selection also keeps `frontline`, air-defence, naval and support clusters with thin evidence below the executive top list. A single low-evidence energy claim is similarly suppressed. These rules affect prioritization, not archival inclusion.

## Temporal delta

Current clusters are compared with structurally similar clusters from up to seven preceding report days.

The states are:

- `NEW`: no comparable recent cluster;
- `ESCALATING`: current information pulse is materially above the matched recent baseline;
- `CONTINUING`: a similar information pattern remains present;
- `DECLINING`: current information pulse is materially below the matched recent baseline.

These labels describe change in the **observed information signal**, not independently verified operational escalation or decline. They are navigation aids only.

Temporal matching uses precomputed canonical location/semantic anchors and token sets. It must not rerun full publication-level geographic regex extraction for every current×historical cluster pair; that creates quadratic repeated work on real daily corpora.

Future iterations may add `REVERSAL` and `DISPUTED` only when those states can be represented without pretending heuristics establish operational truth.

## Editorial ranking

Ranking separates four concepts:

- **importance**: inherent military/political significance;
- **novelty**: change against the recent information baseline;
- **pulse**: current information-space intensity;
- **evidence mix**: structural strength/diversity of source types.

`NEW` is not automatically top-ranked. Materiality, evidence and multi-channel pulse can outrank novelty alone. Routine alerts, broad roundups, weak unlocated items and thin high-risk claim classes are suppressed from primary selection. A per-topic diversity guard prevents one high-volume category from monopolizing top-N.

The coefficients are editorial heuristics, not probabilities, and should be tuned against multiple historical golden days rather than one corpus.

## Daily digest contract

The automatic daily digest has two layers:

1. compact `Контекст для редакционного синтеза` near the top;
2. the existing complete attributable source ledger below it.

The context exposes:

- relevance and strict-filter counts;
- situation-cluster count;
- ranked primary clusters;
- importance and novelty;
- evidence mix;
- Telegram pulse;
- seven-day information-signal delta;
- representative excerpts from diverse source families;
- a pulse watchlist for lower-ranked but rapidly discussed candidates.

Untrusted source names and excerpts are Markdown-escaped. Original links are shown only for valid `http`/`https` URLs without credentials or control characters.

## ChatGPT summary contract

ChatGPT should use deterministic context as the navigation layer, then inspect underlying ledger records needed to resolve attribution, disagreements, casualty updates and high-impact claims.

The final daily summary should be change-oriented:

1. **Картина дня** — compact overall assessment;
2. **Что изменилось** — ranked material changes vs recent baseline;
3. **Фронт** — changed, disputed or unusually high-pulse sectors only;
4. **Дальние удары** — changes in scale, geography and target pattern, not chronology;
5. **Telegram pulse** — early/high-velocity signals separated from verification;
6. **Установлено / вероятно / заявления сторон** — concise epistemic separation with attribution;
7. **На что смотреть дальше** — indicators that could confirm or weaken the emerging interpretation.

Deterministic scores must not be repeated as epistemic probabilities.

## Quality gates

Regression coverage includes:

- off-topic material from war-focused sources is excluded from context;
- cross-language publications about one development coalesce in the production path;
- strike reporting and casualty/damage reporting do not duplicate one event across primary slots;
- target/equipment details do not fragment generic strike events;
- one channel cannot manufacture high Telegram pulse;
- cross-perspective activity can surface as high pulse;
- OSINT evidence remains independent from Telegram pulse;
- temporal matching works for the full supported location set;
- redacted content never enters excerpts;
- untrusted Markdown/HTML and credentialed URLs cannot alter/leak through the context;
- routine alert fragments do not outrank material multi-source developments;
- Ukrainian geographic/casualty inflections are normalized;
- multi-location roundups cannot bridge local clusters;
- memorial/obituary material with historical strike language is rejected;
- legal sanction terminology is not interpreted as geopolitical sanctions;
- thin single-camp frontline/support claims stay out of primary;
- one topic cannot monopolize primary top-N;
- the complete source ledger remains present after context insertion.

Real historical days are part of the acceptance surface. A synthetic green suite is not sufficient if generated top clusters remain editorially incoherent.

Future quality work should add several historical golden days for cluster purity, missed-event rate, source concentration, ranking usefulness and runtime budgets.
