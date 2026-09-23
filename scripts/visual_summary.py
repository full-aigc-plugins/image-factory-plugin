#!/usr/bin/env python3
"""Rebuild deterministic review summaries from verified receipts and scores."""

from __future__ import annotations

import html
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import artifact_collector
import atomic_json


SCHEMA_VERSION = "1.0.0"


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".summary-", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _verified_artifact(destination_dir: Path, receipt: dict) -> Path:
    destination = Path(destination_dir).resolve()
    target = (destination / receipt["path"]).resolve()
    if target != destination and destination not in target.parents:
        raise ValueError(f"receipt artifact path escapes destination: {receipt['path']!r}")
    errors = artifact_collector.verify_receipt(receipt, target)
    if errors:
        raise ValueError(f"receipt artifact verification failed: {'; '.join(errors)}")
    return target


def build_summary(
    *, receipts: dict[str, dict], scores: dict, destination_dir: Path, output_dir: Path
) -> dict:
    """Write an HTML contact sheet and JSON storyboard without copying originals."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    gates = {
        row["item_id"]: row
        for row in scores.get("deterministic_gates", {}).get("per_item", [])
    }
    advisory = {
        row["item_id"]: row for row in scores.get("advisory", {}).get("items", [])
    }
    labels = {row["item_id"]: row for row in scores.get("human_labels", [])}
    rows: list[dict] = []
    html_cards: list[str] = []
    for item_id in sorted(receipts):
        receipt = receipts[item_id]
        artifact = _verified_artifact(Path(destination_dir), receipt)
        relative = Path(os.path.relpath(artifact, output)).as_posix()
        gate = gates.get(item_id, {})
        advisory_row = advisory.get(item_id)
        label = labels.get(item_id, {"label": "unlabeled"})
        row = {
            "item_id": item_id,
            "artifact_id": receipt["artifact_id"],
            "path": receipt["path"],
            "sha256": receipt["sha256"],
            "width": receipt["width"],
            "height": receipt["height"],
            "deterministic_passed": bool(gate.get("passed", False)),
            "failures": list(gate.get("failures") or []),
            "advisory_score": None if advisory_row is None else advisory_row.get("score"),
            "human_label": label.get("label", "unlabeled"),
        }
        rows.append(row)
        failures = ", ".join(row["failures"]) or "none"
        score_text = "n/a" if row["advisory_score"] is None else str(row["advisory_score"])
        html_cards.append(
            '<article class="card">'
            f'<img src="{html.escape(quote(relative, safe="/.:_-"))}" '
            f'alt="{html.escape(item_id)}">'
            f"<h2>{html.escape(item_id)}</h2>"
            f"<p>{receipt['width']}x{receipt['height']} · gate={str(row['deterministic_passed']).lower()}</p>"
            f"<p>failures={html.escape(failures)} · advisory={html.escape(score_text)} "
            f"· human={html.escape(str(row['human_label']))}</p>"
            f"<code>{html.escape(receipt['sha256'])}</code>"
            "</article>"
        )

    index = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": scores["batch_id"],
        "round": scores["round"],
        "decision": scores["decision"],
        "items": rows,
    }
    index_path = output / "storyboard.json"
    atomic_json.write_json_atomic(index_path, index)
    contact_path = output / "contact-sheet.html"
    _write_text_atomic(
        contact_path,
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Image Factory review</title><style>"
        "body{font-family:system-ui;margin:24px;background:#f5f5f2;color:#171717}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}"
        ".card{background:white;border:1px solid #ddd;border-radius:12px;padding:14px}"
        "img{width:100%;height:260px;object-fit:contain;background:#eee}"
        "h2{font-size:18px}code{font-size:10px;overflow-wrap:anywhere}"
        "</style></head><body>"
        f"<h1>{html.escape(str(scores['batch_id']))} · round {scores['round']}</h1>"
        f"<p>decision={html.escape(str(scores['decision']))}</p>"
        f'<main class="grid">{"".join(html_cards)}</main></body></html>\n',
    )
    return {
        "contact_sheet": str(contact_path),
        "storyboard_index": str(index_path),
    }
