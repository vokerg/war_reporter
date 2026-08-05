#!/usr/bin/env python3
"""Validate the self-sustaining runtime and two-round self-review receipts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_OUTPUT_PREFIXES = ("catalogs/", "data/", "maps/", "raw-manifests/", "reports/")
REQUIRED_RUNTIME_FILES = (
    "config/autonomy.json",
    "schemas/autonomy.schema.json",
    "schemas/self-review.schema.json",
    "schemas/task-proposal.schema.json",
    "scripts/reconcile_repository.py",
    "scripts/finalize_merged_task.py",
    "scripts/validate_pr_scope.py",
    ".github/workflows/auto-merge-reviewed.yml",
    ".github/workflows/finalize-task-merge.yml",
    ".github/workflows/reconcile-queue.yml",
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def schema_errors(value: Any, schema: Any, path: Path) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in validator.iter_errors(value):
        field = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{path}: {field}: {error.message}")
    return errors


def validate_auto_merge_trust_boundary(root: Path) -> list[str]:
    auto_path = root / ".github/workflows/auto-merge-reviewed.yml"
    finalizer_path = root / ".github/workflows/finalize-task-merge.yml"
    try:
        auto_text = auto_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"auto-merge workflow unavailable: {exc}"]
    try:
        finalizer_text = finalizer_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"finalizer workflow unavailable: {exc}"]

    auto_required_markers = (
        "ref: main",
        "path: trusted",
        "path: pr-head",
        "python trusted/scripts/validate_autonomy.py",
        "python trusted/scripts/validate_pr_scope.py",
        "validated_sha",
        "commits/$validated_sha/pulls",
        "candidate_count",
        "actions: write",
        "gh workflow run finalize-task-merge.yml",
        "-f pr_number=",
        "-f merge_sha=",
        "-f merged_at=",
        "-f head_ref=",
    )
    finalizer_required_markers = (
        "workflow_dispatch:",
        "FINALIZE_PR_NUMBER:",
        "FINALIZE_MERGE_SHA:",
        "FINALIZE_MERGED_AT:",
        "FINALIZE_HEAD_REF:",
    )
    errors = [
        f"{auto_path}: missing trusted-controller marker: {marker}"
        for marker in auto_required_markers
        if marker not in auto_text
    ]
    errors.extend(
        f"{finalizer_path}: missing dispatch-finalizer marker: {marker}"
        for marker in finalizer_required_markers
        if marker not in finalizer_text
    )
    unsafe_markers = (
        "python scripts/validate_autonomy.py",
        "python scripts/validate_pr_scope.py",
    )
    for marker in unsafe_markers:
        if marker in auto_text:
            errors.append(f"{auto_path}: write-capable controller may not execute validator from PR head: {marker}")
    return errors


def validate_config(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_RUNTIME_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing autonomous runtime file: {relative}")
    try:
        config_path = root / "config/autonomy.json"
        config = load(config_path)
        schema = load(root / "schemas/autonomy.schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"autonomy configuration unavailable: {exc}"]
    errors.extend(schema_errors(config, schema, config_path))
    errors.extend(validate_auto_merge_trust_boundary(root))
    if config.get("self_review", {}).get("required_rounds") != 2:
        errors.append("autonomy requires exactly two self-review rounds")
    if config.get("reports") != {"daily": "automatic", "weekly": "on_demand", "monthly": "on_demand"}:
        errors.append("report cadence must be daily automatic and weekly/monthly on-demand")
    cleanup = config.get("branch_cleanup", {})
    if cleanup.get("workers_must_not_attempt_connector_deletion") is not True:
        errors.append("workers must be told not to attempt branch deletion through the connector")
    controller = config.get("merge_controller", {})
    if controller.get("enabled") is not True or controller.get("strategy") != "squash":
        errors.append("administrative merge controller must be enabled with squash strategy")
    if controller.get("worker_direct_merge_allowed") is not False:
        errors.append("workers may not directly merge; only the controller may merge after attestation")
    try:
        trust = load(root / "config/trust-boundary.json")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"trust boundary unavailable: {exc}")
    else:
        if trust.get("self_approval_allowed") is not False or trust.get("self_merge_allowed") is not False:
            errors.append("direct self-approval/self-merge must remain disabled")
    return errors


def validate_receipt(
    root: Path,
    receipt_path: Path,
    *,
    expected_task_id: str | None = None,
    expected_pr_number: int | None = None,
    require_automerge_eligible: bool = False,
) -> list[str]:
    errors: list[str] = []
    try:
        receipt = load(receipt_path)
        schema = load(root / "schemas/self-review.schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"self-review receipt unavailable: {exc}"]
    errors.extend(schema_errors(receipt, schema, receipt_path))
    if errors:
        return errors
    task_id = receipt["task_id"]
    if expected_task_id and task_id != expected_task_id:
        errors.append(f"{receipt_path}: task_id {task_id} does not match {expected_task_id}")
    if expected_pr_number is not None and receipt["pr_number"] != expected_pr_number:
        errors.append(f"{receipt_path}: pr_number {receipt['pr_number']} does not match {expected_pr_number}")
    rounds = receipt["rounds"]
    if [item["round"] for item in rounds] != [1, 2]:
        errors.append(f"{receipt_path}: rounds must be ordered exactly [1, 2]")
    if any(item["outcome"] != "pass" for item in rounds):
        errors.append(f"{receipt_path}: both self-review rounds must pass")
    try:
        if parse_time(rounds[1]["reviewed_at"]) <= parse_time(rounds[0]["reviewed_at"]):
            errors.append(f"{receipt_path}: round 2 must occur after round 1")
    except ValueError as exc:
        errors.append(f"{receipt_path}: invalid reviewed_at: {exc}")
    required = set(load(root / "config/autonomy.json")["self_review"]["required_checks"])
    for item in rounds:
        missing = sorted(required - set(item["checks"]))
        if missing:
            errors.append(f"{receipt_path}: round {item['round']} missing checks: {', '.join(missing)}")
    if require_automerge_eligible and receipt.get("exceptional_condition") is True:
        errors.append(f"{receipt_path}: exceptional condition requires human review: {receipt.get('exceptional_reason')}")
    return errors


def proposal_output_allowed(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PROPOSAL_OUTPUT_PREFIXES)


def validate_proposals(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        config = load(root / "config/autonomy.json")
        schema = load(root / "schemas/task-proposal.schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"proposal configuration unavailable: {exc}"]
    allowed_types = set(config["queue"]["allowed_proposal_task_types"])
    proposal_root = root / config["queue"]["proposal_root"]
    if not proposal_root.exists():
        return errors
    for path in sorted(proposal_root.rglob("*.json")):
        try:
            value = load(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        errors.extend(schema_errors(value, schema, path))
        for proposal in value.get("proposals", []) if isinstance(value, dict) else []:
            task_type = proposal.get("task_type")
            if task_type not in allowed_types:
                errors.append(f"{path}: proposed task_type {task_type} is not autonomously allowed")
            for output in proposal.get("allowed_output_paths", []):
                if not proposal_output_allowed(str(output)):
                    errors.append(f"{path}: proposal output must remain in a data-plane root: {output}")
    return errors


def validate_all(root: Path) -> list[str]:
    errors = validate_config(root)
    receipt_root = root / "review/self"
    if receipt_root.exists():
        for path in sorted(receipt_root.rglob("*.json")):
            errors.extend(validate_receipt(root, path))
    errors.extend(validate_proposals(root))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--task-id")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--require-automerge-eligible", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.receipt:
        receipt = args.receipt if args.receipt.is_absolute() else root / args.receipt
        errors = validate_config(root)
        errors.extend(validate_receipt(
            root,
            receipt,
            expected_task_id=args.task_id,
            expected_pr_number=args.pr_number,
            require_automerge_eligible=args.require_automerge_eligible,
        ))
    else:
        errors = validate_all(root)
    if errors:
        print("Autonomous runtime validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Autonomous runtime validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
