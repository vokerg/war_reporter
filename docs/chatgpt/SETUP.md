# ChatGPT Project setup

1. Create a ChatGPT Project and paste `PROJECT_INSTRUCTIONS.md` into Project Instructions.
2. Connect GitHub with issue, branch, file, PR, CI-read, and PR-merge capabilities. Workers do not need Connector delete-ref.
3. Connect approved web/search tools for research tasks.
4. Create several ordinary worker chats and send each `копай`.

No campaign bootstrap or next-layer command is required for routine operation. Hourly/post-merge workflows and every worker invocation reconcile duties automatically.

Repository Actions must be permitted to read/write contents, issues, and pull requests for the controller workflows. Routine worker PRs are squash-merged only after two review rounds and exact-head validation.

Human intervention is reserved for exceptional safety/governance conditions or missing platform permissions.
