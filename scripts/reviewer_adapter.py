#!/usr/bin/env python3
"""Validate versioned visual reviewer reports while preserving advisory authority."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import schema_lite


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "reviewer_report.schema.json"

EVALUATOR_DIMENSIONS = frozenset(
    {
        "character_identity",
        "wardrobe",
        "prop_continuity",
        "style",
        "scene_state",
        "text_absence",
        "aspect_ratio",
    }
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def adapt(report: object) -> dict:
    """Return a normalized advisory report and mark low-confidence findings.

    This adapter performs no visual inference and never produces a verdict. Its
    output deliberately retains every finding so future ensemble logic can show
    disagreement instead of selecting a convenient score.
    """
    if not isinstance(report, dict):
        raise ValueError("reviewer report must be a JSON object")
    errors = schema_lite.validate(report, _schema())
    if errors:
        raise ValueError(f"reviewer report is invalid: {'; '.join(errors)}")

    normalized = copy.deepcopy(report)
    threshold = float(normalized["reviewer"]["confidence_threshold"])
    seen_items: set[str] = set()
    for item in normalized["items"]:
        item_id = item["item_id"]
        if item_id in seen_items:
            raise ValueError(f"reviewer report repeats item {item_id!r}")
        seen_items.add(item_id)
        seen_dimensions: set[str] = set()
        for finding in item["findings"]:
            dimension = finding["dimension"]
            if dimension in seen_dimensions:
                raise ValueError(
                    f"reviewer report repeats dimension {dimension!r} for {item_id!r}"
                )
            seen_dimensions.add(dimension)
            finding["uncertain"] = float(finding["confidence"]) < threshold
    normalized["authority"] = "advisory"
    return normalized


def merge_advisory(reports: list[dict]) -> dict:
    """Merge confident findings for evaluation while retaining raw reports.

    Uncertain findings are intentionally absent from the decision signal. They
    remain in ``reviewer_reports`` in the scores document for human inspection
    and later calibration. Multiple confident findings are averaged only in the
    derived advisory; their individual values and sources remain intact.
    """
    per_item: dict[str, list[tuple[str, dict]]] = {}
    for report in reports:
        reviewer_id = report["reviewer"]["id"]
        for item in report["items"]:
            for finding in item["findings"]:
                if finding["uncertain"]:
                    continue
                per_item.setdefault(item["item_id"], []).append((reviewer_id, finding))

    advisory = {}
    for item_id, sourced in sorted(per_item.items()):
        by_dimension: dict[str, list[tuple[str, dict]]] = {}
        for reviewer_id, finding in sourced:
            if finding["dimension"] in EVALUATOR_DIMENSIONS:
                by_dimension.setdefault(finding["dimension"], []).append(
                    (reviewer_id, finding)
                )
        dimensions = []
        for name, rows in sorted(by_dimension.items()):
            score = sum(float(row["score"]) for _reviewer, row in rows) / len(rows)
            evidence = " | ".join(
                f"{reviewer}: {row['evidence']}" for reviewer, row in rows
            )
            dimensions.append({"name": name, "score": score, "evidence": evidence})
        score = sum(float(row["score"]) for _reviewer, row in sourced) / len(sourced)
        reason = " | ".join(
            f"{reviewer}/{row['dimension']}: {row['evidence']}"
            for reviewer, row in sourced
        )
        entry = {"score": score, "reason": reason}
        if dimensions:
            entry["dimensions"] = dimensions
        advisory[item_id] = entry
    return advisory
