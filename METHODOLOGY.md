# Methodology

## Record model

A record represents a source publication, not a fact. The public Git record contains provenance and a bounded excerpt. A SHA-256 fingerprint is calculated from the fuller in-memory capture so changes can be detected without storing the complete third-party response.

The `data/raw/` name is retained for compatibility; the content is a public projection with `archive_policy=public_excerpt_v1`.

## Trust

`trust` is a handling hint:

- `primary`: authoritative for the source's own statement;
- `high`: established newsroom, analyst or OSINT practice;
- `medium`: useful but normally needs comparison;
- `low`: partisan, rumour-prone or propaganda source;
- `unknown`: discovery output not mapped to a known source.

No trust value is a truth verdict.

## Independence

Repeated claims are not independent corroboration when they share an upstream source. Canonical deduplication prevents duplicate X storage, but analytical work must still inspect source lineage.

## Capture and publication

- RSS entries attempt same-run linked-article extraction and fall back to supplied feed text.
- Web index pages use bounded same-host article discovery; snapshot fallback is explicit.
- Publication time is read from feed timestamps, metadata, JSON-LD or `<time>` elements.
- Operational records enter the public archive only after configured 24/72-hour embargoes.
- Undated embargoed snapshots are counted as `items_withheld_undated` and are not silently released.
- Public excerpts are capped by `public_excerpt_chars`; stored HTML is empty and raw payloads are reduced to minimal identifiers plus a content fingerprint.

## Daily boundary

Digests use the calendar day in `report_timezone` (`Europe/Kyiv`). Raw partitions are UTC; report generation reads the adjacent UTC files needed for the local day.

## Automatic output

`reports/daily/` is a transparent automatic source digest. It reports coverage and attributed excerpts; it does not resolve contradictions, calculate territorial control or assign claim confidence.

The map section lists delayed map publications from sources. It is not a verified map layer.

## Coverage

`data/state.json` is the runtime coverage record. `ok` and `idle` are clean. `partial`, `blocked` and `failed` remain visible. Per-source state distinguishes collection errors, cadence skips, configuration skips, recent embargo withholding and undated policy withholding.
