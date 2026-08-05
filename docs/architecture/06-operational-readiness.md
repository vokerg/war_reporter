# Operational readiness

The repository contains an operator-triggered self-sustaining control loop using GitHub Actions. It is suitable for bounded, manually launched parallel chats and hourly duty reconciliation.

Required repository settings:

- Actions may write contents, issues, and pull requests for controller workflows.
- Validation workflow runs on task, review, proposal, schema, script, and workflow changes.
- Squash merge is enabled.
- Secret scanning and dependency alerts are enabled where available.
- Approved research connectors remain separate from repository-control credentials.

Human review is exceptional rather than routine, but remains mandatory for the classes in `config/autonomy.json`.

A green run does not establish truth, neutrality, source authenticity, legality, completeness, or absence of operational harm.
