# Agent contract

The repository has one operational objective: continuously enlarge the raw source archive and keep the daily report readable.

When asked to `копай` or run a continuous loop:

1. run `python -m scripts.continuous_loop --once` for one bounded execution, or run it without `--once` as a service;
2. do not create task manifests, work queues, claims, assessments, review receipts or source shards;
3. add sources directly to `config/sources.json`;
4. preserve full captured source text, HTML, media URLs, canonical URLs and raw platform payloads;
5. do not let one inaccessible, paywalled, rate-limited or malformed source stop unrelated collection;
6. never invent source content, timestamps, identities or URLs;
7. do not publish precise current tactical positions or other targeting-enabling details in generated summaries. Preserve the source in raw storage with an appropriate handling tag when collection is lawful, but coarsen report prose.
