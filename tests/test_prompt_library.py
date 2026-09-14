import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PromptSearchTests(unittest.TestCase):
    def invoke(self, query, limit="3"):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/image_factory_cli.py"), "prompt-search", query, "--limit", limit, "--json"],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_chinese_story_request_has_attributed_templates(self):
        result = self.invoke("成语绘本分镜")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["matches"])
        self.assertLessEqual(len(report["matches"]), 3)
        self.assertFalse(report["network_used"])
        self.assertEqual(len(report["sources"]), 6)
        self.assertIn("comic-storyboard", [row["slug"] for row in report["category_matches"]])
        self.assertTrue(Path(report["gallery_index"]).is_file())
        for hit in report["matches"]:
            self.assertEqual(hit["source"]["license"], "MIT")
            self.assertEqual(len(hit["source"]["revision"]), 40)
            self.assertTrue(hit["template"]["guidance"])

    def test_unmatched_query_does_not_fabricate_examples(self):
        result = self.invoke("zzzzunmatchable")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["matches"], [])

    def test_invalid_limits_and_empty_queries_fail(self):
        for query, limit in [("poster", "0"), ("poster", "11"), (" ", "3")]:
            with self.subTest(query=query, limit=limit):
                self.assertNotEqual(self.invoke(query, limit).returncode, 0)
