import asyncio
import logging
import os
import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, HTTPException
import uuid

from app.services.image_security import (
    ImageValidationError,
    read_validated_image_upload,
)


logger = logging.getLogger(__name__)

# Initialize Cloudinary using environment variables
# Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET in .env
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


async def upload_image_to_cloudinary(file: UploadFile) -> str:
    """
    Validates and uploads an image file to Cloudinary.
    Returns the secure HTTPS URL of the uploaded image.
    """
    try:
        validated = await read_validated_image_upload(file)
    except ImageValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        # Generate a unique filename prefix to avoid collisions
        unique_filename = f"thriftkro_{uuid.uuid4().hex[:8]}"

        # Upload using cloudinary
        result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            validated.content,
            public_id=unique_filename,
            folder="thriftkro/products",
            resource_type="image",
            format=validated.extension,
        )

        secure_url = result.get("secure_url")
        if not secure_url or not secure_url.startswith("https://"):
            raise RuntimeError("Storage provider returned no secure URL")
        return secure_url
    except Exception as exc:
        logger.error(
            "Image upload to storage failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=502, detail="Image storage is temporarily unavailable") from exc
