#!/usr/bin/env python3
"""Validate versioned visual reviewer reports while preserving advisory authority."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import schema_lite


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "reviewer_report.schema.json"


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
