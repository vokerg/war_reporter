# Methodology

## Evidence chain

`source entity → source item → artifact → observation → claim → event → assessment → report/map`

A factual publication statement must resolve to claim IDs. Each claim must resolve to attributable observations, and each observation must resolve to a source item and, where applicable, an immutable artifact manifest.

## Three separate axes

Do not collapse these concepts:

- **Record status:** `draft`, `in_review`, `approved`, `rejected`, `superseded`, or `withdrawn`.
- **Assessment outcome:** `confirmed`, `probable`, `plausible`, `unverified`, `contested`, `misleading`, or `refuted`.
- **Assessment confidence:** `high`, `medium`, or `low`, meaning confidence in the assigned outcome—not confidence that the underlying proposition is true.

Example: a claim may be `approved`, assessed as `contested`, with `high` confidence that substantial conflict exists.

## Independence and lineage

Evidence count is meaningless until upstream lineage is resolved. Publications are not independent when they share a post, document, image, briefing, owner-controlled network, anonymous source, or circular citation. Store upstream item IDs and distinguish original evidence from repetition.

## Source profiles

Assess sources by topic and time period. Separate identity, access, historical accuracy, methodology transparency, correction behavior, independence, affiliation, incentives, and recurring framing. Bias metadata is contextual information, not an automatic truth-value judgment. Every reputation assessment requires documented rationale and resolved evidence.

## Observations and claims

An observation records what a source communicated. A claim is a normalized testable proposition. Extraction must not upgrade source language such as “reportedly,” “may,” or “appears” into certainty. Preserve qualifiers, speaker attribution, event-time uncertainty, and location uncertainty.

## Quotations and rights

Store only short excerpts necessary for verification, with original language, URL, publication time, retrieval time, and page/paragraph/timecode locator. Store translations separately. Do not bulk-copy articles, transcripts, image sets, or proprietary maps. Artifact manifests must record access classification and rights notes.

## Temporal semantics

Use RFC 3339 UTC timestamps where time is known. Use explicit precision when publication or event time is uncertain. Never substitute retrieval time for publication time or assessment time.

## Coverage claims

A completed source scan means only that the assigned source list and time window were checked using the documented access method. It does not mean the open internet was exhaustively searched. Reports must disclose material coverage gaps, inaccessible sources, and platform/API failures.

## Corrections

Released records are append-only in meaning. Supersede or correct them; do not silently mutate history. Corrections must propagate to dependent assessments, reports, and map snapshots.
