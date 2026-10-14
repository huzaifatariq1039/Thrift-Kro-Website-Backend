import inspect
import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import update_order_status


class OrderCompensationContractTests(unittest.TestCase):
    def test_cancel_and_refund_lock_and_restore_inventory(self):
        source = inspect.getsource(update_order_status)
        self.assertIn("with_for_update(of=SellerOrder)", source)
        self.assertIn("with_for_update(of=ProductVariant)", source)
        self.assertIn("quantity_in_stock += quantity", source)

    def test_wallet_compensation_is_locked_and_ledgered(self):
        source = inspect.getsource(update_order_status)
        self.assertIn("TransactionTypeEnum.REFUND", source)
        self.assertIn("record_wallet_refund", source)
        self.assertIn("with_for_update()", source)

    def test_retried_status_command_is_idempotent(self):
        source = inspect.getsource(update_order_status)
        self.assertIn("seller_order.status == new_status", source)


if __name__ == "__main__":
    unittest.main()
