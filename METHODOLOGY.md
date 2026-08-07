# Methodology

## Record model

A stored row represents a **source publication**, not a fact and not an analytical claim.

The path `data/raw/` is retained for compatibility, but it contains one of two public projections:

- `public_excerpt_v1`: provenance, bounded text/media, minimal platform identifiers and a SHA-256 fingerprint calculated from the fuller in-memory capture;
- `public_redacted_v1`: minimal provenance/platform identifiers only. Title, text, HTML, media, content lengths and content fingerprint are absent.

`public_redacted_v1` is used for records tagged `operational-position` or `precise-location`. Omitting the fingerprint and lengths prevents the public archive from acting as a confirmation oracle for guessed sensitive content.

A fingerprint supports duplicate/change detection for ordinary excerpt records. It does not authenticate the publisher, establish factual truth or prove that two reports are independent.

## Trust

`trust` is a handling hint:

- `primary`: authoritative for the source's own statement;
- `high`: established newsroom, analyst or OSINT practice;
- `medium`: useful but normally needs comparison;
- `low`: partisan, rumour-prone or propaganda source;
- `unknown`: discovery output not mapped to a known source.

No trust value is a truth verdict.

## Independence

Repeated claims are not independent corroboration when they share an upstream source. Canonical X deduplication prevents duplicate storage, but analytical work must still inspect source lineage. Registry/source counts are coverage metadata, not evidence counts.

## Capture and publication

- RSS entries attempt same-run linked-article extraction and fall back to supplied feed text.
- Web index pages use bounded same-host article discovery; snapshot fallback is explicit.
- Publication time is read from feed timestamps, metadata, JSON-LD or `<time>` elements.
- Operational records enter the public archive only after configured 24/72-hour embargoes.
- Undated embargoed snapshots are counted as `items_withheld_undated` and are not silently released.
- Public excerpts are capped by `public_excerpt_chars`; stored HTML is always empty.
- Full platform payloads and response HTML are discarded before persistence.
- Archive/state/error writes are atomic and fail closed when an existing NDJSON partition is malformed.

## Daily boundary

Digests use the calendar day in `report_timezone` (`Europe/Kyiv`). Raw partitions are UTC; report generation reads the adjacent UTC files needed for the local day.

## Automatic output

`reports/daily/` is a transparent automatic source digest. It reports coverage and attributed excerpts; it does not resolve contradictions, calculate territorial control or assign claim confidence.

The map section lists delayed map publications from sources. It is not a verified map layer. Any derived geometry is a separate historical product decision under issue #131.

## Runtime coverage

`data/state.json` records the latest execution state:

- `ok`: attempted work completed without known source/configuration degradation;
- `idle`: no request was due under cadence and no blocker was present;
- `partial`: at least one selected source succeeded, but source/configuration degradation remained;
- `blocked`: the selected work could not start because required configuration was missing;
- `failed`: attempted sources produced no successful result.

`last_run_at` is the completion time of the latest pass. `last_successful_run_at` advances only on `ok` or `idle` and survives later partial/failed runs. Per-source `last_success_at` is separate from the run-level clean timestamp.

Configured count is not working count. The current configuration has 146 registry entries and three virtual X recent-search sources. A full run can therefore select 149 execution sources, but public status reports configured, attempted, successful, skipped and errored values separately.

## Public status

`site/status.json` is the allowlist projection `war-reporter-public-status-v1`; `site/status/index.html` renders the same model for readers.

The status model:

- aggregates by platform/group without publishing raw error/configuration text;
- distinguishes cadence-idle, partial, blocked, failed, stale and embargo-only states;
- reports last run, last fully successful run, latest source success, archive day and digest day;
- separates registry entries from virtual X query sources;
- does not imply that successful retrieval validates a source's claims.

Version 1 is deliberately **current-state-only**. Availability/latency history is not retained or claimed until a separate retention and size policy is accepted.
