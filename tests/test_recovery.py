import hashlib
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

import artifact_collector  # noqa: E402
import image_factory_cli as cli  # noqa: E402
import job_ledger  # noqa: E402
import plan_validator  # noqa: E402
import receipt_store  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"

_SHIM_DIR = Path(tempfile.mkdtemp(prefix="image-factory-recovery-shim-"))
SHIM = _SHIM_DIR / "codex"
SHIM.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
SHIM.chmod(SHIM.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def one_item_plan(**overrides) -> dict:
    plan = {
        "schema_version": "1.1.0",
        "batch_id": "portrait-study",
        "round": 1,
        "limits": {"max_images": 5, "max_rounds": 3, "require_approval_before_run": True},
        "judge_policy": {
            "min_dimension": 64,
            "reject_duplicates": True,
            "pass_threshold": 0.8,
            "require_human_labels": True,
        },
        "items": [{"id": "item-01", "prompt": "a calm portrait"}],
    }
    plan.update(overrides)
    return plan


class RecoveryFixture:
    """A job left mid-flight, with or without the artifact its attempt produced."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.codex_home = self.base / "codex-home"
        self.codex_home.mkdir()
        (self.codex_home / "auth.json").write_text("{}", encoding="utf-8")
        (self.codex_home / "config.toml").write_text('model = "gpt-5.6-sol"\n', encoding="utf-8")
        self.generation_dir = self.codex_home / "generated_images"
        self.generation_dir.mkdir()
        self.destination = self.base / "out"
        self.destination.mkdir()
        self.invocation_dir = self.base / "invocations"
        self.invocation_dir.mkdir()
        self.plan_path = self.base / "plan.json"
        self.job_path = self.base / "job.json"
        self.control_path = self.base / "control.json"
        self._previous_env: str | None = None

    def plan(self) -> plan_validator.PlanResult:
        return plan_validator.validate_plan(
            json.loads(self.plan_path.read_text(encoding="utf-8")), base_dir=self.base
        )

    def installed(self) -> "RecoveryFixture":
        self.plan_path.write_text(json.dumps(one_item_plan()), encoding="utf-8")
        # Any Codex call during recovery would write evidence here, which the tests
        # assert stays empty.
        self.control_path.write_text(
            json.dumps(
                {
                    "mode": "generate",
                    "generation_dir": str(self.generation_dir),
                    "png_source": str(REAL_PNG),
                    "invocation_dir": str(self.invocation_dir),
                }
            ),
            encoding="utf-8",
        )
        self._previous_env = os.environ.get("FAKE_CODEX_CONTROL")
        os.environ["FAKE_CODEX_CONTROL"] = str(self.control_path)
        return self

    def interrupted(self, *, item_state: str = "Attempting", with_artifact: bool = False):
        """Leave the job in the state an interrupted run would have left behind."""
        result = self.plan()
        ledger = job_ledger.JobLedger(self.job_path)
        ledger.write(job_ledger.new_job(result.batch_id))
        ledger.transition(job_ledger.JobState.PLAN_VALIDATED)
        ledger.bind_plan(result.plan_sha256, result.round, len(result.items))
        ledger.record_approval(result.plan_sha256, result.round, len(result.items), "run_approve_flag")
        ledger.transition(job_ledger.JobState.APPROVED)
        ledger.transition(job_ledger.JobState.RUNNING)
        item = result.items[0]
        ledger.start_attempt(item, "attempt-1")
        if item_state == "Unknown":
            ledger.mark_attempt_unknown(item.id, "attempt-1")
        if with_artifact:
            receipt_store.write_receipt(self.job_path, self.receipt(item.idempotency_key))
        return ledger

    def receipt(self, idempotency_key: str) -> dict:
        relative = f"portrait-study/round-1/item-01-{idempotency_key[:8]}.png"
        target = self.destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_PNG, target)
        size = artifact_collector.parse_png_size(target)
        assert size is not None
        return {
            "schema_version": "1.0.0",
            "plugin_id": "codex-image-factory",
            "batch_id": "portrait-study",
            "item_id": "item-01",
            "round": 1,
            "artifact_id": f"item-01-r1-{idempotency_key[:12]}",
            "path": relative,
            "sha256": artifact_collector.file_sha256(target),
            "bytes": target.stat().st_size,
            "width": size[0],
            "height": size[1],
            "prompt_sha256": hashlib.sha256(b"prompt").hexdigest(),
            "idempotency_key": idempotency_key,
            "source": {
                "kind": "codex_image_gen",
                "session_id": "session-a",
                "call_id": "call-1",
                "model_reported": None,
            },
            "collected_at": "2026-09-12T00:00:00Z",
        }

    def recover(self) -> tuple[int, str]:
        return cli.run_cli(
            [
                "recover",
                "--plan",
                str(self.plan_path),
                "--job",
                str(self.job_path),
                "--destination",
                str(self.destination),
                "--codex-home",
                str(self.codex_home),
                "--generation-dir",
                str(self.generation_dir),
                "--json",
            ]
        )

    def ledger(self) -> dict:
        return job_ledger.load_ledger(self.job_path)

    def invocations(self) -> list[Path]:
        return sorted(self.invocation_dir.glob("*.json"))

    def cleanup(self) -> None:
        if self._previous_env is None:
            os.environ.pop("FAKE_CODEX_CONTROL", None)
        else:
            os.environ["FAKE_CODEX_CONTROL"] = self._previous_env
        self._tmp.cleanup()


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RecoveryFixture().installed()
        self.addCleanup(self.fixture.cleanup)

    def test_an_interrupted_attempt_with_evidence_becomes_generated(self) -> None:
        self.fixture.interrupted(item_state="Attempting", with_artifact=True)
        code, output = self.fixture.recover()
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["reconciled"], ["item-01"])
        self.assertEqual(payload["unknown"], [])
        self.assertEqual(self.fixture.ledger()["items"][0]["state"], "Generated")
        self.assertEqual(self.fixture.ledger()["state"], "Completed")

    def test_an_interrupted_attempt_without_evidence_becomes_unknown(self) -> None:
        self.fixture.interrupted(item_state="Attempting", with_artifact=False)
        code, output = self.fixture.recover()
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        payload = json.loads(output)
        self.assertEqual(payload["unknown"], ["item-01"])
        self.assertEqual(self.fixture.ledger()["items"][0]["state"], "Unknown")
        self.assertEqual(self.fixture.ledger()["state"], "Unknown")

    def test_an_unknown_item_with_evidence_becomes_generated(self) -> None:
        self.fixture.interrupted(item_state="Unknown", with_artifact=True)
        code, output = self.fixture.recover()
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["reconciled"], ["item-01"])
        self.assertEqual(self.fixture.ledger()["items"][0]["state"], "Generated")

    def test_a_tampered_artifact_does_not_count_as_evidence(self) -> None:
        ledger = self.fixture.interrupted(item_state="Attempting", with_artifact=True)
        receipt = self.fixture.ledger()["items"][0]
        published = self.fixture.destination / "portrait-study" / "round-1"
        for path in published.glob("*.png"):
            path.write_bytes(path.read_bytes() + b"tampered")
        code, output = self.fixture.recover()
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED, output)
        self.assertEqual(json.loads(output)["unknown"], ["item-01"])
        self.assertIsNotNone(receipt)
        self.assertIsNotNone(ledger)

    def test_the_manifest_is_rebuilt_from_verified_receipts(self) -> None:
        self.fixture.interrupted(item_state="Attempting", with_artifact=True)
        self.fixture.recover()
        manifest = receipt_store.manifest_path(self.fixture.job_path)
        self.assertTrue(manifest.is_file())
        self.assertEqual(len(json.loads(manifest.read_text(encoding="utf-8"))), 1)

    def test_recovery_makes_no_generation_call(self) -> None:
        for state, artifact in (("Attempting", True), ("Attempting", False), ("Unknown", False)):
            with self.subTest(state=state, artifact=artifact):
                fixture = RecoveryFixture().installed()
                try:
                    fixture.interrupted(item_state=state, with_artifact=artifact)
                    fixture.recover()
                    self.assertEqual(fixture.invocations(), [])
                finally:
                    fixture.cleanup()

    def test_recovery_reports_the_remaining_generation_calls(self) -> None:
        self.fixture.interrupted(item_state="Attempting", with_artifact=True)
        _code, output = self.fixture.recover()
        payload = json.loads(output)
        self.assertEqual(payload["pending_count"], 0)
        self.assertEqual(payload["remaining_generation_calls"], 0)

    def test_recovery_is_idempotent(self) -> None:
        self.fixture.interrupted(item_state="Attempting", with_artifact=True)
        self.fixture.recover()
        code, output = self.fixture.recover()
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["reconciled"], [])

    def test_a_settled_job_recovers_to_its_own_state(self) -> None:
        self.fixture.interrupted(item_state="Attempting", with_artifact=True)
        self.fixture.recover()
        code, output = self.fixture.recover()
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["state"], "Completed")


if __name__ == "__main__":
    unittest.main()
