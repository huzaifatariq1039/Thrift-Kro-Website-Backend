import os
import unittest

from fastapi import FastAPI
from pydantic import ValidationError

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers.auth import router as auth_router
from app.models.user import RoleEnum
from app.schemas.user import GoogleAuthRequest, PublicUserCreate


app = FastAPI()
app.include_router(auth_router, prefix="/auth")


class PublicRegistrationRoleTests(unittest.TestCase):
    def test_password_registration_rejects_admin_role(self):
        with self.assertRaises(ValidationError):
            PublicUserCreate(
                email="attacker@example.com",
                full_name="Public User",
                password="ValidPass1!",
                role="ADMIN",
            )

    def test_google_registration_rejects_admin_role(self):
        with self.assertRaises(ValidationError):
            GoogleAuthRequest(id_token="unverified-token", role="ADMIN")

    def test_public_registration_accepts_buyer_and_seller_roles(self):
        for role in (RoleEnum.BUYER, RoleEnum.SELLER):
            with self.subTest(role=role):
                payload = PublicUserCreate(
                    email=f"{role.value.lower()}@example.com",
                    full_name="Public User",
                    password="ValidPass1!",
                    role=role,
                )
                self.assertEqual(payload.role, role)

    def test_openapi_public_role_contract_excludes_admin(self):
        schema = app.openapi()
        components = schema["components"]["schemas"]

        public_role_schema = components["PublicUserCreate"]["properties"]["role"]
        google_role_schema = components["GoogleAuthRequest"]["properties"]["role"]

        self.assertNotIn("ADMIN", public_role_schema["enum"])
        self.assertNotIn("ADMIN", google_role_schema["enum"])
        self.assertEqual(set(public_role_schema["enum"]), {"BUYER", "SELLER"})
        self.assertEqual(set(google_role_schema["enum"]), {"BUYER", "SELLER"})


if __name__ == "__main__":
    unittest.main()
