# Architecture overview

## Purpose

War Reporter is a claim-centered research system. It records what was asserted, by whom, with what evidence, how the assessment changed, and why a public conclusion was produced.

## Control plane

GitHub Issues, dependencies, branches, PRs, reviews, and Actions coordinate bounded work and preserve an audit trail.

## Data plane

The repository contains canonical structured knowledge and publication artifacts. A future operational database may handle leases, deduplication, scheduler state, and worker heartbeats. Large immutable evidence belongs in content-addressed object storage; Git stores manifests and hashes.

## Pipeline

1. Dispatcher creates mutually exclusive task contracts.
2. Collectors create source items and observations.
3. Normalizers make observations atomic and link upstream provenance.
4. Corroborators search supporting and contradicting evidence.
5. Editors build assessments from approved claims only.
6. Geo agents convert approved geospatial claims to uncertainty-aware features.
7. Validators enforce schemas, provenance, editorial rules, and safety.
8. A merge controller squash-merges reviewed PRs.
9. A static-site build publishes reports, claim dossiers, source profiles, and maps.

## Boundaries

Collectors do not write final analysis. Editors do not browse freely. Translators do not change facts. Agents do not merge their own PRs. GitHub Actions are suitable for batch orchestration and validation, not as the sole perpetual scheduler.
