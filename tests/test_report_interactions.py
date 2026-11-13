"""Optional Node.js interaction checks; report generation still only needs Python."""
from pathlib import Path
import shutil
import subprocess
import unittest


class FoldInteractionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for JavaScript interaction tests")
    def test_source_folds_open_and_close(self):
        result = subprocess.run(
            [shutil.which("node"), str(Path(__file__).with_name("fold_interactions.cjs"))],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
