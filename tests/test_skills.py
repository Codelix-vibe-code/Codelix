import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from vybelix.skills import SkillError, SkillManager
from vybelix.skills.manager import _satisfies
from vybelix.ui_actions import UIActions


class SkillManagerExtendedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.manager=SkillManager(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def package(self, version="1.0.0", *, dependencies=None, config=False):
        path=self.root/f"source-{version}-{uuid.uuid4().hex[:8]}"
        path.mkdir()
        manifest={"schema_version":"1.0","id":"sample-skill","name":"Sample","version":version,
                  "description":"Test skill","author":"Test","license":"MIT","capabilities":[],
                  "permissions":[],"dependencies":dependencies or []}
        if config:
            manifest["config_schema"]="config.schema.json"
            (path/"config.schema.json").write_text(json.dumps({"type":"object","additionalProperties":False,
                "required":["endpoint"],"properties":{"endpoint":{"type":"string","required":True},
                "token":{"type":"secret","required":False}}}),encoding="utf-8")
        (path/"skill.json").write_text(json.dumps(manifest),encoding="utf-8")
        (path/"capabilities.json").write_text(json.dumps({"schema_version":"1.0","capabilities":[]}),encoding="utf-8")
        (path/"SKILL.md").write_text("# Sample\n\nReference instructions.",encoding="utf-8")
        return path

    def install(self, package):
        return self.manager.install_local(package,approved=True)

    def test_semver_constraints_are_checked_without_installing(self):
        self.assertTrue(_satisfies("2.3.1",">=2.0,<3"))
        self.assertTrue(_satisfies("2.3.1","~=2.3"))
        self.assertFalse(_satisfies("3.0.0",">=2,<3"))

    def test_dependency_detection_reports_missing_package(self):
        package=self.package(dependencies=[{"name":"vybelix-package-that-does-not-exist-98765","version":">=1"}])
        validation=self.manager.validate(package)
        self.assertTrue(validation.valid)
        self.assertIn("DEPENDENCIES_MISSING",{item["code"] for item in validation.warnings})
        self.install(package)
        status=self.manager.dependency_status("sample-skill")
        self.assertEqual(status[0]["status"],"missing")
        self.assertFalse(self.manager.test("sample-skill")["passed"])

    def test_update_requires_approval_and_newer_version_then_disables(self):
        self.install(self.package("1.0.0"))
        with self.assertRaises(SkillError):self.manager.update_local(self.package("1.1.0"))
        updated=self.manager.update_local(self.package("1.1.0"),approved=True)
        self.assertEqual(updated["version"],"1.1.0")
        self.assertEqual(updated["status"],"disabled")
        self.assertEqual(self.manager.list_installed()[0]["version"],"1.1.0")
        with self.assertRaises(SkillError):self.manager.update_local(self.package("1.0.1"),approved=True)

    def test_enabled_skill_context_is_marked_untrusted_and_exec_stays_closed(self):
        self.install(self.package())
        with self.assertRaises(SkillError):self.manager.agent_context("planner",["sample-skill"])
        self.manager.enable("sample-skill",approved_permissions=set())
        context=self.manager.agent_context("planner",["sample-skill"])
        self.assertEqual(context[0]["trust"],"UNTRUSTED_SKILL_DATA")
        self.assertIn("Reference instructions",context[0]["content"])
        with self.assertRaisesRegex(SkillError,"sandbox"):
            self.manager.execute("sample-skill","anything",{})

    def test_config_validates_and_encrypts_secret_separately(self):
        self.install(self.package(config=True))
        with self.assertRaises(SkillError):self.manager.configure("sample-skill",{"endpoint":"https://example.test","extra":"no"})
        with patch("vybelix.skills.secure_store.protect",return_value=b"encrypted-test-blob"):
            result=self.manager.configure("sample-skill",{"endpoint":"https://example.test","token":"do-not-leak-this"})
        config_root=self.manager.home/"config"/"sample-skill"
        plain=(config_root/"1.0.0.json").read_text(encoding="utf-8")
        encrypted=(config_root/"1.0.0.secrets.dpapi").read_bytes()
        self.assertNotIn("do-not-leak-this",plain)
        self.assertNotIn(b"do-not-leak-this",encrypted)
        self.assertEqual(result["secret_fields"],["token"])
        self.assertNotIn("do-not-leak-this",json.dumps(self.manager.configuration_status("sample-skill")))

    def test_tests_report_execution_not_run_and_static_pass(self):
        self.install(self.package())
        report=self.manager.test("sample-skill")
        self.assertTrue(report["passed"])
        self.assertEqual(report["execution_tests"],"not_run_sandbox_unavailable")

    def test_ui_exposes_local_context_and_static_actions(self):
        actions=UIActions(self.root)
        source=self.root/"skills"/"sample-skill"
        source.parent.mkdir()
        draft=self.package()
        self.install(draft)
        self.manager.enable("sample-skill",approved_permissions=set())
        catalog=actions.skills_catalog()
        self.assertFalse(catalog["execution_enabled"])
        self.assertFalse(catalog["sandbox"]["available"])
        context=actions.skill_agent_context(["sample-skill"],"tester")
        self.assertEqual(context["skills"][0]["trust"],"UNTRUSTED_SKILL_DATA")
        self.assertTrue(actions.test_skill("sample-skill")["passed"])

    def test_catalog_detects_newer_local_version_and_static_test_reports_tampering(self):
        installed=self.install(self.package("1.0.0"))
        source=self.package("1.1.0")
        skills_root=self.root/"skills"; skills_root.mkdir()
        candidate=skills_root/"sample-skill"; candidate.mkdir()
        import shutil
        shutil.copytree(source,candidate,dirs_exist_ok=True)
        catalog=UIActions(self.root).skills_catalog()
        self.assertEqual(len(catalog["candidates"]),1)
        self.assertTrue(catalog["candidates"][0]["update_available"])
        installed_path=self.manager.installed/"sample-skill"/installed["version"]
        (installed_path/"SKILL.md").write_text("tampered",encoding="utf-8")
        report=self.manager.test("sample-skill")
        self.assertFalse(report["passed"])
        self.assertFalse(next(item for item in report["checks"] if item["id"]=="integrity")["ok"])


if __name__=="__main__":
    unittest.main()
