import asyncio
import base64
import binascii
import io
import math
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_UPLOAD_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FRAME_IMAGE_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_IMAGE_PIXELS = 20_000_000
MAX_FRAME_IMAGE_PIXELS = 4_194_304
MAX_IMAGE_DIMENSION = 8_192
READ_CHUNK_BYTES = 64 * 1024
MAX_CONCURRENT_IMAGE_DECODES = 2

_IMAGE_DECODE_SLOTS = asyncio.Semaphore(MAX_CONCURRENT_IMAGE_DECODES)

_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class AsyncUpload(Protocol):
    content_type: str | None

    async def read(self, size: int = -1) -> bytes:
        ...


class ImageValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    image: Image.Image
    mime_type: str
    extension: str


def _sniff_mime_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _check_dimensions(image: Image.Image, max_pixels: int) -> None:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ImageValidationError("Image dimensions are invalid")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ImageValidationError("Image dimensions exceed the allowed limit", status_code=413)
    if width * height > max_pixels:
        raise ImageValidationError("Image pixel count exceeds the allowed limit", status_code=413)


def _decode_image(content: bytes, expected_mime: str, max_pixels: int) -> Image.Image:
    try:
        with Image.open(io.BytesIO(content)) as source:
            actual_mime = _MIME_BY_FORMAT.get(source.format or "")
            if actual_mime != expected_mime:
                raise ImageValidationError("Image signature does not match its decoded format")
            _check_dimensions(source, max_pixels)
            source.verify()

        with Image.open(io.BytesIO(content)) as source:
            _check_dimensions(source, max_pixels)
            source.load()
            decoded = ImageOps.exif_transpose(source)
            has_alpha = decoded.mode in {"RGBA", "LA"} or (
                decoded.mode == "P" and "transparency" in decoded.info
            )
            return decoded.convert("RGBA" if has_alpha else "RGB")
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("File is not a valid supported image") from exc


def _safely_reencode(image: Image.Image, max_bytes: int) -> tuple[bytes, str, str]:
    output = io.BytesIO()
    if image.mode == "RGBA":
        image.save(output, format="PNG", optimize=True)
        mime_type, extension = "image/png", "png"
    else:
        image.save(output, format="JPEG", quality=88, optimize=True)
        mime_type, extension = "image/jpeg", "jpg"

    content = output.getvalue()
    if len(content) > max_bytes:
        raise ImageValidationError(
            "Safely encoded image exceeds the allowed size",
            status_code=413,
        )
    return content, mime_type, extension


def validate_image_bytes(
    content: bytes,
    *,
    declared_mime: str | None = None,
    max_bytes: int = MAX_UPLOAD_IMAGE_BYTES,
    max_pixels: int = MAX_UPLOAD_IMAGE_PIXELS,
    reencode: bool = True,
) -> ValidatedImage:
    if not content:
        raise ImageValidationError("Image is empty")
    if len(content) > max_bytes:
        raise ImageValidationError("Image exceeds the allowed size", status_code=413)

    sniffed_mime = _sniff_mime_type(content)
    if sniffed_mime is None:
        raise ImageValidationError("Only JPEG, PNG, and WebP images are allowed")

    normalized_declared_mime = (declared_mime or "").split(";", 1)[0].strip().lower()
    if normalized_declared_mime and normalized_declared_mime != sniffed_mime:
        raise ImageValidationError("Declared image type does not match file contents")

    image = _decode_image(content, sniffed_mime, max_pixels)
    _check_dimensions(image, max_pixels)

    if reencode:
        safe_content, safe_mime, extension = _safely_reencode(image, max_bytes)
    else:
        safe_content = content
        safe_mime = sniffed_mime
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[sniffed_mime]

    return ValidatedImage(
        content=safe_content,
        image=image,
        mime_type=safe_mime,
        extension=extension,
    )


async def _validate_image_bytes_bounded(content: bytes, **kwargs) -> ValidatedImage:
    async with _IMAGE_DECODE_SLOTS:
        return await asyncio.to_thread(validate_image_bytes, content, **kwargs)


async def read_validated_image_upload(
    upload: AsyncUpload,
    *,
    max_bytes: int = MAX_UPLOAD_IMAGE_BYTES,
    max_pixels: int = MAX_UPLOAD_IMAGE_PIXELS,
) -> ValidatedImage:
    content = bytearray()
    while True:
        remaining = max_bytes + 1 - len(content)
        chunk = await upload.read(min(READ_CHUNK_BYTES, remaining))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ImageValidationError("Image exceeds the allowed size", status_code=413)

    return await _validate_image_bytes_bounded(
        bytes(content),
        declared_mime=upload.content_type,
        max_bytes=max_bytes,
        max_pixels=max_pixels,
        reencode=True,
    )


def decode_base64_image(value: str) -> ValidatedImage:
    declared_mime: str | None = None
    payload = value.strip()
    if payload.startswith("data:"):
        try:
            header, payload = payload.split(",", 1)
        except ValueError as exc:
            raise ImageValidationError("Image data URL is malformed") from exc
        if not header.endswith(";base64"):
            raise ImageValidationError("Image data URL must contain base64 data")
        declared_mime = header[5:-7].lower()

    max_encoded_length = 4 * math.ceil(MAX_FRAME_IMAGE_BYTES / 3) + 4
    if len(payload) > max_encoded_length:
        raise ImageValidationError("Frame exceeds the allowed size", status_code=413)

    try:
        encoded = payload.encode("ascii")
        content = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ImageValidationError("Frame is not valid base64 data") from exc

    return validate_image_bytes(
        content,
        declared_mime=declared_mime,
        max_bytes=MAX_FRAME_IMAGE_BYTES,
        max_pixels=MAX_FRAME_IMAGE_PIXELS,
        reencode=False,
    )


async def decode_base64_image_bounded(value: str) -> ValidatedImage:
    async with _IMAGE_DECODE_SLOTS:
        return await asyncio.to_thread(decode_base64_image, value)
