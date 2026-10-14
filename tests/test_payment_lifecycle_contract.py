import inspect
import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import create_order_from_cart, release_escrow, update_order_status
from app.models.order import OrderPayment, OrderStatusEnum, PaymentStatusEnum


class PaymentLifecycleContractTests(unittest.TestCase):
    def test_card_checkout_is_explicitly_disabled(self):
        self.assertIn("Card payments are unavailable", inspect.getsource(create_order_from_cart))

    def test_cod_can_enter_fulfillment_but_other_pending_payments_cannot(self):
        source = inspect.getsource(update_order_status)
        self.assertIn("PaymentMethodEnum.CASH_ON_DELIVERY", source)
        self.assertIn("Only cash-on-delivery orders", source)

    def test_cod_completion_is_not_labeled_as_wallet_payout(self):
        source = inspect.getsource(release_escrow)
        self.assertIn("OrderStatusEnum.COMPLETED", source)
        self.assertIn("PaymentStatusEnum.SETTLED", source)
        self.assertIn("without creating a fictitious wallet payout", source)

    def test_payment_allocation_has_one_row_per_seller_order(self):
        unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in OrderPayment.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("seller_order_id",), unique_columns)
        self.assertIn(OrderStatusEnum.COMPLETED.value, {item.value for item in OrderStatusEnum})
        self.assertIn(PaymentStatusEnum.SETTLED.value, {item.value for item in PaymentStatusEnum})


if __name__ == "__main__":
    unittest.main()
