import inspect
import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import create_order_from_cart, release_escrow, update_order_status
from app.models.ledger import LedgerEntry, LedgerJournal
from app.models.user import Transaction
from app.services.ledger import _post_journal, initialize_wallet_ledger


class DoubleEntryLedgerTests(unittest.TestCase):
    def test_journals_have_unique_idempotency_keys(self):
        unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in LedgerJournal.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("operation_key",), unique_columns)

    def test_entries_require_positive_amounts_and_unique_lines(self):
        constraint_names = {
            constraint.name for constraint in LedgerEntry.__table__.constraints
        }
        self.assertIn("ledger_entries_positive_amount_check", constraint_names)
        self.assertIn("uq_ledger_entries_journal_account_side", constraint_names)

    def test_wallet_projection_references_exactly_one_journal(self):
        column = Transaction.__table__.c.ledger_journal_id
        self.assertFalse(column.nullable)
        self.assertTrue(column.unique)
        self.assertEqual(next(iter(column.foreign_keys)).target_fullname, "ledger_journals.id")

    def test_posting_boundary_rejects_unbalanced_journals(self):
        source = inspect.getsource(_post_journal)
        self.assertIn("debit_total != credit_total", source)
        self.assertIn("journal.posted_at", source)
        self.assertIn("operation_key == operation_key", source)

    def test_all_wallet_mutations_use_the_ledger_boundary(self):
        checkout_source = inspect.getsource(create_order_from_cart)
        refund_source = inspect.getsource(update_order_status)
        payout_source = inspect.getsource(release_escrow)
        self.assertIn("record_wallet_payment", checkout_source)
        self.assertIn("record_wallet_refund", refund_source)
        self.assertIn("record_escrow_payout", payout_source)
        self.assertNotIn(".balance =", checkout_source)
        self.assertNotIn(".balance =", refund_source)
        self.assertNotIn(".balance =", payout_source)

    def test_opening_balance_is_reconciled_before_operations(self):
        source = inspect.getsource(initialize_wallet_ledger)
        self.assertIn("ledger_balance != current_balance", source)
        self.assertIn("wallet-opening:", source)


if __name__ == "__main__":
    unittest.main()
