import json
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from pathlib import Path
import tomllib

from vybelix.progress import ProgressStore
from vybelix.ui import make_handler, project_snapshot
from vybelix.ui_actions import UIActionError, UIActions
from vybelix.project_context import empty_context


class UISnapshotTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        (root / "vybelix.toml").write_text(
            "schema_version = \"1.0\"\n\n[models]\n"
            "planner = [\"gemini:gemini-3.8-flash\"]\n"
            "coder = []\ntester = []\n",
            encoding="utf-8",
        )
        store = ProgressStore(root / "docs" / "progress" / "tasks.json")
        store.save({
            "schema_version": "1.0",
            "project_id": "ui-test",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [{
                "id": "task-1", "title": "Tâche réelle", "status": "needs_review",
                "dependencies": [], "acceptance_criteria": ["Critère"], "attempts": 0,
                "files_modified": [], "verifications": [], "last_result": None,
            }],
        })
        return root

    def test_model_route_update_persists_order_and_preserves_other_config(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            config_path = project / "vybelix.toml"
            config_path.write_text(
                'schema_version = "1.0"\n\n[providers.openai]\n'
                'base_url = "https://api.openai.com/v1"\napi_key_env = "OPENAI_API_KEY"\n\n'
                '[providers.gemini]\nbase_url = "https://generativelanguage.googleapis.com/v1beta"\n'
                'api_key_env = "GEMINI_API_KEY"\n\n'
                '[models]\nplanner = ["gemini:gemini-3.8-flash"]\ncoder = []\ntester = []\n\n'
                '[verifier]\nallowed_commands = []\n',
                encoding="utf-8",
            )
            routes = {
                "planner": ["openai:gpt-4o", "gemini:gemini-3.8-flash"],
                "coder": ["openai:gpt-4o-mini"],
                "tester": [],
            }
            result = UIActions(project).update_model_routes(routes)
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(result["routes"], routes)
        self.assertEqual(data["models"]["planner"], routes["planner"])
        self.assertEqual(data["models"]["coder"], routes["coder"])
        self.assertEqual(data["models"]["tester"], [])
        self.assertEqual(data["providers"]["openai"]["api_key_env"], "OPENAI_API_KEY")
        self.assertEqual(data["verifier"]["allowed_commands"], [])

    def test_model_route_update_allows_removing_the_last_model_from_an_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            actions = UIActions(project)
            result = actions.update_model_routes({"planner": [], "coder": [], "tester": []})
            config = tomllib.loads((project / "vybelix.toml").read_text(encoding="utf-8"))
        self.assertEqual(result["routes"]["planner"], [])
        self.assertEqual(config["models"]["planner"], [])

    def test_remove_model_route_removes_only_the_selected_agent_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            config_path = project / "vybelix.toml"
            config_path.write_text(
                'schema_version = "1.0"\n\n'
                '[providers.openai]\nbase_url = "https://api.openai.com/v1"\napi_key_env = "OPENAI_API_KEY"\n\n'
                '[models]\nplanner = ["openai:gpt-4o", "openai:gpt-4o-mini"]\n'
                'coder = ["openai:gpt-4o-mini"]\ntester = []\n', encoding="utf-8")
            actions = UIActions(project)
            result = actions.remove_model_route("planner", "openai:gpt-4o")
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(result["routes"]["planner"], ["openai:gpt-4o-mini"])
        self.assertEqual(config["models"]["planner"], ["openai:gpt-4o-mini"])
        self.assertEqual(config["models"]["coder"], ["openai:gpt-4o-mini"])

    def test_remove_model_route_rejects_stale_model_without_changing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            config_path = project / "vybelix.toml"
            config_path.write_text(
                'schema_version = "1.0"\n\n'
                '[providers.openai]\nbase_url = "https://api.openai.com/v1"\napi_key_env = "OPENAI_API_KEY"\n\n'
                '[models]\nplanner = ["openai:gpt-4o"]\ncoder = []\ntester = []\n', encoding="utf-8")
            before = config_path.read_text(encoding="utf-8")
            with self.assertRaises(UIActionError):
                UIActions(project).remove_model_route("planner", "openai:stale")
            self.assertEqual(config_path.read_text(encoding="utf-8"), before)

    def test_model_route_update_rejects_unconfigured_provider_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            config_path = project / "vybelix.toml"
            before = config_path.read_text(encoding="utf-8")
            actions = UIActions(project)
            with self.assertRaises(UIActionError):
                actions.update_model_routes({
                    "planner": ["openai:gpt-4o"], "coder": [], "tester": []
                })
            self.assertEqual(config_path.read_text(encoding="utf-8"), before)

    def test_snapshot_uses_real_counts_and_marks_models_unchecked(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            snapshot = project_snapshot(project)
        self.assertEqual(snapshot["project"]["id"], "ui-test")
        self.assertEqual(snapshot["tasks"]["total"], 1)
        self.assertEqual(snapshot["tasks"]["by_status"]["needs_review"], 1)
        self.assertEqual(snapshot["routes"][0]["model"], "gemini-3.8-flash")
        self.assertEqual(snapshot["routes"][0]["availability"], "not_checked")
        self.assertFalse(snapshot["capabilities"]["provider_calls"])
        self.assertFalse(snapshot["capabilities"]["writes"])

    def test_snapshot_does_not_expose_secrets_or_full_task_content(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            snapshot = project_snapshot(project)
        rendered = json.dumps(snapshot)
        self.assertNotIn("api_key_env", rendered)
        self.assertNotIn("last_result", rendered)
        self.assertNotIn("items", snapshot["tasks"])

    def test_context_is_saved_locally_and_resume_requires_eligible_task(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            actions = UIActions(project)
            context = empty_context("ui-test")
            context["goal"] = "Objectif local"
            self.assertTrue(actions.save_project_context(context)["saved"])
            self.assertEqual(actions.project_context()["goal"], "Objectif local")
            with self.assertRaises(UIActionError):
                actions.resume_task("task-1", True)
            store = ProgressStore(project / "docs" / "progress" / "tasks.json")
            data = store.load()
            data["tasks"][0]["status"] = "interrupted"
            store.save(data)
            with self.assertRaises(UIActionError):
                actions.resume_task("task-1", False)
            self.assertEqual(actions.resume_task("task-1", True)["status"], "todo")

    def test_local_shell_serves_real_state_and_rejects_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            assets = Path(__file__).parents[1] / "src" / "vybelix" / "ui_assets"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(project, assets))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"Vybelix", response.read())
                with urlopen(base + "/api/state", timeout=3) as response:
                    payload = json.loads(response.read())
                    self.assertEqual(payload["project"]["id"], "ui-test")
                    self.assertFalse(payload["capabilities"]["writes"])
                request = Request(base + "/api/state", data=b"{}", method="POST", headers={"Origin": base, "Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request, timeout=3)
                self.assertEqual(error.exception.code, 405)
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()

    def test_context_http_routes_serve_and_save_validated_local_data(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            assets = Path(__file__).parents[1] / "src" / "vybelix" / "ui_assets"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(project, assets))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/api/context", timeout=3) as response:
                    context = json.loads(response.read())
                context["goal"] = "But via cockpit"
                request = Request(base + "/api/context", data=json.dumps(context).encode(), method="POST",
                                  headers={"Origin": base, "Content-Type": "application/json"})
                with urlopen(request, timeout=3) as response:
                    self.assertTrue(json.loads(response.read())["saved"])
                self.assertEqual(UIActions(project).project_context()["goal"], "But via cockpit")
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()

    def test_remove_model_route_http_endpoint_persists_fallback_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            (project / "vybelix.toml").write_text(
                'schema_version = "1.0"\n\n'
                '[providers.openai]\nbase_url = "https://api.openai.com/v1"\napi_key_env = "OPENAI_API_KEY"\n\n'
                '[models]\nplanner = ["openai:gpt-4o", "openai:gpt-4o-mini"]\n'
                'coder = []\ntester = []\n', encoding="utf-8")
            assets = Path(__file__).parents[1] / "src" / "vybelix" / "ui_assets"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(project, assets))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                request = Request(base + "/api/models/remove",
                                  data=json.dumps({"role": "planner", "model": "openai:gpt-4o-mini"}).encode(),
                                  method="POST", headers={"Origin": base, "Content-Type": "application/json"})
                with urlopen(request, timeout=3) as response:
                    result = json.loads(response.read())
                config = tomllib.loads((project / "vybelix.toml").read_text(encoding="utf-8"))
                self.assertEqual(config["models"]["planner"], ["openai:gpt-4o"])
                self.assertEqual(result["role"], "planner")
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
