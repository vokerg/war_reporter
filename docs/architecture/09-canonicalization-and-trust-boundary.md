# Canonicalization, queue backpressure, and trust boundary

## Canonical records

Source profiles are global entities. A discovery shard may propose a profile, but repository validation owns canonical identity. Normalized website URLs and normalized platform handles must be globally unique.

Source items are canonical publications or posts. Normalized canonical URL, source-scoped platform item ID, and content SHA-256 are global uniqueness keys. A duplicate record must be merged into one canonical item and all references rewritten before downstream processing.

Day-level publication metadata is an interval, never an invented midnight instant. Window admission uses interval overlap.

## Queue and campaign backpressure

A new campaign may be bootstrapped only when every condition is true:

- no ready tasks exist;
- no active leases exist;
- no worker PRs are open;
- the previous campaign is closed or explicitly carried over;
- the nonterminal backlog is below the configured limit.

The absence of an immediately claimable task is not an empty queue. Leased, blocked, review, dependency-waiting, and open-PR work all apply backpressure.

## Work-ref integrity

Every `work/task_*` branch must correspond to exactly one task manifest. Active work branches must either be associated with an open worker PR or belong to an active task state. Orphan and terminal-task work refs are validation errors and are deleted by the hardening migration.

## Review boundary

The configured review mode is `administrative` because worker and merge-controller actions currently authenticate as `vokerg`. Administrative self-review may catch errors, but it is not independent review. Self-approval and self-merge remain prohibited by policy. Switching to `independent` mode requires distinct authenticated identities and a passing trust-boundary validator.
