#!/usr/bin/env python3
"""Upgrade persisted 1.0.0 documents to the 1.1.0 contracts.

Migration here is deliberately one-directional and safety-strengthening: it may
add a required human gate, but it may never invent human approval that was not
observed. That asymmetry is the whole point. A 1.0.0 plan could be written with
approval optional; upgrading it must therefore *tighten* the plan, never quietly
preserve the looser posture.

Job migration refuses when it would have to guess. A 1.0.0 job that already
carries approval evidence cannot be migrated, because the 1.1.0 approval record
requires a plan hash and remaining count that a 1.0.0 file never captured.
Recording an approval whose binding is unknown would defeat the binding.

Callers own their dictionaries: every function deep-copies before mutating, so a
failed or successful migration never alters the input.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

PLAN_SCHEMA_VERSION = "1.1.0"
JOB_SCHEMA_VERSION = "1.1.0"
LEGACY_SCHEMA_VERSION = "1.0.0"

PLAN_NOTE = "migrated image batch 1.0.0 to 1.1.0"
JOB_NOTE = "migrated factory job 1.0.0 to 1.1.0"

DEFAULT_LIMITS = {"max_images": 20, "max_rounds": 3}
DEFAULT_JUDGE_POLICY = {"min_dimension": 256, "reject_duplicates": True, "pass_threshold": 0.8}


@dataclass(frozen=True)
class MigrationResult:
    document: dict
    notes: tuple[str, ...]


def migrate_image_batch(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("image batch must be a JSON object")
    plan = copy.deepcopy(document)
    version = plan.get("schema_version")
    if version == PLAN_SCHEMA_VERSION:
        return MigrationResult(plan, ())
    if version != LEGACY_SCHEMA_VERSION:
        raise ValueError(f"unsupported image batch schema_version {version!r}")

    plan["schema_version"] = PLAN_SCHEMA_VERSION

    limits = plan.get("limits")
    if limits is None:
        limits = dict(DEFAULT_LIMITS)
        plan["limits"] = limits
    if not isinstance(limits, dict):
        raise ValueError("image batch limits must be a JSON object")

    policy = plan.get("judge_policy")
    if policy is None:
        policy = dict(DEFAULT_JUDGE_POLICY)
        plan["judge_policy"] = policy
    if not isinstance(policy, dict):
        raise ValueError("image batch judge_policy must be a JSON object")

    # Both human gates become mandatory. A legacy plan carrying the opposite
    # value is upgraded rather than rejected: the migration's job is to remove
    # the weaker posture, not to preserve it.
    limits["require_approval_before_run"] = True
    policy["require_human_labels"] = True

    return MigrationResult(plan, (PLAN_NOTE,))


def migrate_factory_job(document: object) -> MigrationResult:
    if not isinstance(document, dict):
        raise ValueError("factory job must be a JSON object")
    job = copy.deepcopy(document)
    version = job.get("schema_version")
    if version == JOB_SCHEMA_VERSION:
        return MigrationResult(job, ())
    if version != LEGACY_SCHEMA_VERSION:
        raise ValueError(f"unsupported factory job schema_version {version!r}")

    job["schema_version"] = JOB_SCHEMA_VERSION

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

    return MigrationResult(job, (JOB_NOTE,))
