# War Reporter

War Reporter is a versioned, evidence-centered OSINT research and publication system. It records what was asserted, by whom, which evidence supports or disputes it, how assessments changed, and why a report or map feature was published.

The repository is the canonical audit and publication source. GitHub Issues coordinate bounded work; machine-readable task manifests define scope; agents submit isolated pull requests; deterministic checks validate schemas, identifiers, references, temporal invariants, and selected safety controls.

## Start here

1. [`AGENTS.md`](AGENTS.md) — routing and non-negotiable contributor rules.
2. [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) — components and trust boundaries.
3. [`METHODOLOGY.md`](METHODOLOGY.md) — evidence, source, and assessment methodology.
4. [`SECURITY_AND_SAFETY.md`](SECURITY_AND_SAFETY.md) — operational, privacy, prompt-injection, and publication safety.
5. [`docs/architecture/03-task-lifecycle.md`](docs/architecture/03-task-lifecycle.md) — issue, task-manifest, lease, PR, and merge lifecycle.
6. [`docs/architecture/06-operational-readiness.md`](docs/architecture/06-operational-readiness.md) — controls required before continuous collection.

## Repository layers

- `catalogs/` — source, region, topic, and terminology registries.
- `data/` — source items, artifacts, observations, claims, events, reactions, assessments, corrections, and report manifests.
- `tasks/` — canonical machine-readable task contracts.
- `maps/` — provenance-linked GeoJSON and snapshot manifests.
- `reports/` — English editorial reports and Russian translations.
- `schemas/` — JSON Schema contracts.
- `.github/agents/` — least-privilege role profiles.
- `.github/ISSUE_TEMPLATE/` — human task intake forms.

## Local validation

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/validate_data.py
```

## Current guarantees

The validator currently checks JSON Schemas, unique IDs, core cross-record references, supported GeoJSON geometry, and key time ordering. It does **not** yet prove source authenticity, evidence independence, quote licensing, geolocation correctness, analytical quality, or operational safety. Those require explicit review gates.

## Status

Architecture foundation. Continuous collectors, external research MCP/API integrations, dispatcher leases, operational database, object storage, website, map renderer, and publication automation remain deliberately unimplemented.
