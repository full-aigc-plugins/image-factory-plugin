#!/usr/bin/env python3
"""Durable state for one image production job.

The ledger is the reason a batch can be interrupted without being paid for
twice. Every transition is written atomically, so the file on disk is always a
complete older or newer state rather than a torn one, and every batch item is
tracked by its content-derived idempotency key so a resume skips work that is
already done.

Two deliberate restrictions:

* `Failed` is terminal. A failed job is not silently restarted; that requires a
  new job, because an automatic restart is exactly how a bad prompt becomes a
  large bill.
* Anything resembling a credential is refused on both read and write. A ledger is
  meant to be shareable evidence, so it must not be able to hold a secret.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import atomic_json
import contract_migrations
import schema_lite
from contract_migrations import JOB_SCHEMA_VERSION

SCHEMA_VERSION = JOB_SCHEMA_VERSION
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "factory_job.schema.json"
JOB_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,63}$"
IMAGE_LIMIT_ID = "image_gen"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "password",
        "secret",
        "client_secret",
        "authorization",
        "credit_card",
        "cookie",
    }
)

ERROR_CATEGORIES = (
    "capability_unavailable",
    "codex_missing",
    "quota_exceeded",
    "timeout",
    "generation_failed",
    "artifact_missing",
    "hash_mismatch",
    "duplicate_artifact",
    "plan_invalid",
    "approval_required",
    "job_already_running",
    "recovery_required",
    "unknown",
)


class JobState(str, Enum):
    DRAFT = "Draft"
    PLAN_VALIDATED = "PlanValidated"
    PENDING_APPROVAL = "PendingApproval"
    APPROVED = "Approved"
    RUNNING = "Running"
    EVALUATED = "Evaluated"
    OPTIMIZED = "Optimized"
    ACCEPTED = "Accepted"
    COMPLETED = "Completed"
    PARTIAL = "Partial"
    FAILED = "Failed"
    UNKNOWN = "Unknown"


ITEM_STATES = ("Pending", "Attempting", "Generated", "Failed", "Skipped", "Unknown")
# Every state that means a call may have reached the generator. An item in one of
# these states is never attempted again automatically.
ATTEMPTED_ITEM_STATES = ("Attempting", "Generated", "Failed", "Skipped", "Unknown")
# An item in one of these states has an unresolved external call, so starting it
# again could spend a second time for work that may already have happened.
BLOCKING_ATTEMPT_STATES = ("Attempting", "Generated", "Failed", "Skipped", "Unknown")

# The only approval source the CLI can actually prove. A caller cannot assert
# that a human agreed; it can only record that the explicit flag was present.
APPROVAL_SOURCES = ("run_approve_flag",)

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.DRAFT: frozenset({JobState.PLAN_VALIDATED, JobState.FAILED}),
    JobState.PLAN_VALIDATED: frozenset(
        {JobState.PENDING_APPROVAL, JobState.APPROVED, JobState.FAILED}
    ),
    JobState.PENDING_APPROVAL: frozenset({JobState.APPROVED, JobState.FAILED}),
    JobState.APPROVED: frozenset({JobState.RUNNING, JobState.FAILED}),
    JobState.RUNNING: frozenset(
        {JobState.COMPLETED, JobState.PARTIAL, JobState.UNKNOWN, JobState.FAILED}
    ),
    JobState.COMPLETED: frozenset({JobState.EVALUATED, JobState.FAILED}),
    # A partial run may resume its remaining items, but only through a fresh
    # approval bound to the reduced call count.
    JobState.PARTIAL: frozenset(
        {JobState.EVALUATED, JobState.PENDING_APPROVAL, JobState.FAILED}
    ),
    JobState.EVALUATED: frozenset(
        {
            JobState.OPTIMIZED,
            JobState.ACCEPTED,
            JobState.PENDING_APPROVAL,
            JobState.COMPLETED,
            JobState.PARTIAL,
            JobState.FAILED,
        }
    ),
    JobState.OPTIMIZED: frozenset(
        {
            JobState.PENDING_APPROVAL,
            JobState.PLAN_VALIDATED,
            JobState.ACCEPTED,
            JobState.COMPLETED,
            JobState.FAILED,
        }
    ),
    JobState.ACCEPTED: frozenset(),
    JobState.UNKNOWN: frozenset({JobState.COMPLETED, JobState.PARTIAL, JobState.FAILED}),
    JobState.FAILED: frozenset(),
}

RESOLVABLE_STATES = frozenset(
    {
        JobState.DRAFT,
        JobState.PLAN_VALIDATED,
        JobState.PENDING_APPROVAL,
        JobState.APPROVED,
        JobState.RUNNING,
        JobState.EVALUATED,
        JobState.OPTIMIZED,
        JobState.ACCEPTED,
        JobState.UNKNOWN,
    }
)


class LedgerCorruptError(Exception):
    """The ledger is missing, unreadable, or holds something it must never hold."""


class InvalidTransitionError(Exception):
    """The requested state change is not permitted from the current state."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_sha256(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(SHA256_PATTERN, value) is None:
        raise ValueError(f"expected a 64-character lowercase hex digest, got {value!r}")


def _require_positive_int(value: object, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer, got {value!r}")


def _approval_covers(
    record: object, plan_sha256: str, round_number: int, image_count: int
) -> bool:
    """An approval covers exactly one plan, one round, and one call count."""
    if not isinstance(record, dict):
        return False
    return (
        record.get("plan_hash") == plan_sha256
        and record.get("round") == round_number
        and record.get("remaining_count") == image_count
    )


def _entry_for(payload: dict, item_id: str) -> dict:
    entry = next((row for row in payload["items"] if row["item_id"] == item_id), None)
    if entry is None:
        entry = {"item_id": item_id, "state": "Pending", "attempts": 0}
        payload["items"].append(entry)
    for key, default in (
        ("state", "Pending"),
        ("attempts", 0),
        ("attempt_id", None),
        ("attempt_started_at", None),
        ("receipt_id", None),
        ("idempotency_key", None),
        ("error_category", None),
    ):
        entry.setdefault(key, default)
    return entry


def new_job(job_id: str) -> dict:
    if not isinstance(job_id, str) or not json_pattern_match(job_id, JOB_ID_PATTERN):
        raise ValueError(f"job_id must match {JOB_ID_PATTERN}, got {job_id!r}")
    stamp = _timestamp()
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "state": JobState.DRAFT.value,
        "revision": 1,
        "created_at": stamp,
        "updated_at": stamp,
        "batch": None,
        "rounds": [],
        "items": [],
        "approval": {"current": None, "history": []},
        "evaluation": None,
        "optimization": None,
        "usage_limit": None,
        "error_category": None,
        "history": [],
    }


def json_pattern_match(value: str, pattern: str) -> bool:
    import re

    return re.search(pattern, value) is not None


def _scrub(node: object, path: str = "$") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                raise LedgerCorruptError(
                    f"{path}: refusing to persist a credential-like key {key!r}"
                )
            _scrub(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _scrub(value, f"{path}[{index}]")


def _assert_well_formed(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise LedgerCorruptError("ledger root must be a JSON object")
    for field in ("schema_version", "job_id", "state", "revision"):
        if field not in payload:
            raise LedgerCorruptError(f"ledger is missing required field {field!r}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise LedgerCorruptError(
            f"unsupported ledger schema_version {payload['schema_version']!r}"
        )
    if payload["state"] not in {state.value for state in JobState}:
        raise LedgerCorruptError(f"unknown ledger state {payload['state']!r}")
    if not isinstance(payload["revision"], int) or payload["revision"] < 1:
        raise LedgerCorruptError("ledger revision must be a positive integer")
    return payload


def load_ledger(path: Path) -> dict:
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise LedgerCorruptError(f"no ledger at {target}") from error
    except OSError as error:
        raise LedgerCorruptError(f"ledger at {target} could not be read: {error}") from error
    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise LedgerCorruptError(f"ledger at {target} is not valid JSON: {error}") from error
    _scrub(payload)
    # A 1.0.0 ledger is upgraded in memory before it is judged, so historical jobs
    # stay readable without ever being written back in the older shape.
    try:
        payload = contract_migrations.migrate_factory_job(payload).document
    except ValueError as error:
        raise LedgerCorruptError(f"ledger at {target} cannot be migrated: {error}") from error
    return _assert_well_formed(payload)


def write_ledger(path: Path, payload: dict) -> None:
    """Validate, scrub, then persist atomically through the shared writer."""
    _scrub(payload)
    _assert_well_formed(payload)
    atomic_json.write_json_atomic(Path(path), payload)


def schema_errors(payload: dict) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema_lite.validate(payload, schema)


class JobLedger:
    def __init__(self, path: Path, job_id: str | None = None) -> None:
        self.path = Path(path)
        self._job_id = job_id

    def read(self) -> dict:
        return load_ledger(self.path)

    def write(self, payload: dict) -> None:
        write_ledger(self.path, payload)

    def transition(self, target: JobState | str, **fields: object) -> dict:
        try:
            destination = JobState(target)
        except ValueError as error:
            raise ValueError(f"unknown job state {target!r}") from error

        payload = self.read()
        current = JobState(payload["state"])
        if destination not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransitionError(
                f"cannot move from {current.value} to {destination.value}"
            )

        payload["history"].append(
            {
                "from_state": current.value,
                "to_state": destination.value,
                "at": _timestamp(),
                **({"note": fields["note"]} if "note" in fields else {}),
            }
        )
        payload["state"] = destination.value
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        for key, value in fields.items():
            if key == "note":
                continue
            payload[key] = value
        self.write(payload)
        return payload

    def record_item(
        self,
        item: object,
        *,
        state: str,
        receipt_id: str | None = None,
        error_category: str | None = None,
        attempt_id: str | None = None,
        attempt_started_at: str | None = None,
    ) -> dict:
        if state not in ITEM_STATES:
            raise ValueError(f"item state must be one of {ITEM_STATES}, got {state!r}")
        if error_category is not None and error_category not in ERROR_CATEGORIES:
            raise ValueError(f"unknown error category {error_category!r}")

        payload = self.read()
        item_id = getattr(item, "id")
        key = getattr(item, "idempotency_key")
        entry = next((row for row in payload["items"] if row["item_id"] == item_id), None)
        if entry is None:
            entry = {
                "item_id": item_id,
                "state": state,
                "attempts": 0,
                "attempt_id": attempt_id,
                "attempt_started_at": attempt_started_at,
                "receipt_id": None,
                "idempotency_key": None,
                "error_category": None,
            }
            payload["items"].append(entry)
        if state in ATTEMPTED_ITEM_STATES:
            entry["attempts"] = entry["attempts"] + 1
        entry["state"] = state
        entry["idempotency_key"] = key
        entry["receipt_id"] = receipt_id
        entry["error_category"] = error_category
        if attempt_id is not None:
            entry["attempt_id"] = attempt_id
        if attempt_started_at is not None:
            entry["attempt_started_at"] = attempt_started_at
        entry.setdefault("attempt_id", None)
        entry.setdefault("attempt_started_at", None)
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    def pending_items(self, items: object) -> list:
        """Items with no recorded attempt.

        An item that was attempted and failed is deliberately absent: retrying it
        automatically is not this plugin's decision to make.
        """
        payload = self.read()
        seen = {row.get("idempotency_key") for row in payload["items"] if row.get("idempotency_key")}
        return [item for item in items if getattr(item, "idempotency_key") not in seen]

    def note_usage_limit(self, *, limit_id: str, resets_at: int | None) -> dict:
        if limit_id != IMAGE_LIMIT_ID:
            raise ValueError(f"only the {IMAGE_LIMIT_ID!r} limit is tracked, got {limit_id!r}")
        payload = self.read()
        payload["usage_limit"] = {"limit_id": limit_id, "resets_at": resets_at}
        payload["error_category"] = "quota_exceeded"
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    def set_error_category(self, category: str | None) -> dict:
        if category is not None and category not in ERROR_CATEGORIES:
            raise ValueError(f"unknown error category {category!r}")
        payload = self.read()
        payload["error_category"] = category
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    # ---------------------------------------------------------- plan and approval

    def bind_plan(self, plan_sha256: str, round_number: int, image_count: int) -> dict:
        """Record the identity of the plan this job is about to execute.

        Only identity and count are stored: no prompts, no local paths. Binding a
        different plan clears the *current* approval because an approval for other
        work authorizes nothing here, while the history is kept as an audit trail.
        """
        _require_sha256(plan_sha256)
        _require_positive_int(round_number, "round")
        _require_positive_int(image_count, "image_count")
        payload = self.read()
        payload["batch"] = {
            "batch_id": payload["job_id"],
            "round": round_number,
            "plan_hash": plan_sha256,
            "image_count": image_count,
        }
        approvals = payload.setdefault("approval", {"current": None, "history": []})
        current = approvals.get("current")
        if current is not None and not _approval_covers(
            current, plan_sha256, round_number, image_count
        ):
            approvals["current"] = None
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    def record_approval(
        self, plan_sha256: str, round_number: int, image_count: int, source: str
    ) -> dict:
        if source not in APPROVAL_SOURCES:
            raise ValueError(f"approval source must be one of {APPROVAL_SOURCES}, got {source!r}")
        _require_sha256(plan_sha256)
        _require_positive_int(round_number, "round")
        _require_positive_int(image_count, "image_count")
        payload = self.read()
        approvals = payload.setdefault("approval", {"current": None, "history": []})
        record = {
            "plan_hash": plan_sha256,
            "round": round_number,
            "remaining_count": image_count,
            "approved_at": _timestamp(),
            "note": f"approved via {source}",
        }
        approvals["history"].append(record)
        approvals["current"] = record
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    def approval_matches(self, plan_sha256: str, round_number: int, image_count: int) -> bool:
        payload = self.read()
        approvals = payload.get("approval") or {}
        return _approval_covers(approvals.get("current"), plan_sha256, round_number, image_count)

    # ------------------------------------------------------------ attempt lifecycle

    def start_attempt(self, item: object, attempt_id: str) -> dict:
        """Reserve an item before the external call, incrementing attempts exactly once."""
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("attempt_id must be a non-empty string")
        payload = self.read()
        entry = _entry_for(payload, getattr(item, "id"))
        if entry["state"] in BLOCKING_ATTEMPT_STATES:
            raise InvalidTransitionError(
                f"item {entry['item_id']} is {entry['state']}; it must not be started again"
            )
        entry["state"] = "Attempting"
        entry["attempts"] = entry["attempts"] + 1
        entry["attempt_id"] = attempt_id
        entry["attempt_started_at"] = _timestamp()
        entry["idempotency_key"] = getattr(item, "idempotency_key")
        entry["receipt_id"] = None
        entry["error_category"] = None
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    def complete_attempt(self, item: object, attempt_id: str, receipt_id: str) -> dict:
        if not isinstance(receipt_id, str) or not receipt_id:
            raise ValueError("receipt_id must be a non-empty string")
        return self._close_attempt(
            getattr(item, "id"), attempt_id, state="Generated", receipt_id=receipt_id
        )

    def fail_attempt(self, item: object, attempt_id: str, error_category: str) -> dict:
        if error_category not in ERROR_CATEGORIES:
            raise ValueError(f"unknown error category {error_category!r}")
        return self._close_attempt(
            getattr(item, "id"), attempt_id, state="Failed", error_category=error_category
        )

    def mark_attempt_unknown(self, item_id: str, attempt_id: str) -> dict:
        """Record that an interrupted call may or may not have reached the generator."""
        return self._close_attempt(item_id, attempt_id, state="Unknown")

    def _close_attempt(
        self,
        item_id: str,
        attempt_id: str,
        *,
        state: str,
        receipt_id: str | None = None,
        error_category: str | None = None,
    ) -> dict:
        payload = self.read()
        entry = _entry_for(payload, item_id)
        if entry["state"] != "Attempting" or entry["attempt_id"] != attempt_id:
            raise InvalidTransitionError(
                f"item {item_id} has no active attempt {attempt_id!r}"
            )
        entry["state"] = state
        entry["receipt_id"] = receipt_id
        entry["error_category"] = error_category
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    # ------------------------------------------------------- evaluation and result

    def record_evaluation(
        self,
        scores_sha256: str,
        decision: str,
        *,
        all_gates_passed: bool,
        scores_path: str | None = None,
    ) -> dict:
        """Record the verdict, hashed so the scores document can be re-identified."""
        _require_sha256(scores_sha256)
        if decision not in ("pass", "fail", "pending_approval"):
            raise ValueError(f"unknown decision {decision!r}")
        payload = self.read()
        payload["evaluation"] = {
            "decision": decision,
            "all_gates_passed": bool(all_gates_passed),
            "evaluated_at": _timestamp(),
            "scores_sha256": scores_sha256,
            "scores_path": scores_path,
        }
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload

    def record_optimization(
        self,
        plan_sha256: str,
        round_number: int,
        *,
        carried_forward=(),
        rework=(),
        next_plan_path: str | None = None,
    ) -> dict:
        _require_sha256(plan_sha256)
        _require_positive_int(round_number, "round")
        payload = self.read()
        payload["optimization"] = {
            "round": round_number,
            "carried_forward": [str(value) for value in carried_forward],
            "rework": [str(value) for value in rework],
            "optimized_at": _timestamp(),
            "next_plan_path": next_plan_path,
        }
        # The approval covered the previous round's calls; a new round needs its own.
        approvals = payload.setdefault("approval", {"current": None, "history": []})
        approvals["current"] = None
        payload["batch"] = {
            "batch_id": payload["job_id"],
            "round": round_number,
            "plan_hash": plan_sha256,
            "image_count": max(1, len(payload["optimization"]["rework"])),
        }
        payload["revision"] = payload["revision"] + 1
        payload["updated_at"] = _timestamp()
        self.write(payload)
        return payload
