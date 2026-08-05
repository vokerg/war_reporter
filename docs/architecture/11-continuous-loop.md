# Continuous Loop supervisor

## Objective

`continuous loop` is a supervisor command above the atomic `копай` worker protocol. It minimizes operator involvement by executing complete task lifecycles sequentially until the repository reaches proven quiescence.

The supervisor does not weaken atomic ownership, review, scope, safety, or merge controls. It composes them and handles uncertain material through automatic withholding rather than a human-review stop.

## Supervisor state machine

```text
START
  -> refresh current main
  -> evaluate repository duties
     -> duties due: reconcile, merge control-plane result, refresh main
  -> select eligible task
     -> ready task available: atomically create work/<task_id>
     -> retired HUMAN_REVIEW_REQUIRED task available: claim as blocked -> leased
     -> no task but nonterminal/in-flight work exists: WAIT
     -> no work visible: QUIESCENCE SWEEP
  -> execute exactly one bounded task
  -> withhold unsafe or unresolved material and record the limitation
  -> tests and validators
  -> self-review round 1 -> repairs
  -> self-review round 2 -> repairs
  -> ready exact-head PR
  -> WAIT FOR CONTROLLER
  -> exact-head squash merge
  -> post-merge finalization on main
  -> refresh main
  -> consume materialized proposals
  -> repeat
```

`scripts/continuous_loop.py` returns only `reconcile`, `claim`, `wait`, or `quiescent`. `human_gate` is retired.

## Iteration boundary

A loop iteration is complete only when all of the following are true:

1. the worker task is complete;
2. both self-review rounds pass;
3. the exact reviewed head passes CI;
4. the controller squash-merges that exact head;
5. `finalize-task-merge.yml` records the real merge SHA and timestamp on `main`;
6. reconciliation has had an opportunity to materialize downstream proposals;
7. the supervisor has refreshed `main`.

Opening or readying a PR is not the iteration boundary. Claiming another task before finalization could hide spawned work and violates the supervisor contract.

## Pickable task set

The normal pickable state is `ready` with all dependencies merged and any canonicalization prerequisite satisfied.

For backward compatibility, a task is also pickable when:

- `state` is `blocked`;
- `blocked_reason` begins with `HUMAN_REVIEW_REQUIRED:`;
- its dependencies are merged;
- downstream canonicalization requirements are satisfied.

The decision payload marks such a task with `retired_human_gate: true` and `claim_transition: blocked_to_leased`. The claimant clears `blocked_reason` while writing lease metadata and preserves the substance of the old blocker as a coverage gap or automatic-withhold note.

## Non-worker and exceptional PR telemetry

Architecture, hardening, and other non-worker PRs are outside the task loop. The compatibility `exceptional_prs` counter remains accepted by the CLI so existing runners do not break, but it is telemetry only. It cannot cause `wait`, prevent `claim`, or block quiescence.

This specifically prevents an unrelated architecture PR from freezing the research queue.

## Automatic withholding

Conditions listed in `merge_controller.automatic_withhold_for` are resolved without operator action. Workers fail closed on the affected material:

- omit ambiguous source attribution;
- omit rights-uncertain copied material;
- withhold, delay, or coarsen sensitive geodata;
- preserve correction history rather than silently replacing released content;
- exclude credential or security-boundary changes from research tasks.

The worker records the limitation, completes the safe bounded remainder, and proceeds through normal self-review. Withholding does not authorize invention, access-control bypass, or unsafe publication.

## Concurrency

`continuous loop` uses no global worker monopoly. It relies on the deterministic task mutex:

```text
work/<task_id>
```

Multiple ordinary `копай` workers and one or more Continuous Loop supervisors can coexist. Branch creation conflict means another worker owns that task; the supervisor refreshes and selects another eligible task or waits.

A supervisor processes one task at a time. Parallelism remains available through separate chats using `копай`.

## Spawn closure

Every valid proposal written by a task completed during the loop belongs to the same supervisor scope after the producer merges. The closure is transitive: a spawned task may itself spawn more tasks, and those tasks remain in scope until no valid downstream work is materialized.

## Waiting behavior

Waiting is an explicit state, not completion. The supervisor waits when:

- a worker PR or `work/<task_id>` branch is still active;
- a task is in `leased`, `collecting`, `pr_open`, `validating`, or `review`;
- planned work is waiting on dependencies;
- ready work is temporarily unclaimable;
- merge/finalization has not appeared on `main`;
- reconciliation is blocked by a temporary repository condition;
- a scheduled daily duty is within the configured guard window;
- the minimum idle proof has not completed.

The supervisor refreshes state at `merge_poll_seconds` while work is in flight and at `idle_poll_seconds` while the repository is otherwise idle.

## Quiescence proof

A single empty queue scan is insufficient. Normal voluntary exit requires all of the following across the configured idle window:

- no due reconciliation duties;
- no eligible task, including no retired-gate candidate;
- no nonterminal task manifest;
- no open worker PR;
- no active deterministic work branch;
- no reconciliation blocker that can still clear;
- no scheduled daily boundary inside `scheduled_duty_guard_seconds`;
- at least `minimum_idle_sweeps` consecutive unchanged idle observations;
- at least `minimum_idle_window_seconds` elapsed since the first idle observation.

Non-worker PRs do not participate in this proof. Any relevant repository-state change resets the idle proof.

## Forced termination

A platform runtime limit, connector failure, revoked credential, or tool interruption is not quiescence. The supervisor classifies it as `continuation_required` and preserves the last observed task/merge state in its final report.

A truly unattended daemon still requires an external runner capable of starting or resuming agent sessions; this repository defines the deterministic contract that such a runner follows.

## Configuration

`config/autonomy.json` defines command aliases, atomic child command, mandatory wait for merge/finalization, refresh and spawn-closure behavior, merge and idle polling, idle proof thresholds, scheduled-duty guard, and automatic-withhold classes.
