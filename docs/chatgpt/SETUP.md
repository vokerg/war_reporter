# ChatGPT Project setup

## 1. Create the Project

Create a ChatGPT Project named `War Reporter`. Paste the contents of `PROJECT_INSTRUCTIONS.md` into Project Instructions.

Connect a GitHub integration that can create issues and branches, commit files, open and merge the deterministic bootstrap PR, open draft research PRs, update issues, and read CI. A read-only repository connector cannot run the worker protocol.

Connect approved web/search tools for research tasks. Keep credentials in the connector or secret store, never in chats or the repository.

## 2. Create repository labels

`config/github-labels.json` is the desired label set.

With a GitHub token:

```bash
GITHUB_TOKEN=... python scripts/sync_github_labels.py
```

Labels mirror task state for humans; they do not provide the lock.

## 3. Start ten workers

Create ten ordinary chats inside the same Project:

```text
Worker 01
Worker 02
...
Worker 10
```

Send each chat one message:

```text
копай
```

No campaign command is required. When `tasks/` has no eligible work:

1. exactly one chat creates `control/bootstrap/<UTC-hour>`;
2. that chat creates a 24-hour campaign issue and ten catalog-independent discovery manifests;
3. it opens, validates, and squash-merges the control-plane-only bootstrap PR;
4. it refreshes `main` and claims one generated task;
5. the remaining chats refresh and atomically claim the other tasks through `work/<task_id>`.

If another chat already owns the bootstrap branch, workers must re-read the bootstrap PR and `main` rather than returning immediately or creating fallback branches.

## 4. Optional explicit campaign

A control chat is still useful when you want a non-default period, region, or research objective:

```text
Создай кампанию за период 2026-08-01T00:00:00Z/2026-08-02T00:00:00Z
по одному ограниченному региону и создай 10 mutually exclusive first-layer tasks.
```

Alternatively generate manifests locally:

```bash
python scripts/bootstrap_pilot.py \
  --from 2026-08-03T18:00:00Z \
  --to 2026-08-04T18:00:00Z \
  --parent-issue 5 \
  --region ukraine-war \
  --output tasks/2026/08/04
```

The initial layer consists only of `open_web_discovery` tasks, so an empty source catalog is not a blocker.

## 5. Advance the campaign

After first-layer PRs merge, use:

```text
создай следующий слой
```

The controller should create extraction and lineage tasks, then claim-investigation tasks, then assessment/report/map/translation/validation tasks. It must not mark a task ready until dependencies are merged.

A later runtime may automatically materialize the next layer; in the current MVP this command remains explicit.

## 6. Observe progress

Use:

```text
покажи прогресс
```

The response should summarize:

- ready tasks;
- active deterministic branches;
- draft PRs;
- blocked tasks and reasons;
- merged coverage;
- missing connectors or inaccessible platforms.

## 7. Recover stale work

Use:

```text
разбери просроченные lease
```

The controller audits stale branches but does not delete ambiguous active work automatically.

## Operational warning

Ten parallel chats are manually triggered workers, not a continuous daemon. Repeated scheduled execution still requires a future MCP queue/scheduler service.
