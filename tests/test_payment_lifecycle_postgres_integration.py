import os
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import create_order_from_cart, release_escrow, update_order_status
from app.models.order import (
    CheckoutOrder,
    OrderPayment,
    OrderStatusEnum,
    PaymentMethodEnum,
    PaymentStatusEnum,
)
from app.models.product import ConditionEnum, Product, ProductStatusEnum, ProductVariant
from app.models.shopping import CartItem, CartSession
from app.models.user import RoleEnum, Transaction, User


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class PaymentLifecyclePostgresIntegrationTests(unittest.TestCase):
    """Exercise supported payment paths; never point this test at application data."""

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
                email=f"payment-buyer-{marker}@example.test",
                full_name="Payment Buyer",
                hex_code=f"payment-buyer-{marker}",
                role=RoleEnum.BUYER,
            )
            seller = User(
                email=f"payment-seller-{marker}@example.test",
                full_name="Payment Seller",
                hex_code=f"payment-seller-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add_all([buyer, seller])
            db.flush()
            product = Product(
                seller_id=seller.id,
                name=f"COD item {marker}",
                condition=ConditionEnum.GOOD,
                price=1000.0,
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add(product)
            db.flush()
            variant = ProductVariant(
                product_id=product.id,
                sku=f"cod-{marker}",
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
            self.variant_id = variant.id
            self.cart_id = cart.id
            self.marker = marker

    def test_card_checkout_is_rejected_without_mutating_cart_or_stock(self):
        with self.Session() as db:
            result = create_order_from_cart(
                db=db,
                buyer_id=self.buyer_id,
                shipping_address_id=None,
                payment_method=PaymentMethodEnum.CARD,
                idempotency_key=f"card-disabled-{self.marker}",
            )
            self.assertIsInstance(result, str)
            self.assertIn("unavailable", result)

        with self.Session() as db:
            self.assertEqual(db.get(ProductVariant, self.variant_id).quantity_in_stock, 1)
            self.assertEqual(
                db.query(CartItem).filter(CartItem.cart_session_id == self.cart_id).count(),
                1,
            )
            self.assertEqual(
                db.query(CheckoutOrder).filter(CheckoutOrder.buyer_id == self.buyer_id).count(),
                0,
            )

    def test_cod_progresses_and_records_settlement_without_wallet_entries(self):
        with self.Session() as db:
            checkout = create_order_from_cart(
                db=db,
                buyer_id=self.buyer_id,
                shipping_address_id=None,
                payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
                idempotency_key=f"cod-lifecycle-{self.marker}",
            )
            self.assertIsInstance(checkout, CheckoutOrder)
            seller_order_id = checkout.seller_orders[0].id

        with self.Session() as db:
            payment = db.query(OrderPayment).filter(
                OrderPayment.seller_order_id == seller_order_id
            ).one()
            self.assertEqual(payment.status, PaymentStatusEnum.PENDING)
            self.assertEqual(payment.amount, 1250.0)
            self.assertEqual(payment.platform_fee, 50.0)
            self.assertEqual(payment.seller_amount, 1200.0)

        for status in (
            OrderStatusEnum.PROCESSING,
            OrderStatusEnum.SHIPPED,
            OrderStatusEnum.DELIVERED,
        ):
            with self.Session() as db:
                result = update_order_status(
                    db=db,
                    seller_order_id=seller_order_id,
                    new_status=status,
                    actor_id=self.seller_id if status != OrderStatusEnum.DELIVERED else self.buyer_id,
                    tracking_number="COD-TRACK-1" if status == OrderStatusEnum.SHIPPED else None,
                )
                self.assertEqual(result.status, status)

        with self.Session() as db:
            completed = release_escrow(
                db=db,
                seller_order_id=seller_order_id,
                actor_id=self.buyer_id,
            )
            self.assertEqual(completed.status, OrderStatusEnum.COMPLETED)

        with self.Session() as db:
            payment = db.query(OrderPayment).filter(
                OrderPayment.seller_order_id == seller_order_id
            ).one()
            self.assertEqual(payment.status, PaymentStatusEnum.SETTLED)
            self.assertEqual(payment.recorded_by_id, self.buyer_id)
            self.assertIsNotNone(payment.settled_at)
            self.assertEqual(
                db.query(Transaction)
                .filter(Transaction.reference_id == seller_order_id)
                .count(),
                0,
            )


if __name__ == "__main__":
    unittest.main()
