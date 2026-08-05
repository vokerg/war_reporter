# ChatGPT Project runtime

This document defines the operating protocol for multiple ordinary ChatGPT chats working in parallel on this repository.

## User interface

The command **`копай`** means:

> ensure that runnable work exists, autonomously acquire exactly one eligible task, perform it completely, persist the result in GitHub, and return the task and pull-request links.

The user does not select a campaign, task, or role. An empty queue is a bootstrap condition, not a reason to stop.

## Required worker capabilities

A worker must have:

- read access to the repository, issues, branches, pull requests, and CI;
- write access to create issues and branches, commit files, open a draft PR, update issues, and merge the deterministic queue-bootstrap PR;
- approved web/search connectors for task types requiring internet research.

A read-only GitHub connection is insufficient. If a required capability is absent, report the exact missing capability. Do not pretend to have persisted work.

## Source of truth

- `tasks/**/*.json` on `main` is the canonical runnable queue.
- GitHub issues are the human dashboard and campaign record.
- `config/worker-routing.json` maps `task_type` to the required agent role.
- `.github/agents/*.agent.md` contains role-specific constraints.
- A deterministic branch named `work/<task_id>` is the atomic task mutex.
- A deterministic branch named `control/bootstrap/<UTC-hour>` is the empty-queue bootstrap mutex.

Issue labels are advisory. Branch creation decides ownership.

## Meaning of `копай`

On `копай`, perform this state machine without asking the user which campaign, task, or role to choose:

1. Read `AGENTS.md`, this file, the routing config, methodology, and safety policy from `main`.
2. Read all task manifests on `main`.
3. When there is no eligible `ready` task, execute the zero-queue bootstrap protocol below. Do not stop merely because `tasks/` is empty.
4. Exclude tasks that:
   - are not `ready`;
   - have unmet dependencies;
   - are outside available worker capabilities;
   - already have a `work/<task_id>` branch or active PR;
   - overlap an active task by idempotency key.
5. Sort eligible tasks by:
   - higher `priority`;
   - earlier `created_at`;
   - lexical `task_id`.
6. Generate a unique `worker_run_id` with prefix `run_`.
7. Try to create `work/<task_id>` from the exact current `main` SHA.
8. If branch creation conflicts, another worker won. Continue to the next eligible task.
9. After successful branch creation:
   - re-read the manifest from `main`;
   - verify it is still `ready`;
   - update the manifest on the work branch to `leased`;
   - write `worker_run_id`, branch, base SHA, lease timestamps, and issue number;
   - open a draft PR immediately so the claim is visible.
10. Resolve the role from `config/worker-routing.json` and read its agent file.
11. Perform only the bounded task and write only `allowed_output_paths` plus the task manifest.
12. Run all applicable tests and validators.
13. Update the manifest to `pr_open`, attach result metadata, and update the issue/campaign dashboard.
14. Never approve or merge your own research PR.
15. Return a concise result containing:
   - acquired task;
   - role;
   - material result or exact blocker;
   - uncertainty/coverage gap;
   - draft PR URL.

Research that exists only in chat is incomplete work.

## Zero-queue bootstrap

This protocol makes the first `копай` sufficient to start a fresh installation.

1. Round the current time down to the UTC hour and derive:

   ```text
   control/bootstrap/YYYYMMDDTHH00Z
   ```

2. Try to create that exact branch from the current `main` SHA.
3. If branch creation conflicts, another chat is the bootstrap controller. Re-read bootstrap branches/PRs and `main` several times during the same run. As soon as the bootstrap PR merges, continue normal task acquisition. Do not create a fallback bootstrap branch.
4. The bootstrap winner:
   - creates a campaign issue for the preceding 24-hour UTC window;
   - generates ten mutually exclusive `open_web_discovery` manifests using `scripts/bootstrap_pilot.py`;
   - uses catalog-independent shards so an empty `catalogs/sources/` is not a blocker;
   - writes only `tasks/**` plus any strictly necessary campaign metadata;
   - opens a PR titled `[bootstrap] <UTC window>`;
   - runs repository and worker-queue validation.
5. A bootstrap PR contains no research findings, reports, claims, map geometry, or source judgments. The bootstrap controller may squash-merge this deterministic control-plane-only PR after CI succeeds, using the expected head SHA. This is the sole self-merge exception.
6. After the bootstrap PR merges, the same chat refreshes `main`, claims one of the ten tasks, and starts research. Other chats refresh and claim the remaining tasks.
7. If repository rules require an independent approval even for bootstrap, record that exact blocker instead of silently pushing to `main`.

## Bootstrap shard requirements

The initial ten tasks must be runnable without an existing source catalog. They cover:

1. Ukrainian official statements;
2. Russian official statements;
3. Ukrainian analysis and media;
4. Russian milbloggers;
5. international media;
6. military analysts;
7. strikes and infrastructure;
8. visual OSINT and maps;
9. diplomacy, military support, and sanctions;
10. reactions, corrections, and retractions.

All are first-layer discovery tasks. They may propose valid source profiles and source items, but they do not make final truth assessments or publish operational maps.

## Atomic claim protocol

GitHub ref creation is the task mutex:

```text
refs/heads/work/<task_id>
```

Only one create-ref operation can succeed for a given task. A worker must not use a random branch name, because that would permit duplicate work.

The first branch commit must update the task manifest with:

```json
{
  "state": "leased",
  "lease": {
    "worker_run_id": "run_...",
    "lease_branch": "work/task_...",
    "base_sha": "40-character main SHA",
    "leased_at": "UTC timestamp",
    "lease_until": "UTC timestamp"
  }
}
```

A worker that did not create the deterministic branch does not own the task.

## Lease expiry and recovery

Workers do not delete another worker's branch. A controller may requeue an expired task only after:

1. verifying that the lease deadline passed;
2. verifying that no active worker or PR is progressing;
3. recording the recovery reason on the issue;
4. deleting the stale deterministic branch;
5. returning the canonical manifest to `ready`.

Ambiguous recovery requires human review.

## Research completion protocol

The worker leaves the task in `pr_open` or `review`. The independent merge controller:

1. verifies expected head SHA and CI;
2. changes the task manifest to `merged`;
3. updates the issue mirror to `state:done`;
4. squash-merges the PR;
5. deletes the work branch.

The deterministic zero-queue bootstrap exception is defined separately above and does not permit self-merging research, analysis, report, translation, correction, or map PRs.

## Blocked work

When blocked:

- do not broaden scope or invent evidence;
- update the branch manifest to `blocked` when a task was already claimed;
- add a precise `blocked_reason`;
- open or update the draft PR with only legitimate partial outputs;
- update the issue/campaign dashboard;
- stop.

Examples include unavailable web connector, inaccessible source, ambiguous source identity, overlapping work, unsafe geodata, or conflicting instructions.

## Controller commands

Control commands remain available but are optional:

- `создай кампанию` — explicitly create a bounded campaign and ready task layer;
- `покажи прогресс` — summarize queue, active branches, PRs, blockers, and coverage;
- `создай следующий слой` — create extraction, corroboration, reporting, translation, or validation tasks whose dependencies are complete;
- `разбери просроченные lease` — audit stale branches without silently deleting active work.

The ordinary command `копай` must bootstrap when needed; the user is not required to invoke `создай кампанию` first.

## Parallel operation

Ten chats may all receive `копай` at once. They share project instructions but coordinate only through GitHub. Project memory is not a lock and must never be used to decide task ownership.

## Canonicalization and bootstrap gate

Discovery workers must not create extraction, claim, corroboration, assessment, map-publication, or report tasks unless repository validation confirms that source-profile and source-item canonicalization is complete.

A worker may bootstrap a new campaign only when all queue backpressure checks pass simultaneously: no eligible ready tasks, no active leases, no open worker PRs, the prior campaign is closed or explicitly carried over, and the configured backlog limit is not exceeded. “No eligible ready task” alone never means “no work exists.”

The repository currently uses one GitHub identity for worker and merge-controller actions. Review is therefore **administrative review**, not cryptographically independent review. Research PRs must not describe this arrangement as independent review unless distinct authenticated identities are configured and enforced.

