#!/usr/bin/env python3
"""Idempotent hardening migration for canonicalization and queue integrity.

The migration operates only on repository metadata and public-source records. It:
- canonicalizes source profiles by normalized website/handle identity;
- canonicalizes source items by canonical URL, platform ID, or content hash;
- rewrites references across JSON and NDJSON records;
- converts fake day-level midnight timestamps into publication intervals;
- clears leases from non-active task states;
- hydrates merged task results with the actual GitHub merge SHA/timestamp;
- optionally deletes stale/orphan work branches;
- writes a deterministic audit report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATES = {"leased", "collecting", "pr_open", "validating", "review"}
NO_LEASE_STATES = {
    "planned",
    "ready",
    "merged",
    "blocked",
    "lease_expired",
    "rejected",
    "cancelled",
    "duplicate",
}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

PREFERRED_SOURCE_IDS = {
    "src_guardian": "src_the_guardian",
}
PREFERRED_ITEM_IDS = {
    "item_20260804_reuters_ports": "item_20260804_reuters_grain_routes",
    "item_reuters_20260804_ukraine_grain_routes": "item_20260804_reuters_grain_routes",
    "item_20260804_reuters_turkiye_black_sea_safety": "item_reuters_20260804_black_sea_navigation",
    "item_20260804_ap_mutual_drone_attacks_reactions": "item_20260804_ap_drone_strikes",
    "item_20260804_guardian_zaluzhnyi_nato_criticism": "item_20260804_guardian_war_briefing",
}


@dataclass
class StoredRecord:
    path: Path
    container_kind: str
    index: int
    value: dict[str, Any]


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        self.add(left)
        self.add(right)
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            if left_root < right_root:
                self.parent[right_root] = left_root
            else:
                self.parent[left_root] = right_root

    def groups(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for item in self.parent:
            groups[self.find(item)].append(item)
        return {root: sorted(items) for root, items in groups.items()}


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_pairs = [
        (key, val)
        for key, val in query_pairs
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    query = urllib.parse.urlencode(sorted(query_pairs))
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def load_json_or_ndjson(path: Path) -> tuple[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".ndjson":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        return "ndjson", records
    value = json.loads(text)
    if isinstance(value, list):
        return "array", value
    return "object", value


def dump_json_or_ndjson(path: Path, kind: str, value: Any) -> None:
    if kind == "ndjson":
        lines = [json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in value]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_data_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.suffix in {".json", ".geojson", ".ndjson"} and path.is_file():
            yield path


def load_record_collection(root: Path, relative_root: str) -> tuple[list[StoredRecord], dict[Path, tuple[str, Any]]]:
    base = root / relative_root
    records: list[StoredRecord] = []
    documents: dict[Path, tuple[str, Any]] = {}
    if not base.exists():
        return records, documents
    for path in iter_data_files(base):
        kind, value = load_json_or_ndjson(path)
        documents[path] = (kind, value)
        if kind in {"array", "ndjson"}:
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    records.append(StoredRecord(path, kind, index, item))
        elif isinstance(value, dict):
            records.append(StoredRecord(path, kind, 0, value))
    return records, documents


def unique_list(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def pick_preferred_id(ids: list[str], aliases: dict[str, str]) -> str:
    mapped = [aliases.get(item, item) for item in ids]
    candidates = [item for item in mapped if item in ids]
    if candidates:
        return sorted(candidates)[0]
    return sorted(mapped)[0]


def profile_identity_keys(profile: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for website in profile.get("websites", []) if isinstance(profile.get("websites"), list) else []:
        if isinstance(website, str):
            keys.add(f"website:{normalize_url(website)}")
    handles = profile.get("handles")
    if isinstance(handles, dict):
        for platform, handle in handles.items():
            if isinstance(handle, str):
                keys.add(f"handle:{str(platform).casefold()}:{handle.strip().casefold().lstrip('@')}")
    return keys


def merge_profiles(records: list[dict[str, Any]], canonical_id: str) -> dict[str, Any]:
    richest = max(records, key=lambda record: (len(json.dumps(record, sort_keys=True)), record.get("source_entity_id", "")))
    merged = dict(richest)
    merged["source_entity_id"] = canonical_id
    for field in ("aliases", "languages", "websites", "topics", "affiliations", "assessments"):
        values: list[Any] = []
        for record in records:
            candidate = record.get(field)
            if isinstance(candidate, list):
                values.extend(candidate)
        if values or field in merged:
            merged[field] = unique_list(values)
    handles: dict[str, str] = {}
    for record in records:
        candidate = record.get("handles")
        if isinstance(candidate, dict):
            for platform, handle in sorted(candidate.items()):
                handles.setdefault(str(platform), str(handle))
    if handles:
        merged["handles"] = handles
    updated = [record.get("updated_at") for record in records if isinstance(record.get("updated_at"), str)]
    if updated:
        merged["updated_at"] = max(updated)
    merged.setdefault("assessments", [])
    merged.setdefault("record_status", "draft")
    return merged


def item_identity_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    url = item.get("canonical_url")
    if isinstance(url, str):
        keys.add(f"url:{normalize_url(url)}")
    platform_id = item.get("platform_item_id")
    if isinstance(platform_id, str) and platform_id.strip():
        source = str(item.get("source_entity_id", ""))
        keys.add(f"platform:{source}:{platform_id.strip().casefold()}")
    digest = item.get("content_sha256")
    if isinstance(digest, str) and digest:
        keys.add(f"sha256:{digest.lower()}")
    return keys


def precision_rank(value: Any) -> int:
    return {"second": 5, "minute": 4, "hour": 3, "day": 2, "unknown": 1}.get(str(value), 0)


def merge_items(records: list[dict[str, Any]], canonical_id: str) -> dict[str, Any]:
    best = max(
        records,
        key=lambda record: (
            precision_rank(record.get("published_at_precision")),
            len(json.dumps(record, sort_keys=True)),
            record.get("source_item_id", ""),
        ),
    )
    merged = dict(best)
    merged["source_item_id"] = canonical_id
    canonical_urls = [record.get("canonical_url") for record in records if isinstance(record.get("canonical_url"), str)]
    if canonical_urls:
        merged["canonical_url"] = sorted(canonical_urls, key=lambda value: (len(normalize_url(value)), value))[0]
    for field in ("archive_urls", "upstream_item_ids", "artifact_ids"):
        values: list[Any] = []
        for record in records:
            candidate = record.get(field)
            if isinstance(candidate, list):
                values.extend(candidate)
        if values or field in merged:
            merged[field] = unique_list(values)
    retrievals = [record.get("retrieved_at") for record in records if isinstance(record.get("retrieved_at"), str)]
    if retrievals:
        merged["retrieved_at"] = min(retrievals)
    notes = [record.get("rights_note") for record in records if isinstance(record.get("rights_note"), str) and record.get("rights_note")]
    if notes:
        merged["rights_note"] = max(notes, key=len)
    return merged


def replace_strings(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, str):
        return aliases.get(value, value)
    if isinstance(value, list):
        return [replace_strings(item, aliases) for item in value]
    if isinstance(value, dict):
        return {key: replace_strings(item, aliases) for key, item in value.items()}
    return value


def rewrite_all_references(root: Path, aliases: dict[str, str]) -> int:
    if not aliases:
        return 0
    changed = 0
    for path in iter_data_files(root):
        # Schemas/config may contain example IDs or enum strings; only rewrite record-bearing trees.
        if path.parts and any(part in {".git", ".war-reporter"} for part in path.parts):
            continue
        relative = path.relative_to(root)
        if relative.parts[0] not in {"catalogs", "data", "maps", "raw-manifests", "tasks", "config"}:
            continue
        kind, value = load_json_or_ndjson(path)
        updated = replace_strings(value, aliases)
        if updated != value:
            dump_json_or_ndjson(path, kind, updated)
            changed += 1
    return changed


def canonicalize_profiles(root: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    records, documents = load_record_collection(root, "catalogs/sources")
    by_id = {str(record.value.get("source_entity_id")): record for record in records if isinstance(record.value.get("source_entity_id"), str)}
    union = UnionFind()
    key_owner: dict[str, str] = {}
    for source_id, stored in by_id.items():
        union.add(source_id)
        for key in profile_identity_keys(stored.value):
            if key in key_owner:
                union.union(source_id, key_owner[key])
            else:
                key_owner[key] = source_id
    for old, preferred in PREFERRED_SOURCE_IDS.items():
        if old in by_id and preferred in by_id:
            union.union(old, preferred)
    aliases: dict[str, str] = {}
    audit: list[dict[str, Any]] = []
    modified_paths: set[Path] = set()
    delete_paths: set[Path] = set()
    groups = [ids for ids in union.groups().values() if len(ids) > 1]
    for ids in sorted(groups):
        canonical_id = pick_preferred_id(ids, PREFERRED_SOURCE_IDS)
        for item in ids:
            if item != canonical_id:
                aliases[item] = canonical_id
        merged = merge_profiles([by_id[item].value for item in ids], canonical_id)
        target_record = by_id.get(canonical_id) or min((by_id[item] for item in ids), key=lambda record: str(record.path))
        for path, (kind, value) in list(documents.items()):
            if kind in {"array", "ndjson"}:
                filtered = [
                    item for item in value
                    if not (isinstance(item, dict) and item.get("source_entity_id") in ids)
                ]
                if path == target_record.path:
                    filtered.append(merged)
                if filtered != value:
                    documents[path] = (kind, filtered)
                    modified_paths.add(path)
            elif isinstance(value, dict) and value.get("source_entity_id") in ids:
                if path == target_record.path:
                    documents[path] = (kind, merged)
                    modified_paths.add(path)
                else:
                    delete_paths.add(path)
        audit.append({"canonical_id": canonical_id, "aliases": sorted(item for item in ids if item != canonical_id)})
    for path in sorted(modified_paths):
        kind, value = documents[path]
        dump_json_or_ndjson(path, kind, value)
    for path in sorted(delete_paths):
        path.unlink()
    return aliases, audit


def canonicalize_items(root: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    records, documents = load_record_collection(root, "data/source-items")
    by_id = {str(record.value.get("source_item_id")): record for record in records if isinstance(record.value.get("source_item_id"), str)}
    union = UnionFind()
    key_owner: dict[str, str] = {}
    for item_id, stored in by_id.items():
        union.add(item_id)
        for key in item_identity_keys(stored.value):
            if key in key_owner:
                union.union(item_id, key_owner[key])
            else:
                key_owner[key] = item_id
    for old, preferred in PREFERRED_ITEM_IDS.items():
        if old in by_id and preferred in by_id:
            union.union(old, preferred)
    aliases: dict[str, str] = {}
    audit: list[dict[str, Any]] = []
    modified_paths: set[Path] = set()
    delete_paths: set[Path] = set()
    groups = [ids for ids in union.groups().values() if len(ids) > 1]
    for ids in sorted(groups):
        canonical_id = pick_preferred_id(ids, PREFERRED_ITEM_IDS)
        for item in ids:
            if item != canonical_id:
                aliases[item] = canonical_id
        merged = merge_items([by_id[item].value for item in ids], canonical_id)
        target_record = by_id.get(canonical_id) or min((by_id[item] for item in ids), key=lambda record: str(record.path))
        for path, (kind, value) in list(documents.items()):
            if kind in {"array", "ndjson"}:
                filtered = [
                    item for item in value
                    if not (isinstance(item, dict) and item.get("source_item_id") in ids)
                ]
                if path == target_record.path:
                    filtered.append(merged)
                if filtered != value:
                    documents[path] = (kind, filtered)
                    modified_paths.add(path)
            elif isinstance(value, dict) and value.get("source_item_id") in ids:
                if path == target_record.path:
                    documents[path] = (kind, merged)
                    modified_paths.add(path)
                else:
                    delete_paths.add(path)
        audit.append({"canonical_id": canonical_id, "aliases": sorted(item for item in ids if item != canonical_id)})
    for path in sorted(modified_paths):
        kind, value = documents[path]
        dump_json_or_ndjson(path, kind, value)
    for path in sorted(delete_paths):
        path.unlink()
    return aliases, audit


def migrate_publication_intervals(root: Path) -> list[str]:
    changed_ids: list[str] = []
    base = root / "data/source-items"
    if not base.exists():
        return changed_ids
    for path in iter_data_files(base):
        kind, value = load_json_or_ndjson(path)
        records = value if kind in {"array", "ndjson"} else [value]
        modified = False
        for record in records:
            if not isinstance(record, dict):
                continue
            if record.get("published_at_precision") != "day":
                continue
            published_at = record.get("published_at")
            if isinstance(published_at, str):
                instant = parse_datetime(published_at).astimezone(UTC)
                day_start = instant.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
                record["published_at"] = None
                record["published_not_before"] = utc_iso(day_start)
                record["published_not_after"] = utc_iso(day_end)
                modified = True
                if isinstance(record.get("source_item_id"), str):
                    changed_ids.append(record["source_item_id"])
        if modified:
            dump_json_or_ndjson(path, kind, value)
    return sorted(changed_ids)


class GitHubClient:
    def __init__(self, repository: str, token: str | None) -> None:
        self.repository = repository
        self.token = token
        self.api_root = f"https://api.github.com/repos/{repository}"

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        url = path if path.startswith("https://") else f"{self.api_root}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "war-reporter-hardening",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                if not body:
                    return None
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {detail}") from exc

    def get_pull(self, number: int) -> dict[str, Any]:
        value = self.request("GET", f"/pulls/{number}")
        if not isinstance(value, dict):
            raise RuntimeError(f"unexpected pull response for #{number}")
        return value

    def paged(self, path: str) -> list[dict[str, Any]]:
        page = 1
        result: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        while True:
            value = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not isinstance(value, list):
                raise RuntimeError(f"unexpected paged response for {path}")
            result.extend(item for item in value if isinstance(item, dict))
            if len(value) < 100:
                return result
            page += 1

    def delete_branch(self, branch: str) -> None:
        encoded = urllib.parse.quote(branch, safe="/")
        self.request("DELETE", f"/git/refs/heads/{encoded}")


def repair_tasks(root: Path, github: GitHubClient | None) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    tasks_root = root / "tasks"
    if not tasks_root.exists():
        return repairs
    for path in sorted(tasks_root.rglob("*.json")):
        kind, value = load_json_or_ndjson(path)
        records = value if kind in {"array", "ndjson"} else [value]
        modified = False
        for record in records:
            if not isinstance(record, dict):
                continue
            task_id = record.get("task_id")
            state = record.get("state")
            changes: list[str] = []
            if state in NO_LEASE_STATES and record.get("lease") is not None:
                record["lease"] = None
                modified = True
                changes.append("cleared_lease")
            if state == "merged":
                result = record.get("result")
                if not isinstance(result, dict):
                    continue
                pr_number = result.get("pr_number")
                if github and isinstance(pr_number, int):
                    pull = github.get_pull(pr_number)
                    merge_sha = pull.get("merge_commit_sha")
                    merged_at = pull.get("merged_at")
                    if pull.get("merged") is not True or not isinstance(merge_sha, str) or not isinstance(merged_at, str):
                        raise RuntimeError(f"task {task_id}: PR #{pr_number} is not merged or lacks merge metadata")
                    if result.get("merge_sha") != merge_sha:
                        result["merge_sha"] = merge_sha
                        modified = True
                        changes.append("set_merge_sha")
                    if result.get("merged_at") != merged_at:
                        result["merged_at"] = merged_at
                        modified = True
                        changes.append("set_merged_at")
                    if result.get("completed_at") != merged_at:
                        result["completed_at"] = merged_at
                        modified = True
                        changes.append("set_completed_at")
            if changes:
                repairs.append({"task_id": task_id, "changes": changes})
        if modified:
            dump_json_or_ndjson(path, kind, value)
    return repairs


def load_tasks(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "tasks").rglob("*.json")):
        _, value = load_json_or_ndjson(path)
        records = value if isinstance(value, list) else [value]
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("task_id"), str):
                result[record["task_id"]] = record
    return result


def audit_or_delete_work_branches(root: Path, github: GitHubClient, delete_stale: bool) -> dict[str, Any]:
    tasks = load_tasks(root)
    branches = [item.get("name") for item in github.paged("/branches") if isinstance(item.get("name"), str)]
    open_pulls = github.paged("/pulls?state=open")
    open_heads = {
        pull.get("head", {}).get("ref")
        for pull in open_pulls
        if isinstance(pull.get("head"), dict) and isinstance(pull.get("head", {}).get("ref"), str)
    }
    stale: list[dict[str, str]] = []
    retained: list[str] = []
    deleted: list[str] = []
    for branch in sorted(name for name in branches if name.startswith("work/")):
        task_id = branch.removeprefix("work/")
        task = tasks.get(task_id)
        reason: str | None = None
        if task is None:
            reason = "orphan_no_task_manifest"
        else:
            state = task.get("state")
            expected = f"work/{task_id}"
            if branch != expected:
                reason = "non_deterministic_branch"
            elif branch in open_heads:
                retained.append(branch)
                continue
            elif state not in ACTIVE_STATES:
                reason = f"stale_task_state_{state}"
            else:
                retained.append(branch)
                continue
        stale.append({"branch": branch, "reason": reason or "stale"})
        if delete_stale:
            github.delete_branch(branch)
            deleted.append(branch)
    return {"stale": stale, "deleted": deleted, "retained": retained}


def append_hardening_docs(root: Path) -> list[str]:
    changed: list[str] = []
    additions = {
        "CHATGPT_PROJECT.md": """

## Canonicalization and bootstrap gate

Discovery workers must not create extraction, claim, corroboration, assessment, map-publication, or report tasks unless repository validation confirms that source-profile and source-item canonicalization is complete.

A worker may bootstrap a new campaign only when all queue backpressure checks pass simultaneously: no eligible ready tasks, no active leases, no open worker PRs, the prior campaign is closed or explicitly carried over, and the configured backlog limit is not exceeded. “No eligible ready task” alone never means “no work exists.”

The repository currently uses one GitHub identity for worker and merge-controller actions. Review is therefore **administrative review**, not cryptographically independent review. Research PRs must not describe this arrangement as independent review unless distinct authenticated identities are configured and enforced.
""",
        "docs/chatgpt/PROJECT_INSTRUCTIONS.md": """

## Hardening gate and backpressure

Before bootstrapping, compute the queue status. Bootstrap is prohibited unless ready tasks are zero, active leases are zero, open worker PRs are zero, the previous campaign is closed or explicitly carried over, and the backlog is below its configured limit. Do not infer an empty queue from the absence of an immediately claimable task.

Do not create extraction, claim, corroboration, assessment, or report tasks while canonicalization validation is failing.

This repository's configured trust boundary is administrative review when worker and merge-controller actions share one GitHub login. Do not call that independent review.
""",
    }
    marker = "## Canonicalization and bootstrap gate"
    for relative, addition in additions.items():
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        local_marker = marker if relative == "CHATGPT_PROJECT.md" else "## Hardening gate and backpressure"
        if local_marker not in text:
            path.write_text(text.rstrip() + addition + "\n", encoding="utf-8")
            changed.append(relative)
    return changed


def write_hardening_gate(root: Path) -> None:
    path = root / "config" / "hardening-gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "canonicalization_complete": True,
        "downstream_task_creation_allowed": True,
        "reason": "Canonicalization migration completed; repository validators must still pass before merge.",
    }
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_audit(root: Path, payload: dict[str, Any]) -> None:
    path = root / "config" / "hardening-audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(root: Path, repository: str | None, token: str | None, delete_stale_branches: bool) -> dict[str, Any]:
    source_aliases, source_groups = canonicalize_profiles(root)
    rewrite_all_references(root, source_aliases)
    item_aliases, item_groups = canonicalize_items(root)
    rewrite_all_references(root, item_aliases)
    interval_items = migrate_publication_intervals(root)

    github = GitHubClient(repository, token) if repository and token else None
    task_repairs = repair_tasks(root, github)
    branch_audit: dict[str, Any] = {"stale": [], "deleted": [], "retained": []}
    if github:
        branch_audit = audit_or_delete_work_branches(root, github, delete_stale_branches)
    doc_updates = append_hardening_docs(root)

    payload = {
        "schema_version": 1,
        "generated_at": utc_iso(datetime.now(UTC)),
        "repository": repository,
        "source_profile_canonicalization": source_groups,
        "source_item_canonicalization": item_groups,
        "publication_interval_migrations": interval_items,
        "task_repairs": task_repairs,
        "work_branch_audit": branch_audit,
        "documentation_updates": doc_updates,
    }
    write_hardening_gate(root)
    write_audit(root, payload)
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--delete-stale-branches", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = run(args.root.resolve(), args.repo, args.token, args.delete_stale_branches)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"hardening migration failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
