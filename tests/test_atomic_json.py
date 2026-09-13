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
        self.target = self.base / "document.json"

    def test_write_is_sorted_and_ends_with_one_newline(self) -> None:
        atomic_json.write_json_atomic(self.target, {"z": 1, "a": 2})
        self.assertEqual(self.target.read_text(encoding="utf-8"), '{\n  "a": 2,\n  "z": 1\n}\n')

    def test_failed_atomic_write_preserves_previous_document(self) -> None:
        self.target.write_text('{"revision":1}\n', encoding="utf-8")
        with mock.patch("json.dump", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                atomic_json.write_json_atomic(self.target, {"revision": 2})
        self.assertEqual(self.target.read_text(encoding="utf-8"), '{"revision":1}\n')
        self.assertEqual(list(self.base.glob(".atomic-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
