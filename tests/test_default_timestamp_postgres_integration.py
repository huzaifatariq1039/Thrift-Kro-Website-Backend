import os
import unittest

from sqlalchemy import create_engine, inspect


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class DefaultAndTimestampPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.inspector = inspect(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_updated_at_columns_are_non_null_with_database_defaults(self):
        tables = (
            "cart_sessions",
            "categories",
            "checkout_orders",
            "order_payments",
            "product_variants",
            "products",
            "reviews",
            "seller_orders",
            "seller_profiles",
            "seller_verification_requests",
            "support_tickets",
            "user_addresses",
            "users",
            "wallets",
        )

        for table_name in tables:
            with self.subTest(table=table_name):
                columns = {
                    column["name"]: column
                    for column in self.inspector.get_columns(table_name)
                }
                updated_at = columns["updated_at"]
                self.assertFalse(updated_at["nullable"])
                self.assertRegex(
                    updated_at["default"].upper(),
                    r"(CURRENT_TIMESTAMP|NOW\(\))",
                )

    def test_verification_json_lists_are_non_null_with_defaults(self):
        columns = {
            column["name"]: column
            for column in self.inspector.get_columns("seller_verification_requests")
        }

        for column_name in ("shop_photo_urls", "products_proof"):
            with self.subTest(column=column_name):
                column = columns[column_name]
                self.assertFalse(column["nullable"])
                self.assertIn("[]", column["default"])


if __name__ == "__main__":
    unittest.main()
