# War Reporter

War Reporter is a versioned, evidence-centered OSINT research and publication system. It records what was asserted, by whom, which evidence supports or disputes it, how assessments changed, and why a report or map feature was published.

The intended interactive runtime is a **ChatGPT Project containing a control chat and multiple parallel worker chats**. The routine worker command is:

```text
копай
```

A worker then selects one eligible task, atomically claims it through a deterministic GitHub branch, resolves its role, performs bounded research, persists structured output, and opens a draft PR.

## Start here

1. [`CHATGPT_PROJECT.md`](CHATGPT_PROJECT.md) — exact runtime and command protocol.
2. [`docs/chatgpt/PROJECT_INSTRUCTIONS.md`](docs/chatgpt/PROJECT_INSTRUCTIONS.md) — text to paste into ChatGPT Project Instructions.
3. [`docs/chatgpt/SETUP.md`](docs/chatgpt/SETUP.md) — bootstrap and ten-chat operating procedure.
4. [`AGENTS.md`](AGENTS.md) — contributor invariants and role routing.
5. [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) — system components and trust boundaries.
6. [`METHODOLOGY.md`](METHODOLOGY.md) — evidence, source, and assessment methodology.
7. [`SECURITY_AND_SAFETY.md`](SECURITY_AND_SAFETY.md) — operational, privacy, prompt-injection, and publication safety.

## Parallel worker model

- `tasks/**/*.json` on `main` is the canonical queue.
- GitHub issues mirror queue state for humans.
- `work/<task_id>` is the atomic task lock and working branch.
- `config/worker-routing.json` maps task types to role instructions.
- Ten chats may all receive `копай`; only one can create a particular deterministic work branch.

## Bootstrap a pilot queue

```bash
python scripts/bootstrap_pilot.py \
  --date 2026-08-04 \
  --parent-issue 3 \
  --region ukraine-war \
  --output tasks/2026/08/04
```

This creates ten independent first-layer tasks. Commit them through a planning PR before starting workers.

## Inspect and simulate the queue locally

```bash
python scripts/worker_queue.py next
python scripts/worker_queue.py run-id
python scripts/worker_queue.py role source_scan
python scripts/worker_queue.py claim-local task_example
```

The local claim command simulates GitHub's atomic create-ref behavior. Production ChatGPT workers claim by creating `work/<task_id>` through the GitHub integration.

## Repository validation

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/validate_data.py
python scripts/validate_worker_queue.py
```

## Repository layers

- `catalogs/` — source, region, topic, and terminology registries.
- `data/` — source items, artifacts, observations, claims, events, reactions, assessments, corrections, and report manifests.
- `tasks/` — canonical machine-readable task contracts.
- `maps/` — provenance-linked GeoJSON and snapshot manifests.
- `reports/` — English editorial reports and Russian translations.
- `schemas/` — JSON Schema contracts.
- `.github/agents/` — least-privilege role profiles.
- `.github/ISSUE_TEMPLATE/` — human task intake and dashboard forms.
- `config/` — worker routing and repository-label configuration.

## Current boundary

This branch protocol supports manually launched parallel ChatGPT chats without a separate queue service. Continuous autonomous scheduling, a transactional MCP queue, operational database, object storage, website, map renderer, and publication automation remain future work.
