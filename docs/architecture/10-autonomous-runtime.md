# Autonomous runtime and self-sustaining queue

## Objective

A repository-authorized agent should be able to receive `копай` without knowing internal roles or queue stages. The invocation checks duties, triggers control-plane work, claims one task, completes it, self-reviews twice, and hands it to an exact-head merge controller.

`continuous loop` composes this atomic lifecycle into a long-running supervisor. Its detailed contract is defined in [`11-continuous-loop.md`](11-continuous-loop.md).

## Control loop

```text
operator invocation / hourly schedule / merged PR
  -> reconcile repository duties
  -> promote dependencies and materialize proposals
  -> create due daily discovery or snapshot tasks
  -> select a pickable task
  -> create deterministic work branch
  -> bounded execution with automatic withholding
  -> self-review round 1 -> repairs
  -> self-review round 2 -> repairs
  -> CI + exact scope gate
  -> administrative squash merge
  -> actual merge metadata finalization
  -> issue closure + reconciliation + cleanup retry
```

In Continuous Loop mode, the supervisor refreshes `main` after the finalization barrier and starts the control loop again instead of reporting after one task.

## Queue reproduction

The system does not rely on an operator to create the next layer. Every task writes `queue/proposals/<task_id>.json`. After the producer merges, the reconciler validates each proposal, enforces dependency linkage and allowed task types, deduplicates by idempotency key, and creates `ready` or `planned` manifests.

Proposal-generated task permissions are restricted to data-plane roots: `catalogs/`, `data/`, `maps/`, `raw-manifests/`, and `reports/`. A worker cannot use a proposal to grant access to workflows, schemas, scripts, tasks, review receipts, tests, or other control-plane files.

An empty proposal list is meaningful: it records that the worker considered downstream work and found none justified.

## Daily obligations

The reconciler runs hourly and after every merge. After the configured Copenhagen local hour, it creates ten source-sharded tasks for the previous UTC day if the complete UTC day began at or after the autonomy activation boundary and backlog limits allow. A day that started before `activation_not_before` is not backfilled automatically. The reconciler creates a daily snapshot task only after all related tasks and materialized proposals for the day are complete and at least one input merged.

Weekly and monthly snapshots are on-demand.

## Two-round self-review

Both rounds use the configured check set: scope, provenance, deduplication, temporal precision, safety, tests, and coverage gaps. Round 2 occurs after round 1 and all round-1 repairs.

Self-review is not independent review. It is an accountable administrative quality gate. Unsafe or uncertain material must be removed, withheld, coarsened, or represented only as a coverage gap before the task is handed to the merge controller.

## Merge and scope boundary

Workers cannot directly merge. A GitHub Actions controller receives the successful validation event, verifies that the current PR head is the exact SHA validated by CI, checks the task receipt, and then squash-merges.

The write-capable controller executes validator code only from trusted `main`. The reviewed PR head is checked out separately and treated as untrusted data. It cannot replace its own merge gates.

Worker permissions are taken from the base task manifest on `main`, not from the modified head manifest. Task-contract fields such as scope, dependencies, idempotency key, and `allowed_output_paths` are immutable inside the worker PR. Only lifecycle/result metadata may change.

Hardening and other control-plane PRs are excluded from the worker auto-merge path and are also excluded from Continuous Loop scheduling decisions.

## Retired human gate

`human_gate` is no longer part of the supervisor state machine. Open architecture/hardening PRs and the compatibility `exceptional_prs` counter cannot stop task selection or quiescence.

Legacy task manifests with `state: blocked` and a `blocked_reason` beginning with `HUMAN_REVIEW_REQUIRED:` are treated as pickable after the normal dependency and canonicalization checks. The claimant transitions the task directly to `leased`, clears the retired blocker, and preserves its substance as a withholding note or coverage gap.

## Automatic withholding

The configured `automatic_withhold_for` classes are handled without operator review:

- source identity ambiguity: do not attribute or publish the ambiguous material;
- legal or rights uncertainty: do not copy or release the disputed content;
- sensitive geodata: omit, delay, or coarsen it;
- released corrections: preserve the correction record and do not silently rewrite history;
- credential or security-boundary changes: exclude them from the task and repository output.

The safe bounded remainder of the task continues. The worker records the omission and reason rather than inventing evidence or blocking the entire queue.

## Supervisor boundary

Continuous Loop is a control-plane supervisor, not a wider worker permission set. It cannot combine several tasks in one work branch, bypass exact-head CI, or merge directly.

The supervisor waits for both squash merge and finalization before selecting the next task. This makes proposal creation and dependency promotion visible before the next selection.

## Cleanup boundary

Branch deletion is controller-owned. Workers must not spend task time attempting GitHub Connector branch deletion. Failure to delete a branch is cleanup debt, not incomplete research, and the hourly reconciler retries it.
