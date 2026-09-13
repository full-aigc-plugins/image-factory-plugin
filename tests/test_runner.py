import atexit
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generation_runner as runner  # noqa: E402
import plan_validator  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"


def fast_python() -> str:
    """Prefer the plain framework interpreter over Python.app.

    On macOS `sys.executable` can point inside Python.app, and launching that
    costs extra through the app-bundle machinery. That is pure test overhead:
    production invokes the real Codex binary.
    """
    candidate = Path(sys.base_prefix) / "bin" / "python3"
    if candidate.is_file():
        return str(candidate)
    return sys.executable


def _build_shared_shim() -> Path:
    """Create the fake-codex shim once for the whole module.

    macOS performs a security evaluation the first time each newly written
    executable is run, which costs about half a second. Building one shim for the
    module keeps that cost off every individual test.
    """
    directory = Path(tempfile.mkdtemp(prefix="image-factory-codex-shim-"))
    atexit.register(shutil.rmtree, directory, True)
    shim = directory / "codex"
    shim.write_text(f'#!/bin/sh\nexec "{fast_python()}" "{FAKE}" "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


SHIM = _build_shared_shim()


def make_item(item_id: str = "item-01", prompt: str = "a calm portrait", references: tuple[str, ...] = ()) -> plan_validator.PlanItem:
    return plan_validator.PlanItem(
        id=item_id,
        prompt=prompt,
        round=1,
        reference_images=references,
        reference_sha256=(),
        idempotency_key=plan_validator.compute_idempotency_key(
            batch_id="portrait-study",
            item_id=item_id,
            round_number=1,
            prompt=prompt,
            reference_sha256=(),
        ),
    )


class RunnerFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.workdir = self.base / "work"
        self.workdir.mkdir()
        self.generation_dir = self.base / "generated_images"
        self.generation_dir.mkdir()
        self.control_path = self.base / "control.json"
        self.binary = SHIM
        self._previous_env: str | None = None

    def control(self, **values) -> None:
        values.setdefault("generation_dir", str(self.generation_dir))
        self.control_path.write_text(json.dumps(values), encoding="utf-8")
        self._previous_env = os.environ.get("FAKE_CODEX_CONTROL")
        os.environ["FAKE_CODEX_CONTROL"] = str(self.control_path)

    def recorded_argv(self) -> list[str]:
        payload = json.loads((self.base / "fake-codex-argv.json").read_text(encoding="utf-8"))
        return payload["argv"]

    def run(self, item: plan_validator.PlanItem | None = None, **overrides) -> runner.GenerationOutcome:
        kwargs = {
            "binary": str(self.binary),
            "item": item or make_item(),
            "round_number": 1,
            "workdir": self.workdir,
            "output_dir": self.base / "out",
            "generation_dir": self.generation_dir,
            "timeout_seconds": 10.0,
        }
        kwargs.update(overrides)
        return runner.run_item(**kwargs)

    def cleanup(self) -> None:
        if self._previous_env is None:
            os.environ.pop("FAKE_CODEX_CONTROL", None)
        else:
            os.environ["FAKE_CODEX_CONTROL"] = self._previous_env
        self._tmp.cleanup()


class ArgvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RunnerFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_argv_is_a_list_and_never_uses_a_shell_string(self) -> None:
        argv = runner.build_argv(
            binary="/usr/bin/codex",
            prompt="draw a portrait",
            reference_images=(),
            workdir=Path("/tmp/work"),
            last_message_path=Path("/tmp/out/last.txt"),
        )
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(part, str) for part in argv))
        self.assertEqual(argv[0], "/usr/bin/codex")
        self.assertEqual(argv[1], "exec")
        self.assertEqual(argv[-1], runner.build_prompt("draw a portrait"))

    def test_argv_never_bypasses_approvals_or_sandbox(self) -> None:
        argv = runner.build_argv(
            binary="codex",
            prompt="p",
            reference_images=(),
            workdir=Path("/tmp/work"),
            last_message_path=Path("/tmp/out/last.txt"),
        )
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertNotIn("--yolo", argv)
        self.assertNotIn("--dangerously-bypass-hook-trust", argv)

    def test_reference_images_are_attached_individually(self) -> None:
        argv = runner.build_argv(
            binary="codex",
            prompt="p",
            reference_images=("a.png", "b.png"),
            workdir=Path("/tmp/work"),
            last_message_path=Path("/tmp/out/last.txt"),
        )
        self.assertEqual(argv.count("-i"), 2)
        self.assertEqual(argv[argv.index("-i") + 1], "a.png")

    def test_reference_image_values_cannot_consume_the_prompt(self) -> None:
        argv = runner.build_argv(
            binary="codex",
            prompt="draw the next story scene",
            reference_images=("style.png",),
            workdir=Path("/tmp/work"),
            last_message_path=Path("/tmp/out/last.txt"),
        )
        self.assertEqual(argv[-2], "--")
        self.assertEqual(argv[-1], runner.build_prompt("draw the next story scene"))

    def test_prompt_is_a_single_argument(self) -> None:
        argv = runner.build_argv(
            binary="codex",
            prompt="line one\nline two",
            reference_images=(),
            workdir=Path("/tmp/work"),
            last_message_path=Path("/tmp/out/last.txt"),
        )
        self.assertIn(runner.build_prompt("line one\nline two"), argv)

    def test_built_prompt_carries_the_author_prompt_and_the_instruction(self) -> None:
        built = runner.build_prompt("a calm portrait")
        self.assertIn("a calm portrait", built)
        self.assertIn("built-in image generation tool", built)


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RunnerFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_successful_run_reports_session_and_last_message(self) -> None:
        self.fixture.control(mode="generate", png_source=str(REAL_PNG))
        result = self.fixture.run()
        self.assertTrue(result.ok, result.failure)
        self.assertEqual(result.session_id, "session-fake")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(result.new_files), 1)
        self.assertIn("session-fake", result.last_message)

    def test_generation_mode_actually_writes_an_image(self) -> None:
        self.fixture.control(mode="generate", png_source=str(REAL_PNG))
        result = self.fixture.run()
        self.assertTrue(result.ok, result.failure)
        produced = list(self.fixture.generation_dir.rglob("*.png"))
        self.assertEqual(len(produced), 1)

    def test_reported_success_without_an_artifact_is_not_success(self) -> None:
        """Exit code 0 is a claim; a new file on disk is the evidence."""
        self.fixture.control(mode="success")
        result = self.fixture.run()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "artifact_missing")

    def test_jsonl_events_are_captured_as_evidence(self) -> None:
        self.fixture.control(mode="generate", png_source=str(REAL_PNG))
        result = self.fixture.run()
        kinds = [event.get("type") for event in result.events]
        self.assertIn("session.started", kinds)
        self.assertIn("session.completed", kinds)

    def test_timeout_is_classified_and_never_retried(self) -> None:
        self.fixture.control(mode="timeout", sleep_seconds=3)
        result = self.fixture.run(timeout_seconds=0.5)
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "timeout")
        self.assertEqual(result.attempts_made, 1)

    def test_usage_limit_is_classified_with_its_reset_time(self) -> None:
        self.fixture.control(mode="usage_limit", resets_at=1_800_000_000)
        result = self.fixture.run()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "quota_exceeded")
        self.assertEqual(result.failure.limit_id, "image_gen")
        self.assertEqual(result.failure.resets_at, 1_800_000_000)

    def test_usage_limit_is_not_retried(self) -> None:
        self.fixture.control(mode="usage_limit")
        result = self.fixture.run()
        self.assertEqual(result.attempts_made, 1)

    def test_plain_failure_is_classified(self) -> None:
        self.fixture.control(mode="failure", message="the model call failed")
        result = self.fixture.run()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "generation_failed")
        self.assertIn("the model call failed", result.failure.message)

    def test_silent_success_without_an_image_is_not_treated_as_success(self) -> None:
        self.fixture.control(mode="silent")
        result = self.fixture.run()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "artifact_missing")
    def test_missing_binary_is_classified(self) -> None:
        self.fixture.control(mode="success")
        result = self.fixture.run(binary=str(self.fixture.base / "absent-codex"))
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "codex_missing")

    def test_codex_is_invoked_with_cd_json_and_output_file(self) -> None:
        self.fixture.control(mode="success")
        self.fixture.run()
        argv = self.fixture.recorded_argv()
        self.assertIn("--json", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertEqual(argv[argv.index("-C") + 1], str(self.fixture.workdir))
        self.assertIn("-o", argv)

    def test_reference_images_reach_codex(self) -> None:
        reference = self.fixture.base / "ref.png"
        reference.write_bytes(b"reference-bytes")
        self.fixture.control(mode="success")
        self.fixture.run(item=make_item(references=(str(reference),)))
        argv = self.fixture.recorded_argv()
        self.assertIn("-i", argv)
        self.assertEqual(argv[argv.index("-i") + 1], str(reference))

    def test_workdir_is_created_when_absent(self) -> None:
        self.fixture.control(mode="generate", png_source=str(REAL_PNG))
        missing = self.fixture.base / "new-workdir"
        result = self.fixture.run(workdir=missing)
        self.assertTrue(result.ok, result.failure)
        self.assertTrue(missing.is_dir())

    def test_run_is_serialised_by_construction(self) -> None:
        """One item, one subprocess, one attempt: the runner has no internal retry loop."""
        self.fixture.control(mode="failure")
        result = self.fixture.run()
        self.assertEqual(result.attempts_made, 1)
        self.assertFalse(result.ok)


class OutcomeShapeTests(unittest.TestCase):
    def test_outcome_is_json_serialisable(self) -> None:
        outcome = runner.GenerationOutcome(
            ok=False,
            failure=runner.GenerationFailure(code="timeout", message="took too long"),
            attempts_made=1,
        )
        payload = json.loads(json.dumps(runner.as_report(outcome)))
        self.assertEqual(payload["failure"]["code"], "timeout")
        self.assertEqual(payload["attempts_made"], 1)


if __name__ == "__main__":
    unittest.main()
