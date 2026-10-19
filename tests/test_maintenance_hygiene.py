import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MaintenanceHygieneTests(unittest.TestCase):
    def test_database_commands_are_not_root_level_python_scripts(self):
        root_python_files = sorted(path.name for path in PROJECT_ROOT.glob("*.py"))

        self.assertEqual(
            root_python_files,
            [],
            "Root-level Python scripts are unsupported; use Alembic or a reviewed "
            "module under scripts/.",
        )

    def test_runbook_names_alembic_as_the_only_schema_authority(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Alembic as the only schema authority", readme)
        self.assertIn("Do not run `Base.metadata.create_all()`", readme)
        self.assertIn("raw schema", readme)


if __name__ == "__main__":
    unittest.main()
