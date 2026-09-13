import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor" / "upstream"


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class UpstreamSnapshotBaselineTests(unittest.TestCase):
    def test_every_vendored_file_matches_its_pinned_git_blob(self) -> None:
        rows = (UPSTREAM / "BLOB_SHA1SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 77)
        for row in rows:
            expected, relative = row.split("  ", 1)
            target = UPSTREAM / relative
            with self.subTest(file=relative):
                self.assertTrue(target.is_file())
                self.assertEqual(git_blob_sha1(target), expected)

    def test_unlicensed_sources_are_pointers_only(self) -> None:
        sources = json.loads((UPSTREAM / "sources.json").read_text(encoding="utf-8"))
        unlicensed = [source for source in sources["sources"] if source["license"] == "UNSPECIFIED"]
        self.assertEqual(len(unlicensed), 2)
        for source in unlicensed:
            with self.subTest(source=source["id"]):
                self.assertFalse(source["vendored"])
                self.assertEqual(source["files"], 0)
                self.assertFalse((UPSTREAM / source["id"]).exists())

    def test_upstream_skills_are_outside_the_active_inventory(self) -> None:
        active = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
        upstream = list(UPSTREAM.glob("**/SKILL.md"))
        self.assertEqual(len(active), 4)
        self.assertEqual(len(upstream), 4)
        self.assertFalse(any("vendor" in path.parts for path in (ROOT / "skills").glob("**/*")))
