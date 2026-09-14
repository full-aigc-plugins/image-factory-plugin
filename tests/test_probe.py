import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import capability_probe as probe  # noqa: E402


CONFIG_WITH_GENERATION_DISABLED = """
model = "gpt-5.6-sol"
model_provider = "openai"

[features]
image_generation = false
"""

CONFIG_WITH_GENERATION_ENABLED = """
model = "gpt-5.6-sol"
model_provider = "openai"

[features]
image_generation = true
"""

CONFIG_WITHOUT_FEATURE_BLOCK = """
model = "gpt-5.6-sol"
model_provider = "openai"
"""

CONFIG_BEDROCK = """
model = "gpt-5.6-sol"
model_provider = "amazon-bedrock"
"""


class ProbeFixture:
    """Builds a disposable CODEX_HOME plus a PATH directory holding a fake codex."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.codex_home = self.base / "codex-home"
        self.bin_dir = self.base / "bin"
        self.marker = self.base / "binary-was-executed"
        self.codex_home.mkdir()
        self.bin_dir.mkdir()

    def write_auth(self) -> None:
        target = self.codex_home / "auth.json"
        target.write_text('{"tokens": {"access_token": "placeholder"}}', encoding="utf-8")
        os.chmod(target, 0o600)

    def write_config(self, body: str) -> None:
        (self.codex_home / "config.toml").write_text(body, encoding="utf-8")

    def make_generation_dir(self) -> None:
        (self.codex_home / "generated_images").mkdir()

    def place_codex_on_path(self) -> Path:
        target = self.bin_dir / ("codex.cmd" if os.name == "nt" else "codex")
        if os.name == "nt":
            target.write_text(f'@type nul > "{self.marker}"\r\n@exit /b 0\r\n', encoding="utf-8")
        else:
            target.write_text(f"#!/bin/sh\ntouch '{self.marker}'\nexit 0\n", encoding="utf-8")
            os.chmod(target, 0o755)
        return target

    def probe(self) -> "probe.Capability":
        return probe.probe(
            search_path=(str(self.bin_dir),),
            codex_home=self.codex_home,
            config_path=self.codex_home / "config.toml",
        )

    def probe_with_binary(self, binary: Path) -> "probe.Capability":
        return probe.probe(
            search_path=(str(self.bin_dir),),
            codex_home=self.codex_home,
            config_path=self.codex_home / "config.toml",
            binary_override=binary,
        )

    def cleanup(self) -> None:
        self._tmp.cleanup()


class CapabilityProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ProbeFixture()
        self.addCleanup(self.fixture.cleanup)

    def test_missing_binary_is_unavailable_with_guidance(self) -> None:
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "unavailable")
        self.assertIn("codex_binary_missing", result.reasons)
        self.assertIn("codex", result.guidance.lower())
        self.assertIsNone(result.codex_binary)

    def test_healthy_environment_is_available(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "available", result.reasons)
        self.assertTrue(result.auth_present)
        self.assertTrue(result.generation_dir_writable)
        self.assertIn("verified_codex_binary", result.reasons)

    def test_missing_auth_is_unavailable(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "unavailable")
        self.assertIn("auth_missing", result.reasons)

    def test_explicit_feature_disable_is_unavailable(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_DISABLED)
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "unavailable")
        self.assertIn("generation_disabled_by_config", result.reasons)
        self.assertIs(result.image_generation_override, False)

    def test_absence_of_override_stays_unknown_not_assumed(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITHOUT_FEATURE_BLOCK)
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "available")
        self.assertIsNone(result.image_generation_override)

    def test_bedrock_provider_disables_generation(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_BEDROCK)
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "unavailable")
        self.assertIn("provider_lacks_image_generation", result.reasons)

    @unittest.skipIf(os.name == "nt", "Windows chmod does not remove directory write access")
    def test_unwritable_generation_dir_is_unavailable(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        blocked = self.fixture.codex_home / "generated_images"
        blocked.mkdir()
        os.chmod(blocked, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, blocked, 0o755)
        result = self.fixture.probe()
        self.assertFalse(result.generation_dir_writable)
        self.assertEqual(result.verdict, "unavailable")
        self.assertIn("generation_dir_unwritable", result.reasons)

    def test_appserver_binary_is_used_as_fallback(self) -> None:
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        bundled = self.fixture.codex_home / "plugins" / ".plugin-appserver" / (
            "codex.cmd" if os.name == "nt" else "codex"
        )
        bundled.parent.mkdir(parents=True)
        bundled.write_text("@exit /b 0\r\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(bundled, 0o755)
        result = self.fixture.probe()
        self.assertEqual(result.binary_source, "codex_home_appserver")
        self.assertEqual(result.verdict, "available")

    def test_probe_never_executes_the_binary(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        self.fixture.probe()
        self.assertFalse(
            self.fixture.marker.exists(),
            "the probe must stay offline and must not spawn the codex binary",
        )

    def test_report_never_claims_a_model(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        payload = probe.as_report(self.fixture.probe())
        self.assertIsNone(payload["model_reported"])
        self.assertIn("model_is_chosen_by_codex", payload["unverified"])
        self.assertIn("account_plan_type", payload["unverified"])
        self.assertNotIn("gpt-image", json.dumps(payload))
        round_tripped = json.loads(probe.render_json(self.fixture.probe()))
        self.assertEqual(round_tripped["verdict"], payload["verdict"])
        self.assertEqual(round_tripped["schema_version"], "1.0.0")

    def test_configured_model_is_reported_separately_from_image_model(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.configured_model, "gpt-5.6-sol")
        self.assertEqual(result.configured_provider, "openai")
        self.assertIsNone(result.model_reported)

    def test_malformed_config_does_not_crash_the_probe(self) -> None:
        self.fixture.place_codex_on_path()
        self.fixture.write_auth()
        self.fixture.write_config("this is not = valid toml [[[")
        self.fixture.make_generation_dir()
        result = self.fixture.probe()
        self.assertEqual(result.verdict, "available")
        self.assertIn("config_unreadable", result.reasons)

    def test_an_explicit_binary_overrides_the_search(self) -> None:
        """Without this, a caller that already resolved the binary cannot use it."""
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        explicit = self.fixture.base / "elsewhere" / ("codex.cmd" if os.name == "nt" else "codex")
        explicit.parent.mkdir()
        explicit.write_text("@exit /b 0\r\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(explicit, 0o755)
        result = self.fixture.probe_with_binary(explicit)
        self.assertEqual(result.verdict, "available", result.reasons)
        self.assertEqual(result.binary_source, "explicit")
        self.assertEqual(result.codex_binary, explicit)

    def test_a_non_executable_override_is_unavailable(self) -> None:
        self.fixture.write_auth()
        self.fixture.write_config(CONFIG_WITH_GENERATION_ENABLED)
        self.fixture.make_generation_dir()
        plain = self.fixture.base / "not-executable"
        plain.write_text("data", encoding="utf-8")
        result = self.fixture.probe_with_binary(plain)
        self.assertEqual(result.verdict, "unavailable")
        self.assertIn("codex_binary_missing", result.reasons)

    def test_windows_accepts_cmd_launchers_but_rejects_arbitrary_files(self) -> None:
        launcher = self.fixture.base / "codex.cmd"
        launcher.write_text("@exit /b 0\n", encoding="utf-8")
        arbitrary = self.fixture.base / "codex.txt"
        arbitrary.write_text("data", encoding="utf-8")
        self.assertTrue(probe._is_executable_file(launcher, platform_name="nt"))
        self.assertFalse(probe._is_executable_file(arbitrary, platform_name="nt"))


if __name__ == "__main__":
    unittest.main()
