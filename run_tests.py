"""Run tests with temporary application state."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

if __name__ == "__main__":
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="cac-plugin-tests-") as directory:
        os.environ["CAC_SIGNATURE_HOME"] = directory
        root = Path(__file__).resolve().parent
        suite = unittest.defaultTestLoader.discover(
            str(root / "tests"), pattern="test_*.py"
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
