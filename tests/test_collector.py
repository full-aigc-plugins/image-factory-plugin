import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_collector as collector  # noqa: E402
import plan_validator  # noqa: E402


REAL_PNG = ROOT / "assets" / "logo.png"          # 1024x1024 RGBA
SMALL_PNG = ROOT / "assets" / "composer-icon.png"  # 256x256 RGBA


def make_item(item_id: str = "item-01", prompt: str = "a calm portrait", round_number: int = 1) -> plan_validator.PlanItem:
    return plan_validator.PlanItem(
        id=item_id,
        prompt=prompt,
        round=round_number,
        reference_images=(),
        reference_sha256=(),
        idempotency_key=plan_validator.compute_idempotency_key(
            batch_id="portrait-study",
            item_id=item_id,
            round_number=round_number,
            prompt=prompt,
            reference_sha256=(),
        ),
    )


class CollectorFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.generation_dir = self.base / "generated_images"
        self.destination = self.base / "batch-out"
        self.generation_dir.mkdir()
        self.destination.mkdir()

    def emit(self, session: str, call_id: str, source: Path = REAL_PNG) -> Path:
        target = self.generation_dir / session / f"{call_id}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target

    def cleanup(self) -> None:
        self._tmp.cleanup()


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CollectorFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_detects_new_and_changed_files_but_not_removed_ones(self) -> None:
        existing = self.fixture.emit("session-a", "call-1")
        before = collector.snapshot(self.fixture.generation_dir)
        self.fixture.emit("session-a", "call-2")
        existing.write_bytes(existing.read_bytes() + b"trailing")
        after = collector.snapshot(self.fixture.generation_dir)
        new = collector.new_entries(before, after)
        self.assertIn("session-a/call-2.png", new)
        self.assertIn("session-a/call-1.png", new)

    def test_removed_file_is_not_reported_as_new(self) -> None:
        existing = self.fixture.emit("session-a", "call-1")
        before = collector.snapshot(self.fixture.generation_dir)
        existing.unlink()
        after = collector.snapshot(self.fixture.generation_dir)
        self.assertEqual(collector.new_entries(before, after), ())

    def test_snapshot_of_missing_directory_is_empty(self) -> None:
        self.assertEqual(collector.snapshot(self.fixture.base / "nope"), {})


class PngTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_reads_dimensions_of_a_real_png(self) -> None:
        self.assertEqual(collector.parse_png_size(REAL_PNG), (1024, 1024))
        self.assertEqual(collector.parse_png_size(SMALL_PNG), (256, 256))

    def test_rejects_non_png(self) -> None:
        target = self.base / "not-an-image.png"
        target.write_bytes(b"this is plainly not a png")
        self.assertIsNone(collector.parse_png_size(target))

    def test_rejects_truncated_png_header(self) -> None:
        target = self.base / "truncated.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
        self.assertIsNone(collector.parse_png_size(target))

    def test_rejects_missing_file(self) -> None:
        self.assertIsNone(collector.parse_png_size(self.base / "absent.png"))


class CollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CollectorFixture()
        self.addCleanup(self.fixture.cleanup)
        self.before = collector.snapshot(self.fixture.generation_dir)

    def collect(self, item: plan_validator.PlanItem | None = None, **overrides):
        kwargs = {
            "item": item or make_item(),
            "batch_id": "portrait-study",
            "generation_dir": self.fixture.generation_dir,
            "destination_dir": self.fixture.destination,
            "before": self.before,
            "min_dimension": 64,
        }
        kwargs.update(overrides)
        return collector.collect_artifact(**kwargs)

    def test_successful_collection_writes_a_verifying_receipt(self) -> None:
        self.fixture.emit("session-a", "call-1")
        result = self.collect()
        self.assertTrue(result.ok, result.failure)
        receipt = result.receipt
        assert receipt is not None
        self.assertEqual(receipt["plugin_id"], "image-factory")
        self.assertEqual(receipt["batch_id"], "portrait-study")
        self.assertEqual(receipt["item_id"], "item-01")
        self.assertEqual(receipt["round"], 1)
        self.assertEqual((receipt["width"], receipt["height"]), (1024, 1024))
        self.assertEqual(receipt["bytes"], REAL_PNG.stat().st_size)
        self.assertEqual(receipt["source"]["kind"], "codex_image_gen")
        self.assertEqual(receipt["source"]["session_id"], "session-a")
        self.assertEqual(receipt["source"]["call_id"], "call-1")
        self.assertIsNone(receipt["source"]["model_reported"])
        self.assertEqual(receipt["sha256"], collector.file_sha256(REAL_PNG))
        self.assertRegex(receipt["artifact_id"], r"^[a-z0-9][a-z0-9_-]{2,127}$")
        self.assertRegex(receipt["prompt_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["idempotency_key"], make_item().idempotency_key)

        published = self.fixture.destination / Path(receipt["path"])
        self.assertTrue(published.is_file())
        self.assertEqual(collector.verify_receipt(receipt, published), [])

    def test_published_path_is_deterministic_and_under_the_destination(self) -> None:
        self.fixture.emit("session-a", "call-1")
        first = self.collect().receipt["path"]
        self.assertEqual(first, self.collect().receipt["path"])
        self.assertTrue(first.startswith("portrait-study/round-1/item-01"))
        self.assertTrue(first.endswith(".png"))

    def test_missing_new_file_is_reported(self) -> None:
        result = self.collect()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "artifact_missing")

    def test_two_new_files_are_rejected_by_default(self) -> None:
        self.fixture.emit("session-a", "call-1")
        self.fixture.emit("session-a", "call-2")
        result = self.collect()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "duplicate_artifact")
        self.assertIn("call-1.png", result.failure.message)
        self.assertIn("call-2.png", result.failure.message)

    def test_newest_sibling_policy_selects_the_latest_and_reports_the_rest(self) -> None:
        older = self.fixture.emit("session-a", "call-1")
        newer = self.fixture.emit("session-a", "call-2")
        os.utime(older, (1_600_000_000, 1_600_000_000))
        os.utime(newer, (1_700_000_000, 1_700_000_000))
        result = self.collect(sibling_policy="newest")
        self.assertTrue(result.ok, result.failure)
        self.assertEqual(result.receipt["source"]["call_id"], "call-2")
        self.assertEqual(result.ignored, ("session-a/call-1.png",))

    def test_unknown_sibling_policy_is_rejected(self) -> None:
        self.fixture.emit("session-a", "call-1")
        with self.assertRaises(ValueError):
            self.collect(sibling_policy="whatever")

    def test_non_png_output_is_rejected(self) -> None:
        target = self.fixture.generation_dir / "session-a" / "call-1.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not a png at all")
        result = self.collect()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "not_a_png")

    def test_small_image_is_rejected_against_min_dimension(self) -> None:
        self.fixture.emit("session-a", "call-1", source=SMALL_PNG)
        result = self.collect(min_dimension=512)
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "below_min_dimension")

    def test_duplicate_content_is_rejected_when_asked(self) -> None:
        self.fixture.emit("session-a", "call-1")
        digest = collector.file_sha256(REAL_PNG)
        result = self.collect(known_hashes={digest}, reject_duplicates=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "duplicate_content")

    def test_duplicate_content_is_allowed_when_duplicates_are_accepted(self) -> None:
        self.fixture.emit("session-a", "call-1")
        digest = collector.file_sha256(REAL_PNG)
        result = self.collect(item=make_item("item-02"), known_hashes={digest}, reject_duplicates=False)
        self.assertTrue(result.ok, result.failure)

    def test_source_rewritten_during_copy_is_caught(self) -> None:
        """The source is re-hashed after the copy: a rewrite mid-collection must fail, not be recorded."""
        source = self.fixture.emit("session-a", "call-1")
        real = collector.file_sha256
        calls = {"n": 0}

        def flaky(target: Path) -> str:
            digest = real(target)
            if Path(target) == source:
                calls["n"] += 1
                if calls["n"] > 1:
                    return "0" * 64
            return digest

        with mock.patch.object(collector, "file_sha256", side_effect=flaky):
            result = self.collect()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "hash_mismatch")

    def test_failed_collection_leaves_no_published_file(self) -> None:
        self.fixture.emit("session-a", "call-1", source=SMALL_PNG)
        self.collect(min_dimension=512)
        published = list(self.fixture.destination.rglob("*.png"))
        self.assertEqual(published, [])


class VerifyReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CollectorFixture()
        self.addCleanup(self.fixture.cleanup)

    def collected(self) -> tuple[dict, Path]:
        before = collector.snapshot(self.fixture.generation_dir)
        self.fixture.emit("session-a", "call-1")
        result = collector.collect_artifact(
            item=make_item(),
            batch_id="portrait-study",
            generation_dir=self.fixture.generation_dir,
            destination_dir=self.fixture.destination,
            before=before,
            min_dimension=64,
        )
        assert result.ok and result.receipt is not None
        return result.receipt, self.fixture.destination / Path(result.receipt["path"])

    def test_detects_content_tampering(self) -> None:
        receipt, published = self.collected()
        published.write_bytes(published.read_bytes() + b"tampered")
        errors = collector.verify_receipt(receipt, published)
        self.assertTrue(any("bytes" in error for error in errors), errors)
        self.assertTrue(any("sha256" in error for error in errors), errors)

    def test_detects_missing_file(self) -> None:
        receipt, published = self.collected()
        published.unlink()
        self.assertEqual(collector.verify_receipt(receipt, published), ["artifact is missing"])

    def test_detects_receipt_field_mismatch(self) -> None:
        receipt, published = self.collected()
        broken = dict(receipt)
        broken["bytes"] = receipt["bytes"] + 1
        errors = collector.verify_receipt(broken, published)
        self.assertTrue(any("bytes" in error for error in errors), errors)

    def test_clean_receipt_verifies(self) -> None:
        receipt, published = self.collected()
        self.assertEqual(collector.verify_receipt(receipt, published), [])

    def test_receipt_is_json_serialisable(self) -> None:
        receipt, _ = self.collected()
        self.assertEqual(json.loads(json.dumps(receipt))["artifact_id"], receipt["artifact_id"])


if __name__ == "__main__":
    unittest.main()
