# Methodology

## Evidence chain

`source entity → source item → observation → claim → event → assessment → report/map`

A report must never cite an untracked statement directly. Every factual passage must resolve to one or more claim IDs, and each claim must resolve to attributable observations.

## Confidence labels

- `confirmed` — multiple genuinely independent channels or strong direct evidence.
- `probable` — persuasive evidence with a material unresolved gap.
- `plausible` — possible and partially supported.
- `unverified` — reported without adequate independent confirmation.
- `contested` — substantial conflicting evidence exists.
- `misleading` — factual core may exist, but framing, scale, or implication is distorted.
- `false` — contradicted by strong evidence.
- `obsolete` — superseded by a later assessment.

Internal numeric scores may assist ranking, but publication must show a label and written rationale.

## Independence

Multiple publications are not independent when they share one upstream post, document, image, briefing, ownership network, or anonymous source. Provenance lineage must be recorded before evidence count is used in confidence assessment.

## Source assessment

Source reliability is multidimensional and topic-specific. Evaluate identity, access, historical accuracy, methodology transparency, correction behavior, affiliation, incentives, and recurring framing. Never assign one permanent global trust score.

## Quotations

Store short, necessary excerpts in the original language with URL, author, publication time, and retrieval time. Store translations separately. Do not replace the original quotation with a translation.

## Corrections

Never silently rewrite an assessment. Supersede it, retain prior state in Git history, explain the reason, and link the correction to affected claims and reports.
