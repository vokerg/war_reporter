# Domain model

## Core records

- **Source profile:** person, organization, outlet, account, channel, official body, or project; reliability assessments vary by topic and period.
- **Source item:** one concrete publication and its retrieval/access metadata.
- **Artifact manifest:** hash, media type, size, storage pointer, rights note, and access classification for preserved evidence.
- **Observation:** one attributable atomic statement or visual observation.
- **Claim:** a normalized testable proposition linked to evidence relations.
- **Event:** a grouping of related claims about an occurrence or process.
- **Reaction:** an attributable response to a source item or claim.
- **Assessment:** a time-bounded editorial conclusion from a frozen claim set.
- **Correction:** a visible change record with propagation requirements.
- **Report manifest:** content path, period, language, frozen claim-set hash, and translation lineage.
- **Map feature:** provenance-linked GeoJSON with uncertainty and publication controls.
- **Map snapshot:** an immutable manifest of map layer files and claim-set hash.
- **Task manifest:** canonical scope, exclusions, paths, lease, and idempotency contract.

## Identifier conventions

Stable lowercase prefixes with opaque suffixes:

`src_`, `item_`, `art_`, `obs_`, `clm_`, `evt_`, `react_`, `asm_`, `corr_`, `rpt_`, `geo_`, `map_`, `task_`.

Identifiers are immutable and must not encode conclusions that may change.

## Lifecycle

Record lifecycle is independent of analytical outcome. Supersession retains the old record and points to the replacement. Released facts are not rewritten in place.
