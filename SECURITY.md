# Security policy

## Reporting a vulnerability

Do not open a public issue containing credentials, private data, exploitable workflow details, unredacted operational material or a live proof of concept against the deployed collector/site.

Use GitHub private vulnerability reporting for this repository when it is enabled. If private reporting is unavailable, contact the repository owner through a private channel and provide only the minimum information needed to establish impact.

Include:

- affected commit, workflow, path or deployed URL;
- whether public Git history, Pages, Actions artifacts or credentials are affected;
- a minimal reproduction that does not expose third-party private data or current operational locations;
- recommended containment steps;
- whether disclosure should be delayed while credentials/data are removed.

## Initial response

Maintainers should follow `OPERATIONS.md`:

1. disable affected schedules/deployments when continued execution can publish unsafe output;
2. rotate/revoke exposed credentials before discussing details;
3. preserve audit evidence privately;
4. remove unsafe public artifacts/history when required;
5. add a regression test and reviewed fix;
6. resume only after exact-head CI and targeted smoke evidence.

A green latest status does not prove that earlier Git objects, Pages deployments or Actions artifacts are clean.

## Scope

Security-relevant components include:

- GitHub Actions permissions, artifacts and persistence jobs;
- Docker/container privilege boundaries;
- source URL, DNS and redirect handling;
- RSS/web publisher-domain policy;
- X credentials and API handling;
- operational-location classification and embargo;
- public archive projection/redaction;
- Markdown/HTML rendering and outbound links;
- public state/status/error projections;
- retention, correction and history-removal procedures.

## Disclosure

After containment, publish a concise correction or advisory when users may have consumed unsafe or materially incorrect output. Do not repeat the sensitive payload in the advisory.
