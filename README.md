# War Reporter

War Reporter is a versioned, evidence-centered OSINT research and publication system. It records assertions, provenance, competing evidence, assessment history, corrections, and publication decisions.

The primary runtime is a ChatGPT Project with parallel worker chats. The routine atomic command is:

```text
копай
```

One invocation is enough to check repository duties, create or promote necessary tasks, claim one task, complete it, self-review it twice, and hand it to automatic exact-head squash merge. The operator does not need to know the internal queue or role topology.

The long-running supervisor command is:

```text
continuous loop
```

Aliases are `continuous-loop`, `копай непрерывно`, and `непрерывный цикл`. This mode repeats the complete `копай` lifecycle. It waits for the current task's actual squash merge and post-merge finalization on `main`, refreshes repository state, consumes any newly materialized proposals, and claims the next eligible task. It does not voluntarily finish after one task or one empty queue scan.

## Autonomous control loop

- `tasks/**/*.json` on `main` is the canonical queue.
- `work/<task_id>` is the atomic worker lock.
- `control/reconcile/<UTC-hour>` is the duty-controller lock.
- `queue/proposals/<task_id>.json` reproduces downstream work after merges.
- `review/self/<task_id>.json` records two separate self-review rounds.
- `scripts/continuous_loop.py` provides a deterministic supervisor decision engine.
- `reconcile-queue.yml` runs hourly and after merges.
- `auto-merge-reviewed.yml` squash-merges exact CI-green reviewed worker heads.
- `finalize-task-merge.yml` records actual merge metadata and closes tasks.
- Workers ignore Connector branch-deletion limitations; cleanup is controller-owned and non-blocking.

Daily discovery is automatic across ten configured source shards. Daily snapshots are automatic when their full window is complete. Weekly and monthly snapshots are on-demand.

## Start here

1. [`AGENTS.md`](AGENTS.md) — all-the-way-down worker and supervisor contract.
2. [`CHATGPT_PROJECT.md`](CHATGPT_PROJECT.md) — exact multi-chat runtime.
3. [`config/autonomy.json`](config/autonomy.json) — machine-readable cadence, loop, and merge policy.
4. [`docs/architecture/10-autonomous-runtime.md`](docs/architecture/10-autonomous-runtime.md) — atomic control-loop architecture.
5. [`docs/architecture/11-continuous-loop.md`](docs/architecture/11-continuous-loop.md) — long-running supervisor architecture.
6. [`METHODOLOGY.md`](METHODOLOGY.md) and [`SECURITY_AND_SAFETY.md`](SECURITY_AND_SAFETY.md).

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/validate_data.py
python scripts/validate_worker_queue.py
python scripts/validate_autonomy.py
python scripts/continuous_loop.py --open-worker-prs 0 --active-work-branches 0
```

## Explicit human-review boundary

Routine bounded work should complete without human intervention. Human review remains mandatory for source-identity ambiguity, legal/rights uncertainty, sensitive-geodata release, released corrections, credential/security-boundary changes, and other exceptional safety or governance ambiguity.
