# Task lifecycle

The manifest in `tasks/` on `main` is authoritative.

```text
planned -> ready -> leased -> collecting -> pr_open -> validating -> review -> merged
```

Recovery states include `blocked`, `lease_expired`, `rejected`, `cancelled`, and `duplicate`.

## Acquisition

`work/<task_id>` is the mutex. Successful exact-ref creation owns the task; conflict means another worker won. Random fallback branches are prohibited.

## Completion

A worker persists outputs, `queue/proposals/<task_id>.json`, and two ordered passing rounds in `review/self/<task_id>.json`; then sets the task to `review` and makes the PR ready.

The merge controller verifies exact-head CI, scope, receipt, and exceptional status, then squash-merges. Post-merge finalization writes actual merge SHA/time and clears the lease.

## Queue continuation

Merged proposal files create bounded downstream tasks. Dependency-complete planned tasks are promoted automatically. Daily discovery and daily snapshot duties are reconciled hourly and after merges.

## Cleanup

Branch deletion is controller-owned and non-blocking. Workers do not retry Connector deletion failures.
