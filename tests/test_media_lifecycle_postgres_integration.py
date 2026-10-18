from datetime import timedelta
import os
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.media import (
    MediaAsset,
    MediaModerationStatusEnum,
    MediaPurposeEnum,
    MediaStatusEnum,
    MediaVisibilityEnum,
)
from app.models.user import RoleEnum, User
from app.services.media_lifecycle import (
    MediaAssetValidationError,
    claim_public_product_image,
    cleanup_due_media_assets,
    utc_now,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class MediaLifecyclePostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @staticmethod
    def _asset(owner_id, marker, **overrides):
        values = {
            "owner_id": owner_id,
            "provider": "cloudinary",
            "provider_public_id": f"thriftkro/products/{marker}",
            "secure_url": f"https://media.example.test/{marker}.jpg",
            "purpose": MediaPurposeEnum.PRODUCT_IMAGE,
            "visibility": MediaVisibilityEnum.PUBLIC,
            "status": MediaStatusEnum.PENDING,
            "moderation_status": MediaModerationStatusEnum.NOT_REVIEWED,
            "content_type": "image/jpeg",
            "byte_size": 128,
            "width": 10,
            "height": 10,
            "delete_after": utc_now() + timedelta(hours=24),
        }
        values.update(overrides)
        return MediaAsset(**values)

    def test_only_the_owner_can_claim_a_pending_product_upload(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            owner = User(
                email=f"media-owner-{marker}@example.test",
                full_name="Media Owner",
                hex_code=f"media-owner-{marker}",
                role=RoleEnum.SELLER,
            )
            other = User(
                email=f"media-other-{marker}@example.test",
                full_name="Other Seller",
                hex_code=f"media-other-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add_all([owner, other])
            db.flush()
            asset = self._asset(owner.id, marker)
            db.add(asset)
            db.commit()

            with self.assertRaises(MediaAssetValidationError):
                claim_public_product_image(
                    db,
                    owner_id=other.id,
                    secure_url=asset.secure_url,
                )
            db.rollback()

            claimed = claim_public_product_image(
                db,
                owner_id=owner.id,
                secure_url=asset.secure_url,
            )
            db.commit()
            self.assertEqual(claimed.status, MediaStatusEnum.ATTACHED)
            self.assertIsNone(claimed.delete_after)

    def test_cleanup_deletes_due_cloudinary_objects_and_redacts_urls(self):
        marker = uuid.uuid4().hex
        deleted_public_ids = []
        with self.Session() as db:
            owner = User(
                email=f"media-cleanup-{marker}@example.test",
                full_name="Cleanup Owner",
                hex_code=f"media-cleanup-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add(owner)
            db.flush()
            asset = self._asset(
                owner.id,
                marker,
                delete_after=utc_now() - timedelta(seconds=1),
            )
            db.add(asset)
            db.commit()
            asset_id = asset.id

            count = cleanup_due_media_assets(
                db,
                provider_delete=deleted_public_ids.append,
            )
            refreshed = db.get(MediaAsset, asset_id)

            self.assertEqual(count, 1)
            self.assertEqual(deleted_public_ids, [f"thriftkro/products/{marker}"])
            self.assertEqual(refreshed.status, MediaStatusEnum.DELETED)
            self.assertEqual(refreshed.secure_url, f"deleted://{asset_id}")
            self.assertIsNotNone(refreshed.deleted_at)

    def test_cleanup_failure_releases_the_lease_for_a_delayed_retry(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            owner = User(
                email=f"media-retry-{marker}@example.test",
                full_name="Retry Owner",
                hex_code=f"media-retry-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add(owner)
            db.flush()
            asset = self._asset(
                owner.id,
                marker,
                delete_after=utc_now() - timedelta(seconds=1),
            )
            db.add(asset)
            db.commit()
            asset_id = asset.id

            def fail_delete(_provider_public_id):
                raise RuntimeError("provider unavailable")

            count = cleanup_due_media_assets(db, provider_delete=fail_delete)
            refreshed = db.get(MediaAsset, asset_id)

            self.assertEqual(count, 0)
            self.assertEqual(refreshed.status, MediaStatusEnum.DELETION_PENDING)
            self.assertGreater(refreshed.delete_after, utc_now())

    def test_database_rejects_public_kyc_assets(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            owner = User(
                email=f"media-kyc-{marker}@example.test",
                full_name="KYC Owner",
                hex_code=f"media-kyc-{marker}",
                role=RoleEnum.SELLER,
            )
            db.add(owner)
            db.flush()
            asset = self._asset(
                owner.id,
                marker,
                purpose=MediaPurposeEnum.KYC_DOCUMENT,
                visibility=MediaVisibilityEnum.PUBLIC,
            )
            db.add(asset)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
