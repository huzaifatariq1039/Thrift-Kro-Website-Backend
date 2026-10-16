import os
import threading
import unittest
import uuid

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.seller_verification import (
    VerificationSubmissionBlockedError,
    create_verification_request,
)
from app.models.seller_verification import SellerVerificationRequest
from app.models.user import (
    BusinessTypeEnum,
    RoleEnum,
    SellerProfile,
    User,
    VerificationStatusEnum,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class KYCSubmissionIntegrityPostgresIntegrationTests(unittest.TestCase):
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
            user = User(
                email=f"kyc-{self.marker}@example.test",
                full_name="KYC Seller",
                hex_code=f"kyc-{self.marker}",
                role=RoleEnum.SELLER,
            )
            db.add(user)
            db.flush()
            profile = SellerProfile(
                user_id=user.id,
                shop_name="KYC Shop",
                verification_status=VerificationStatusEnum.UNVERIFIED,
                is_verified=False,
            )
            db.add(profile)
            db.commit()
            self.user_id = user.id
            self.profile_id = profile.id

    def tearDown(self):
        with self.Session() as db:
            db.query(SellerVerificationRequest).filter(
                SellerVerificationRequest.seller_profile_id == self.profile_id
            ).delete(synchronize_session=False)
            db.query(SellerProfile).filter(SellerProfile.id == self.profile_id).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id == self.user_id).delete(
                synchronize_session=False
            )
            db.commit()

    def _payload(self, suffix: str) -> dict:
        return {
            "business_name": f"KYC Shop {suffix}",
            "business_type": BusinessTypeEnum.INDIVIDUAL,
            "phone_number": "+923001234567",
            "address": "Private address",
            "city": "Lahore",
            "cnic_number": "00000-0000000-0",
            "cnic_front_url": f"private://kyc/{self.marker}/{suffix}/front",
            "cnic_back_url": f"private://kyc/{self.marker}/{suffix}/back",
        }

    def test_concurrent_submissions_create_exactly_one_pending_request(self):
        barrier = threading.Barrier(2)
        outcomes = []

        def submit(index: int):
            try:
                with self.Session() as db:
                    barrier.wait(timeout=5)
                    create_verification_request(
                        db,
                        self.profile_id,
                        self._payload(str(index)),
                    )
                outcomes.append("created")
            except VerificationSubmissionBlockedError:
                outcomes.append("blocked")

        threads = [
            threading.Thread(target=submit, args=(index,), daemon=True)
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["created", "blocked"])
        with self.Session() as db:
            pending_count = (
                db.query(SellerVerificationRequest)
                .filter(
                    SellerVerificationRequest.seller_profile_id == self.profile_id,
                    SellerVerificationRequest.status == VerificationStatusEnum.PENDING,
                )
                .count()
            )
        self.assertEqual(pending_count, 1)

    def test_fourth_submission_in_rolling_window_is_frozen(self):
        for index in range(3):
            with self.Session() as db:
                request = create_verification_request(
                    db,
                    self.profile_id,
                    self._payload(str(index)),
                )
                request.status = VerificationStatusEnum.REJECTED
                request.seller_profile.verification_status = VerificationStatusEnum.REJECTED
                db.commit()

        with self.Session() as db:
            with self.assertRaises(VerificationSubmissionBlockedError) as blocked:
                create_verification_request(
                    db,
                    self.profile_id,
                    self._payload("fourth"),
                )

        self.assertEqual(blocked.exception.submissions_in_window, 3)
        self.assertIsNotNone(blocked.exception.freeze_until)

    def test_migrated_database_has_pending_and_history_indexes(self):
        indexes = {
            index["name"]: index
            for index in inspect(self.engine).get_indexes(
                "seller_verification_requests"
            )
        }

        self.assertTrue(indexes["uq_seller_verification_one_pending"]["unique"])
        self.assertIn("idx_seller_verification_seller_created", indexes)


if __name__ == "__main__":
    unittest.main()
