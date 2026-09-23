#!/usr/bin/env python3
"""A stand-in for `codex exec` that behaves deterministically under test.

Behaviour is driven by a JSON control file named in the FAKE_CODEX_CONTROL
environment variable, so tests can express an outcome without standing up a real
model call. Modes:

    success       emit a normal JSONL stream, write the last-message file, exit 0
    generate      as `success`, and also drop a PNG into the generation directory
    failure       emit an error item, exit 1
    usage_limit   emit an image-generation failure carrying the image_gen limit id
    timeout       emit a session event, then sleep past any reasonable timeout
    stream        emit progress with a delay before producing an image
    silent        exit 0 without producing anything

The script records the argv it received next to the control file so a test can
assert exactly how Codex was invoked.
"""

import json
import os
import shutil
import signal
import sys
import time
import uuid
from pathlib import Path

PNG_HEADER = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\x0dIHDR"
    b"\x00\x00\x04\x00"  # width 1024
    b"\x00\x00\x04\x00"  # height 1024
    b"\x08\x06\x00\x00\x00"
)


def load_control() -> tuple[dict, Path]:
    control_path = Path(os.environ["FAKE_CODEX_CONTROL"])
    return json.loads(control_path.read_text(encoding="utf-8")), control_path


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def write_png(directory: Path, session: str, call_id: str, source: Path | None) -> Path:
    """Write a distinct image per call, the way a real generator would.

    A trailing comment is appended after IEND so two calls never produce byte
    identical files. PNG readers ignore trailing data and this plugin only reads
    the IHDR header, so the artifact stays a valid image.
    """
    target = directory / session / f"{call_id}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source is not None and Path(source).is_file():
        payload = Path(source).read_bytes()
    else:
        payload = PNG_HEADER + b"\x00" * 64
    target.write_bytes(payload + f"\n# {session}/{call_id}\n".encode())
    return target


def next_call_id(control_path: Path, override: str | None) -> str:
    """Give every invocation its own call id.

    A real generator names each output differently, and a batch that reused one
    name would overwrite its own earlier results. A counter next to the control
    file keeps runs reproducible while still being unique per invocation.
    """
    if override:
        return override
    counter_file = control_path.parent / "fake-codex-calls"
    try:
        current = int(counter_file.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        current = 0
    counter_file.write_text(str(current + 1), encoding="utf-8")
    return f"call-{current + 1}"


def main() -> int:
    control, control_path = load_control()
    argv = sys.argv[1:]
    (control_path.parent / "fake-codex-argv.json").write_text(
        json.dumps({"argv": argv}, indent=2), encoding="utf-8"
    )
    invocation_dir = control.get("invocation_dir")
    if invocation_dir:
        evidence_dir = Path(invocation_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence = evidence_dir / f"{os.getpid()}-{uuid.uuid4().hex}.json"
        temporary = evidence.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "argv": argv}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, evidence)
    delay = float(control.get("delay_before_result_seconds", 0))
    if delay:
        time.sleep(delay)

    if control.get("mode") == "signal":
        os.kill(os.getpid(), signal.SIGTERM)

    mode = control.get("mode", "success")
    session = control.get("session_id", "session-fake")
    call_id = next_call_id(control_path, control.get("call_id"))

    last_message = None
    if "-o" in argv:
        last_message = Path(argv[argv.index("-o") + 1])
    elif "--output-last-message" in argv:
        last_message = Path(argv[argv.index("--output-last-message") + 1])

    if mode == "timeout":
        emit({"type": "session.started", "session_id": session})
        time.sleep(float(control.get("sleep_seconds", 30)))
        return 0

    if mode == "usage_limit":
        emit(
            {
                "type": "item.completed",
                "item": {
                    "type": "image_generation",
                    "failure": {
                        "type": "usage_limit_exceeded",
                        "limit_id": control.get("limit_id", "image_gen"),
                        "resets_at": control.get("resets_at", 1800000000),
                    },
                },
            }
        )
        if last_message is not None:
            last_message.parent.mkdir(parents=True, exist_ok=True)
            last_message.write_text("image generation usage limit reached\n", encoding="utf-8")
        return 1

    if mode == "failure":
        emit({"type": "error", "message": control.get("message", "the model call failed")})
        if last_message is not None:
            last_message.parent.mkdir(parents=True, exist_ok=True)
            last_message.write_text("failed\n", encoding="utf-8")
        return 1

    if mode == "silent":
        return 0

    produced = None
    generation_dir = control.get("generation_dir")
    if mode == "stream":
        emit({"type": "session.started", "session_id": session})
        emit({"type": "item.started", "item": {"type": "image_generation"}})
        time.sleep(float(control.get("stream_delay_seconds", 0.25)))
    if mode in ("generate", "stream") and generation_dir:
        produced = write_png(
            Path(generation_dir),
            session,
            call_id,
            control.get("png_source"),
        )

    if mode != "stream":
        emit({"type": "session.started", "session_id": session})
    emit(
        {
            "type": "item.completed",
            "item": {
                "type": "image_generation",
                "saved_path": str(produced) if produced else None,
            },
        }
    )
    emit({"type": "session.completed", "session_id": session})

    if last_message is not None:
        last_message.parent.mkdir(parents=True, exist_ok=True)
        last_message.write_text(
            str(produced) if produced else "no image was produced\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
