#!/usr/bin/env python3
"""Build a launcher for the fake Codex CLI on any supported host.

A shell script is not a launcher on Windows, so the CI matrix would silently skip
every test that needs a second process there. This module owns the platform
difference in one place, so each test file asks for a launcher instead of
repeating a Unix-only assumption.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

LAUNCHER_NAME = "codex"


def interpreter() -> str:
    """Prefer the plain framework interpreter over Python.app on macOS.

    Launching inside Python.app costs extra through the app-bundle machinery,
    which is pure test overhead: production invokes the real Codex binary.
    """
    candidate = Path(sys.base_prefix) / "bin" / ("python.exe" if os.name == "nt" else "python3")
    if candidate.is_file():
        return str(candidate)
    return sys.executable


def launcher_suffix() -> str:
    return ".cmd" if os.name == "nt" else ""


def build_launcher(directory: Path, script: Path, name: str = LAUNCHER_NAME) -> Path:
    """Create an executable that runs `script` with this interpreter."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}{launcher_suffix()}"
    python = interpreter()
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI only
        target.write_text(f'@echo off\r\n"{python}" "{script}" %*\r\n', encoding="utf-8")
    else:
        target.write_text(f'#!/bin/sh\nexec "{python}" "{script}" "$@"\n', encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def build_shared_launcher(directory: Path, script: Path, name: str = LAUNCHER_NAME) -> Path:
    """One launcher per interpreter session.

    macOS evaluates a newly written executable on first run, which costs about
    half a second. Building one launcher and reusing it keeps that cost off every
    individual test.
    """
    return build_launcher(directory, script, name)
