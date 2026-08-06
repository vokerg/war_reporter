# Source lifecycle

Source IDs are durable provenance identifiers, not disposable configuration rows.

## Add

- Use a stable lowercase ID with the platform suffix when applicable (`-tg`, `-x`, `-rss`, `-web`).
- Record the public HTTPS source URL, platform, group, perspective, trust handling, priority and enabled state.
- Add publisher-domain exceptions only when an observed feed/article relationship requires them.
- Run validator, registry contracts and a targeted smoke before claiming the source works.
- Adding a registry row changes configured coverage only; it does not establish operational availability.

## Disable

When a source is dead, unsafe, duplicated or intentionally excluded, normally set:

```json
"enabled": false
```

Do not delete the row merely to reduce the configured count. Historical archive/error rows retain the source ID and validator requires that provenance to remain resolvable.

In the same PR:

- remove the ID from source-specific delay or publisher allowlist maps when those settings are no longer needed;
- document the coverage impact;
- update group minimums only through an explicit coverage decision;
- inspect `data/state.json`; disabled registry IDs may retain historical health state without becoming orphaned.

## Replace

Create a new source ID instead of silently reusing an old one when:

- publisher/account ownership changes;
- platform changes;
- the canonical domain/account is materially different;
- the source has been replaced by a successor with different editorial identity;
- a feed endpoint changes to a web index or vice versa and historical semantics would become ambiguous.

Disable the old row and add the new row in the same PR. Never rewrite historical records to the new ID merely to make counts look cleaner.

A simple endpoint correction for the same publisher/platform may retain the ID when historical meaning is unchanged; explain the correction in the PR.

## Delete

Delete a registry ID only when all of the following are true:

- no `data/raw/**/items.ndjson` row references it;
- no `data/errors/**/errors.ndjson` row references it;
- no `data/state.json` row references it;
- no source-specific settings or tests reference it;
- the deletion does not erase reader-visible provenance.

Use `python -m scripts.prune_state` to detect stale runtime health rows and `python -m scripts.prune_state --write` to atomically remove them **after** the registry/history decision is reviewed. The command does not alter historical archive or error records.

If historical rows exist, preserve a disabled registry tombstone instead of deleting the ID.

## Trust, group and tag changes

- `trust` is a handling hint, not a truth score.
- A change to trust/group/tags must not be used to retroactively claim corroboration.
- Stored rows preserve their handling fields at collection time; document material policy corrections rather than silently changing historical meaning.
- Stronger safety delays/tags may be applied prospectively without weakening old public records. Review whether already published rows require takedown or further redaction.

## Verification

A source-lifecycle PR should run:

```bash
python -m scripts.prune_state
python -m scripts.validate
python -m unittest discover -s tests -v
python -m scripts.collect --force --lookback-hours 168 --sources <new-or-changed-id>
```

Do not remove the old source or claim the replacement works until exact-head validation and targeted smoke evidence are inspected.
