# Task lifecycle

## Canonical contract

The file in `tasks/` is authoritative. The GitHub issue is the human coordination surface and links the manifest. Issue-form Markdown is not a machine-stable task protocol.

A manifest defines task type, parent, UTC window, source/region/topic/content scope, exclusions, allowed output paths, definition of done, idempotency key, state, and optional lease.

## States

`planned → ready → leased → collecting → pr_open → validating → review → merged`

Terminal or recovery states: `blocked`, `lease_expired`, `rejected`, `cancelled`, `duplicate`.

Only the dispatcher changes lease ownership. State transitions must be monotonic except an explicitly recorded recovery from `blocked` or `lease_expired`.

## Parallelization

Shard deterministically by source group, non-overlapping time window, region/topic partition, and content type. An idempotency key represents the normalized scope, not a randomly generated issue identifier.

Before lease creation, check open tasks, merged manifests, canonical URLs, platform IDs, hashes, and upstream lineage. Workers must not broaden scope to “everything important.”

## Pull-request gate

A PR links its issue and manifest, lists generated/modified IDs, stays inside allowed paths, documents coverage gaps, passes deterministic validation, and receives independent research/safety review as applicable. The merge controller verifies the expected head SHA and squash-merges.
