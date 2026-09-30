import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from vybelix.cli import _cache_file, main
from vybelix.progress import ProgressStore


class CliTests(unittest.TestCase):
    def test_cache_path_stays_inside_project(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.assertTrue(_cache_file(project, "plan.json").is_relative_to(project))
            with self.assertRaises(ValueError):
                _cache_file(project, "..", "outside.json")

    def test_init_creates_local_config_and_progress_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "mon projet"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["init", str(project)]), 0)
            config = project / "vybelix.toml"
            progress = project / "docs" / "progress" / "tasks.json"
            self.assertTrue(config.is_file())
            self.assertEqual(ProgressStore(progress).load()["project_id"], "mon-projet")
            original = config.read_text(encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["init", str(project)]), 0)
            self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_verify_records_actual_result_in_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["init", str(project)]), 0)
            command = 'python -c "print(\'check passed\')"'
            config_path = project / "vybelix.toml"
            config_text = config_path.read_text(encoding="utf-8").replace(
                "allowed_commands = []", f"allowed_commands = [{json.dumps(command)}]"
            )
            config_path.write_text(config_text, encoding="utf-8")
            progress_store = ProgressStore(project / "docs" / "progress" / "tasks.json")
            progress = progress_store.load()
            progress["tasks"].append({
                "id": "task-1", "title": "Vérifier la CLI", "status": "in_progress",
                "dependencies": [], "acceptance_criteria": ["La commande réussit"], "attempts": 0,
                "files_modified": [], "verifications": [], "last_result": None,
            })
            progress_store.save(progress)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["verify", "--project", str(project), "--task-id", "task-1", "--command", command]), 0)
            saved = progress_store.load()["tasks"][0]
            self.assertEqual(saved["verifications"][0]["exit_code"], 0)
            self.assertIn("check passed", saved["last_result"])

    def test_unapproved_command_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with redirect_stdout(io.StringIO()):
                main(["init", str(project)])
            store = ProgressStore(project / "docs" / "progress" / "tasks.json")
            data = store.load()
            data["tasks"].append({
                "id": "absent", "title": "Test", "status": "in_progress", "dependencies": [],
                "acceptance_criteria": ["No execution"], "attempts": 0, "files_modified": [],
                "verifications": [], "last_result": None,
            })
            store.save(data)
            error = io.StringIO()
            with redirect_stderr(error):
                result = main(["verify", "--project", str(project), "--task-id", "absent", "--command", "whoami"])
            self.assertEqual(result, 2)
            self.assertIn("pas dans la liste", error.getvalue())

    def test_plan_is_saved_and_added_only_after_interactive_approval(self):
        plan = {
            "schema_version": "1.0", "project_id": "demo", "request_summary": "Créer hello.txt",
            "affected_paths": ["hello.txt"], "tasks": [{
                "id": "task-plan-1", "parent_id": None, "title": "Créer hello.txt",
                "description": "Écrire le fichier.", "type": "code", "role": "coder", "priority": 2,
                "dependencies": [], "acceptance_criteria": ["Le fichier existe"],
                "verification_strategy": "Vérifier son contenu.",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with redirect_stdout(io.StringIO()):
                main(["init", str(project)])
            progress_path = project / "docs" / "progress" / "tasks.json"
            progress_store = ProgressStore(progress_path)
            data = progress_store.load()
            data["project_id"] = "demo"
            progress_store.save(data)
            with patch("vybelix.cli.build_router", return_value=object()), patch(
                "vybelix.cli.VybelixWorkflow"
            ) as workflow_type:
                workflow_type.return_value.create_plan.return_value = plan
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["plan", "Créer hello.txt", "--project", str(project)]), 0)
            self.assertTrue((project / ".vybelix-cache" / "plan.json").is_file())
            with patch("builtins.input", return_value="o"), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["approve-plan", "--project", str(project)]), 0)
            self.assertEqual(progress_store.load()["tasks"][0]["status"], "todo")

    def test_rejected_plan_does_not_add_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with redirect_stdout(io.StringIO()):
                main(["init", str(project)])
            project_id = ProgressStore(project / "docs" / "progress" / "tasks.json").load()["project_id"]
            plan = {
                "schema_version": "1.0", "project_id": project_id, "request_summary": "Rien",
                "affected_paths": [], "tasks": [{
                    "id": "task-plan-1", "parent_id": None, "title": "Tâche", "description": "À faire",
                    "type": "analysis", "role": "planner", "priority": 1, "dependencies": [],
                    "acceptance_criteria": ["Analyse faite"], "verification_strategy": "Relire le résultat",
                }],
            }
            cache = project / ".vybelix-cache"
            cache.mkdir()
            (cache / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            with patch("builtins.input", return_value="n"), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["approve-plan", "--project", str(project)]), 0)
            self.assertEqual(ProgressStore(project / "docs" / "progress" / "tasks.json").load()["tasks"], [])

    def test_failed_verification_allows_at_most_two_manual_corrections(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with redirect_stdout(io.StringIO()):
                main(["init", str(project)])
            task = {
                "id": "task-1", "parent_id": None, "title": "Créer hello", "description": "Créer un fichier",
                "type": "code", "role": "coder", "priority": 2, "dependencies": [],
                "acceptance_criteria": ["fichier présent"], "verification_strategy": "vérifier le fichier",
            }
            (project / ".vybelix-cache").mkdir(exist_ok=True)
            (project / ".vybelix-cache" / "plan.json").write_text(json.dumps({
                "schema_version": "1.0", "project_id": project.name, "request_summary": "Créer hello",
                "affected_paths": ["hello.txt"], "tasks": [task],
            }), encoding="utf-8")
            store = ProgressStore(project / "docs" / "progress" / "tasks.json")
            data = store.load()
            data["tasks"].append({
                "id": "task-1", "title": "Créer hello", "status": "needs_review", "dependencies": [],
                "acceptance_criteria": ["fichier présent"], "attempts": 1, "files_modified": [],
                "verifications": [{"errors": ["fichier manquant"]}], "last_result": "Échec de vérification.",
            })
            store.save(data)
            proposal = {
                "schema_version": "1.0", "task_id": "task-1", "summary": "Correction",
                "files": [{"path": "hello.txt", "operation": "write", "content": "ok"}],
                "notes": [], "verification_hints": [],
            }
            with patch("vybelix.cli.build_router", return_value=object()), patch("vybelix.cli.VybelixWorkflow") as flow:
                flow.return_value.create_code_proposal.return_value = proposal
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["code", "--project", str(project), "--task-id", "task-1"]), 0)
                self.assertEqual(store.load()["tasks"][0]["attempts"], 2)
                with redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(main(["code", "--project", str(project), "--task-id", "task-1"]), 2)
                self.assertIn("limite de corrections", error.getvalue())


if __name__ == "__main__":
    unittest.main()
