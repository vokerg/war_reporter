# War Reporter

War Reporter is a small source-collection and daily-digest pipeline for public reporting about Russia's war against Ukraine.

```text
config/sources.json
        ↓
parallel Telegram / X / RSS / web collection
        ↓
publication embargo + public projection
        ↓
data/raw/YYYY/MM/DD/items.ndjson
        ↓
automatic source digest + static source/status reader
```

The generated output is a **source digest**, not a verified intelligence assessment. It reports what configured sources published, with attribution and coverage metadata. Repetition across outlets is not independent corroboration.

## Source counts

`config/sources.json` currently contains **146 registry entries**. Three configured X recent-search queries become virtual execution sources (`x-discovery-1..3`), so a full run can select **149 source adapters**. Neither number means that all sources are currently reachable or producing material. The status page reports configured, attempted, successful, skipped, failed and withheld counts separately.

## Public-repository boundary

This repository is public. Collectors may temporarily hold fuller source responses in memory, but only a bounded public projection is written to Git:

- source identity, canonical URL and timestamps;
- a configurable text excerpt (1,200 characters by default);
- a limited list of public media links;
- tags and handling metadata;
- minimal platform identifiers and, for ordinary excerpt records, a SHA-256 content fingerprint.

Captured HTML and full platform payloads are **not** persisted. Records tagged `operational-position` or `precise-location` use the stricter `public_redacted_v1` projection: title, text, HTML, media, content lengths and content fingerprint are omitted. This avoids turning the public archive into a confirmation oracle for guessed sensitive content.

The path name `data/raw/` is retained for compatibility; its records are public source projections, not a private full-text archive. A private durable capture backend is outside this PR.

## Implemented

- one registry instead of task/source shards;
- isolated per-source failures and meaningful process exit codes;
- platform-specific cadence;
- paginated Telegram history, X account timelines and X recent search;
- canonical X deduplication across discovery and watched accounts;
- RSS linked-article retrieval with feed-summary fallback;
- bounded same-host article discovery for web index pages;
- publication-time extraction from metadata, JSON-LD and `<time>` elements;
- `Europe/Kyiv` daily boundaries;
- 24/72-hour storage embargoes for configured operational source groups/tags;
- permanent content suppression for `operational-position` and `precise-location` records;
- atomic fail-closed state/archive/error writes;
- searchable static source cards and delayed map-publication cards;
- sanitized report HTML, hash-based Content Security Policy and no-referrer outbound links;
- explicit `ok`, `idle`, `partial`, `blocked` and `failed` states;
- versioned public collection status with platform/group aggregates and staleness.

The map section displays delayed map publications from sources. It is not a territorial-control map and does not derive geometry.

## Layout

```text
AGENTS.md                         agent operating contract
SAFETY.md                         publication policy
METHODOLOGY.md                    evidence semantics
config/sources.json               configured source registry
config/settings.json              cadence, timezone and publication policy
data/raw/YYYY/MM/DD/items.ndjson  public excerpt/redacted records
data/errors/YYYY/MM/DD/errors.ndjson source-specific safe error categories
data/state.json                   latest run, clean-run time and source health
reports/daily/YYYY-MM-DD.md       automatic source digest
schemas/raw-item.schema.json      public archive contract
schemas/public-status.schema.json public status contract
scripts/collect.py                collector facade and CLI
scripts/collector_common.py       URL safety, extraction, base projection
scripts/public_archive.py         final fail-closed archive hardening
scripts/collector_adapters.py     Telegram, X, RSS and web adapters
scripts/collector_runtime.py      cadence, embargo, state and persistence
scripts/continuous_loop.py        one-shot/service runner
scripts/build_report.py           source digest renderer
scripts/build_site.py             static source/status reader
scripts/html_safety.py            rendered-report allowlist sanitizer
scripts/public_status.py          safe current-state projection
scripts/validate.py               structural and safety validation
tests/                            regression and repository contract tests
```

## Run once

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m scripts.validate
python -m scripts.continuous_loop --once
cat data/state.json
```

`python -m scripts.continuous_loop --once` returns `0` only when collection and rendering complete cleanly. It returns `1` for any blocked, failed, partial or rendering-failed iteration. The precise collection state remains in `data/state.json`; `last_successful_run_at` is preserved when a later run degrades.

The lower-level `python -m scripts.collect` command returns:

- `0`: complete or cadence-idle;
- `1`: blocked or failed;
- `2`: partial coverage.

Successful sources are retained during a partial run, but the run remains visibly incomplete.

## Targeted source smoke

```bash
python -m scripts.collect \
  --force \
  --lookback-hours 168 \
  --sources ua-general-staff-tg,bellingcat-rss,ua-president-web
```

PR CI runs the same bounded Telegram/RSS/web adapters and requires each to return `status=ok` with at least one fetched item. The separate `Source smoke test` workflow supports manual reruns and alternate source IDs without committing its archive. Its optional X job receives `X_BEARER_TOKEN` only when explicitly enabled and checks both a watched account and recent search. Without inspected X smoke evidence, X is configured but unproven.

## Continuous service

```bash
mkdir -p data reports site
cp .env.example .env
# Add X_BEARER_TOKEN when X coverage is required.
export WAR_REPORTER_UID="$(id -u)"
export WAR_REPORTER_GID="$(id -g)"
docker compose up -d --build
```

The image excludes `.env`, Git metadata and generated/runtime data from the build context. The collector runs as a non-root user in a read-only container with no Linux capabilities; only `data/`, `reports/`, `site/` and `/tmp` are writable. The bind-mount directories must be writable by `WAR_REPORTER_UID:WAR_REPORTER_GID`.

Scheduled GitHub collection builds in a read-only job, uploads only `data/` and `reports/`, then uses a separate minimal write job to persist the artifact. Pages build and deployment credentials are separated the same way.

One source failure never terminates service mode. Scheduled collection persists successful and partial public projections, then leaves incomplete runs red.

## Read the source cards and status

```bash
python -m scripts.build_site
python -m http.server --directory site 8000
```

Open:

- `/index.html` for daily digests;
- `/raw/index.html` for source cards;
- `/maps/index.html` for delayed map-source publications;
- `/status/index.html` for reader-facing health;
- `/status.json` for `war-reporter-public-status-v1`.

The public status artifact is deliberately **current-state-only**. It does not retain availability history yet. It omits raw errors, configuration strings and credential names, and distinguishes registry entries from virtual X query sources. Undated material subject to an embargo is shown as withheld rather than failed.

The site renders excerpts and links; it does not embed third-party media. Undated material subject to an embargo is withheld because no deterministic publication-time boundary exists.

## Validation

```bash
python -m compileall -q scripts tests
python -m scripts.validate
python -m unittest discover -s tests -v
python -m scripts.build_report 2026-08-05
python -m scripts.build_site
```

The validator rejects absolute/traversing repository paths, credentialed source URLs, source ID/platform mismatches, unsafe persisted error records and public archive rows that do not match `public_excerpt_v1` or `public_redacted_v1`.

Merge readiness additionally requires a reviewed current-head GitHub-hosted run, a successful representative network smoke artifact, plus X smoke evidence when X coverage is claimed.
