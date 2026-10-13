import io
import os
import re
from urllib.parse import urlsplit

import requests
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CLOUDINARY_IMAGE_HOST = "res.cloudinary.com"
_CLOUD_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class UnsafeMediaUrl(ValueError):
    pass


def validate_platform_image_url(url: str) -> str:
    """Accept only HTTPS images in this deployment's Cloudinary namespace."""
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    if not cloud_name or not _CLOUD_NAME_PATTERN.fullmatch(cloud_name):
        raise UnsafeMediaUrl("Platform media storage is not configured")

    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise UnsafeMediaUrl("Image URL must use HTTPS")
    if parsed.username or parsed.password or parsed.port is not None:
        raise UnsafeMediaUrl("Image URL credentials and custom ports are not allowed")
    if (parsed.hostname or "").lower() != CLOUDINARY_IMAGE_HOST:
        raise UnsafeMediaUrl("Image URL is not on the approved media origin")

    expected_prefix = f"/{cloud_name}/image/upload/"
    if not parsed.path.startswith(expected_prefix):
        raise UnsafeMediaUrl("Image URL is outside the approved media namespace")
    return url


def load_platform_image(url: str) -> Image.Image:
    """Download a bounded image from approved storage without following redirects."""
    approved_url = validate_platform_image_url(url)
    response = requests.get(
        approved_url,
        allow_redirects=False,
        stream=True,
        timeout=(3.05, 10),
    )
    try:
        response.raise_for_status()
        if response.is_redirect or response.is_permanent_redirect:
            raise UnsafeMediaUrl("Media redirects are not allowed")

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise UnsafeMediaUrl("Media response is not an approved image type")

        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise UnsafeMediaUrl("Media response has an invalid content length") from exc
            if declared_size > MAX_IMAGE_BYTES:
                raise UnsafeMediaUrl("Image exceeds the maximum download size")

        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > MAX_IMAGE_BYTES:
                raise UnsafeMediaUrl("Image exceeds the maximum download size")
    finally:
        response.close()

    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise UnsafeMediaUrl("Image exceeds the maximum pixel count")
            image.load()
            return image.convert("RGB")
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise UnsafeMediaUrl("Media response is not a valid image") from exc
