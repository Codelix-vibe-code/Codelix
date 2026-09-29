import unittest

from codelix.contracts import ContractError, validate_coder_output, validate_planner_output


def task(task_id, dependencies=None, parent_id=None):
    return {
        "id": task_id,
        "parent_id": parent_id,
        "title": f"Tâche {task_id}",
        "description": "Description de la tâche",
        "type": "code",
        "role": "coder",
        "priority": 3,
        "dependencies": dependencies or [],
        "acceptance_criteria": ["Un résultat observable est fourni"],
        "verification_strategy": "Exécuter les tests ciblés après approbation",
    }


def plan(tasks=None):
    return {
        "schema_version": "1.0",
        "project_id": "codelix",
        "request_summary": "Ajouter une fonctionnalité",
        "affected_paths": ["src/codelix/contracts.py"],
        "tasks": tasks or [task("implement")],
    }


class PlannerContractTests(unittest.TestCase):
    def test_accepts_valid_plan(self):
        self.assertEqual(validate_planner_output(plan(), expected_project_id="codelix")["project_id"], "codelix")

    def test_rejects_project_mismatch(self):
        with self.assertRaises(ContractError):
            validate_planner_output(plan(), expected_project_id="other")

    def test_rejects_duplicate_ids(self):
        with self.assertRaises(ContractError):
            validate_planner_output(plan([task("same"), task("same")]))

    def test_rejects_unknown_dependency(self):
        with self.assertRaises(ContractError):
            validate_planner_output(plan([task("one", ["missing"])]))

    def test_rejects_dependency_cycle(self):
        with self.assertRaises(ContractError):
            validate_planner_output(plan([task("one", ["two"]), task("two", ["one"])]))

    def test_rejects_hierarchy_cycle(self):
        with self.assertRaises(ContractError):
            validate_planner_output(plan([task("one", parent_id="two"), task("two", parent_id="one")]))

    def test_rejects_unsafe_affected_path(self):
        value = plan()
        value["affected_paths"] = ["../outside.py"]
        with self.assertRaises(ContractError):
            validate_planner_output(value)


class CoderContractTests(unittest.TestCase):
    def valid_output(self):
        return {
            "schema_version": "1.0",
            "task_id": "task-1",
            "summary": "Écrire un fichier",
            "files": [{"path": "src/codelix/new.py", "operation": "write", "content": "# code\n"}],
            "notes": [],
            "verification_hints": ["Vérifier la syntaxe"],
        }

    def test_accepts_valid_proposal(self):
        self.assertEqual(validate_coder_output(self.valid_output(), expected_task_id="task-1")["task_id"], "task-1")

    def test_rejects_wrong_task_id(self):
        with self.assertRaises(ContractError):
            validate_coder_output(self.valid_output(), expected_task_id="task-2")

    def test_rejects_absolute_and_parent_paths(self):
        for unsafe in ("C:/outside.py", "/outside.py", "../outside.py", "src/../outside.py", "src\\outside.py"):
            with self.subTest(path=unsafe):
                value = self.valid_output()
                value["files"][0]["path"] = unsafe
                with self.assertRaises(ContractError):
                    validate_coder_output(value, expected_task_id="task-1")

    def test_rejects_non_write_operation(self):
        value = self.valid_output()
        value["files"][0]["operation"] = "delete"
        with self.assertRaises(ContractError):
            validate_coder_output(value, expected_task_id="task-1")

    def test_rejects_duplicate_paths(self):
        value = self.valid_output()
        value["files"].append(dict(value["files"][0]))
        with self.assertRaises(ContractError):
            validate_coder_output(value, expected_task_id="task-1")


if __name__ == "__main__":
    unittest.main()
