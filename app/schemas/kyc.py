"""Data-minimized response contracts for the privacy-gated KYC workflow."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.user import VerificationStatusEnum


class KYCRequestMetadataResponse(BaseModel):
    """Workflow metadata that intentionally excludes identity and document data."""

    id: UUID
    seller_profile_id: UUID
    status: VerificationStatusEnum
    created_at: datetime
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KYCVerificationStateResponse(BaseModel):
    """Seller-visible state without a copy of submitted identity information."""

    verification_status: VerificationStatusEnum
    is_verified: bool
    submissions_today: int
    max_submissions_per_day: int = 3
    can_submit: bool = False
    freeze_until: Optional[datetime] = None
    latest_request: Optional[KYCRequestMetadataResponse] = None
