# Domain model

## Entities

### Source entity

A person, organization, outlet, account, channel, or official body. Reliability and bias are modeled by topic and time period.

### Source item

A concrete publication: post, article, video, report, briefing, image, map, or document.

### Observation

An attributable atomic statement extracted from one source item. It records what the source said without deciding whether it is true.

### Claim

A normalized, testable proposition. Evidence relations may support, partially support, dispute, contextualize, or correct it.

### Event

A group of related claims concerning one occurrence or process.

### Assessment

A time-bounded editorial conclusion based on a frozen set of reviewed claims.

### Reaction

A source entity's response to a source item or claim. Allowed relations include `supports`, `partially_supports`, `disputes`, `partially_disputes`, `contextualizes`, `corrects`, `questions_methodology`, `questions_evidence`, and `quotes_without_endorsement`.

### Map feature

A GeoJSON feature derived from approved claims, with temporal validity, uncertainty, provenance, precision, and sensitivity metadata.

## Identifier convention

Use stable lowercase prefixes and opaque sortable suffixes:

- `src_...`
- `item_...`
- `obs_...`
- `clm_...`
- `evt_...`
- `asm_...`
- `react_...`
- `geo_...`

Identifiers are immutable and must not encode a conclusion that may later change.
