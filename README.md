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
automatic source digest + static source reader
```

The generated output is a **source digest**, not a verified intelligence assessment. It reports what configured sources published, with attribution and coverage metadata. Repetition across outlets is not independent corroboration.

## Public-repository boundary

This repository is public. Collectors may temporarily hold fuller source responses in memory, but only a bounded public projection is written to Git:

- source identity, canonical URL and timestamps;
- a configurable text excerpt (1,200 characters by default);
- a limited list of public media links;
- tags and handling metadata;
- a SHA-256 fingerprint and minimal platform identifiers.

Captured HTML and full platform payloads are **not** persisted. The path name `data/raw/` is retained for compatibility; its records are public source projections, not a private full-text archive. A private durable capture backend is outside this PR.

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
- permanent excerpt suppression for `operational-position` and `precise-location` records;
- searchable static source cards and delayed map-publication cards;
- explicit `ok`, `idle`, `partial`, `blocked` and `failed` states.

The map section displays delayed map publications from sources. It is not a territorial-control map and does not derive geometry.

## Layout

```text
AGENTS.md                         agent operating contract
SAFETY.md                         publication policy
METHODOLOGY.md                    evidence semantics
config/sources.json               configured source registry
config/settings.json              cadence, timezone and publication policy
data/raw/YYYY/MM/DD/items.ndjson  public excerpt records
data/errors/YYYY/MM/DD/errors.ndjson source-specific failures
data/state.json                   latest run and per-source health
reports/daily/YYYY-MM-DD.md       automatic source digest
scripts/collect.py                collector facade and CLI
scripts/collector_common.py       URL safety, extraction, public projection
scripts/collector_adapters.py     Telegram, X, RSS and web adapters
scripts/collector_runtime.py      cadence, embargo, state and persistence
scripts/continuous_loop.py        one-shot/service runner
scripts/build_report.py           source digest renderer
scripts/build_site.py             static source reader
scripts/validate.py               structural validation
tests/test_pipeline.py            regression suite
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

`python -m scripts.continuous_loop --once` returns `0` only when collection and rendering complete cleanly. It returns `1` for any blocked, failed, partial or rendering-failed iteration. The precise collection state remains in `data/state.json`.

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

The `Source smoke test` workflow runs the same bounded adapters without committing its archive. X timelines and discovery require `X_BEARER_TOKEN`; absence of the token is reported as degraded coverage rather than one error per X source.

## Continuous service

```bash
cp .env.example .env
# Add X_BEARER_TOKEN when X coverage is required.
docker compose up -d --build
```

One source failure never terminates service mode. Scheduled GitHub collection persists successful and partial public projections, then leaves incomplete runs red.

## Read the source cards

```bash
python -m scripts.build_site
python -m http.server --directory site 8000
```

The site renders excerpts and links; it does not embed third-party media. Undated material subject to an embargo is withheld because no deterministic publication-time boundary exists.

## Validation

```bash
python -m compileall -q scripts tests
python -m scripts.validate
python -m unittest discover -s tests -v
python -m scripts.build_report 2026-08-05
python -m scripts.build_site
```

Merge readiness additionally requires a reviewed network smoke run on representative Telegram, RSS and web sources, plus X when X coverage is claimed.
