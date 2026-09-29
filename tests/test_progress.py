import json
import tempfile
import unittest
from pathlib import Path

from codelix.progress import ProgressError, ProgressStore, validate_progress


def task(task_id, dependencies=None):
    return {
        "id": task_id,
        "title": f"Tâche {task_id}",
        "status": "todo",
        "dependencies": dependencies or [],
        "acceptance_criteria": ["Critère observable"],
        "attempts": 0,
        "files_modified": [],
        "verifications": [],
        "last_result": None,
    }


def progress(tasks=None):
    return {"schema_version": "1.0", "project_id": "codelix", "updated_at": "2026-09-29T00:00:00Z", "tasks": tasks or [task("one")]}


class ProgressTests(unittest.TestCase):
    def test_accepts_valid_progress(self):
        self.assertEqual(validate_progress(progress())["project_id"], "codelix")

    def test_rejects_unknown_status(self):
        value = progress()
        value["tasks"][0]["status"] = "finished"
        with self.assertRaises(ProgressError):
            validate_progress(value)

    def test_rejects_unknown_dependency(self):
        with self.assertRaises(ProgressError):
            validate_progress(progress([task("one", ["missing"])]))

    def test_rejects_more_than_two_attempts(self):
        value = progress()
        value["tasks"][0]["attempts"] = 3
        with self.assertRaises(ProgressError):
            validate_progress(value)

    def test_rejects_timestamp_without_timezone(self):
        value = progress()
        value["updated_at"] = "2026-09-29T12:00:00"
        with self.assertRaises(ProgressError):
            validate_progress(value)

    def test_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docs" / "tasks.json"
            store = ProgressStore(path)
            store.save(progress())
            self.assertEqual(store.load(), progress())
            self.assertTrue(json.loads(path.read_text(encoding="utf-8")))

    def test_repository_progress_file_is_valid(self):
        path = Path(__file__).resolve().parents[1] / "docs" / "progress" / "tasks.json"
        data = ProgressStore(path).load()
        phase_one = next(item for item in data["tasks"] if item["id"] == "phase-1-foundations")
        self.assertEqual(phase_one["status"], "done")


if __name__ == "__main__":
    unittest.main()
