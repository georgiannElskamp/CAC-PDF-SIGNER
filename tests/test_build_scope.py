import unittest
from pathlib import Path

from build_scope import requires_build


class BuildScopeTests(unittest.TestCase):
    def test_runtime_and_dependency_changes_cannot_use_source_checks_alone(self):
        for path in ("signing.py", "requirements-lock.txt", "requirements-linux.txt",
                     "requirements-build.txt", "requirements-native-build.txt", ".python-version", "plugin/native-host.js", "native_linux/runtime.json",
                     "fonts/manifest.json", "licenses/manifest.json", "tools/build_linux.py"):
            with self.subTest(path=path):
                self.assertTrue(requires_build([path]))

    def test_documentation_and_test_only_updates_do_not_rebuild_workers(self):
        self.assertFalse(requires_build(["README.md", "docs/TESTING.md", "tests/test_automation.py", "requirements-dev.txt"]))

    def test_aiohttp_3_uses_supported_multidict_major(self):
        lock = Path(__file__).resolve().parents[1] / "requirements-lock.txt"
        requirements = dict(line.split("==", 1) for line in lock.read_text().splitlines()
                            if "==" in line)
        if requirements["aiohttp"].split(".", 1)[0] == "3":
            self.assertLess(int(requirements["multidict"].split(".", 1)[0]), 7)
