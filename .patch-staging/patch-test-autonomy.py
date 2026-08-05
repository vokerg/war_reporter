from pathlib import Path

path = Path("tests/test_autonomy.py")
text = path.read_text(encoding="utf-8")
old = '''    def test_reconciler_creates_daily_discovery_and_snapshot(self) -> None:
        root = self.make_root()
        now = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
        plan = plan_duties(root, now)
        self.assertEqual([d["kind"] for d in plan["duties"]], ["discovery_campaign"])
        result = apply_plan(root, plan, parent_issue=12)
        self.assertEqual(len(result["created_task_ids"]), 10)
        tasks = task_index(root)
        for path, task in tasks.values():
            task["state"] = "merged"
            task["lease"] = None
            task["result"] = {"branch": f"work/{task['task_id']}", "pr_number": 1, "merge_sha": "a" * 40, "merged_at": "2026-08-07T08:00:00Z", "completed_at": "2026-08-07T08:00:00Z"}
            dump(path, task)
        snapshot_plan = plan_duties(root, now)
        self.assertIn("daily_snapshot", [d["kind"] for d in snapshot_plan["duties"]])
'''
new = '''    def test_reconciler_creates_daily_discovery_and_snapshot(self) -> None:
        root = self.make_root()
        now = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
        plan = plan_duties(root, now)
        self.assertEqual([d["kind"] for d in plan["duties"]], ["discovery_campaign"])
        result = apply_plan(root, plan, parent_issue=12)
        self.assertEqual(len(result["created_task_ids"]), 10)
        tasks = task_index(root)
        for path, task in tasks.values():
            task["state"] = "merged"
            task["lease"] = None
            task["result"] = {"branch": f"work/{task['task_id']}", "pr_number": 1, "merge_sha": "a" * 40, "merged_at": "2026-08-07T08:00:00Z", "completed_at": "2026-08-07T08:00:00Z"}
            dump(path, task)

        assessment_plan = plan_duties(root, now)
        assessment_kinds = [d["kind"] for d in assessment_plan["duties"]]
        self.assertNotIn("daily_snapshot", assessment_kinds)
        self.assertIn("report_input_assessment", assessment_kinds)
        assessment_result = apply_plan(root, assessment_plan)
        assessment_task_id = "task_daily_20260806_80_report_inputs"
        self.assertEqual(assessment_result["created_task_ids"], [assessment_task_id])

        dump(root / "data/claims/2026/08/06/clm_fixture.json", {
            "claim_id": "clm_fixture",
            "record_status": "approved",
            "event_time": {"start": "2026-08-06T12:00:00Z", "precision": "hour"},
        })
        assessment_path, assessment_task = task_index(root)[assessment_task_id]
        assessment_task["state"] = "merged"
        assessment_task["lease"] = None
        assessment_task["result"] = {"branch": f"work/{assessment_task_id}", "pr_number": 2, "merge_sha": "b" * 40, "merged_at": "2026-08-07T09:00:00Z", "completed_at": "2026-08-07T09:00:00Z"}
        dump(assessment_path, assessment_task)

        snapshot_plan = plan_duties(root, now)
        snapshot = next(d for d in snapshot_plan["duties"] if d["kind"] == "daily_snapshot")
        self.assertEqual(snapshot["report_inputs"]["claim_ids"], ["clm_fixture"])
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one legacy autonomy test block, found {count}")
path.write_text(text.replace(old, new), encoding="utf-8")
