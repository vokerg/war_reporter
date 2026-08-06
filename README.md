# War Reporter 2.0

War Reporter is a raw-first OSINT collector for the Russia–Ukraine war.

The old task/claim/assessment/review control plane is gone. The system now polls one registry of **130+ official, OSINT, analyst, newsroom, Ukrainian and Russian milblogger sources**, collects Telegram, X, RSS and public web material in parallel, appends complete captured text/HTML/media/raw payload to daily NDJSON, and builds one transparent report plus a readable raw-source site.

## Layout

```text
config/sources.json                 one source registry
data/raw/YYYY/MM/DD/items.ndjson    append-only source archive
data/errors/YYYY/MM/DD/errors.ndjson isolated failures
reports/daily/YYYY-MM-DD.md         daily report
site/raw/YYYY-MM-DD.html            readable full source cards
scripts/collect.py                  parallel Telegram/X/RSS/web collection
scripts/continuous_loop.py          never-ending service loop
```

There are no task manifests, queue proposals, review receipts, claims, assessments, source shards, arbitrary task caps or human gates.

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m scripts.collect --lookback-hours 72
python -m scripts.build_report 2026-08-05
python -m scripts.build_site
```

Continuous service:

```bash
cp .env.example .env
# Set X_BEARER_TOKEN for X API v2 timelines.
docker compose up -d --build
```

An empty scan, unavailable source, paywall, rate limit, malformed feed or missing X token never ends the loop. The source failure is appended to `data/errors/`; unrelated sources continue.

## Source object

```json
{"id":"deepstate-tg","name":"DeepState","platform":"telegram","url":"https://t.me/DeepStateUA","group":"osint","perspective":"ukrainian","trust":"high","priority":100,"enabled":true}
```

`primary` means authoritative only for that source's own statement. `high`, `medium` and `low` are handling hints, not automatic truth verdicts. Low-trust partisan channels are intentionally collected for early indicators, imagery and narrative analysis.

## Raw item

```json
{"id":"stable-id","source":"deepstate-tg","platform":"telegram","url":"canonical URL","published_at":"...","collected_at":"...","title":"","text":"complete captured text","html":"captured HTML","media":[],"author":"","language":"uk","group":"osint","perspective":"ukrainian","trust":"high","tags":[],"raw":{}}
```

X uses the official API v2 and `X_BEARER_TOKEN`. Telegram uses public channel web views and preserves visible full message text, public media URLs and canonical post URLs.

## Check

```bash
python -m scripts.validate
python -m unittest discover -s tests -v
```
