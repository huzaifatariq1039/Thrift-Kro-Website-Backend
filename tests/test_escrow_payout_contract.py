import inspect
import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import release_escrow
from app.models.user import Transaction


class EscrowPayoutContractTests(unittest.TestCase):
    def test_payout_locks_order_and_wallet(self):
        source = inspect.getsource(release_escrow)
        self.assertIn("with_for_update(of=SellerOrder)", source)
        self.assertIn("with_for_update()", source)

    def test_ledger_operation_reference_is_unique(self):
        constraints = {
            constraint.name: tuple(column.name for column in constraint.columns)
            for constraint in Transaction.__table__.constraints
            if constraint.name
        }
        self.assertEqual(
            constraints["uq_transactions_reference_operation"],
            ("reference_type", "reference_id", "type"),
        )


if __name__ == "__main__":
    unittest.main()
