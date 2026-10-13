import io
import os
import unittest
from unittest.mock import patch

from PIL import Image

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.services.media_fetch import (
    MAX_IMAGE_BYTES,
    UnsafeMediaUrl,
    load_platform_image,
    validate_platform_image_url,
)


class FakeResponse:
    def __init__(self, chunks=(), content_type="image/png", content_length=None, status_code=200):
        self._chunks = chunks
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.closed = False

    @property
    def is_redirect(self):
        return 300 <= self.status_code < 400

    @property
    def is_permanent_redirect(self):
        return self.status_code in (301, 308)

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        return iter(self._chunks)

    def close(self):
        self.closed = True


class MediaFetchSecurityTests(unittest.TestCase):
    def setUp(self):
        self.cloudinary = patch.dict(os.environ, {"CLOUDINARY_CLOUD_NAME": "thrift-kro"})
        self.cloudinary.start()
        self.approved_url = (
            "https://res.cloudinary.com/thrift-kro/image/upload/"
            "v123/thriftkro/products/example.png"
        )

    def tearDown(self):
        self.cloudinary.stop()

    def test_accepts_only_configured_cloudinary_namespace(self):
        self.assertEqual(validate_platform_image_url(self.approved_url), self.approved_url)

        blocked_urls = (
            "http://res.cloudinary.com/thrift-kro/image/upload/example.png",
            "https://127.0.0.1/internal.png",
            "https://169.254.169.254/latest/meta-data/",
            "https://res.cloudinary.com/another-cloud/image/upload/example.png",
            "https://res.cloudinary.com.evil.example/thrift-kro/image/upload/example.png",
            "https://user@res.cloudinary.com/thrift-kro/image/upload/example.png",
        )
        for url in blocked_urls:
            with self.subTest(url=url), self.assertRaises(UnsafeMediaUrl):
                validate_platform_image_url(url)

    def test_rejected_url_never_reaches_http_client(self):
        with patch("app.services.media_fetch.requests.get") as request:
            with self.assertRaises(UnsafeMediaUrl):
                load_platform_image("http://169.254.169.254/latest/meta-data/")
        request.assert_not_called()

    def test_download_is_streamed_without_redirects_and_decodes_valid_image(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (2, 2), color="red").save(image_bytes, format="PNG")
        response = FakeResponse(chunks=[image_bytes.getvalue()])

        with patch("app.services.media_fetch.requests.get", return_value=response) as request:
            image = load_platform_image(self.approved_url)

        self.assertEqual(image.size, (2, 2))
        self.assertTrue(response.closed)
        request.assert_called_once_with(
            self.approved_url,
            allow_redirects=False,
            stream=True,
            timeout=(3.05, 10),
        )

    def test_rejects_oversized_and_redirected_responses(self):
        oversized = FakeResponse(content_length=MAX_IMAGE_BYTES + 1)
        with patch("app.services.media_fetch.requests.get", return_value=oversized):
            with self.assertRaisesRegex(UnsafeMediaUrl, "maximum download size"):
                load_platform_image(self.approved_url)

        redirected = FakeResponse(status_code=302)
        with patch("app.services.media_fetch.requests.get", return_value=redirected):
            with self.assertRaisesRegex(UnsafeMediaUrl, "redirects"):
                load_platform_image(self.approved_url)


if __name__ == "__main__":
    unittest.main()
