import inspect
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import sellers
from app.models.user import VerificationStatusEnum
from app.schemas.kyc import KYCRequestMetadataResponse


SENSITIVE_FIELDS = {
    "address",
    "business_reg_url",
    "cnic_back_url",
    "cnic_front_url",
    "cnic_number",
    "phone_number",
    "products_proof",
    "shop_photo_urls",
}


class RecordingSession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class KYCPrivacyGateTests(unittest.TestCase):
    def test_kyc_metadata_contract_excludes_identity_and_document_fields(self):
        self.assertTrue(SENSITIVE_FIELDS.isdisjoint(KYCRequestMetadataResponse.model_fields))

    def test_submission_and_review_fail_closed_without_accepting_payloads(self):
        with self.assertRaises(HTTPException) as submission:
            sellers.submit_verification(current_seller=object())
        self.assertEqual(submission.exception.status_code, 503)

        with self.assertRaises(HTTPException) as review:
            sellers.review_verification_request(
                request_id=uuid4(),
                admin=object(),
            )
        self.assertEqual(review.exception.status_code, 503)

        self.assertNotIn("data", inspect.signature(sellers.submit_verification).parameters)
        self.assertNotIn("review", inspect.signature(sellers.review_verification_request).parameters)

    def test_seller_status_returns_only_minimized_request_metadata(self):
        request = SimpleNamespace(
            id=uuid4(),
            seller_profile_id=uuid4(),
            status=VerificationStatusEnum.PENDING,
            created_at=datetime.now(timezone.utc),
            reviewed_at=None,
            cnic_number="12345-1234567-1",
            cnic_front_url="https://public.example.test/front.jpg",
        )
        profile = SimpleNamespace(
            id=request.seller_profile_id,
            verification_status=VerificationStatusEnum.PENDING,
            is_verified=False,
        )
        seller = SimpleNamespace(seller_profile=profile)

        with (
            patch.object(
                sellers.crud_sv,
                "check_rate_limit",
                return_value=(False, 1, None),
            ),
            patch.object(
                sellers.crud_sv,
                "get_requests_by_seller",
                return_value=[request],
            ),
        ):
            result = sellers.get_my_verification_status(db=object(), current_seller=seller)

        serialized = result.model_dump()
        self.assertFalse(serialized["can_submit"])
        self.assertTrue(SENSITIVE_FIELDS.isdisjoint(serialized["latest_request"]))

    def test_admin_metadata_access_is_audited_without_sensitive_details(self):
        request_id = uuid4()
        request = SimpleNamespace(id=request_id)
        admin = SimpleNamespace(id=uuid4())
        db = RecordingSession()

        with (
            patch.object(
                sellers.crud_sv,
                "get_verification_request",
                return_value=request,
            ),
            patch.object(sellers, "record_audit_event") as audit,
        ):
            result = sellers.get_verification_request(
                request_id=request_id,
                db=db,
                admin=admin,
            )

        self.assertIs(result, request)
        self.assertEqual(db.commits, 1)
        audit.assert_called_once_with(
            db,
            actor_id=admin.id,
            action="seller_verification.metadata_viewed",
            resource_type="seller_verification_request",
            resource_id=request_id,
        )
        self.assertNotIn("details", audit.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
