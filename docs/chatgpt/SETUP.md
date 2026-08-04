# ChatGPT Project setup

## 1. Create the Project

Create a ChatGPT Project named `War Reporter`. Paste the contents of `PROJECT_INSTRUCTIONS.md` into Project Instructions.

Connect a GitHub integration that can create branches, commit files, open draft PRs, update issues, and read CI. A read-only repository connector cannot run the worker protocol.

Connect approved web/search tools for research tasks. Keep credentials in the connector or secret store, never in chats or the repository.

## 2. Create repository labels

`config/github-labels.json` is the desired label set.

With a GitHub token:

```bash
GITHUB_TOKEN=... python scripts/sync_github_labels.py
```

Labels mirror task state for humans; they do not provide the lock.

## 3. Create a campaign

Use a control chat:

```text
Создай кампанию за последние 24 часа по одному ограниченному региону.
Создай parent issue и 10 mutually exclusive first-layer task manifests.
Не выполняй research в этом чате.
```

Alternatively generate the pilot manifests locally with `scripts/bootstrap_pilot.py`, review them, and merge the planning PR.

## 4. Start ten workers

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

Each chat independently scans `main`. GitHub deterministic branch creation ensures that only one chat owns each task.

## 5. Advance the campaign

After first-layer PRs merge, tell the control chat:

```text
создай следующий слой
```

The controller should create extraction and lineage tasks, then claim-investigation tasks, then assessment/report/map/translation/validation tasks. It must not mark a task ready until dependencies are merged.

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
- missing source groups or connectors.

## 7. Recover stale work

Use:

```text
разбери просроченные lease
```

The controller audits stale branches but does not delete ambiguous active work automatically.

## Operational warning

Ten parallel chats are manually triggered workers, not a continuous daemon. Repeated or scheduled execution requires a future MCP queue/scheduler service.
