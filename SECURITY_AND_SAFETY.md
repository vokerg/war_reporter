# Security and safety

The public project must not increase operational risk.

## Prohibited publication

- Exact current positions of active military units.
- Coordinates derived from non-public material that could facilitate targeting.
- Personal addresses or identifying data of vulnerable individuals.
- Precise locations of sensitive infrastructure when disclosure creates a material risk.
- Real-time movement tracks of operational assets.

## Required controls

Every geospatial feature must include:

- `precision_m`;
- `publication_delay_hours`;
- `sensitivity`;
- `valid_from` and `assessed_at`;
- linked claim and evidence IDs.

Sensitive features must be delayed, coarsened, generalized, withheld, or rejected. Reported presence must not be represented as territorial control. Approximate prose must not be converted into false coordinate precision.

## Agent behavior

When safety classification is ambiguous, stop publication and request review. A validator may reject data but must not silently weaken or relocate a sensitive feature.
