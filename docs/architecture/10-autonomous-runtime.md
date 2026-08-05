# Autonomous runtime and self-sustaining queue

## Objective

A repository-authorized agent should be able to receive `копай` without any knowledge of internal roles or queue stages. The invocation checks duties, triggers control-plane work, claims one task, completes it, self-reviews twice, and hands it to an exact-head merge controller.

## Control loop

```text
operator invocation / hourly schedule / merged PR
  -> reconcile repository duties
  -> promote dependencies and materialize proposals
  -> create due daily discovery or snapshot tasks
  -> worker claims one deterministic branch
  -> bounded execution
  -> self-review round 1 -> repairs
  -> self-review round 2 -> repairs
  -> CI + exact scope gate
  -> administrative squash merge
  -> actual merge metadata finalization
  -> issue closure + reconciliation + cleanup retry
```

## Queue reproduction

The system does not rely on an operator to create the next layer. Every task writes `queue/proposals/<task_id>.json`. After the producer merges, the reconciler validates each proposal, enforces dependency linkage and allowed task types, rejects control-plane paths, deduplicates by idempotency key, and creates `ready` or `planned` manifests.

An empty proposal list is meaningful: it records that the worker considered downstream work and found none justified.

## Daily obligations

The reconciler runs hourly and after every merge. After the configured Copenhagen local hour, it creates ten source-sharded tasks for the previous UTC day if the autonomy activation boundary has passed and backlog limits allow. It creates a daily snapshot task only after all related tasks and materialized proposals for the day are complete and at least one input merged.

Weekly and monthly snapshots are intentionally on-demand.

## Two-round self-review

Both rounds use the configured check set: scope, provenance, deduplication, temporal precision, safety, tests, and coverage gaps. Round 2 must occur after round 1 and after all round-1 repairs. A receipt with failed rounds or an exceptional condition cannot auto-merge.

Self-review is not represented as independent review. It is an accountable administrative quality gate.

## Merge and cleanup boundary

Workers cannot directly merge. A GitHub Actions controller receives the successful validation event, verifies the exact head, task scope, receipt, and exceptional-condition status, then squash-merges. Post-merge automation records actual merge metadata.

Branch deletion is controller-owned. Failure to delete a branch is cleanup debt, not incomplete research. The hourly reconciler retries it.

## Exceptional human gate

Automation stops for source-identity ambiguity, legal/rights uncertainty, sensitive geodata release, released corrections, credential/security-boundary changes, or any other configured exceptional condition. These cases are expected to be rare and explicitly recorded.
