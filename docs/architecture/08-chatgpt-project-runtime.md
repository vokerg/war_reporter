# ChatGPT Project runtime

## Objective

Operate the repository through one ChatGPT Project containing a control chat and approximately ten parallel worker chats. The routine worker command is `копай`.

## Coordination model

Shared project instructions provide common behavior but are not concurrency control. GitHub is the coordination plane:

- manifests on `main` are the canonical queue;
- issues mirror state for humans;
- deterministic work branches are atomic mutexes;
- draft PRs expose ownership and progress;
- CI and independent review gate merge.

## Worker state machine

```text
discover ready task
  → create work/<task_id>
  → leased
  → collecting/executing
  → pr_open
  → validating
  → review
  → merged
```

A failed deterministic branch creation means another worker acquired the task. The losing worker must continue scanning, not create a differently named branch.

## Task eligibility

A task is eligible only when:

- `state == ready`;
- all `depends_on_task_ids` resolve to tasks in `merged`;
- its idempotency key is unique;
- no deterministic work branch or active PR exists;
- the worker has the required GitHub and research tools.

Ordering is priority descending, creation time ascending, task ID ascending.

## Layered campaigns

A campaign should create independent collection/discovery tasks first. Later layers are generated only from merged inputs:

```text
collection/discovery
  → extraction and lineage
  → claim investigation
  → assessments/maps
  → report
  → translation
  → validation
```

This prevents report writers from browsing freely and avoids premature synthesis.

## Failure model

- Missing write-capable GitHub integration: no task claim.
- Missing web connector: research task becomes blocked.
- Branch conflict: normal contention; try another task.
- Expired lease: controller audit and explicit recovery.
- CI failure: keep PR open and repair within task scope.
- Unsafe or ambiguous geodata: blocked pending human review.

## MVP and future service

The deterministic branch mutex is sufficient for manually launched parallel chats. A future MCP queue service may replace branch scanning with `get_next_task` and transactional leases, but it must preserve the same manifest and audit semantics.
