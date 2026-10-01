import tempfile
import unittest
from pathlib import Path

from vybelix.project_context import ProjectContextError, ProjectContextStore, empty_context


class ProjectContextTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectContextStore(Path(directory) / ".vybelix-cache" / "context.json", "demo")
            value = empty_context("demo")
            value["goal"] = "Construire une CLI locale"
            value["next_steps"] = ["Relire les critères"]
            saved = store.save(value)
            self.assertEqual(store.load()["goal"], value["goal"])
            self.assertEqual(saved["project_id"], "demo")
            self.assertIsNotNone(saved["updated_at"])

    def test_rejects_other_project_secrets_and_secret_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectContextStore(Path(directory) / "context.json", "demo")
            with self.assertRaises(ProjectContextError):
                store.save({**empty_context("other"), "goal": "wrong project"})
            with self.assertRaises(ProjectContextError):
                store.save({**empty_context("demo"), "goal": "api_key=ghp_12345678901234567890"})
            with self.assertRaises(ProjectContextError):
                store.save({**empty_context("demo"), "relevant_files": [{"path": ".env", "summary": "secret"}]})
            self.assertFalse(store.path.exists())


if __name__ == "__main__":
    unittest.main()
