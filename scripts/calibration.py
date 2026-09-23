#!/usr/bin/env python3
"""Compare advisory quality signals with human labels without tuning automatically."""

from __future__ import annotations

import math

SCHEMA_VERSION = "1.1.0"
STRATA_AXES = ("model", "provider", "style", "shot_type")
_WILSON_Z = 1.959963984540054


def _rate_interval(successes: int, trials: int) -> dict:
    if trials == 0:
        return {"value": None, "interval": {"method": "wilson-95-v1", "low": None, "high": None}}
    p = successes / trials
    z2 = _WILSON_Z * _WILSON_Z
    denominator = 1 + z2 / trials
    center = (p + z2 / (2 * trials)) / denominator
    radius = _WILSON_Z * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials)) / denominator
    return {"value": p, "interval": {"method": "wilson-95-v1", "low": max(0.0, center - radius), "high": min(1.0, center + radius)}}


def _confusion(observations: list[tuple[float, bool]], threshold: float) -> dict:
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for score, accepted in observations:
        predicted = score >= threshold
        if predicted and accepted:
            counts["tp"] += 1
        elif predicted:
            counts["fp"] += 1
        elif accepted:
            counts["fn"] += 1
        else:
            counts["tn"] += 1
    return counts


def _statistics(observations: list[tuple[float, bool]], threshold: float, min_samples: int) -> dict:
    confusion = _confusion(observations, threshold)
    disagreements = confusion["fp"] + confusion["fn"]
    return {
        "labeled_count": len(observations),
        "agreements": len(observations) - disagreements,
        "disagreements": disagreements,
        "confusion": confusion,
        "sample_sufficient": len(observations) >= min_samples,
        "false_positive_rate": _rate_interval(confusion["fp"], confusion["fp"] + confusion["tn"]),
        "false_negative_rate": _rate_interval(confusion["fn"], confusion["fn"] + confusion["tp"]),
    }


def build_report(
    scores: dict,
    *,
    min_samples: int = 30,
    item_context: dict[str, dict] | None = None,
    approved_baseline: dict | None = None,
    drift_tolerance: float = 0.05,
) -> dict:
    """Build calibration evidence while preserving the configured threshold."""
    if type(min_samples) is not int or min_samples < 2:
        raise ValueError("min_samples must be at least 2")
    if not 0 <= drift_tolerance <= 1:
        raise ValueError("drift_tolerance must be between 0 and 1")
    item_context = item_context or {}
    if not isinstance(item_context, dict) or any(
        not isinstance(item_id, str) or not isinstance(metadata, dict)
        or any(axis not in STRATA_AXES or not isinstance(value, str) or not value for axis, value in metadata.items())
        for item_id, metadata in item_context.items()
    ):
        raise ValueError("item_context must map item ids to nonempty model/provider/style/shot_type strings")
    if approved_baseline is not None:
        if (not isinstance(approved_baseline, dict) or approved_baseline.get("approved") is not True
                or not isinstance(approved_baseline.get("reviewer_id"), str)
                or not isinstance(approved_baseline.get("reviewer_version"), str)
                or not isinstance(approved_baseline.get("false_positive_rate"), (int, float))
                or not 0 <= approved_baseline["false_positive_rate"] <= 1
                or type(approved_baseline.get("min_samples")) is not int
                or approved_baseline["min_samples"] < 2):
            raise ValueError("approved baseline requires approval, reviewer id/version, false-positive rate and minimum sample count")
    threshold = float(scores["pass_threshold"])
    labels = {
        row["item_id"]: row["label"]
        for row in scores.get("human_labels", [])
        if row.get("label") in ("approved", "rejected")
    }
    overall: list[tuple[float, bool]] = []
    by_dimension: dict[str, list[tuple[float, bool]]] = {}
    strata: dict[tuple[str, str], list[tuple[float, bool]]] = {}
    for row in scores.get("advisory", {}).get("items", []):
        label = labels.get(row.get("item_id"))
        if label is None:
            continue
        accepted = label == "approved"
        overall.append((float(row["score"]), accepted))
        for axis in STRATA_AXES:
            value = item_context.get(row["item_id"], {}).get(axis)
            if isinstance(value, str) and value:
                strata.setdefault((axis, value), []).append((float(row["score"]), accepted))
        for dimension in row.get("dimensions") or []:
            if not dimension.get("complete", False):
                continue
            by_dimension.setdefault(str(dimension["name"]), []).append(
                (float(dimension["score"]), accepted)
            )

    candidates = []
    if len(overall) >= min_samples:
        for value in sorted({score for score, _accepted in overall} | {threshold}):
            stats = _statistics(overall, value, min_samples)
            candidates.append({"threshold": value, "agreements": stats["agreements"], "disagreements": stats["disagreements"]})
    reviewer_versions = sorted({(str(report.get("reviewer", {}).get("id")), str(report.get("reviewer", {}).get("version"))) for report in scores.get("reviewer_reports", [])})
    current_reviewer = reviewer_versions[0] if len(reviewer_versions) == 1 else None
    current_fpr = _statistics(overall, threshold, min_samples)["false_positive_rate"]["value"]
    baseline_fpr = None if approved_baseline is None else approved_baseline.get("false_positive_rate")
    comparable = (
        current_reviewer is not None and approved_baseline is not None
        and current_reviewer[0] == approved_baseline.get("reviewer_id")
        and current_reviewer[1] != approved_baseline.get("reviewer_version")
        and current_fpr is not None and isinstance(baseline_fpr, (int, float))
        and len(overall) >= approved_baseline.get("min_samples", min_samples)
    )
    drift = {
        "baseline_reviewer_version": None if approved_baseline is None else approved_baseline.get("reviewer_version"),
        "current_reviewer_version": None if current_reviewer is None else current_reviewer[1],
        "baseline_false_positive_rate": baseline_fpr,
        "current_false_positive_rate": current_fpr,
        "tolerance": drift_tolerance,
        "comparable": comparable,
        "review_required": bool(comparable and current_fpr - baseline_fpr > drift_tolerance),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": scores["batch_id"],
        "round": scores["round"],
        "configured_threshold": threshold,
        "threshold_changed": False,
        "minimum_samples": min_samples,
        "overall": _statistics(overall, threshold, min_samples),
        "dimensions": [
            {"name": name, **_statistics(observations, threshold, min_samples)}
            for name, observations in sorted(by_dimension.items())
        ],
        "strata": [
            {"axis": axis, "value": value, **_statistics(observations, threshold, min_samples)}
            for (axis, value), observations in sorted(strata.items())
        ],
        "drift": drift,
        "threshold_candidates": candidates,
    }
