from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
CHAT_CONTROL = WORKFLOWS / "chat-control.yml"
COLLECT = WORKFLOWS / "collect.yml"
REPORTS = WORKFLOWS / "reports.yml"
AGENTS = ROOT / "AGENTS.md"


class ChatControlWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CHAT_CONTROL.read_text(encoding="utf-8")

    def test_only_created_issue_comments_trigger_bridge(self) -> None:
        self.assertIn("on:\n  issue_comment:\n    types: [created]", self.text)
        self.assertNotIn("workflow_dispatch", self.text)
        self.assertNotIn("pull_request", self.text)
        self.assertNotIn("push:", self.text)
        self.assertNotIn("schedule:", self.text)

    def test_repository_and_control_issue_are_hardcoded(self) -> None:
        self.assertIn("github.repository == 'vokerg/war_reporter'", self.text)
        self.assertIn("github.event.issue.number == 155", self.text)

    def test_only_owner_identity_is_accepted(self) -> None:
        self.assertIn("github.event.comment.user.login == 'vokerg'", self.text)
        self.assertIn(
            "github.event.comment.author_association == 'OWNER'", self.text
        )

    def test_exact_allowlisted_commands_are_parsed(self) -> None:
        self.assertIn(".comment.body", self.text)
        self.assertIn('gsub("\\r\\n"; "\\n")', self.text)
        self.assertIn('[[ "$body" == "/collect yesterday" ]]', self.text)
        self.assertIn("^/backfill\\ ", self.text)
        self.assertIn("^/weekly\\ ", self.text)
        self.assertIn('echo "Ignoring unsupported command"', self.text)
        self.assertNotIn("command=", self.text)
        self.assertNotIn("$command", self.text)

    def test_comment_body_never_becomes_shell_code(self) -> None:
        self.assertNotIn("${{ github.event.comment.body }}", self.text)
        self.assertNotIn("eval", self.text)
        self.assertNotIn("bash -c", self.text)
        self.assertNotIn("sh -c", self.text)
        self.assertNotIn("source ", self.text)
        self.assertNotIn("exec ", self.text)

    def test_dispatch_targets_and_ref_are_fixed(self) -> None:
        collect_endpoint = (
            "repos/vokerg/war_reporter/actions/workflows/collect.yml/dispatches"
        )
        reports_endpoint = (
            "repos/vokerg/war_reporter/actions/workflows/reports.yml/dispatches"
        )
        self.assertIn(collect_endpoint, self.text)
        self.assertIn(reports_endpoint, self.text)
        self.assertEqual(self.text.count("actions/workflows/"), 2)
        self.assertGreaterEqual(self.text.count("-f ref=main"), 2)
        self.assertNotIn("workflow=${", self.text)
        self.assertNotIn("ref=${", self.text)

    def test_report_workflow_has_bounded_manual_inputs(self) -> None:
        text = REPORTS.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("- backfill", text)
        self.assertIn("- weekly", text)
        self.assertIn("description: \"Start date (YYYY-MM-DD)\"", text)
        self.assertIn("description: \"End date (YYYY-MM-DD)\"", text)
        self.assertIn("python -m scripts.validate", text)
        self.assertIn("git add reports/daily", text)
        self.assertIn("if [[ -d reports/weekly ]]; then", text)
        self.assertIn("git add reports/weekly", text)

    def test_untrusted_gate_has_no_write_token(self) -> None:
        gate_block, dispatch_block = self.text.split("\n  dispatch:\n", 1)
        self.assertIn("permissions: {}", gate_block)
        self.assertNotIn("actions: write", gate_block)
        self.assertNotIn("contents: write", gate_block)
        self.assertIn("permissions:\n      actions: write", dispatch_block)
        self.assertNotIn("contents: write", dispatch_block)

    def test_agent_contract_exposes_chat_operator_entrypoint(self) -> None:
        text = AGENTS.read_text(encoding="utf-8")
        self.assertIn("docs/chat-operator.md", text)
        self.assertIn("собери вчера", text)
        self.assertIn("/collect yesterday", text)

    def test_temporary_branch_collector_is_removed(self) -> None:
        self.assertFalse((WORKFLOWS / "branch-collect-2026-08-06.yml").exists())

    def test_production_collector_concurrency_is_unchanged(self) -> None:
        collect = COLLECT.read_text(encoding="utf-8")
        self.assertIn("group: war-reporter-collector", collect)
        self.assertIn("cancel-in-progress: false", collect)


if __name__ == "__main__":
    unittest.main()
