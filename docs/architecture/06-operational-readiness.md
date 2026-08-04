# Operational readiness

The repository is not ready for continuous autonomous collection until all items below have owners and tests.

## Required platform controls

- Protect `main`; require PRs, independent approval, CODEOWNERS, passing validation, linear history, and stale-review dismissal.
- Create repository labels referenced by issue forms before adding those labels to templates.
- Keep agents manually invoked and least-privileged.
- Configure approved research MCP/API connectors separately from coding-agent tools.
- Enable secret scanning, dependency alerts, and private vulnerability reporting where available.

## Required services

- External scheduler and durable queue with leases, retries, dead-letter handling, and worker heartbeats.
- Operational database for idempotency, deduplication, canonical URLs, platform IDs, and provenance lineage.
- Content-addressed object storage with malware quarantine, retention rules, access controls, and backups.
- Monitoring for scan coverage, source failures, queue age, duplicate rate, validator failures, publication latency, and cost.

## Release gates

Before public deployment, define geodata delay/coarsening thresholds, legal review policy, quote limits, source-removal and privacy procedures, correction severity, backup/restore tests, disaster recovery, and public methodology versioning.

## Explicit non-guarantees

A green CI run does not establish truth, neutrality, completeness, source authenticity, legality, or absence of operational harm.
