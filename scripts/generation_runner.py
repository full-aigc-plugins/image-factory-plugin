#!/usr/bin/env python3
"""Drive one generation step by invoking Codex, and decide honestly whether it worked.

The plugin does not generate images. It asks Codex to, once, and then checks the
filesystem for evidence. That ordering produces the single most important rule
here: an exit code of zero is a claim, not a result. A step is successful only
when a new image file appeared in the generation directory, so a run that reports
success without producing anything is recorded as a failure rather than as a
completed item.

Three further rules are enforced by construction rather than by policy:

* Every attempt is a fresh argv-array subprocess. There is no retry loop inside
  this module, because a silent retry is how one bad prompt becomes a large bill.
* The approval-bypass flags are never passed. Whatever approval posture the user
  configured for Codex stays in force.
* An exhausted usage limit is classified, its reset time is recorded, and the
  attempt stops there.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from artifact_collector import new_entries, snapshot

DEFAULT_TIMEOUT_SECONDS = 600.0
IMAGE_LIMIT_ID = "image_gen"

# Stable wrapper telling Codex what this invocation is for. Kept minimal and
# constant so the author's prompt stays the only variable part of a request.
GENERATION_INSTRUCTION = (
    "Generate exactly one image with the built-in image generation tool. "
    "Treat any attached images as visual references for the result. "
    "Do not modify or create any other file. "
    "When you are done, reply with the absolute path of the generated image.\n\n"
    "Image description:\n"
)

# Never passed, and asserted against in tests: these would silently widen what a
# batch run is allowed to do to the machine.
FORBIDDEN_FLAGS = (
    "--dangerously-bypass-approvals-and-sandbox",
    "--yolo",
    "--dangerously-bypass-hook-trust",
)


@dataclass(frozen=True)
class GenerationFailure:
    code: str
    message: str
    limit_id: str | None = None
    resets_at: int | None = None


@dataclass(frozen=True)
class GenerationOutcome:
    ok: bool
    failure: GenerationFailure | None = None
    session_id: str | None = None
    last_message: str = ""
    events: tuple[dict, ...] = ()
    exit_code: int | None = None
    attempts_made: int = 0
    new_files: tuple[str, ...] = ()
    attributed_files: tuple[str, ...] = ()
    before_snapshot: dict = field(default_factory=dict)


def build_prompt(prompt: str) -> str:
    return GENERATION_INSTRUCTION + prompt


def build_argv(
    *,
    binary: str,
    prompt: str,
    reference_images: tuple[str, ...] | list[str],
    workdir: Path,
    last_message_path: Path,
) -> list[str]:
    """Build the Codex invocation as an argv array; a shell string is never used."""
    argv = [
        binary,
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--color",
        "never",
        "-C",
        str(workdir),
        "-o",
        str(last_message_path),
    ]
    for reference in reference_images:
        argv.extend(["-i", str(reference)])
    if reference_images:
        argv.append("--")
    argv.append(build_prompt(prompt))
    return argv


def build_item_argv(
    *,
    binary: str,
    item: object,
    workdir: Path,
    last_message_path: Path,
) -> list[str]:
    """Build one invocation from the validator's effective generation inputs."""
    effective_prompt = getattr(item, "effective_prompt", "") or getattr(item, "prompt")
    return build_argv(
        binary=binary,
        prompt=effective_prompt,
        reference_images=getattr(item, "reference_images"),
        workdir=workdir,
        last_message_path=last_message_path,
    )


def _parse_events(stdout: str) -> tuple[dict, ...]:
    events: list[dict] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            payload = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return tuple(events)


def _usage_limit_failure(stdout: str, stderr: str, events: tuple[dict, ...]) -> GenerationFailure | None:
    """Detect an exhausted image allowance without matching on the limit id alone.

    Matching the substring "image_gen" would fire on the ordinary
    `image_generation` item, so detection keys on the failure marker instead and
    the limit id is only read out of an event already known to be a limit event.
    """
    markers = ("usage_limit_exceeded", "usagelimitexceeded", "usage limit", "rate limit", "quota")
    source: dict | None = None
    for event in events:
        lowered = json.dumps(event).lower()
        if any(marker in lowered for marker in markers):
            source = event
            break
    if source is None:
        lowered_error = (stderr or "").lower()
        if any(marker in lowered_error for marker in ("usage limit", "rate limit", "quota")):
            source = {}

    if source is None:
        return None

    limit_id = _find_key(source, "limit_id")
    if not isinstance(limit_id, str):
        limit_id = IMAGE_LIMIT_ID
    resets_at = _find_key(source, "resets_at")
    if not isinstance(resets_at, int):
        resets_at = None
    return GenerationFailure(
        code="quota_exceeded",
        message="the image generation usage limit for this account was reached",
        limit_id=limit_id,
        resets_at=resets_at,
    )


def _error_message(events: tuple[dict, ...], stderr: str) -> str:
    """Prefer the event stream's own error text; fall back to stderr, then to the exit code."""
    for event in events:
        if event.get("type") == "error" and isinstance(event.get("message"), str):
            return event["message"]
    for event in events:
        candidate = _find_key(event, "message")
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    lines = [line for line in (stderr or "").strip().splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return "codex exited without reporting a reason"


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


def _session_id(events: tuple[dict, ...], new_files: tuple[str, ...]) -> str | None:
    for event in events:
        if event.get("type") == "session.started" and isinstance(event.get("session_id"), str):
            return event["session_id"]
    for event in events:
        candidate = _find_key(event, "session_id")
        if isinstance(candidate, str):
            return candidate
    if new_files:
        parts = Path(new_files[0]).parts
        if len(parts) >= 2:
            return parts[-2]
    return None


def reported_candidate_paths(
    events: tuple[dict, ...], generation_dir: Path
) -> tuple[str, ...]:
    """Return safe generation-relative paths explicitly reported by Codex."""
    root = Path(generation_dir).resolve(strict=False)
    reported: list[str] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("saved_path", "output_path", "artifact_path") and isinstance(value, str) and value:
                    candidate = Path(value)
                    absolute = (
                        candidate.resolve(strict=False)
                        if candidate.is_absolute()
                        else (root / candidate).resolve(strict=False)
                    )
                    try:
                        relative = absolute.relative_to(root).as_posix()
                    except ValueError:
                        continue
                    if relative.lower().endswith(".png"):
                        reported.append(relative)
                else:
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for event in events:
        visit(event)
    return tuple(dict.fromkeys(reported))


def attribute_candidates(
    candidates: tuple[str, ...],
    session_id: str | None,
    reported_paths: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Select candidates owned by the reported session, with one legacy fallback.

    A reported session is authoritative: a file under another session must never
    be collected merely because it appeared during the same wall-clock window.
    Older Codex streams that report no session retain the strict single-file
    fallback for compatibility.
    """
    if session_id:
        session_candidates = tuple(
            candidate
            for candidate in candidates
            if session_id in Path(candidate).parts[:-1]
        )
        if reported_paths:
            reported = set(reported_paths)
            return tuple(
                candidate for candidate in session_candidates if candidate in reported
            )
        return session_candidates
    if reported_paths:
        reported = set(reported_paths)
        exact = tuple(candidate for candidate in candidates if candidate in reported)
        return exact if len(exact) == 1 else ()
    return candidates if len(candidates) == 1 else ()


def _stream_process(
    process: subprocess.Popen,
    *,
    timeout_seconds: float,
    progress_callback: Callable[[dict], None] | None,
) -> tuple[int, str, str, tuple[dict, ...], bool]:
    """Consume both pipes concurrently and publish parsed events immediately."""
    messages: queue.Queue[tuple[str, str | None]] = queue.Queue()

    def reader(name: str, stream: object) -> None:
        try:
            for line in stream:  # type: ignore[union-attr]
                messages.put((name, line))
        finally:
            messages.put((name, None))

    assert process.stdout is not None and process.stderr is not None
    threads = [
        threading.Thread(target=reader, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=reader, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    stdout: list[str] = []
    stderr: list[str] = []
    events: list[dict] = []
    closed: set[str] = set()
    deadline = time.monotonic() + timeout_seconds
    timed_out = False

    while len(closed) < 2:
        remaining = deadline - time.monotonic()
        if remaining <= 0 and process.poll() is None:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            continue
        try:
            source, line = messages.get(timeout=max(0.01, min(0.1, max(remaining, 0.01))))
        except queue.Empty:
            if process.poll() is not None and all(not thread.is_alive() for thread in threads):
                break
            continue
        if line is None:
            closed.add(source)
            continue
        if source == "stdout":
            stdout.append(line)
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    event = json.loads(stripped)
                except ValueError:
                    event = None
                if isinstance(event, dict):
                    events.append(event)
                    if progress_callback is not None:
                        try:
                            progress_callback(event)
                        except BaseException:
                            if process.poll() is None:
                                process.terminate()
                                try:
                                    process.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                            process.stdout.close()
                            process.stderr.close()
                            raise
        else:
            stderr.append(line)

    for thread in threads:
        thread.join(timeout=1)
    process.stdout.close()
    process.stderr.close()
    return process.wait(), "".join(stdout), "".join(stderr), tuple(events), timed_out


def run_item(
    *,
    binary: str,
    item: object,
    round_number: int,
    workdir: Path,
    output_dir: Path,
    generation_dir: Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    progress_callback: Callable[[dict], None] | None = None,
    before_snapshot: dict | None = None,
) -> GenerationOutcome:
    """Invoke Codex once for one batch item. Never retries."""
    workdir = Path(workdir)
    output_dir = Path(output_dir)
    generation_dir = Path(generation_dir)
    workdir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    last_message_path = output_dir / f"{getattr(item, 'id')}-round-{round_number}.last-message.txt"
    before = snapshot(generation_dir) if before_snapshot is None else dict(before_snapshot)
    argv = build_item_argv(
        binary=binary,
        item=item,
        workdir=workdir,
        last_message_path=last_message_path,
    )

    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(workdir),
        )
        return_code, stdout, stderr, events, timed_out = _stream_process(
            process,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError) as error:
        return GenerationOutcome(
            ok=False,
            failure=GenerationFailure("codex_missing", f"codex could not be executed: {error}"),
            attempts_made=1,
            before_snapshot=before,
        )

    last_message = ""
    try:
        last_message = last_message_path.read_text(encoding="utf-8")
    except OSError:
        last_message = ""

    common = {
        "session_id": None,
        "last_message": last_message,
        "events": events,
        "exit_code": return_code,
        "attempts_made": 1,
    }

    after = snapshot(generation_dir)
    fresh = new_entries(before, after)
    session_id = _session_id(events, fresh)
    reported_paths = reported_candidate_paths(events, generation_dir)
    attributed = attribute_candidates(fresh, session_id, reported_paths)
    common.update(
        {
            "session_id": session_id,
            "new_files": fresh,
            "attributed_files": attributed,
        }
    )

    if timed_out:
        return GenerationOutcome(
            ok=False,
            failure=GenerationFailure(
                "timeout",
                f"codex did not finish within {timeout_seconds:.0f}s; it is not retried automatically",
            ),
            before_snapshot=before,
            **common,
        )

    if return_code < 0:
        return GenerationOutcome(
            ok=False,
            failure=GenerationFailure(
                "interrupted",
                f"codex was terminated by signal {-return_code}; its external outcome is unknown",
            ),
            before_snapshot=before,
            **common,
        )

    limit = _usage_limit_failure(stdout, stderr, events)
    if limit is not None:
        return GenerationOutcome(ok=False, failure=limit, before_snapshot=before, **common)

    if return_code != 0:
        return GenerationOutcome(
            ok=False,
            failure=GenerationFailure("generation_failed", _error_message(events, stderr)),
            before_snapshot=before,
            **common,
        )

    if not attributed:
        return GenerationOutcome(
            ok=False,
            failure=GenerationFailure(
                "artifact_missing",
                "codex reported success but no image was attributable to the active attempt",
            ),
            before_snapshot=before,
            **common,
        )

    return GenerationOutcome(
        ok=True,
        before_snapshot=before,
        **common,
    )


def as_report(outcome: GenerationOutcome) -> dict:
    return {
        "ok": outcome.ok,
        "failure": (
            {
                "code": outcome.failure.code,
                "message": outcome.failure.message,
                "limit_id": outcome.failure.limit_id,
                "resets_at": outcome.failure.resets_at,
            }
            if outcome.failure
            else None
        ),
        "session_id": outcome.session_id,
        "last_message": outcome.last_message,
        "exit_code": outcome.exit_code,
        "attempts_made": outcome.attempts_made,
        "new_files": list(outcome.new_files),
        "attributed_files": list(outcome.attributed_files),
    }


def resolved_binary(explicit: str | None = None) -> str:
    """Pick the Codex binary to invoke, preferring an explicit path."""
    if explicit:
        return explicit
    import shutil

    found = shutil.which("codex")
    if found:
        return found
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    bundled = home / "plugins" / ".plugin-appserver" / "codex"
    if bundled.is_file():
        return str(bundled)
    return "codex"
