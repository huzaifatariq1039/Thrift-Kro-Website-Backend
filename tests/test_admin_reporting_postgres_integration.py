import os
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.order import (
    CheckoutOrder,
    OrderPayment,
    OrderStatusEnum,
    PaymentMethodEnum,
    PaymentStatusEnum,
    SellerOrder,
)
from app.models.user import RoleEnum, User
from app.services.admin_reporting import get_platform_stats


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class AdminReportingPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.marker = uuid.uuid4().hex
        with self.Session() as db:
            self.before = get_platform_stats(db)
            buyer = self._user(RoleEnum.BUYER, "buyer")
            sellers = [
                self._user(RoleEnum.SELLER, "seller-one"),
                self._user(RoleEnum.SELLER, "seller-two"),
            ]
            admin = self._user(RoleEnum.ADMIN, "admin")
            db.add_all([buyer, *sellers, admin])
            db.flush()

            completed_checkout = CheckoutOrder(
                buyer_id=buyer.id,
                total_amount=Decimal("3350.00"),
                currency="PKR",
                payment_method=PaymentMethodEnum.WALLET,
            )
            open_checkout = CheckoutOrder(
                buyer_id=buyer.id,
                total_amount=Decimal("625.00"),
                currency="PKR",
                payment_method=PaymentMethodEnum.WALLET,
            )
            closed_checkout = CheckoutOrder(
                buyer_id=buyer.id,
                total_amount=Decimal("520.00"),
                currency="PKR",
                payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
            )
            db.add_all([completed_checkout, open_checkout, closed_checkout])
            db.flush()

            settled_orders = [
                self._seller_order(
                    completed_checkout.id,
                    sellers[0].id,
                    subtotal="1000.00",
                    shipping="100.00",
                    fee="50.00",
                    status=OrderStatusEnum.COMPLETED_PAYOUT,
                ),
                self._seller_order(
                    completed_checkout.id,
                    sellers[1].id,
                    subtotal="2000.00",
                    shipping="100.00",
                    fee="100.00",
                    status=OrderStatusEnum.COMPLETED,
                ),
            ]
            held_order = self._seller_order(
                open_checkout.id,
                sellers[0].id,
                subtotal="500.00",
                shipping="100.00",
                fee="25.00",
                status=OrderStatusEnum.PAID_FUNDS_IN_ESCROW,
            )
            cancelled_order = self._seller_order(
                closed_checkout.id,
                sellers[0].id,
                subtotal="400.00",
                shipping="100.00",
                fee="20.00",
                status=OrderStatusEnum.CANCELLED,
            )
            db.add_all([*settled_orders, held_order, cancelled_order])
            db.flush()

            now = datetime.now(timezone.utc)
            payments = [
                self._payment(order, PaymentStatusEnum.SETTLED, now)
                for order in settled_orders
            ]
            payments.extend(
                [
                    self._payment(held_order, PaymentStatusEnum.HELD),
                    self._payment(cancelled_order, PaymentStatusEnum.CANCELLED, now),
                ]
            )
            db.add_all(payments)
            db.commit()

            self.user_ids = [buyer.id, *(seller.id for seller in sellers), admin.id]
            self.checkout_ids = [
                completed_checkout.id,
                open_checkout.id,
                closed_checkout.id,
            ]

    def tearDown(self):
        with self.Session() as db:
            db.query(CheckoutOrder).filter(
                CheckoutOrder.id.in_(self.checkout_ids)
            ).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(self.user_ids)).delete(
                synchronize_session=False
            )
            db.commit()

    def _user(self, role: RoleEnum, label: str) -> User:
        return User(
            email=f"report-{label}-{self.marker}@example.test",
            full_name=f"Report {label}",
            hex_code=f"report-{label}-{self.marker}",
            role=role,
        )

    @staticmethod
    def _seller_order(
        checkout_id,
        seller_id,
        *,
        subtotal: str,
        shipping: str,
        fee: str,
        status: OrderStatusEnum,
    ) -> SellerOrder:
        return SellerOrder(
            checkout_order_id=checkout_id,
            seller_id=seller_id,
            subtotal=Decimal(subtotal),
            shipping_fee=Decimal(shipping),
            platform_fee=Decimal(fee),
            total_amount=Decimal(subtotal) + Decimal(shipping) + Decimal(fee),
            currency="PKR",
            status=status,
        )

    @staticmethod
    def _payment(
        order: SellerOrder,
        status: PaymentStatusEnum,
        settled_at=None,
    ) -> OrderPayment:
        return OrderPayment(
            seller_order_id=order.id,
            payment_method=(
                PaymentMethodEnum.CASH_ON_DELIVERY
                if status == PaymentStatusEnum.CANCELLED
                else PaymentMethodEnum.WALLET
            ),
            status=status,
            amount=order.total_amount,
            platform_fee=order.platform_fee,
            seller_amount=order.subtotal + order.shipping_fee,
            currency="PKR",
            settled_at=settled_at,
        )

    def test_metrics_use_checkout_units_and_settled_payment_states(self):
        with self.Session() as db:
            after = get_platform_stats(db)

        self.assertEqual(after.users.total_users - self.before.users.total_users, 4)
        self.assertEqual(after.users.admins - self.before.users.admins, 1)
        self.assertEqual(
            after.orders.total_checkout_orders
            - self.before.orders.total_checkout_orders,
            3,
        )
        self.assertEqual(
            after.orders.total_seller_orders - self.before.orders.total_seller_orders,
            4,
        )
        self.assertEqual(
            after.orders.open_checkout_orders - self.before.orders.open_checkout_orders,
            1,
        )
        self.assertEqual(
            after.orders.completed_checkout_orders
            - self.before.orders.completed_checkout_orders,
            1,
        )
        self.assertEqual(
            after.orders.closed_checkout_orders
            - self.before.orders.closed_checkout_orders,
            1,
        )
        self.assertEqual(
            after.revenue.settled_gmv_pkr - self.before.revenue.settled_gmv_pkr,
            Decimal("3000.00"),
        )
        self.assertEqual(
            after.revenue.settled_payment_volume_pkr
            - self.before.revenue.settled_payment_volume_pkr,
            Decimal("3350.00"),
        )
        self.assertEqual(
            after.revenue.recognized_platform_revenue_pkr
            - self.before.revenue.recognized_platform_revenue_pkr,
            Decimal("150.00"),
        )
        self.assertEqual(
            after.revenue.escrow_held_pkr - self.before.revenue.escrow_held_pkr,
            Decimal("625.00"),
        )


if __name__ == "__main__":
    unittest.main()
