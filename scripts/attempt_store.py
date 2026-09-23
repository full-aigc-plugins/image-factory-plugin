#!/usr/bin/env python3
"""Durable, read-only-observable evidence for external generation attempts."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import atomic_json
import schema_lite


ATTEMPT_ID = re.compile(r"^[0-9a-f]{32}$")
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "attempt_progress.schema.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def attempt_root(job_path: Path) -> Path:
    job = Path(job_path)
    return job.parent / f"{job.name}.attempts"


def attempt_directory(job_path: Path, attempt_id: str) -> Path:
    if not ATTEMPT_ID.fullmatch(attempt_id):
        raise ValueError("attempt_id must be 32 lowercase hexadecimal characters")
    return attempt_root(job_path) / attempt_id


def _progress_path(job_path: Path, attempt_id: str) -> Path:
    return attempt_directory(job_path, attempt_id) / "progress.json"


def _events_path(job_path: Path, attempt_id: str) -> Path:
    return attempt_directory(job_path, attempt_id) / "events.jsonl"


def begin_attempt(
    job_path: Path,
    attempt_id: str,
    item_id: str,
    before_snapshot: dict,
    generation_dir: Path | None = None,
) -> dict:
    directory = attempt_directory(job_path, attempt_id)
    directory.mkdir(parents=True, exist_ok=False)
    stamp = _timestamp()
    progress = {
        "schema_version": "1.0.0",
        "attempt_id": attempt_id,
        "item_id": item_id,
        "status": "running",
        "session_id": None,
        "event_count": 0,
        "candidate_artifacts": [],
        "attributed_artifacts": [],
        "before_snapshot": {
            str(name): list(signature) for name, signature in before_snapshot.items()
        },
        "generation_dir": (
            str(Path(generation_dir).resolve(strict=False))
            if generation_dir is not None
            else None
        ),
        "started_at": stamp,
        "updated_at": stamp,
    }
    atomic_json.write_json_atomic(_progress_path(job_path, attempt_id), progress)
    return progress


def load_attempt(job_path: Path, attempt_id: str) -> dict:
    payload = json.loads(_progress_path(job_path, attempt_id).read_text(encoding="utf-8"))
    if payload.get("attempt_id") != attempt_id:
        raise ValueError("attempt progress id does not match its directory")
    violations = schema_lite.validate(
        payload, json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    if violations:
        raise ValueError(f"attempt progress does not conform to its schema: {'; '.join(violations)}")
    return payload


def append_event(job_path: Path, attempt_id: str, event: dict) -> dict:
    if not isinstance(event, dict):
        raise ValueError("attempt event must be an object")
    progress = load_attempt(job_path, attempt_id)
    events_path = _events_path(job_path, attempt_id)
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    progress["event_count"] += 1
    session_id = _find_key(event, "session_id")
    if isinstance(session_id, str) and session_id:
        progress["session_id"] = session_id
    progress["updated_at"] = _timestamp()
    atomic_json.write_json_atomic(_progress_path(job_path, attempt_id), progress)
    return progress


def finish_attempt(
    job_path: Path,
    attempt_id: str,
    *,
    status: str,
    session_id: str | None,
    candidate_artifacts: tuple[str, ...] | list[str],
    attributed_artifacts: tuple[str, ...] | list[str],
) -> dict:
    progress = load_attempt(job_path, attempt_id)
    progress.update(
        {
            "status": status,
            "session_id": session_id or progress.get("session_id"),
            "candidate_artifacts": list(candidate_artifacts),
            "attributed_artifacts": list(attributed_artifacts),
            "updated_at": _timestamp(),
        }
    )
    atomic_json.write_json_atomic(_progress_path(job_path, attempt_id), progress)
    return progress


def load_events(job_path: Path, attempt_id: str) -> list[dict]:
    path = _events_path(job_path, attempt_id)
    if not path.is_file():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def latest_attempt(job_path: Path) -> dict | None:
    root = attempt_root(job_path)
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("*/progress.json"), key=lambda path: path.stat().st_mtime_ns)
    if not candidates:
        return None
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def before_snapshot(progress: dict) -> dict:
    return {
        str(name): tuple(signature)
        for name, signature in (progress.get("before_snapshot") or {}).items()
    }


def _find_key(node: object, key: str) -> object | None:
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None
