#!/usr/bin/env python3
"""Exclusive, process-scoped access to one job's state.

Two `run` invocations against the same job were previously able to interleave:
both could read the same ledger revision, both could decide an item was pending,
and both could then spend an allowance call on it. The ledger write is atomic, so
the file never tore, but atomic replacement says nothing about who may *decide*.
This lock supplies that missing exclusion.

The lock is an advisory lock on a sibling `*.lock` file, using `flock` on Unix and
`msvcrt.locking` on Windows. The handle is opened once and held for the lifetime of
the context manager, because both platforms release the lock when the handle
closes: a lock whose handle is closed is not a lock.

Contention and failure are kept apart on purpose. Only genuine contention becomes
`JobAlreadyRunningError`; an unusable path or a permission problem propagates as
the original OS error, so a broken environment never masquerades as a busy one.
"""

from __future__ import annotations

import errno
import os
import time
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 0.0
POLL_INTERVAL_SECONDS = 0.05

CONTENTION_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK})

if os.name == "nt":  # pragma: no cover - exercised on Windows CI only
    import msvcrt

    def _try_lock(handle) -> bool:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError as error:
            if error.errno in CONTENTION_ERRNOS:
                return False
            raise

    def _unlock(handle) -> None:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _try_lock(handle) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as error:
            if error.errno in CONTENTION_ERRNOS:
                return False
            raise

    def _unlock(handle) -> None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


class JobAlreadyRunningError(Exception):
    """Another process is currently mutating this job."""


def lock_path_for(job_path: Path) -> Path:
    return Path(str(job_path) + ".lock")


class JobLock:
    def __init__(self, job_path: Path, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.job_path = Path(job_path)
        self.path = lock_path_for(job_path)
        self.timeout_seconds = max(0.0, float(timeout_seconds))
        self._handle = None

    def acquire(self) -> "JobLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            # Windows byte-range locking requires the region to exist.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                if _try_lock(handle):
                    self._handle = handle
                    return self
                if time.monotonic() >= deadline:
                    raise JobAlreadyRunningError(
                        f"another process is mutating {self.job_path}"
                    )
                time.sleep(POLL_INTERVAL_SECONDS)
        except BaseException:
            handle.close()
            raise

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            _unlock(handle)
        finally:
            handle.close()

    def __enter__(self) -> "JobLock":
        return self.acquire()

    def __exit__(self, *_exc) -> bool:
        self.release()
        return False
