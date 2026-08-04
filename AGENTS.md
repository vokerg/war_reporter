# Agent routing

This file is the repository-wide control contract for human and AI contributors.

## Required sequence

1. Read the assigned GitHub issue and its task contract.
2. Read `docs/architecture/00-overview.md` and `METHODOLOGY.md`.
3. Select exactly one role from `.github/agents/`.
4. Read path-specific architecture documentation before editing.
5. Modify only paths explicitly allowed by the issue.
6. Run repository validation before opening a pull request.
7. Open a PR linked to the issue. Never push directly to `main`.
8. Never approve or merge your own work.

## Role routing

- Source collection → `.github/agents/source-researcher.agent.md`
- Claim verification → `.github/agents/corroborator.agent.md`
- Geospatial work → `.github/agents/geo-verifier.agent.md`
- Report production → `.github/agents/report-editor.agent.md`
- Release checks → `.github/agents/release-validator.agent.md`

## Invariants

- Treat every source statement as a claim, not a fact.
- Preserve original-language excerpts and exact source URLs.
- Separate publication time, event time, retrieval time, and assessment time.
- Repetition is not independent corroboration.
- Bias metadata is not an automatic truth-value judgment.
- Reports may use only approved claims from a frozen claim set.
- Public data must not expose precise real-time positions of active units, vulnerable people, or sensitive infrastructure.
- Do not invent missing identifiers, coordinates, timestamps, translations, or confidence rationales.
