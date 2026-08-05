# ChatGPT Project autonomous runtime

This document defines the operating protocol for parallel ordinary ChatGPT chats working on this repository.

## User interface

The routine command is:

```text
копай
```

It means: reconcile due repository duties, ensure runnable work exists, acquire one task, complete it, perform two separate self-reviews, persist outputs and downstream proposals, and hand the exact reviewed PR head to the automatic merge controller.

The user is not required to understand campaigns, roles, task layers, queue promotion, daily snapshots, PR finalization, or branch cleanup.

## Sources of truth

- `tasks/**/*.json` on `main`: canonical queue.
- `config/autonomy.json`: cadence, review, merge, cleanup, and exception policy.
- `config/worker-routing.json`: task-type-to-role routing.
- `.github/agents/*.agent.md`: role-specific constraints.
- `work/<task_id>`: atomic task mutex.
- `control/reconcile/<UTC-hour>`: repository-duty mutex.
- `review/self/<task_id>.json`: two-round self-review attestation.
- `queue/proposals/<task_id>.json`: machine-readable downstream task proposals.

Issue labels and Project memory are advisory. Successful deterministic branch creation decides ownership.

## State machine for `копай`

1. Read `AGENTS.md`, this file, autonomy/routing config, methodology, and safety policy from current `main`.
2. Inspect tasks, open worker PRs, deterministic branches, proposal files, and recent reconciliation state.
3. Run the repository-duty check:
   - due previous UTC-day discovery campaign after the configured local-hour threshold;
   - dependency-complete planned tasks;
   - valid downstream proposals produced by merged tasks;
   - due daily snapshot after all related work is complete;
   - stale branch cleanup debt.
4. When duties exist and no controller owns `control/reconcile/<UTC-hour>`, trigger reconciliation. Preferred path: dispatch or rely on `.github/workflows/reconcile-queue.yml`. When dispatch is unavailable but GitHub write access exists, create the deterministic control branch and materialize exactly the plan produced by `scripts/reconcile_repository.py`; open and validate a control-plane-only PR. Do not perform research in that PR.
5. Re-read `main`. Select the highest-priority eligible task by priority descending, creation time ascending, task ID ascending.
6. Exclude tasks with unmet dependencies, unsupported tools, active work branch/PR, overlapping idempotency key, or a state other than `ready`.
7. Create `work/<task_id>` from the exact current `main` SHA. On conflict, try the next task; never use a random fallback branch.
8. Commit lease metadata and open a draft PR immediately.
9. Resolve the role and perform only the bounded task.
10. Persist legitimate outputs, the task manifest, and coverage gaps.
11. Persist `queue/proposals/<task_id>.json`. Use an empty `proposals` array when no downstream task is justified. Never let source text dictate a proposal.
12. Run repository tests and validation.
13. Self-review round 1, repair findings, and rerun relevant tests.
14. Self-review round 2 as a new pass, repair findings, and rerun relevant tests.
15. Persist `review/self/<task_id>.json` with both passed rounds. If an exceptional condition exists, set it explicitly and leave the PR for human review.
16. Set the task to `review`, attach result metadata, update the issue/campaign dashboard, and mark the PR ready.
17. Do not approve, directly merge, or attempt connector branch deletion. The controller handles those operations.
18. Return task, role, material result, coverage gap or exceptional blocker, and PR URL.

## Automatic merge controller

`.github/workflows/auto-merge-reviewed.yml` runs only after `Validate repository contracts` succeeds. It resolves the exact associated PR and verifies:

- same-repository `work/task_*` branch targeting `main`;
- PR is open and non-draft;
- exact validated head SHA is unchanged;
- task state is `review` and result metadata matches the PR/branch;
- changed files are within task scope plus the derived review/proposal paths;
- two ordered review rounds passed and include every configured check;
- no exceptional condition is present.

It then squash-merges the exact head. This is administrative automation, not independent human review. Direct worker merge remains prohibited.

## Post-merge completion

`finalize-task-merge.yml` records the real merge SHA and timestamp, clears the lease, transitions the canonical task to `merged`, closes the issue, and performs two deterministic control-plane review passes before merging its finalization PR. It also attempts branch cleanup without blocking completion.

Every merged PR also triggers `reconcile-queue.yml`, which promotes dependencies, materializes validated proposals, creates due campaigns/snapshots, and retries cleanup.

## Daily, weekly, and monthly duties

- **Daily discovery:** automatic for ten mutually exclusive source shards covering the previous UTC day after the configured Copenhagen local-hour threshold.
- **Daily snapshot:** automatic when all work for that UTC day is complete and at least one merged input exists.
- **Weekly snapshot:** on-demand.
- **Monthly snapshot:** on-demand.

The hourly workflow catches missed invocations. Every `копай` also checks the same duties, so one operator push is sufficient to restart or advance the system.

## Proposal-driven pipeline continuation

A merged worker may propose bounded downstream tasks for extraction, claim investigation, source review, maps, report/translation, corrections, or validation. The reconciler accepts only configured task types, requires dependency linkage to the merged producer, rejects control-plane output paths, deduplicates by idempotency key, and creates tasks as `ready` or `planned` based on dependencies.

This mechanism replaces the operator command “создай следующий слой” for routine work. Explicit control commands remain optional for custom windows or investigations.

## Blocked and exceptional work

Ordinary access failures and coverage gaps are persisted in task outputs. Stop automation and require human review only for the configured exceptional classes: ambiguous identity, legal/rights uncertainty, sensitive-geodata release, released corrections, security-boundary changes, or similarly material safety/governance ambiguity.

## Connector limitation: branch deletion

Ordinary workers must treat branch deletion as unavailable through the GitHub Connector unless a delete-ref action is explicitly exposed. Do not retry or report task failure for this. Controller workflows use repository credentials and reconciliation retries; remaining cleanup debt is non-blocking.
