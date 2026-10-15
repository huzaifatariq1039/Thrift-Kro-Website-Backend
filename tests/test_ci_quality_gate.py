import unittest
from pathlib import Path

from scripts.run_postgres_tests import _validate_temporary_database_name


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "backend-tests.yml"
)


class CIQualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci_builds_the_database_from_migrations(self):
        self.assertIn("image: postgres:16-alpine", self.workflow)
        self.assertIn("python -m scripts.migrate", self.workflow)

    def test_ci_enables_postgres_integration_tests(self):
        self.assertIn("TEST_DATABASE_URL:", self.workflow)
        self.assertIn(
            'python -m unittest discover -s tests -p "test_*.py" -v',
            self.workflow,
        )

    def test_ci_cannot_silently_ignore_test_failures(self):
        self.assertNotIn("continue-on-error", self.workflow)

    def test_local_runner_only_manages_generated_test_databases(self):
        _validate_temporary_database_name("thriftkro_test_" + "a" * 32)
        for unsafe_name in ("postgres", "thriftkro", "thriftkro_test_manual"):
            with self.subTest(unsafe_name=unsafe_name):
                with self.assertRaises(ValueError):
                    _validate_temporary_database_name(unsafe_name)


if __name__ == "__main__":
    unittest.main()
