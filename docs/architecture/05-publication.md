# Publication model

## Outputs

- Daily brief: material changes, confidence changes, contested claims, notable reactions, and unresolved questions.
- Weekly assessment: operational trends, territorial change, strike campaign, force generation, logistics, external support, information environment, competing interpretations, and indicators to watch.
- Monthly snapshot: durable processes, discarded noise, changed source track records, analytical misses, and map change over the period.

## Languages

Structured data is language-neutral where possible. English is the primary editorial narrative; Russian is a derived translation. Original quotations remain in their source language and translations are stored alongside them.

A translated report must reference the source report commit and frozen claim-set hash. Translation fails when the source changes during work.

## Site routes

- `/latest`
- `/daily`
- `/weekly`
- `/snapshots`
- `/map`
- `/events/{id}`
- `/claims/{id}`
- `/sources/{id}`
- `/methodology`
- `/corrections`

Each claim page should expose current status, supporting and contradicting evidence, source lineage, reactions, map references, assessment history, corrections, and the responsible commit/PR.
