import json
import subprocess
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "codex-image-factory"
DISPLAY_NAME = "Codex Image Factory"
RELEASE_VERSION = "0.1.2"
PRIOR_RELEASE_SHA = "fff20c9aad9a9cd7893644306c752b2f7231071d"

EXPECTED_SKILLS = (
    "codex-image-factory-use",
    "codex-image-factory-run",
    "codex-image-factory-judge",
    "codex-image-factory-recover",
)

BILINGUAL_PAIRS = (
    ("README.md", "README.zh-CN.md"),
    (
        "docs/Codex-Image-Factory-Plugin-Architecture.md",
        "docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md",
    ),
    (
        "docs/Codex-Image-Factory-Plugin-Technical-Solution.md",
        "docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md",
    ),
)

REQUIRED_DOCUMENTS = (
    "docs/portable-migration.md",
    "docs/verification/offline.md",
    "docs/superpowers/specs/2026-09-12-codex-image-factory-plugin-design.md",
    "docs/superpowers/plans/2026-09-12-codex-image-factory-plugin-implementation.md",
)

# Gates that cannot be satisfied offline must be declared with their observed status.
# Updated only when a gate is actually observed; the test holds the document to the
# status recorded here, so a stale document fails rather than passing quietly.
RUNTIME_GATES = {
    "remote_ci_matrix": "PASS",
    "remote_sha_parity": "PASS",
    "fresh_marketplace_install": "PASS",
    "fresh_session_no_spend_smoke": "PASS",
    "paid_canary": "PASS",
    "multi_round_closed_loop": "PASS",
    "product_surface_paid_run": "PASS",
    "cross_platform_generation": "NOT_RUN",
    "usage_limit_evidence": "NOT_RUN",
}

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def relative_markdown_links(path: Path) -> list[str]:
    """Collect local targets only; URLs, anchors, and placeholders are out of scope."""
    targets = []
    for match in MARKDOWN_LINK.finditer(path.read_text(encoding="utf-8")):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].strip()
        if not target or "{" in target:
            continue
        targets.append(target)
    return targets


class SkillInventoryTests(unittest.TestCase):
    def test_skill_set_is_exactly_as_designed(self) -> None:
        present = tuple(sorted(entry.name for entry in (ROOT / "skills").iterdir() if entry.is_dir()))
        self.assertEqual(present, tuple(sorted(EXPECTED_SKILLS)))

    def test_each_skill_frontmatter_name_matches_its_directory(self) -> None:
        for name in EXPECTED_SKILLS:
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=name):
                self.assertTrue(text.startswith("---\n"))
                head = text[4 : text.index("\n---", 4)]
                declared = re.search(r"^name:\s*(\S+)\s*$", head, re.MULTILINE)
                self.assertIsNotNone(declared, f"{name}: no name field")
                self.assertEqual(declared.group(1), name)


class DocumentationTests(unittest.TestCase):
    def test_release_documents_align_with_the_manifest_version(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], RELEASE_VERSION)
        for relative in (
            "CHANGELOG.md",
            "README.md",
            "README.zh-CN.md",
            "docs/Codex-Image-Factory-Plugin-Architecture.md",
            "docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md",
            "docs/Codex-Image-Factory-Plugin-Technical-Solution.md",
            "docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md",
            "docs/verification/runtime.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(RELEASE_VERSION, text)

    def test_bilingual_pairs_exist(self) -> None:
        for english, chinese in BILINGUAL_PAIRS:
            with self.subTest(pair=english):
                self.assertTrue((ROOT / english).is_file(), english)
                self.assertTrue((ROOT / chinese).is_file(), chinese)

    def test_bilingual_pairs_cross_link(self) -> None:
        for english, chinese in BILINGUAL_PAIRS:
            with self.subTest(pair=english):
                self.assertIn(
                    Path(chinese).name, (ROOT / english).read_text(encoding="utf-8")
                )
                self.assertIn(
                    Path(english).name, (ROOT / chinese).read_text(encoding="utf-8")
                )

    def test_required_documents_exist(self) -> None:
        for relative in REQUIRED_DOCUMENTS:
            with self.subTest(document=relative):
                self.assertTrue((ROOT / relative).is_file(), relative)

    def test_architecture_and_solution_declare_their_status(self) -> None:
        for relative in (
            "docs/Codex-Image-Factory-Plugin-Architecture.md",
            "docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md",
            "docs/Codex-Image-Factory-Plugin-Technical-Solution.md",
            "docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("0.1.2", text)
                self.assertIn("release candidate", text.lower())

    def test_no_document_names_an_image_model(self) -> None:
        """The platform chooses the model; claiming one would mislead the reader."""
        product_documents = [
            ROOT / "README.md",
            ROOT / "README.zh-CN.md",
            ROOT / "docs/Codex-Image-Factory-Plugin-Architecture.md",
            ROOT / "docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md",
            ROOT / "docs/Codex-Image-Factory-Plugin-Technical-Solution.md",
            ROOT / "docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md",
            *sorted((ROOT / "skills").glob("*/SKILL.md")),
        ]
        for path in product_documents:
            # Source URLs identify upstream repositories, not the runtime model.
            text = re.sub(r"https?://[^\s)]+", "", path.read_text(encoding="utf-8").lower())
            for model in ("gpt-image", "image-2.5", "sunburst", "flare"):
                with self.subTest(document=path.name, model=model):
                    self.assertNotIn(model, text)

    def test_runtime_evidence_is_versioned_and_declares_every_external_gate(self) -> None:
        text = (ROOT / "docs/verification/runtime.md").read_text(encoding="utf-8")
        self.assertIn("0.1.2", text)
        for gate, expected_status in RUNTIME_GATES.items():
            with self.subTest(gate=gate):
                self.assertIn(gate, text)
                line = next(row for row in text.splitlines() if gate in row and row.startswith("|"))
                self.assertIn(expected_status, line)
                status = line.split("|")[2].strip().strip("`")
                self.assertIn(status, {"PASS", "FAIL", "NOT_RUN"})

        self.assertNotIn(PRIOR_RELEASE_SHA, text)
        self.assertNotIn("version `0.1.0`", text)


class LinkTests(unittest.TestCase):
    def test_every_relative_markdown_link_resolves(self) -> None:
        failures: list[str] = []
        for path in sorted(ROOT.rglob("*.md")):
            if ".git" in path.parts or "__pycache__" in path.parts or "vendor" in path.parts:
                continue
            for target in relative_markdown_links(path):
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    failures.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(failures, [], "unresolved relative links")

    def test_documents_avoid_absolute_local_paths(self) -> None:
        for path in sorted(ROOT.rglob("*.md")):
            if ".git" in path.parts or "vendor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(document=path.name):
                self.assertNotIn("/Users/", text)
                self.assertNotIn("file://", text)


class RepositoryStructureTests(unittest.TestCase):
    def test_no_symlinks_anywhere(self) -> None:
        offenders = [
            str(entry.relative_to(ROOT))
            for entry in ROOT.rglob("*")
            if entry.is_symlink() and ".git" not in entry.parts
        ]
        self.assertEqual(offenders, [])

    def test_no_build_artifacts_are_tracked(self) -> None:
        """Caches appear in any working tree that has run the suite; what matters is what is committed."""
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", check=False
        ).stdout.splitlines()
        noise = ("__pycache__", ".pytest_cache", "node_modules", ".DS_Store")
        offenders = [name for name in tracked if any(marker in name for marker in noise)]
        self.assertEqual(offenders, [])

    def test_the_working_tree_has_no_stray_editor_or_dependency_directories(self) -> None:
        noise = ("node_modules", ".DS_Store")
        offenders = [
            str(entry.relative_to(ROOT))
            for entry in ROOT.rglob("*")
            if ".git" not in entry.parts and any(marker in entry.parts for marker in noise)
        ]
        self.assertEqual(offenders, [])

    def test_cli_entry_point_is_executable(self) -> None:
        entry = ROOT / "bin/image-factory"
        self.assertTrue(entry.is_file())
        tracked = subprocess.run(
            ["git", "ls-files", "-s", "--", "bin/image-factory"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout.split()
        self.assertEqual(tracked[0], "100755", "bin/image-factory must be executable in the Git index")

    def test_manifest_asset_paths_exist(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], PLUGIN_ID)
        self.assertEqual(manifest["interface"]["displayName"], DISPLAY_NAME)
        for key in ("logo", "logoDark", "composerIcon"):
            target = ROOT / manifest["interface"][key].lstrip("./")
            with self.subTest(asset=key):
                self.assertTrue(target.is_file(), f"{key} -> {target}")

    def test_schema_identifiers_agree_with_the_repository(self) -> None:
        repository = json.loads(
            (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )["repository"]
        for path in sorted((ROOT / "schemas").glob("*.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(schema=path.name):
                self.assertEqual(schema["$id"], f"{repository}/schemas/{path.name}")



OPEN_MODE = re.compile(r"""open\([^)]*?["']([rwxat+]+b?[rwxat+]*b?|[rwxat+]{1,3})["']""")


def text_mode_open_without_encoding(line: str) -> bool:
    """True when a line opens a file in text mode but never states its encoding.

    Deliberately narrow: `os.open` returns a descriptor and has no encoding, and any
    mode containing `b` is binary. Flagging those would make the guard useless.
    """
    if "open(" not in line or "encoding=" in line:
        return False
    if "os.fdopen(" in line or "os.open(" in line:
        return False
    match = OPEN_MODE.search(line)
    if match is None:
        return False
    return "b" not in match.group(1)


class LocaleIndependenceTests(unittest.TestCase):
    """Text I/O must not depend on the host locale.

    Windows defaults text reads to cp1252, so a `read_text()` without an explicit
    encoding fails on any byte cp1252 leaves undefined. That bug shipped once, in
    `prompt_library`, where it broke `prompt-search` for every Windows user while
    passing on every POSIX host. It is cheaper to forbid the pattern than to find
    it again from a CI log.
    """

    def source_lines(self):
        for path in sorted((ROOT / "scripts").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                yield path.name, number, line

    def test_no_read_text_without_an_explicit_encoding(self) -> None:
        offenders = [
            f"{name}:{number}"
            for name, number, line in self.source_lines()
            if ".read_text(" in line and "encoding=" not in line
        ]
        self.assertEqual(offenders, [], "read_text() must state its encoding")

    def test_no_text_mode_open_without_an_explicit_encoding(self) -> None:
        offenders = [
            f"{name}:{number}"
            for name, number, line in self.source_lines()
            if text_mode_open_without_encoding(line)
        ]
        self.assertEqual(offenders, [], "text-mode open() must state its encoding")


class TextModeOpenDetectionTests(unittest.TestCase):
    """The guard's own classifier, so it cannot silently stop detecting anything."""

    def test_flags_a_text_open_without_encoding(self) -> None:
        self.assertTrue(text_mode_open_without_encoding('path.open("r")'))
        self.assertTrue(text_mode_open_without_encoding('open(name, "w")'))

    def test_accepts_a_text_open_that_states_its_encoding(self) -> None:
        self.assertFalse(text_mode_open_without_encoding('path.open("r", encoding="utf-8")'))

    def test_ignores_binary_modes(self) -> None:
        for line in ('temporary.open("rb+") as stream:', 'self.lock_path.open("a+b")', 'open(p, "rb")'):
            with self.subTest(line=line):
                self.assertFalse(text_mode_open_without_encoding(line))

    def test_ignores_descriptor_opens(self) -> None:
        self.assertFalse(text_mode_open_without_encoding("descriptor = os.open(directory, flags)"))


if __name__ == "__main__":
    unittest.main()
