# Structured-data contracts

Each canonical record type has one Draft 2020-12 JSON Schema. Files may be JSON objects, arrays of objects, NDJSON, or—under `maps/layers/`—GeoJSON Features or FeatureCollections.

## Record mapping

| Path | Schema | Primary ID |
|---|---|---|
| `catalogs/sources/` | `source-profile.schema.json` | `source_entity_id` |
| `data/source-items/` | `source-item.schema.json` | `source_item_id` |
| `data/artifacts/` | `artifact.schema.json` | `artifact_id` |
| `data/observations/` | `observation.schema.json` | `observation_id` |
| `data/claims/` | `claim.schema.json` | `claim_id` |
| `data/events/` | `event.schema.json` | `event_id` |
| `data/reactions/` | `reaction.schema.json` | `reaction_id` |
| `data/assessments/` | `assessment.schema.json` | `assessment_id` |
| `data/corrections/` | `correction.schema.json` | `correction_id` |
| `data/reports/` | `report.schema.json` | `report_id` |
| `maps/layers/` | `map-feature.schema.json` | `id` |
| `maps/snapshots/` | `map-snapshot.schema.json` | `snapshot_id` |
| `tasks/` | `task-manifest.schema.json` | `task_id` |

Schema validity is necessary but insufficient. `scripts/validate_data.py` also checks core references, duplicate IDs, and time ordering.
