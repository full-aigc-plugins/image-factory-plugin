#!/usr/bin/env python3
"""Durable, schema-checked storage for per-item artifact receipts."""

from __future__ import annotations

import json
from pathlib import Path

import artifact_collector
import atomic_json
import schema_lite


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "artifact_receipt.schema.json"


class ReceiptStoreError(ValueError):
    """A receipt is malformed, duplicated, unreadable, or fails artifact verification."""


def receipt_directory(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts")


def receipt_path(job_path: Path, idempotency_key: str) -> Path:
    return receipt_directory(job_path) / f"{idempotency_key}.json"


def manifest_path(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts.json")


def _validate(receipt: object, source: Path | None = None) -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    violations = schema_lite.validate(receipt, schema)
    if violations:
        location = f" at {source}" if source is not None else ""
        raise ReceiptStoreError(
            f"receipt{location} does not conform to its schema: {'; '.join(violations)}"
        )
    assert isinstance(receipt, dict)
    return receipt


def write_receipt(job_path: Path, receipt: dict) -> Path:
    validated = _validate(receipt)
    target = receipt_path(job_path, validated["idempotency_key"])
    if target.exists():
        raise ReceiptStoreError(
            f"duplicate idempotency key {validated['idempotency_key']!r}"
        )
    atomic_json.write_json_atomic(target, validated)
    return target


def _artifact_path(destination_dir: Path, receipt: dict) -> Path:
    destination = Path(destination_dir).resolve()
    target = (destination / receipt["path"]).resolve()
    if target != destination and destination not in target.parents:
        raise ReceiptStoreError(f"receipt artifact path escapes destination: {receipt['path']!r}")
    return target


def load_verified_receipts(job_path: Path, destination_dir: Path) -> dict[str, dict]:
    directory = receipt_directory(job_path)
    if not directory.exists():
        return {}
    if not directory.is_dir():
        raise ReceiptStoreError(f"receipt store is not a directory: {directory}")

    loaded: dict[str, dict] = {}
    for source in sorted(directory.glob("*.json")):
        try:
            decoded = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ReceiptStoreError(f"receipt at {source} could not be read: {error}") from error
        receipt = _validate(decoded, source)
        key = receipt["idempotency_key"]
        if source.name != f"{key}.json":
            raise ReceiptStoreError(
                f"receipt filename {source.name!r} does not match idempotency key {key!r}"
            )
        if key in loaded:
            raise ReceiptStoreError(f"duplicate idempotency key {key!r}")
        artifact = _artifact_path(destination_dir, receipt)
        verification = artifact_collector.verify_receipt(receipt, artifact)
        if verification:
            raise ReceiptStoreError(
                f"receipt at {source} failed artifact verification: {'; '.join(verification)}"
            )
        loaded[key] = receipt
    return loaded


def rebuild_manifest(job_path: Path, receipts: dict[str, dict]) -> Path:
    ordered = [receipts[key] for key in sorted(receipts)]
    for receipt in ordered:
        _validate(receipt)
    target = manifest_path(job_path)
    atomic_json.write_json_atomic(target, ordered)
    return target
