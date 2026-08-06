# War Reporter 2.0

War Reporter is a **raw-first OSINT collector** for the Russia–Ukraine war.

The previous task/claim/assessment/review control plane has been removed. The system now:

1. polls one registry of **146 sources**;
2. runs paginated Telegram collection, configured X timelines, X recent-search discovery, RSS and public-web capture in parallel;
3. appends captured text, source HTML, public media URLs and raw platform payloads to daily NDJSON;
4. builds one transparent daily report and a readable static source browser directly from that archive.

## Repository layout

```text
config/sources.json                 one source registry
config/settings.json                runtime and discovery settings
data/raw/YYYY/MM/DD/items.ndjson    append-only source archive
data/errors/YYYY/MM/DD/errors.ndjson isolated source failures
data/state.json                     last collection run
reports/daily/YYYY-MM-DD.md         daily report
site/                               generated readable reports and raw cards
scripts/collect.py                  parallel collection and discovery
scripts/continuous_loop.py          never-ending service loop
scripts/build_report.py             one raw-to-report pass
scripts/build_site.py               static reader
```

There are no task manifests, queue proposals, review receipts, claims, assessments, shards, arbitrary task caps or human gates.

## Run once

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m scripts.collect --lookback-hours 72
python -m scripts.build_report 2026-08-05
python -m scripts.build_site
```

## Run continuously

```bash
cp .env.example .env
# Add X_BEARER_TOKEN for X timelines and recent search.
docker compose up -d --build
```

The service runs until SIGINT or SIGTERM. An empty scan, blocked page, missing X token, malformed feed or individual source failure never ends the loop; errors go to `data/errors/` while unrelated collection continues.

## Coverage model

`config/sources.json` contains Ukrainian and Russian official sources, regional authorities, Ukrainian media/bloggers, Russian milbloggers, OSINT organisations, map projects, military analysts and international news/defence institutions.

Telegram follows public-history pagination until the configured lookback boundary or page ceiling. X account timelines and recent-search queries follow API pagination. A canonical content ID deduplicates the same X post when it appears both through a watched account and discovery search.

## Source object

```json
{
  "id": "deepstate-tg",
  "name": "DeepState",
  "platform": "telegram",
  "url": "https://t.me/DeepStateUA",
  "group": "osint",
  "perspective": "ukrainian",
  "trust": "high",
  "priority": 100,
  "tags": ["frontline", "map"],
  "enabled": true
}
```

`trust` is a handling hint, not a truth verdict:

- `primary`: authoritative for the source's own statements and releases;
- `high`: established analytical, OSINT or newsroom source;
- `medium`: useful reporting or commentary that normally needs comparison;
- `low`: partisan milblogger, rumour channel or propaganda source, retained for early indicators, imagery and narrative analysis.

## Raw item

```json
{
  "id": "stable-content-id",
  "source": "source-id",
  "platform": "telegram",
  "url": "canonical item URL",
  "published_at": "2026-08-05T03:16:00Z",
  "collected_at": "2026-08-06T11:30:00Z",
  "title": "",
  "text": "complete captured text",
  "html": "captured source HTML",
  "media": ["https://..."],
  "author": "channel or account",
  "group": "official-ua",
  "perspective": "ukrainian",
  "trust": "primary",
  "tags": ["civilian-harm", "strike-aftermath"],
  "raw": {"platform_specific": "payload"}
}
```

X collection uses the official API v2 and requires `X_BEARER_TOKEN`. Without it, X errors are isolated while Telegram/RSS/web collection continues.

## Validate

```bash
python -m scripts.validate
python -m unittest discover -s tests -v
```
