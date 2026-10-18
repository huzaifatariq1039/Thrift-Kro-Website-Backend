import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_verified_seller, get_db
from app.models.media import MediaAsset, MediaStatusEnum
from app.models.user import User
from app.schemas.media import PublicImageUploadResponse
from app.services.media_lifecycle import (
    register_public_product_image,
    schedule_asset_deletion,
)
from app.services.upload import (
    delete_image_from_cloudinary,
    upload_image_to_cloudinary,
)

router = APIRouter()

@router.post(
    "/image",
    response_model=PublicImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """
    Uploads a product image to Cloudinary and returns the public URL.
    Requires the user to be a verified seller.
    Max size: 5MB.
    """
    stored = await upload_image_to_cloudinary(file)
    try:
        asset = register_public_product_image(
            db,
            owner_id=current_seller.id,
            stored=stored,
        )
    except Exception:
        db.rollback()
        try:
            await asyncio.to_thread(
                delete_image_from_cloudinary,
                stored.provider_public_id,
            )
        except Exception:
            pass
        raise
    return PublicImageUploadResponse(
        asset_id=asset.id,
        url=asset.secure_url,
        expires_at=asset.delete_after,
    )


@router.delete("/image/{asset_id}", status_code=status.HTTP_202_ACCEPTED)
def discard_pending_image(
    asset_id: UUID,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """Schedule an unattached upload for provider deletion."""
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id)
        .with_for_update()
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset.owner_id != current_seller.id:
        raise HTTPException(status_code=403, detail="Media asset is not owned by this seller")
    if asset.status != MediaStatusEnum.PENDING:
        raise HTTPException(status_code=409, detail="Only pending media can be discarded")
    schedule_asset_deletion(db, asset=asset)
    db.commit()
    return {"detail": "Media asset scheduled for deletion"}
