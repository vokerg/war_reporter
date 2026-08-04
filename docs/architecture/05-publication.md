# Publication model

## Outputs

- **Daily brief:** material changes, confidence changes, contested claims, notable reactions, unresolved questions, and coverage gaps.
- **Weekly assessment:** operational trends, territorial change, strike campaign, force generation, logistics, external support, information environment, competing interpretations, and indicators.
- **Snapshot:** durable processes, discarded noise, analytical misses, source-track-record changes, and map change over a requested period.

## Frozen inputs

Each report manifest records its period, `as_of`, claim IDs, assessment IDs, and claim-set hash. Editors do not browse while composing. New evidence requires a new claim-set version and rerun.

## Languages

Structured records use canonical-language fields plus translations. English is the primary editorial report for the initial implementation; Russian is derived. Original quotations remain in their source language. A translation records the source report ID and exact source commit and fails when either changes.

## Public routes

Planned routes include `/latest`, `/daily`, `/weekly`, `/snapshots`, `/map`, `/events/{id}`, `/claims/{id}`, `/sources/{id}`, `/methodology`, and `/corrections`.

Claim pages expose outcome, confidence, lifecycle, supporting/disputing evidence, lineage, reactions, map references, assessment history, corrections, and responsible commits.
