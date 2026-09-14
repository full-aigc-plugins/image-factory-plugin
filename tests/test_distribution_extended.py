import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "codex-image-factory"
DISPLAY_NAME = "Codex Image Factory"

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
# Gates that need a live account or an installation. The observations recorded
# against 0.1.0 do not describe the 1.1.0 contracts, so they are NOT_RUN until they
# are observed again. Claiming an inherited PASS would be the one thing this
# evidence structure exists to prevent.
RUNTIME_GATES = {
    "runtime_generation_evidence": "NOT_RUN",
    "usage_limit_evidence": "NOT_RUN",
    "plugin_installation": "NOT_RUN",
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
                self.assertIn("2026-09-14", text)

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

    def test_runtime_evidence_declares_completed_gates(self) -> None:
        text = (ROOT / "docs/verification/offline.md").read_text(encoding="utf-8")
        for gate, expected_status in RUNTIME_GATES.items():
            with self.subTest(gate=gate):
                self.assertIn(gate, text)
                line = next(row for row in text.splitlines() if gate in row and row.startswith("|"))
                self.assertIn(expected_status, line)

        # The earlier observations are preserved, but must be labelled as history
        # rather than left looking like evidence for the current build.
        runtime = (ROOT / "docs/verification/runtime.md").read_text(encoding="utf-8")
        self.assertIn("## Historical evidence", runtime)
        self.assertIn("not evidence for the 0.1.2 candidate", runtime)
        for heading in (
            "## Real two-item generation",
            "## Marketplace resolution and installation",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, runtime)
        self.assertIn("Status: `PASS`.", runtime)
        self.assertIn("Installation status: `PASS`.", runtime)
        self.assertIn("attempted each item exactly once", runtime)
        self.assertIn("all four exact Skill names as discoverable", runtime)


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
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True, check=False
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
        self.assertTrue(entry.stat().st_mode & 0o111, "bin/image-factory must be executable")

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



class ContinuousIntegrationTests(unittest.TestCase):
    """The CI workflow is asserted as text: the suite stays standard-library only."""

    def workflow(self) -> str:
        path = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(path.is_file(), "the CI workflow must exist")
        return path.read_text(encoding="utf-8")

    def test_the_matrix_covers_every_supported_host(self) -> None:
        text = self.workflow()
        for host in ("ubuntu-latest", "macos-latest", "windows-latest"):
            with self.subTest(host=host):
                self.assertIn(host, text)

    def test_the_matrix_covers_both_python_versions(self) -> None:
        text = self.workflow()
        for version in ('"3.11"', '"3.13"'):
            with self.subTest(version=version):
                self.assertIn(version, text)

    def test_every_job_runs_the_offline_gates(self) -> None:
        text = self.workflow()
        for command in (
            "python -m compileall -q scripts tests",
            "python -m unittest discover -s tests -v",
            "python scripts/validate_distribution.py .",
            "git diff --check",
        ):
            with self.subTest(command=command):
                self.assertIn(command, text)

    def test_no_job_installs_a_dependency(self) -> None:
        """A job that installed anything would stop being evidence that none is needed."""
        lowered = self.workflow().lower()
        for forbidden in ("pip install", "npm install", "poetry install", "requirements"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)


class RuntimeEvidenceTests(unittest.TestCase):
    """External gates must be declared per version, never inherited from an older one."""

    GATES = (
        "remote_ci_matrix",
        "remote_sha_parity",
        "fresh_marketplace_install",
        "fresh_session_no_spend_smoke",
        "paid_canary",
    )

    def evidence(self) -> str:
        return (ROOT / "docs" / "verification" / "runtime.md").read_text(encoding="utf-8")

    def test_every_external_gate_has_an_explicit_status(self) -> None:
        rows = {
            line.split("`")[1]: line
            for line in self.evidence().splitlines()
            if line.startswith("| `")
        }
        for gate in self.GATES:
            with self.subTest(gate=gate):
                self.assertIn(gate, rows, f"{gate} is not declared")
                self.assertRegex(rows[gate], r"PASS|FAIL|NOT_RUN")

    def test_an_unobserved_gate_is_not_reported_as_passing(self) -> None:
        rows = {
            line.split("`")[1]: line
            for line in self.evidence().splitlines()
            if line.startswith("| `")
        }
        for gate in self.GATES:
            if gate in rows:
                with self.subTest(gate=gate):
                    self.assertIn("NOT_RUN", rows[gate], f"{gate} claims a result it cannot show")

    def test_the_earlier_version_evidence_is_labelled_historical(self) -> None:
        text = self.evidence()
        self.assertIn("Historical evidence", text)
        self.assertIn("not evidence for the 0.1.2 candidate", text)



RELEASE_VERSION = "0.1.2"

RELEASE_ARTIFACTS = (
    "CHANGELOG.md",
    "docs/Codex-Image-Factory-Plugin-Architecture.md",
    "docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md",
    "docs/Codex-Image-Factory-Plugin-Technical-Solution.md",
    "docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md",
    "docs/verification/runtime.md",
)

SHA40 = re.compile(r"\b[0-9a-f]{40}\b")


class ReleaseAlignmentTests(unittest.TestCase):
    """One version, stated identically everywhere, with no inherited evidence."""

    def test_the_manifest_declares_the_release_version(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], RELEASE_VERSION)

    def test_every_release_artifact_names_the_release_version(self) -> None:
        for relative in RELEASE_ARTIFACTS:
            with self.subTest(artifact=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(RELEASE_VERSION, text)

    def test_the_distribution_validator_prints_the_release_version(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_distribution.py"), "."],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(RELEASE_VERSION, result.stdout)

    def test_the_candidate_evidence_claims_no_inherited_commit(self) -> None:
        """A prior run's SHA must never appear as evidence for the current candidate."""
        text = (ROOT / "docs/verification/runtime.md").read_text(encoding="utf-8")
        split = text.index("## Historical evidence")
        candidate_section = text[:split]
        self.assertEqual(
            SHA40.findall(candidate_section),
            [],
            "the candidate section must not carry a commit hash it did not observe",
        )
        self.assertNotIn("Observed remote head", candidate_section)


if __name__ == "__main__":
    unittest.main()
