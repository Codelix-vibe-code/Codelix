import unittest
from pathlib import Path

from vybelix.config import ConfigurationError, VybelixConfig, load_config, validate_config
from vybelix.paths import project_config_path


class ConfigTests(unittest.TestCase):
    def test_defaults_are_safe(self):
        config = validate_config({"schema_version": "1.0"})
        self.assertEqual(config.runtime.request_timeout_seconds, 300)
        self.assertEqual(config.runtime.max_file_bytes, 204800)
        self.assertEqual(config.runtime.correction_attempts, 2)
        self.assertEqual(config.runtime.network_retries, 2)
        self.assertEqual(config.allowed_commands, ())

    def test_accepts_example_shape(self):
        config = validate_config({
            "schema_version": "1.0",
            "runtime": {"request_timeout_seconds": 300, "max_file_bytes": 204800, "correction_attempts": 2, "network_retries": 2},
            "providers": {"gemini": {"base_url": "", "api_key_env": "GEMINI_API_KEY"}},
            "models": {"planner": [], "coder": [], "tester": []},
            "verifier": {"allowed_commands": []},
        })
        self.assertEqual(config.providers["gemini"].api_key_env, "GEMINI_API_KEY")

    def test_example_toml_loads(self):
        example = Path(__file__).resolve().parents[1] / "config.example.toml"
        self.assertEqual(load_config(example).allowed_commands, ())

    def test_rejects_excessive_correction_attempts(self):
        with self.assertRaises(ConfigurationError):
            validate_config({"schema_version": "1.0", "runtime": {"correction_attempts": 3}})

    def test_rejects_non_https_provider_url(self):
        with self.assertRaises(ConfigurationError):
            validate_config({"schema_version": "1.0", "providers": {"x": {"base_url": "http://example.test"}}})

    def test_rejects_unknown_configuration_keys(self):
        with self.assertRaises(ConfigurationError):
            validate_config({"schema_version": "1.0", "surprise": True})

    def test_rejects_duplicate_models(self):
        with self.assertRaises(ConfigurationError):
            validate_config({"schema_version": "1.0", "models": {"coder": ["model-a", "model-a"]}})

    def test_legacy_imports_resolve_to_primary_types(self):
        from codelix.config import CodelixConfig
        from codelix.workflow import CodelixWorkflow
        from vybelix.workflow import VybelixWorkflow

        self.assertIs(CodelixConfig, VybelixConfig)
        self.assertIs(CodelixWorkflow, VybelixWorkflow)

    def test_legacy_config_is_used_until_new_config_exists(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            legacy = project / "codelix.toml"
            legacy.write_text("legacy", encoding="utf-8")
            self.assertEqual(project_config_path(project), legacy)
            current = project / "vybelix.toml"
            current.write_text("current", encoding="utf-8")
            self.assertEqual(project_config_path(project), current)


if __name__ == "__main__":
    unittest.main()
