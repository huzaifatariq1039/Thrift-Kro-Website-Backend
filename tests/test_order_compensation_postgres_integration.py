import os
import threading
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import create_order_from_cart, update_order_status
from app.models.order import CheckoutOrder, OrderStatusEnum, PaymentMethodEnum
from app.models.product import ConditionEnum, Product, ProductStatusEnum, ProductVariant
from app.models.shopping import CartItem, CartSession
from app.models.user import (
    RoleEnum,
    Transaction,
    TransactionTypeEnum,
    User,
    Wallet,
)
from app.services.ledger import initialize_wallet_ledger


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class OrderCompensationPostgresIntegrationTests(unittest.TestCase):
    """Exercise refund locks; never point this test at application data."""

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
            buyer = User(
                email=f"refund-buyer-{marker}@example.test",
                full_name="Refund Buyer",
                hex_code=f"refund-buyer-{marker}",
                role=RoleEnum.BUYER,
            )
            seller = User(
                email=f"refund-seller-{marker}@example.test",
                full_name="Refund Seller",
                hex_code=f"refund-seller-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add_all([buyer, seller])
            db.flush()
            buyer_wallet = Wallet(user_id=buyer.id, balance=5000.0)
            product = Product(
                seller_id=seller.id,
                name=f"Refundable item {marker}",
                condition=ConditionEnum.GOOD,
                price=1000.0,
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add_all([buyer_wallet, product])
            db.flush()
            initialize_wallet_ledger(db, buyer_wallet)
            variant = ProductVariant(
                product_id=product.id,
                sku=f"refundable-{marker}",
                attributes={},
                quantity_in_stock=1,
            )
            cart = CartSession(user_id=buyer.id)
            db.add_all([variant, cart])
            db.flush()
            db.add(CartItem(
                cart_session_id=cart.id,
                product_variant_id=variant.id,
                quantity=1,
            ))
            db.commit()
            self.buyer_id = buyer.id
            self.seller_id = seller.id
            self.buyer_wallet_id = buyer_wallet.id
            self.variant_id = variant.id

        with self.Session() as db:
            checkout = create_order_from_cart(
                db=db,
                buyer_id=self.buyer_id,
                shipping_address_id=None,
                payment_method=PaymentMethodEnum.WALLET,
                idempotency_key=f"refund-checkout-{marker}",
            )
            self.assertIsInstance(checkout, CheckoutOrder)
            self.seller_order_id = checkout.seller_orders[0].id
            self.refund_amount = checkout.seller_orders[0].total_amount

    def test_concurrent_refund_restores_money_and_stock_once(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def refund():
            try:
                with self.Session() as db:
                    barrier.wait(timeout=10)
                    results.append(update_order_status(
                        db=db,
                        seller_order_id=self.seller_order_id,
                        new_status=OrderStatusEnum.REFUNDED,
                        actor_id=self.buyer_id,
                        notes="Integration refund",
                    ))
            except Exception as exc:  # pragma: no cover - reported by assertion
                errors.append(exc)

        threads = [threading.Thread(target=refund, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(any(thread.is_alive() for thread in threads), "refund deadlocked")
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.status == OrderStatusEnum.REFUNDED for result in results))

        with self.Session() as db:
            wallet = db.get(Wallet, self.buyer_wallet_id)
            variant = db.get(ProductVariant, self.variant_id)
            refunds = (
                db.query(Transaction)
                .filter(
                    Transaction.reference_type == "seller_order",
                    Transaction.reference_id == self.seller_order_id,
                    Transaction.type == TransactionTypeEnum.REFUND,
                )
                .all()
            )
            self.assertEqual(wallet.balance, 5000.0)
            self.assertEqual(variant.quantity_in_stock, 1)
            self.assertEqual(len(refunds), 1)
            self.assertEqual(refunds[0].amount, self.refund_amount)

    def test_cod_cancellation_restores_stock_without_wallet_credit(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            product = Product(
                seller_id=self.seller_id,
                name=f"Cancelled COD item {marker}",
                condition=ConditionEnum.GOOD,
                price=800.0,
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add(product)
            db.flush()
            variant = ProductVariant(
                product_id=product.id,
                sku=f"cancelled-cod-{marker}",
                attributes={},
                quantity_in_stock=1,
            )
            db.add(variant)
            db.flush()
            cart = db.query(CartSession).filter(CartSession.user_id == self.buyer_id).one()
            db.add(CartItem(
                cart_session_id=cart.id,
                product_variant_id=variant.id,
                quantity=1,
            ))
            db.commit()
            variant_id = variant.id

        with self.Session() as db:
            checkout = create_order_from_cart(
                db=db,
                buyer_id=self.buyer_id,
                shipping_address_id=None,
                payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
                idempotency_key=f"cancel-cod-{marker}",
            )
            self.assertIsInstance(checkout, CheckoutOrder)
            seller_order_id = checkout.seller_orders[0].id

        with self.Session() as db:
            cancelled = update_order_status(
                db=db,
                seller_order_id=seller_order_id,
                new_status=OrderStatusEnum.CANCELLED,
                actor_id=self.buyer_id,
                notes="Integration cancellation",
            )
            self.assertEqual(cancelled.status, OrderStatusEnum.CANCELLED)

        with self.Session() as db:
            wallet = db.get(Wallet, self.buyer_wallet_id)
            variant = db.get(ProductVariant, variant_id)
            refund_count = (
                db.query(Transaction)
                .filter(
                    Transaction.reference_type == "seller_order",
                    Transaction.reference_id == seller_order_id,
                    Transaction.type == TransactionTypeEnum.REFUND,
                )
                .count()
            )
            self.assertEqual(wallet.balance, Decimal("5000.00") - self.refund_amount)
            self.assertEqual(variant.quantity_in_stock, 1)
            self.assertEqual(refund_count, 0)


if __name__ == "__main__":
    unittest.main()
