# Continuous Loop supervisor

## Objective

`continuous loop` is a supervisor command above the atomic `копай` worker protocol. It minimizes operator involvement by executing complete task lifecycles sequentially until the repository reaches proven quiescence.

The supervisor does not weaken atomic ownership, review, scope, or merge controls. It composes them.

## Supervisor state machine

```text
START
  -> refresh current main
  -> evaluate repository duties
     -> duties due: reconcile, merge control-plane result, refresh main
  -> select eligible task
     -> task available: atomically create work/<task_id>
     -> no task but nonterminal/in-flight work exists: WAIT
     -> no work visible: QUIESCENCE SWEEP
  -> execute exactly one bounded task
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

## Iteration boundary

A loop iteration is complete only when all of the following are true:

1. the worker task is complete;
2. both self-review rounds pass;
3. the exact reviewed head passes CI;
4. the controller squash-merges that exact head;
5. `finalize-task-merge.yml` records the real merge SHA and timestamp on `main`;
6. reconciliation has had an opportunity to materialize downstream proposals;
7. the supervisor has refreshed `main`.

A pre-materialized `planned` daily report may omit `report_inputs` while its dependencies are unfinished. Reconciliation must freeze an approved claim/assessment set and persist its deterministic hash in the task before promotion to `ready`; without such inputs the task remains planned.

Opening or readying a PR is not the iteration boundary. Claiming another task before finalization could hide spawned work and would violate the supervisor contract.

## Concurrency

`continuous loop` uses no global worker monopoly. It relies on the existing deterministic task mutex:

```text
work/<task_id>
```

Multiple ordinary `копай` workers and one or more Continuous Loop supervisors can coexist. Branch creation conflict means another worker owns that task; the supervisor must refresh and select another eligible task or wait.

A supervisor processes one task at a time. Parallelism remains available through separate chats using `копай`.

## Spawn closure

Every valid proposal written by a task completed during the loop belongs to the same supervisor scope after the producer merges. The supervisor must not stop between producer merge and proposal reconciliation.

The closure is transitive: a spawned task may itself spawn more tasks, and those tasks remain in scope until no valid downstream work is materialized.

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
- no eligible task;
- no nonterminal task manifest;
- no open worker PR;
- no active deterministic work branch;
- no exceptional PR;
- no reconciliation blocker that can still clear;
- no scheduled daily boundary inside `scheduled_duty_guard_seconds`;
- at least `minimum_idle_sweeps` consecutive unchanged idle observations;
- at least `minimum_idle_window_seconds` elapsed since the first idle observation.

Any state change resets the idle proof.

`scripts/continuous_loop.py` is the reference decision engine and returns `reconcile`, `claim`, `wait`, `human_gate`, or `quiescent`.

## Exceptional and forced termination

`human_gate` remains mandatory for the configured safety and governance exceptions. Continuous mode does not convert exceptional work into self-approved work.

A platform runtime limit, connector failure, revoked credential, or tool interruption is not quiescence. The supervisor must classify it as `continuation_required` and preserve the last observed task/merge state in its final report. A truly unattended daemon still requires an external runner capable of starting or resuming agent sessions; this repository change defines the deterministic contract that such a runner must follow.

## Configuration

`config/autonomy.json` defines:

- command and aliases;
- the atomic child command;
- mandatory wait for merge and finalization;
- refresh and spawn-closure behavior;
- merge and idle polling;
- idle sweep and elapsed-time thresholds;
- the near-term scheduled-duty guard;
- the rule that forced interruption is not quiescence.

The schema makes the safety-critical properties constants so a configuration change cannot silently weaken the supervisor contract.
