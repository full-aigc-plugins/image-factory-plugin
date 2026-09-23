#!/usr/bin/env python3
"""Compare advisory quality signals with human labels without tuning automatically."""

from __future__ import annotations


SCHEMA_VERSION = "1.0.0"


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


def _statistics(observations: list[tuple[float, bool]], threshold: float) -> dict:
    confusion = _confusion(observations, threshold)
    disagreements = confusion["fp"] + confusion["fn"]
    return {
        "labeled_count": len(observations),
        "agreements": len(observations) - disagreements,
        "disagreements": disagreements,
        "confusion": confusion,
    }


def build_report(scores: dict) -> dict:
    """Build calibration evidence while preserving the configured threshold."""
    threshold = float(scores["pass_threshold"])
    labels = {
        row["item_id"]: row["label"]
        for row in scores.get("human_labels", [])
        if row.get("label") in ("approved", "rejected")
    }
    overall: list[tuple[float, bool]] = []
    by_dimension: dict[str, list[tuple[float, bool]]] = {}
    for row in scores.get("advisory", {}).get("items", []):
        label = labels.get(row.get("item_id"))
        if label is None:
            continue
        accepted = label == "approved"
        overall.append((float(row["score"]), accepted))
        for dimension in row.get("dimensions") or []:
            if not dimension.get("complete", False):
                continue
            by_dimension.setdefault(str(dimension["name"]), []).append(
                (float(dimension["score"]), accepted)
            )

    candidates = []
    for value in sorted({score for score, _accepted in overall} | {threshold}):
        stats = _statistics(overall, value)
        candidates.append(
            {
                "threshold": value,
                "agreements": stats["agreements"],
                "disagreements": stats["disagreements"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": scores["batch_id"],
        "round": scores["round"],
        "configured_threshold": threshold,
        "threshold_changed": False,
        "overall": _statistics(overall, threshold),
        "dimensions": [
            {"name": name, **_statistics(observations, threshold)}
            for name, observations in sorted(by_dimension.items())
        ],
        "threshold_candidates": candidates,
    }
