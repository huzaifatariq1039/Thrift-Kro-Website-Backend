import os
import unittest

from sqlalchemy import create_engine, text


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class SearchScalabilityPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_catalog_search_indexes_use_postgresql_trigrams(self):
        with self.engine.connect() as connection:
            extension = connection.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            ).scalar_one_or_none()
            rows = connection.execute(
                text(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'products'
                    """
                )
            ).all()

        definitions = {name: definition for name, definition in rows}
        self.assertEqual(extension, 1)
        for index_name in (
            "idx_products_name_trgm",
            "idx_products_description_trgm",
            "idx_products_brand_trgm",
        ):
            with self.subTest(index=index_name):
                self.assertIn(index_name, definitions)
                self.assertIn("USING gin", definitions[index_name])
                self.assertIn("gin_trgm_ops", definitions[index_name])


if __name__ == "__main__":
    unittest.main()
