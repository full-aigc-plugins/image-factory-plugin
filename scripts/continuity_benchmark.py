#!/usr/bin/env python3
"""Validate and aggregate continuity benchmark evidence without model calls."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import schema_lite


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
PACK_SCHEMA_PATH = SCHEMA_DIR / "continuity_benchmark.schema.json"
RUN_SCHEMA_PATH = SCHEMA_DIR / "continuity_benchmark_run.schema.json"
REPORT_SCHEMA_PATH = SCHEMA_DIR / "continuity_benchmark_report.schema.json"

SHOT_COUNTS = frozenset({4, 8, 12})
DIMENSIONS = (
    "character_identity",
    "hairstyle",
    "age",
    "wardrobe",
    "core_props",
    "scene_state",
)


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(document: object, schema_path: Path, label: str) -> dict:
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    errors = schema_lite.validate(document, _load_schema(schema_path))
    if errors:
        raise ValueError(f"{label} is invalid: {'; '.join(errors)}")
    return document


def validate_pack(pack: object) -> dict:
    """Validate one benchmark pack, including exact supported shot counts."""
    document = _validate(pack, PACK_SCHEMA_PATH, "benchmark pack")
    shot_count = len(document["shots"])
    if shot_count not in SHOT_COUNTS:
        raise ValueError("benchmark pack must contain exactly 4, 8, or 12 shots")
    identifiers = [row["id"] for row in document["shots"]]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("benchmark pack shot ids must be unique")
    return document


def validate_run(pack: dict, run: object) -> dict:
    """Validate a run against its pack without filling missing evidence."""
    document = _validate(run, RUN_SCHEMA_PATH, "benchmark run")
    if document["benchmark_id"] != pack["benchmark_id"]:
        raise ValueError("benchmark run id does not match the pack")
    if document["evidence_tier"] != pack["evidence_tier"]:
        raise ValueError("benchmark run evidence_tier does not match the pack")

    expected = [row["id"] for row in pack["shots"]]
    observed = [row["shot_id"] for row in document["labels"]]
    if len(observed) != len(set(observed)):
        raise ValueError("benchmark run shot labels must be unique")
    if set(observed) != set(expected):
        raise ValueError("benchmark run must label every pack shot exactly once")

    for row in document["labels"]:
        for dimension, truth in row["dimensions"].items():
            evidence = truth["evidence"]
            if truth["label"] == "rejected" and (
                not isinstance(evidence, str) or not evidence.strip()
            ):
                raise ValueError(
                    f"rejected {dimension} label for {row['shot_id']!r} requires evidence"
                )
            if truth["label"] == "unlabeled" and evidence is not None:
                raise ValueError(
                    f"unlabeled {dimension} label for {row['shot_id']!r} must have null evidence"
                )
    return document


def _mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _dimension_metrics(runs: list[dict]) -> dict:
    counters = {
        name: {"labeled_count": 0, "unlabeled_count": 0, "rejected_count": 0}
        for name in DIMENSIONS
    }
    for run in runs:
        for shot in run["labels"]:
            for name in DIMENSIONS:
                decision = shot["dimensions"][name]["label"]
                if decision == "unlabeled":
                    counters[name]["unlabeled_count"] += 1
                else:
                    counters[name]["labeled_count"] += 1
                    if decision == "rejected":
                        counters[name]["rejected_count"] += 1

    result = {}
    for name in DIMENSIONS:
        row = counters[name]
        labeled = row["labeled_count"]
        result[name] = {
            **row,
            "rejection_rate": (
                None if labeled == 0 else row["rejected_count"] / labeled
            ),
        }
    return result


def _metrics(runs: list[dict], minimum_sample_size: int) -> dict:
    dimensions = _dimension_metrics(runs)
    costs = [float(row["cost_usd"]) for row in runs if row["cost_usd"] is not None]
    elapsed = [
        float(row["elapsed_seconds"])
        for row in runs
        if row["elapsed_seconds"] is not None
    ]
    return {
        "run_count": len(runs),
        "sample_status": (
            "sufficient" if len(runs) >= minimum_sample_size else "insufficient_sample"
        ),
        "first_pass_rate": sum(1 for row in runs if row["first_pass"]) / len(runs),
        "mean_rework_rounds": sum(row["rework_rounds"] for row in runs) / len(runs),
        "character_drift_rate": dimensions["character_identity"]["rejection_rate"],
        "element_omission_rate": dimensions["core_props"]["rejection_rate"],
        "mean_cost_usd": _mean(costs),
        "cost_observed_runs": len(costs),
        "mean_elapsed_seconds": _mean(elapsed),
        "elapsed_observed_runs": len(elapsed),
        "dimension_metrics": dimensions,
    }


def summarize(pack: object, runs: list[object]) -> dict:
    """Build a deterministic report; synthetic evidence stays synthetic."""
    benchmark = validate_pack(pack)
    if not runs:
        raise ValueError("at least one benchmark run is required")
    validated = [validate_run(benchmark, run) for run in runs]
    run_ids = [run["run_id"] for run in validated]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("benchmark run ids must be unique")

    grouped: dict[tuple[str | None, str | None, str], list[dict]] = defaultdict(list)
    for run in validated:
        grouped[(run["model"], run["provider"], run["prompt_strategy"])].append(run)
    minimum = benchmark["minimum_sample_size"]
    strata = []
    for key in sorted(grouped, key=lambda row: tuple("" if value is None else value for value in row)):
        model, provider, prompt_strategy = key
        strata.append(
            {
                "model": model,
                "provider": provider,
                "prompt_strategy": prompt_strategy,
                "metrics": _metrics(grouped[key], minimum),
            }
        )
    report = {
        "schema_version": "1.0.0",
        "benchmark_id": benchmark["benchmark_id"],
        "evidence_tier": benchmark["evidence_tier"],
        "minimum_sample_size": minimum,
        "overall": _metrics(validated, minimum),
        "strata": strata,
    }
    errors = schema_lite.validate(report, _load_schema(REPORT_SCHEMA_PATH))
    if errors:
        raise ValueError(f"generated benchmark report is invalid: {'; '.join(errors)}")
    return report
