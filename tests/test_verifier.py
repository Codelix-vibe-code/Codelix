import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vybelix.verifier import VerificationError, Verifier, correction_limit


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_runs_only_exact_allowlisted_command_without_shell(self):
        command = 'python -c "print(\'verification OK\')"'
        verifier = Verifier(self.root, [command])
        result = verifier.run(command, acceptance_criteria=["sortie attendue"])
        self.assertTrue(result.passed)
        self.assertEqual(result.acceptance_criteria, ("sortie attendue",))
        self.assertEqual(result.summary, "verification OK")
        with self.assertRaises(VerificationError):
            verifier.run(command + " & whoami")

    def test_failed_result_records_real_exit_and_errors(self):
        command = 'python -c "import sys; print(\'concrete failure\', file=sys.stderr); sys.exit(3)"'
        result = Verifier(self.root, [command]).run(command)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)
        self.assertIn("concrete failure", result.errors[0])

    def test_redacts_environment_secrets(self):
        command = 'python -c "import os; print(os.getenv(\'CODELIX_SECRET_TEST\'))"'
        with patch.dict(os.environ, {"CODELIX_SECRET_TEST": "private-value-9876"}):
            result = Verifier(self.root, [command]).run(command)
        self.assertNotIn("private-value-9876", result.summary)
        self.assertNotIn("private-value-9876", "\n".join(result.errors))

    def test_rejects_nonexistent_executable_clearly(self):
        command = "program-that-does-not-exist-codelix"
        with self.assertRaises(VerificationError):
            Verifier(self.root, [command]).run(command)

    def test_correction_limit_never_exceeds_configured_two(self):
        self.assertEqual(correction_limit(0), 2)
        self.assertEqual(correction_limit(1), 1)
        self.assertEqual(correction_limit(2), 0)
        with self.assertRaises(ValueError):
            correction_limit(0, 3)


if __name__ == "__main__":
    unittest.main()
