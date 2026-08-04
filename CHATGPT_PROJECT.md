# ChatGPT Project runtime

This document defines the operating protocol for multiple ordinary ChatGPT chats working in parallel on this repository.

## User interface

The command **`копай`** means:

> autonomously acquire exactly one eligible task, perform it completely, persist the result in GitHub, and return the task and pull-request links.

The user does not select a task or role. The queue and routing table do that.

## Required worker capabilities

A worker must have:

- read access to the repository, issues, branches, pull requests, and CI;
- write access to create a branch, commit files, open a draft PR, and update the linked issue;
- approved web/search connectors for task types requiring internet research.

A read-only GitHub connection is insufficient. If a required capability is absent, mark the selected task blocked or report that no task can be safely claimed. Do not pretend to have persisted work.

## Source of truth

- `tasks/**/*.json` on `main` is the canonical queue.
- GitHub issues are the human dashboard and mirror task state.
- `config/worker-routing.json` maps `task_type` to the required agent role.
- `.github/agents/*.agent.md` contains role-specific constraints.
- A deterministic branch named `work/<task_id>` is the atomic task mutex.

Issue labels are advisory. Branch creation decides who acquired a task.

## Meaning of `копай`

On `копай`, perform this state machine without asking the user which task to choose:

1. Read `AGENTS.md`, this file, the routing config, methodology, and safety policy from `main`.
2. Read all task manifests on `main`.
3. Exclude tasks that:
   - are not `ready`;
   - have unmet dependencies;
   - are outside available worker capabilities;
   - already have a `work/<task_id>` branch or active PR;
   - overlap an active task by idempotency key.
4. Sort eligible tasks by:
   - higher `priority`;
   - earlier `created_at`;
   - lexical `task_id`.
5. Generate a unique `worker_run_id` with prefix `run_`.
6. Try to create `work/<task_id>` from the exact current `main` SHA.
7. If branch creation conflicts, another worker won. Continue to the next eligible task.
8. After successful branch creation:
   - re-read the manifest from `main`;
   - verify it is still `ready`;
   - update the manifest on the work branch to `leased`;
   - write `worker_run_id`, branch, base SHA, lease timestamps, and issue number;
   - open a draft PR immediately so the claim is visible.
9. Resolve the role from `config/worker-routing.json` and read its agent file.
10. Perform only the bounded task and write only `allowed_output_paths` plus the task manifest.
11. Run all applicable tests and validators.
12. Update the manifest to `pr_open`, attach the result metadata, and update the issue mirror to `state:review`.
13. Never approve or merge your own PR.
14. Return a concise result containing:
   - acquired task;
   - role;
   - material result or exact blocker;
   - uncertainty/coverage gap;
   - draft PR URL.

Research that exists only in chat is incomplete work.

## Atomic claim protocol

GitHub ref creation is the mutex:

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

## Completion protocol

The worker leaves the task in `pr_open` or `review`. The independent merge controller:

1. verifies expected head SHA and CI;
2. changes the task manifest to `merged`;
3. updates the issue mirror to `state:done`;
4. squash-merges the PR;
5. deletes the work branch.

## Blocked work

When blocked:

- do not broaden scope or invent evidence;
- update the branch manifest to `blocked`;
- add a precise `blocked_reason`;
- open or update the draft PR with only legitimate partial outputs;
- update the issue mirror to `state:blocked`;
- stop.

Examples include unavailable web connector, inaccessible source, ambiguous source identity, overlapping work, unsafe geodata, or conflicting instructions.

## Controller commands

A control chat may receive:

- `создай кампанию` — create a bounded campaign and ready task layer;
- `покажи прогресс` — summarize queue, active branches, PRs, blockers, and coverage;
- `создай следующий слой` — create extraction, corroboration, reporting, translation, or validation tasks whose dependencies are complete;
- `разбери просроченные lease` — audit stale branches without silently deleting active work.

## Parallel operation

Ten chats may all receive `копай` at once. They share project instructions but coordinate only through GitHub. Project memory is not a lock and must never be used to decide task ownership.
