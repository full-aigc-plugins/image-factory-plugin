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


REAL_PNG = ROOT / "assets" / "logo.png"


class ReceiptStoreFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.job = self.base / "job.json"
        self.destination = self.base / "output"
        self.destination.mkdir()

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def receipt(self, idempotency_key: str) -> dict:
        item_id = f"item-{idempotency_key[0]}"
        relative = Path("portrait-study") / "round-1" / f"{item_id}.png"
        artifact = self.destination / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_PNG, artifact)
        width, height = artifact_collector.parse_png_size(artifact) or (0, 0)
        return {
            "schema_version": "1.0.0",
            "plugin_id": "image-factory",
            "batch_id": "portrait-study",
            "item_id": item_id,
            "round": 1,
            "artifact_id": f"{item_id}-r1-{idempotency_key[:12]}",
            "path": relative.as_posix(),
            "sha256": artifact_collector.file_sha256(artifact),
            "bytes": artifact.stat().st_size,
            "width": width,
            "height": height,
            "prompt_sha256": "c" * 64,
            "idempotency_key": idempotency_key,
            "source": {
                "kind": "codex_image_gen",
                "session_id": "session-a",
                "call_id": f"call-{idempotency_key[0]}",
                "model_reported": None,
            },
            "collected_at": "2026-09-14T12:00:00Z",
        }


class ReceiptStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReceiptStoreFixture()
        self.addCleanup(self.fixture.cleanup)
        self.job = self.fixture.job
        self.destination = self.fixture.destination

    def test_manifest_is_rebuilt_from_verified_per_item_receipts(self) -> None:
        first = receipt_store.write_receipt(self.job, self.fixture.receipt("a" * 64))
        second = receipt_store.write_receipt(self.job, self.fixture.receipt("b" * 64))
        receipts = receipt_store.load_verified_receipts(self.job, self.destination)
        manifest = receipt_store.rebuild_manifest(self.job, receipts)
        self.assertEqual(len(json.loads(manifest.read_text(encoding="utf-8"))), 2)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertTrue(all(row["schema_version"] == "1.1.0" for row in receipts.values()))
        self.assertTrue(all(row["provenance"]["plugin_revision"] is None for row in receipts.values()))

    def test_closed_schema_rejects_unknown_receipt_fields(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt["unexpected"] = True
        with self.assertRaises(receipt_store.ReceiptStoreError):
            receipt_store.write_receipt(self.job, receipt)

    def test_load_refuses_an_artifact_whose_bytes_were_tampered(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt_store.write_receipt(self.job, receipt)
        (self.destination / receipt["path"]).write_bytes(b"tampered")
        with self.assertRaises(receipt_store.ReceiptStoreError):
            receipt_store.load_verified_receipts(self.job, self.destination)

    def test_load_refuses_a_tampered_receipt_document(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        stored = receipt_store.write_receipt(self.job, receipt)
        altered = dict(receipt)
        altered["sha256"] = "f" * 64
        stored.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaises(receipt_store.ReceiptStoreError):
            receipt_store.load_verified_receipts(self.job, self.destination)

    def test_duplicate_idempotency_key_is_refused(self) -> None:
        receipt_store.write_receipt(self.job, self.fixture.receipt("a" * 64))
        with self.assertRaises(receipt_store.ReceiptStoreError):
            receipt_store.write_receipt(self.job, self.fixture.receipt("a" * 64))

    def test_load_refuses_duplicate_keys_hidden_under_different_filenames(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt_store.write_receipt(self.job, receipt)
        duplicate = receipt_store.receipt_directory(self.job) / f"{'b' * 64}.json"
        duplicate.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaises(receipt_store.ReceiptStoreError):
            receipt_store.load_verified_receipts(self.job, self.destination)

    def test_load_refuses_invalid_legacy_manifest_receipts(self) -> None:
        receipt = self.fixture.receipt("a" * 64)
        receipt["unexpected"] = True
        receipt_store.manifest_path(self.job).write_text(
            json.dumps([receipt]), encoding="utf-8"
        )
        with self.assertRaises(receipt_store.ReceiptStoreError):
            receipt_store.load_verified_receipts(self.job, self.destination)


if __name__ == "__main__":
    unittest.main()
