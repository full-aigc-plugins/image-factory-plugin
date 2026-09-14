#!/usr/bin/env python3
"""Store one verified receipt per produced artifact, and derive the manifest from them.

The aggregate manifest used to be the only record of what a run produced, which
made it the weakest link: a single write described every artifact, so an
interruption could lose them all, and nothing re-checked the files it named. Here
each item's receipt is its own file, written atomically under its idempotency key,
and the manifest is rebuilt by reading them back.

"Verified" is not a claim about the producer; it is a recheck done on read. A
receipt is only accepted when it matches the published schema and its artifact
still matches the recorded hash, byte count, and dimensions. A tampered or missing
file is reported through `unverified_receipts` rather than being quietly dropped,
because a caller deciding what to do next needs to tell "not produced" apart from
"produced and then changed".
"""

from __future__ import annotations

import json
from pathlib import Path

import artifact_collector
import atomic_json
import schema_lite

RECEIPT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "artifact_receipt.schema.json"
)


class ReceiptError(Exception):
    """A receipt could not be stored because it is invalid or conflicts with an existing one."""


def receipt_directory(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts")


def receipt_path(job_path: Path, idempotency_key: str) -> Path:
    return receipt_directory(job_path) / f"{idempotency_key}.json"


def manifest_path(job_path: Path) -> Path:
    return Path(str(job_path) + ".receipts.json")


def _schema() -> dict:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


def write_receipt(job_path: Path, receipt: dict) -> Path:
    """Persist one receipt under its idempotency key.

    Rewriting an identical receipt is a no-op so a resumed run is idempotent. A
    *different* receipt under the same key is refused: the key identifies the
    work, so two different receipts for it mean something upstream is confused,
    and silently overwriting would hide that.
    """
    errors = schema_lite.validate(receipt, _schema())
    if errors:
        raise ReceiptError("; ".join(errors))
    key = receipt["idempotency_key"]
    target = receipt_path(job_path, key)
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ReceiptError(f"existing receipt for {key} is unreadable: {error}") from error
        if existing == receipt:
            return target
        raise ReceiptError(f"a different receipt already exists for idempotency key {key}")
    atomic_json.write_json_atomic(target, receipt)
    return target


def _scan(job_path: Path, destination_dir: Path) -> tuple[dict, dict]:
    directory = receipt_directory(job_path)
    verified: dict[str, dict] = {}
    rejected: dict[str, tuple[str, ...]] = {}
    if not directory.is_dir():
        return verified, rejected

    destination = Path(destination_dir)
    for path in sorted(directory.glob("*.json")):
        key = path.stem
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            rejected[key] = (f"receipt file is unreadable: {error}",)
            continue
        structural = list(schema_lite.validate(receipt, _schema()))
        if structural:
            rejected[key] = tuple(structural)
            continue
        artifact_errors = artifact_collector.verify_receipt(
            receipt, destination / str(receipt["path"])
        )
        if artifact_errors:
            rejected[key] = tuple(artifact_errors)
            continue
        verified[key] = receipt
    return verified, rejected


def load_verified_receipts(job_path: Path, destination_dir: Path) -> dict[str, dict]:
    return _scan(job_path, destination_dir)[0]


def unverified_receipts(job_path: Path, destination_dir: Path) -> dict[str, tuple[str, ...]]:
    return _scan(job_path, destination_dir)[1]


def rebuild_manifest(job_path: Path, receipts: dict[str, dict]) -> Path:
    rows = sorted(
        receipts.values(),
        key=lambda row: (str(row.get("item_id", "")), str(row.get("idempotency_key", ""))),
    )
    target = manifest_path(job_path)
    atomic_json.write_json_atomic(target, rows)
    return target
