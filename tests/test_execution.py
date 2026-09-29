import tempfile
import unittest
from pathlib import Path

from codelix.execution import (
    ExecutionError,
    ExecutionManager,
    FileConflictError,
)


def proposal(path="hello.txt", content="nouveau"):
    return {
        "schema_version": "1.0",
        "task_id": "task-1",
        "summary": "Mettre à jour un fichier.",
        "files": [{"path": path, "operation": "write", "content": content}],
        "notes": [],
        "verification_hints": [],
    }


class ExecutionManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "hello.txt").write_text("ancien", encoding="utf-8")
        self.manager = ExecutionManager(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_preview_only_describes_changes_without_writing(self):
        snapshots = self.manager.inspect(["hello.txt"])
        preview = self.manager.preview(proposal(), expected_task_id="task-1", snapshots=snapshots)
        self.assertEqual(preview[0]["operation"], "replace")
        self.assertEqual((self.root / "hello.txt").read_text(encoding="utf-8"), "ancien")

    def test_apply_requires_approval_then_writes_backup(self):
        snapshots = self.manager.inspect(["hello.txt"])
        pending = self.manager.apply(proposal(), expected_task_id="task-1", snapshots=snapshots)
        self.assertEqual(pending.status, "needs_approval")
        self.assertEqual((self.root / "hello.txt").read_text(encoding="utf-8"), "ancien")
        result = self.manager.apply(proposal(), expected_task_id="task-1", snapshots=snapshots, approved=True)
        self.assertEqual(result.status, "applied")
        self.assertEqual((self.root / "hello.txt").read_text(encoding="utf-8"), "nouveau")
        backup = self.root / ".codelix-backups" / result.backup_id / "hello.txt"
        self.assertEqual(backup.read_text(encoding="utf-8"), "ancien")

    def test_rejects_secret_git_progress_and_backup_paths(self):
        for path in (".env", ".git/config", "docs/progress/tasks.json", ".codelix-backups/keep.txt"):
            with self.subTest(path=path):
                with self.assertRaises(ExecutionError):
                    self.manager.inspect([path])

    def test_rejects_path_escape_and_symlink(self):
        with self.assertRaises(ExecutionError):
            self.manager.inspect(["../outside.txt"])
        outside = self.root.parent / f"{self.root.name}-outside.txt"
        outside.write_text("protected", encoding="utf-8")
        link = self.root / "linked.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            outside.unlink(missing_ok=True)
            self.skipTest("Création de lien symbolique interdite sur cet environnement.")
        try:
            with self.assertRaises(ExecutionError):
                self.manager.inspect(["linked.txt"])
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_detects_conflict_since_inspection(self):
        snapshots = self.manager.inspect(["hello.txt"])
        (self.root / "hello.txt").write_text("édition concurrente", encoding="utf-8")
        with self.assertRaises(FileConflictError):
            self.manager.preview(proposal(), expected_task_id="task-1", snapshots=snapshots)

    def test_enforces_content_size(self):
        manager = ExecutionManager(self.root, max_file_bytes=2)
        snapshots = manager.inspect(["hello.txt"])
        with self.assertRaises(ExecutionError):
            manager.preview(proposal(content="trop"), expected_task_id="task-1", snapshots=snapshots)


if __name__ == "__main__":
    unittest.main()
