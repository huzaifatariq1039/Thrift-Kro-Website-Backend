from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.user import BusinessTypeEnum, VerificationStatusEnum
from pydantic import Field

class VerificationProductSchema(BaseModel):
    name: str
    category: Optional[str] = None
    sizes: str
    price: str
    description: str
    images: List[str]


class SellerVerificationCreate(BaseModel):
    """Seller submits this to apply for verification."""
    business_name: str
    business_type: BusinessTypeEnum
    phone_number: str
    address: str
    city: str
    cnic_number: Optional[str] = None
    cnic_front_url: str
    cnic_back_url: str
    shop_photo_urls: List[str] = []
    products_proof: List[VerificationProductSchema] = []
    ai_verified: bool = False
    business_reg_url: Optional[str] = None


class SellerVerificationResponse(BaseModel):
    """Response showing a verification request's details."""
    id: UUID
    seller_profile_id: UUID
    business_name: str
    business_type: BusinessTypeEnum
    phone_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    cnic_number: Optional[str] = None
    cnic_front_url: str
    cnic_back_url: str
    business_reg_url: Optional[str] = None
    status: VerificationStatusEnum
    rejection_reason: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SellerVerificationReview(BaseModel):
    """Admin uses this to approve or reject a verification request."""
    status: VerificationStatusEnum  # Must be APPROVED or REJECTED
    rejection_reason: Optional[str] = None


class SellerVerificationStatusResponse(BaseModel):
    """Summary of a seller's verification state."""
    verification_status: VerificationStatusEnum
    is_verified: bool
    submissions_today: int
    max_submissions_per_day: int = 3
    can_submit: bool
    freeze_until: Optional[datetime] = None
    latest_request: Optional[SellerVerificationResponse] = None
