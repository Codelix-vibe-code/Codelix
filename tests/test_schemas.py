import json
import re
import unittest
from pathlib import Path


SCHEMA_DIRECTORY = Path(__file__).resolve().parents[1] / "schemas"


class JsonSchemaDefinitionTests(unittest.TestCase):
    def test_all_schema_files_are_valid_json(self):
        schema_files = sorted(SCHEMA_DIRECTORY.glob("*.schema.json"))
        self.assertGreaterEqual(len(schema_files), 3)
        for path in schema_files:
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["type"], "object")

    def test_contract_path_patterns_compile_and_reject_unsafe_paths(self):
        for filename in ("planner-v1.schema.json", "coder-v1.schema.json"):
            with self.subTest(schema=filename):
                schema = json.loads((SCHEMA_DIRECTORY / filename).read_text(encoding="utf-8"))
                path_definition = schema["$defs"].get("path")
                if path_definition is None:
                    path_definition = schema["$defs"]["file"]["properties"]["path"]
                pattern = re.compile(path_definition["pattern"])
                self.assertIsNotNone(pattern.search("src/vybelix/module.py"))
                for unsafe in ("../secret", "/outside.py", "C:/outside.py", "src\\outside.py"):
                    with self.subTest(path=unsafe):
                        self.assertIsNone(pattern.search(unsafe))


if __name__ == "__main__":
    unittest.main()
