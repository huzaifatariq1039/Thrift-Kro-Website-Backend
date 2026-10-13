import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.core.config import settings, validate_secret_key


class SecurityConfigurationTests(unittest.TestCase):
    def test_secret_key_is_required(self):
        with self.assertRaisesRegex(ValueError, "strictly required"):
            validate_secret_key(None)

    def test_secret_key_has_minimum_length(self):
        with self.assertRaisesRegex(ValueError, "at least 32"):
            validate_secret_key("too-short")

    def test_exposed_default_secret_is_rejected(self):
        with patch("app.core.config.hashlib.sha256") as sha256:
            sha256.return_value.hexdigest.return_value = (
                "570dad43de1af4c925f92c16a68a50936"
                "da42b7dd6fdeb24850507a1199aac89"
            )
            with self.assertRaisesRegex(ValueError, "known exposed value"):
                validate_secret_key("a-long-enough-secret-used-only-for-this-test")

    def test_strong_explicit_secret_is_accepted(self):
        value = "a-unique-test-secret-that-is-longer-than-32-characters"
        self.assertEqual(validate_secret_key(value), value)

    def test_admin_bootstrap_credentials_are_not_configuration(self):
        self.assertFalse(hasattr(settings, "ADMIN_EMAIL"))
        self.assertFalse(hasattr(settings, "ADMIN_PASSWORD"))


if __name__ == "__main__":
    unittest.main()
