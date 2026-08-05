# ChatGPT Project autonomous runtime

This document defines the operating protocol for parallel ordinary ChatGPT chats working on this repository.

## User interface

The routine atomic command is:

```text
копай
```

It means: reconcile due repository duties, ensure runnable work exists, acquire one task, complete it, perform two separate self-reviews, persist outputs and downstream proposals, and hand the exact reviewed PR head to the automatic merge controller.

The long-running supervisor command is:

```text
continuous loop
```

Configured aliases are `continuous-loop`, `копай непрерывно`, and `непрерывный цикл`. It repeatedly executes the full atomic protocol, waits for actual merge/finalization, refreshes `main`, and continues through all proposal-generated work.

The user is not required to understand campaigns, roles, task layers, queue promotion, daily snapshots, PR finalization, branch cleanup, withholding decisions, or loop quiescence.

## Sources of truth

- `tasks/**/*.json` on `main`: canonical queue.
- `config/autonomy.json`: cadence, loop, review, merge, cleanup, and automatic-withhold policy.
- `config/worker-routing.json`: task-type-to-role routing.
- `.github/agents/*.agent.md`: role-specific constraints.
- `work/<task_id>`: atomic task mutex.
- `control/reconcile/<UTC-hour>`: repository-duty mutex.
- `review/self/<task_id>.json`: two-round self-review attestation.
- `queue/proposals/<task_id>.json`: machine-readable downstream task proposals.
- `scripts/continuous_loop.py`: deterministic supervisor decision engine.

Issue labels and Project memory are advisory. Successful deterministic branch creation decides ownership.

## State machine for `копай`

1. Read `AGENTS.md`, this file, autonomy/routing config, methodology, and safety policy from current `main`.
2. Inspect tasks, open worker PRs, deterministic branches, proposal files, and recent reconciliation state.
3. Check due repository duties: previous UTC-day discovery, dependency promotion, merged-task proposals, daily snapshots, and cleanup debt.
4. When duties exist, complete only deterministic control-plane reconciliation and refresh `main`.
5. Select the highest-priority eligible task by priority descending, creation time ascending, task ID ascending.
6. A normal task is eligible only in `ready` with satisfied dependencies. A legacy task in `blocked` whose `blocked_reason` begins with `HUMAN_REVIEW_REQUIRED:` is also eligible; this marker is retired and no longer requires operator action.
7. Create `work/<task_id>` from the exact current `main` SHA. On conflict, try the next task; never use a random fallback branch.
8. For a legacy retired-gate task, transition the manifest directly from `blocked` to `leased`, clear `blocked_reason`, and preserve the former reason as a coverage gap or withholding note.
9. Commit lease metadata and open a draft PR immediately.
10. Resolve the role and perform only the bounded task.
11. Apply automatic withholding for identity ambiguity, rights uncertainty, sensitive geodata, released corrections, and security-boundary changes. Omit, coarsen, or defer unsafe material; do not stop for human review.
12. Persist legitimate outputs, the task manifest, coverage gaps, and `queue/proposals/<task_id>.json`.
13. Run repository tests and validation.
14. Perform self-review round 1, repair findings, then perform a fresh round 2 and repair any new findings.
15. Persist `review/self/<task_id>.json` with both passed rounds and any withholding notes.
16. Set the task to `review`, attach result metadata, update the issue/campaign dashboard, and mark the PR ready.
17. Do not approve, directly merge, or attempt connector branch deletion. The controller handles those operations.
18. Return task, role, material result, coverage gaps, and PR URL.

## State machine for `continuous loop`

1. Read the same current-`main` contract as `копай`, including `continuous_loop` configuration.
2. Evaluate the repository with `scripts/continuous_loop.py` semantics.
3. On `reconcile`, complete only deterministic control-plane reconciliation, wait for its result on `main`, refresh, and evaluate again.
4. On `claim`, execute one complete `копай` task lifecycle. The claim payload can include `retired_human_gate: true`; in that case perform the `blocked` to `leased` transition described above.
5. After the task reaches a ready exact-head PR, do not report completion and do not claim another task.
6. Poll until the controller has squash-merged the exact reviewed head and post-merge finalization is visible on `main`.
7. Refresh `main`; allow post-merge reconciliation to materialize proposals; evaluate again.
8. Treat every transitively spawned task as part of the same loop.
9. On `wait`, remain in supervisor mode and recheck at the configured merge or idle cadence.
10. On `quiescent`, return one final aggregate report covering all tasks completed in the loop.
11. If runtime or tools force termination before `quiescent`, report `continuation_required`; do not claim that the loop completed.

`human_gate` is not a valid action. The backward-compatible `exceptional_prs` input is telemetry only and cannot change the decision. Architecture, hardening, or other non-worker PRs therefore cannot stop the research loop.

## Automatic merge controller

`.github/workflows/auto-merge-reviewed.yml` runs only after `Validate repository contracts` succeeds. It resolves the exact associated PR and verifies:

- same-repository `work/task_*` branch targeting `main`;
- PR is open and non-draft;
- exact validated head SHA is unchanged;
- task state is `review` and result metadata matches the PR/branch;
- changed files are within task scope plus the derived review/proposal paths;
- two ordered review rounds passed and include every configured check;
- unsafe material identified during review has been removed, withheld, or coarsened before handoff.

It then squash-merges the exact head. This is administrative automation, not independent human review. Direct worker merge remains prohibited.

## Post-merge completion

`finalize-task-merge.yml` records the real merge SHA and timestamp, clears the lease, transitions the canonical task to `merged`, closes the issue, and performs deterministic control-plane review before merging its finalization PR. It also attempts branch cleanup without blocking completion.

Every merged PR also triggers `reconcile-queue.yml`, which promotes dependencies, materializes validated proposals, creates due campaigns/snapshots, and retries cleanup.

For Continuous Loop, post-merge completion is a synchronization barrier. The next task may be claimed only after this state is visible on refreshed `main`.

## Daily, weekly, and monthly duties

- **Daily discovery:** automatic for ten mutually exclusive source shards covering the previous UTC day after the configured Copenhagen local-hour threshold.
- **Daily snapshot:** automatic when all work for that UTC day is complete and at least one merged input exists.
- **Weekly snapshot:** on-demand.
- **Monthly snapshot:** on-demand.

The hourly workflow catches missed invocations. Every `копай` and every Continuous Loop iteration checks the same duties.

## Proposal-driven pipeline continuation

A merged worker may propose bounded downstream tasks for extraction, claim investigation, source review, maps, report/translation, corrections, or validation. The reconciler accepts only configured task types, requires dependency linkage to the merged producer, rejects control-plane output paths, deduplicates by idempotency key, and creates tasks as `ready` or `planned` based on dependencies.

Continuous Loop follows this proposal closure transitively without returning control between layers.

## Quiescence and idle waiting

A single empty scan cannot end Continuous Loop. Voluntary exit requires the configured number of unchanged idle sweeps and minimum elapsed idle window, with no due duty, eligible or nonterminal task, open worker PR, active work branch, temporary reconciliation blocker, or scheduled daily boundary inside the guard.

Non-worker and architecture PRs are outside this calculation. The reference decision engine returns `reconcile`, `claim`, `wait`, or `quiescent`.

## Blocked work and withholding

Ordinary access failures remain `blocked` or are recorded as coverage gaps according to the task contract. Retired `HUMAN_REVIEW_REQUIRED:` tasks are pickable. Safety/governance uncertainty does not become an operator queue: withhold the unsafe portion, preserve the reason, and complete the safe bounded remainder without inventing evidence.

## Connector limitation: branch deletion

Ordinary workers must treat branch deletion as unavailable through the GitHub Connector unless a delete-ref action is explicitly exposed. Do not retry or report task failure for this. Controller workflows use repository credentials and reconciliation retries; remaining cleanup debt is non-blocking.
