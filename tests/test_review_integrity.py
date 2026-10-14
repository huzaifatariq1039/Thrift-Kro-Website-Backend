import inspect
import os
import unittest

from pydantic import ValidationError

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import reviews, stores
from app.crud.review import get_reviews_by_product
from app.models.order import OrderItem
from app.models.review import Review
from app.schemas.review import ReviewCreate
from app.services.review_integrity import (
    _recalculate_seller_rating,
    create_verified_review,
)


class ReviewIntegrityContractTests(unittest.TestCase):
    def test_verified_reviews_require_order_item_proof(self):
        self.assertFalse(Review.__table__.c.is_verified_purchase.default.arg)
        foreign_key = next(iter(Review.__table__.c.order_item_id.foreign_keys))
        self.assertEqual(foreign_key.ondelete, "RESTRICT")
        constraint_names = {constraint.name for constraint in Review.__table__.constraints}
        self.assertIn("reviews_verified_requires_order_item", constraint_names)

    def test_database_uniqueness_protects_concurrent_review_creation(self):
        indexes = {index.name: index for index in Review.__table__.indexes}
        self.assertTrue(indexes["uq_reviews_verified_buyer_product"].unique)
        self.assertTrue(indexes["uq_reviews_order_item"].unique)
        self.assertIsNotNone(
            indexes["uq_reviews_verified_buyer_product"].dialect_options["postgresql"]["where"]
        )

    def test_order_deletion_does_not_orphan_or_delete_review_proof(self):
        cascade = OrderItem.reviews.property.cascade
        self.assertNotIn("delete", cascade)
        self.assertNotIn("delete-orphan", cascade)

    def test_creation_locks_proof_and_aggregate_then_recalculates(self):
        source = inspect.getsource(create_verified_review)
        self.assertIn("OrderItem.product_id_snapshot == review.product_id", source)
        self.assertIn("with_for_update(of=OrderItem)", source)
        self.assertIn("with_for_update()", source)
        self.assertIn(
            "func.avg(Review.rating)",
            inspect.getsource(_recalculate_seller_rating),
        )
        self.assertIn("is_verified_purchase=True", source)

    def test_public_reads_and_rankings_only_use_trusted_reviews(self):
        self.assertIn(
            "Review.is_verified_purchase.is_(True)",
            inspect.getsource(get_reviews_by_product),
        )
        self.assertIn("get_current_buyer", inspect.getsource(reviews.submit_review))
        ranking_source = inspect.getsource(stores.get_store_rankings)
        self.assertIn("SellerProfile.review_count > 0", ranking_source)
        self.assertIn("VerificationStatusEnum.APPROVED", ranking_source)

    def test_review_comment_is_bounded_and_normalized(self):
        payload = ReviewCreate(
            product_id="00000000-0000-0000-0000-000000000001",
            rating=5,
            comment="  Great item  ",
        )
        self.assertEqual(payload.comment, "Great item")
        with self.assertRaises(ValidationError):
            ReviewCreate(
                product_id="00000000-0000-0000-0000-000000000001",
                rating=5,
                comment="x" * 2001,
            )


if __name__ == "__main__":
    unittest.main()
