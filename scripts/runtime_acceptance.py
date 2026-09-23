#!/usr/bin/env python3
"""Evidence-gated runtime acceptance; offline fixtures never prove live stability."""

from __future__ import annotations

import copy
from datetime import datetime


SCHEMA_VERSION = "1.0.0"
CASES = (
    ("paid-4", "paid_story", "Codex"),
    ("paid-8", "paid_story", "Codex"),
    ("paid-12", "paid_story", "Codex"),
    ("host-codex", "cross_host", "Codex"),
    ("host-zcode", "cross_host", "ZCode"),
    ("host-kimi", "cross_host", "Kimi"),
    ("fault-interruption", "fault", "Codex"),
    ("fault-duplicate-callback", "fault", "Codex"),
    ("fault-concurrency", "fault", "Codex"),
    ("fault-disk-full", "fault", "Codex"),
    ("fault-quota-exhaustion", "fault", "Codex"),
)


def new_matrix(*, plugin_version: str) -> dict:
    """Seed explicit NOT_RUN cases without manufacturing execution evidence."""
    if not plugin_version:
        raise ValueError("plugin_version is required")
    return {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": plugin_version,
        "cases": [
            {
                "case_id": case_id, "kind": kind, "status": "NOT_RUN", "host": host,
                "plugin_version": plugin_version,
                "model": None, "provider": None, "prompt_strategy": None,
                "started_at": None, "ended_at": None, "evidence_tier": "none", "evidence_refs": [],
                "fault_proof": None, "notes": None,
            }
            for case_id, kind, host in CASES
        ],
    }


def _valid_time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def add_case(
    matrix: dict, *, case_id: str, kind: str, host: str,
    model: str | None = None, provider: str | None = None,
    prompt_strategy: str | None = None,
) -> dict:
    """Add a separately tracked host/model/provider combination as NOT_RUN."""
    validate_matrix(matrix)
    if not case_id or any(case["case_id"] == case_id for case in matrix["cases"]):
        raise ValueError(f"duplicate or empty case_id {case_id!r}")
    if kind not in ("cross_host", "model_comparison", "fault") or not host:
        raise ValueError("kind and host are required")
    updated = copy.deepcopy(matrix)
    updated["cases"].append({
        "case_id": case_id, "kind": kind, "status": "NOT_RUN", "host": host,
        "plugin_version": matrix["plugin_version"], "model": model, "provider": provider,
        "prompt_strategy": prompt_strategy, "started_at": None, "ended_at": None,
        "evidence_tier": "none", "evidence_refs": [], "fault_proof": None, "notes": None,
    })
    validate_matrix(updated)
    return updated


def _validate_case(case: dict, plugin_version: str) -> None:
    case_id = case["case_id"]
    status = case.get("status")
    if status not in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
        raise ValueError("status must be PASS, FAIL, BLOCKED or NOT_RUN")
    if not case.get("host") or case.get("plugin_version") != plugin_version:
        raise ValueError("host and matching plugin version are required")
    if status == "NOT_RUN":
        if (case["evidence_tier"] != "none" or case["evidence_refs"]
                or case["started_at"] is not None or case["ended_at"] is not None
                or case["fault_proof"] is not None or case.get("story_proof") is not None):
            raise ValueError("NOT_RUN cannot carry execution evidence")
        return
    if status == "BLOCKED":
        if not case.get("notes"):
            raise ValueError("BLOCKED requires a reason in notes")
        return
    if case.get("evidence_tier") != "live_runtime":
        raise ValueError("PASS/FAIL requires live_runtime evidence tier")
    if not case.get("evidence_refs") or not all(isinstance(ref, str) and ref.strip() for ref in case["evidence_refs"]):
        raise ValueError("PASS/FAIL requires nonempty evidence_refs")
    if not _valid_time(case.get("started_at")) or not _valid_time(case.get("ended_at")):
        raise ValueError("PASS/FAIL requires observed start and end times")
    if datetime.fromisoformat(case["ended_at"].replace("Z", "+00:00")) < datetime.fromisoformat(case["started_at"].replace("Z", "+00:00")):
        raise ValueError("ended_at precedes started_at")
    if case["kind"] == "paid_story" and status == "PASS":
        proof = case.get("story_proof")
        expected = {"paid-4": 4, "paid-8": 8, "paid-12": 12}.get(case_id)
        if (not isinstance(proof, dict) or expected is None
                or proof.get("shot_count") != expected
                or proof.get("verified_receipt_count", -1) < expected
                or proof.get("human_labeled_count", -1) < expected
                or proof.get("paid_call_count", -1) < expected
                or not proof.get("receipt_refs") or not proof.get("human_label_refs")
                or not isinstance(proof.get("elapsed_seconds"), (int, float))
                or proof["elapsed_seconds"] <= 0):
            raise ValueError("story_proof must bind exact shot count, verified receipts, human labels, paid calls and elapsed time")
    if case["kind"] == "fault":
        proof = case.get("fault_proof")
        required = {"duplicate_paid_calls", "recovery_handle_preserved", "artifact_misattributed", "external_calls", "final_state"}
        if not isinstance(proof, dict) or not required <= set(proof):
            raise ValueError("fault_proof must record duplicate calls, recovery, attribution, external calls and final state")
        if status == "PASS" and (proof["duplicate_paid_calls"] or proof["artifact_misattributed"]):
            raise ValueError("PASS cannot include duplicate paid calls or misattributed artifacts")
        if status == "PASS" and case_id == "fault-disk-full" and proof["external_calls"] != 0:
            raise ValueError("disk-full PASS requires zero external calls")
        if status == "PASS" and case_id == "fault-interruption" and not proof["recovery_handle_preserved"]:
            raise ValueError("interruption PASS requires a recovery handle")


def validate_matrix(matrix: dict) -> None:
    """Reject hand-edited PASS claims that lack runtime evidence metadata."""
    if matrix.get("schema_version") != SCHEMA_VERSION or not matrix.get("plugin_version"):
        raise ValueError("invalid runtime matrix version")
    cases = matrix.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("runtime matrix requires cases")
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id in matrix")
    for case in cases:
        _validate_case(case, matrix["plugin_version"])


def record_case(matrix: dict, case_id: str, record: dict) -> dict:
    """Return a new matrix after validating one case and its evidence tier."""
    validate_matrix(matrix)
    updated = copy.deepcopy(matrix)
    matches = [case for case in updated.get("cases", []) if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or duplicate case_id {case_id!r}")
    case = matches[0]
    if "host" in record and record["host"] != case["host"]:
        raise ValueError("case host is immutable; add a separate host case")
    allowed = (set(case) | {"story_proof"}) - {"case_id", "kind"}
    if set(record) - allowed:
        raise ValueError("record contains unknown or immutable fields")
    case.update(record)
    validate_matrix(updated)
    return updated
