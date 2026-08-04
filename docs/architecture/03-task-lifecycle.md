# Task lifecycle

## Task contract

Every research issue should define:

- task type;
- parent campaign;
- UTC time window;
- source group or discovery scope;
- regions and topics;
- explicit exclusions;
- allowed output paths;
- definition of done;
- idempotency key.

## States

`planned → ready → leased → collecting → PR open → validating → review → merged`

Failure states: `blocked`, `lease expired`, `rejected`, `cancelled`, `duplicate`.

## Parallelization

Shard work deterministically by:

`source group × time window × region × content type`

The dispatcher is the sole owner of leases and idempotency keys. A worker receives one bounded issue, writes only allowed paths, and opens one PR. Expired leases return to the queue.

## Pull request gate

A PR must:

- link its issue;
- list generated and modified IDs;
- identify upstream sources;
- pass schema, provenance, duplication, editorial, translation, and map-safety checks as applicable;
- receive independent review;
- be squash-merged by a controller.
