#!/usr/bin/env python3
"""Evaluate a batch round and record the verdict.

The single design rule here is that a machine verdict and a model verdict are not
the same kind of thing, so they are not given the same authority.

Deterministic gates decide. They answer questions with one true answer: did a file
appear, is it a PNG, is it large enough, does its hash match the receipt, is the
same image standing in for two different items. A batch fails on these alone.

A model-authored score is advisory. This module never calls a model; if a score is
supplied it is recorded and compared against the threshold, and a low score asks
for a human rather than failing the batch. Making a model's opinion authoritative
would mean an optimizer tuning against its own judge, which is how a loop drifts
somewhere the operator never asked for.

A human decision outranks both, because it is the only signal that is actually
about the desired result. Human labels are recorded next to the scores so the
advisory signal can later be calibrated against real decisions.

An advisory entry may additionally carry named dimensions (a bounded per-dimension
score plus a gap statement naming observable evidence). Dimensions refine the
advisory without changing its authority: they never fail a batch, and a dimension
whose statement names no observable evidence is recorded as incomplete so it is
reported without being counted as a gap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from artifact_collector import file_sha256, parse_png_size
from declared_checks import evaluate_checks

SCHEMA_VERSION = "1.1.0"
HUMAN_LABELS = ("approved", "rejected", "unlabeled")
DECISIONS = ("pass", "fail", "pending_approval")
MAX_DIMENSIONS = 16
DIMENSION_FIELDS = frozenset({"name", "score", "evidence"})


@dataclass(frozen=True)
class EvaluationResult:
    ok: bool
    scores: dict
    errors: tuple[str, ...] = ()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gate(
    receipt: dict | None,
    destination_dir: Path,
    min_dimension: int,
    pixel_checks: tuple[dict, ...] = (),
) -> tuple[str, ...]:
    if receipt is None:
        return ("missing_artifact",)
    target = destination_dir / str(receipt.get("path", ""))
    if not target.is_file():
        return ("missing_artifact",)

    failures: list[str] = []
    size = parse_png_size(target)
    if size is None:
        failures.append("not_a_png")
    elif size[0] < min_dimension or size[1] < min_dimension:
        failures.append("below_min_dimension")
    if file_sha256(target) != receipt.get("sha256"):
        failures.append("hash_mismatch")
    if pixel_checks and any(
        not row["passed"] for row in evaluate_checks(pixel_checks, target)
    ):
        failures.append("failed_pixel_check")
    return tuple(failures)


def _validate_dimension(dimension: object, item_id: str) -> None:
    if not isinstance(dimension, dict):
        raise ValueError(f"advisory dimension for {item_id!r} must be an object")
    unknown = sorted(set(dimension) - DIMENSION_FIELDS)
    if unknown:
        raise ValueError(
            f"advisory dimension for {item_id!r} has unknown fields: {', '.join(unknown)}"
        )
    name = dimension.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 64:
        raise ValueError(
            f"advisory dimension name for {item_id!r} must be a non-empty string "
            "of at most 64 characters"
        )
    score = dimension.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError(f"advisory dimension score for {item_id!r} must be a number")
    if not 0.0 <= float(score) <= 1.0:
        raise ValueError(f"advisory dimension score for {item_id!r} must be between 0 and 1")
    evidence = dimension.get("evidence")
    if evidence is not None and (not isinstance(evidence, str) or len(evidence) > 2000):
        raise ValueError(
            f"advisory dimension evidence for {item_id!r} must be a string "
            "of at most 2000 characters"
        )


def _validate_advisory(advisory: dict, known: set[str]) -> None:
    for item_id, entry in advisory.items():
        if item_id not in known:
            raise ValueError(f"advisory score given for unknown item {item_id!r}")
        if isinstance(entry, dict):
            score = entry.get("score")
            dimensions = entry.get("dimensions", [])
            if not isinstance(dimensions, list) or len(dimensions) > MAX_DIMENSIONS:
                raise ValueError(
                    f"advisory dimensions for {item_id!r} must be a list "
                    f"of at most {MAX_DIMENSIONS} entries"
                )
            for dimension in dimensions:
                _validate_dimension(dimension, item_id)
        else:
            score = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"advisory score for {item_id!r} must be a number")
        if not 0.0 <= float(score) <= 1.0:
            raise ValueError(f"advisory score for {item_id!r} must be between 0 and 1")


def _validate_labels(labels: dict, known: set[str]) -> None:
    for item_id, label in labels.items():
        if item_id not in known:
            raise ValueError(f"label given for unknown item {item_id!r}")
        if label not in HUMAN_LABELS:
            raise ValueError(f"label for {item_id!r} must be one of {HUMAN_LABELS}")


def _dimension_rows(entry: dict) -> list[dict]:
    rows = []
    for dimension in (entry.get("dimensions") or []):
        evidence = dimension.get("evidence")
        rows.append(
            {
                "name": str(dimension["name"]).strip(),
                "score": float(dimension["score"]),
                # A dimension whose statement names no observable evidence is
                # recorded as incomplete: it is reported, but it never counts
                # as a gap.
                "complete": bool(str(evidence or "").strip()),
                **({"evidence": evidence} if evidence is not None else {}),
            }
        )
    return rows


def evaluate_batch(
    *,
    batch_id: str,
    round_number: int,
    items,
    receipts: dict,
    destination_dir: Path,
    min_dimension: int,
    reject_duplicates: bool,
    pass_threshold: float,
    advisory_enabled: bool,
    require_human_labels: bool,
    advisory: dict | None = None,
    human_labels: dict | None = None,
) -> EvaluationResult:
    destination_dir = Path(destination_dir)
    advisory = dict(advisory or {})
    human_labels = dict(human_labels or {})
    known = {item.id for item in items}
    _validate_advisory(advisory, known)
    _validate_labels(human_labels, known)

    item_ids = [item.id for item in items]
    gates: dict[str, tuple[str, ...]] = {}
    hashes: dict[str, str | None] = {}

    for item in items:
        receipt = receipts.get(item.id)
        gates[item.id] = _gate(receipt, destination_dir, min_dimension, getattr(item, "pixel_checks", ()))
        resolved = destination_dir / str(receipt.get("path", "")) if receipt else None
        hashes[item.id] = (
            file_sha256(resolved) if resolved is not None and resolved.is_file() else None
        )

    if reject_duplicates:
        counts: dict[str, int] = {}
        for digest in hashes.values():
            if digest is not None:
                counts[digest] = counts.get(digest, 0) + 1
        for item_id, digest in hashes.items():
            if digest is not None and counts.get(digest, 0) > 1:
                gates[item_id] = gates[item_id] + ("duplicate_content",)

    checks_by_item = {
        item.id: tuple(getattr(item, "pixel_checks", ()) or ()) for item in items
    }
    details_by_item: dict[str, list[dict]] = {}
    for item in items:
        checks = checks_by_item.get(item.id) or ()
        if checks and receipts.get(item.id) is not None:
            target = destination_dir / str(receipts[item.id].get("path", ""))
            if target.is_file():
                details_by_item[item.id] = evaluate_checks(checks, target)

    per_item = []
    for item_id in item_ids:
        row = {"item_id": item_id, "passed": not gates[item_id], "failures": list(gates[item_id])}
        if item_id in details_by_item:
            row["pixel_checks"] = details_by_item[item_id]
        per_item.append(row)
    all_passed = all(row["passed"] for row in per_item)

    advisory_items = []
    for item_id in item_ids:
        if item_id not in advisory:
            continue
        entry = advisory[item_id]
        if isinstance(entry, dict):
            row = {
                "item_id": item_id,
                "score": float(entry.get("score")),
                "reason": str(entry.get("reason", "")),
            }
            dimensions = _dimension_rows(entry)
            if entry.get("dimensions") is not None:
                row["dimensions"] = dimensions
        else:
            score, reason = (entry if isinstance(entry, (tuple, list)) else (entry, ""))
            row = {"item_id": item_id, "score": float(score), "reason": str(reason)}
        advisory_items.append(row)

    label_rows = []
    for item_id in item_ids:
        label = human_labels.get(item_id, "unlabeled")
        label_rows.append(
            {
                "item_id": item_id,
                "label": label,
                "at": _timestamp() if label != "unlabeled" else None,
            }
        )

    rejected = any(row["label"] == "rejected" for row in label_rows)
    unlabeled = any(row["label"] == "unlabeled" for row in label_rows)
    below_threshold = any(row["score"] < pass_threshold for row in advisory_items)

    if not all_passed:
        decision = "fail"
    elif rejected:
        decision = "fail"
    elif require_human_labels and unlabeled:
        decision = "pending_approval"
    elif advisory_enabled and below_threshold:
        decision = "pending_approval"
    else:
        decision = "pass"

    scores = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "round": round_number,
        "pass_threshold": pass_threshold,
        "deterministic_gates": {"all_passed": all_passed, "per_item": per_item},
        "advisory": {"enabled": advisory_enabled, "items": advisory_items},
        "human_labels": label_rows,
        "decision": decision,
    }
    # `ok` means "nothing is wrong with this batch". A pending approval is not a
    # failure: the artifacts are sound and a person still has to look at them.
    return EvaluationResult(ok=decision in ("pass", "pending_approval"), scores=scores)


def summarize_numeric(scores: dict, pass_threshold: float) -> dict:
    """Condense one round's numeric assessment for the durable ledger.

    The ledger must be able to answer "which round scored best" without the
    external scores document, which lives at a caller-chosen path and can be
    overwritten. When the advisory is disabled or carries no numbers, the entry
    records that fact instead of inventing a value.
    """
    advisory = scores.get("advisory") or {}
    rows = list(advisory.get("items") or [])
    values = [float(row["score"]) for row in rows]
    gaps = sorted(
        {
            str(dimension["name"])
            for row in rows
            for dimension in (row.get("dimensions") or [])
            if dimension.get("complete", False) and float(dimension["score"]) < pass_threshold
        }
    )
    return {
        "advisory_enabled": bool(advisory.get("enabled")),
        "scored_items": len(rows),
        "best_score": max(values) if values else None,
        "mean_score": (sum(values) / len(values)) if values else None,
        "gap_dimensions": gaps,
    }


def render_scores(result: EvaluationResult) -> str:
    return json.dumps(result.scores, indent=2, sort_keys=True)
