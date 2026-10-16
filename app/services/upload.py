import asyncio
import logging
import os
import uuid

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.services.image_security import (
    ImageValidationError,
    read_validated_image_upload,
)
from app.services.provider_resilience import (
    ProviderCircuitBreaker,
    ProviderCircuitOpenError,
    RetryPolicy,
    call_with_resilience,
)


logger = logging.getLogger(__name__)
_CLOUDINARY_CIRCUIT = ProviderCircuitBreaker(
    "cloudinary_upload",
    failure_threshold=5,
    recovery_seconds=30,
)
_CLOUDINARY_RETRY_POLICY = RetryPolicy(max_attempts=2, base_delay_seconds=0.1)


def _is_transient_cloudinary_error(exc: Exception) -> bool:
    status_code = getattr(exc, "http_code", None) or getattr(exc, "status_code", None)
    return (
        isinstance(exc, (TimeoutError, Urllib3HTTPError))
        or status_code in {408, 425, 429}
        or (isinstance(status_code, int) and status_code >= 500)
    )


# Initialize Cloudinary using environment variables
# Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET in .env
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
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
            call_with_resilience,
            lambda: cloudinary.uploader.upload(
                validated.content,
                public_id=unique_filename,
                folder="thriftkro/products",
                resource_type="image",
                format=validated.extension,
                overwrite=True,
                timeout=15,
            ),
            circuit=_CLOUDINARY_CIRCUIT,
            retry_if=_is_transient_cloudinary_error,
            policy=_CLOUDINARY_RETRY_POLICY,
        )

        secure_url = result.get("secure_url")
        if not secure_url or not secure_url.startswith("https://"):
            raise RuntimeError("Storage provider returned no secure URL")
        return secure_url
    except ProviderCircuitOpenError as exc:
        logger.warning("Image upload circuit is open")
        raise HTTPException(
            status_code=503,
            detail="Image storage is temporarily unavailable",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except Exception as exc:
        logger.error(
            "Image upload to storage failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=502,
            detail="Image storage is temporarily unavailable",
        ) from exc
