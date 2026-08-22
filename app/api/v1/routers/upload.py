from fastapi import APIRouter, Depends, UploadFile, File
from app.services.upload import upload_image_to_cloudinary
from app.api.deps import get_current_verified_seller

router = APIRouter()

@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    current_seller=Depends(get_current_verified_seller)
):
    """
    Uploads a product image to Cloudinary and returns the public URL.
    Requires the user to be a verified seller.
    Max size: 5MB.
    """
    url = await upload_image_to_cloudinary(file)
    return {"url": url}
