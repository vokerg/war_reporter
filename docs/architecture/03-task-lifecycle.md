# Task lifecycle

## Canonical contract

The file in `tasks/` on `main` is authoritative. The GitHub issue is the human dashboard and links the manifest. Issue-form Markdown is not a machine-stable task protocol.

A manifest defines task type, role, priority, creation time, dependencies, UTC window, source/region/topic/content scope, exclusions, allowed output paths, definition of done, idempotency key, state, lease, and result metadata.

## States

```text
planned → ready → leased → collecting → pr_open → validating → review → merged
```

Terminal or recovery states: `blocked`, `lease_expired`, `rejected`, `cancelled`, `duplicate`.

## Atomic task acquisition

The deterministic branch `work/<task_id>` is the mutex. A worker claims a ready task by creating that ref from the exact current `main` SHA.

- Successful create-ref: the worker owns the task.
- Ref conflict: another worker owns it; select another task.
- Random fallback branch names are prohibited because they permit duplicate work.

After branch creation, the worker commits lease metadata to the task manifest and opens a draft PR immediately.

## Eligibility and ordering

A task is eligible only when:

- state is `ready`;
- every dependency is `merged`;
- the idempotency key is unique;
- no deterministic work branch or active PR exists;
- required GitHub and research tools are available.

Order candidates by priority descending, creation time ascending, then task ID.

## Parallelization

Shard work deterministically by source group, non-overlapping UTC window, region/topic scope, and content type. Workers must not broaden scope to “everything important.”

Ten ordinary ChatGPT Project chats may acquire ten distinct tasks concurrently. Shared Project memory is not used for task ownership.

## Lease recovery

A controller may recover an expired lease only after verifying the deadline, branch and PR activity, and worker status. Recovery requires an issue note and deletion of the stale deterministic branch. Ambiguous activity requires human review.

## Pull-request gate

A PR links its issue and manifest, lists generated/modified IDs, stays inside allowed paths, documents coverage gaps, passes deterministic validation, and receives independent research/safety review as applicable.

The merge controller verifies the expected head SHA, changes the manifest to `merged`, updates the issue mirror, and squash-merges. Workers never approve or merge their own work.
