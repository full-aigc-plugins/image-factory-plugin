import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_collector  # noqa: E402
import receipt_store  # noqa: E402
import schema_lite  # noqa: E402


REAL_PNG = ROOT / "assets" / "logo.png"
RECEIPT_SCHEMA = json.loads(
    (ROOT / "schemas/artifact_receipt.schema.json").read_text(encoding="utf-8")
)


class ReceiptStoreFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.job = self.base / "job.json"
        self.destination = self.base / "out"
        self.destination.mkdir()

    def receipt(self, idempotency_key: str, item_id: str = "item-01", relative: str | None = None) -> dict:
        relative = relative or f"portrait-study/round-1/{item_id}-{idempotency_key[:8]}.png"
        target = self.destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_PNG, target)
        size = artifact_collector.parse_png_size(target)
        assert size is not None
        return {
            "schema_version": "1.0.0",
            "plugin_id": "codex-image-factory",
            "batch_id": "portrait-study",
            "item_id": item_id,
            "round": 1,
            "artifact_id": f"{item_id}-r1-{idempotency_key[:12]}",
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

    def cleanup(self) -> None:
        self._tmp.cleanup()


class ReceiptPathTests(unittest.TestCase):
    def test_paths_derive_from_the_job_file(self) -> None:
        job = Path("/tmp/job.json")
        self.assertEqual(receipt_store.receipt_directory(job), Path("/tmp/job.json.receipts"))
        self.assertEqual(
            receipt_store.receipt_path(job, "a" * 64),
            Path("/tmp/job.json.receipts") / f"{'a' * 64}.json",
        )
        self.assertEqual(receipt_store.manifest_path(job), Path("/tmp/job.json.receipts.json"))


class WriteReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReceiptStoreFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_receipt_is_written_under_its_idempotency_key(self) -> None:
        path = receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("a" * 64))
        self.assertEqual(path.name, f"{'a' * 64}.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["idempotency_key"], "a" * 64)

    def test_rewriting_an_identical_receipt_is_a_no_op(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        first = receipt_store.write_receipt(self.fixture.job, receipt)
        second = receipt_store.write_receipt(self.fixture.job, receipt)
        self.assertEqual(first, second)

    def test_a_different_receipt_under_the_same_key_is_refused(self) -> None:
        receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("a" * 64))
        conflicting = self.fixture.receipt("a" * 64, item_id="item-02")
        with self.assertRaises(receipt_store.ReceiptError):
            receipt_store.write_receipt(self.fixture.job, conflicting)

    def test_a_receipt_that_violates_the_schema_is_refused(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt["unexpected"] = "field"
        with self.assertRaises(receipt_store.ReceiptError):
            receipt_store.write_receipt(self.fixture.job, receipt)
        self.assertEqual(schema_lite.validate(self.fixture.receipt("a" * 64), RECEIPT_SCHEMA), [])

    def test_a_receipt_with_a_bad_hash_shape_is_refused(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt["sha256"] = "not-a-hash"
        with self.assertRaises(receipt_store.ReceiptError):
            receipt_store.write_receipt(self.fixture.job, receipt)


class LoadVerifiedReceiptsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReceiptStoreFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_verified_receipts_are_indexed_by_idempotency_key(self) -> None:
        receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("a" * 64))
        receipt_store.write_receipt(
            self.fixture.job, self.fixture.receipt("b" * 64, item_id="item-02")
        )
        verified = receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination)
        self.assertEqual(sorted(verified), ["a" * 64, "b" * 64])

    def test_a_tampered_artifact_is_not_verified(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt_store.write_receipt(self.fixture.job, receipt)
        target = self.fixture.destination / receipt["path"]
        target.write_bytes(target.read_bytes() + b"tampered")
        self.assertEqual(
            receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination), {}
        )
        reasons = receipt_store.unverified_receipts(self.fixture.job, self.fixture.destination)
        self.assertIn("a" * 64, reasons)
        self.assertTrue(any("sha256" in entry for entry in reasons["a" * 64]))

    def test_a_missing_artifact_is_not_verified(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt_store.write_receipt(self.fixture.job, receipt)
        (self.fixture.destination / receipt["path"]).unlink()
        self.assertEqual(
            receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination), {}
        )
        self.assertTrue(
            any("missing" in entry for entry in
                receipt_store.unverified_receipts(self.fixture.job, self.fixture.destination)["a" * 64])
        )

    def test_an_unreadable_receipt_file_is_reported(self) -> None:
        directory = receipt_store.receipt_directory(self.fixture.job)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{'c' * 64}.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(
            receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination), {}
        )
        self.assertIn("c" * 64, receipt_store.unverified_receipts(self.fixture.job, self.fixture.destination))

    def test_no_receipt_directory_yields_nothing(self) -> None:
        self.assertEqual(
            receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination), {}
        )
        self.assertEqual(
            receipt_store.unverified_receipts(self.fixture.job, self.fixture.destination), {}
        )


class RebuildManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReceiptStoreFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_manifest_is_rebuilt_from_verified_per_item_receipts(self) -> None:
        first = receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("a" * 64))
        second = receipt_store.write_receipt(
            self.fixture.job, self.fixture.receipt("b" * 64, item_id="item-02")
        )
        receipts = receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination)
        manifest = receipt_store.rebuild_manifest(self.fixture.job, receipts)
        self.assertEqual(len(json.loads(manifest.read_text(encoding="utf-8"))), 2)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())

    def test_manifest_is_written_atomically_and_is_sorted(self) -> None:
        receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("b" * 64, item_id="item-02"))
        receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("a" * 64))
        receipts = receipt_store.load_verified_receipts(self.fixture.job, self.fixture.destination)
        manifest = receipt_store.rebuild_manifest(self.fixture.job, receipts)
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual([row["item_id"] for row in rows], ["item-01", "item-02"])
        self.assertEqual(list(manifest.parent.glob(".atomic-*.tmp")), [])

    def test_manifest_derives_only_from_the_receipts_it_is_given(self) -> None:
        receipt_store.write_receipt(self.fixture.job, self.fixture.receipt("a" * 64))
        manifest = receipt_store.rebuild_manifest(self.fixture.job, {})
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
