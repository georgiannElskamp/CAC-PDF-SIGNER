import unittest

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
