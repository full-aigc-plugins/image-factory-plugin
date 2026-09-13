import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "use-cases"
CASE_FILES = {
    "story-series-reference.zh-CN.md": ("S", 14),
    "commercial-content.zh-CN.md": ("C", 16),
    "knowledge-design.zh-CN.md": ("K", 14),
    "character-ui-game.zh-CN.md": ("D", 16),
    "edit-review.zh-CN.md": ("E", 8),
}
CASE_HEADING = re.compile(r"^## ([SCKDE]\d{2}) .+$", re.MULTILINE)


class UseCaseDocumentationTests(unittest.TestCase):
    def test_case_ids_are_complete_and_unique(self) -> None:
        all_ids: list[str] = []
        for filename, (prefix, count) in CASE_FILES.items():
            text = (DOCS / filename).read_text(encoding="utf-8")
            ids = CASE_HEADING.findall(text)
            with self.subTest(file=filename):
                self.assertEqual(ids, [f"{prefix}{index:02d}" for index in range(1, count + 1)])
            all_ids.extend(ids)
        self.assertEqual(len(all_ids), 68)
        self.assertEqual(len(set(all_ids)), 68)

    def test_every_case_has_an_actionable_contract(self) -> None:
        required = ("用户输入", "批次条件", "自动处理", "交付", "验收", "参考能力")
        for filename in CASE_FILES:
            text = (DOCS / filename).read_text(encoding="utf-8")
            headings = list(CASE_HEADING.finditer(text))
            for index, heading in enumerate(headings):
                end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
                case = text[heading.start():end]
                with self.subTest(case=heading.group(1)):
                    for field in required:
                        self.assertIn(f"**{field}**", case)

    def test_all_structured_templates_are_mapped(self) -> None:
        index = (DOCS / "README.zh-CN.md").read_text(encoding="utf-8")
        library = json.loads((ROOT / "data" / "style-library.json").read_text(encoding="utf-8"))
        for template in library["templates"]:
            with self.subTest(template=template["id"]):
                self.assertIn(f"`{template['id']}`", index)

    def test_all_gallery_categories_are_mapped(self) -> None:
        index = (DOCS / "README.zh-CN.md").read_text(encoding="utf-8")
        gallery = (
            ROOT
            / "vendor/upstream/wuyoscar-gpt-image2-skill"
            / "05cb1130bba29e0fc028220376280a2e934a8041"
            / "skills/gpt-image/references/gallery.md"
        ).read_text(encoding="utf-8")
        categories = []
        for row in gallery.splitlines():
            if not row.startswith("|") or "gallery-" not in row:
                continue
            category_with_icon = row.split("|", 2)[1].strip()
            categories.append(category_with_icon.split(" ", 1)[1])
        self.assertEqual(len(categories), 31)
        for category in categories:
            with self.subTest(category=category.strip()):
                self.assertIn(f"| {category.strip()} |", index)

    def test_all_large_library_directories_are_mapped(self) -> None:
        index = (DOCS / "README.zh-CN.md").read_text(encoding="utf-8")
        manifest = json.loads(
            (
                ROOT
                / "vendor/upstream/youmind-ai-image-prompts-skill"
                / "6e8339bbfda7ed3f21978df84f266f1c393f5918"
                / "references/manifest.json"
            ).read_text(encoding="utf-8")
        )
        for category in manifest["categories"]:
            anchor = category["title"].split(" / ")[0]
            with self.subTest(category=category["slug"]):
                self.assertIn(anchor, index)
