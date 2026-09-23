from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_collector  # noqa: E402
import attempt_store  # noqa: E402
import capacity_preflight  # noqa: E402
import generation_runner  # noqa: E402
import image_factory_cli as cli  # noqa: E402
import job_ledger  # noqa: E402
import plan_validator  # noqa: E402
from tests.test_cli import SHIM, CliFixture  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"


def make_item() -> plan_validator.PlanItem:
    prompt = "the same apprentice studies by lamplight"
    return plan_validator.PlanItem(
        id="scene-01",
        prompt=prompt,
        round=1,
        reference_images=(),
        reference_sha256=(),
        idempotency_key=plan_validator.compute_idempotency_key(
            batch_id="diligence-story",
            item_id="scene-01",
            round_number=1,
            prompt=prompt,
            reference_sha256=(),
        ),
    )


def build_shim(base: Path) -> Path:
    if os.name == "nt":
        return Path(sys.executable)
    shim = base / "codex"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    return shim


class RuntimeFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.work = self.base / "work"
        self.work.mkdir()
        if os.name == "nt":
            (self.work / "exec").write_text(
                "import runpy, sys\n"
                "sys.argv.insert(1, 'exec')\n"
                f"runpy.run_path({str(FAKE)!r}, run_name='__main__')\n",
                encoding="utf-8",
            )
        self.generated = self.base / "generated"
        self.generated.mkdir()
        self.control_path = self.base / "control.json"
        self.binary = build_shim(self.base)
        self.previous = os.environ.get("FAKE_CODEX_CONTROL")
        os.environ["FAKE_CODEX_CONTROL"] = str(self.control_path)

    def control(self, **values: object) -> None:
        values.setdefault("generation_dir", str(self.generated))
        values.setdefault("png_source", str(REAL_PNG))
        self.control_path.write_text(json.dumps(values), encoding="utf-8")

    def run(self, callback=None, timeout: float = 5.0):
        return generation_runner.run_item(
            binary=str(self.binary),
            item=make_item(),
            round_number=1,
            workdir=self.work,
            output_dir=self.base / "messages",
            generation_dir=self.generated,
            timeout_seconds=timeout,
            progress_callback=callback,
        )

    def cleanup(self) -> None:
        if self.previous is None:
            os.environ.pop("FAKE_CODEX_CONTROL", None)
        else:
            os.environ["FAKE_CODEX_CONTROL"] = self.previous
        self._tmp.cleanup()


class StreamingAttemptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RuntimeFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_events_are_observable_before_the_process_finishes(self) -> None:
        self.fixture.control(mode="stream", stream_delay_seconds=0.4)
        seen: list[dict] = []
        finished = threading.Event()

        def invoke() -> None:
            self.fixture.run(seen.append)
            finished.set()

        thread = threading.Thread(target=invoke)
        thread.start()
        deadline = time.monotonic() + 2
        while len(seen) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreaterEqual(len(seen), 2)
        self.assertFalse(finished.is_set())
        thread.join(3)
        self.assertTrue(finished.is_set())

    def test_timeout_keeps_session_and_candidate_evidence(self) -> None:
        self.fixture.control(mode="timeout", sleep_seconds=3, session_id="session-timeout")
        outcome = self.fixture.run(timeout=0.8)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.failure.code, "timeout")
        self.assertEqual(outcome.session_id, "session-timeout")
        self.assertEqual(outcome.attempts_made, 1)

    def test_unrelated_global_image_is_not_attributed_to_reported_session(self) -> None:
        before = artifact_collector.snapshot(self.fixture.generated)
        unrelated = self.fixture.generated / "other-session" / "call-x.png"
        unrelated.parent.mkdir()
        shutil.copyfile(REAL_PNG, unrelated)
        attributed = generation_runner.attribute_candidates(
            artifact_collector.new_entries(before, artifact_collector.snapshot(self.fixture.generated)),
            "session-active",
        )
        self.assertEqual(attributed, ())

    def test_single_candidate_fallback_requires_no_reported_session(self) -> None:
        candidates = ("legacy-session/call-1.png",)
        self.assertEqual(generation_runner.attribute_candidates(candidates, None), candidates)
        self.assertEqual(generation_runner.attribute_candidates(candidates, "different"), ())

    def test_reported_saved_path_selects_the_exact_call_within_one_session(self) -> None:
        candidates = (
            "session-active/call-1.png",
            "session-active/call-2.png",
        )
        events = (
            {
                "type": "item.completed",
                "item": {
                    "type": "image_generation",
                    "saved_path": str(self.fixture.generated / "session-active" / "call-2.png"),
                },
            },
        )
        reported = generation_runner.reported_candidate_paths(
            events, self.fixture.generated
        )
        self.assertEqual(reported, ("session-active/call-2.png",))
        self.assertEqual(
            generation_runner.attribute_candidates(
                candidates, "session-active", reported
            ),
            ("session-active/call-2.png",),
        )


class AttemptStoreTests(unittest.TestCase):
    def test_events_and_progress_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / "job.json"
            attempt_id = uuid.uuid4().hex
            attempt_store.begin_attempt(job, attempt_id, "scene-01", {"old.png": (1, 2)})
            attempt_store.append_event(
                job, attempt_id, {"type": "session.started", "session_id": "session-a"}
            )
            attempt_store.finish_attempt(
                job,
                attempt_id,
                status="unknown",
                session_id="session-a",
                candidate_artifacts=("session-a/call-1.png",),
                attributed_artifacts=("session-a/call-1.png",),
            )
            progress = attempt_store.load_attempt(job, attempt_id)
            self.assertEqual(progress["session_id"], "session-a")
            self.assertEqual(progress["event_count"], 1)
            self.assertEqual(attempt_store.load_events(job, attempt_id)[0]["type"], "session.started")


class CapacityTests(unittest.TestCase):
    def test_capacity_rejects_any_checked_path_below_budget(self) -> None:
        usage = shutil._ntuple_diskusage(total=1000, used=900, free=100)
        with mock.patch.object(capacity_preflight.shutil, "disk_usage", return_value=usage):
            report = capacity_preflight.check_capacity(
                [Path("/tmp/work"), Path("/tmp/generated"), Path("/tmp/output")],
                image_count=2,
            )
        self.assertFalse(report.ok)
        self.assertGreater(report.required_bytes, 100)
        self.assertEqual(report.available_bytes, 100)

    def test_cli_capacity_failure_spends_no_call_and_writes_no_job(self) -> None:
        fixture = CliFixture()
        self.addCleanup(fixture.cleanup)
        fixture.write_plan()
        fixture.control()
        report = capacity_preflight.CapacityReport(
            ok=False,
            required_bytes=1024,
            available_bytes=10,
            checks=({"path": str(fixture.destination), "available_bytes": 10},),
        )
        with mock.patch.object(cli.capacity_preflight, "check_capacity", return_value=report), mock.patch.object(
            cli.generation_runner,
            "run_item",
            side_effect=AssertionError("capacity refusal must spend zero calls"),
        ):
            code, output = fixture.run_cli(
                "run",
                "--plan",
                str(fixture.plan_path),
                "--job",
                str(fixture.job_path),
                "--codex-bin",
                str(SHIM),
                *fixture.base_args(),
                "--approve",
                "--json",
            )
        self.assertEqual(code, cli.EXIT_FAILURE, output)
        self.assertEqual(json.loads(output)["stage"], "capacity")
        self.assertFalse(fixture.job_path.exists())


class CollectionAttributionTests(unittest.TestCase):
    def test_explicit_attributed_candidate_ignores_unrelated_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            generated = base / "generated"
            destination = base / "out"
            generated.mkdir()
            for session in ("active", "unrelated"):
                target = generated / session / "call-1.png"
                target.parent.mkdir()
                shutil.copyfile(REAL_PNG, target)
            result = artifact_collector.collect_artifact(
                item=make_item(),
                batch_id="diligence-story",
                generation_dir=generated,
                destination_dir=destination,
                before={},
                min_dimension=64,
                candidates=("active/call-1.png",),
            )
            self.assertTrue(result.ok, result.failure)
            self.assertEqual(result.receipt["source"]["session_id"], "active")

    def test_explicit_candidate_symlink_cannot_escape_generation_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            generated = base / "generated"
            destination = base / "out"
            generated.mkdir()
            outside = base / "outside.png"
            shutil.copyfile(REAL_PNG, outside)
            candidate = generated / "active" / "call-1.png"
            candidate.parent.mkdir()
            candidate.symlink_to(outside)
            with self.assertRaises(ValueError):
                artifact_collector.collect_artifact(
                    item=make_item(),
                    batch_id="diligence-story",
                    generation_dir=generated,
                    destination_dir=destination,
                    before={},
                    min_dimension=64,
                    candidates=("active/call-1.png",),
                )


class StatusObservationTests(unittest.TestCase):
    def test_status_includes_latest_attempt_progress_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_path = Path(directory) / "job.json"
            ledger = job_ledger.JobLedger(job_path)
            ledger.write(job_ledger.new_job("diligence-story"))
            before = job_path.read_bytes()
            attempt_id = uuid.uuid4().hex
            attempt_store.begin_attempt(job_path, attempt_id, "scene-01", {})
            attempt_store.append_event(
                job_path, attempt_id, {"type": "session.started", "session_id": "session-a"}
            )
            code, output = cli.run_cli(["status", "--job", str(job_path), "--json"])
            self.assertEqual(code, cli.EXIT_OK, output)
            report = json.loads(output)
            self.assertEqual(report["attempt"]["attempt_id"], attempt_id)
            self.assertEqual(report["attempt"]["event_count"], 1)
            self.assertEqual(job_path.read_bytes(), before)

    def test_watch_returns_when_attempt_progress_changes_and_does_not_mutate_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_path = Path(directory) / "job.json"
            ledger = job_ledger.JobLedger(job_path)
            ledger.write(job_ledger.new_job("diligence-story"))
            attempt_id = uuid.uuid4().hex
            attempt_store.begin_attempt(job_path, attempt_id, "scene-01", {})
            before = job_path.read_bytes()

            def publish() -> None:
                time.sleep(0.1)
                attempt_store.append_event(
                    job_path,
                    attempt_id,
                    {"type": "session.started", "session_id": "session-watch"},
                )

            thread = threading.Thread(target=publish)
            thread.start()
            code, output = cli.run_cli(
                [
                    "status",
                    "--job",
                    str(job_path),
                    "--watch",
                    "--watch-timeout",
                    "2",
                    "--poll-interval",
                    "0.02",
                    "--json",
                ]
            )
            thread.join(2)
            self.assertEqual(code, cli.EXIT_OK, output)
            report = json.loads(output)
            self.assertFalse(report["watch_timed_out"])
            self.assertEqual(report["attempt"]["session_id"], "session-watch")
            self.assertEqual(job_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
