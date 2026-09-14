import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import atomic_json  # noqa: E402


class AtomicJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.target = self.base / "doc.json"

    def test_document_is_written_with_sorted_keys_and_one_trailing_newline(self) -> None:
        atomic_json.write_json_atomic(self.target, {"b": 1, "a": 2})
        self.assertEqual(self.target.read_text(encoding="utf-8"), '{\n  "a": 2,\n  "b": 1\n}\n')

    def test_failed_atomic_write_preserves_previous_document(self) -> None:
        self.target.write_text('{"revision":1}\n', encoding="utf-8")
        with mock.patch("json.dump", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                atomic_json.write_json_atomic(self.target, {"revision": 2})
        self.assertEqual(self.target.read_text(encoding="utf-8"), '{"revision":1}\n')
        self.assertEqual(list(self.base.glob(".atomic-*.tmp")), [])

    def test_no_temporary_file_survives_a_successful_write(self) -> None:
        atomic_json.write_json_atomic(self.target, {"revision": 2})
        self.assertEqual(list(self.base.glob(".atomic-*.tmp")), [])

    def test_an_existing_document_is_replaced(self) -> None:
        atomic_json.write_json_atomic(self.target, {"revision": 1})
        atomic_json.write_json_atomic(self.target, {"revision": 2})
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), {"revision": 2})

    def test_missing_parent_directories_are_created(self) -> None:
        nested = self.base / "a" / "b" / "doc.json"
        atomic_json.write_json_atomic(nested, {"ok": True})
        self.assertTrue(nested.is_file())

    def test_unserialisable_payload_is_rejected_and_nothing_is_left_behind(self) -> None:
        with self.assertRaises(TypeError):
            atomic_json.write_json_atomic(self.target, {"bad": {1, 2}})
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.base.glob(".atomic-*.tmp")), [])

    def test_the_written_document_round_trips(self) -> None:
        payload = {"nested": {"list": [1, 2, 3]}, "unicode": "画像"}
        atomic_json.write_json_atomic(self.target, payload)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), payload)


if __name__ == "__main__":
    unittest.main()
