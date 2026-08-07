# Operations and incident response

This runbook applies to the public raw-first pipeline. It does not create a second task system.

## Operating states

Read `data/state.json` and the generated `status.json` together.

- `ok`: the selected run completed without known source/configuration degradation;
- `idle`: no source was due under cadence;
- `partial`: at least one source succeeded and at least one source/configuration path degraded;
- `blocked`: required configuration prevented the selected run from starting;
- `failed`: attempted sources produced no successful result;
- stale status: the latest state is older than `status_stale_after_hours`.

Only `ok` and understood `idle` are clean. A zero-item `ok` run may still be legitimate embargo; inspect withholding counters before treating it as data loss.

## Failed scheduled collection

1. Stop repeated writes before debugging if the failure can corrupt or republish unsafe data:
   - disable the `Collect OSINT` workflow in GitHub Actions, or temporarily remove its schedule in a reviewed PR;
   - do not delete `data/state.json` to make the dashboard green.
2. Inspect the failed run, `data/state.json`, the safe `data/errors/` categories and the persistence job separately.
3. Classify the failure:
   - adapter/source failure;
   - missing X configuration;
   - validator/publication-policy rejection;
   - malformed existing NDJSON;
   - artifact/persistence/push conflict;
   - Actions/Pages infrastructure failure.
4. Reproduce with the smallest source set and `--force` in a disposable checkout. Do not run all 149 execution sources while diagnosing one adapter.
5. Add a regression test before changing the collector or validator.
6. Re-enable the schedule only after exact-head CI and a targeted smoke pass.

Never edit a malformed NDJSON file in place while the scheduled collector is running. Stop collection, repair through a reviewed branch, run validation, then resume.

## Rollback

For ordinary code/config regressions:

1. disable scheduled collection and Pages deployment if continued execution can publish bad output;
2. identify the last reviewed clean commit and the commits that introduced the regression;
3. create a revert PR—do not force-push `main`;
4. run validator, full tests, targeted source smoke, report build and site build on the revert head;
5. merge only after reviewing generated public output;
6. re-enable schedules and confirm a clean state/status artifact.

For public-data safety incidents, use the removal procedure below instead of relying on a normal revert: a revert leaves the material in Git history.

## X credential rotation

`X_BEARER_TOKEN` is the only long-lived collector credential expected by this repository.

1. disable scheduled collection and the opt-in X smoke job;
2. revoke or rotate the credential at the provider;
3. replace the GitHub Actions secret—never commit or paste it into issues, logs, state, artifacts or PR descriptions;
4. inspect recent Actions logs/artifacts and repository history for accidental disclosure;
5. run the opt-in X smoke against one watched account and `x-discovery-1`;
6. re-enable X coverage only after both paths return inspected non-empty evidence.

GitHub-provided `GITHUB_TOKEN` is run-scoped. If a repository/app token is suspected compromised, revoke the app/token, inspect audit logs and workflow changes, and reinstall/re-authorize only after review.

## Repository or workflow compromise

1. disable all Actions workflows and Pages deployment;
2. revoke external app/token access and rotate repository secrets;
3. preserve audit logs and failed-run metadata; do not publish raw secrets in a public incident issue;
4. inspect changes to `.github/workflows/`, dependency files, Docker files, source registry, schemas and publication-policy code;
5. compare the public archive/status output before and after the suspected compromise;
6. restore through a reviewed commit from a known clean base;
7. require exact-head hosted CI and targeted live smoke before resuming schedules;
8. publish a concise public incident/correction note when reader-visible output was affected, without repeating sensitive material.

## Public data correction and takedown

Use this for operational safety, privacy, copyright, platform-policy or factual-attribution corrections.

1. disable scheduled collection and Pages deployment when the source can immediately reintroduce the material;
2. identify every affected item ID, UTC partition, digest day, generated page and commit;
3. decide whether the source/adapter also requires disabling or a stronger tag/embargo;
4. remove or replace the affected public rows in a dedicated PR and regenerate all derived reports/site output;
5. add a regression test or source-policy change that prevents reintroduction;
6. record the correction in the PR/commit message and a reader-visible correction mechanism once #130 defines it;
7. run validator, full suite and site/report builds before merging;
8. for material that must disappear from Git history, rotate/revoke any exposed credential first, then coordinate a repository-history purge and cache/support request with GitHub. Treat history rewriting as an incident operation requiring maintainer coordination, not a normal correction;
9. verify raw Git URLs, Pages, Actions artifacts and any mirrors/caches after removal;
10. re-enable collection only after a targeted source smoke confirms the new policy.

A normal delete/revert does not erase earlier Git objects or downloaded artifacts.

## Source removal or disabling

1. establish that the source is dead, unsafe, duplicated or outside policy using repeated health evidence—not one transient failure;
2. update `config/sources.json` and any source-specific delay/allowlist entries in the same PR;
3. update minimum group coverage when removal changes an intentional coverage floor;
4. run registry contracts and a replacement-source smoke when applicable;
5. document the coverage impact. Never silently preserve the configured count by adding an unverified replacement.

## Branch protection and review

Before calling the system production-ready, protect `main` with:

- required pull requests and at least one review;
- required exact-head CI checks;
- dismissal of stale approvals after new commits;
- no direct pushes or force pushes;
- restricted workflow changes;
- required resolution of review threads.

Repository settings are external to Git and must be verified in the GitHub UI/API; the presence of a workflow file does not prove enforcement.

## Dependency updates

Dependabot may open weekly PRs for Python, GitHub Actions and Docker dependencies. It must not auto-merge.

For each update:

1. inspect upstream release/security notes;
2. verify action/image publisher and provenance;
3. run exact-head tests, validator, builds and representative smoke;
4. inspect generated archive/status/site diffs;
5. merge one coherent dependency group at a time;
6. revert through a PR if runtime/source behavior changes unexpectedly.

Exact version pins without package hashes do not provide fully reproducible installs. The decision to adopt a hash-locked requirements workflow remains in production gate #2.

## Post-incident evidence

After any operational incident, record:

- first/last affected time;
- affected sources, partitions and outputs;
- whether unsafe data reached Git history, Pages or artifacts;
- containment, removal and credential actions;
- tests/policy changes added;
- exact clean commit and hosted/smoke evidence used to resume.

Do not mark an incident resolved merely because the latest status is green.
