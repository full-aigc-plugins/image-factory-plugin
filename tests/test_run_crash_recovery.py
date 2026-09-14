import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "fakes"))
import launcher  # noqa: E402

import generation_runner  # noqa: E402
import image_factory_cli as cli  # noqa: E402
import job_ledger  # noqa: E402
import plan_validator  # noqa: E402
import receipt_store  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"

SHIM = launcher.build_shared_launcher(
    Path(tempfile.mkdtemp(prefix="image-factory-crash-shim-")), FAKE
)


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


class CrashFixture:
    """A one-item job whose single generation call can be interrupted at each boundary."""

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
        self.invocation_dir = self.base / "invocations"
        self.invocation_dir.mkdir()
        self.plan_path = self.base / "plan.json"
        self.job_path = self.base / "job.json"
        self.control_path = self.base / "control.json"
        self._previous_env: str | None = None

    def installed(self) -> "CrashFixture":
        self.plan_path.write_text(json.dumps(one_item_plan()), encoding="utf-8")
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

    def run(self) -> tuple[int, str]:
        return cli.run_cli(
            [
                "run",
                "--plan",
                str(self.plan_path),
                "--job",
                str(self.job_path),
                "--codex-bin",
                str(SHIM),
                "--codex-home",
                str(self.codex_home),
                "--generation-dir",
                str(self.generation_dir),
                "--destination",
                str(self.destination),
                "--approve",
                "--json",
            ]
        )

    def invocations(self) -> list[Path]:
        return sorted(self.invocation_dir.glob("*.json"))

    def ledger(self) -> dict:
        return job_ledger.load_ledger(self.job_path)

    def items(self):
        return plan_validator.validate_plan(
            json.loads(self.plan_path.read_text(encoding="utf-8")), base_dir=self.base
        ).items

    def pending(self) -> list:
        return job_ledger.JobLedger(self.job_path).pending_items(self.items())

    def receipts(self) -> dict:
        return receipt_store.load_verified_receipts(self.job_path, self.destination)

    def cleanup(self) -> None:
        if self._previous_env is None:
            os.environ.pop("FAKE_CODEX_CONTROL", None)
        else:
            os.environ["FAKE_CODEX_CONTROL"] = self._previous_env
        self._tmp.cleanup()


class CrashMatrixTests(unittest.TestCase):
    """Each durability boundary must leave the job recoverable, never re-spendable."""

    def setUp(self) -> None:
        self.fixture = CrashFixture().installed()
        self.addCleanup(self.fixture.cleanup)

    def crash(self, target: str) -> None:
        """Interrupt at a boundary before the real function runs."""
        with mock.patch(target, side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.fixture.run()

    def crash_after(self, target: str) -> None:
        """Interrupt after the real function has already done its work."""
        module_path, attribute = target.rsplit(".", 1)
        real = getattr(sys.modules[module_path], attribute)

        def interrupt(*args, **kwargs):
            real(*args, **kwargs)
            raise KeyboardInterrupt

        with mock.patch(target, side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.fixture.run()

    def test_crash_before_starting_the_attempt_leaves_the_item_runnable(self) -> None:
        """Nothing external happened, so re-running the item is the correct recovery."""
        self.crash("job_ledger.JobLedger.start_attempt")
        self.assertEqual(self.fixture.invocations(), [])
        self.assertEqual([item.id for item in self.fixture.pending()], ["item-01"])
        # The job now sits in Running, which `run` refuses: an unfinished
        # transaction is reconciled by `recover`, not by a silent second run.
        self.assertEqual(self.fixture.ledger()["state"], "Running")
        code, _output = self.fixture.run()
        self.assertEqual(code, cli.EXIT_RECOVERY_REQUIRED)

    def test_crash_after_the_external_call_marks_the_item_unknown(self) -> None:
        self.crash_after("generation_runner.run_item")
        self.assertEqual(len(self.fixture.invocations()), 1)
        entry = self.fixture.ledger()["items"][0]
        self.assertEqual(entry["state"], "Attempting")
        self.assertEqual(self.fixture.pending(), [])

    def test_crash_after_publication_leaves_the_item_unresolved(self) -> None:
        self.crash("receipt_store.write_receipt")
        self.assertEqual(len(self.fixture.invocations()), 1)
        self.assertEqual(self.fixture.ledger()["items"][0]["state"], "Attempting")
        self.assertEqual(self.fixture.pending(), [])

    def test_crash_after_receipt_persistence_leaves_the_item_unresolved(self) -> None:
        self.crash("job_ledger.JobLedger.complete_attempt")
        self.assertEqual(self.fixture.ledger()["items"][0]["state"], "Attempting")
        self.assertEqual(self.fixture.pending(), [])
        self.assertEqual(len(self.fixture.receipts()), 1)

    def test_crash_after_completion_leaves_a_rebuildable_manifest(self) -> None:
        self.crash("receipt_store.rebuild_manifest")
        entry = self.fixture.ledger()["items"][0]
        self.assertEqual(entry["state"], "Generated")
        self.assertEqual(self.fixture.pending(), [])
        self.assertEqual(len(self.fixture.receipts()), 1)

    def test_a_completed_run_is_unaffected_by_the_crash_boundaries(self) -> None:
        code, output = self.fixture.run()
        self.assertEqual(code, 0, output)
        self.assertEqual(len(self.fixture.invocations()), 1)
        self.assertEqual(self.fixture.ledger()["state"], "Completed")
        self.assertEqual(self.fixture.pending(), [])

    def test_the_second_run_of_a_settled_job_spends_nothing(self) -> None:
        self.fixture.run()
        code, output = self.fixture.run()
        self.assertEqual(code, 0, output)
        self.assertEqual(len(self.fixture.invocations()), 1)
        self.assertEqual(json.loads(output)["receipts"], [])


if __name__ == "__main__":
    unittest.main()
