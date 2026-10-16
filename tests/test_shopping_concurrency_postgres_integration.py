import os
import threading
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.shopping import add_to_cart, toggle_wishlist
from app.models.product import ConditionEnum, Product, ProductStatusEnum, ProductVariant
from app.models.shopping import CartItem, CartSession, WishlistItem
from app.models.user import RoleEnum, User


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class ShoppingConcurrencyPostgresIntegrationTests(unittest.TestCase):
    """Exercise row locks and upserts; never point this test at application data."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            seller = User(
                email=f"cart-seller-{marker}@example.test",
                full_name="Cart Seller",
                hex_code=f"cart-seller-{marker}",
                role=RoleEnum.SELLER,
            )
            buyer = User(
                email=f"cart-buyer-{marker}@example.test",
                full_name="Cart Buyer",
                hex_code=f"cart-buyer-{marker}",
                role=RoleEnum.BUYER,
            )
            db.add_all([seller, buyer])
            db.flush()

            product = Product(
                seller_id=seller.id,
                name=f"Concurrent cart item {marker}",
                condition=ConditionEnum.GOOD,
                price=1000.0,
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add(product)
            db.flush()
            variant = ProductVariant(
                product_id=product.id,
                sku=f"concurrent-cart-{marker}",
                attributes={},
                quantity_in_stock=10,
            )
            db.add(variant)
            db.commit()

            self.buyer_id = buyer.id
            self.product_id = product.id
            self.variant_id = variant.id

    def _run_two(self, operation):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def invoke():
            try:
                with self.Session() as db:
                    barrier.wait(timeout=10)
                    results.append(operation(db))
            except Exception as exc:  # pragma: no cover - reported by assertion
                errors.append(exc)

        threads = [threading.Thread(target=invoke, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(any(thread.is_alive() for thread in threads), "operation deadlocked")
        self.assertEqual(errors, [])
        return results

    def test_concurrent_adds_create_one_session_and_increment_one_line(self):
        def add(db):
            item, error = add_to_cart(db, self.buyer_id, self.variant_id, 1)
            return item.id if item else None, error

        results = self._run_two(add)

        self.assertTrue(all(error is None for _, error in results))
        self.assertEqual(len({item_id for item_id, _ in results}), 1)
        with self.Session() as db:
            sessions = db.query(CartSession).filter(CartSession.user_id == self.buyer_id).all()
            self.assertEqual(len(sessions), 1)
            lines = db.query(CartItem).filter(CartItem.cart_session_id == sessions[0].id).all()
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].quantity, 2)

    def test_concurrent_wishlist_toggles_are_serialized(self):
        results = self._run_two(
            lambda db: toggle_wishlist(db, self.buyer_id, self.product_id)[0]
        )

        self.assertEqual(sorted(results), [False, True])
        with self.Session() as db:
            self.assertEqual(
                db.query(WishlistItem)
                .filter(
                    WishlistItem.user_id == self.buyer_id,
                    WishlistItem.product_id == self.product_id,
                )
                .count(),
                0,
            )


if __name__ == "__main__":
    unittest.main()
