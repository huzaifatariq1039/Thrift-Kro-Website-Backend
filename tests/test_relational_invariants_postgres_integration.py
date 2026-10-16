import os
import unittest

from sqlalchemy import create_engine, inspect


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class RelationalInvariantPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.inspector = inspect(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_required_unique_rules_and_checks_exist(self):
        cart_unique_columns = {
            tuple(constraint["column_names"])
            for constraint in self.inspector.get_unique_constraints("cart_items")
        }
        wishlist_unique_columns = {
            tuple(constraint["column_names"])
            for constraint in self.inspector.get_unique_constraints("wishlist_items")
        }
        check_names = {
            table: {
                constraint["name"]
                for constraint in self.inspector.get_check_constraints(table)
            }
            for table in ("cart_items", "product_variants", "order_items", "reviews")
        }

        self.assertIn(("cart_session_id", "product_variant_id"), cart_unique_columns)
        self.assertIn(("user_id", "product_id"), wishlist_unique_columns)
        self.assertIn("cart_items_quantity_check", check_names["cart_items"])
        self.assertIn(
            "product_variants_quantity_in_stock_check",
            check_names["product_variants"],
        )
        self.assertIn("order_items_quantity_check", check_names["order_items"])
        self.assertIn("reviews_rating_check", check_names["reviews"])

    def test_required_indexes_exist_in_migrated_postgres(self):
        expected = {
            "checkout_orders": {"idx_checkout_orders_buyer_created"},
            "seller_orders": {"idx_seller_orders_seller_created"},
            "cart_items": {"idx_cart_items_session_added", "idx_cart_items_variant"},
            "wishlist_items": {
                "idx_wishlist_items_user_added",
                "idx_wishlist_items_product",
            },
            "product_images": {
                "uq_product_images_primary_per_product",
                "idx_product_images_product_display",
            },
            "product_tags": {"idx_product_tags_product"},
            "order_items": {"idx_order_items_seller_order", "idx_order_items_variant"},
            "order_status_history": {"idx_order_status_history_seller_created"},
            "reviews": {"idx_reviews_product_created"},
            "messages": {"idx_messages_seller_order"},
            "support_tickets": {
                "idx_support_tickets_user_created",
                "idx_support_tickets_seller_order",
            },
        }

        for table, names in expected.items():
            with self.subTest(table=table):
                actual = {index["name"] for index in self.inspector.get_indexes(table)}
                self.assertTrue(names.issubset(actual))

        primary = next(
            index
            for index in self.inspector.get_indexes("product_images")
            if index["name"] == "uq_product_images_primary_per_product"
        )
        self.assertTrue(primary["unique"])
        self.assertIn(
            "is_primary",
            str(primary["dialect_options"]["postgresql_where"]),
        )


if __name__ == "__main__":
    unittest.main()
