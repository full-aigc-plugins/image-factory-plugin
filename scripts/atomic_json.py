#!/usr/bin/env python3
"""Write a JSON document so a reader never observes a partially written file.

The sequence is the same one the ledger already relied on, extracted here because
receipts and scores need it too: serialize into a temporary file in the same
directory, flush and fsync it, rename it over the target, then best-effort fsync
the directory so the rename itself is durable.

Two properties matter and are both asserted in tests. A failure before the rename
leaves the previous document exactly as it was, and no temporary file survives any
outcome. Callers therefore get all-or-nothing at the document level rather than a
half-written file that still parses as JSON sometimes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

TEMPORARY_PREFIX = ".atomic-"
TEMPORARY_SUFFIX = ".tmp"


def _fsync_directory(directory: Path) -> None:
    """Persist the rename itself where the platform supports it."""
    try:
        handle = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def write_json_atomic(path: Path, payload: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=TEMPORARY_PREFIX, suffix=TEMPORARY_SUFFIX
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            # Deliberately json.dump rather than dumps: the stream is the thing
            # being made atomic, and serialising straight into it avoids holding a
            # second full copy of a receipt manifest in memory.
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
