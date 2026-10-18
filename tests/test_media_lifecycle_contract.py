import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import upload as upload_router
from app.models.media import MediaAsset
from app.models.product import ProductImage
from app.services import media_lifecycle


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MediaLifecycleContractTests(unittest.TestCase):
    def test_assets_record_ownership_provider_policy_and_cleanup_state(self):
        columns = MediaAsset.__table__.columns
        for name in (
            "owner_id",
            "provider_public_id",
            "secure_url",
            "purpose",
            "visibility",
            "status",
            "moderation_status",
            "delete_after",
            "deleted_at",
        ):
            with self.subTest(column=name):
                self.assertIn(name, columns)

        constraints = {constraint.name for constraint in MediaAsset.__table__.constraints}
        self.assertIn("media_assets_kyc_private_check", constraints)
        self.assertIn("uq_media_assets_provider_identity", constraints)

    def test_product_images_require_one_managed_asset(self):
        column = ProductImage.__table__.columns.media_asset_id
        self.assertFalse(column.nullable)
        self.assertTrue(column.unique)
        foreign_key = next(iter(column.foreign_keys))
        self.assertEqual(foreign_key.target_fullname, "media_assets.id")
        self.assertEqual(foreign_key.ondelete, "RESTRICT")

    def test_uploads_expire_and_trash_has_a_bounded_retention(self):
        self.assertEqual(media_lifecycle.PENDING_UPLOAD_RETENTION.total_seconds(), 86400)
        self.assertEqual(media_lifecycle.PRODUCT_TRASH_RETENTION.days, 30)
        self.assertEqual(media_lifecycle.MEDIA_DELETE_LEASE.total_seconds(), 900)
        self.assertEqual(media_lifecycle.MEDIA_DELETE_RETRY_DELAY.total_seconds(), 300)
        source = inspect.getsource(upload_router.upload_image)
        self.assertIn("register_public_product_image", source)
        self.assertIn("delete_image_from_cloudinary", source)

    def test_runbook_defines_private_kyc_and_scheduled_cleanup(self):
        policy = (
            PROJECT_ROOT / "docs" / "operations" / "media-lifecycle.md"
        ).read_text(encoding="utf-8")
        self.assertIn("KYC asset can never use `PUBLIC` visibility", policy)
        self.assertIn("python -m scripts.cleanup_media_assets --limit 100", policy)
        self.assertIn("15-minute `DELETING` lease", policy)
        self.assertIn("Semantic image moderation is not automated", policy)

    def test_migration_backfills_existing_product_images_before_not_null(self):
        migration = (
            PROJECT_ROOT
            / "alembic"
            / "versions"
            / "20261018_15_media_asset_lifecycle.py"
        ).read_text(encoding="utf-8")
        backfill_query = "WHERE pi.media_asset_id IS NULL"
        insert_asset = "INSERT INTO media_assets"
        bind_image = "UPDATE product_images SET media_asset_id"
        enforce_not_null = (
            'op.alter_column("product_images", "media_asset_id", nullable=False)'
        )

        for marker in (backfill_query, insert_asset, bind_image, enforce_not_null):
            self.assertIn(marker, migration)
        self.assertLess(migration.index(backfill_query), migration.index(insert_asset))
        self.assertLess(migration.index(insert_asset), migration.index(bind_image))
        self.assertLess(migration.index(bind_image), migration.index(enforce_not_null))


if __name__ == "__main__":
    unittest.main()
