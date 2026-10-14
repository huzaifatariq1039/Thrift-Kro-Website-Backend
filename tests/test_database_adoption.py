import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from scripts.adopt_existing_database import EXPECTED_COLUMNS, compare_schema


class DatabaseAdoptionTests(unittest.TestCase):
    def test_exact_normalized_schema_is_compatible(self):
        columns = {table: set(names) for table, names in EXPECTED_COLUMNS.items()}
        report = compare_schema(set(columns), columns)
        self.assertTrue(report.compatible)
        self.assertEqual(report.repairs, [])

    def test_existing_pgadmin_schema_allows_only_known_title_repair(self):
        columns = {table: set(names) for table, names in EXPECTED_COLUMNS.items()}
        columns["notifications"].remove("title")
        report = compare_schema(set(columns), columns)
        self.assertTrue(report.compatible)
        self.assertEqual(report.repairs, ["add and backfill notifications.title"])

    def test_unknown_column_drift_blocks_adoption(self):
        columns = {table: set(names) for table, names in EXPECTED_COLUMNS.items()}
        columns["products"].add("legacy_price")
        report = compare_schema(set(columns), columns)
        self.assertFalse(report.compatible)
        self.assertIn("products unexpected columns: legacy_price", report.errors)

    def test_missing_table_blocks_adoption(self):
        columns = {table: set(names) for table, names in EXPECTED_COLUMNS.items()}
        del columns["transactions"]
        report = compare_schema(set(columns), columns)
        self.assertFalse(report.compatible)
        self.assertIn("missing tables: transactions", report.errors)


if __name__ == "__main__":
    unittest.main()
