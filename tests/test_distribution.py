import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import validate_distribution


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "codex-image-factory"
DISPLAY_NAME = "Codex Image Factory"
REPOSITORY = "https://github.com/partme-ai/codex-image-factory-plugin"
BRAND_COLOR = "#10B981"
RELEASE_VERSION = "0.1.2"


def load_json(relative: str) -> dict:
    target = ROOT / relative
    if not target.is_file():
        raise AssertionError(f"missing distribution file: {relative}")
    return json.loads(target.read_text(encoding="utf-8"))


def png_shape(relative: str) -> tuple[int, int, int]:
    data = (ROOT / relative).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not PNG: {relative}")
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


class DistributionTests(unittest.TestCase):
    def validator_errors_for_workflow(self, workflow: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex-plugin").mkdir()
            (root / ".agents/plugins").mkdir(parents=True)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".codex-plugin/plugin.json").write_text(
                json.dumps(
                    {
                        "name": PLUGIN_ID,
                        "version": RELEASE_VERSION,
                        "repository": REPOSITORY,
                        "skills": "./skills/",
                        "interface": {},
                    }
                ),
                encoding="utf-8",
            )
            (root / ".agents/plugins/marketplace.json").write_text(
                json.dumps({"plugins": []}), encoding="utf-8"
            )
            (root / ".github/workflows/ci.yml").write_text(workflow, encoding="utf-8")
            return validate_distribution.validate(root)

    def test_ci_runs_the_offline_gates_on_the_supported_matrix(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for operating_system in ("ubuntu-latest", "macos-latest", "windows-latest"):
            self.assertIn(operating_system, workflow)
        for python_version in ('"3.11"', '"3.13"'):
            self.assertIn(python_version, workflow)
        for command in (
            "python -m compileall -q scripts tests",
            "python -m unittest discover -s tests -v",
            "python scripts/validate_distribution.py .",
            "git diff --check",
        ):
            self.assertIn(command, workflow)
        self.assertNotIn("pip install", workflow)

    def test_vendored_upstream_snapshots_disable_git_text_conversion(self) -> None:
        vendored_files = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "vendor" / "upstream").rglob("*")
            if path.is_file()
        )
        self.assertTrue(vendored_files)
        result = subprocess.run(
            ["git", "check-attr", "-z", "text", "--", *vendored_files],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        fields = result.stdout.decode("utf-8").split("\0")
        self.assertEqual(fields[-1], "")
        attributes = {
            path: (attribute, value)
            for path, attribute, value in zip(
                fields[0:-1:3], fields[1:-1:3], fields[2:-1:3], strict=True
            )
        }
        self.assertEqual(set(attributes), set(vendored_files))
        for path in vendored_files:
            with self.subTest(path=path):
                self.assertEqual(attributes[path], ("text", "unset"))

    def test_validator_rejects_extra_ci_matrix_axes_and_values(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        workflow = workflow.replace(
            'python-version: ["3.11", "3.13"]',
            'python-version: ["3.11", "3.12", "3.13"]\n        architecture: [x64]',
        )
        errors = self.validator_errors_for_workflow(workflow)
        self.assertIn(
            "CI matrix must contain exactly os and python-version with the supported values",
            errors,
        )

    def test_validator_rejects_dependency_installer_variants(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for command in (
            "pip install package",
            "python -m pip install package",
            "uv sync",
            "poetry install",
            "pipx install package",
            "conda install package",
        ):
            with self.subTest(command=command):
                candidate = workflow + f"\n      - run: {command}\n"
                errors = self.validator_errors_for_workflow(candidate)
                self.assertIn("CI workflow must not install dependencies", errors)

    def test_validator_accepts_distribution(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_distribution.py"), str(ROOT)],
            capture_output=True,
            text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"validated {PLUGIN_ID} compatibility foundation {RELEASE_VERSION}",
            result.stdout,
        )

    def test_validator_accepts_relative_root(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_distribution.py"), "docs/.."],
            capture_output=True,
            text=True, encoding="utf-8",
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_manifest_and_marketplace(self) -> None:
        manifest = load_json(".codex-plugin/plugin.json")
        self.assertEqual(manifest["name"], PLUGIN_ID)
        self.assertEqual(manifest["version"], RELEASE_VERSION)
        self.assertEqual(manifest["repository"], REPOSITORY)
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("mcpServers", manifest)
        interface = manifest["interface"]
        self.assertEqual(interface["displayName"], DISPLAY_NAME)
        self.assertEqual(interface["category"], "Creativity")
        self.assertEqual(interface["brandColor"], BRAND_COLOR)
        self.assertEqual(interface["logo"], "./assets/logo.png")
        self.assertEqual(interface["logoDark"], "./assets/logo-dark.png")
        self.assertEqual(interface["composerIcon"], "./assets/composer-icon.png")
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        self.assertTrue(all(len(prompt) <= 128 for prompt in interface["defaultPrompt"]))

        marketplace = load_json(".agents/plugins/marketplace.json")
        entries = [entry for entry in marketplace["plugins"] if entry["name"] == PLUGIN_ID]
        self.assertEqual(len(entries), 1)
        self.assertEqual(marketplace["name"], "partme-ai-image-factory")
        self.assertEqual(
            entries[0]["source"],
            {"source": "url", "url": REPOSITORY + ".git", "ref": "main"},
        )
        self.assertEqual(entries[0]["policy"], {"installation": "AVAILABLE", "authentication": "ON_USE"})

    def test_structure_legal_and_brand_assets(self) -> None:
        for directory in ("assets", "skills", "schemas", "scripts", "tests"):
            self.assertTrue((ROOT / directory).is_dir(), directory)
        for filename in (
            "LICENSE",
            "NOTICE",
            "PRIVACY.md",
            "TERMS.md",
            "THIRD_PARTY_NOTICES.md",
            ".gitignore",
            "README.md",
            "README.zh-CN.md",
            "docs/portable-migration.md",
            "scripts/validate_distribution.py",
        ):
            self.assertTrue((ROOT / filename).is_file(), filename)
        self.assertFalse((ROOT / "plugin.json").exists())
        self.assertFalse((ROOT / "mcp.json").exists())
        self.assertFalse((ROOT / ".mcp.json").exists())
        self.assertEqual(png_shape("assets/logo.png"), (1024, 1024, 6))
        self.assertEqual(png_shape("assets/logo-dark.png"), (1024, 1024, 6))
        self.assertEqual(png_shape("assets/composer-icon.png"), (256, 256, 6))

    def test_readme_pair_is_linked(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("README.zh-CN.md", english)
        self.assertIn("README.md", chinese)
        for text in (english, chinese):
            self.assertIn(PLUGIN_ID, text)


if __name__ == "__main__":
    unittest.main()
