#!/usr/bin/env python3
"""Conservative free-space gate for a generation batch."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


MINIMUM_BATCH_BYTES = 256 * 1024 * 1024
BYTES_PER_IMAGE = 64 * 1024 * 1024


@dataclass(frozen=True)
class CapacityReport:
    ok: bool
    required_bytes: int
    available_bytes: int
    checks: tuple[dict, ...]


def required_bytes(image_count: int) -> int:
    if not isinstance(image_count, int) or isinstance(image_count, bool) or image_count < 1:
        raise ValueError("image_count must be a positive integer")
    return max(MINIMUM_BATCH_BYTES, image_count * BYTES_PER_IMAGE)


def _existing_parent(path: Path) -> Path:
    candidate = Path(path).resolve(strict=False)
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def check_capacity(paths: list[Path] | tuple[Path, ...], *, image_count: int) -> CapacityReport:
    required = required_bytes(image_count)
    checks: list[dict] = []
    seen_devices: set[int] = set()
    for requested in paths:
        checked = _existing_parent(Path(requested))
        device = checked.stat().st_dev
        if device in seen_devices:
            continue
        seen_devices.add(device)
        usage = shutil.disk_usage(checked)
        checks.append(
            {
                "path": str(Path(requested)),
                "checked_path": str(checked),
                "available_bytes": usage.free,
            }
        )
    available = min((row["available_bytes"] for row in checks), default=0)
    return CapacityReport(
        ok=bool(checks) and available >= required,
        required_bytes=required,
        available_bytes=available,
        checks=tuple(checks),
    )
