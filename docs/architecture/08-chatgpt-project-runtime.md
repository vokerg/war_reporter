# ChatGPT Project runtime

The routine command `копай` executes a complete control loop: duty reconciliation, atomic acquisition, role resolution, bounded execution, proposal persistence, two self-review rounds, and controller handoff.

GitHub is the coordination plane. Manifests are the queue, deterministic branches are mutexes, PRs expose ownership, receipts attest review, proposals reproduce downstream work, and Actions merge/finalize/reconcile.

The worker does not need a separate control chat. Every invocation first checks repository obligations. The hourly workflow catches periods with no active chats.

Branch cleanup is never a worker blocker. Connector delete-ref limitations are ignored by workers and handled by controller retries.
