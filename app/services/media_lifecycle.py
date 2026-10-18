from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.media import (
    MediaAsset,
    MediaModerationStatusEnum,
    MediaPurposeEnum,
    MediaStatusEnum,
    MediaVisibilityEnum,
)
from app.models.product import ProductImage
from app.services.upload import StoredImage


PENDING_UPLOAD_RETENTION = timedelta(hours=24)
PRODUCT_TRASH_RETENTION = timedelta(days=30)
MEDIA_DELETE_LEASE = timedelta(minutes=15)
MEDIA_DELETE_RETRY_DELAY = timedelta(minutes=5)


class MediaAssetValidationError(ValueError):
    """A client tried to attach an unavailable or unauthorized media asset."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def register_public_product_image(
    db: Session,
    *,
    owner_id: UUID,
    stored: StoredImage,
) -> MediaAsset:
    now = utc_now()
    asset = MediaAsset(
        owner_id=owner_id,
        provider="cloudinary",
        provider_public_id=stored.provider_public_id,
        secure_url=stored.secure_url,
        purpose=MediaPurposeEnum.PRODUCT_IMAGE,
        visibility=MediaVisibilityEnum.PUBLIC,
        status=MediaStatusEnum.PENDING,
        moderation_status=MediaModerationStatusEnum.NOT_REVIEWED,
        content_type=stored.content_type,
        byte_size=stored.byte_size,
        width=stored.width,
        height=stored.height,
        delete_after=now + PENDING_UPLOAD_RETENTION,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def claim_public_product_image(
    db: Session,
    *,
    owner_id: UUID,
    secure_url: str,
) -> MediaAsset:
    asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.secure_url == secure_url,
            MediaAsset.owner_id == owner_id,
            MediaAsset.purpose == MediaPurposeEnum.PRODUCT_IMAGE,
            MediaAsset.visibility == MediaVisibilityEnum.PUBLIC,
            MediaAsset.status == MediaStatusEnum.PENDING,
        )
        .with_for_update()
        .one_or_none()
    )
    now = utc_now()
    if asset is None:
        raise MediaAssetValidationError(
            "Product images must be uploaded through the managed upload endpoint"
        )
    if asset.owner_id != owner_id:
        raise MediaAssetValidationError("Product image is not owned by this seller")
    if asset.delete_after is not None and asset.delete_after <= now:
        raise MediaAssetValidationError("Product image upload has expired")

    asset.status = MediaStatusEnum.ATTACHED
    asset.attached_at = now
    asset.delete_after = None
    return asset


def schedule_product_media_deletion(
    db: Session,
    *,
    product_id: UUID,
    retention: timedelta = PRODUCT_TRASH_RETENTION,
) -> None:
    delete_after = utc_now() + retention
    assets = (
        db.query(MediaAsset)
        .join(ProductImage, ProductImage.media_asset_id == MediaAsset.id)
        .filter(ProductImage.product_id == product_id)
        .with_for_update()
        .all()
    )
    for asset in assets:
        if asset.status not in {
            MediaStatusEnum.DELETING,
            MediaStatusEnum.DELETED,
        }:
            asset.status = MediaStatusEnum.DELETION_PENDING
            asset.delete_after = delete_after


def restore_product_media(db: Session, *, product_id: UUID) -> bool:
    assets = (
        db.query(MediaAsset)
        .join(ProductImage, ProductImage.media_asset_id == MediaAsset.id)
        .filter(ProductImage.product_id == product_id)
        .with_for_update()
        .all()
    )
    if not assets or any(
        asset.status in {MediaStatusEnum.DELETING, MediaStatusEnum.DELETED}
        for asset in assets
    ):
        return False
    for asset in assets:
        asset.status = MediaStatusEnum.ATTACHED
        asset.delete_after = None
    return True


def schedule_asset_deletion(
    db: Session,
    *,
    asset: MediaAsset,
    delete_after: datetime | None = None,
) -> None:
    if asset.status == MediaStatusEnum.DELETED:
        return
    asset.status = MediaStatusEnum.DELETION_PENDING
    asset.delete_after = delete_after or utc_now()


def cleanup_due_media_assets(
    db: Session,
    *,
    provider_delete: Callable[[str], None],
    limit: int = 100,
) -> int:
    """Delete expired or retired provider objects without holding a DB transaction."""
    now = utc_now()
    due = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.provider == "cloudinary",
            MediaAsset.status.in_(
                [
                    MediaStatusEnum.PENDING,
                    MediaStatusEnum.DELETION_PENDING,
                    MediaStatusEnum.DELETING,
                ]
            ),
            MediaAsset.delete_after.isnot(None),
            MediaAsset.delete_after <= now,
        )
        .order_by(MediaAsset.delete_after, MediaAsset.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    work = [(asset.id, asset.provider_public_id) for asset in due]
    for asset in due:
        asset.status = MediaStatusEnum.DELETING
        asset.delete_after = now + MEDIA_DELETE_LEASE
    db.commit()

    deleted = 0
    for asset_id, provider_public_id in work:
        try:
            provider_delete(provider_public_id)
        except Exception:
            asset = (
                db.query(MediaAsset)
                .filter(MediaAsset.id == asset_id)
                .with_for_update()
                .one_or_none()
            )
            if asset is not None and asset.status == MediaStatusEnum.DELETING:
                asset.status = MediaStatusEnum.DELETION_PENDING
                asset.delete_after = utc_now() + MEDIA_DELETE_RETRY_DELAY
                db.commit()
            else:
                db.rollback()
            continue

        asset = (
            db.query(MediaAsset)
            .filter(MediaAsset.id == asset_id)
            .with_for_update()
            .one_or_none()
        )
        if asset is None or asset.status != MediaStatusEnum.DELETING:
            db.rollback()
            continue
        asset.status = MediaStatusEnum.DELETED
        asset.deleted_at = utc_now()
        asset.delete_after = None
        asset.secure_url = f"deleted://{asset.id}"
        db.commit()
        deleted += 1
    return deleted
