import os
import threading
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import release_escrow
from app.models.order import (
    CheckoutOrder,
    OrderStatusEnum,
    PaymentMethodEnum,
    SellerOrder,
)
from app.models.user import (
    RoleEnum,
    Transaction,
    TransactionTypeEnum,
    User,
    Wallet,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class EscrowPayoutPostgresIntegrationTests(unittest.TestCase):
    """Exercise payout row locks; never point this test at application data."""

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
                email=f"payout-buyer-{marker}@example.test",
                full_name="Payout Buyer",
                hex_code=f"payout-buyer-{marker}",
                role=RoleEnum.BUYER,
            )
            seller = User(
                email=f"payout-seller-{marker}@example.test",
                full_name="Payout Seller",
                hex_code=f"payout-seller-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add_all([buyer, seller])
            db.flush()
            wallet = Wallet(user_id=seller.id, balance=0.0)
            checkout = CheckoutOrder(
                buyer_id=buyer.id,
                total_amount=1250.0,
                payment_method=PaymentMethodEnum.WALLET,
                idempotency_key=f"payout-checkout-{marker}",
            )
            db.add_all([wallet, checkout])
            db.flush()
            seller_order = SellerOrder(
                checkout_order_id=checkout.id,
                seller_id=seller.id,
                subtotal=1000.0,
                shipping_fee=200.0,
                platform_fee=50.0,
                total_amount=1250.0,
                status=OrderStatusEnum.DELIVERED,
            )
            db.add(seller_order)
            db.commit()
            self.seller_order_id = seller_order.id
            self.seller_wallet_id = wallet.id

    def test_concurrent_release_credits_seller_once(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def release(index):
            try:
                with self.Session() as db:
                    barrier.wait(timeout=10)
                    results.append(
                        release_escrow(
                            db=db,
                            seller_order_id=self.seller_order_id,
                            actor_id=uuid.uuid4(),
                        )
                    )
            except Exception as exc:  # pragma: no cover - reported by assertion
                errors.append(exc)

        threads = [
            threading.Thread(target=release, args=(index,), daemon=True)
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(any(thread.is_alive() for thread in threads), "payout deadlocked")
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.status == OrderStatusEnum.COMPLETED_PAYOUT for result in results))

        with self.Session() as db:
            wallet = db.get(Wallet, self.seller_wallet_id)
            seller_order = db.get(SellerOrder, self.seller_order_id)
            payouts = (
                db.query(Transaction)
                .filter(
                    Transaction.reference_type == "seller_order",
                    Transaction.reference_id == self.seller_order_id,
                    Transaction.type == TransactionTypeEnum.ESCROW_RELEASE,
                )
                .all()
            )
            self.assertEqual(wallet.balance, 1200.0)
            self.assertEqual(seller_order.status, OrderStatusEnum.COMPLETED_PAYOUT)
            self.assertEqual(len(payouts), 1)
            self.assertEqual(payouts[0].amount, 1200.0)


if __name__ == "__main__":
    unittest.main()
