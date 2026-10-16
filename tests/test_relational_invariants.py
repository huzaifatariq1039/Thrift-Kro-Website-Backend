import os
import unittest
from pathlib import Path

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.message import Message
from app.models.order import CheckoutOrder, OrderItem, OrderStatusHistory, SellerOrder
from app.models.product import ProductImage, ProductTag, ProductVariant
from app.models.review import Review
from app.models.shopping import CartItem, WishlistItem
from app.models.support import SupportTicket


def constraint_names(model, constraint_type):
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type)
    }


def index_names(model):
    return {index.name for index in model.__table__.indexes if isinstance(index, Index)}


class RelationalInvariantTests(unittest.TestCase):
    def test_duplicate_cart_and_wishlist_rows_are_database_invariants(self):
        self.assertIn(
            "uq_cart_items_session_variant",
            constraint_names(CartItem, UniqueConstraint),
        )
        self.assertIn(
            "uq_wishlist_items_user_product",
            constraint_names(WishlistItem, UniqueConstraint),
        )

    def test_quantity_and_stock_checks_are_mirrored_in_model_metadata(self):
        self.assertIn(
            "cart_items_quantity_check",
            constraint_names(CartItem, CheckConstraint),
        )
        self.assertIn(
            "product_variants_quantity_in_stock_check",
            constraint_names(ProductVariant, CheckConstraint),
        )
        self.assertIn(
            "order_items_quantity_check",
            constraint_names(OrderItem, CheckConstraint),
        )

    def test_only_one_primary_image_is_allowed_per_product(self):
        primary_index = next(
            index
            for index in ProductImage.__table__.indexes
            if index.name == "uq_product_images_primary_per_product"
        )
        self.assertTrue(primary_index.unique)
        self.assertIsNotNone(primary_index.dialect_options["postgresql"]["where"])

    def test_query_and_foreign_key_indexes_are_mirrored_in_models(self):
        expected = {
            CheckoutOrder: {"idx_checkout_orders_buyer_created"},
            SellerOrder: {
                "idx_seller_orders_checkout",
                "idx_seller_orders_seller",
                "idx_seller_orders_seller_created",
            },
            CartItem: {"idx_cart_items_session_added", "idx_cart_items_variant"},
            WishlistItem: {
                "idx_wishlist_items_user_added",
                "idx_wishlist_items_product",
            },
            ProductVariant: {"idx_product_variants_product_active"},
            ProductImage: {"idx_product_images_product_display"},
            ProductTag: {"idx_product_tags_product"},
            OrderItem: {"idx_order_items_seller_order", "idx_order_items_variant"},
            OrderStatusHistory: {"idx_order_status_history_seller_created"},
            Review: {"idx_reviews_product_created"},
            Message: {"idx_messages_conversation", "idx_messages_seller_order"},
            SupportTicket: {
                "idx_support_tickets_user_created",
                "idx_support_tickets_seller_order",
            },
        }

        for model, names in expected.items():
            with self.subTest(model=model.__name__):
                self.assertTrue(names.issubset(index_names(model)))

    def test_migration_preflights_conflicting_legacy_rows(self):
        source = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "20261016_12_relational_invariants.py"
        ).read_text(encoding="utf-8")

        self.assertIn("_assert_no_duplicates", source)
        self.assertIn("_assert_no_rows", source)
        self.assertLess(
            source.index("_assert_no_duplicates"),
            source.index("_ensure_unique_constraint"),
        )


if __name__ == "__main__":
    unittest.main()
