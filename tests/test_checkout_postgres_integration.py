import os
import threading
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import create_order_from_cart
from app.models.order import CheckoutOrder, PaymentMethodEnum
from app.models.product import ConditionEnum, Product, ProductStatusEnum, ProductVariant
from app.models.shopping import CartItem, CartSession
from app.models.user import RoleEnum, User


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class CheckoutPostgresIntegrationTests(unittest.TestCase):
    """Exercise PostgreSQL row locks; never point this test at application data."""

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
                email=f"seller-{marker}@example.test",
                full_name="Concurrency Seller",
                hex_code=f"seller-{marker}",
                role=RoleEnum.SELLER,
            )
            buyers = [
                User(
                    email=f"buyer-{index}-{marker}@example.test",
                    full_name=f"Concurrency Buyer {index}",
                    hex_code=f"buyer-{index}-{marker}",
                    role=RoleEnum.BUYER,
                )
                for index in range(2)
            ]
            db.add_all([seller, *buyers])
            db.flush()

            product = Product(
                seller_id=seller.id,
                name=f"Single stock item {marker}",
                condition=ConditionEnum.GOOD,
                price=1000.0,
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add(product)
            db.flush()
            variant = ProductVariant(
                product_id=product.id,
                sku=f"single-stock-{marker}",
                attributes={},
                quantity_in_stock=1,
            )
            db.add(variant)
            db.flush()

            for buyer in buyers:
                cart = CartSession(user_id=buyer.id)
                db.add(cart)
                db.flush()
                db.add(
                    CartItem(
                        cart_session_id=cart.id,
                        product_variant_id=variant.id,
                        quantity=1,
                    )
                )

            db.commit()
            self.buyer_ids = [buyer.id for buyer in buyers]
            self.variant_id = variant.id

    def test_two_buyers_cannot_purchase_the_last_unit(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def checkout(buyer_id, index):
            try:
                with self.Session() as db:
                    barrier.wait(timeout=10)
                    result = create_order_from_cart(
                        db=db,
                        buyer_id=buyer_id,
                        shipping_address_id=None,
                        payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
                        idempotency_key=f"concurrency-{index}-{uuid.uuid4().hex}",
                    )
                    results.append(result)
            except Exception as exc:  # pragma: no cover - reported by assertion
                errors.append(exc)

        threads = [
            threading.Thread(target=checkout, args=(buyer_id, index), daemon=True)
            for index, buyer_id in enumerate(self.buyer_ids)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(any(thread.is_alive() for thread in threads), "checkout deadlocked")
        self.assertEqual(errors, [])
        self.assertEqual(sum(isinstance(result, CheckoutOrder) for result in results), 1)
        self.assertEqual(
            sum(isinstance(result, str) and "Insufficient stock" in result for result in results),
            1,
        )

        with self.Session() as db:
            variant = db.get(ProductVariant, self.variant_id)
            self.assertEqual(variant.quantity_in_stock, 0)
            self.assertEqual(
                db.query(CheckoutOrder)
                .filter(CheckoutOrder.buyer_id.in_(self.buyer_ids))
                .count(),
                1,
            )

    def test_retry_after_cart_clear_returns_the_original_order(self):
        key = f"retry-{uuid.uuid4().hex}"
        with self.Session() as db:
            first = create_order_from_cart(
                db=db,
                buyer_id=self.buyer_ids[0],
                shipping_address_id=None,
                payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
                idempotency_key=key,
            )
        with self.Session() as db:
            retry = create_order_from_cart(
                db=db,
                buyer_id=self.buyer_ids[0],
                shipping_address_id=None,
                payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
                idempotency_key=key,
            )

        self.assertIsInstance(first, CheckoutOrder)
        self.assertIsInstance(retry, CheckoutOrder)
        self.assertEqual(first.id, retry.id)
        with self.Session() as db:
            self.assertEqual(
                db.query(CheckoutOrder)
                .filter(
                    CheckoutOrder.buyer_id == self.buyer_ids[0],
                    CheckoutOrder.idempotency_key == key,
                )
                .count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
