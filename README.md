# War Reporter

War Reporter is a versioned, evidence-centered OSINT research and publication system. It records assertions, provenance, competing evidence, assessment history, corrections, and publication decisions.

The primary runtime is a ChatGPT Project with parallel worker chats. The routine atomic command is:

```text
копай
```

One invocation checks repository duties, creates or promotes necessary tasks, claims one task, completes it, self-reviews it twice, and hands it to automatic exact-head squash merge. The operator does not need to know the internal queue or role topology.

The long-running supervisor command is:

```text
continuous loop
```

Aliases are `continuous-loop`, `копай непрерывно`, and `непрерывный цикл`. This mode repeats the complete `копай` lifecycle. It waits for the current task's actual squash merge and post-merge finalization on `main`, refreshes repository state, consumes newly materialized proposals, and claims the next eligible task. It does not voluntarily finish after one task or one empty queue scan.

## Autonomous control loop

- `tasks/**/*.json` on `main` is the canonical queue.
- `work/<task_id>` is the atomic worker lock.
- `queue/proposals/<task_id>.json` reproduces downstream work after merges.
- `review/self/<task_id>.json` records two separate self-review rounds.
- `scripts/continuous_loop.py` provides a deterministic supervisor decision engine.
- `reconcile-queue.yml` runs hourly and after successful task finalization; it validates and pushes task-only queue transitions directly to `main`.
- `auto-merge-reviewed.yml` squash-merges exact CI-green reviewed worker heads.
- `finalize-task-merge.yml` records actual merge metadata directly on `main` and triggers downstream reconciliation.
- Workers ignore Connector branch-deletion limitations; cleanup is controller-owned and non-blocking.

The supervisor returns only `reconcile`, `claim`, `wait`, or `quiescent`. There is no operator-stop action. Blocked tasks do not preempt unrelated ready work.

Daily discovery is automatic across ten configured source shards. Daily snapshots are automatic when their full window is complete. Russian daily translations are automatic after the English report merges. Weekly and monthly snapshots are on-demand.

## Automatic withholding

The operator is not asked to adjudicate source ambiguity, rights uncertainty, sensitive geodata, released corrections, or credential/security-boundary changes. Workers fail closed on the affected material: omit it, coarsen it, preserve the correction history, or exclude the security change. They record the limitation as a coverage gap and complete the safe bounded remainder.

Automatic withholding never permits invented evidence, access-control bypass, or unsafe publication.

## Static publication site

Approved report manifests and map snapshots can be projected into a dependency-light static site:

```bash
python scripts/build_site.py --strict --output _site
python -m http.server 8000 --directory _site
```

The site provides latest-report, archive, report-reader, map, and methodology views. Its build step copies only approved reports and filters map geometry by record status, publication status, embargo time, and snapshot cutoff before any data reaches the browser.

`.github/workflows/deploy-pages.yml` rebuilds and deploys `_site/` to the `github-pages` environment after relevant changes reach `main`, and it can also be run manually through `workflow_dispatch`.

## Start here

1. [`AGENTS.md`](AGENTS.md) — all-the-way-down worker and supervisor contract.
2. [`CHATGPT_PROJECT.md`](CHATGPT_PROJECT.md) — exact multi-chat runtime.
3. [`config/autonomy.json`](config/autonomy.json) — machine-readable cadence, loop, merge, and withholding policy.
4. [`docs/architecture/10-autonomous-runtime.md`](docs/architecture/10-autonomous-runtime.md) — atomic control-loop architecture.
5. [`docs/architecture/11-continuous-loop.md`](docs/architecture/11-continuous-loop.md) — long-running supervisor architecture.
6. [`docs/architecture/12-static-publication-site.md`](docs/architecture/12-static-publication-site.md) — public-site build and publication boundary.
7. [`METHODOLOGY.md`](METHODOLOGY.md) and [`SECURITY_AND_SAFETY.md`](SECURITY_AND_SAFETY.md).

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/validate_data.py
python scripts/validate_worker_queue.py
python scripts/validate_autonomy.py
python scripts/build_site.py --strict --output _site
python scripts/continuous_loop.py --open-worker-prs 0 --active-work-branches 0
```
