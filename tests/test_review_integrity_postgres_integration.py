import os
import threading
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.order import (
    CheckoutOrder,
    OrderItem,
    OrderStatusEnum,
    PaymentMethodEnum,
    SellerOrder,
)
from app.models.product import ConditionEnum, Product, ProductStatusEnum, ProductVariant
from app.models.review import Review
from app.models.user import RoleEnum, SellerProfile, User, VerificationStatusEnum
from app.schemas.review import ReviewCreate
from app.services.review_integrity import (
    DuplicateReviewError,
    ReviewEligibilityError,
    create_verified_review,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class ReviewIntegrityPostgresIntegrationTests(unittest.TestCase):
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
            seller = User(
                email=f"review-seller-{self.marker}@example.test",
                full_name="Review Seller",
                hex_code=f"review-seller-{self.marker}",
                role=RoleEnum.SELLER,
            )
            buyers = [
                User(
                    email=f"review-buyer-{index}-{self.marker}@example.test",
                    full_name=f"Review Buyer {index}",
                    hex_code=f"review-buyer-{index}-{self.marker}",
                    role=RoleEnum.BUYER,
                )
                for index in range(3)
            ]
            db.add_all([seller, *buyers])
            db.flush()
            profile = SellerProfile(
                user_id=seller.id,
                shop_name="Review Shop",
                verification_status=VerificationStatusEnum.APPROVED,
                is_verified=True,
            )
            product = Product(
                seller_id=seller.id,
                name=f"Review Product {self.marker}",
                condition=ConditionEnum.GOOD,
                price=Decimal("1000.00"),
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add_all([profile, product])
            db.flush()
            variant = ProductVariant(
                product_id=product.id,
                sku=f"review-{self.marker}",
                attributes={},
                quantity_in_stock=5,
            )
            db.add(variant)
            db.flush()

            for index, buyer in enumerate(buyers[:2]):
                checkout = CheckoutOrder(
                    buyer_id=buyer.id,
                    total_amount=Decimal("1000.00"),
                    payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
                    idempotency_key=f"review-{index}-{self.marker}",
                )
                db.add(checkout)
                db.flush()
                seller_order = SellerOrder(
                    checkout_order_id=checkout.id,
                    seller_id=seller.id,
                    subtotal=Decimal("1000.00"),
                    shipping_fee=Decimal("0.00"),
                    platform_fee=Decimal("0.00"),
                    total_amount=Decimal("1000.00"),
                    status=(
                        OrderStatusEnum.DELIVERED
                        if index == 0
                        else OrderStatusEnum.COMPLETED
                    ),
                )
                db.add(seller_order)
                db.flush()
                db.add(
                    OrderItem(
                        seller_order_id=seller_order.id,
                        product_variant_id=variant.id,
                        product_id_snapshot=product.id,
                        product_name_snapshot=product.name,
                        variant_attributes_snapshot={},
                        price_at_purchase=Decimal("1000.00"),
                        quantity=1,
                    )
                )
            db.commit()
            self.seller_id = seller.id
            self.buyer_ids = [buyer.id for buyer in buyers]
            self.product_id = product.id

    def tearDown(self):
        with self.Session() as db:
            db.query(Review).filter(Review.product_id == self.product_id).delete(
                synchronize_session=False
            )
            db.query(CheckoutOrder).filter(
                CheckoutOrder.buyer_id.in_(self.buyer_ids)
            ).delete(synchronize_session=False)
            db.query(Product).filter(Product.id == self.product_id).delete(
                synchronize_session=False
            )
            db.query(SellerProfile).filter(
                SellerProfile.user_id == self.seller_id
            ).delete(synchronize_session=False)
            db.query(User).filter(
                User.id.in_([self.seller_id, *self.buyer_ids])
            ).delete(synchronize_session=False)
            db.commit()

    def test_unpurchased_review_is_rejected(self):
        with self.Session() as db:
            with self.assertRaises(ReviewEligibilityError):
                create_verified_review(
                    db,
                    ReviewCreate(product_id=self.product_id, rating=1),
                    self.buyer_ids[2],
                )
            self.assertEqual(
                db.query(Review).filter(Review.product_id == self.product_id).count(),
                0,
            )

    def test_duplicate_review_is_rejected(self):
        with self.Session() as db:
            payload = ReviewCreate(product_id=self.product_id, rating=5)
            create_verified_review(db, payload, self.buyer_ids[0])
            with self.assertRaises(DuplicateReviewError):
                create_verified_review(db, payload, self.buyer_ids[0])

    def test_concurrent_reviews_produce_exact_verified_aggregate(self):
        barrier = threading.Barrier(2)
        errors = []

        def submit(buyer_id, rating):
            try:
                with self.Session() as db:
                    barrier.wait(timeout=5)
                    create_verified_review(
                        db,
                        ReviewCreate(product_id=self.product_id, rating=rating),
                        buyer_id,
                    )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [
            threading.Thread(target=submit, args=(self.buyer_ids[0], 5), daemon=True),
            threading.Thread(target=submit, args=(self.buyer_ids[1], 3), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        with self.Session() as db:
            profile = db.query(SellerProfile).filter(
                SellerProfile.user_id == self.seller_id
            ).one()
            reviews = db.query(Review).filter(Review.product_id == self.product_id).all()
            self.assertEqual(len(reviews), 2)
            self.assertTrue(all(review.is_verified_purchase for review in reviews))
            self.assertEqual(profile.review_count, 2)
            self.assertEqual(profile.rating, 4.0)


if __name__ == "__main__":
    unittest.main()
