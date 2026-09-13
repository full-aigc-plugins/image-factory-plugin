import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATHS = (
    "docs/guides/creative-studio-user-guide.zh-CN.md",
    "docs/superpowers/specs/2026-09-13-codex-creative-studio-design.md",
    "docs/superpowers/plans/2026-09-13-codex-creative-studio-implementation.md",
    "docs/use-cases/edit-review-video.zh-CN.md",
)

STUDIO_MARKERS = (
    "Creative Studio",
    "creative-studio",
    "studio_server.py",
    "video_renderer.py",
    "Local Video Composer",
    "本地故事视频",
)


class RepositoryOwnershipTests(unittest.TestCase):
    def test_studio_owned_documents_are_not_distributed_by_image_factory(self) -> None:
        for relative in FORBIDDEN_PATHS:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists(), relative)

    def test_image_factory_product_documents_do_not_claim_studio_ownership(self) -> None:
        product_documents = [ROOT / "README.md", ROOT / "README.zh-CN.md"]
        product_documents.extend(sorted((ROOT / "docs").rglob("*.md")))
        for path in product_documents:
            text = path.read_text(encoding="utf-8")
            for marker in STUDIO_MARKERS:
                with self.subTest(document=path.relative_to(ROOT), marker=marker):
                    self.assertNotIn(marker, text)

    def test_image_factory_keeps_an_image_only_edit_and_review_casebook(self) -> None:
        self.assertTrue((ROOT / "docs/use-cases/edit-review.zh-CN.md").is_file())


if __name__ == "__main__":
    unittest.main()
