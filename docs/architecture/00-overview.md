# Architecture overview

War Reporter is a claim-centered OSINT system preserving assertions, provenance, competing evidence, assessment history, corrections, and publication decisions.

## Planes

- **Control plane:** GitHub task manifests, issues, deterministic branches, PRs, Actions, self-review receipts, and task proposals.
- **Canonical data plane:** versioned structured records and publication manifests in Git.
- **Evidence boundary:** permitted public-source artifacts and lineage; hostile or restricted content remains quarantined.
- **Publication plane:** reports and maps built only from frozen merged inputs.

## Autonomous pipeline

1. Hourly/post-merge/worker-invocation reconciliation creates due discovery, promotes dependencies, and materializes validated proposals.
2. A worker atomically claims `work/<task_id>`.
3. Role-specific execution persists bounded outputs.
4. The worker writes downstream proposals and completes two separate self-review rounds.
5. Exact-head CI and scope validation gate administrative squash merge.
6. Post-merge finalization records actual merge metadata and closes the issue.
7. Reconciliation advances the next layer and daily snapshot duties.

## Trust boundaries

External content is adversarial. Model outputs and self-review are accountable proposals, not evidence or independent review. Deterministic scripts enforce structure, scope, and workflow invariants but not truth. Human review remains mandatory for configured exceptional safety, legal, identity, correction, and security-boundary cases.
