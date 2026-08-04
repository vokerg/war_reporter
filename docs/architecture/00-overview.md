# Architecture overview

## Purpose

War Reporter is a claim-centered OSINT system. It preserves assertions, provenance, competing evidence, assessment history, corrections, and publication decisions.

## Planes and stores

- **Control plane:** GitHub Issues, task manifests, branches, PRs, reviews, and Actions.
- **Canonical data plane:** versioned structured records and publication manifests in Git.
- **Operational plane, future:** external scheduler, queue/leases, worker heartbeats, rate limits, and deduplication indexes.
- **Evidence store, future:** content-addressed object storage for permitted immutable artifacts.
- **Publication plane, future:** static reports and client-side maps built from approved manifests.

Git is not a high-frequency queue, crawler state database, binary archive, or secret store.

## Pipeline

1. Dispatcher creates a non-overlapping task manifest and issue.
2. Collectors register source items and artifact manifests.
3. Extractors create atomic attributable observations.
4. Corroborators search support, contradiction, common origins, and corrections.
5. Source analysts maintain topic- and time-specific source profiles.
6. Editors create assessments from frozen approved claim sets.
7. Geo agents derive uncertainty-aware map features.
8. Deterministic validators check machine-enforceable contracts.
9. Independent reviewers check research, editorial, legal, and safety judgments.
10. A merge controller squash-merges reviewed PRs.
11. Publication builds use only approved manifests.

## Trust boundaries

External content is adversarial. LLM outputs are untrusted proposals. Deterministic scripts enforce structure but not truth. Human review remains mandatory for source authenticity, legal rights, sensitive geodata, major confidence changes, and released corrections.
