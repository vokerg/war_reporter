# Canonical source watchlist architecture

## Problem

Daily discovery tasks previously carried empty `scope.source_ids` and `scope.source_groups`.
Workers therefore improvised search queries, and a successful empty scan could mean only that a
small, worker-selected subset was checked. The dated `catalogs/sources/YYYY/MM/DD/*.json` files
were then mistaken for a complete source registry even though they are discovery outputs.

## Decision

`config/source-watchlist.json` is the canonical assignment control for recurring discovery.
It is separate from dated source-profile catalogs:

- the watchlist says **what must be checked, where, how often, and under which handling rule**;
- dated source catalogs preserve source profiles discovered or reviewed during a bounded run;
- source items and raw manifests preserve the evidence and the per-run scan outcome.

The first baseline contains **168 active sources**: **69 core**
and **99 extended**.

## Assignment semantics

1. `scripts/reconcile_repository.py` may create discovery manifests with an initially empty scope.
2. `scripts/assign_source_watchlist.py --write` materializes the exact active source list for each shard.
3. The reconciliation workflow runs the assignment step before committing task manifests.
4. `scripts/assign_source_watchlist.py --check` blocks drift between task scopes and the watchlist.
5. The rule applies to discovery windows beginning at or after `2026-08-06T00:00:00Z`.
6. A task must use `source_groups: [<shard>]` and the ordered `source_ids` produced from the watchlist.

The ordering in the JSON file is intentional. Core sources appear before or alongside extended
sources and may be used by workers as the scan order when time or access failures require triage.
All active sources in the configured priority tiers are still assigned.

## Per-source outcome requirement

A completed raw discovery manifest must record one outcome for every assigned source, including
sources with no retained item:

- `item_retained`
- `checked_no_in_window_item`
- `candidate_time_uncertain`
- `inaccessible`
- `subscription_index_only`
- `excluded_out_of_window`
- `excluded_overlap`
- `not_checked` with a material coverage-gap explanation

A zero-item task is acceptable only when all assigned sources have an explicit outcome.

## Handling classes

| Class | Operational meaning |
|---|---|
| `authoritative_for_own_statements` | Establishes what the institution or office publicly stated. It does not independently verify the underlying event. |
| `strong_independent_reporting` | Useful for event discovery and corroboration; upstream lineage and named sourcing still matter. |
| `specialist_analysis` | Analytical interpretation. Preserve assumptions, methodology, publication date, and author attribution. |
| `osint_artifact_verification` | Prefer the underlying visual artifact, geolocation method, timestamp, and revision history over a map label alone. |
| `partisan_signal_only` | Use for attributed claims, narrative shifts, warnings, and leads. Never treat repetition as corroboration. |
| `correction_factcheck` | Use to locate corrections, debunks, retractions, and disputed narratives; inspect the evidence cited by the fact-checker. |
| `primary_local_reporting` | Local first-hand or regional reporting requiring identity and proximity checks. |
| `discovery_lead_only` | Lead generation only until another evidence path is established. |

These classes are not global truth scores. Formal source assessments remain topic- and
time-bounded under `schemas/source-profile.schema.json`.

## Collection model

Each source contains one or more collection endpoints:

- `website` or `rss` for canonical publications;
- `telegram` for public preview channels;
- `youtube` or `podcast` for briefings and interviews;
- `api` for structured public datasets;
- `search` only as a fallback when a stable native archive is unavailable.

`access` distinguishes public pages, public previews, subscriptions, and index-only coverage.
The system must not bypass paywalls or access controls. For subscription sources, headlines and
metadata can be recorded, but unsupported article claims cannot be imported.

## Coverage floors

| Shard | Active | Core | Minimum active | Minimum core |
|---|---:|---:|---:|---:|
| `ua-official` | 22 | 5 | 15 | 5 |
| `ru-official` | 12 | 3 | 10 | 3 |
| `ua-analysis-media` | 16 | 5 | 12 | 5 |
| `ru-milbloggers` | 15 | 4 | 12 | 4 |
| `international-media` | 20 | 8 | 15 | 8 |
| `military-analysts` | 29 | 16 | 20 | 12 |
| `strikes-infrastructure` | 37 | 11 | 25 | 8 |
| `visual-osint-maps` | 17 | 8 | 12 | 8 |
| `diplomacy-support-sanctions` | 33 | 20 | 20 | 10 |
| `reactions-corrections` | 11 | 6 | 8 | 5 |

## Anchor sources

The watchlist protects a small set of high-value anchors against accidental removal. The initial
anchor set includes Michael Kofman, Rob Lee, Dara Massicot, The Russia Contingency, Conflict
Intelligence Team, DeepState, GeoConfirmed, Bellingcat, Eyes on Russia, Black Bird Group,
Frontelligence Insight, Oryx, ISW, and the Deep Cuts Commission.

## Research and identity evidence

The baseline uses native organization, author-profile, project, or official-government pages as
identity evidence whenever available. Examples:

- Carnegie identifies Michael Kofman as a senior fellow focused on the Russian military,
  Ukrainian armed forces, and Eurasian security.
- FPRI identifies Rob Lee as a senior fellow and open-source researcher focused on Ukrainian
  forces and Russian military strategy.
- Carnegie identifies Dara Massicot as a senior fellow focused on Russian and Eurasian defense.
- War on the Rocks publishes *The Russia Contingency with Michael Kofman* as a recurring
  Russia–Ukraine military-analysis feed.
- CIT publishes its own notes archive and public Russian- and English-language Telegram previews.
- GeoConfirmed, CIR Eyes on Russia, Bellingcat, Oryx, DeepState, and the other OSINT projects are
  collected through their native project pages.

Identity evidence establishes source ownership and collection endpoints; it does not establish
historical accuracy. Formal reliability assessments require separate, evidence-linked review.

## Maintenance

- Add or retire sources only through a reviewed pull request.
- Preserve source IDs across renames, affiliation changes, and channel migrations.
- Change `active` rather than deleting historically used source IDs.
- Update identity evidence and `reviewed_at` when an endpoint or affiliation changes.
- Raise coverage floors only after the expanded list has passed at least one complete daily cycle.
- Review core sources monthly and the full extended list quarterly.
