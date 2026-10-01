import json
import tempfile
import unittest
from pathlib import Path

from vybelix.config import validate_config
from vybelix.execution import ExecutionError
from vybelix.workflow import VybelixWorkflow, WorkflowError


def config():
    return validate_config({"schema_version": "1.0", "models": {"planner": ["fake:planner"], "coder": ["fake:coder"]}})


class FakeRouter:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, role, messages):
        self.calls.append((role, messages))
        return self.responses.pop(0)


def valid_plan():
    return {
        "schema_version": "1.0", "project_id": "demo", "request_summary": "Créer un fichier.",
        "affected_paths": ["hello.txt"], "tasks": [{
            "id": "task-1", "parent_id": None, "title": "Créer hello", "description": "Créer le fichier.",
            "type": "code", "role": "coder", "priority": 2, "dependencies": [],
            "acceptance_criteria": ["Le fichier contient bonjour"], "verification_strategy": "Lire le fichier.",
        }],
    }


class WorkflowTests(unittest.TestCase):
    def test_plan_is_parsed_and_validated(self):
        router = FakeRouter(json.dumps(valid_plan()))
        plan = VybelixWorkflow(config(), router, "demo").create_plan("Créer hello.txt")
        self.assertEqual(plan["tasks"][0]["id"], "task-1")
        self.assertEqual(router.calls[0][0], "planner")
        self.assertIn("affected_paths", router.calls[0][1][0]["content"])
        self.assertIn("verification_strategy", router.calls[0][1][0]["content"])
        self.assertIn("chaîne exacte 1.1", router.calls[0][1][0]["content"])

    def test_invalid_plan_is_not_accepted(self):
        router = FakeRouter('{"not":"a plan"}')
        with self.assertRaises(WorkflowError):
            VybelixWorkflow(config(), router, "demo").create_plan("Créer un fichier")

    def test_coder_receives_only_validated_relevant_context(self):
        proposal = {
            "schema_version": "1.0", "task_id": "task-1", "summary": "Mettre à jour hello.",
            "files": [{"path": "hello.txt", "operation": "write", "content": "au revoir"}],
            "notes": [], "verification_hints": [],
        }
        router = FakeRouter(json.dumps(proposal))
        task = {"id": "task-1", "title": "Modifier hello", "affected_paths": ["hello.txt"]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hello.txt").write_text("bonjour", encoding="utf-8")
            result = VybelixWorkflow(config(), router, "demo").create_code_proposal(task, root)
        self.assertEqual(result["task_id"], "task-1")
        payload = json.loads(router.calls[0][1][1]["content"])
        self.assertEqual(payload["context_files"], [{"path": "hello.txt", "content": "bonjour"}])
        self.assertIn("verification_hints", router.calls[0][1][0]["content"])
        self.assertIn("chaîne exacte 1.1", router.calls[0][1][0]["content"])

    def test_coder_cannot_receive_secret_or_outside_context(self):
        router = FakeRouter('{}')
        workflow = VybelixWorkflow(config(), router, "demo")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ExecutionError):
                workflow.create_code_proposal({"id": "task-1", "affected_paths": [".env"]}, Path(directory))
        self.assertEqual(router.calls, [])


if __name__ == "__main__":
    unittest.main()
