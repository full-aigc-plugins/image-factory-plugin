import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "fakes"))
import launcher  # noqa: E402

import image_factory_cli as cli  # noqa: E402
import receipt_store  # noqa: E402


FAKE = ROOT / "tests" / "fakes" / "fake_codex.py"
REAL_PNG = ROOT / "assets" / "logo.png"
CLI_ENTRY = ROOT / "bin" / "image-factory"

# Long enough that the second process is certain to arrive while the first still
# holds the lock, however the two are scheduled.
GENERATOR_DELAY_SECONDS = 1.5

SHIM = launcher.build_shared_launcher(
    Path(tempfile.mkdtemp(prefix="image-factory-concurrency-shim-")), FAKE
)


def two_item_plan() -> dict:
    return {
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
        "items": [
            {"id": "item-01", "prompt": "a calm portrait"},
            {"id": "item-02", "prompt": "a second portrait"},
        ],
    }


class ConcurrencyFixture:
    """Two real CLI processes racing for the same job."""

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

    def installed(self) -> "ConcurrencyFixture":
        self.plan_path.write_text(json.dumps(two_item_plan()), encoding="utf-8")
        self.control_path.write_text(
            json.dumps(
                {
                    "mode": "generate",
                    "generation_dir": str(self.generation_dir),
                    "png_source": str(REAL_PNG),
                    "invocation_dir": str(self.invocation_dir),
                    "delay_before_result_seconds": GENERATOR_DELAY_SECONDS,
                }
            ),
            encoding="utf-8",
        )
        self._previous_env = os.environ.get("FAKE_CODEX_CONTROL")
        os.environ["FAKE_CODEX_CONTROL"] = str(self.control_path)
        return self

    def command(self) -> list[str]:
        return [
            str(CLI_ENTRY),
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

    def invocations(self) -> list[Path]:
        return sorted(self.invocation_dir.glob("*.json"))

    def receipts_for_unique_idempotency_keys(self) -> set[str]:
        verified = receipt_store.load_verified_receipts(self.job_path, self.destination)
        return {receipt["idempotency_key"] for receipt in verified.values()}

    def cleanup(self) -> None:
        if self._previous_env is None:
            os.environ.pop("FAKE_CODEX_CONTROL", None)
        else:
            os.environ["FAKE_CODEX_CONTROL"] = self._previous_env
        self._tmp.cleanup()


class TwoProcessRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ConcurrencyFixture().installed()
        self.addCleanup(self.fixture.cleanup)

    def test_only_one_of_two_processes_runs_the_batch(self) -> None:
        environment = dict(os.environ)
        processes = [
            subprocess.Popen(
                self.fixture.command(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
            )
            for _ in range(2)
        ]
        for process in processes:
            try:
                process.communicate(timeout=120)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                process.kill()
                process.communicate()
                self.fail("a run process did not finish")

        self.assertEqual(
            sorted(result.returncode for result in processes),
            [0, cli.EXIT_JOB_LOCKED],
        )
        # The winning process makes exactly the two planned calls; the losing one
        # makes none, which is the whole point of serialising the job.
        self.assertEqual(len(self.fixture.invocations()), 2)
        self.assertEqual(len(self.fixture.receipts_for_unique_idempotency_keys()), 2)

    def test_the_losing_process_reports_the_lock_not_a_spend(self) -> None:
        environment = dict(os.environ)
        winner = subprocess.Popen(
            self.fixture.command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=environment,
        )
        time.sleep(0.4)
        loser = subprocess.Popen(
            self.fixture.command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=environment,
        )
        winner_out = winner.communicate(timeout=120)[0]
        loser_out = loser.communicate(timeout=120)[0]

        self.assertEqual(winner.returncode, 0, winner_out)
        self.assertEqual(loser.returncode, cli.EXIT_JOB_LOCKED, loser_out)
        self.assertEqual(json.loads(loser_out)["error_category"], "job_already_running")


if __name__ == "__main__":
    unittest.main()
