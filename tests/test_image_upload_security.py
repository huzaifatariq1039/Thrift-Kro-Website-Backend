import asyncio
import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from app.services.image_security import (
    MAX_FRAME_IMAGE_BYTES,
    MAX_UPLOAD_IMAGE_BYTES,
    ImageValidationError,
    decode_base64_image,
    read_validated_image_upload,
    validate_image_bytes,
)
from app.services.upload import upload_image_to_cloudinary


def make_image_bytes(
    image_format: str = "PNG",
    *,
    size: tuple[int, int] = (8, 8),
    color: str = "red",
) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color=color).save(output, format=image_format)
    return output.getvalue()


class FakeUpload:
    def __init__(self, content: bytes, content_type: str | None):
        self.content = content
        self.content_type = content_type
        self.offset = 0
        self.bytes_read = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            size = len(self.content) - self.offset
        chunk = self.content[self.offset:self.offset + size]
        self.offset += len(chunk)
        self.bytes_read += len(chunk)
        return chunk


class ImageUploadSecurityTests(unittest.TestCase):
    def test_upload_limit_is_enforced_while_streaming(self):
        upload = FakeUpload(b"x" * (MAX_UPLOAD_IMAGE_BYTES + 1024), "image/png")

        with self.assertRaises(ImageValidationError) as raised:
            asyncio.run(read_validated_image_upload(upload))

        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(upload.bytes_read, MAX_UPLOAD_IMAGE_BYTES + 1)
        self.assertTrue(all(size <= 64 * 1024 for size in upload.read_sizes))

    def test_declared_mime_must_match_magic_bytes(self):
        upload = FakeUpload(make_image_bytes("PNG"), "image/jpeg")

        with self.assertRaisesRegex(ImageValidationError, "does not match"):
            asyncio.run(read_validated_image_upload(upload))

    def test_non_image_payload_is_rejected_even_with_image_header(self):
        with self.assertRaisesRegex(ImageValidationError, "JPEG, PNG, and WebP"):
            validate_image_bytes(b"not really an image", declared_mime="image/png")

    def test_excessive_dimensions_are_rejected_before_pixel_decode(self):
        content = make_image_bytes("PNG", size=(8193, 1))

        with self.assertRaises(ImageValidationError) as raised:
            validate_image_bytes(content, declared_mime="image/png")

        self.assertEqual(raised.exception.status_code, 413)

    def test_accepted_image_is_safely_reencoded(self):
        original = make_image_bytes("PNG")
        validated = validate_image_bytes(original, declared_mime="image/png")

        self.assertEqual(validated.mime_type, "image/jpeg")
        self.assertEqual(validated.extension, "jpg")
        self.assertNotEqual(validated.content, original)
        with Image.open(io.BytesIO(validated.content)) as decoded:
            self.assertEqual(decoded.format, "JPEG")
            self.assertEqual(decoded.size, (8, 8))
            self.assertNotIn("exif", decoded.info)

    def test_cloudinary_receives_only_safely_reencoded_content(self):
        upload = FakeUpload(make_image_bytes("PNG"), "image/png")
        with patch(
            "app.services.upload.cloudinary.uploader.upload",
            return_value={"secure_url": "https://example.test/safe.jpg"},
        ) as provider_upload:
            url = asyncio.run(upload_image_to_cloudinary(upload))

        self.assertEqual(url, "https://example.test/safe.jpg")
        safe_content = provider_upload.call_args.args[0]
        self.assertTrue(safe_content.startswith(b"\xff\xd8\xff"))
        self.assertEqual(provider_upload.call_args.kwargs["format"], "jpg")

    def test_base64_frame_is_strictly_validated(self):
        with self.assertRaisesRegex(ImageValidationError, "valid base64"):
            decode_base64_image("not!base64")

        oversized = "A" * (4 * ((MAX_FRAME_IMAGE_BYTES + 2) // 3) + 5)
        with self.assertRaises(ImageValidationError) as raised:
            decode_base64_image(oversized)
        self.assertEqual(raised.exception.status_code, 413)

    def test_valid_data_url_uses_decoded_content_type(self):
        content = make_image_bytes("PNG")
        frame = f"data:image/png;base64,{base64.b64encode(content).decode('ascii')}"

        validated = decode_base64_image(frame)

        self.assertEqual(validated.mime_type, "image/png")
        self.assertEqual(validated.image.size, (8, 8))


if __name__ == "__main__":
    unittest.main()
