import json
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from pathlib import Path

from vybelix.progress import ProgressStore
from vybelix.ui import make_handler, project_snapshot


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
                    self.assertIn(b"VYBELIX", response.read())
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


if __name__ == "__main__":
    unittest.main()
