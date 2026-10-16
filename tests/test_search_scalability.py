import os
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.product import Product


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SearchScalabilityTests(unittest.TestCase):
    def test_every_leading_wildcard_product_field_has_a_trigram_index(self):
        indexes = {index.name: index for index in Product.__table__.indexes}

        expected = {
            "idx_products_name_trgm": "name",
            "idx_products_description_trgm": "description",
            "idx_products_brand_trgm": "brand",
        }
        for index_name, column_name in expected.items():
            with self.subTest(index=index_name):
                index = indexes[index_name]
                self.assertEqual(index.dialect_options["postgresql"]["using"], "gin")
                self.assertEqual(
                    index.dialect_options["postgresql"]["ops"],
                    {column_name: "gin_trgm_ops"},
                )

    def test_migration_is_additive_for_existing_pgadmin_databases(self):
        migration = (
            PROJECT_ROOT
            / "alembic"
            / "versions"
            / "20261016_14_search_scalability.py"
        ).read_text(encoding="utf-8")

        self.assertIn('down_revision: Union[str, Sequence[str], None] = "20261016_13"', migration)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS pg_trgm", migration)
        self.assertIn("if NAME_INDEX not in indexes", migration)
        self.assertIn("if DESCRIPTION_INDEX not in indexes", migration)
        self.assertIn("if BRAND_INDEX not in indexes", migration)


if __name__ == "__main__":
    unittest.main()
