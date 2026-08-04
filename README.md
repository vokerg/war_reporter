# War Reporter

A versioned, evidence-centered OSINT research and publication system.

The repository is the canonical audit log and publication source. GitHub Issues coordinate bounded research tasks; agents submit isolated pull requests; structured claims, provenance, map features, and bilingual reports are validated before publication.

## Architecture

Start with:

1. [`AGENTS.md`](AGENTS.md) — agent routing and repository rules.
2. [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) — system boundaries.
3. [`METHODOLOGY.md`](METHODOLOGY.md) — evidence and confidence policy.
4. [`SECURITY_AND_SAFETY.md`](SECURITY_AND_SAFETY.md) — sensitive geodata rules.
5. [`docs/architecture/03-task-lifecycle.md`](docs/architecture/03-task-lifecycle.md) — issue/PR workflow.

## Repository layers

- `catalogs/` — source, region, topic, and terminology registries.
- `data/` — source items, observations, claims, events, reactions, and provenance.
- `maps/` — versioned GeoJSON and snapshot manifests.
- `reports/` — English primary reports and Russian translations.
- `schemas/` — machine-enforced data contracts.
- `.github/agents/` — role-specific agent instructions.
- `.github/ISSUE_TEMPLATE/` — structured task contracts.

## Current status

Architecture foundation only. Collectors, dispatcher, website, and production scheduler are intentionally deferred until the data contracts and review gates stabilize.
