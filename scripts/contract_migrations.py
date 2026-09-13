#!/usr/bin/env python3
"""Deterministic, safety-strengthening migrations for persistent contracts."""

from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationResult:
    document: dict
    notes: tuple[str, ...]


def migrate_image_batch(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("image batch must be a JSON object")
    plan = copy.deepcopy(document)
    version = plan.get("schema_version")
    if version == "1.1.0":
        return MigrationResult(plan, ())
    if version != "1.0.0":
        raise ValueError(f"unsupported image batch schema_version {version!r}")
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
    return MigrationResult(plan, ("migrated image batch 1.0.0 to 1.1.0",))


def migrate_factory_job(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("factory job must be a JSON object")
    job = copy.deepcopy(document)
    version = job.get("schema_version")
    if version == "1.1.0":
        return MigrationResult(job, ())
    if version != "1.0.0":
        raise ValueError(f"unsupported factory job schema_version {version!r}")
    job["schema_version"] = "1.1.0"
    if job.get("approval") is not None:
        raise ValueError("factory job 1.0.0 approval evidence cannot be migrated safely")
    if job.get("batch") is not None and not isinstance(job.get("batch"), dict):
        raise ValueError("factory job batch must be a JSON object or null")
    job["approval"] = {"current": None, "history": []}
    job["evaluation"] = None
    job["optimization"] = None
    items = job.get("items", [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                item.setdefault("attempt_id", None)
                item.setdefault("attempt_started_at", None)
    return MigrationResult(job, ("migrated factory job 1.0.0 to 1.1.0",))
