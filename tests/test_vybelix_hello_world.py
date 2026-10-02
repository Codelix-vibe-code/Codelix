import unittest
import subprocess

class TestHelloWorld(unittest.TestCase):
    def test_output(self):
        result = subprocess.run(['python', 'vybelix_hello_world.py'], capture_output=True, text=True)
        self.assertEqual(result.stdout, 'Hello, world!\n', f"stdout mismatch: expected 'Hello, world!\\n' but got {result.stdout!r}")

if __name__ == '__main__':
    unittest.main()
