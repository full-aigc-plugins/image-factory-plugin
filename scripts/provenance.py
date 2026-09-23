#!/usr/bin/env python3
"""Build honest, reproducible provenance for collected image artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


def capability_signature(report: dict | None) -> str | None:
    """Hash the observed capability report, or return null when none was observed."""
    if report is None:
        return None
    encoded = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def detect_plugin_revision(repo_root: Path | None = None) -> str | None:
    """Return an explicit or Git-observed plugin revision without inventing one."""
    explicit = os.environ.get("IMAGE_FACTORY_PLUGIN_REVISION")
    if explicit:
        return explicit
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = completed.stdout.strip()
    if not revision:
        return None
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        dirty = ""
    return f"{revision}-dirty" if dirty else revision


def build_provenance(
    *,
    plugin_revision: str | None = None,
    host_version: str | None = None,
    codex_version: str | None = None,
    capability_report: dict | None = None,
    reviewer_version: str | None = None,
    consistency_profile_sha256: str | None = None,
) -> dict:
    """Return provenance containing only values actually supplied or observed."""
    return {
        "plugin_revision": plugin_revision,
        "host_version": host_version,
        "codex_version": codex_version,
        "capability_signature": capability_signature(capability_report),
        "reviewer_version": reviewer_version,
        "consistency_profile_sha256": consistency_profile_sha256,
    }
