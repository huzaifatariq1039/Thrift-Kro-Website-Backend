import inspect
import os
import unittest
from pathlib import Path

from sqlalchemy import Index

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import sellers
from app.crud import seller_verification
from app.models.seller_verification import SellerVerificationRequest


class KYCSubmissionIntegrityTests(unittest.TestCase):
    def test_pending_request_and_history_indexes_are_in_model_metadata(self):
        indexes = {
            index.name: index
            for index in SellerVerificationRequest.__table__.indexes
            if isinstance(index, Index)
        }

        pending = indexes["uq_seller_verification_one_pending"]
        self.assertTrue(pending.unique)
        self.assertIn(
            "PENDING",
            str(pending.dialect_options["postgresql"]["where"]),
        )
        self.assertIn("idx_seller_verification_seller_created", indexes)

    def test_rate_limit_uses_database_aggregates_and_aware_timestamps(self):
        source = inspect.getsource(seller_verification.check_rate_limit)

        self.assertIn("sa_func.count", source)
        self.assertIn("sa_func.lag", source)
        self.assertNotIn(".all()", source)
        self.assertNotIn("replace(tzinfo", source)

    def test_creation_serializes_on_seller_and_owns_rollback(self):
        source = inspect.getsource(seller_verification.create_verification_request)

        self.assertLess(source.index("with_for_update"), source.index("check_rate_limit"))
        self.assertIn("db.flush()", source)
        self.assertIn("db.rollback()", source)
        self.assertIn("uq_seller_verification_one_pending", source)

    def test_status_fetches_only_latest_request(self):
        source = inspect.getsource(sellers.get_my_verification_status)

        self.assertIn("get_latest_request_by_seller", source)
        self.assertNotIn("get_requests_by_seller", source)

    def test_migration_preflights_existing_pgadmin_rows_before_indexing(self):
        migration = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "20261016_13_kyc_submission_invariants.py"
        ).read_text(encoding="utf-8")

        self.assertIn("HAVING COUNT(*) > 1", migration)
        upgrade_start = migration.index("def upgrade")
        self.assertLess(
            migration.index("_assert_no_duplicate_pending_requests()", upgrade_start),
            migration.index("op.create_index", upgrade_start),
        )


if __name__ == "__main__":
    unittest.main()
