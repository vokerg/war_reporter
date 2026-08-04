# Agent routing and separation of duties

## Roles

- `source-researcher` — bounded source collection.
- `corroborator` — adversarial evidence review and lineage analysis.
- `geo-verifier` — uncertainty-aware GeoJSON production.
- `report-editor` — concise synthesis from an approved claim set.
- `release-validator` — deterministic publication gate.

Future roles may include dispatcher, open-web discovery researcher, extractor, source analyst, translator, and merge controller.

## Separation rules

- A collector cannot set a claim to `confirmed`.
- A report editor cannot add untracked evidence.
- A translator cannot change claim IDs, figures, dates, confidence labels, or links.
- A release validator cannot repair substantive research by inference.
- The author of a PR cannot be its approving reviewer or merge controller.

## Context minimization

Each issue must provide a narrow scope, time window, allowed output paths, exclusions, definition of done, and idempotency key. Agents should not load the entire repository or repeat another shard's work.
