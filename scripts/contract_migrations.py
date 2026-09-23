#!/usr/bin/env python3
"""Deterministic, safety-strengthening migrations for persistent contracts."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BATCH_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


def _is_transaction_batch(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "batch_id",
        "round",
        "plan_sha256",
        "image_count",
    }:
        return False
    return (
        isinstance(value["batch_id"], str)
        and BATCH_ID_PATTERN.fullmatch(value["batch_id"]) is not None
        and isinstance(value["round"], int)
        and not isinstance(value["round"], bool)
        and value["round"] >= 1
        and isinstance(value["plan_sha256"], str)
        and SHA256_PATTERN.fullmatch(value["plan_sha256"]) is not None
        and isinstance(value["image_count"], int)
        and not isinstance(value["image_count"], bool)
        and 1 <= value["image_count"] <= 200
    )


def _is_usage_limit(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"limit_id", "resets_at"}
        and value["limit_id"] == "image_gen"
        and (
            value["resets_at"] is None
            or (isinstance(value["resets_at"], int) and not isinstance(value["resets_at"], bool))
        )
    )


@dataclass(frozen=True)
class MigrationResult:
    document: dict
    notes: tuple[str, ...]


def migrate_image_batch(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("image batch must be a JSON object")
    plan = copy.deepcopy(document)
    version = plan.get("schema_version")
    if version == "1.6.0":
        return MigrationResult(plan, ())
    if version not in ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"):
        raise ValueError(f"unsupported image batch schema_version {version!r}")
    notes: list[str] = []
    if version == "1.0.0":
        plan["schema_version"] = "1.1.0"
        limits = plan.get("limits")
        if limits is None:
            limits = {"max_images": 20, "max_rounds": 3}
            plan["limits"] = limits
        if not isinstance(limits, dict):
            raise ValueError("image batch limits must be a JSON object")
        policy = plan.get("judge_policy")
        if policy is None:
            policy = {
                "min_dimension": 256,
                "reject_duplicates": True,
                "pass_threshold": 0.8,
            }
            plan["judge_policy"] = policy
        if not isinstance(policy, dict):
            raise ValueError("image batch judge_policy must be a JSON object")
        limits["require_approval_before_run"] = True
        policy["require_human_labels"] = True
        notes.append("migrated image batch 1.0.0 to 1.1.0")
        version = "1.1.0"
    if version == "1.1.0":
        # 1.1.0 -> 1.2.0 adds optional per-item pixel checks.
        plan["schema_version"] = "1.2.0"
        notes.append("migrated image batch 1.1.0 to 1.2.0")
        version = "1.2.0"
    if version == "1.2.0":
        # 1.2.0 -> 1.3.0 adds only optional series-consistency fields.
        plan["schema_version"] = "1.3.0"
        notes.append("migrated image batch 1.2.0 to 1.3.0")
        version = "1.3.0"
    if version == "1.3.0":
        # 1.3.0 -> 1.4.0 adds optional, file-derived production quality gates.
        plan["schema_version"] = "1.4.0"
        notes.append("migrated image batch 1.3.0 to 1.4.0")
        version = "1.4.0"
    if version == "1.4.0":
        # 1.4.0 -> 1.5.0 adds only optional structured story-state fields.
        # There is no safe state to infer for an older plan.
        plan["schema_version"] = "1.5.0"
        notes.append("migrated image batch 1.4.0 to 1.5.0")
        version = "1.5.0"
    if version == "1.5.0":
        plan["schema_version"] = "1.6.0"
        notes.append("migrated image batch 1.5.0 to 1.6.0")
    return MigrationResult(plan, tuple(notes))


def migrate_artifact_receipt(document: object) -> MigrationResult:
    """Add explicit nullable provenance to legacy receipts without guessing values."""
    if not isinstance(document, dict):
        raise ValueError("artifact receipt must be a JSON object")
    receipt = copy.deepcopy(document)
    version = receipt.get("schema_version")
    if version == "1.1.0":
        return MigrationResult(receipt, ())
    if version != "1.0.0":
        raise ValueError(f"unsupported artifact receipt schema_version {version!r}")
    receipt["schema_version"] = "1.1.0"
    receipt["provenance"] = {
        "plugin_revision": None,
        "host_version": None,
        "codex_version": None,
        "capability_signature": None,
        "reviewer_version": None,
        "consistency_profile_sha256": None,
    }
    return MigrationResult(
        receipt, ("migrated artifact receipt 1.0.0 to 1.1.0",)
    )


def migrate_scores(document: object) -> MigrationResult:
    """Upgrade scores without inventing reviewer evidence."""
    if not isinstance(document, dict):
        raise ValueError("scores must be a JSON object")
    scores = copy.deepcopy(document)
    version = scores.get("schema_version")
    if version == "1.4.0":
        return MigrationResult(scores, ())
    if version not in ("1.1.0", "1.2.0", "1.3.0"):
        raise ValueError(f"unsupported scores schema_version {version!r}")
    notes: list[str] = []
    if version == "1.1.0":
        scores["schema_version"] = "1.2.0"
        notes.append("migrated scores 1.1.0 to 1.2.0")
        version = "1.2.0"
    if version == "1.2.0":
        scores["schema_version"] = "1.3.0"
        scores["reviewer_reports"] = []
        notes.append("migrated scores 1.2.0 to 1.3.0")
        version = "1.3.0"
    if version == "1.3.0":
        scores["schema_version"] = "1.4.0"
        notes.append("migrated scores 1.3.0 to 1.4.0")
    return MigrationResult(scores, tuple(notes))


def migrate_factory_job(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("factory job must be a JSON object")
    job = copy.deepcopy(document)
    notes: list[str] = []
    version = job.get("schema_version")
    if version == "1.2.0":
        return MigrationResult(job, ())
    if version not in ("1.0.0", "1.1.0"):
        raise ValueError(f"unsupported factory job schema_version {version!r}")
    if version == "1.0.0":
        if job.get("approval") is not None:
            raise ValueError("factory job 1.0.0 approval evidence cannot be migrated safely")
        if job.get("batch") is not None and not isinstance(job.get("batch"), dict):
            raise ValueError("factory job batch must be a JSON object or null")
        if job.get("batch") is not None and not _is_transaction_batch(job["batch"]):
            job["batch"] = None
        if job.get("usage_limit") is not None and not _is_usage_limit(job["usage_limit"]):
            job["usage_limit"] = None
        job["approval"] = {"current": None, "history": []}
        job["evaluation"] = None
        job["optimization"] = None
        items = job.get("items", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    item.setdefault("attempt_id", None)
                    item.setdefault("attempt_started_at", None)
                    item.setdefault("receipt_id", None)
                    item.setdefault("idempotency_key", None)
                    key = item["idempotency_key"]
                    if key is not None and (
                        not isinstance(key, str) or SHA256_PATTERN.fullmatch(key) is None
                    ):
                        item["idempotency_key"] = None
                    item.setdefault("error_category", None)
        notes.append("migrated factory job 1.0.0 to 1.1.0")
    # 1.1.0 -> 1.2.0 adds the durable per-round numeric history. Historic rounds
    # cannot be backfilled (their numbers were never kept), so the default is an
    # empty record rather than an invented one.
    job["schema_version"] = "1.2.0"
    numeric_history = job.setdefault("numeric_history", [])
    if not isinstance(numeric_history, list):
        raise ValueError("factory job numeric_history must be a list")
    notes.append("migrated factory job 1.1.0 to 1.2.0")
    return MigrationResult(job, tuple(notes))
