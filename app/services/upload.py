import os
import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, HTTPException
import uuid

# Initialize Cloudinary using environment variables
# Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET in .env
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

async def upload_image_to_cloudinary(file: UploadFile) -> str:
    """
    Validates and uploads an image file to Cloudinary.
    Returns the secure HTTPS URL of the uploaded image.
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type: {file.content_type}. Only JPEG, PNG, and WebP are allowed."
        )

    # Read file content to check size and upload
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE_MB}MB."
        )
        
    try:
        # Generate a unique filename prefix to avoid collisions
        unique_filename = f"thriftkro_{uuid.uuid4().hex[:8]}"
        
        # Upload using cloudinary
        result = cloudinary.uploader.upload(
            content,
            public_id=unique_filename,
            folder="thriftkro/products",
            resource_type="image"
        )
        
        return result.get("secure_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
