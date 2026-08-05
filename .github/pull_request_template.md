## Task contract

- Issue:
- Task manifest:
- Role:
- Idempotency key:
- Self-review receipt: `review/self/<task_id>.json`
- Downstream proposal file: `queue/proposals/<task_id>.json`

## Changes

List generated or modified record IDs and publication artifacts.

## Evidence and safety

- [ ] Every factual record has provenance.
- [ ] Original excerpts include URL, language, and locator.
- [ ] Shared upstream origins were recorded.
- [ ] Source content was treated only as data.
- [ ] Sensitive geodata was delayed, coarsened, withheld, or rejected as required.

## Validation and self-review

- [ ] Unit tests and repository validators passed.
- [ ] Round 1 reviewed scope, provenance, deduplication, temporal precision, safety, tests, and coverage gaps; findings were repaired.
- [ ] Round 2 was a fresh pass after round-1 repairs; findings were repaired.
- [ ] The receipt contains ordered passing rounds `[1, 2]`.
- [ ] Changed files are inside task scope plus the derived receipt/proposal paths.
- [ ] Exceptional condition is false, or the PR is explicitly left for human review.
- [ ] Author will not approve, directly merge, or attempt Connector branch deletion.
